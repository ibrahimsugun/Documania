"""10.7.4 — kuyruk öğesini kapatma ve yeniden açma çekirdeği (`app.pipeline.queue_close`).

Kayıtlar sentetik satırlardır: parti, iki plan sürümü ve kuyruk öğeleri. Çekirdek yalnız
veritabanına yazar; dosya sistemine dokunmadığı, aday tür görülmelerinin kaldığı ve iki aşamalı
onayın panelde yürüdüğü `tests/web/test_queue_close.py`'dedir.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Event,
    Plan,
    QueueCloseReason,
    QueueItem,
    QueueKind,
    QueueResolution,
    Upload,
    UploadStatus,
    utcnow,
)
from app.events import EventType
from app.pipeline.queue_close import (
    ALREADY_RESOLVED,
    BATCH_DISMISSED,
    CLOSE_REASON_LABELS,
    NOT_CLOSED,
    NOTE_MAX_LENGTH,
    NOTE_REQUIRED,
    NOTE_TOO_LONG,
    CloseNoteError,
    QueueItemNotClosableError,
    QueueItemNotReopenableError,
    clean_close_note,
    close_queue_item,
    close_reason_label,
    closing_refusal,
    reopen_queue_item,
    reopening_refusal,
)
from app.pipeline.route import QueueItemNotFoundError

ACTOR = "ik-yonetici"
UPLOAD = "u_20260929_0001"
OTHER = "u_20260929_0002"
PAYLOAD = {"sources": [{"file_id": 1, "pages": [0]}], "document_type_slug": None}


def _upload(session: Session, upload_id: str) -> Upload:
    upload = Upload(id=upload_id, channel="web", status=UploadStatus.DONE.value)
    session.add(upload)
    session.flush()
    return upload


def _plan(session: Session, upload_id: str, version: int) -> Plan:
    plan = Plan(upload_id=upload_id, version=version, json={}, plan_hash=f"{version:064d}")
    session.add(plan)
    session.flush()
    return plan


def _item(
    session: Session,
    upload_id: str,
    plan: Plan | None,
    *,
    resolved: bool = False,
    resolution: QueueResolution | None = None,
) -> QueueItem:
    item = QueueItem(
        upload_id=upload_id,
        plan_id=plan.id if plan is not None else None,
        plan_item_id="i1",
        kind=QueueKind.UNKNOWN.value,
        reason="Tür katalogda yok",
        payload_json=PAYLOAD,
        resolved_at=utcnow() - timedelta(hours=1) if resolved else None,
        resolved_by="onceki-kullanici" if resolved else None,
        resolution=resolution.value if resolution is not None else None,
    )
    session.add(item)
    session.flush()
    return item


@pytest.fixture
def rows(session: Session) -> dict[str, QueueItem]:
    """Güncel planın bekleyen öğesi, eski sürümün öğesi, atanmış (nedeni boş), yoksayılmış ve
    başka partinin bekleyen öğesi."""
    _upload(session, UPLOAD)
    old, current = _plan(session, UPLOAD, 1), _plan(session, UPLOAD, 2)
    _upload(session, OTHER)
    other_plan = _plan(session, OTHER, 1)
    items = {
        "open": _item(session, UPLOAD, current),
        "superseded": _item(session, UPLOAD, old),
        "assigned": _item(session, UPLOAD, current, resolved=True),
        "dismissed": _item(
            session, UPLOAD, current, resolved=True, resolution=QueueResolution.DISMISSED
        ),
        "other": _item(session, OTHER, other_plan),
    }
    session.commit()
    return items


def _snapshot(session: Session) -> list[tuple[object, ...]]:
    session.expire_all()
    return [
        (
            item.id,
            item.plan_id,
            item.plan_item_id,
            item.kind,
            item.reason,
            item.payload_json,
            item.resolved_at,
            item.resolved_by,
            item.resolution,
            item.resolution_reason,
            item.resolution_note,
        )
        for item in session.scalars(select(QueueItem).order_by(QueueItem.id))
    ]


def _events(session: Session) -> list[Event]:
    return list(session.scalars(select(Event).order_by(Event.id)))


# --- kapatma --------------------------------------------------------------------------------------


def test_closing_resolves_the_item_with_the_reason_and_the_note_and_logs_the_user(
    session: Session, rows: dict[str, QueueItem]
) -> None:
    item = rows["open"]
    untouched = [row for row in _snapshot(session) if row[0] != item.id]
    before = utcnow()

    closed = close_queue_item(
        session,
        item.id,
        reason=QueueCloseReason.NOT_A_DOCUMENT,
        note="  boş arka sayfa  ",
        actor=ACTOR,
    )
    session.commit()

    assert closed is item
    assert item.resolved_at is not None and before <= item.resolved_at <= utcnow()
    assert item.resolved_by == ACTOR
    assert item.resolution == QueueResolution.CLOSED
    assert item.resolution_reason == QueueCloseReason.NOT_A_DOCUMENT
    assert item.resolution_note == "boş arka sayfa"
    # Öğenin kaydı ve planı değişmez (K9); öteki öğeler olduğu gibi kalır.
    assert (item.plan_id, item.plan_item_id, item.payload_json) == (
        rows["open"].plan_id,
        "i1",
        PAYLOAD,
    )
    assert [row for row in _snapshot(session) if row[0] != item.id] == untouched
    (event,) = _events(session)
    assert event.type == EventType.QUEUE_ITEM_CLOSED
    assert event.actor == ACTOR
    assert event.upload_id == UPLOAD
    # Not ve kişisel değer olaya girmez; onay olayı çağıranın işidir.
    assert event.data_json == {"queue_item_id": item.id, "reason": "not_a_document"}


def test_an_item_of_an_old_plan_version_can_be_closed_too(
    session: Session, rows: dict[str, QueueItem]
) -> None:
    item = rows["superseded"]

    close_queue_item(
        session, item.id, reason=QueueCloseReason.ALREADY_EXISTS, note=None, actor=ACTOR
    )

    assert item.resolution == QueueResolution.CLOSED
    assert item.resolution_reason == QueueCloseReason.ALREADY_EXISTS
    assert item.resolution_note is None


@pytest.mark.parametrize(
    ("reason", "note", "stored"),
    [
        (QueueCloseReason.NOT_A_DOCUMENT, None, None),
        (QueueCloseReason.ALREADY_EXISTS, "   ", None),
        (QueueCloseReason.OTHER, "yanlış müşteri", "yanlış müşteri"),
        (QueueCloseReason.OTHER, "x" * NOTE_MAX_LENGTH, "x" * NOTE_MAX_LENGTH),
    ],
)
def test_the_note_is_trimmed_and_optional_except_for_other(
    reason: QueueCloseReason, note: str | None, stored: str | None
) -> None:
    assert clean_close_note(reason, note) == stored


@pytest.mark.parametrize(
    ("reason", "note", "message"),
    [
        (QueueCloseReason.OTHER, None, NOTE_REQUIRED),
        (QueueCloseReason.OTHER, "  ", NOTE_REQUIRED),
        (QueueCloseReason.NOT_A_DOCUMENT, "x" * (NOTE_MAX_LENGTH + 1), NOTE_TOO_LONG),
    ],
)
def test_an_invalid_note_writes_nothing(
    session: Session,
    rows: dict[str, QueueItem],
    reason: QueueCloseReason,
    note: str | None,
    message: str,
) -> None:
    before = _snapshot(session)

    with pytest.raises(CloseNoteError) as refused:
        close_queue_item(session, rows["open"].id, reason=reason, note=note, actor=ACTOR)

    assert str(refused.value) == message
    assert _snapshot(session) == before
    assert _events(session) == []


@pytest.mark.parametrize("key", ["assigned", "dismissed"])
def test_a_resolved_item_is_not_closed(
    session: Session, rows: dict[str, QueueItem], key: str
) -> None:
    before = _snapshot(session)

    assert closing_refusal(session, rows[key]) == ALREADY_RESOLVED
    with pytest.raises(QueueItemNotClosableError, match="zaten çözülmüş"):
        close_queue_item(
            session, rows[key].id, reason=QueueCloseReason.OTHER, note="n", actor=ACTOR
        )

    assert _snapshot(session) == before
    assert _events(session) == []


def test_a_closed_item_is_closed_once(session: Session, rows: dict[str, QueueItem]) -> None:
    item = rows["open"]
    close_queue_item(
        session, item.id, reason=QueueCloseReason.NOT_A_DOCUMENT, note=None, actor=ACTOR
    )
    session.commit()

    with pytest.raises(QueueItemNotClosableError):
        close_queue_item(
            session, item.id, reason=QueueCloseReason.OTHER, note="ikinci", actor="baska"
        )
    session.rollback()

    session.refresh(item)
    assert (item.resolved_by, item.resolution_reason) == (ACTOR, "not_a_document")
    assert len(_events(session)) == 1


def test_an_item_of_a_dismissed_batch_is_not_closed(session: Session) -> None:
    upload = _upload(session, UPLOAD)
    upload.dismissed_at, upload.dismissed_by = utcnow(), ACTOR
    item = _item(session, UPLOAD, _plan(session, UPLOAD, 1))
    session.commit()

    assert closing_refusal(session, item) == BATCH_DISMISSED
    with pytest.raises(QueueItemNotClosableError, match="yoksayılmış"):
        close_queue_item(
            session, item.id, reason=QueueCloseReason.NOT_A_DOCUMENT, note=None, actor=ACTOR
        )
    assert item.resolved_at is None


def test_an_item_resolved_by_a_concurrent_request_is_not_closed_again(
    session: Session, rows: dict[str, QueueItem]
) -> None:
    item = rows["open"]
    # Öteki işlem öğeyi bu işlem okuduktan sonra atadı: koşullu güncelleme satır bulamaz.
    session.connection().exec_driver_sql(
        "UPDATE queue_items SET resolved_at = '2026-09-29 10:00:00', resolved_by = 'oteki' "
        f"WHERE id = {item.id}"
    )

    with pytest.raises(QueueItemNotClosableError, match="zaten çözülmüş"):
        close_queue_item(
            session, item.id, reason=QueueCloseReason.NOT_A_DOCUMENT, note=None, actor=ACTOR
        )

    assert item.resolved_by == "oteki" and item.resolution is None
    assert _events(session) == []


def test_closing_an_unknown_item_or_without_a_user_is_refused(
    session: Session, rows: dict[str, QueueItem]
) -> None:
    with pytest.raises(QueueItemNotFoundError):
        close_queue_item(
            session, 999_999, reason=QueueCloseReason.NOT_A_DOCUMENT, note=None, actor=ACTOR
        )
    with pytest.raises(ValueError, match="actor"):
        close_queue_item(
            session, rows["open"].id, reason=QueueCloseReason.NOT_A_DOCUMENT, note=None, actor=" "
        )

    assert rows["open"].resolved_at is None


def test_the_reason_labels_are_turkish() -> None:
    assert CLOSE_REASON_LABELS == {
        "not_a_document": "Belge değil / çöp sayfa",
        "already_exists": "Zaten var",
        "other": "Diğer",
    }
    assert set(CLOSE_REASON_LABELS) == {reason.value for reason in QueueCloseReason}
    assert close_reason_label("already_exists") == "Zaten var"
    assert close_reason_label(None) is None
    assert close_reason_label("eski_kod") == "eski_kod"


# --- yeniden açma ---------------------------------------------------------------------------------


def test_reopening_clears_the_resolution_keeps_the_plan_and_logs_the_user(
    session: Session, rows: dict[str, QueueItem]
) -> None:
    item = rows["open"]
    before = _snapshot(session)
    close_queue_item(
        session, item.id, reason=QueueCloseReason.OTHER, note="yanlışlıkla", actor="ilk"
    )
    session.commit()

    reopened = reopen_queue_item(session, item.id, actor=ACTOR)
    session.commit()

    assert reopened is item
    # Öğe kapatılmadan önceki hâline döner: plan, kayıt ve kaynaklar değişmedi (S18).
    assert _snapshot(session) == before
    closed_event, reopened_event = _events(session)
    assert closed_event.type == EventType.QUEUE_ITEM_CLOSED and closed_event.actor == "ilk"
    assert reopened_event.type == EventType.QUEUE_ITEM_REOPENED
    assert reopened_event.actor == ACTOR
    assert reopened_event.upload_id == UPLOAD
    assert reopened_event.data_json == {"queue_item_id": item.id, "reason": "other"}


@pytest.mark.parametrize("key", ["open", "assigned", "dismissed"])
def test_only_a_closed_item_is_reopened(
    session: Session, rows: dict[str, QueueItem], key: str
) -> None:
    before = _snapshot(session)

    assert reopening_refusal(session, rows[key]) == NOT_CLOSED
    with pytest.raises(QueueItemNotReopenableError, match="Yalnız kapatılan"):
        reopen_queue_item(session, rows[key].id, actor=ACTOR)

    assert _snapshot(session) == before
    assert _events(session) == []


def test_a_closed_item_of_a_dismissed_batch_waits_for_the_batch(
    session: Session, rows: dict[str, QueueItem]
) -> None:
    item = rows["open"]
    close_queue_item(
        session, item.id, reason=QueueCloseReason.NOT_A_DOCUMENT, note=None, actor=ACTOR
    )
    upload = session.get_one(Upload, UPLOAD)
    upload.dismissed_at, upload.dismissed_by = utcnow(), ACTOR
    session.commit()
    before = _snapshot(session)

    assert reopening_refusal(session, item) == BATCH_DISMISSED
    with pytest.raises(QueueItemNotReopenableError, match="yoksayılmış"):
        reopen_queue_item(session, item.id, actor=ACTOR)

    assert _snapshot(session) == before


def test_a_concurrent_reopening_that_already_won_is_refused(
    session: Session, rows: dict[str, QueueItem]
) -> None:
    item = rows["open"]
    close_queue_item(
        session, item.id, reason=QueueCloseReason.NOT_A_DOCUMENT, note=None, actor=ACTOR
    )
    session.commit()
    session.connection().exec_driver_sql(
        "UPDATE queue_items SET resolved_at = NULL, resolved_by = NULL, resolution = NULL, "
        f"resolution_reason = NULL WHERE id = {item.id}"
    )

    with pytest.raises(QueueItemNotReopenableError, match="Yalnız kapatılan"):
        reopen_queue_item(session, item.id, actor="ikinci")

    assert [event.type for event in _events(session)] == [EventType.QUEUE_ITEM_CLOSED]


def test_reopening_an_unknown_item_or_without_a_user_is_refused(
    session: Session, rows: dict[str, QueueItem]
) -> None:
    with pytest.raises(QueueItemNotFoundError):
        reopen_queue_item(session, 999_999, actor=ACTOR)
    with pytest.raises(ValueError, match="actor"):
        reopen_queue_item(session, rows["open"].id, actor="")
