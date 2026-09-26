"""11.9.3 — eğitim yapay zekâ yolu: yanıtın bilinen türe eşlenmesi, "AI kararı" etiketiyle
yerleşme, ipucuyla çelişki, yerleştirilemeyen öğe, isteğin görüntüleri ve metni, hata kaydı ve
S20'nin yapay zekâ yolu (PLAN.md §C86 "Yapay zekâ yolu", `app.training.classification`).

Yapay zekâ canlı çağrılmaz: sağlayıcı testin sahte sağlayıcısı ya da kayıtlı yanıttır. Belgeler ve
kişiler sentetiktir (`tests/fixtures/gen.py`); gerçek kimlik belgesi yoktur (CONVENTIONS §6).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai.provider import AnalysisProvider, PageAnalysisRequest, TrainingClassificationRequest
from app.ai.recording_provider import RecordingProvider
from app.ai.training_classification import TrainingClassification
from app.ai.usage import TokenUsage, UsageMeter, measure_usage, report_usage
from app.catalog import import_catalog, load_seed_catalog
from app.catalog.describe import page_images
from app.catalog.prompt_builder import compile_catalog
from app.catalog.schema import validate_catalog
from app.config import Settings
from app.db.models import (
    Event,
    ExampleFileRecord,
    TrainingItem,
    TrainingItemStatus,
    TrainingMethod,
    TrainingRun,
    TrainingRunKind,
)
from app.db.session import create_session_factory
from app.events import USAGE_DATA_KEY, EventType
from app.storage import DataLayout, FileKind
from app.storage.examples import list_examples, store_example
from app.training import (
    ItemNotPlaceableError,
    KnownTypes,
    build_known_types,
    create_run,
    load_suggested_types,
    place_example,
    recognize_item,
    stage_and_recognize,
    stage_file,
)
from app.training.classification import (
    AI_CHECK_KEY,
    ERROR_NOTE,
    MAX_CLASSIFICATION_PAGES,
    NO_TYPE_REASON,
    ClassificationSource,
    ResolutionBasis,
    TrainingClassificationJob,
    apply_classification,
    build_classification_prompt,
    classify,
    read_classification,
    resolve_classification,
    store_classification_error,
)
from app.worker import IdleContext
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_PRUEBA,
    make_half_filled_image_bytes,
    make_page_image_bytes,
    make_pdf_bytes,
    passport_page,
    unknown_document_page,
)
from tests.training.invariants import assert_employee_data_untouched

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = ROOT / "tests" / "fixtures" / "ai" / "training_classifications"
LIMIT = 1024 * 1024
MODEL = "sahte-model"
SETTINGS = Settings(_env_file=None, database_url="sqlite://", worker_max_attempts=3)
FILE_NAME = "Ornekova-belge.jpg"
PERSONAL_VALUES = ("ORNEKOVA", "Ornekova", "00 0000001", "1990-01-01")


def _answer(**changes: Any) -> TrainingClassification:
    data: dict[str, Any] = {
        "catalog_slug": None,
        "country_iso3": None,
        "doc_kind": None,
        "proposed_name": None,
        "side": "single",
        "notes": "",
    }
    data.update(changes)
    return TrainingClassification.model_validate(data)


class Classifier(AnalysisProvider):
    """Sahte sağlayıcı: sınıflandırma isteklerine sırayla yanıt döner, kullanım bildirir."""

    name = "sahte"

    def __init__(self, *responses: object) -> None:
        super().__init__(model=MODEL)
        self._responses = list(responses)
        self.requests: list[TrainingClassificationRequest] = []

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        raise AssertionError("sayfa analizi istenmemeli (§C86 kapsam sınırı)")

    def _request_training_classification(self, request: TrainingClassificationRequest) -> object:
        self.requests.append(request)
        report_usage(900, 100)
        response = self._responses.pop(0)
        if isinstance(response, TrainingClassification):
            return response.model_dump(mode="json")
        return response


@pytest.fixture
def catalog(session: Session) -> None:
    import_catalog(session, load_seed_catalog())
    session.flush()


def _run(session: Session) -> TrainingRun:
    return create_run(session, kind=TrainingRunKind.UPLOAD, created_by="ik")


def _pending(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    content: bytes | None = None,
    *,
    name: str = FILE_NAME,
    hint: str | None = None,
    run: TrainingRun | None = None,
) -> TrainingItem:
    """Mekanik tanınmayan öğe: varsayılan içerik ipucusuz bir JPEG'dir (metin katmanı yok)."""
    item = stage_and_recognize(
        session,
        layout,
        known,
        run or _run(session),
        name,
        make_half_filled_image_bytes("JPEG") if content is None else content,
        max_bytes=LIMIT,
        inventory=None,
        hint_slug=hint,
    )
    assert item.status == TrainingItemStatus.AI_PENDING
    return item


def _apply(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    item: TrainingItem,
    answer: TrainingClassification,
) -> Any:
    meter = UsageMeter()
    meter.add(TokenUsage(900, 100))
    return apply_classification(
        session, layout, item, answer, provider=Classifier(), meter=meter, known=known
    )


def _events(session: Session, event_type: EventType) -> list[Event]:
    return list(
        session.scalars(select(Event).where(Event.type == event_type.value).order_by(Event.id))
    )


# --- eşleme (saf) ----------------------------------------------------------------------------


def test_a_catalog_slug_resolves_to_that_catalog_type(known: KnownTypes) -> None:
    resolution = resolve_classification(
        known, _answer(catalog_slug="turkish_passport", country_iso3="TUR", doc_kind="pasaport")
    )

    assert resolution.known is not None and resolution.known.slug == "turkish_passport"
    assert resolution.basis is ResolutionBasis.CATALOG
    assert resolution.basis_text == "katalog türü"


@pytest.mark.parametrize(
    ("changes", "clash"),
    [
        ({"country_iso3": "RUS"}, "ülke"),
        ({"doc_kind": "ehliyet"}, "tür"),
        ({"country_iso3": "SRB", "doc_kind": "vize"}, "ülke ve tür"),
    ],
    ids=["ulke", "tur", "ikisi"],
)
def test_a_catalog_slug_contradicted_by_the_answer_is_not_resolved(
    known: KnownTypes, changes: dict[str, str], clash: str
) -> None:
    resolution = resolve_classification(known, _answer(catalog_slug="turkish_passport", **changes))

    assert resolution.known is None
    assert (
        resolution.reason
        == f"katalog türü `turkish_passport` yanıttaki {clash} bilgisiyle çelişiyor"
    )


def test_a_catalog_type_without_a_pair_is_not_contradicted(known: KnownTypes) -> None:
    resolution = resolve_classification(
        known, _answer(catalog_slug="work_permit", country_iso3="SRB", doc_kind="oturum_izni")
    )

    assert resolution.known is not None and resolution.known.slug == "work_permit"


def test_a_catalog_slug_missing_from_the_known_types_is_not_resolved() -> None:
    # Katalog okuma ile yazma arasında değişmiş olabilir; yanıt bilinmeyen türe yerleşmez.
    entries = [entry.model_dump(mode="json") for entry in load_seed_catalog()]
    known = build_known_types(validate_catalog([e for e in entries if e["slug"] != "work_permit"]))

    resolution = resolve_classification(known, _answer(catalog_slug="work_permit"))

    assert resolution.known is None
    assert resolution.reason == "katalog türü `work_permit` bilinen türlerde yok"


@pytest.mark.parametrize(
    ("country", "kind", "slug"),
    [
        ("ALB", "pasaport", "albanian_passport"),
        ("TUR", "pasaport", "turkish_passport"),
        ("SRB", "oturum_izni", "serbian_residence_card"),
        ("EU", "pasaport", "eu_passport"),
        ("KKTC", "pasaport", "northern_cyprus_passport"),
        ("XKX", "pasaport", "kosovar_passport"),
    ],
)
def test_a_unique_country_and_kind_resolve_to_a_known_type(
    known: KnownTypes, country: str, kind: str, slug: str
) -> None:
    resolution = resolve_classification(known, _answer(country_iso3=country, doc_kind=kind))

    assert resolution.known is not None and resolution.known.slug == slug
    assert resolution.basis is ResolutionBasis.KIND
    assert resolution.basis_text == f"ülke ve tür {country}/{kind}"


@pytest.mark.parametrize(
    ("country", "kind", "slugs"),
    [
        ("RUS", "kimlik_karti", "`russian_identity_card`, `russian_internal_passport`"),
        ("TUR", "ehliyet", "`turkish_driving_license`, `turkish_international_driving_permit`"),
    ],
)
def test_an_ambiguous_pair_is_not_resolved(
    known: KnownTypes, country: str, kind: str, slugs: str
) -> None:
    resolution = resolve_classification(known, _answer(country_iso3=country, doc_kind=kind))

    assert resolution.known is None
    assert resolution.reason == f"{country}/{kind} birden çok türe iniyor ({slugs})"


def test_the_ambiguous_turkish_license_is_not_settled_by_its_ambiguous_name(
    known: KnownTypes,
) -> None:
    resolution = resolve_classification(
        known,
        _answer(country_iso3="TUR", doc_kind="ehliyet", proposed_name="Turkish Driving License"),
    )

    assert resolution.known is None
    assert "TUR/ehliyet birden çok türe iniyor" in resolution.reason
    assert "ad birden çok türe iniyor" in resolution.reason


def test_an_ambiguous_pair_is_settled_by_a_consistent_name(known: KnownTypes) -> None:
    resolution = resolve_classification(
        known,
        _answer(
            country_iso3="RUS", doc_kind="kimlik_karti", proposed_name="Russian Internal Passport"
        ),
    )

    assert resolution.known is not None and resolution.known.slug == "russian_internal_passport"
    assert resolution.basis is ResolutionBasis.NAME
    assert resolution.basis_text == "ad Russian Internal Passport"


def test_a_name_resolves_after_normalization(known: KnownTypes) -> None:
    resolution = resolve_classification(known, _answer(proposed_name="serbian driving LICENCE"))

    assert resolution.known is not None and resolution.known.slug == "serbian_driving_license"
    assert resolution.basis is ResolutionBasis.NAME


def test_a_partial_pair_is_skipped_and_the_name_decides(known: KnownTypes) -> None:
    resolution = resolve_classification(
        known, _answer(doc_kind="pasaport", proposed_name="Albanian Passport")
    )

    assert resolution.known is not None and resolution.known.slug == "albanian_passport"
    assert resolution.basis is ResolutionBasis.NAME


def test_a_name_contradicting_the_answer_s_country_is_not_resolved(known: KnownTypes) -> None:
    resolution = resolve_classification(
        known, _answer(country_iso3="TUR", proposed_name="Albanian Passport")
    )

    assert resolution.known is None
    assert resolution.reason == ("ad `albanian_passport` türüne iniyor ama yanıttaki ülke tutmuyor")


def test_a_pair_without_a_type_and_an_unknown_name_are_both_reported(known: KnownTypes) -> None:
    resolution = resolve_classification(
        known,
        _answer(country_iso3="ZZZ", doc_kind="pasaport", proposed_name="Martian Passport"),
    )

    assert resolution.known is None
    assert resolution.reason == (
        "ZZZ/pasaport bilinen bir türe inmiyor; ad bilinen bir türe inmiyor"
    )


def test_an_empty_answer_is_not_resolved(known: KnownTypes) -> None:
    resolution = resolve_classification(known, _answer(side="unknown"))

    assert resolution.known is None
    assert resolution.reason == NO_TYPE_REASON


def test_every_suggested_type_is_reachable_by_its_own_name_or_pair(known: KnownTypes) -> None:
    # Önerilen kayıttaki her tür ya kendi adıyla ya da (ülke, tür) çiftiyle bulunabilir; ikisi de
    # belirsizse (ör. `turkish_driving_license`) tür yalnız İK'nın "Türe yerleştir"iyle dolar.
    unreachable = []
    for row in load_suggested_types():
        by_name = resolve_classification(known, _answer(proposed_name=row.name)).known
        by_pair = None
        if row.country_iso3:
            by_pair = resolve_classification(
                known, _answer(country_iso3=row.country_iso3, doc_kind=row.doc_kind)
            ).known
        target = known.get(row.slug)
        assert target is not None
        if target not in (by_name, by_pair):
            unreachable.append(row.slug)

    assert "albanian_passport" not in unreachable
    assert "turkish_driving_license" in unreachable
    assert len(unreachable) < len(load_suggested_types()) // 10


# --- sonuç: yerleşme -------------------------------------------------------------------------


def test_a_suggested_type_is_placed_with_the_ai_decision_label(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _pending(session, layout, known)
    mechanical = dict(item.checks_json or {})

    outcome = _apply(session, layout, known, item, _answer(country_iso3="ALB", doc_kind="pasaport"))

    note = "AI kararı: `albanian_passport` (ülke ve tür ALB/pasaport, model sahte-model)"
    assert (outcome.status, outcome.slug, outcome.note) == (
        TrainingItemStatus.PLACED,
        "albanian_passport",
        note,
    )
    assert (item.status, item.method, item.result_slug, item.note) == (
        "placed",
        "ai",
        "albanian_passport",
        note,
    )
    (example,) = session.scalars(select(ExampleFileRecord)).all()
    assert (example.type_slug, example.method, example.label, example.note) == (
        "albanian_passport",
        "ai",
        "ai_decision",
        note,
    )
    assert [entry.name for entry in list_examples(layout, "albanian_passport")] == [FILE_NAME]
    assert item.run.status == "done"
    assert item.run.counts_json == {"placed": 1}
    checks = item.checks_json or {}
    assert checks["result"] == mechanical["result"]  # mekanik döküm kalır
    assert checks[AI_CHECK_KEY]["response"]["country_iso3"] == "ALB"
    assert checks[AI_CHECK_KEY]["result"] == {
        "slug": "albanian_passport",
        "basis": "country_kind",
        "reason": None,
        "status": "placed",
    }
    assert (checks[AI_CHECK_KEY]["provider"], checks[AI_CHECK_KEY]["model"]) == ("sahte", MODEL)
    (event,) = _events(session, EventType.TRAINING_EXAMPLE_PLACED)
    assert event.data_json["method"] == "ai"
    assert event.data_json["label"] == "ai_decision"
    assert event.data_json["basis"] == "country_kind"
    assert event.data_json["provider"] == "sahte"
    assert event.data_json["model"] == MODEL
    assert event.data_json[USAGE_DATA_KEY] == {"input_tokens": 900, "output_tokens": 100}
    assert_employee_data_untouched(session, layout)


def test_a_catalog_type_is_placed_with_the_ai_decision_label(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _pending(session, layout, known)

    outcome = _apply(
        session,
        layout,
        known,
        item,
        _answer(catalog_slug="russian_passport", country_iso3="RUS", doc_kind="pasaport"),
    )

    assert outcome.status == TrainingItemStatus.PLACED
    assert item.note == "AI kararı: `russian_passport` (katalog türü, model sahte-model)"
    (example,) = session.scalars(select(ExampleFileRecord)).all()
    assert (example.type_slug, example.label) == ("russian_passport", "ai_decision")
    assert_employee_data_untouched(session, layout)


def test_the_expected_type_confirmed_by_the_ai_is_placed(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    # `turkish_passport` PNG kabul etmez: mekanik yol ipucunu doğrulayamadı, yapay zekâ doğruladı.
    item = _pending(
        session, layout, known, make_half_filled_image_bytes("PNG"), hint="turkish_passport"
    )

    outcome = _apply(session, layout, known, item, _answer(country_iso3="TUR", doc_kind="pasaport"))

    assert outcome.status == TrainingItemStatus.PLACED
    assert item.result_slug == "turkish_passport"
    assert item.note == (
        "AI kararı: `turkish_passport` (ülke ve tür TUR/pasaport, model sahte-model)"
    )


def test_content_already_in_the_type_s_folder_is_skipped_and_the_event_keeps_the_usage(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = make_half_filled_image_bytes("JPEG")
    store_example(layout, "albanian_passport", "onceden.jpg", content, FileKind.JPEG)
    item = _pending(session, layout, known, content)

    outcome = _apply(session, layout, known, item, _answer(country_iso3="ALB", doc_kind="pasaport"))

    assert outcome.status == TrainingItemStatus.SKIPPED
    assert outcome.note.endswith("; zaten örnek: onceden.jpg")
    assert (item.checks_json or {})[AI_CHECK_KEY]["result"]["status"] == "skipped"
    (event,) = _events(session, EventType.TRAINING_ITEM_UNPLACED)
    assert event.data_json["status"] == "skipped"
    assert event.data_json[USAGE_DATA_KEY] == {"input_tokens": 900, "output_tokens": 100}


# --- sonuç: çelişki ve yerleştirilemedi ------------------------------------------------------


def test_a_result_that_differs_from_the_expected_type_is_a_conflict(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _pending(
        session, layout, known, make_half_filled_image_bytes("PNG"), hint="turkish_passport"
    )

    outcome = _apply(session, layout, known, item, _answer(country_iso3="ALB", doc_kind="pasaport"))

    note = (
        "AI kararı `albanian_passport` beklenen tür `turkish_passport` ile çelişiyor "
        "(ülke ve tür ALB/pasaport, model sahte-model)"
    )
    assert (outcome.status, outcome.slug, outcome.note) == (
        TrainingItemStatus.CONFLICT,
        "albanian_passport",
        note,
    )
    assert (item.status, item.method, item.result_slug, item.note) == (
        "conflict",
        "ai",
        "albanian_passport",
        note,
    )
    assert session.scalars(select(ExampleFileRecord)).all() == []
    assert list_examples(layout, "albanian_passport") == []
    assert list_examples(layout, "turkish_passport") == []
    assert item.run.status == "done"  # İK bekleyen öğe çalıştırmayı açık tutmaz
    (event,) = _events(session, EventType.TRAINING_ITEM_UNPLACED)
    assert event.data_json["status"] == "conflict"
    assert event.data_json["type_slug"] == "albanian_passport"
    assert event.data_json["hint_slug"] == "turkish_passport"
    assert event.data_json[USAGE_DATA_KEY] == {"input_tokens": 900, "output_tokens": 100}
    # İK'nın "Türe yerleştir"i (tm 118) çelişkideki öğeyi yerleştirebilir.
    placement = place_example(
        session, layout, known, item, "turkish_passport", method=TrainingMethod.MANUAL, actor="ik"
    )
    assert placement.example.label == "verified"
    assert_employee_data_untouched(session, layout)


def test_a_map_row_is_named_in_the_conflict_note(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    run = create_run(session, kind=TrainingRunKind.MAP, created_by="ik", map_name="harita.csv")
    item = stage_file(
        session,
        layout,
        run,
        "satir.png",
        make_half_filled_image_bytes("PNG"),
        max_bytes=LIMIT,
        hint_slug="turkish_passport",
        row_number=12,
    )
    recognize_item(session, layout, known, item, inventory=None)
    assert item.status == TrainingItemStatus.AI_PENDING

    _apply(session, layout, known, item, _answer(country_iso3="ALB", doc_kind="pasaport"))

    assert item.status == "conflict"
    assert "harita satırı 12 `turkish_passport`" in (item.note or "")


def test_an_unknown_hint_is_not_a_conflict(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _pending(session, layout, known, hint="martian_passport")

    outcome = _apply(session, layout, known, item, _answer(country_iso3="ALB", doc_kind="pasaport"))

    assert outcome.status == TrainingItemStatus.PLACED


def test_an_answer_without_a_known_type_is_left_unplaced_with_the_proposal(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _pending(session, layout, known)

    outcome = _apply(
        session,
        layout,
        known,
        item,
        _answer(doc_kind="pasaport", proposed_name="Martian Passport"),
    )

    note = "Yapay zekâ önerisi: Martian Passport; ad bilinen bir türe inmiyor; model sahte-model"
    assert (outcome.status, outcome.slug, outcome.note) == (
        TrainingItemStatus.UNPLACED,
        None,
        note,
    )
    assert (item.status, item.method, item.result_slug, item.note) == (
        "unplaced",
        "ai",
        None,
        note,
    )
    assert session.scalars(select(ExampleFileRecord)).all() == []
    assert item.run.status == "done"
    assert item.run.counts_json == {"unplaced": 1}
    assert (item.checks_json or {})[AI_CHECK_KEY]["result"] == {
        "slug": None,
        "basis": None,
        "reason": "ad bilinen bir türe inmiyor",
        "status": "unplaced",
    }
    (event,) = _events(session, EventType.TRAINING_ITEM_UNPLACED)
    assert event.data_json["status"] == "unplaced"
    assert event.data_json["type_slug"] is None
    assert event.data_json[USAGE_DATA_KEY] == {"input_tokens": 900, "output_tokens": 100}
    assert_employee_data_untouched(session, layout)


def test_an_ambiguous_pair_is_left_unplaced(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _pending(session, layout, known)

    _apply(session, layout, known, item, _answer(country_iso3="RUS", doc_kind="kimlik_karti"))

    assert item.status == "unplaced"
    assert item.note == (
        "Yapay zekâ önerisi yok; RUS/kimlik_karti birden çok türe iniyor "
        "(`russian_identity_card`, `russian_internal_passport`); model sahte-model"
    )


def test_an_unplaced_item_does_not_become_a_candidate_type(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    # İnsan kararı: yerleştirilemeyen belge aday tür olmaz, eğitim sekmesinde bekler.
    item = _pending(session, layout, known)

    _apply(session, layout, known, item, _answer(proposed_name="Library Membership Card"))

    assert item.status == "unplaced"
    assert_employee_data_untouched(session, layout)  # candidate_document_types dahil


def test_an_item_that_is_not_ai_pending_is_refused(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _pending(session, layout, known)
    _apply(session, layout, known, item, _answer(country_iso3="ALB", doc_kind="pasaport"))
    before = len(session.scalars(select(Event)).all())

    with pytest.raises(ItemNotPlaceableError):
        _apply(session, layout, known, item, _answer(country_iso3="TUR", doc_kind="pasaport"))

    assert item.result_slug == "albanian_passport"
    assert len(session.scalars(select(Event)).all()) == before


def test_notes_checks_and_events_carry_no_file_name_or_personal_value(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    placed = _pending(session, layout, known)
    unplaced = _pending(session, layout, known, make_half_filled_image_bytes("PNG"))
    _apply(session, layout, known, placed, _answer(country_iso3="ALB", doc_kind="pasaport"))
    _apply(session, layout, known, unplaced, _answer(proposed_name="Library Membership Card"))

    texts = [json.dumps(item.checks_json, ensure_ascii=False) for item in (placed, unplaced)]
    texts += [item.note or "" for item in (placed, unplaced)]
    for event in session.scalars(select(Event)):
        texts += [event.message or "", json.dumps(event.data_json, ensure_ascii=False)]
    for text in texts:
        assert FILE_NAME not in text
        for value in PERSONAL_VALUES:
            assert value not in text


# --- istek -----------------------------------------------------------------------------------


@pytest.mark.usefixtures("catalog")
def test_an_image_is_sent_as_one_image_with_the_file_described(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = make_half_filled_image_bytes("JPEG")
    item = _pending(session, layout, known, content)
    source = read_classification(session, layout, item)
    provider = Classifier(_answer(country_iso3="ALB", doc_kind="pasaport"))

    classification = classify(source, SETTINGS, provider)

    assert classification.country_iso3 == "ALB"
    (request,) = provider.requests
    (expected,), _ = page_images(content, FileKind.JPEG, SETTINGS, MAX_CLASSIFICATION_PAGES)
    assert [image.data for image in request.images] == [expected]
    assert request.prompt == (
        "Dosya türü: JPEG\nSayfa sayısı: 1\n\nGörüntüler (1, gönderildiği sırayla):\n1. sayfa 1"
    )
    assert FILE_NAME not in request.prompt
    compiled = compile_catalog(load_seed_catalog())
    assert request.known_slugs == compiled.known_slugs
    assert request.doc_kinds == known.doc_kinds
    assert compiled.text in request.instructions
    assert_employee_data_untouched(session, layout)  # sayfa önbelleğine yazılmadı


@pytest.mark.usefixtures("catalog")
def test_a_pdf_sends_its_first_two_pages_and_says_the_rest_was_not_sent(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = make_pdf_bytes(3)
    item = _pending(session, layout, known, content, name="uc-sayfa.pdf")
    provider = Classifier(_answer())

    classify(read_classification(session, layout, item), SETTINGS, provider)

    (request,) = provider.requests
    expected, pages = page_images(content, FileKind.PDF, SETTINGS, MAX_CLASSIFICATION_PAGES)
    assert pages == 3
    assert [image.data for image in request.images] == expected
    assert len(request.images) == 2
    assert request.prompt.splitlines() == [
        "Dosya türü: PDF",
        "Sayfa sayısı: 3",
        "",
        "Görüntüler (2, gönderildiği sırayla):",
        "1. sayfa 1",
        "2. sayfa 2",
        "Kalan 1 sayfa gönderilmedi.",
    ]


def test_the_prompt_builder_counts_the_images() -> None:
    assert build_classification_prompt(FileKind.PNG, 1, 1).startswith("Dosya türü: PNG\n")
    assert "Kalan" not in build_classification_prompt(FileKind.PDF, 2, 2)


@pytest.mark.usefixtures("catalog")
def test_reading_the_source_writes_nothing(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = make_half_filled_image_bytes("PNG")
    item = _pending(session, layout, known, content)
    session.flush()

    source = read_classification(session, layout, item)

    assert isinstance(source, ClassificationSource)
    assert (source.item_id, source.content, source.file_kind, source.page_count) == (
        item.id,
        content,
        FileKind.PNG,
        1,
    )
    assert not session.dirty and not session.new
    assert repr(content) not in repr(source)


def test_an_item_without_a_staged_file_cannot_be_read(session: Session, layout: DataLayout) -> None:
    item = TrainingItem(run=_run(session), original_name="yok.jpg", status="ai_pending")
    session.add(item)
    session.flush()

    with pytest.raises(ItemNotPlaceableError):
        read_classification(session, layout, item)


# --- hata kaydı ------------------------------------------------------------------------------


def test_a_failed_attempt_records_its_usage_and_keeps_the_item_pending(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _pending(session, layout, known)
    note = item.note
    with measure_usage() as meter:
        report_usage(300, 20)

    store_classification_error(
        session,
        item,
        error="TrainingClassificationError",
        final=False,
        provider=Classifier(),
        meter=meter,
    )

    assert (item.status, item.note) == ("ai_pending", note)
    (event,) = _events(session, EventType.TRAINING_ITEM_UNPLACED)
    assert event.data_json["status"] == "ai_pending"
    assert event.data_json["error"] == "TrainingClassificationError"
    assert event.data_json[USAGE_DATA_KEY] == {"input_tokens": 300, "output_tokens": 20}


def test_a_final_failure_leaves_the_item_unplaced_for_hr(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _pending(session, layout, known)
    item.status = TrainingItemStatus.UNPLACED.value  # çerçevenin `failed` değerleri

    store_classification_error(
        session,
        item,
        error="ProviderServerError",
        final=True,
        provider=Classifier(),
        meter=UsageMeter(),
    )

    assert item.status == "unplaced"
    assert item.method == "ai"
    assert item.note == ERROR_NOTE.format(error="ProviderServerError")
    assert item.run.status == "done"
    (event,) = _events(session, EventType.TRAINING_ITEM_UNPLACED)
    assert event.data_json["status"] == "unplaced"
    assert USAGE_DATA_KEY not in event.data_json  # yanıt gelmedi, kullanım ölçülmedi


# --- S20: yapay zekâ yolu --------------------------------------------------------------------


@pytest.mark.usefixtures("catalog")
def test_s20_the_passport_gets_the_ai_decision_label_and_the_other_file_waits_unplaced(
    engine: Engine, session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    # S20: eğitim modunda pasaport yükleniyor, ikinci dosya hiçbir türe uymuyor. Pasaport görüntüsü
    # (metin katmanı yok) mekanik tanınmaz ve "AI kararı" etiketiyle örneklere girer; ikincisi
    # "Yerleştirilemedi"de bekler. Çalışan, kuyruk öğesi, parti ve çıktı belgesi oluşmaz.
    passport = make_page_image_bytes(
        passport_page(PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1))
    )
    card = make_page_image_bytes(
        unknown_document_page(
            PERSON_PRUEBA, candidate_type_name="Library Card", title="LIBRARY CARD"
        )
    )
    run = _run(session)
    first = _pending(session, layout, known, passport, name="pasaport.jpg", run=run)
    second = _pending(session, layout, known, card, name="kart.jpg", run=run)
    session.commit()
    provider = RecordingProvider.from_directory(RECORDINGS / "s20")
    context = IdleContext(create_session_factory(engine), layout, SETTINGS, provider)

    job = TrainingClassificationJob()
    assert job.run_one(context) is True
    assert job.run_one(context) is True
    assert job.run_one(context) is False

    session.expire_all()
    first, second = (
        session.get_one(TrainingItem, first.id),
        session.get_one(TrainingItem, second.id),
    )
    assert (first.status, first.result_slug, first.method) == ("placed", "russian_passport", "ai")
    (example,) = session.scalars(select(ExampleFileRecord)).all()
    assert (example.type_slug, example.label) == ("russian_passport", "ai_decision")
    assert [entry.name for entry in list_examples(layout, "russian_passport")] == ["pasaport.jpg"]
    assert second.status == "unplaced"
    assert (second.note or "").startswith("Yapay zekâ önerisi: Library Membership Card;")
    assert session.get_one(TrainingRun, run.id).counts_json == {"placed": 1, "unplaced": 1}
    assert session.get_one(TrainingRun, run.id).status == "done"
    assert len(provider.training_requests) == 2
    assert provider.requests == []  # sayfa analizi yok
    assert_employee_data_untouched(session, layout)
    for text in (first.note, second.note, json.dumps(first.checks_json, ensure_ascii=False)):
        for value in PERSONAL_VALUES:
            assert value not in (text or "")
