"""10.3.4 — taramayı (partiyi) yoksayma çekirdeği (`app.pipeline.dismiss`).

Kayıtlar sentetik satırlardır: parti, iki plan sürümü, çıktılar ve kuyruk öğeleri. Yoksayma yalnız
veritabanına yazar; dosya sistemine dokunmadığı ve iki aşamalı onayın panelde yürüdüğü
`tests/web/test_upload_dismiss.py`'dedir.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import import_catalog, load_seed_catalog
from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    Event,
    Plan,
    QueueItem,
    QueueKind,
    QueueResolution,
    Upload,
    UploadStatus,
    utcnow,
)
from app.events import EventType
from app.pipeline.dismiss import (
    DismissalPreview,
    UploadNotDismissableError,
    check_dismissable,
    dismiss_upload,
    is_dismissed,
    preview_dismissal,
)

ACTOR = "ik-yonetici"
UPLOAD = "u_20260922_0001"
OTHER = "u_20260922_0002"


def _upload(session: Session, upload_id: str, status: UploadStatus = UploadStatus.DONE) -> Upload:
    upload = Upload(id=upload_id, channel="web", status=status.value)
    session.add(upload)
    session.flush()
    return upload


def _plan(session: Session, upload_id: str, version: int) -> Plan:
    plan = Plan(upload_id=upload_id, version=version, json={}, plan_hash=f"{version:064d}")
    session.add(plan)
    session.flush()
    return plan


def _document(session: Session, plan: Plan, status: DocumentStatus) -> Document:
    document = Document(
        employee_id="E0001",
        type_slug="russian_passport",
        path=f"Employees/Test_Kisi_E0001/Hazir/belge-{plan.id}-{status.value}.pdf",
        format="pdf",
        plan_id=plan.id,
        source_refs_json=[],
        status=status.value,
    )
    session.add(document)
    session.flush()
    return document


def _queue_item(
    session: Session, upload_id: str, plan: Plan | None, *, resolved: bool = False
) -> QueueItem:
    item = QueueItem(
        upload_id=upload_id,
        plan_id=plan.id if plan is not None else None,
        plan_item_id="i1",
        kind=QueueKind.UNREADABLE.value,
        reason="Okunamayan alanlar: document_number",
        resolved_at=utcnow() - timedelta(hours=1) if resolved else None,
        resolved_by="onceki-kullanici" if resolved else None,
    )
    session.add(item)
    session.flush()
    return item


@pytest.fixture
def batch(session: Session) -> dict[str, object]:
    """İki plan sürümlü parti: eski ve güncel sürümün çözülmemiş öğeleri, çözülmüş bir öğe, etkin,
    eski sürüm ve arşivlenmiş çıktılar; ayrıca başka bir partinin öğesi ve çıktısı."""
    import_catalog(session, load_seed_catalog())
    session.add(
        Employee(id="E0001", folder_name="Test_Kisi_E0001", given_names="Test", surname="Kisi")
    )
    upload = _upload(session, UPLOAD)
    old, current = _plan(session, UPLOAD, 1), _plan(session, UPLOAD, 2)
    _upload(session, OTHER)
    other_plan = _plan(session, OTHER, 1)
    rows: dict[str, object] = {
        "upload": upload,
        "old_open": _queue_item(session, UPLOAD, old),
        "open": _queue_item(session, UPLOAD, current),
        "planless": _queue_item(session, UPLOAD, None),
        "resolved": _queue_item(session, UPLOAD, current, resolved=True),
        "other_open": _queue_item(session, OTHER, other_plan),
        "active": _document(session, current, DocumentStatus.ACTIVE),
        "superseded": _document(session, old, DocumentStatus.SUPERSEDED),
        "archived": _document(session, current, DocumentStatus.ARCHIVED),
        "other_active": _document(session, other_plan, DocumentStatus.ACTIVE),
    }
    session.commit()
    return rows


def test_the_preview_counts_unresolved_items_and_active_documents_of_the_batch_only(
    session: Session, batch: dict[str, object]
) -> None:
    upload = batch["upload"]
    assert isinstance(upload, Upload)

    assert preview_dismissal(session, upload) == DismissalPreview(queue_items=3, active_documents=1)
    assert not session.new and not session.dirty


def test_dismissal_marks_the_batch_and_closes_every_unresolved_item_with_the_reason(
    session: Session, batch: dict[str, object]
) -> None:
    upload = batch["upload"]
    assert isinstance(upload, Upload)
    before = utcnow()

    dismissal = dismiss_upload(session, upload, actor=ACTOR)
    session.commit()

    assert is_dismissed(upload)
    assert upload.dismissed_by == ACTOR
    assert upload.dismissed_at is not None and before <= upload.dismissed_at <= utcnow()
    assert upload.status == UploadStatus.DONE  # durum makinesi değişmez (09.2.1)
    closed = [batch[key] for key in ("old_open", "open", "planless")]
    assert all(isinstance(item, QueueItem) for item in closed)
    assert dismissal.queue_item_ids == tuple(
        item.id for item in closed if isinstance(item, QueueItem)
    )
    for item in closed:
        assert isinstance(item, QueueItem)
        session.refresh(item)
        assert item.resolved_at == upload.dismissed_at
        assert item.resolved_by == ACTOR
        assert item.resolution == QueueResolution.DISMISSED
    # Daha önce çözülmüş öğe ve başka partinin öğesi değişmez.
    resolved, other = batch["resolved"], batch["other_open"]
    assert isinstance(resolved, QueueItem) and isinstance(other, QueueItem)
    assert resolved.resolved_by == "onceki-kullanici" and resolved.resolution is None
    assert other.resolved_at is None and other.resolution is None
    # Çıktılar yerinde, durumları değişmez; kaldırmak arşivin işidir (08.4.1).
    active = batch["active"]
    assert isinstance(active, Document)
    assert dismissal.active_document_ids == (active.id,)
    assert [
        document.status for document in session.scalars(select(Document).order_by(Document.id))
    ] == [
        DocumentStatus.ACTIVE,
        DocumentStatus.SUPERSEDED,
        DocumentStatus.ARCHIVED,
        DocumentStatus.ACTIVE,
    ]


def test_dismissal_writes_upload_dismissed_with_the_user_and_the_ids_only(
    session: Session, batch: dict[str, object]
) -> None:
    upload = batch["upload"]
    assert isinstance(upload, Upload)

    dismissal = dismiss_upload(session, upload, actor=ACTOR)
    session.commit()

    (event,) = session.scalars(
        select(Event).where(Event.type == EventType.UPLOAD_DISMISSED.value)
    ).all()
    assert event.actor == ACTOR
    assert event.upload_id == UPLOAD
    assert event.data_json == {
        "queue_item_ids": list(dismissal.queue_item_ids),
        "active_document_ids": list(dismissal.active_document_ids),
    }
    # Onay olayı çağıranın işidir (`app.web.confirm`); çekirdek yazmaz.
    assert (
        session.scalars(select(Event).where(Event.type == EventType.USER_CONFIRMED.value)).all()
        == []
    )


def test_a_batch_without_items_or_outputs_is_dismissed_with_empty_lists(session: Session) -> None:
    upload = _upload(session, UPLOAD, UploadStatus.FAILED)
    session.commit()

    assert preview_dismissal(session, upload) == DismissalPreview(0, 0)
    dismissal = dismiss_upload(session, upload, actor=ACTOR)

    assert dismissal.queue_item_ids == () and dismissal.active_document_ids == ()
    assert is_dismissed(upload)


@pytest.mark.parametrize(
    "status",
    [
        UploadStatus.RECEIVED,
        UploadStatus.RENDERING,
        UploadStatus.ANALYZING,
        UploadStatus.PLANNING,
        UploadStatus.EXECUTING,
    ],
)
def test_a_running_batch_is_not_dismissed_and_nothing_is_written(
    session: Session, status: UploadStatus
) -> None:
    upload = _upload(session, UPLOAD, status)
    item = _queue_item(session, UPLOAD, None)
    session.commit()

    with pytest.raises(UploadNotDismissableError, match="işleniyor"):
        dismiss_upload(session, upload, actor=ACTOR)
    session.rollback()

    session.refresh(upload)
    session.refresh(item)
    assert upload.dismissed_at is None and item.resolved_at is None
    assert session.scalars(select(Event)).all() == []


@pytest.mark.parametrize("status", [UploadStatus.DONE, UploadStatus.PARTIAL, UploadStatus.FAILED])
def test_every_final_status_can_be_dismissed(session: Session, status: UploadStatus) -> None:
    upload = _upload(session, UPLOAD, status)

    check_dismissable(upload)
    dismiss_upload(session, upload, actor=ACTOR)

    assert is_dismissed(upload)


def test_a_batch_is_dismissed_once(session: Session, batch: dict[str, object]) -> None:
    upload = batch["upload"]
    assert isinstance(upload, Upload)
    dismiss_upload(session, upload, actor=ACTOR)
    session.commit()
    first_at = upload.dismissed_at

    with pytest.raises(UploadNotDismissableError, match="zaten"):
        dismiss_upload(session, upload, actor="baska-kullanici")
    session.rollback()

    session.refresh(upload)
    assert upload.dismissed_at == first_at and upload.dismissed_by == ACTOR
    events = session.scalars(
        select(Event).where(Event.type == EventType.UPLOAD_DISMISSED.value)
    ).all()
    assert len(events) == 1


def test_a_concurrent_dismissal_that_already_won_is_refused(
    session: Session, batch: dict[str, object]
) -> None:
    upload = batch["upload"]
    assert isinstance(upload, Upload)
    # Öteki işlem partiyi bu işlem okuduktan sonra yoksaydı: koşullu güncelleme satır bulamaz.
    session.connection().exec_driver_sql(
        "UPDATE uploads SET dismissed_at = '2026-09-22 10:00:00', dismissed_by = 'oteki' "
        f"WHERE id = '{UPLOAD}'"
    )

    with pytest.raises(UploadNotDismissableError, match="zaten"):
        dismiss_upload(session, upload, actor=ACTOR)

    open_item = batch["open"]
    assert isinstance(open_item, QueueItem)
    assert session.scalar(select(QueueItem.resolved_at).where(QueueItem.id == open_item.id)) is None


def test_a_dismissal_needs_a_user_name(session: Session, batch: dict[str, object]) -> None:
    upload = batch["upload"]
    assert isinstance(upload, Upload)

    with pytest.raises(ValueError, match="actor"):
        dismiss_upload(session, upload, actor="  ")

    assert not is_dismissed(upload)
