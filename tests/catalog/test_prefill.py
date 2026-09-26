"""11.5.6 — onay formu sistemin taslağıyla dolu açılır (`app.catalog.prefill`).

Taslak kayıtlı yanıttır (`tests/fixtures/ai/type_proposals/residence_permit/0.json`, sentetik tür
anlatımı; kişisel değer yok). Aday satırları çoğunlukla veritabanısızdır: form yalnız adayın
alanlarından kurulur. Önerilen tür kaydı paketle gelen `suggested_types.csv`'dir (§C86)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.ai.type_proposal import TypeProposal
from app.catalog import (
    Catalog,
    CatalogEntry,
    Sides,
    TypeForm,
    build_entry,
    load_seed_catalog,
    validate_catalog,
)
from app.catalog.describe import format_description
from app.catalog.prefill import (
    FIELD_LABELS,
    SuggestedForm,
    matched_type,
    name_slug,
    prefill_form,
    proposal_form,
    suggested_form,
    suggested_type,
    type_matches,
    unverified_example_count,
    validated_form,
)
from app.catalog.propose import SuggestedType
from app.db.models import (
    CandidateDocumentType,
    CandidateProposalStatus,
    ExampleFileRecord,
    ExampleLabel,
    ExampleMethod,
)
from app.training.known_types import KnownTypes, build_known_types

ROOT = Path(__file__).resolve().parents[2]
PROPOSAL = json.loads(
    (
        ROOT / "tests" / "fixtures" / "ai" / "type_proposals" / "residence_permit" / "0.json"
    ).read_text("utf-8")
)
NAME = "Montenegrin Residence Permit"
GENERATED = datetime(2026, 9, 26, 8, 30, tzinfo=UTC)


@pytest.fixture(scope="module")
def known() -> KnownTypes:
    return build_known_types(load_seed_catalog())


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db_session:
        yield db_session


def _proposal(**overrides: Any) -> TypeProposal:
    """Kayıtlı taslak; `overrides` doğrulamasız uygulanır (sözleşmenin geçirmeyeceği değer de)."""
    return TypeProposal.model_validate(PROPOSAL).model_copy(update=overrides)


def _candidate(
    name: str = NAME,
    proposal: TypeProposal | None = None,
    *,
    status: CandidateProposalStatus | None = None,
    description: str | None = None,
    reason: str | None = None,
) -> CandidateDocumentType:
    """Veritabanısız aday; `proposal` verilirse inceleme `ready` ve taslak saklı."""
    if proposal is not None:
        status = CandidateProposalStatus.READY
    stored = None
    if status is not None:
        stored = {
            "proposal": None if proposal is None else proposal.model_dump(mode="json"),
            "reason": reason,
            "evidence": None,
            "model": "recording",
            "pages": 3 if proposal is not None else 0,
        }
    return CandidateDocumentType(
        proposed_name=name,
        description=description,
        proposal_status=None if status is None else status.value,
        proposal_generated_at=None if status is None else GENERATED,
        proposal_json=stored,
    )


# --- taslaktan form ------------------------------------------------------------------------------


def test_a_ready_candidate_opens_with_every_field_of_the_proposal() -> None:
    proposal = _proposal()

    prefill = suggested_form(_candidate(proposal=proposal))

    assert prefill.form == TypeForm(
        slug="montenegrin_residence_permit",
        name=NAME,
        file_label="Residence Permit",
        country="ME",
        description="Karadağ'da yabancılara verilen oturma izni kartı; ön ve arka yüzlü.",
        expected_file_types=("jpeg", "png"),
        pages_min="1",
        pages_max="2",
        sides="front_back",
        front_back_layouts=("separate", "combined"),
        direct=False,
        analyze=True,
        required_fields="surname, given_names, date_of_birth, document_number, expiry_date",
        allowed_conversions=("merge", "wrap_image"),
        output_format="pdf",
        acceptance_criteria=(
            "Kartın iki yüzü de tam görünür olmalı, kenarlar kesilmemiş",
            "Arka yüzdeki MRZ üç satırı da okunabilir olmalı",
        ),
        prompt_description=format_description(proposal.appearance),
    )
    assert prefill.form.prompt_description.startswith("Kart, yatay;")
    assert "MRZ: 3 satır, arka yüzün altında." in prefill.form.prompt_description
    assert (prefill.filled, prefill.unfilled, prefill.catalog_slug) == (True, (), None)
    assert (prefill.proposal_status, prefill.proposal_pages) == ("ready", 3)
    assert prefill.proposal_generated_at == GENERATED
    # İK değiştirmeden kaydetse de form katalog sözleşmesinden geçer.
    entry = build_entry(prefill.form)
    assert entry.required_fields[0] == "surname"
    assert entry.expected_pages is not None
    assert (entry.expected_pages.min, entry.expected_pages.max) == (1, 2)


def test_a_direct_proposal_opens_without_conversions() -> None:
    form = proposal_form(_proposal(direct=True))

    assert (form.direct, form.allowed_conversions) == (True, ())
    assert validated_form(form) == (form, ())


def test_front_back_pages_are_derived_from_the_layouts() -> None:
    # 11.1.2: taslağın aralığı düzenlerle çelişse de form düzenlerden türeyen aralıkla açılır.
    separate = {
        **PROPOSAL,
        "front_back_layouts": ["separate"],
        "expected_pages": {"min": 1, "max": 3},
    }

    form = proposal_form(TypeProposal.model_validate(separate))

    assert (form.pages_min, form.pages_max) == ("2", "2")
    single = proposal_form(
        _proposal(sides=Sides.SINGLE, front_back_layouts=(), expected_pages=None)
    )
    assert (single.sides, single.pages_min, single.pages_max) == ("single", "", "")


def test_a_field_failing_validation_returns_to_the_default_and_is_named() -> None:
    proposal = _proposal(required_fields=("Surname", "document_number"), country="MNE")

    prefill = prefill_form(_candidate(proposal=proposal), proposal)

    assert prefill.form.required_fields == TypeForm().required_fields
    assert prefill.form.country == TypeForm().country
    assert prefill.unfilled == ("Ülke", "Zorunlu alanlar")
    # Geri kalan alanlar taslaktan gelir ve form geçer.
    assert prefill.form.name == NAME
    assert prefill.form.expected_file_types == ("jpeg", "png")
    build_entry(prefill.form)


def test_a_consistency_violation_empties_the_violating_field() -> None:
    # Analiz edilmeyen türde zorunlu alan olmaz (katalog sözleşmesi): alan boşa döner.
    proposal = _proposal(analyze=False)

    prefill = prefill_form(_candidate(proposal=proposal), proposal)

    assert (prefill.form.analyze, prefill.form.required_fields) == (False, "")
    assert prefill.unfilled == ("Zorunlu alanlar",)
    build_entry(prefill.form)


def test_a_field_invalid_even_by_default_stays_empty_for_hr() -> None:
    # Ön/arka yüzlü taslakta düzen yok: düzen alanı boş kalır (varsayılanı da boş) ve İK'ya
    # bildirilir; yüz yapısı taslağınkidir, tahminle tek yüze çevrilmez.
    proposal = _proposal(front_back_layouts=())

    prefill = prefill_form(_candidate(proposal=proposal), proposal)

    assert (prefill.form.sides, prefill.form.front_back_layouts) == ("front_back", ())
    assert prefill.unfilled == ("Kabul edilen düzenler",)


def test_validated_form_reports_record_fields_in_form_order() -> None:
    form = replace_form(country="MNE", output_format="gif", expected_file_types=("bmp",))

    fixed, reverted = validated_form(form)

    assert reverted == ("country", "expected_file_types", "output_format")
    assert list(reverted) == [name for name in FIELD_LABELS if name in reverted]
    assert (fixed.country, fixed.output_format) == ("", "keep")
    assert fixed.expected_file_types == ("pdf",)


def replace_form(**changes: Any) -> TypeForm:
    base = proposal_form(_proposal())
    return TypeForm(**{**{name: getattr(base, name) for name in base.__slots__}, **changes})


def test_a_name_without_a_valid_slug_leaves_the_slug_to_hr() -> None:
    proposal = _proposal(name="1099 Residence Form")

    prefill = prefill_form(_candidate("1099 Residence Form", proposal), proposal)

    assert prefill.form.slug == ""
    assert prefill.unfilled == ("Slug",)
    assert name_slug("—") == ""
    assert name_slug("A" + " very" * 20) == "a" + "_very" * 12


# --- önerilen tür kaydı ve katalog çakışması -----------------------------------------------------


def test_slug_label_and_country_come_from_the_suggested_type_record(known: KnownTypes) -> None:
    # Adayın adı önerilen kayıttaki bir türe iner: slug hazır örnek klasörüyle aynıdır.
    proposal = _proposal(country="RS")

    prefill = suggested_form(_candidate("Montenegrin  identity card", proposal), known=known)

    assert (prefill.form.slug, prefill.form.file_label, prefill.form.country) == (
        "montenegrin_identity_card",
        "Identity Card",
        "ME",
    )
    assert prefill.suggested_slug == "montenegrin_identity_card"
    assert (prefill.catalog_slug, prefill.unfilled) == (None, ())
    assert prefill.form.name == NAME  # ad taslağındır
    build_entry(prefill.form)


def test_the_proposal_name_also_finds_the_suggested_type(known: KnownTypes) -> None:
    proposal = _proposal(name="Serbian Identity Card", file_label="Card")

    prefill = suggested_form(_candidate("Kartica", proposal), known=known)

    assert (prefill.form.slug, prefill.form.file_label, prefill.form.country) == (
        "serbian_identity_card",
        "Identity Card",
        "RS",
    )


def test_a_record_without_a_country_keeps_the_proposal_country(known: KnownTypes) -> None:
    proposal = _proposal(country="BE")

    prefill = suggested_form(_candidate("EU Birth Certificate", proposal), known=known)

    assert (prefill.form.slug, prefill.form.country) == ("eu_birth_certificate", "BE")


def test_a_candidate_without_a_proposal_still_takes_the_suggested_record(
    known: KnownTypes,
) -> None:
    prefill = suggested_form(_candidate("Serbian Diploma", description="Diploma"), known=known)

    assert (prefill.form.slug, prefill.form.name, prefill.form.file_label) == (
        "serbian_diploma",
        "Serbian Diploma",
        "Diploma",
    )
    assert (prefill.form.country, prefill.form.description) == ("RS", "Diploma")
    assert (prefill.filled, prefill.suggested_slug) == (False, "serbian_diploma")
    assert prefill.form.required_fields == ""  # yapı formun varsayılanı


@pytest.mark.parametrize(
    ("candidate_name", "proposal_name"),
    [
        ("Turkish Driving License", None),  # tek ad iki slug'a iner
        ("Turkish Driving Licence", NAME),  # `licence` → `license`
        ("Serbian Identity Card", "Montenegrin Identity Card"),  # iki ad iki türe
    ],
)
def test_an_ambiguous_name_leaves_the_slug_empty(
    known: KnownTypes, candidate_name: str, proposal_name: str | None
) -> None:
    proposal = None if proposal_name is None else _proposal(name=proposal_name)

    prefill = prefill_form(_candidate(candidate_name, proposal), proposal, known=known)

    assert prefill.form.slug == ""
    assert (prefill.suggested_slug, prefill.catalog_slug) == (None, None)
    assert len(type_matches(known, _candidate(candidate_name), proposal)) == 2
    assert matched_type(known, _candidate(candidate_name), proposal) is None
    if proposal is not None:
        assert prefill.unfilled[0] == "Slug"


def test_a_type_already_in_the_catalog_is_warned_and_the_slug_is_left_empty(
    known: KnownTypes,
) -> None:
    proposal = _proposal(name="Serbian Passport")

    prefill = suggested_form(_candidate("Srpski pasoš", proposal), known=known)

    assert (prefill.form.slug, prefill.catalog_slug, prefill.suggested_slug) == (
        "",
        "serbian_passport",
        None,
    )
    assert prefill.unfilled == ()  # boş slug'ın nedeni uyarıdadır
    assert prefill.form.file_label == "Residence Permit"  # katalog türünden alınmaz


def test_a_derived_slug_taken_in_the_catalog_is_a_conflict_too() -> None:
    catalog = validate_catalog(
        [
            {
                "slug": "montenegrin_residence_permit",
                "name": "Dozvola za boravak",
                "file_label": "Dozvola",
                "expected_file_types": ["pdf"],
                "sides": "single",
                "direct": False,
                "analyze": True,
                "required_fields": [],
                "allowed_conversions": [],
                "output_format": "keep",
            }
        ]
    )
    known = build_known_types(catalog, suggested=())

    prefill = suggested_form(_candidate(proposal=_proposal()), known=known)

    assert (prefill.form.slug, prefill.catalog_slug) == ("", "montenegrin_residence_permit")


def test_an_ambiguous_name_reaching_a_catalog_type_warns_about_it(known: KnownTypes) -> None:
    proposal = _proposal(name="Serbian Passport")

    prefill = prefill_form(_candidate("Serbian Diploma", proposal), proposal, known=known)

    assert (prefill.form.slug, prefill.catalog_slug) == ("", "serbian_passport")


def test_suggested_type_is_the_record_row_of_a_non_catalog_match(known: KnownTypes) -> None:
    assert suggested_type(known, _candidate("Serbian Diploma")) == SuggestedType(
        name="Serbian Diploma", file_label="Diploma", country="RS"
    )
    assert suggested_type(known, _candidate("Serbian Passport")) is None
    assert suggested_type(known, _candidate("Turkish Driving License")) is None
    assert suggested_type(known, _candidate(NAME)) is None


# --- taslaksız ve başarısız aday -----------------------------------------------------------------


def test_a_failed_examination_opens_the_old_form_and_keeps_the_reason() -> None:
    candidate = _candidate(
        "Peruvian Diploma",
        status=CandidateProposalStatus.FAILED,
        reason="Taslakta örnekteki kişiye ait değer bulundu",
    )

    prefill = suggested_form(candidate)

    assert prefill == SuggestedForm(
        form=TypeForm(
            slug="peruvian_diploma", name="Peruvian Diploma", file_label="Peruvian Diploma"
        ),
        filled=False,
        proposal_status="failed",
        proposal_pages=0,
        proposal_generated_at=GENERATED,
        proposal_reason="Taslakta örnekteki kişiye ait değer bulundu",
    )


def test_a_broken_stored_proposal_opens_the_old_form() -> None:
    candidate = _candidate(proposal=_proposal())
    assert candidate.proposal_json is not None
    candidate.proposal_json = {"proposal": {"name": NAME}, "pages": "üç"}

    prefill = suggested_form(candidate)

    assert prefill.filled is False
    assert prefill.form == TypeForm(slug="montenegrin_residence_permit", name=NAME, file_label=NAME)
    assert (prefill.proposal_status, prefill.proposal_pages) == ("ready", None)


# --- doğrulanmamış "AI kararı" örnekleri ---------------------------------------------------------


def test_unverified_examples_count_only_ai_decisions_of_the_slug(session: Session) -> None:
    rows = [
        ("serbian_diploma", "a.jpg", ExampleLabel.AI_DECISION),
        ("serbian_diploma", "b.jpg", ExampleLabel.AI_DECISION),
        ("serbian_diploma", "c.jpg", ExampleLabel.VERIFIED),
        ("serbian_diploma", "d.jpg", None),
        ("serbian_passport", "e.jpg", ExampleLabel.AI_DECISION),
    ]
    session.add_all(
        ExampleFileRecord(
            type_slug=slug,
            name=name,
            sha256=f"{index:064d}",
            method=ExampleMethod.AI.value,
            label=None if label is None else label.value,
        )
        for index, (slug, name, label) in enumerate(rows)
    )
    session.flush()

    assert unverified_example_count(session, "serbian_diploma") == 2
    assert unverified_example_count(session, "serbian_passport") == 1
    assert unverified_example_count(session, "montenegrin_passport") == 0


def test_field_labels_cover_the_catalog_record_fields() -> None:
    form_fields = set(CatalogEntry.model_fields) - {"photo_rules", "active"}

    assert set(FIELD_LABELS) == form_fields
    assert isinstance(load_seed_catalog(), Catalog)
