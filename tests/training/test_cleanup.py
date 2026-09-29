"""11.9.6 — eğitim temizliği çekirdeği: öğeyi yoksay / geri al, çalıştırmayı arşivle / geri al, tür
sayfasından yüklenen örneğin kaydı ve kayıtsız örneklerin bir kez kaydı (`app.training.cleanup`,
PLAN.md §C92-c).

Veri sentetiktir (`tests/fixtures/gen.py`); gerçek kimlik belgesi ve yapay zekâ çağrısı yoktur."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.db.models import (
    Event,
    ExampleFileRecord,
    ExampleLabel,
    ExampleMethod,
    TrainingItem,
    TrainingItemStatus,
    TrainingMethod,
    TrainingRun,
    TrainingRunKind,
)
from app.db.session import create_session_factory
from app.events import EventType
from app.storage import DataLayout, sha256_bytes
from app.storage.examples import check_example, list_examples, store_example
from app.training import (
    DISMISSABLE_STATUSES,
    CleanupError,
    CleanupNoteError,
    KnownTypes,
    archive_run,
    create_run,
    dismiss_item,
    leave_unplaced,
    listed_hashes,
    place_example,
    record_uploaded_example,
    refresh_run,
    register_examples,
    remove_example,
    restore_item,
    restore_run,
    same_type_example,
    stage_file,
)
from app.training import cleanup as cleanup_module
from app.training.cleanup import (
    DISMISSED_NOTE,
    NOT_DISMISSABLE,
    NOT_DISMISSED,
    NOTE_TOO_LONG,
    REGISTERED_NOTE,
    RESTORED_NOTE,
    RUN_ALREADY_ARCHIVED,
    RUN_NOT_ARCHIVED,
    UPLOADED_NOTE,
    clean_note,
)
from tests.fixtures.gen import make_pdf_bytes, make_portrait_image_bytes
from tests.training.invariants import assert_employee_data_untouched

LIMIT = 1024 * 1024
ACTOR = "ik"
SLUG = "albanian_passport"


def _png(width: int) -> bytes:
    return make_portrait_image_bytes("PNG", (width, 300))


def _item(
    session: Session,
    layout: DataLayout,
    run: TrainingRun,
    status: TrainingItemStatus,
    *,
    width: int = 200,
    note: str = "bilinen türe inmedi",
) -> TrainingItem:
    """`status` durumunda bir öğe (yerleşmeyenler `leave_unplaced` ile, sistemin notuyla)."""
    item = stage_file(session, layout, run, f"dosya-{width}.png", _png(width), max_bytes=LIMIT)
    if status in DISMISSABLE_STATUSES:
        leave_unplaced(session, item, status, note=note, method=TrainingMethod.AI)
    elif status is not TrainingItemStatus.QUEUED:
        item.status = status.value
        refresh_run(session, run)
    return item


def _events(session: Session, event_type: EventType) -> list[Event]:
    return list(
        session.scalars(select(Event).where(Event.type == event_type.value).order_by(Event.id))
    )


@pytest.fixture
def run(session: Session) -> TrainingRun:
    return create_run(session, kind=TrainingRunKind.UPLOAD, created_by=ACTOR)


# --- öğeyi yoksay / geri al -------------------------------------------------------------------


@pytest.mark.parametrize("status", sorted(DISMISSABLE_STATUSES))
def test_an_item_waiting_for_hr_is_dismissed_with_the_note_kept_and_an_event(
    session: Session, layout: DataLayout, run: TrainingRun, status: TrainingItemStatus
) -> None:
    item = _item(session, layout, run, status)
    staged = layout.resolve(item.staged_path or "")
    before = staged.read_bytes()

    dismiss_item(session, item, actor=ACTOR, note="  çöp tarama  ")
    session.commit()

    assert item.status == TrainingItemStatus.DISMISSED
    assert item.note == f"bilinen türe inmedi; {DISMISSED_NOTE}: çöp tarama"
    assert item.decided_by == ACTOR and item.decided_at is not None
    # Dosya yerinde ve aynı; örnek kaydı açılmaz (R11).
    assert staged.read_bytes() == before
    assert session.scalars(select(ExampleFileRecord)).all() == []
    (event,) = _events(session, EventType.TRAINING_ITEM_DISMISSED)
    assert event.actor == ACTOR
    assert event.data_json == {
        "training_item_id": item.id,
        "run_id": run.id,
        "previous_status": status.value,
        "status": "dismissed",
    }
    # Not ve dosya adı olaya girmez (CONVENTIONS §6).
    assert "çöp" not in (event.message or "") and "dosya-" not in str(event.data_json)
    assert run.counts_json == {"dismissed": 1}
    assert_employee_data_untouched(session, layout)


def test_a_dismissal_without_a_note_says_only_that_hr_dismissed_it(
    session: Session, layout: DataLayout, run: TrainingRun
) -> None:
    item = _item(session, layout, run, TrainingItemStatus.UNPLACED, note="")
    item.note = None

    dismiss_item(session, item, actor=ACTOR, note="   ")

    assert item.note == DISMISSED_NOTE


@pytest.mark.parametrize(
    "status",
    [
        TrainingItemStatus.QUEUED,
        TrainingItemStatus.AI_PENDING,
        TrainingItemStatus.PLACED,
        TrainingItemStatus.SKIPPED,
        TrainingItemStatus.FAILED,
        TrainingItemStatus.DISMISSED,
    ],
)
def test_only_items_waiting_for_hr_can_be_dismissed(
    session: Session, layout: DataLayout, run: TrainingRun, status: TrainingItemStatus
) -> None:
    item = _item(session, layout, run, status)
    note = item.note

    with pytest.raises(CleanupError, match=NOT_DISMISSABLE):
        dismiss_item(session, item, actor=ACTOR)

    assert item.status == status and item.note == note
    assert _events(session, EventType.TRAINING_ITEM_DISMISSED) == []


def test_a_too_long_note_dismisses_nothing(
    session: Session, layout: DataLayout, run: TrainingRun
) -> None:
    item = _item(session, layout, run, TrainingItemStatus.UNPLACED)

    with pytest.raises(CleanupNoteError, match=NOTE_TOO_LONG):
        dismiss_item(session, item, actor=ACTOR, note="x" * 201)

    assert item.status == TrainingItemStatus.UNPLACED
    assert clean_note("x" * 200) == "x" * 200
    assert clean_note(None) is None


def test_the_actor_is_required(session: Session, layout: DataLayout, run: TrainingRun) -> None:
    item = _item(session, layout, run, TrainingItemStatus.UNPLACED)

    for call in (
        lambda: dismiss_item(session, item, actor=" "),
        lambda: restore_item(session, item, actor=""),
        lambda: archive_run(session, run, actor=""),
    ):
        with pytest.raises(ValueError, match="actor"):
            call()
    assert item.status == TrainingItemStatus.UNPLACED and run.archived_at is None


def test_a_dismissal_racing_another_decision_changes_nothing(
    session: Session, engine: Engine, layout: DataLayout, run: TrainingRun
) -> None:
    item = _item(session, layout, run, TrainingItemStatus.UNPLACED)
    session.commit()
    # Başka bir işlem (ör. "Türe yerleştir") öğeyi bu arada karara bağladı.
    with create_session_factory(engine)() as other:
        other.execute(
            update(TrainingItem).where(TrainingItem.id == item.id).values(status="placed")
        )
        other.commit()
    session.expire(item, ["decided_at"])  # nesne eski durumu (`unplaced`) taşır

    with pytest.raises(CleanupError, match=NOT_DISMISSABLE):
        dismiss_item(session, item, actor=ACTOR)

    assert item.status == TrainingItemStatus.PLACED
    assert _events(session, EventType.TRAINING_ITEM_DISMISSED) == []


def test_restoring_a_dismissed_item_makes_it_wait_as_unplaced(
    session: Session, layout: DataLayout, run: TrainingRun
) -> None:
    item = _item(session, layout, run, TrainingItemStatus.CONFLICT)
    dismiss_item(session, item, actor=ACTOR)

    restore_item(session, item, actor="ik2")
    session.commit()

    assert item.status == TrainingItemStatus.UNPLACED
    assert item.note == f"bilinen türe inmedi; {DISMISSED_NOTE}; {RESTORED_NOTE}"
    assert item.decided_by == "ik2"
    (event,) = _events(session, EventType.TRAINING_ITEM_RESTORED)
    assert event.actor == "ik2"
    assert event.data_json == {
        "training_item_id": item.id,
        "run_id": run.id,
        "previous_status": "dismissed",
        "status": "unplaced",
    }
    assert run.counts_json == {"unplaced": 1}


def test_only_a_dismissed_item_is_restored(
    session: Session, layout: DataLayout, run: TrainingRun
) -> None:
    item = _item(session, layout, run, TrainingItemStatus.UNPLACED)

    with pytest.raises(CleanupError, match=NOT_DISMISSED):
        restore_item(session, item, actor=ACTOR)

    assert _events(session, EventType.TRAINING_ITEM_RESTORED) == []


def test_run_counts_add_dismissed_and_keep_the_other_counters(
    session: Session, layout: DataLayout, run: TrainingRun
) -> None:
    kept = _item(session, layout, run, TrainingItemStatus.UNPLACED, width=200)
    dropped = _item(session, layout, run, TrainingItemStatus.UNPLACED, width=210)
    _item(session, layout, run, TrainingItemStatus.FAILED, width=220)
    assert run.counts_json == {"unplaced": 2, "failed": 1}

    dismiss_item(session, dropped, actor=ACTOR)

    assert run.counts_json == {"unplaced": 1, "failed": 1, "dismissed": 1}
    assert kept.status == TrainingItemStatus.UNPLACED
    assert run.status == "done"


# --- çalıştırmayı arşivle / geri al -----------------------------------------------------------


def test_archiving_a_run_keeps_its_items_and_examples(
    session: Session, layout: DataLayout, known: KnownTypes, run: TrainingRun
) -> None:
    placed = stage_file(session, layout, run, "yer.png", _png(230), max_bytes=LIMIT)
    place_example(session, layout, known, placed, SLUG, method=TrainingMethod.MANUAL, actor=ACTOR)
    waiting = _item(session, layout, run, TrainingItemStatus.UNPLACED)
    items_before = [(i.id, i.status, i.note) for i in run.items]
    examples_before = [
        (e.id, e.type_slug, e.name) for e in session.scalars(select(ExampleFileRecord))
    ]
    counts = dict(run.counts_json)

    archive_run(session, run, actor=ACTOR)
    session.commit()

    assert run.archived_at is not None
    assert [(i.id, i.status, i.note) for i in run.items] == items_before
    assert [
        (e.id, e.type_slug, e.name) for e in session.scalars(select(ExampleFileRecord))
    ] == examples_before
    assert [e.name for e in list_examples(layout, SLUG)] == ["yer.png"]
    assert run.counts_json == counts and waiting.status == TrainingItemStatus.UNPLACED
    (event,) = _events(session, EventType.TRAINING_RUN_ARCHIVED)
    assert event.actor == ACTOR
    assert event.data_json == {"run_id": run.id, "restored": False}

    with pytest.raises(CleanupError, match=RUN_ALREADY_ARCHIVED):
        archive_run(session, run, actor=ACTOR)

    restore_run(session, run, actor="ik2")
    session.commit()
    assert run.archived_at is None
    events = _events(session, EventType.TRAINING_RUN_ARCHIVED)
    assert [(e.actor, e.data_json) for e in events][1] == (
        "ik2",
        {"run_id": run.id, "restored": True},
    )
    with pytest.raises(CleanupError, match=RUN_NOT_ARCHIVED):
        restore_run(session, run, actor=ACTOR)
    assert len(_events(session, EventType.TRAINING_RUN_ARCHIVED)) == 2
    assert_employee_data_untouched(session, layout)


# --- katalog örneklerinin kaydı ---------------------------------------------------------------


def _stored(layout: DataLayout, name: str, content: bytes, slug: str = SLUG):  # type: ignore[no-untyped-def]
    kind = check_example(name, content, max_bytes=LIMIT)
    return store_example(layout, slug, name, content, kind)


def test_an_uploaded_example_is_recorded_as_manual_and_verified_without_an_event(
    session: Session, layout: DataLayout
) -> None:
    content = _png(240)
    stored = _stored(layout, "ön.png", content)

    record = record_uploaded_example(session, SLUG, stored)
    session.commit()

    assert (record.type_slug, record.name, record.sha256) == (SLUG, "on.png", sha256_bytes(content))
    assert record.method == ExampleMethod.MANUAL
    assert record.label == ExampleLabel.VERIFIED
    assert record.training_item_id is None
    assert record.note == UPLOADED_NOTE
    assert session.scalars(select(Event)).all() == []


def test_the_same_type_example_is_found_by_record_or_by_folder(
    session: Session, layout: DataLayout
) -> None:
    recorded, legacy, other = _png(250), _png(260), _png(270)
    record_uploaded_example(session, SLUG, _stored(layout, "kayitli.png", recorded))
    _stored(layout, "eski.png", legacy)  # kaydı olmayan eski dosya
    record_uploaded_example(
        session, "afghan_passport", _stored(layout, "b.png", other, "afghan_passport")
    )
    listed = listed_hashes(layout, SLUG)

    assert listed == {sha256_bytes(recorded): "kayitli.png", sha256_bytes(legacy): "eski.png"}
    assert same_type_example(session, SLUG, sha256_bytes(recorded)) == "kayitli.png"
    assert same_type_example(session, SLUG, sha256_bytes(legacy)) is None
    assert same_type_example(session, SLUG, sha256_bytes(legacy), listed) == "eski.png"
    # Başka türdeki aynı içerik bu türde örnek sayılmaz.
    assert same_type_example(session, SLUG, sha256_bytes(other), listed) is None


def test_a_removed_example_does_not_count_as_the_same_type_example(
    session: Session, layout: DataLayout
) -> None:
    content = _png(280)
    record = record_uploaded_example(session, SLUG, _stored(layout, "c.png", content))
    remove_example(session, layout, record, actor=ACTOR)

    assert (
        same_type_example(session, SLUG, sha256_bytes(content), listed_hashes(layout, SLUG)) is None
    )


def test_register_examples_records_unregistered_files_once(
    session: Session, layout: DataLayout
) -> None:
    record_uploaded_example(session, SLUG, _stored(layout, "kayitli.png", _png(290)))
    legacy = [("a.png", _png(300)), ("b.pdf", make_pdf_bytes(1))]
    for name, content in legacy:
        _stored(layout, name, content)
    _stored(layout, "c.png", _png(310), "afghan_passport")
    (layout.examples / "notlar").mkdir()  # içinde örnek olmayan klasör
    (layout.examples / "_gizli").mkdir()  # slug olamayan klasör adı: taranmaz
    (layout.examples / "_gizli" / "x.png").write_bytes(_png(320))
    (layout.examples / "tek-dosya.png").write_bytes(_png(330))  # klasör değil
    calls: list[tuple[int, int]] = []

    result = register_examples(session, layout, progress=lambda i, n: calls.append((i, n)))
    session.commit()

    assert (result.types, result.listed, result.recorded, result.registered) == (3, 4, 1, 3)
    assert calls == [(1, 3), (2, 3), (3, 3)]
    rows = session.scalars(
        select(ExampleFileRecord).where(ExampleFileRecord.method == ExampleMethod.LEGACY.value)
    ).all()
    assert sorted((r.type_slug, r.name) for r in rows) == [
        ("afghan_passport", "c.png"),
        (SLUG, "a.png"),
        (SLUG, "b.pdf"),
    ]
    by_name = {r.name: r for r in rows}
    assert by_name["b.pdf"].sha256 == sha256_bytes(make_pdf_bytes(1))
    assert all(r.label is None and r.note == REGISTERED_NOTE for r in rows)
    assert session.scalars(select(Event)).all() == []

    again = register_examples(session, layout)
    assert (again.listed, again.recorded, again.registered) == (4, 4, 0)
    assert_employee_data_untouched(session, layout)


def test_a_file_back_in_place_of_a_removed_record_is_registered_again(
    session: Session, layout: DataLayout
) -> None:
    content = _png(340)
    record = record_uploaded_example(session, SLUG, _stored(layout, "geri.png", content))
    remove_example(session, layout, record, actor=ACTOR)
    (layout.type_examples_dir(SLUG) / "geri.png").write_bytes(content)

    result = register_examples(session, layout)

    assert result.registered == 1
    active = session.scalars(
        select(ExampleFileRecord).where(ExampleFileRecord.removed_at.is_(None))
    ).all()
    assert [(r.name, r.method) for r in active] == [("geri.png", "legacy")]


def test_register_examples_skips_a_file_that_vanished_and_an_empty_tree(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stored(layout, "gidecek.png", _png(350))

    def vanished(path):  # type: ignore[no-untyped-def]
        raise FileNotFoundError(path)

    monkeypatch.setattr(cleanup_module, "sha256_file", vanished)
    result = register_examples(session, layout)
    assert (result.listed, result.registered) == (1, 0)
    assert listed_hashes(layout, SLUG) == {}
    assert session.scalars(select(ExampleFileRecord)).all() == []

    empty = DataLayout(layout.root / "bos")
    assert register_examples(session, empty) == cleanup_module.RegisterResult(0, 0, 0, 0)
