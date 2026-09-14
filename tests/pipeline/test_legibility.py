"""04.4.1 — zorunlu alanların biri bile okunaksızsa aday Unreadable olur ve eksik alan adları
gerekçeye yazılır; 04.4.2 — türün `acceptance_criteria` maddeleri varsa her biri değerlendirilir,
karşılanmayan madde Unresolved gerekçesine madde adıyla yazılır, liste boşsa tek ölçüt 04.4.1'dir.
Kabul senaryosu: S9.

Birim testleri `check_legibility`'ye sentetik analizlerden kurulmuş adaylar verir. Entegrasyon
testleri sentetik PDF/JPEG'i gerçek render adımlarından, kayıtlı yanıt sağlayıcısıyla (03.6)
analizden ve gruplamadan (04.1–04.3) geçirir — gerçek kişi/belge yok, ağ çağrısı yok.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import PageAnalysis, build_page_analysis_instructions
from app.ai.prompts import load_page_analysis_template
from app.ai.recording_provider import RecordingProvider
from app.catalog import Catalog, load_seed_catalog, validate_catalog
from app.db.models import Event, QueueKind
from app.pipeline.analyze import analyze_upload
from app.pipeline.group import CandidatePage, DocumentCandidate, group_upload
from app.pipeline.legibility import (
    IllegibleRequiredFields,
    LegibilityCheck,
    UnmetAcceptanceCriteria,
    check_legibility,
)
from app.storage import DataLayout
from tests.ai.payloads import analysis_payload
from tests.fixtures.gen import make_half_filled_image_bytes, make_text_pdf_bytes
from tests.pipeline.test_group import _recordings, _upload

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = ROOT / "tests" / "fixtures" / "ai" / "recordings"
CATALOG = load_seed_catalog()
INSTRUCTIONS = build_page_analysis_instructions(CATALOG)
FILE_ID = 7

PASSPORT = "russian_passport"  # single; iki kabul kriteri
LICENSE = "serbian_driving_license"  # front_back; kabul kriteri yok
PHOTO = "profile_picture"  # zorunlu alan yok
REQUIRED = ("surname", "given_names", "date_of_birth", "document_number", "expiry_date")
EDGE_CRITERION = "Kimlik sayfası tam görünür olmalı, kenarlar kesilmemiş"
MRZ_CRITERION = "MRZ iki satırı da okunabilir olmalı"
UNMET = "Karşılanmayan kabul kriteri:"


def _readings(*illegible: str, names: tuple[str, ...] = REQUIRED) -> dict[str, Any]:
    return {
        name: {"value": None, "legible": False}
        if name in illegible
        else {"value": "OKUNDU", "legible": True}
        for name in names
    }


def _analysis(
    index: int = 0,
    slug: str | None = PASSPORT,
    *,
    fields: dict[str, Any] | None = None,
    notes: str | None = None,
    **top: Any,
) -> PageAnalysis:
    payload = analysis_payload(
        page_index=index,
        document_type_slug=slug,
        fields=_readings() if fields is None else fields,
        notes=notes,
        **top,
    )
    return PageAnalysis.model_validate(payload)


def _candidate(*pages: PageAnalysis | tuple[int, PageAnalysis]) -> DocumentCandidate:
    """Sayfalar verilen sırayla; `(file_id, analiz)` başka dosyadaki sayfadır."""
    built = []
    for page in pages:
        file_id, analysis = page if isinstance(page, tuple) else (FILE_ID, page)
        built.append(CandidatePage(file_id, analysis.page_index, analysis))
    return DocumentCandidate(tuple(built))


def _check(
    *pages: PageAnalysis | tuple[int, PageAnalysis], catalog: Catalog = CATALOG
) -> LegibilityCheck:
    check = check_legibility(_candidate(*pages), catalog=catalog)
    assert isinstance(check, LegibilityCheck)
    return check


def _front(*illegible: str, notes: str | None = None) -> PageAnalysis:
    return _analysis(0, LICENSE, side="front", fields=_readings(*illegible), notes=notes)


def _back(*legible: str, notes: str | None = None) -> PageAnalysis:
    # Kartın arka yüzünde zorunlu alan yazmaz; analizci o yüzde bulunmayanı `legible: false` okur.
    illegible = tuple(name for name in REQUIRED if name not in legible)
    return _analysis(
        1,
        LICENSE,
        side="back",
        continues_previous_page=True,
        fields=_readings(*illegible),
        notes=notes,
    )


def _catalog_with(slug: str, **changes: Any) -> Catalog:
    entries = [entry.model_dump(mode="json") for entry in CATALOG]
    for entry in entries:
        if entry["slug"] == slug:
            entry.update(changes)
    return validate_catalog(entries)


def _criteria_catalog(slug: str, *criteria: str) -> Catalog:
    return _catalog_with(slug, acceptance_criteria=list(criteria))


# --- 04.4.1 zorunlu alan okunaklılık kapısı (R1) --------------------------------------------------


def test_candidate_with_every_required_field_legible_is_accepted() -> None:
    check = _check(_analysis())

    assert check == LegibilityCheck(document_type_slug=PASSPORT)
    assert check.accepted
    assert (check.queue, check.reason) == (None, None)


@pytest.mark.parametrize("name", REQUIRED)
def test_one_illegible_required_field_sends_candidate_to_unreadable(name: str) -> None:
    check = _check(_analysis(fields=_readings(name)))

    assert check.illegible_fields == IllegibleRequiredFields((name,))
    assert check.illegible_fields.rule == "R1"
    assert check.unmet_criteria is None
    assert not check.accepted
    assert check.queue is QueueKind.UNREADABLE
    assert check.reason == f"Okunamayan alanlar: {name}"


def test_required_field_missing_from_the_reading_counts_as_illegible() -> None:
    fields = _readings()
    del fields["expiry_date"]

    check = _check(_analysis(fields=fields))

    assert check.illegible_fields == IllegibleRequiredFields(("expiry_date",))
    assert check.reason == "Okunamayan alanlar: expiry_date"


def test_every_illegible_field_is_named_in_catalog_order() -> None:
    fields = dict(reversed(_readings("surname", "expiry_date", "document_number").items()))
    del fields["given_names"]

    check = _check(_analysis(fields=fields))

    assert check.illegible_fields == IllegibleRequiredFields(
        ("surname", "given_names", "document_number", "expiry_date")
    )
    assert check.reason == "Okunamayan alanlar: surname, given_names, document_number, expiry_date"


def test_fields_outside_the_required_list_do_not_matter() -> None:
    fields = {**_readings(), "place_of_birth": {"value": None, "legible": False}}

    assert _check(_analysis(fields=fields)).accepted


def test_readings_are_merged_over_the_pages_of_the_candidate() -> None:
    # Ön yüz her alanı okur, arka yüzde alan yoktur (`legible: false`): kart kabul edilir.
    assert _check(_front(), _back()).accepted
    # Alan bir yüzde okunamasa da öteki yüzde okunaklıysa okunaklıdır.
    assert _check(_front("expiry_date", "surname"), _back("expiry_date", "surname")).accepted
    # Alan hiçbir yüzde okunaklı değilse aday Unreadable.
    check = _check(_front("document_number", "surname"), _back("surname"))
    assert check.illegible_fields == IllegibleRequiredFields(("document_number",))
    assert check.queue is QueueKind.UNREADABLE


def test_faces_paired_across_files_are_merged_too() -> None:
    check = _check((1, _front("expiry_date")), (2, _back("expiry_date")))

    assert check.accepted


def test_legible_reading_on_a_page_its_own_answer_calls_unreadable_is_not_trusted() -> None:
    # Çelişkili yanıt: sayfa bütün olarak okunamıyor denmiş ama alanlar okunaklı yazılmış (R7).
    unreadable = _analysis(is_readable=False)

    check = _check(unreadable)

    assert check.illegible_fields == IllegibleRequiredFields(REQUIRED)
    assert check.reason == f"Okunamayan alanlar: {', '.join(REQUIRED)}"
    # Adayın okunabilir sayfasındaki okuma yine sayılır.
    readable = _analysis(1, fields=_readings("surname"), continues_previous_page=True)
    assert _check(unreadable, readable).illegible_fields == IllegibleRequiredFields(("surname",))


def test_legible_reading_on_a_page_its_own_answer_calls_blank_is_not_trusted() -> None:
    check = _check(_analysis(is_blank=True))

    assert check.illegible_fields == IllegibleRequiredFields(REQUIRED)


@pytest.mark.parametrize("readable", [True, False], ids=["okunabilir", "okunamaz"])
def test_type_without_required_fields_has_no_legibility_gate(readable: bool) -> None:
    # Ayrı güven skoru yok (K1): `is_readable` tek başına rota vermez.
    photo = _analysis(slug=PHOTO, fields={}, is_readable=readable)

    check = _check(photo)

    assert check == LegibilityCheck(document_type_slug=PHOTO)


@pytest.mark.parametrize(
    "analysis",
    [
        pytest.param(
            _analysis(slug=None, candidate_type_name="Peruvian Diploma", fields={}),
            id="katalog-disi",
        ),
        pytest.param(_analysis(slug=None, fields={}, notes="Tür belirlenemedi."), id="tur-yok"),
        pytest.param(_analysis(slug="bosnian_identity_card"), id="katalogda-olmayan-slug"),
    ],
)
def test_candidate_without_a_catalog_type_is_not_judged(analysis: PageAnalysis) -> None:
    assert check_legibility(_candidate(analysis), catalog=CATALOG) is None


def test_required_fields_are_read_from_the_current_catalog() -> None:
    added = _catalog_with(PASSPORT, required_fields=[*REQUIRED, "place_of_birth"])
    removed = _catalog_with(PASSPORT, required_fields=["surname", "given_names"])

    check = _check(_analysis(), catalog=added)

    assert check.illegible_fields == IllegibleRequiredFields(("place_of_birth",))
    assert _check(_analysis(fields=_readings("document_number")), catalog=removed).accepted


# --- 04.4.2 kabul kriteri değerlendirmesi ---------------------------------------------------------


def test_seed_passport_has_criteria_and_the_card_has_none() -> None:
    assert CATALOG.get(PASSPORT).acceptance_criteria == (EDGE_CRITERION, MRZ_CRITERION)
    assert CATALOG.get(LICENSE).acceptance_criteria == ()


@pytest.mark.parametrize(
    "notes",
    [
        pytest.param(None, id="not-yok"),
        pytest.param("Alt kenar hafif bulanık; değerler okunuyor.", id="kriter-gecmiyor"),
    ],
)
def test_every_criterion_not_reported_as_unmet_is_met(notes: str | None) -> None:
    check = _check(_analysis(notes=notes))

    assert check.unmet_criteria is None
    assert check.accepted


@pytest.mark.parametrize("criterion", [EDGE_CRITERION, MRZ_CRITERION])
def test_unmet_criterion_sends_candidate_to_unresolved_by_name(criterion: str) -> None:
    check = _check(_analysis(notes=f"Sayfa kontrol edildi. {UNMET} {criterion}"))

    assert check.illegible_fields is None
    assert check.unmet_criteria == UnmetAcceptanceCriteria((criterion,))
    assert not check.accepted
    assert check.queue is QueueKind.UNRESOLVED
    assert check.reason == f'Karşılanmayan kabul kriterleri: "{criterion}"'


def test_several_unmet_criteria_are_named_in_catalog_order() -> None:
    notes = f"{UNMET} {MRZ_CRITERION}. {UNMET} {EDGE_CRITERION}."

    check = _check(_analysis(notes=notes))

    assert check.unmet_criteria == UnmetAcceptanceCriteria((EDGE_CRITERION, MRZ_CRITERION))
    assert check.reason == (
        f'Karşılanmayan kabul kriterleri: "{EDGE_CRITERION}"; "{MRZ_CRITERION}"'
    )


def test_empty_criteria_list_leaves_legibility_as_the_only_measure() -> None:
    without = _criteria_catalog(PASSPORT)
    notes = f"{UNMET} {MRZ_CRITERION}"

    assert _check(_analysis(notes=notes), catalog=without).accepted
    check = _check(_analysis(fields=_readings("surname"), notes=notes), catalog=without)
    assert check.queue is QueueKind.UNREADABLE
    assert check.unmet_criteria is None


def test_criteria_are_read_from_the_current_catalog() -> None:
    changed = _criteria_catalog(PASSPORT, "Fotoğraf net görünmeli")

    check = _check(
        _analysis(notes=f"{UNMET} {MRZ_CRITERION}. {UNMET} Fotoğraf net görünmeli"), catalog=changed
    )

    assert check.unmet_criteria == UnmetAcceptanceCriteria(("Fotoğraf net görünmeli",))


@pytest.mark.parametrize(
    "notes",
    [
        pytest.param(f"{UNMET} {MRZ_CRITERION.lower()}", id="kucuk-harf"),
        pytest.param(
            "KARŞILANMAYAN KABUL KRİTERİ: MRZ İKİ SATIRI DA OKUNABİLİR OLMALI", id="buyuk-harf"
        ),
        pytest.param(
            "Karsilanmayan kabul kriteri: MRZ iki satiri da okunabilir olmali", id="aksansiz"
        ),
        pytest.param(f'{UNMET} "{MRZ_CRITERION}."', id="tirnak-nokta"),
        pytest.param(f"{UNMET}\nMRZ  iki\tsatırı da\nokunabilir olmalı", id="bosluk"),
        pytest.param(
            unicodedata.normalize("NFD", f"{UNMET} {MRZ_CRITERION}"), id="ayrisik-unicode"
        ),
        pytest.param("MRZ-iki-satırı-da-okunabilir-olmalı", id="noktalama"),
    ],
)
def test_criterion_is_recognised_regardless_of_case_accents_punctuation_and_spacing(
    notes: str,
) -> None:
    check = _check(_analysis(notes=notes))

    assert check.unmet_criteria == UnmetAcceptanceCriteria((MRZ_CRITERION,))


@pytest.mark.parametrize(
    "notes",
    [
        pytest.param("MRZ satırları okunamıyor.", id="baska-sozcuklerle"),
        pytest.param(f"{UNMET} MRZ iki satırı da okunabilir", id="eksik-son-kelime"),
        pytest.param(f"{UNMET} MRZ iki satırı okunabilir olmalı", id="eksik-ara-kelime"),
        pytest.param(f"{UNMET} iki satırı da MRZ okunabilir olmalı", id="kelime-sirasi"),
        pytest.param(f"{UNMET} MRZ iki satırı da okunabilir olmalıdır", id="ek-almis-kelime"),
    ],
)
def test_paraphrased_or_partial_criterion_is_not_counted(notes: str) -> None:
    assert _check(_analysis(notes=notes)).unmet_criteria is None


def test_criterion_written_in_the_prompts_format_is_recognised() -> None:
    # Analizci karşılanmayan maddeyi talimattaki biçimle yazar (03.4); karar motoru onu tanır.
    template = " ".join(load_page_analysis_template().split())
    example = f"`{UNMET} <katalogdaki madde metni>`"
    assert example in template

    notes = example.strip("`").replace("<katalogdaki madde metni>", EDGE_CRITERION)

    assert _check(_analysis(notes=notes)).unmet_criteria == UnmetAcceptanceCriteria(
        (EDGE_CRITERION,)
    )


def test_criterion_reported_on_any_page_of_the_candidate_is_unmet() -> None:
    catalog = _criteria_catalog(
        LICENSE, "Dört köşe görünür olmalı", "Sınıf tablosu okunabilir olmalı"
    )

    check = _check(
        _front(), _back(notes=f"{UNMET} Sınıf tablosu okunabilir olmalı"), catalog=catalog
    )

    assert check.unmet_criteria == UnmetAcceptanceCriteria(("Sınıf tablosu okunabilir olmalı",))
    assert check.queue is QueueKind.UNRESOLVED


def test_criterion_is_not_assembled_from_the_notes_of_two_pages() -> None:
    catalog = _criteria_catalog(LICENSE, "Sınıf tablosu okunabilir olmalı")

    check = _check(
        _front(notes=f"{UNMET} Sınıf tablosu"), _back(notes="okunabilir olmalı"), catalog=catalog
    )

    assert check.accepted


LONG = "Fotoğraf net olmalı ve yüz tam görünmeli"
SHORT = "Fotoğraf net olmalı"


@pytest.mark.parametrize(
    ("notes", "unmet"),
    [
        pytest.param(f"{UNMET} {LONG}", (LONG,), id="yalniz-uzun"),
        pytest.param(f"{UNMET} {SHORT}", (SHORT,), id="yalniz-kisa"),
        pytest.param(f"{UNMET} {LONG}. {UNMET} {SHORT}", (SHORT, LONG), id="ikisi-ayri"),
        pytest.param(f"{UNMET} {SHORT} ve yüz kısmen görünüyor", (SHORT,), id="uzun-eksik"),
    ],
)
def test_criterion_inside_a_longer_reported_criterion_is_not_counted_twice(
    notes: str, unmet: tuple[str, ...]
) -> None:
    catalog = _criteria_catalog(PHOTO, SHORT, LONG)

    check = _check(_analysis(slug=PHOTO, fields={}, notes=notes), catalog=catalog)

    assert check.unmet_criteria == UnmetAcceptanceCriteria(unmet)


def test_overlapping_criteria_that_do_not_contain_each_other_are_both_counted() -> None:
    catalog = _criteria_catalog(PHOTO, "Yüz tam görünmeli", "tam görünmeli arka plan düz olmalı")

    check = _check(
        _analysis(slug=PHOTO, fields={}, notes=f"{UNMET} Yüz tam görünmeli arka plan düz olmalı"),
        catalog=catalog,
    )

    assert check.unmet_criteria == UnmetAcceptanceCriteria(
        ("Yüz tam görünmeli", "tam görünmeli arka plan düz olmalı")
    )


def test_criteria_with_the_same_words_share_the_verdict_and_are_named_once_per_text() -> None:
    catalog = _criteria_catalog(PHOTO, "Yüz görünmeli", "Yüz  görünmeli", "Yüz görünmeli.")

    check = _check(
        _analysis(slug=PHOTO, fields={}, notes=f"{UNMET} yüz görünmeli"), catalog=catalog
    )

    assert check.unmet_criteria == UnmetAcceptanceCriteria(("Yüz görünmeli", "Yüz görünmeli."))


def test_criterion_without_words_cannot_be_reported() -> None:
    catalog = _criteria_catalog(PHOTO, "***", "Yüz görünmeli")

    assert _check(_analysis(slug=PHOTO, fields={}, notes="***"), catalog=catalog).accepted
    check = _check(
        _analysis(slug=PHOTO, fields={}, notes=f"{UNMET} *** Yüz görünmeli"), catalog=catalog
    )
    assert check.unmet_criteria == UnmetAcceptanceCriteria(("Yüz görünmeli",))


def test_multiline_criterion_is_matched_and_named_on_one_line() -> None:
    catalog = _criteria_catalog(PHOTO, "Yüz tam\n  görünür olmalı")

    check = _check(
        _analysis(slug=PHOTO, fields={}, notes=f"{UNMET} Yüz tam görünür olmalı"), catalog=catalog
    )

    assert check.reason == 'Karşılanmayan kabul kriterleri: "Yüz tam görünür olmalı"'


def test_illegible_field_outranks_unmet_criterion_and_both_verdicts_are_kept() -> None:
    check = _check(_analysis(fields=_readings("document_number"), notes=f"{UNMET} {MRZ_CRITERION}"))

    assert check.illegible_fields == IllegibleRequiredFields(("document_number",))
    assert check.unmet_criteria == UnmetAcceptanceCriteria((MRZ_CRITERION,))
    assert check.queue is QueueKind.UNREADABLE
    assert check.reason == "Okunamayan alanlar: document_number"


# --- entegrasyon: veritabanı, render, kayıtlı yanıt, gruplama -------------------------------------

S9_PERSONAL_VALUES = ("ORNEKOVA", "Орнекова", "1990-01-01", "2030-01-01", "RUS")


def _event_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Event))


def test_s9_blurred_passport_goes_to_unreadable_naming_the_illegible_field(
    session: Session, layout: DataLayout
) -> None:
    # S9: bulanık pasaport; belge numarası okunamıyor → Unreadable, "Okunamayan alanlar:
    # document_number". Bulanık MRZ ayrıca kabul kriterini karşılamıyor; öncelik R1'in.
    pdf = make_text_pdf_bytes(["PASAPORT KIMLIK SAYFASI"])
    upload = _upload(session, layout, [("pasaport.pdf", pdf)])
    provider = RecordingProvider.from_directory(RECORDINGS / "s9_blurred_passport")
    analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)
    (candidate,) = group_upload(session, upload, catalog=CATALOG).candidates
    events = _event_count(session)

    check = check_legibility(candidate, catalog=CATALOG)

    assert check is not None and check.document_type_slug == PASSPORT
    assert check.queue is QueueKind.UNREADABLE
    assert check.reason == "Okunamayan alanlar: document_number"
    assert check.illegible_fields == IllegibleRequiredFields(("document_number",))
    assert check.unmet_criteria == UnmetAcceptanceCriteria((MRZ_CRITERION,))
    # Hüküm bu adımda olay loguna yazılmaz; plana (K9) ve kuyruk kaydına (08.1) geçer.
    assert _event_count(session) == events
    reasons = check.reason + check.unmet_criteria.reason
    for value in S9_PERSONAL_VALUES:
        assert value not in reasons


@pytest.mark.parametrize(
    ("notes", "queue", "reason"),
    [
        pytest.param(None, None, None, id="kriterler-karsilaniyor"),
        pytest.param(
            f"Sağ kenar kesik. {UNMET} {EDGE_CRITERION}",
            QueueKind.UNRESOLVED,
            f'Karşılanmayan kabul kriterleri: "{EDGE_CRITERION}"',
            id="kenar-kesik",
        ),
    ],
)
def test_analysed_passport_is_judged_by_its_acceptance_criteria(
    session: Session,
    layout: DataLayout,
    tmp_path: Path,
    notes: str | None,
    queue: QueueKind | None,
    reason: str | None,
) -> None:
    recording = json.loads((RECORDINGS / "russian_passport" / "0.json").read_text("utf-8"))
    recording["notes"] = notes
    upload = _upload(session, layout, [("pasaport.pdf", make_text_pdf_bytes(["PASAPORT"]))])
    provider = _recordings(tmp_path, [recording])
    analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)
    (candidate,) = group_upload(session, upload, catalog=CATALOG).candidates

    check = check_legibility(candidate, catalog=CATALOG)

    assert check is not None and check.illegible_fields is None
    assert (check.queue, check.reason) == (queue, reason)


def test_s5_card_paired_across_files_reads_required_fields_from_its_front(
    session: Session, layout: DataLayout
) -> None:
    # Arka yüz zorunlu alanları `legible: false` okur; ön yüzdeki okumalar kartı kabul ettirir.
    front = ("on.jpg", make_half_filled_image_bytes("JPEG", size=(300, 190)))
    back = ("arka.jpg", make_half_filled_image_bytes("JPEG", size=(310, 195)))
    upload = _upload(session, layout, [front, back])
    provider = RecordingProvider.from_directory(RECORDINGS / "s5_front_back_images")
    analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)
    (card,) = group_upload(session, upload, catalog=CATALOG).candidates
    assert len(card.file_ids) == 2

    check = check_legibility(card, catalog=CATALOG)

    assert check == LegibilityCheck(document_type_slug=LICENSE)
