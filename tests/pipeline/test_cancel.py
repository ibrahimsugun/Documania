"""10.3.6, 10.3.7 — süren partiyi iptal etme ve takılan partinin otomatik iptali
(`app.pipeline.cancel`; PLAN.md §D114).

Parti ve işi doğrudan veritabanına yazılır; saat her çağrıda `now` ile verilir — 10 dakikalık test
beklemez. Yapay zekâ, dosya ya da ağ yoktur; boru hattının iptale tepkisi `tests/worker/
test_cancel_worker.py`'dedir.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import (
    Event,
    JobStatus,
    Upload,
    UploadFile,
    UploadJob,
    UploadStatus,
)
from app.events import EventType
from app.pipeline.cancel import (
    CANCELLABLE_STATUSES,
    SYSTEM_ACTOR,
    CancelReason,
    UploadNotCancellableError,
    cancel_stale_uploads,
    cancel_upload,
)
from app.pipeline.orchestrate import UPLOAD_TRANSITIONS, UploadTransitionError, check_transition
from app.storage import find_original_by_sha256
from app.worker import (
    LeaseLostError,
    claim_next,
    claim_upload,
    enqueue_upload,
    renew_claim,
)
from app.worker.monitor import AlertKind, AlertThresholds, measure

T0 = datetime(2026, 10, 9, 9, 0, 0, tzinfo=UTC)
TIMEOUT = 600
USER = "ik-kullanici"
RUNNING = (
    UploadStatus.RECEIVED,
    UploadStatus.RENDERING,
    UploadStatus.ANALYZING,
    UploadStatus.PLANNING,
    UploadStatus.EXECUTING,
)
FINAL = (UploadStatus.DONE, UploadStatus.PARTIAL, UploadStatus.FAILED, UploadStatus.CANCELLED)


def _batch(
    session: Session,
    upload_id: str,
    status: UploadStatus = UploadStatus.RECEIVED,
    *,
    created_at: datetime = T0,
    job: bool = True,
) -> Upload:
    upload = Upload(id=upload_id, channel="web", status=status.value, created_at=created_at)
    session.add(upload)
    session.flush()
    if job:
        enqueue_upload(session, upload_id, now=created_at)
    session.commit()
    return upload


def _job(session: Session, upload_id: str) -> UploadJob:
    return session.scalars(
        select(UploadJob)
        .where(UploadJob.upload_id == upload_id)
        .execution_options(populate_existing=True)
    ).one()


def _cancellations(session: Session) -> list[Event]:
    return list(
        session.scalars(
            select(Event)
            .where(Event.type == EventType.UPLOAD_CANCELLED.value)
            .order_by(Event.id)
            .execution_options(populate_existing=True)
        )
    )


# --- durum makinesi --------------------------------------------------------------------------


def test_every_unfinished_status_can_be_cancelled_and_cancelled_is_a_dead_end() -> None:
    assert frozenset(RUNNING) == CANCELLABLE_STATUSES
    for status in RUNNING:
        check_transition(status, UploadStatus.CANCELLED)
    for status in FINAL:
        with pytest.raises(UploadTransitionError):
            check_transition(status, UploadStatus.CANCELLED)
    assert UPLOAD_TRANSITIONS[UploadStatus.CANCELLED] == frozenset()


# --- elle iptal (10.3.6) -----------------------------------------------------------------------


@pytest.mark.parametrize("status", RUNNING, ids=[status.value for status in RUNNING])
def test_a_running_batch_is_cancelled_its_job_dropped_and_the_user_logged(
    session: Session, status: UploadStatus
) -> None:
    upload = _batch(session, "u_1", status)

    cancellation = cancel_upload(
        session, upload, actor=USER, reason=CancelReason.MANUAL, now=T0 + timedelta(seconds=75)
    )
    session.commit()

    assert cancellation.stage is status
    assert session.get_one(Upload, "u_1").status == UploadStatus.CANCELLED
    job = _job(session, "u_1")
    assert (job.status, job.lease_expires_at) == (JobStatus.CANCELLED, None)
    assert job.finished_at == T0 + timedelta(seconds=75)
    (event,) = _cancellations(session)
    assert (event.upload_id, event.actor) == ("u_1", USER)
    assert event.data_json == {
        "stage": status.value,
        "reason": "manual",
        "waited_seconds": 75,
        "job_status": "queued",
    }


@pytest.mark.parametrize("status", FINAL, ids=[status.value for status in FINAL])
def test_a_final_batch_is_not_cancelled_and_nothing_is_written(
    session: Session, status: UploadStatus
) -> None:
    upload = _batch(session, "u_1", status)

    with pytest.raises(UploadNotCancellableError):
        cancel_upload(session, upload, actor=USER, reason=CancelReason.MANUAL)
    session.rollback()

    assert session.get_one(Upload, "u_1").status == status
    assert _job(session, "u_1").status == JobStatus.QUEUED
    assert _cancellations(session) == []


def test_cancelling_twice_writes_one_event(session: Session) -> None:
    upload = _batch(session, "u_1")
    cancel_upload(session, upload, actor=USER, reason=CancelReason.MANUAL)
    session.commit()

    with pytest.raises(UploadNotCancellableError):
        cancel_upload(session, upload, actor=SYSTEM_ACTOR, reason=CancelReason.TIMEOUT)
    session.rollback()

    assert len(_cancellations(session)) == 1


def test_the_batch_is_read_again_before_it_is_cancelled(session: Session) -> None:
    # Oturumdaki kopya bayat: parti bu arada başka bir işlemde bitti. İptal etmez.
    upload = _batch(session, "u_1", UploadStatus.EXECUTING)
    session.execute(
        Upload.__table__.update().where(Upload.id == "u_1").values(status=UploadStatus.DONE.value)
    )
    session.commit()

    with pytest.raises(UploadNotCancellableError):
        cancel_upload(session, upload, actor=USER, reason=CancelReason.MANUAL)


def test_a_manual_cancellation_needs_a_user_name(session: Session) -> None:
    upload = _batch(session, "u_1")

    with pytest.raises(ValueError, match="K16"):
        cancel_upload(session, upload, actor="  ", reason=CancelReason.MANUAL)


def test_a_batch_without_a_job_is_cancelled_too(session: Session) -> None:
    upload = _batch(session, "u_1", job=False)

    cancellation = cancel_upload(session, upload, actor=USER, reason=CancelReason.MANUAL)

    assert cancellation.job_status is None
    assert _cancellations(session)[0].data_json["job_status"] is None


def test_a_cancelled_job_is_never_taken_and_its_holder_loses_it(session: Session) -> None:
    upload = _batch(session, "u_1")
    claim = claim_upload(session, "u_1", token="isleyici-a", lease_seconds=60, now=T0)
    session.commit()
    assert claim is not None

    cancel_upload(session, upload, actor=USER, reason=CancelReason.MANUAL, now=T0)
    session.commit()

    assert _cancellations(session)[0].data_json["job_status"] == "running"
    with pytest.raises(LeaseLostError):
        renew_claim(session, claim, lease_seconds=60)
    session.rollback()
    later = T0 + timedelta(hours=1)
    assert claim_next(session, token="b", lease_seconds=60, max_attempts=3, now=later) is None


# --- zaman aşımı (10.3.7) ----------------------------------------------------------------------


def test_the_default_timeout_is_ten_minutes_built_in() -> None:
    assert Settings(_env_file=None, database_url="sqlite://").upload_timeout_seconds == TIMEOUT


@pytest.mark.parametrize(
    ("waited", "cancelled"),
    [
        (timedelta(minutes=9, seconds=59), False),
        (timedelta(minutes=10), False),
        (timedelta(minutes=10, seconds=1), True),
    ],
    ids=["9dk59sn", "10dk", "10dk1sn"],
)
def test_a_batch_older_than_the_timeout_is_cancelled_by_the_system(
    session: Session, waited: timedelta, cancelled: bool
) -> None:
    _batch(session, "u_1")

    result = cancel_stale_uploads(session, timeout_seconds=TIMEOUT, now=T0 + waited)
    session.commit()

    upload = session.get_one(Upload, "u_1")
    if not cancelled:
        assert result == []
        assert upload.status == UploadStatus.RECEIVED
        assert _cancellations(session) == []
        return
    assert result == ["u_1"]
    assert upload.status == UploadStatus.CANCELLED
    (event,) = _cancellations(session)
    assert event.actor == SYSTEM_ACTOR
    assert event.data_json == {
        "stage": "received",
        "reason": "timeout",
        "waited_seconds": 601,
        "job_status": "queued",
    }


def test_the_timeout_leaves_final_dismissed_and_young_batches_alone(session: Session) -> None:
    old = T0 - timedelta(hours=1)
    for status in FINAL:
        _batch(session, f"u_{status.value}", status, created_at=old)
    dismissed = _batch(session, "u_dismissed", UploadStatus.DONE, created_at=old)
    dismissed.dismissed_at, dismissed.dismissed_by = T0, USER
    _batch(session, "u_young", UploadStatus.ANALYZING, created_at=T0 - timedelta(minutes=5))
    _batch(session, "u_stuck_2", UploadStatus.EXECUTING, created_at=old + timedelta(minutes=1))
    _batch(session, "u_stuck_1", UploadStatus.RECEIVED, created_at=old)
    session.commit()

    assert cancel_stale_uploads(session, timeout_seconds=TIMEOUT, now=T0) == [
        "u_stuck_1",
        "u_stuck_2",
    ]
    session.commit()

    statuses = dict(session.execute(select(Upload.id, Upload.status)).tuples().all())
    assert statuses["u_young"] == UploadStatus.ANALYZING
    assert statuses["u_stuck_1"] == statuses["u_stuck_2"] == UploadStatus.CANCELLED
    for status in FINAL:
        assert statuses[f"u_{status.value}"] == status
    assert [event.upload_id for event in _cancellations(session)] == ["u_stuck_1", "u_stuck_2"]
    # İkinci denetim aynı partiyi yeniden iptal etmez, olay yazmaz.
    assert cancel_stale_uploads(session, timeout_seconds=TIMEOUT, now=T0) == []
    assert len(_cancellations(session)) == 2


def test_manual_and_automatic_cancellation_of_the_same_batch_write_one_event(
    session: Session,
) -> None:
    upload = _batch(session, "u_1")
    cancel_upload(session, upload, actor=USER, reason=CancelReason.MANUAL, now=T0)
    session.commit()

    assert cancel_stale_uploads(session, timeout_seconds=TIMEOUT, now=T0 + timedelta(hours=1)) == []

    (event,) = _cancellations(session)
    assert event.actor == USER


# --- tekrar tespiti (01.4.1, §D114 g) ------------------------------------------------------------


def _file(session: Session, upload_id: str, digest: str) -> UploadFile:
    row = UploadFile(
        upload_id=upload_id,
        original_name="a.pdf",
        stored_path=f"Inbox/{upload_id}/a.pdf",
        sha256=digest,
        mime="application/pdf",
    )
    session.add(row)
    session.flush()
    return row


def test_a_cancelled_batch_s_file_is_not_an_original(session: Session) -> None:
    digest = "ab" * 32
    upload = _batch(session, "u_1")
    _file(session, "u_1", digest)
    assert find_original_by_sha256(session, digest) is not None

    cancel_upload(session, upload, actor=USER, reason=CancelReason.MANUAL)

    assert find_original_by_sha256(session, digest) is None
    later = _batch(session, "u_2")
    second = _file(session, later.id, digest)
    assert find_original_by_sha256(session, digest) == second


# --- izleme ve hata oranı (13.6.1) ----------------------------------------------------------------


def test_the_alert_readings_do_not_count_cancelled_batches(
    session: Session, tmp_path: Path
) -> None:
    for number in range(3):
        upload = _batch(session, f"u_{number}", created_at=T0)
        cancel_upload(session, upload, actor=SYSTEM_ACTOR, reason=CancelReason.TIMEOUT, now=T0)
    session.commit()
    thresholds = AlertThresholds(
        error_count=1,
        error_window=timedelta(hours=1),
        disk_used_percent=100.0,
        job_queue_length=1,
        review_queue_length=1,
        interval=timedelta(seconds=60),
        repeat=timedelta(hours=6),
    )

    readings = {
        reading.kind: reading.value
        for reading in measure(session, tmp_path, thresholds, now=T0 + timedelta(minutes=1))
    }

    assert readings[AlertKind.ERRORS] == 0
    assert readings[AlertKind.JOB_QUEUE] == 0
