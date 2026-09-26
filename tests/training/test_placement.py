"""11.9 — eğitim çekirdeği: çalıştırma, `_egitim/gelen` staging'i, örneğe yerleştirme, türler arası
SHA-256 dizini, yerinde kayıt, olaylar ve değişmez güvence (PLAN.md §C86).

Veri sentetiktir (`tests/fixtures/gen.py`); gerçek kimlik belgesi yoktur."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.storage.atomic as atomic
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
from app.storage import ContentMismatchError, DataLayout, find_original_by_sha256, sha256_bytes
from app.storage.examples import check_example, list_examples, store_example
from app.training import (
    SYSTEM_ACTOR,
    ItemNotPlaceableError,
    KnownTypes,
    UnknownTypeError,
    create_run,
    place_example,
    refresh_run,
    stage_file,
)
from tests.fixtures.gen import (
    make_docx_bytes,
    make_pdf_bytes,
    make_portrait_image_bytes,
)
from tests.training.invariants import assert_employee_data_untouched

LIMIT = 1024 * 1024
CATALOG_SLUG = "turkish_passport"
SUGGESTED_SLUG = "albanian_passport"
OTHER_SLUG = "afghan_passport"


def _run(session: Session) -> TrainingRun:
    return create_run(session, kind=TrainingRunKind.UPLOAD, created_by="ik")


def _stage(
    session: Session, layout: DataLayout, run: TrainingRun, name: str, content: bytes
) -> TrainingItem:
    return stage_file(session, layout, run, name, content, max_bytes=LIMIT)


def _files(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def _events(session: Session, event_type: EventType) -> list[Event]:
    return list(session.scalars(select(Event).where(Event.type == event_type.value)))


def _records(session: Session) -> list[ExampleFileRecord]:
    return list(session.scalars(select(ExampleFileRecord).order_by(ExampleFileRecord.id)))


# --- çalıştırma ve staging -----------------------------------------------------------------------


def test_a_new_run_is_running_and_counts_nothing(session: Session) -> None:
    run = create_run(session, kind=TrainingRunKind.MAP, created_by="ik", map_name="envanter.csv")

    assert (run.kind, run.created_by, run.map_name) == ("map", "ik", "envanter.csv")
    assert (run.status, run.counts_json) == ("running", {})


@pytest.mark.parametrize(
    ("name", "content", "extension", "kind", "pages"),
    [
        ("pasaport.pdf", make_pdf_bytes(2), "pdf", "pdf", 2),
        ("kimlik.jpeg", make_portrait_image_bytes("JPEG"), "jpg", "jpeg", 1),
        ("kart.png", make_portrait_image_bytes("PNG"), "png", "png", 1),
        # Uzantı içerikten gelir: adı `.jpg` olan PDF `.pdf` olarak yazılır.
        ("tarama.jpg", make_pdf_bytes(1), "pdf", "pdf", 1),
    ],
    ids=["pdf", "jpeg", "png", "pdf-named-jpg"],
)
def test_an_upload_is_staged_atomically_under_egitim_gelen(
    session: Session,
    layout: DataLayout,
    name: str,
    content: bytes,
    extension: str,
    kind: str,
    pages: int,
) -> None:
    run = _run(session)

    item = _stage(session, layout, run, name, content)

    staged = f"KnownDocuments/_egitim/gelen/{run.id}/{item.id}.{extension}"
    assert item.staged_path == staged
    assert (layout.root / staged).read_bytes() == content
    assert (item.status, item.original_name, item.sha256) == ("queued", name, sha256_bytes(content))
    assert (item.file_kind, item.page_count, item.method, item.result_slug) == (
        kind,
        pages,
        None,
        None,
    )
    assert _files(layout.root) == [staged]
    assert (run.status, run.counts_json) == ("running", {"queued": 1})


@pytest.mark.parametrize(
    ("name", "content", "reason"),
    [
        ("sozlesme.docx", make_docx_bytes(), "yalnız PDF, JPEG ve PNG"),
        ("bos.pdf", b"", "boş"),
        ("buyuk.pdf", b"%PDF-1.7\n" + b"0" * LIMIT, "MB sınırını aşıyor"),
        ("bozuk.pdf", b"%PDF-1.7\nbozuk", "açılamadı"),
    ],
    ids=["docx", "empty", "too-large", "corrupt"],
)
def test_a_file_that_cannot_be_an_example_fails_and_writes_nothing(
    session: Session, layout: DataLayout, name: str, content: bytes, reason: str
) -> None:
    run = _run(session)

    item = _stage(session, layout, run, name, content)

    assert item.status == "failed"
    assert reason in (item.note or "")
    assert (item.staged_path, item.sha256, item.file_kind) == (None, None, None)
    assert (item.decided_by, item.decided_at is not None) == (SYSTEM_ACTOR, True)
    assert _files(layout.root) == []
    assert (run.status, run.counts_json) == ("done", {"failed": 1})


def test_an_interrupted_staging_leaves_no_file(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(session)

    def refuse(*_args: object) -> None:
        raise OSError("disk dolu")

    monkeypatch.setattr(atomic.os, "link", refuse)
    with pytest.raises(OSError, match="disk dolu"):
        _stage(session, layout, run, "pasaport.pdf", make_pdf_bytes())

    # Ne yayınlanmış dosya ne yarım kalmış geçici dosya: hedefte ya tam dosya vardır ya hiç yoktur.
    assert _files(layout.root) == []


def test_an_uploaded_name_cannot_reach_a_path(session: Session, layout: DataLayout) -> None:
    run = _run(session)

    item = _stage(session, layout, run, "..\\..\\Inbox\\kimlik.png", make_portrait_image_bytes())

    assert item.original_name == "kimlik.png"
    assert _files(layout.root) == [f"KnownDocuments/_egitim/gelen/{run.id}/{item.id}.jpg"]


# --- yerleştirme ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "actor", "label"),
    [
        (TrainingMethod.MECHANICAL, SYSTEM_ACTOR, None),
        (TrainingMethod.AI, SYSTEM_ACTOR, "ai_decision"),
        (TrainingMethod.MANUAL, "ik", "verified"),
    ],
)
def test_a_placed_example_is_copied_recorded_and_logged(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    method: TrainingMethod,
    actor: str,
    label: str | None,
) -> None:
    run = _run(session)
    content = make_pdf_bytes(1)
    item = _stage(session, layout, run, "Pasaport Taraması.pdf", content)
    note = "Mekanik: beklenen tür → `turkish_passport`; PDF"

    placement = place_example(
        session, layout, known, item, CATALOG_SLUG, method=method, note=note, actor=actor
    )

    # Kopya: örnek klasörüne aynı baytlar, `_egitim/gelen` kopyası yerinde kalır (K11, silme yok).
    assert (placement.status, placement.copied, placement.note) == ("placed", True, note)
    example_dir = f"KnownDocuments/examples/{CATALOG_SLUG}"
    assert _files(layout.root) == [
        f"KnownDocuments/_egitim/gelen/{run.id}/{item.id}.pdf",
        f"{example_dir}/Pasaport-Taramasi.pdf",
    ]
    assert (layout.root / example_dir / "Pasaport-Taramasi.pdf").read_bytes() == content
    (record,) = _records(session)
    assert record is placement.example
    assert (record.type_slug, record.name, record.sha256) == (
        CATALOG_SLUG,
        "Pasaport-Taramasi.pdf",
        sha256_bytes(content),
    )
    assert (record.method, record.label, record.note, record.training_item_id) == (
        method.value,
        label,
        note,
        item.id,
    )
    assert (item.status, item.result_slug, item.method, item.note) == (
        "placed",
        CATALOG_SLUG,
        method.value,
        note,
    )
    assert (item.decided_by, item.decided_at is not None) == (actor, True)
    assert (run.status, run.counts_json) == ("done", {"placed": 1})
    (event,) = _events(session, EventType.TRAINING_EXAMPLE_PLACED)
    assert event.actor == actor
    assert event.data_json == {
        "run_id": run.id,
        "training_item_id": item.id,
        "example_file_id": record.id,
        "type_slug": CATALOG_SLUG,
        "method": method.value,
        "label": label,
        "in_place": False,
    }
    # Olay dosya adını taşımaz (CONVENTIONS §6); partiye, dosyaya, çalışana bağlanmaz.
    assert "Pasaport" not in (event.message or "")
    assert (event.upload_id, event.file_id, event.employee_id, event.document_id) == (
        None,
        None,
        None,
        None,
    )


def test_a_suggested_type_outside_the_catalog_receives_examples(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _stage(session, layout, _run(session), "a.png", make_portrait_image_bytes("PNG"))

    place_example(session, layout, known, item, SUGGESTED_SLUG, method=TrainingMethod.MECHANICAL)

    assert [example.name for example in list_examples(layout, SUGGESTED_SLUG)] == ["a.png"]
    assert (item.status, item.result_slug, item.note) == ("placed", SUGGESTED_SLUG, None)


def test_the_same_content_in_the_same_type_is_skipped(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = make_portrait_image_bytes("JPEG")
    run = _run(session)
    first = _stage(session, layout, run, "ilk.jpg", content)
    place_example(session, layout, known, first, SUGGESTED_SLUG, method=TrainingMethod.AI)
    second = _stage(session, layout, run, "ikinci.jpg", content)

    placement = place_example(
        session, layout, known, second, SUGGESTED_SLUG, method=TrainingMethod.AI, note="AI kararı"
    )

    assert placement.status == "skipped" and placement.copied is False
    assert placement.example.name == "ilk.jpg"
    assert (second.status, second.result_slug, second.note) == (
        "skipped",
        SUGGESTED_SLUG,
        "AI kararı; zaten örnek: ilk.jpg",
    )
    assert [example.name for example in list_examples(layout, SUGGESTED_SLUG)] == ["ilk.jpg"]
    assert len(_records(session)) == 1
    (event,) = _events(session, EventType.TRAINING_ITEM_UNPLACED)
    assert event.data_json == {
        "run_id": run.id,
        "training_item_id": second.id,
        "status": "skipped",
        "type_slug": SUGGESTED_SLUG,
        "example_file_id": placement.example.id,
        "example_type_slug": SUGGESTED_SLUG,
    }
    assert "ilk" not in (event.message or "")
    assert run.counts_json == {"placed": 1, "skipped": 1}


def test_the_same_content_in_another_type_is_a_conflict(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = make_pdf_bytes(1)
    run = _run(session)
    first = _stage(session, layout, run, "ilk.pdf", content)
    place_example(session, layout, known, first, OTHER_SLUG, method=TrainingMethod.MECHANICAL)
    second = _stage(session, layout, run, "ikinci.pdf", content)

    placement = place_example(
        session, layout, known, second, SUGGESTED_SLUG, method=TrainingMethod.MANUAL, actor="ik"
    )

    assert placement.status == "conflict" and placement.copied is False
    assert (second.status, second.result_slug, second.note, second.decided_by) == (
        "conflict",
        SUGGESTED_SLUG,
        f"başka türde örnek: {OTHER_SLUG}",
        "ik",
    )
    assert list_examples(layout, SUGGESTED_SLUG) == []
    assert len(_records(session)) == 1
    (event,) = _events(session, EventType.TRAINING_ITEM_UNPLACED)
    assert event.actor == "ik"
    assert event.data_json["status"] == "conflict"
    assert event.data_json["example_type_slug"] == OTHER_SLUG
    assert run.counts_json == {"placed": 1, "conflict": 1}


def test_an_unrecorded_example_already_in_the_folder_is_recorded_as_legacy(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    # Tür sayfasından el ile yüklenmiş örnek (11.2.1) kayıtsızdır; aynı içerik eğitimde gelince
    # kopya yazılmaz, var olan dosya `legacy` olarak kaydedilir ve türler arası dizine girer.
    content = make_portrait_image_bytes("PNG")
    store_example(
        layout, SUGGESTED_SLUG, "elle.png", content, check_example("e", content, max_bytes=LIMIT)
    )
    run = _run(session)
    item = _stage(session, layout, run, "egitim.png", content)

    placement = place_example(
        session, layout, known, item, SUGGESTED_SLUG, method=TrainingMethod.MECHANICAL
    )

    assert placement.status == "skipped"
    assert item.note == "zaten örnek: elle.png"
    assert [example.name for example in list_examples(layout, SUGGESTED_SLUG)] == ["elle.png"]
    (legacy,) = _records(session)
    assert (legacy.type_slug, legacy.name, legacy.method, legacy.label) == (
        SUGGESTED_SLUG,
        "elle.png",
        "legacy",
        None,
    )
    assert legacy.training_item_id is None

    other = _stage(session, layout, run, "baska.png", content)
    conflict = place_example(
        session, layout, known, other, OTHER_SLUG, method=TrainingMethod.MECHANICAL
    )

    assert conflict.status == "conflict"
    assert list_examples(layout, OTHER_SLUG) == []


def test_a_file_already_in_the_example_folder_is_recorded_in_place(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = make_pdf_bytes(2)
    stored = store_example(
        layout, SUGGESTED_SLUG, "yerinde.pdf", content, check_example("y", content, max_bytes=LIMIT)
    )
    source = layout.type_examples_dir(SUGGESTED_SLUG) / stored.name
    before = _files(layout.root)
    run = create_run(session, kind=TrainingRunKind.MAP, created_by="ik", map_name="harita.csv")
    item = TrainingItem(
        run=run,
        original_name="yerinde.pdf",
        row_number=12,
        source_ref=f"KnownDocuments/examples/{SUGGESTED_SLUG}/yerinde.pdf",
        hint_slug=SUGGESTED_SLUG,
    )
    session.add(item)
    session.flush()

    placement = place_example(
        session,
        layout,
        known,
        item,
        SUGGESTED_SLUG,
        method=TrainingMethod.MECHANICAL,
        note="Mekanik: harita satırı 12 → `albanian_passport`; PDF",
        source=source,
    )

    # Kopyalanmaz: diskte hiçbir şey değişmez, dosya yerinde kaydedilir.
    assert (placement.status, placement.copied) == ("placed", False)
    assert _files(layout.root) == before
    (record,) = _records(session)
    assert (record.name, record.sha256, record.training_item_id) == (
        "yerinde.pdf",
        sha256_bytes(content),
        item.id,
    )
    assert (item.sha256, item.file_kind, item.page_count, item.staged_path) == (
        sha256_bytes(content),
        "pdf",
        2,
        None,
    )
    (event,) = _events(session, EventType.TRAINING_EXAMPLE_PLACED)
    assert event.data_json["in_place"] is True

    # Aynı harita yeniden taranırsa kayıtlı (SHA, tür) öğe atlanır (§C87).
    again = TrainingItem(run=run, original_name="yerinde.pdf", row_number=12)
    session.add(again)
    session.flush()
    skipped = place_example(
        session,
        layout,
        known,
        again,
        SUGGESTED_SLUG,
        method=TrainingMethod.MECHANICAL,
        source=source,
    )

    assert skipped.status == "skipped"
    assert again.note == "zaten örnek: yerinde.pdf"
    assert _files(layout.root) == before


def test_a_file_in_another_types_folder_is_copied_not_recorded_in_place(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = make_portrait_image_bytes("JPEG")
    stored = store_example(
        layout, OTHER_SLUG, "baska.jpg", content, check_example("b", content, max_bytes=LIMIT)
    )
    run = _run(session)
    item = TrainingItem(run=run, original_name="baska.jpg")
    session.add(item)
    session.flush()

    placement = place_example(
        session,
        layout,
        known,
        item,
        SUGGESTED_SLUG,
        method=TrainingMethod.MECHANICAL,
        source=layout.type_examples_dir(OTHER_SLUG) / stored.name,
    )

    assert (placement.status, placement.copied) == ("placed", True)
    assert [example.name for example in list_examples(layout, SUGGESTED_SLUG)] == ["baska.jpg"]


# --- reddedilen yerleştirmeler -------------------------------------------------------------------


def _nothing_written(session: Session, layout: DataLayout, before: list[str]) -> None:
    assert _files(layout.root) == before
    assert _records(session) == []
    assert session.scalar(select(func.count()).select_from(Event)) == 0


def test_an_unknown_type_is_refused(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _stage(session, layout, _run(session), "a.pdf", make_pdf_bytes())
    before = _files(layout.root)

    with pytest.raises(UnknownTypeError, match="martian_passport"):
        place_example(
            session, layout, known, item, "martian_passport", method=TrainingMethod.MANUAL
        )

    assert item.status == "queued"
    _nothing_written(session, layout, before)


@pytest.mark.parametrize("status", ["placed", "skipped", "failed"])
def test_an_item_in_its_final_state_is_not_placed_again(
    session: Session, layout: DataLayout, known: KnownTypes, status: str
) -> None:
    item = _stage(session, layout, _run(session), "a.pdf", make_pdf_bytes())
    item.status = status
    before = _files(layout.root)

    with pytest.raises(ItemNotPlaceableError, match="son kararında"):
        place_example(session, layout, known, item, CATALOG_SLUG, method=TrainingMethod.MANUAL)

    _nothing_written(session, layout, before)


@pytest.mark.parametrize("status", ["queued", "ai_pending", "unplaced", "conflict", "review"])
def test_waiting_items_can_be_placed(
    session: Session, layout: DataLayout, known: KnownTypes, status: str
) -> None:
    item = _stage(session, layout, _run(session), "a.pdf", make_pdf_bytes())
    item.status = status

    placement = place_example(
        session, layout, known, item, CATALOG_SLUG, method=TrainingMethod.MANUAL, actor="ik"
    )

    assert placement.status == TrainingItemStatus.PLACED


def test_an_item_without_a_file_is_refused(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    run = _run(session)
    item = TrainingItem(run=run, original_name="yok.pdf")
    session.add(item)
    session.flush()

    with pytest.raises(ItemNotPlaceableError, match="dosya yok"):
        place_example(session, layout, known, item, CATALOG_SLUG, method=TrainingMethod.MANUAL)

    _nothing_written(session, layout, [])


def test_a_source_that_is_not_an_example_kind_is_refused(
    session: Session, layout: DataLayout, known: KnownTypes, tmp_path: Path
) -> None:
    source = tmp_path / "sozlesme.docx"
    source.write_bytes(make_docx_bytes())
    item = TrainingItem(run=_run(session), original_name="sozlesme.docx")
    session.add(item)
    session.flush()

    with pytest.raises(ItemNotPlaceableError, match="PDF, JPEG ya da PNG değil"):
        place_example(
            session,
            layout,
            known,
            item,
            CATALOG_SLUG,
            method=TrainingMethod.MECHANICAL,
            source=source,
        )

    _nothing_written(session, layout, [])


def test_a_staged_file_that_changed_is_refused(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    item = _stage(session, layout, _run(session), "a.pdf", make_pdf_bytes(1))
    staged = layout.resolve(item.staged_path or "")
    staged.write_bytes(make_pdf_bytes(2))
    before = _files(layout.root)

    with pytest.raises(ContentMismatchError):
        place_example(session, layout, known, item, CATALOG_SLUG, method=TrainingMethod.MANUAL)

    assert item.status == "queued"
    _nothing_written(session, layout, before)


# --- çalıştırmanın sayaçları ---------------------------------------------------------------------


def test_a_run_stays_running_while_the_system_still_has_to_decide(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    run = _run(session)
    placed = _stage(session, layout, run, "a.pdf", make_pdf_bytes(1))
    waiting = _stage(session, layout, run, "b.pdf", make_pdf_bytes(2))
    _stage(session, layout, run, "c.docx", make_docx_bytes())
    place_example(session, layout, known, placed, CATALOG_SLUG, method=TrainingMethod.MECHANICAL)
    waiting.status = TrainingItemStatus.AI_PENDING.value

    refresh_run(session, run)
    assert (run.status, run.counts_json) == (
        "running",
        {"placed": 1, "ai_pending": 1, "failed": 1},
    )

    waiting.status = TrainingItemStatus.UNPLACED.value
    refresh_run(session, run)
    # İK'nın kararını bekleyen öğe çalıştırmayı açık tutmaz.
    assert (run.status, run.counts_json) == ("done", {"placed": 1, "failed": 1, "unplaced": 1})


# --- değişmez güvence ----------------------------------------------------------------------------


def test_training_leaves_employee_data_alone(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    # Eğitim yolu parti, dosya, sayfa, plan, çalışan, kuyruk öğesi, belge ya da aday tür açmaz;
    # Inbox, çalışan, kuyruk, arşiv ve önbellek dizinlerine dosya koymaz (§C86, PRD 11.9.1).
    passport = make_pdf_bytes(1)
    card = make_portrait_image_bytes("JPEG")
    run = _run(session)
    items = [
        _stage(session, layout, run, "pasaport.pdf", passport),
        _stage(session, layout, run, "kart.jpg", card),
        _stage(session, layout, run, "yine.pdf", passport),
        _stage(session, layout, run, "baska.jpg", card),
        _stage(session, layout, run, "sozlesme.docx", make_docx_bytes()),
    ]
    place_example(session, layout, known, items[0], CATALOG_SLUG, method=TrainingMethod.MECHANICAL)
    place_example(session, layout, known, items[1], SUGGESTED_SLUG, method=TrainingMethod.AI)
    place_example(session, layout, known, items[2], CATALOG_SLUG, method=TrainingMethod.AI)
    place_example(
        session, layout, known, items[3], OTHER_SLUG, method=TrainingMethod.MANUAL, actor="ik"
    )
    session.commit()

    assert [item.status for item in items] == ["placed", "placed", "skipped", "conflict", "failed"]
    assert_employee_data_untouched(session, layout)
    # K10: eğitim içeriği gerçek bir yüklemeyi "tekrar" işaretlemez.
    for content in (passport, card):
        assert find_original_by_sha256(session, sha256_bytes(content)) is None
    # Yazılan her dosya `KnownDocuments` altındadır.
    assert all(path.startswith("KnownDocuments/") for path in _files(layout.root))
