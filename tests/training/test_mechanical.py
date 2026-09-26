"""11.9.2 — mekanik tanıma: örnek olamayan dosya, SHA-256 (örnek kaydı ve envanter), ipucunun yapı
kuralları, PDF metin katmanında MRZ, çelişkiler, kişisel değersiz not ve döküm, yapay zekâsız yol
(PLAN.md §C86 "Mekanik tanıma").

Veri sentetiktir (`tests/fixtures/gen.py`: kurgusal kişi `ORNEKOVA TEST`, numara `U00000001`,
sentetik PDF ve görüntüler); gerçek kimlik belgesi ve canlı yapay zekâ çağrısı yoktur.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.ai.provider as provider_module
from app.ai.provider import AnalysisProvider
from app.db.models import (
    Event,
    ExampleFileRecord,
    TrainingItem,
    TrainingItemStatus,
    TrainingMethod,
    TrainingRun,
    TrainingRunKind,
)
from app.events import EventType
from app.matching.mrz import MrzFormat
from app.storage import DataLayout, sha256_bytes
from app.storage.examples import check_example, list_examples, store_example
from app.training import (
    ExampleInventory,
    ItemNotPlaceableError,
    KnownTypes,
    MrzReading,
    MrzSearchStatus,
    RecognitionBasis,
    create_run,
    find_mrz_readings,
    load_example_inventory,
    mrz_doc_kind,
    parse_example_inventory,
    place_example,
    read_mrz_evidence,
    recognize,
    recognize_item,
    stage_and_recognize,
    stage_file,
)
from tests.fixtures.gen import (
    make_half_filled_image_bytes,
    make_mrz_lines,
    make_pdf_bytes,
    make_portrait_image_bytes,
    make_text_pdf_bytes,
)
from tests.training.invariants import assert_employee_data_untouched

LIMIT = 1024 * 1024
SURNAME, GIVEN, NUMBER = "ORNEKOVA", "TEST", "U00000001"
BIRTH, EXPIRY = date(1990, 1, 1), date(2030, 1, 1)
# Kişisel değerlerin MRZ'deki ve düz yazımları: not, döküm ve olaylarda hiçbiri geçmez.
PERSONAL_VALUES = (SURNAME, GIVEN, NUMBER, "900101", "300101", "1990-01-01", "2030-01-01")

_FORBIDDEN_PROVIDER_CALLS = (
    "analyze_page",
    "describe_type",
    "check_photo",
    "read_document_query",
    "propose_type",
    "classify_training_page",
)


@pytest.fixture(autouse=True)
def ai_calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Yapay zekâ sağlayıcısı çağrılırsa kaydeder ve testi düşürür; her test sonunda sayı 0."""
    calls: list[str] = []

    def forbidden(name: str):
        def call(*args: object, **kwargs: object) -> None:
            calls.append(name)
            raise AssertionError(f"mekanik tanımada yapay zekâ çağrıldı: {name}")

        return call

    for name in _FORBIDDEN_PROVIDER_CALLS:
        monkeypatch.setattr(AnalysisProvider, name, forbidden(name))
    monkeypatch.setattr(provider_module, "create_provider", forbidden("create_provider"))
    yield calls
    assert calls == []


def _run(session: Session, kind: TrainingRunKind = TrainingRunKind.UPLOAD) -> TrainingRun:
    return create_run(session, kind=kind, created_by="ik")


def _upload(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    name: str,
    content: bytes,
    *,
    hint: str | None = None,
    inventory: ExampleInventory | None = None,
    run: TrainingRun | None = None,
) -> TrainingItem:
    return stage_and_recognize(
        session,
        layout,
        known,
        run or _run(session),
        name,
        content,
        max_bytes=LIMIT,
        inventory=inventory,
        hint_slug=hint,
    )


def _mrz(
    fmt: str = "TD3", code: str = "P", state: str = "TUR", *, number: str = NUMBER
) -> tuple[str, ...]:
    return make_mrz_lines(
        fmt,  # type: ignore[arg-type]
        document_code=code,
        issuing_state=state,
        surname=SURNAME,
        given_names=GIVEN,
        document_number=number,
        nationality=state if len(state) == 3 else "UTO",
        date_of_birth=BIRTH,
        sex="F",
        expiry_date=EXPIRY,
    )


def _broken(lines: tuple[str, ...]) -> tuple[str, ...]:
    """TD3/TD2 satırlarında belge numarasının kontrol hanesi bozulur (bileşik de tutmaz)."""
    first, second = lines
    digit = str((int(second[9]) + 1) % 10)
    return first, second[:9] + digit + second[10:]


def _mrz_pdf(*pages: tuple[str, ...] | None, heading: str = "PASAPORT") -> bytes:
    return make_text_pdf_bytes(
        [None if lines is None else "\n".join((heading, *lines)) for lines in pages]
    )


def _inventory_csv(rows: list[tuple[str, str, str]], *, delimiter: str = ",") -> str:
    header = ["slug", "in_catalog", "role", "dest", "note", "sha256", "status"]
    lines = [delimiter.join(header)]
    for slug, role, sha256 in rows:
        values = [slug, "hayır", role, f"KnownDocuments/examples/{slug}/x.jpg", "not", sha256, "ok"]
        lines.append(delimiter.join(values))
    return "\n".join(lines) + "\n"


def _write_inventory(layout: DataLayout, rows: list[tuple[str, str, str]]) -> ExampleInventory:
    layout.example_inventory_path.write_text(_inventory_csv(rows), encoding="utf-8-sig")
    inventory = load_example_inventory(layout)
    assert inventory is not None
    return inventory


def _placed_events(session: Session) -> list[Event]:
    return list(
        session.scalars(select(Event).where(Event.type == EventType.TRAINING_EXAMPLE_PLACED.value))
    )


def _records(session: Session) -> list[ExampleFileRecord]:
    return list(session.scalars(select(ExampleFileRecord).order_by(ExampleFileRecord.id)))


def _assert_no_personal_values(*texts: object) -> None:
    dumped = json.dumps(texts, ensure_ascii=False, default=str)
    for value in PERSONAL_VALUES:
        assert value not in dumped


# --- (1) örnek olamayan dosya ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "reason"),
    [(b"%PDF-1.7\nbozuk", "açılamadı"), (b"", "boş"), (b"duz metin", "yalnız PDF, JPEG ve PNG")],
    ids=["bozuk-pdf", "bos", "metin"],
)
def test_a_file_that_cannot_be_an_example_fails_before_recognition(
    session: Session, layout: DataLayout, known: KnownTypes, content: bytes, reason: str
) -> None:
    item = _upload(session, layout, known, "belge.pdf", content, hint="turkish_passport")

    assert item.status == TrainingItemStatus.FAILED
    assert reason in (item.note or "")
    assert (item.checks_json, item.method, item.result_slug, item.staged_path) == (
        None,
        None,
        None,
        None,
    )
    assert _records(session) == []
    assert_employee_data_untouched(session, layout)


# --- (2) SHA-256 --------------------------------------------------------------------------------


def test_a_known_sha256_is_recognized_and_the_same_file_is_not_added_twice(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = make_portrait_image_bytes("JPEG")
    first = _upload(session, layout, known, "arnavut.jpg", content, hint="albanian_passport")

    again = _upload(session, layout, known, "tekrar.jpg", content)

    assert first.status == TrainingItemStatus.PLACED
    assert (again.status, again.result_slug, again.method) == (
        TrainingItemStatus.SKIPPED,
        "albanian_passport",
        TrainingMethod.MECHANICAL,
    )
    assert again.note == (
        "Mekanik: SHA-256 örnek kaydında → `albanian_passport`; JPEG; "
        f"zaten örnek: {_records(session)[0].name}"
    )
    assert again.checks_json is not None
    assert again.checks_json["sha256"] == {"index": ["albanian_passport"], "inventory": None}
    assert again.checks_json["result"] == {
        "slug": "albanian_passport",
        "basis": RecognitionBasis.SHA256_INDEX.value,
    }
    assert "mrz" not in again.checks_json  # ilk kesin sonuç kazanır: MRZ'ye bakılmadı
    assert len(_records(session)) == 1
    assert [example.name for example in list_examples(layout, "albanian_passport")] == [
        "arnavut.jpg"
    ]
    assert_employee_data_untouched(session, layout)


def test_an_inventory_sha256_places_the_file_into_its_type(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = make_half_filled_image_bytes("PNG")
    inventory = _write_inventory(
        layout,
        [
            ("kosovar_passport", "example", sha256_bytes(content)),
            ("afghan_passport", "reference", sha256_bytes(make_pdf_bytes(1))),
        ],
    )

    item = _upload(session, layout, known, "kosova.png", content, inventory=inventory)

    assert (item.status, item.result_slug, item.method) == (
        "placed",
        "kosovar_passport",
        "mechanical",
    )
    assert item.note == "Mekanik: SHA-256 örnek envanterinde → `kosovar_passport`; PNG"
    assert item.checks_json is not None
    assert item.checks_json["sha256"] == {"index": [], "inventory": ["kosovar_passport"]}
    [record] = _records(session)
    assert (record.type_slug, record.method, record.label) == (
        "kosovar_passport",
        "mechanical",
        None,
    )
    [event] = _placed_events(session)
    assert event.data_json is not None
    assert (event.data_json["method"], event.data_json["label"]) == ("mechanical", None)
    assert_employee_data_untouched(session, layout)


def test_an_inventory_file_already_in_its_folder_is_recorded_and_skipped(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = make_half_filled_image_bytes("PNG")
    kind = check_example("kosova.png", content, max_bytes=LIMIT)
    stored = store_example(layout, "kosovar_passport", "kosova.png", content, kind)
    inventory = _write_inventory(layout, [("kosovar_passport", "example", sha256_bytes(content))])

    item = _upload(session, layout, known, "baska-ad.png", content, inventory=inventory)

    assert (item.status, item.result_slug) == ("skipped", "kosovar_passport")
    [record] = _records(session)
    assert (record.name, record.method) == (stored.name, "legacy")
    assert len(list_examples(layout, "kosovar_passport")) == 1


def test_a_reference_row_or_an_unknown_slug_in_the_inventory_is_not_a_recognition(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    reference, unknown = make_half_filled_image_bytes("PNG"), make_portrait_image_bytes("PNG")
    inventory = _write_inventory(
        layout,
        [
            ("kosovar_passport", "reference", sha256_bytes(reference)),
            ("no_such_type", "example", sha256_bytes(unknown)),
        ],
    )

    first = _upload(session, layout, known, "ref.png", reference, inventory=inventory)
    second = _upload(session, layout, known, "bilinmez.png", unknown, inventory=inventory)

    for item in (first, second):
        assert item.status == TrainingItemStatus.AI_PENDING
        assert item.checks_json is not None
        assert item.checks_json["sha256"] == {"index": [], "inventory": []}
    assert _records(session) == []


def test_a_sha256_recorded_in_two_types_is_not_mechanical(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = make_portrait_image_bytes("JPEG")
    _upload(session, layout, known, "arnavut.jpg", content, hint="albanian_passport")
    inventory = _write_inventory(layout, [("afghan_passport", "example", sha256_bytes(content))])

    item = _upload(session, layout, known, "tekrar.jpg", content, inventory=inventory)

    assert item.status == TrainingItemStatus.AI_PENDING
    assert item.note == (
        "Mekanik tanınmadı: SHA-256 birden çok türde kayıtlı "
        "(`afghan_passport`, `albanian_passport`); JPEG"
    )


def test_without_an_inventory_file_the_sha256_step_uses_the_index_only(
    layout: DataLayout,
) -> None:
    assert not layout.example_inventory_path.exists()
    assert load_example_inventory(layout) is None


# --- envanter okuma ------------------------------------------------------------------------------


def test_the_inventory_reads_only_example_rows_with_a_valid_sha256() -> None:
    good, other = "a" * 64, "b" * 64
    text = (
        "﻿SLUG;Role;sha256;note\n"
        f"albanian_passport;example;{good.upper()};özel\n"
        f"afghan_passport;EXAMPLE;{good};\n"
        f"kosovar_passport;reference;{other};\n"
        f"kosovar_passport;example;kisa;\n"
        f";example;{other};\n"
        "eksik;example\n"
        f'turkish_passport;example;{other};"iki\nsatır"\n'
    )

    inventory = parse_example_inventory(text)

    assert dict(inventory.slugs_by_sha256) == {
        good: frozenset({"albanian_passport", "afghan_passport"}),
        other: frozenset({"turkish_passport"}),
    }
    assert inventory.slugs(good.upper()) == {"albanian_passport", "afghan_passport"}
    assert inventory.slugs("c" * 64) == frozenset()


@pytest.mark.parametrize("text", ["", "slug,sha256\nalbanian_passport," + "a" * 64 + "\n"])
def test_an_inventory_without_the_needed_columns_is_empty(text: str) -> None:
    assert dict(parse_example_inventory(text).slugs_by_sha256) == {}


# --- (3) ipucu ve yapı kuralları -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("hint", "name", "content", "note"),
    [
        (
            "turkish_passport",
            "pasaport.pdf",
            make_pdf_bytes(1),
            "Mekanik: beklenen tür → `turkish_passport`; PDF, 1 sayfa (beklenen 1–1)",
        ),
        (
            "turkish_passport",
            "pasaport.jpg",
            make_portrait_image_bytes("JPEG"),
            "Mekanik: beklenen tür → `turkish_passport`; JPEG",
        ),
        (
            "serbian_residence_card",
            "kart.pdf",
            make_pdf_bytes(2),
            "Mekanik: beklenen tür → `serbian_residence_card`; PDF, 2 sayfa (beklenen 1–2)",
        ),
        (
            "albanian_passport",
            "arnavut.png",
            make_portrait_image_bytes("PNG"),
            "Mekanik: beklenen tür → `albanian_passport`; PNG",
        ),
        (
            "albanian_passport",
            "arnavut.pdf",
            make_pdf_bytes(5),
            "Mekanik: beklenen tür → `albanian_passport`; PDF, 5 sayfa",
        ),
    ],
    ids=["katalog-pdf", "katalog-jpeg", "on-arka-iki-sayfa", "onerilen-png", "onerilen-pdf"],
)
def test_a_known_hint_whose_structure_holds_is_placed_mechanically(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    hint: str,
    name: str,
    content: bytes,
    note: str,
) -> None:
    item = _upload(session, layout, known, name, content, hint=hint)

    assert (item.status, item.result_slug, item.method, item.note) == (
        "placed",
        hint,
        "mechanical",
        note,
    )
    assert item.checks_json is not None
    assert item.checks_json["hint"] == {
        "slug": hint,
        "from": "expected",
        "known": True,
        "structure": [],
    }
    assert item.checks_json["result"] == {"slug": hint, "basis": "hint"}
    [record] = _records(session)
    assert (record.type_slug, record.method, record.label, record.note) == (
        hint,
        "mechanical",
        None,
        note,
    )
    assert_employee_data_untouched(session, layout)


@pytest.mark.parametrize(
    ("hint", "name", "content", "problem"),
    [
        (
            "turkish_passport",
            "pasaport.png",
            make_portrait_image_bytes("PNG"),
            "dosya türü PNG izinli değil (izinli: PDF, JPEG)",
        ),
        ("turkish_passport", "pasaport.pdf", make_pdf_bytes(2), "sayfa sayısı 2, beklenen 1–1"),
        (
            "serbian_driving_license",
            "ehliyet.pdf",
            make_pdf_bytes(3),
            "sayfa sayısı 3, beklenen 1–2",
        ),
        (
            "attachment",
            "ek.pdf",
            make_pdf_bytes(1),
            "dosya türü PDF izinli değil (izinli: DOC, DOCX, XLS, XLSX)",
        ),
    ],
    ids=["yanlis-dosya-turu", "fazla-sayfa", "on-arka-fazla-sayfa", "analiz-edilmeyen-tur"],
)
def test_a_hint_whose_structure_fails_goes_to_ai(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    hint: str,
    name: str,
    content: bytes,
    problem: str,
) -> None:
    item = _upload(session, layout, known, name, content, hint=hint)

    assert (item.status, item.result_slug, item.method) == ("ai_pending", None, None)
    assert item.note is not None
    assert item.note.startswith(f"Mekanik tanınmadı: beklenen tür `{hint}` yapısına uymuyor: ")
    assert problem in item.note
    assert item.checks_json is not None
    assert item.checks_json["hint"]["structure"] == [problem]
    assert item.checks_json["result"]["slug"] is None
    assert _records(session) == []
    assert _placed_events(session) == []
    assert_employee_data_untouched(session, layout)


def _map_item(
    session: Session, layout: DataLayout, content: bytes, hint: str, row: int = 12
) -> TrainingItem:
    run = _run(session, TrainingRunKind.MAP)
    return stage_file(
        session,
        layout,
        run,
        "harita-dosyasi.jpg",
        content,
        max_bytes=LIMIT,
        hint_slug=hint,
        row_number=row,
        source_ref="KnownDocuments/examples/x/harita-dosyasi.jpg",
    )


def test_a_map_row_whose_sha256_holds_is_placed_with_the_row_in_the_note(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = make_portrait_image_bytes("JPEG")
    item = _map_item(session, layout, content, "albanian_passport")

    outcome = recognize_item(
        session, layout, known, item, inventory=None, hint_sha256=sha256_bytes(content).upper()
    )

    assert outcome.status == TrainingItemStatus.PLACED
    assert outcome.recognition.basis is RecognitionBasis.HINT
    assert item.note == "Mekanik: harita satırı 12 → `albanian_passport`; SHA-256 tuttu; JPEG"
    assert item.checks_json is not None
    assert item.checks_json["hint"]["from"] == "map"
    assert item.checks_json["hint_sha256"] is True


def test_a_map_row_whose_sha256_does_not_hold_goes_to_ai(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = make_portrait_image_bytes("JPEG")
    item = _map_item(session, layout, content, "albanian_passport")

    outcome = recognize_item(session, layout, known, item, inventory=None, hint_sha256="0" * 64)

    assert (outcome.status, outcome.placement) == (TrainingItemStatus.AI_PENDING, None)
    assert item.note == "Mekanik tanınmadı: haritadaki SHA-256 dosyayla tutmuyor; JPEG"
    assert item.checks_json is not None
    assert item.checks_json["hint_sha256"] is False
    assert _records(session) == []


def test_a_hint_that_contradicts_the_sha256_record_goes_to_ai(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = make_portrait_image_bytes("JPEG")
    _upload(session, layout, known, "arnavut.jpg", content, hint="albanian_passport")

    item = _upload(session, layout, known, "afgan.jpg", content, hint="afghan_passport")

    assert item.status == TrainingItemStatus.AI_PENDING
    assert item.note == (
        "Mekanik tanınmadı: beklenen tür `afghan_passport` SHA-256 kaydıyla "
        "(`albanian_passport`) çelişiyor; JPEG"
    )
    assert len(_records(session)) == 1


def test_an_unknown_hint_is_ignored_and_recognition_continues_without_it(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    image = _upload(
        session, layout, known, "x.jpg", make_portrait_image_bytes("JPEG"), hint="no_such_type"
    )
    passport = _upload(session, layout, known, "p.pdf", _mrz_pdf(_mrz()), hint="no_such_type")

    assert image.status == TrainingItemStatus.AI_PENDING
    assert image.note == (
        "Mekanik tanınmadı: SHA-256 kayıtlı değil; görüntü dosyasında metin katmanı yok "
        "(OCR yapılmaz); ipucu `no_such_type` bilinen bir tür değil; JPEG"
    )
    assert image.checks_json is not None
    assert image.checks_json["hint"] == {"slug": "no_such_type", "from": "expected", "known": False}
    assert (passport.status, passport.result_slug) == ("placed", "turkish_passport")


# --- (4) PDF metin katmanında MRZ ----------------------------------------------------------------


def test_a_valid_td3_mrz_in_the_text_layer_recognizes_the_passport(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _upload(session, layout, known, "pasaport.pdf", _mrz_pdf(_mrz()))

    assert (item.status, item.result_slug, item.method) == (
        "placed",
        "turkish_passport",
        "mechanical",
    )
    assert item.note == (
        "Mekanik: PDF metin katmanında MRZ (TD3, P, TUR) → `turkish_passport`; "
        "kontrol haneleri tuttu; PDF, 1 sayfa (beklenen 1–1)"
    )
    assert item.checks_json is not None
    assert item.checks_json["mrz"] == {
        "status": "matched",
        "slug": "turkish_passport",
        "readings": [
            {
                "page": 1,
                "format": "TD3",
                "document_code": "P",
                "issuing_state": "TUR",
                "failed_checks": [],
            }
        ],
        "structure": [],
    }
    assert item.checks_json["result"] == {"slug": "turkish_passport", "basis": "mrz"}
    [record] = _records(session)
    [event] = _placed_events(session)
    _assert_no_personal_values(item.note, item.checks_json, record.note, event.data_json)
    _assert_no_personal_values(event.message)
    assert_employee_data_untouched(session, layout)


@pytest.mark.parametrize(
    ("lines", "slug", "described"),
    [
        (_mrz("TD1", "I", "SRB", number="S0000001"), "serbian_identity_card", "TD1, I, SRB"),
        (_mrz("TD1", "IR", "SRB", number="S0000001"), "serbian_residence_card", "TD1, IR, SRB"),
        (_mrz("TD1", "ID", "D", number="L0000001"), "german_identity_card", "TD1, ID, D"),
        (_mrz("TD2", "I", "ALB", number="A0000001"), "albanian_identity_card", "TD2, I, ALB"),
        (_mrz("TD3", "PD", "RKS"), "kosovar_passport", "TD3, PD, RKS"),
    ],
    ids=["td1-kimlik", "td1-oturum", "almanya-D", "td2-kimlik", "kosova-RKS-diplomatik"],
)
def test_mrz_codes_and_states_map_to_the_single_known_type(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    lines: tuple[str, ...],
    slug: str,
    described: str,
) -> None:
    item = _upload(session, layout, known, "kart.pdf", _mrz_pdf(lines, heading="KART"))

    assert (item.status, item.result_slug) == ("placed", slug)
    assert item.note is not None
    assert item.note.startswith(f"Mekanik: PDF metin katmanında MRZ ({described}) → `{slug}`")


def test_an_mrz_with_spaces_between_characters_is_still_read(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    first, second = _mrz()
    spaced = (" ".join(first), " ".join(second[:20]) + "  " + second[20:])

    item = _upload(session, layout, known, "pasaport.pdf", _mrz_pdf(spaced))

    assert (item.status, item.result_slug) == ("placed", "turkish_passport")


def test_an_mrz_whose_check_digits_fail_goes_to_ai(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _upload(session, layout, known, "pasaport.pdf", _mrz_pdf(_broken(_mrz())))

    assert (item.status, item.result_slug) == ("ai_pending", None)
    assert item.note == (
        "Mekanik tanınmadı: SHA-256 kayıtlı değil; MRZ kontrol haneleri tutmuyor "
        "(composite, document_number); PDF, 1 sayfa"
    )
    assert item.checks_json is not None
    assert item.checks_json["mrz"]["status"] == "failed_checks"
    assert item.checks_json["mrz"]["readings"][0]["failed_checks"] == [
        "document_number",
        "composite",
    ]
    _assert_no_personal_values(item.note, item.checks_json)
    assert_employee_data_untouched(session, layout)


@pytest.mark.parametrize(
    ("content", "reason", "status"),
    [
        (make_pdf_bytes(1), "PDF'te metin katmanı yok", "no_text"),
        (
            make_text_pdf_bytes(["TÜRKİYE CUMHURİYETİ\nPASAPORT"]),
            "PDF metin katmanında MRZ yok",
            "absent",
        ),
        (
            _mrz_pdf(_mrz("TD1", "AR", "D", number="L0000001")),
            "MRZ (TD1, AR, D) belge kodu bir belge türüne eşlenmiyor",
            "unmapped_code",
        ),
        (
            _mrz_pdf(_mrz("TD1", "I", "RUS", number="R0000001")),
            "MRZ (TD1, I, RUS) tek bir bilinen türe inmiyor",
            "no_type",
        ),
        (
            _mrz_pdf(_mrz("TD3", "P", "UTO")),
            "MRZ (TD3, P, UTO) tek bir bilinen türe inmiyor",
            "no_type",
        ),
        (
            _mrz_pdf(_mrz(), _mrz("TD3", "P", "SRB")),
            "MRZ'ler farklı türlere işaret ediyor (TD3, P, TUR; TD3, P, SRB)",
            "ambiguous",
        ),
    ],
    ids=["metinsiz", "mrz-yok", "eslenmeyen-kod", "belirsiz-cift", "bilinmeyen-ulke", "iki-mrz"],
)
def test_a_pdf_without_a_conclusive_mrz_goes_to_ai(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    content: bytes,
    reason: str,
    status: str,
) -> None:
    item = _upload(session, layout, known, "belge.pdf", content)

    assert item.status == TrainingItemStatus.AI_PENDING
    assert item.note is not None
    assert item.note.startswith(f"Mekanik tanınmadı: SHA-256 kayıtlı değil; {reason}; PDF, ")
    assert item.checks_json is not None
    assert item.checks_json["mrz"]["status"] == status
    assert _records(session) == []


def test_an_image_file_without_a_hint_goes_to_ai(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _upload(session, layout, known, "tarama.jpg", make_portrait_image_bytes("JPEG"))

    assert item.status == TrainingItemStatus.AI_PENDING
    assert item.note == (
        "Mekanik tanınmadı: SHA-256 kayıtlı değil; görüntü dosyasında metin katmanı yok "
        "(OCR yapılmaz); JPEG"
    )
    assert item.checks_json is not None
    assert item.checks_json["mrz"] == {"status": "not_pdf", "slug": None, "readings": []}
    assert "hint" not in item.checks_json


def test_an_mrz_type_whose_structure_fails_goes_to_ai(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _upload(session, layout, known, "pasaport.pdf", _mrz_pdf(_mrz(), None))

    assert item.status == TrainingItemStatus.AI_PENDING
    assert item.note == (
        "Mekanik tanınmadı: MRZ `turkish_passport` gösteriyor ama yapısına uymuyor: "
        "sayfa sayısı 2, beklenen 1–1; PDF, 2 sayfa"
    )
    assert item.checks_json is not None
    assert item.checks_json["mrz"]["structure"] == ["sayfa sayısı 2, beklenen 1–1"]


# --- ipucu ile MRZ ------------------------------------------------------------------------------


def test_a_hint_confirmed_by_the_mrz_is_placed_on_the_hint(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _upload(
        session, layout, known, "pasaport.pdf", _mrz_pdf(_mrz()), hint="turkish_passport"
    )

    assert (item.status, item.result_slug) == ("placed", "turkish_passport")
    assert item.note == (
        "Mekanik: beklenen tür → `turkish_passport`; MRZ (TD3, P, TUR) tuttu; "
        "PDF, 1 sayfa (beklenen 1–1)"
    )
    assert item.checks_json is not None
    assert item.checks_json["result"]["basis"] == "hint"


@pytest.mark.parametrize(
    ("hint", "lines"),
    [
        ("turkish_passport", _mrz("TD3", "P", "SRB")),
        ("turkish_passport", _mrz("TD1", "I", "TUR", number="T0000001")),
        ("serbian_residence_card", _mrz("TD1", "AR", "SRB", number="S0000001")),
        ("work_permit", _mrz("TD1", "IR", "SRB", number="S0000001")),
    ],
    ids=["baska-ulke", "baska-tur", "eslenmeyen-kod", "ciftsiz-ipucu"],
)
def test_a_hint_that_contradicts_a_valid_mrz_goes_to_ai(
    session: Session, layout: DataLayout, known: KnownTypes, hint: str, lines: tuple[str, ...]
) -> None:
    item = _upload(session, layout, known, "belge.pdf", _mrz_pdf(lines), hint=hint)

    assert item.status == TrainingItemStatus.AI_PENDING
    assert item.note is not None
    assert item.note.startswith(f"Mekanik tanınmadı: beklenen tür `{hint}` MRZ (")
    assert ") ile çelişiyor; PDF, 1 sayfa" in item.note
    assert _records(session) == []
    _assert_no_personal_values(item.note, item.checks_json)


def test_an_invalid_mrz_is_not_evidence_against_the_hint(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = _mrz_pdf(_broken(_mrz("TD3", "P", "SRB")))

    item = _upload(session, layout, known, "pasaport.pdf", content, hint="turkish_passport")

    assert (item.status, item.result_slug) == ("placed", "turkish_passport")
    assert item.note == "Mekanik: beklenen tür → `turkish_passport`; PDF, 1 sayfa (beklenen 1–1)"


# --- MRZ adayları ve kod eşlemesi -----------------------------------------------------------------


def test_mrz_candidates_are_consecutive_lines_of_one_mrz_length() -> None:
    first, second = _mrz()
    noise = "A" * 44
    texts = [
        None,
        f"başlık\n{noise}\n{first}\n\n{second}\nson",
        f"{first.lower()}\n{second.lower()}",
        f"{first[:36]}\n{second}",
        f"{first}\nara satır\n{second}",
    ]

    readings = find_mrz_readings(texts)

    # Gürültü satırı ile MRZ'nin ilk satırı da bir pencere olur; haneleri tutmadığı için kanıt
    # değildir. Küçük harfli, farklı uzunlukta ve araya satır girmiş adaylar pencere olmaz.
    noise_window, valid = readings
    assert (noise_window.page, noise_window.valid) == (2, False)
    assert valid == MrzReading(2, MrzFormat.TD3, "P", "TUR", ())


def test_mrz_readings_keep_no_personal_value() -> None:
    [reading] = find_mrz_readings(["\n".join(_mrz())])

    assert reading.as_check() == {
        "page": 1,
        "format": "TD3",
        "document_code": "P",
        "issuing_state": "TUR",
        "failed_checks": [],
    }
    _assert_no_personal_values(reading.as_check(), repr(reading))


@pytest.mark.parametrize(
    ("code", "kind"),
    [
        ("P", "pasaport"),
        ("PD", "pasaport"),
        ("V", "vize"),
        ("VD", "vize"),
        ("I", "kimlik_karti"),
        ("ID", "kimlik_karti"),
        ("A", "kimlik_karti"),
        ("C", "kimlik_karti"),
        ("IR", "oturum_izni"),
        ("R", "oturum_izni"),
        ("AR", None),
        ("IP", None),
        ("", None),
    ],
)
def test_mrz_document_codes_map_to_document_kinds(code: str, kind: str | None) -> None:
    assert mrz_doc_kind(code) == kind


def test_mrz_evidence_is_read_from_the_text_layer_only(known: KnownTypes) -> None:
    content = _mrz_pdf(_mrz())

    assert read_mrz_evidence(known, "jpeg", content).status is MrzSearchStatus.NOT_PDF
    unreadable = read_mrz_evidence(known, "pdf", b"%PDF-1.7\nbozuk")
    assert (unreadable.status, unreadable.reason()) == (
        MrzSearchStatus.UNREADABLE,
        "PDF metin katmanı okunamadı",
    )
    evidence = read_mrz_evidence(known, "pdf", content)
    assert (evidence.status, evidence.matched) == (
        MrzSearchStatus.MATCHED,
        known.get("turkish_passport"),
    )


# --- servis bağlantısı ----------------------------------------------------------------------------


def test_recognition_counts_the_run_and_writes_no_event_for_ai_pending(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    run = _run(session)
    _upload(session, layout, known, "pasaport.pdf", _mrz_pdf(_mrz()), run=run)
    _upload(session, layout, known, "tarama.jpg", make_portrait_image_bytes("JPEG"), run=run)
    _upload(session, layout, known, "bozuk.pdf", b"%PDF-1.7\nbozuk", run=run)

    assert run.counts_json == {"placed": 1, "ai_pending": 1, "failed": 1}
    assert run.status == "running"  # ai_pending öğe yapay zekâ yolunu bekliyor
    assert len(_placed_events(session)) == 1
    assert (
        list(
            session.scalars(
                select(Event).where(Event.type == EventType.TRAINING_ITEM_UNPLACED.value)
            )
        )
        == []
    )
    assert_employee_data_untouched(session, layout)


def test_recognize_item_accepts_only_queued_items(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _upload(session, layout, known, "tarama.jpg", make_portrait_image_bytes("JPEG"))
    assert item.status == TrainingItemStatus.AI_PENDING

    with pytest.raises(ItemNotPlaceableError, match="mekanik tanıma beklemiyor"):
        recognize_item(session, layout, known, item, inventory=None)


def test_recognize_needs_a_staged_item(session: Session, known: KnownTypes) -> None:
    item = TrainingItem(run=_run(session), original_name="yok.pdf")
    session.add(item)
    session.flush()

    with pytest.raises(ItemNotPlaceableError, match="staging"):
        recognize(session, known, item, b"", inventory=None)


def test_recognize_item_without_a_staged_file_is_rejected(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = TrainingItem(run=_run(session), original_name="yok.pdf", status="queued")
    session.add(item)
    session.flush()

    with pytest.raises(ItemNotPlaceableError, match="tanınacak dosya yok"):
        recognize_item(session, layout, known, item, inventory=None)


def test_a_file_already_in_its_example_folder_is_recorded_in_place(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = _mrz_pdf(_mrz())
    kind = check_example("pasaport.pdf", content, max_bytes=LIMIT)
    stored = store_example(layout, "turkish_passport", "pasaport.pdf", content, kind)
    source = layout.type_examples_dir("turkish_passport") / stored.name
    item = TrainingItem(
        run=_run(session, TrainingRunKind.MAP),
        original_name=stored.name,
        row_number=3,
        sha256=sha256_bytes(content),
        file_kind="pdf",
        page_count=1,
        status="queued",
    )
    session.add(item)
    session.flush()

    outcome = recognize_item(session, layout, known, item, inventory=None, source=source)

    assert outcome.status == TrainingItemStatus.PLACED
    assert outcome.placement is not None and outcome.placement.copied is False
    [record] = _records(session)
    assert (record.name, record.method) == (stored.name, "mechanical")
    assert len(list_examples(layout, "turkish_passport")) == 1


def test_a_mechanical_placement_uses_the_placement_core(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    # Mekanik yerleşen örnek ile İK'nın yerleştirdiği örnek aynı çekirdekten geçer: türler arası
    # tekrar tespiti mekanik tanımaya da uygulanır.
    content = make_portrait_image_bytes("JPEG")
    manual = stage_file(session, layout, _run(session), "el.jpg", content, max_bytes=LIMIT)
    place_example(
        session, layout, known, manual, "afghan_passport", method=TrainingMethod.MANUAL, actor="ik"
    )

    item = _upload(session, layout, known, "tekrar.jpg", content)

    assert (item.status, item.result_slug) == ("skipped", "afghan_passport")
    assert item.note is not None and item.note.startswith("Mekanik: SHA-256 örnek kaydında")
