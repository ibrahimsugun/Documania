"""13.6.1 — hata, disk doluluğu ve kuyruk uzunluğu için uyarı üretilir.

Ölçümler gerçek veritabanına (geçici SQLite) karşı çalışır; disk yalnız kullanım sayıları
sahtelenerek denenir (gerçek diski doldurmak gerekmez). Zaman `now` ile verilir. Veri sentetiktir;
uyarı metni yalnız sayı ve yüzde taşır (CONVENTIONS §6) — bunu da sınarız.
"""

from __future__ import annotations

import logging
import threading
from collections import namedtuple
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import (
    JobStatus,
    Plan,
    QueueItem,
    QueueKind,
    Upload,
    UploadJob,
    utcnow,
)
from app.events import EventType, record_event
from app.storage import DataLayout
from app.web.routers.queue import QueueState, _counts
from app.worker import monitor
from app.worker.monitor import (
    ADVICE,
    CLEAR_RATIO,
    LABELS,
    AlertKind,
    AlertThresholds,
    AlertTracker,
    AlertWatch,
    Notice,
    NoticeState,
    Reading,
    measure,
)
from app.worker.queue import enqueue_upload
from app.worker.runner import Worker

Usage = namedtuple("Usage", "total used free")  # noqa: PYI024 — shutil.disk_usage'in biçimi
NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
SECRET = "Ekaterina Ornekova 00 0000001"
GIB = 1024**3


def _disk(monkeypatch: pytest.MonkeyPatch, *, used: int, free: int) -> None:
    usage = Usage(used + free, used, free)
    monkeypatch.setattr(monitor.shutil, "disk_usage", lambda _path: usage)


def _reading(kind: AlertKind, readings: list[Reading]) -> Reading:
    (found,) = [reading for reading in readings if reading.kind is kind]
    return found


def _values(readings: list[Reading]) -> dict[AlertKind, float]:
    return {reading.kind: reading.value for reading in readings}


def _failures(session_factory: sessionmaker[Session], count: int, *, at: datetime) -> None:
    with session_factory() as session:
        for _ in range(count):
            record_event(session, EventType.PIPELINE_FAILED, data={"stage": "analyzing"}).ts = at
        session.commit()


def _jobs(
    session_factory: sessionmaker[Session],
    status: JobStatus,
    count: int,
    *,
    lease_expires_at: datetime | None = None,
    prefix: str = "u",
) -> list[str]:
    ids = [f"{prefix}_{status.value}_{n}" for n in range(count)]
    with session_factory() as session:
        for upload_id in ids:
            session.add(Upload(id=upload_id, channel="web"))
            session.flush()
            job = enqueue_upload(session, upload_id)
            job.status = status.value
            job.lease_expires_at = lease_expires_at
        session.commit()
    return ids


def _queue_items(
    session_factory: sessionmaker[Session], *, open_current: int, resolved: int, superseded: int
) -> None:
    """Güncel planda `open_current` açık, `resolved` çözülmüş; eski planda `superseded` öğe."""
    with session_factory() as session:
        upload = Upload(id="u_kuyruk", channel="web")
        session.add(upload)
        session.flush()
        old, new = (
            Plan(upload_id=upload.id, version=v, json={}, plan_hash=f"h{v}") for v in (1, 2)
        )
        session.add_all([old, new])
        session.flush()

        def add(plan: Plan | None, *, done: bool) -> None:
            session.add(
                QueueItem(
                    upload_id=upload.id,
                    plan_id=None if plan is None else plan.id,
                    plan_item_id="i1",
                    kind=QueueKind.UNRESOLVED.value,
                    reason="Sentetik gerekçe",
                    resolved_at=utcnow() if done else None,
                    resolved_by="ik" if done else None,
                )
            )

        for _ in range(open_current):
            add(new, done=False)
        for _ in range(resolved):
            add(new, done=True)
        for _ in range(superseded):
            add(old, done=False)
        add(None, done=False)  # planı olmayan kayıt güncel plana ait sayılmaz
        session.commit()


THRESHOLDS = AlertThresholds(
    error_count=3, disk_used_percent=85.0, job_queue_length=4, review_queue_length=5
)


# --- eşikler ve mesajlar ---------------------------------------------------------------------


def test_thresholds_default_to_the_documented_settings() -> None:
    assert AlertThresholds.from_settings(Settings(_env_file=None, database_url="sqlite://")) == (
        AlertThresholds()
    )


def test_thresholds_follow_the_settings() -> None:
    settings = Settings(
        _env_file=None,
        database_url="sqlite://",
        alert_error_count=7,
        alert_error_window_minutes=15,
        alert_disk_used_percent=70,
        alert_job_queue_length=9,
        alert_review_queue_length=11,
        alert_check_seconds=5,
        alert_repeat_minutes=30,
    )

    assert AlertThresholds.from_settings(settings) == AlertThresholds(
        error_count=7,
        error_window=timedelta(minutes=15),
        disk_used_percent=70.0,
        job_queue_length=9,
        review_queue_length=11,
        interval=timedelta(seconds=5),
        repeat=timedelta(minutes=30),
    )


def test_a_reading_trips_at_the_limit_and_recovers_only_below_the_clear_ratio() -> None:
    def reading(value: float) -> Reading:
        return Reading(AlertKind.JOB_QUEUE, value, 10, "metin")

    assert [reading(v).tripped for v in (9, 10, 11)] == [False, True, True]
    assert [reading(v).recovered for v in (8, 9, 9.5, 10)] == [True, False, False, False]
    assert CLEAR_RATIO == 0.9


def test_every_kind_has_a_label_and_advice() -> None:
    assert set(LABELS) == set(ADVICE) == set(AlertKind)


def test_notice_messages_say_what_happened_and_what_to_do() -> None:
    reading = Reading(AlertKind.REVIEW_QUEUE, 7, 5, "7 öğe karar bekliyor (eşik 5)")

    assert Notice(NoticeState.RAISED, reading).message == (
        "Uyarı — kuyruk: 7 öğe karar bekliyor (eşik 5). Panelde kuyruğa bakın."
    )
    assert Notice(NoticeState.REMINDER, reading).message == (
        "Uyarı sürüyor — kuyruk: 7 öğe karar bekliyor (eşik 5). Panelde kuyruğa bakın."
    )
    assert Notice(NoticeState.CLEARED, reading).message == (
        "Uyarı giderildi — kuyruk: 7 öğe karar bekliyor (eşik 5)."
    )


# --- hata ------------------------------------------------------------------------------------


def test_errors_count_the_failed_batches_inside_the_window_only(
    session_factory: sessionmaker[Session],
) -> None:
    _failures(session_factory, 2, at=NOW - timedelta(minutes=59))
    _failures(session_factory, 5, at=NOW - timedelta(minutes=61))  # pencere dışı
    with session_factory() as session:
        record_event(session, EventType.PAGE_ANALYSIS_FAILED)  # parti hatası değil
        record_event(session, EventType.PLAN_CREATED)
        session.commit()
        readings = measure(session, Path("."), THRESHOLDS, now=NOW)

    errors = _reading(AlertKind.ERRORS, readings)
    assert errors.value == 2
    assert errors.text == "son 60 dakikada 2 parti işlenemedi (eşik 3)"
    assert not errors.tripped


def test_errors_trip_at_the_configured_count_and_window(
    session_factory: sessionmaker[Session],
) -> None:
    _failures(session_factory, 3, at=NOW - timedelta(minutes=10))
    thresholds = AlertThresholds(error_count=3, error_window=timedelta(minutes=15))
    with session_factory() as session:
        errors = _reading(AlertKind.ERRORS, measure(session, Path("."), thresholds, now=NOW))

    assert errors.tripped
    assert errors.text == "son 15 dakikada 3 parti işlenemedi (eşik 3)"


# --- disk ------------------------------------------------------------------------------------


def test_disk_reports_the_percentage_used_like_df(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    _disk(monkeypatch, used=87 * GIB, free=13 * GIB)
    with session_factory() as session:
        disk = _reading(AlertKind.DISK, measure(session, Path("."), THRESHOLDS, now=NOW))

    assert disk.value == pytest.approx(87.0)
    assert disk.tripped
    assert disk.text == "veri diski %87 dolu, 13,0 GB boş (eşik %85)"


def test_disk_below_the_limit_does_not_trip(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    _disk(monkeypatch, used=84 * GIB, free=16 * GIB)
    with session_factory() as session:
        disk = _reading(AlertKind.DISK, measure(session, Path("."), THRESHOLDS, now=NOW))

    assert not disk.tripped


def test_disk_of_a_data_directory_that_does_not_exist_yet_is_the_nearest_existing_ancestor(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    missing = tmp_path / "henuz" / "acilmamis" / "veri"
    with session_factory() as session:
        disk = _reading(AlertKind.DISK, measure(session, missing, THRESHOLDS, now=NOW))

    assert 0 <= disk.value <= 100


def test_a_disk_that_cannot_be_measured_is_logged_by_type_and_skipped(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(_path: Path) -> Any:
        raise PermissionError(SECRET)

    monkeypatch.setattr(monitor.shutil, "disk_usage", broken)
    with session_factory() as session, caplog.at_level(logging.WARNING, logger=monitor.__name__):
        readings = measure(session, Path("."), THRESHOLDS, now=NOW)

    assert {reading.kind for reading in readings} == {
        AlertKind.ERRORS,
        AlertKind.JOB_QUEUE,
        AlertKind.REVIEW_QUEUE,
    }
    assert "Disk doluluğu ölçülemedi (PermissionError)" in caplog.text
    assert "Ornekova" not in caplog.text


def test_a_disk_reporting_no_capacity_is_skipped(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    _disk(monkeypatch, used=0, free=0)
    with session_factory() as session:
        readings = measure(session, Path("."), THRESHOLDS, now=NOW)

    assert AlertKind.DISK not in {reading.kind for reading in readings}


# --- işçi kuyruğu ----------------------------------------------------------------------------


def test_the_job_queue_counts_waiting_jobs_and_jobs_whose_worker_stopped(
    session_factory: sessionmaker[Session],
) -> None:
    _jobs(session_factory, JobStatus.QUEUED, 2)
    _jobs(session_factory, JobStatus.RUNNING, 1, lease_expires_at=NOW - timedelta(seconds=1))
    _jobs(
        session_factory,
        JobStatus.RUNNING,
        3,
        lease_expires_at=NOW + timedelta(minutes=1),
        prefix="c",
    )
    _jobs(session_factory, JobStatus.FINISHED, 4)
    _jobs(session_factory, JobStatus.ABANDONED, 5)
    with session_factory() as session:
        jobs = _reading(AlertKind.JOB_QUEUE, measure(session, Path("."), THRESHOLDS, now=NOW))

    assert jobs.value == 3  # 2 bekleyen + kirası dolmuş 1; canlı işleyicideki 3 iş sayılmaz
    assert jobs.text == "3 parti işlenmeyi bekliyor (eşik 4)"


# --- karar bekleyen kuyruk -------------------------------------------------------------------


def test_the_review_queue_counts_open_items_of_the_current_plan_like_the_panel(
    session_factory: sessionmaker[Session],
) -> None:
    _queue_items(session_factory, open_current=6, resolved=2, superseded=3)
    with session_factory() as session:
        queue = _reading(AlertKind.REVIEW_QUEUE, measure(session, Path("."), THRESHOLDS, now=NOW))
        panel = sum(_counts(session, QueueState.OPEN).values())

    assert queue.value == panel == 6
    assert queue.tripped
    assert queue.text == "6 öğe karar bekliyor (eşik 5)"


def test_a_quiet_system_reads_zero_and_trips_nothing(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    _disk(monkeypatch, used=10 * GIB, free=90 * GIB)
    with session_factory() as session:
        readings = measure(session, Path("."), THRESHOLDS, now=NOW)

    assert _values(readings) == {
        AlertKind.ERRORS: 0,
        AlertKind.DISK: pytest.approx(10.0),
        AlertKind.JOB_QUEUE: 0,
        AlertKind.REVIEW_QUEUE: 0,
    }
    assert not any(reading.tripped for reading in readings)


# --- izleyici: çıkma, hatırlatma, giderme ----------------------------------------------------


def _jobs_reading(value: float) -> Reading:
    return Reading(AlertKind.JOB_QUEUE, value, 10, f"{value:g} parti")


def _states(notices: list[Notice]) -> list[NoticeState]:
    return [notice.state for notice in notices]


def test_an_alert_is_raised_once_when_the_value_reaches_the_limit() -> None:
    tracker = AlertTracker(timedelta(hours=6))

    assert tracker.observe([_jobs_reading(9)], NOW) == []
    assert _states(tracker.observe([_jobs_reading(10)], NOW + timedelta(minutes=1))) == [
        NoticeState.RAISED
    ]
    assert tracker.observe([_jobs_reading(15)], NOW + timedelta(minutes=2)) == []
    assert tracker.active == {AlertKind.JOB_QUEUE}


def test_a_lasting_alert_is_reminded_every_repeat_interval() -> None:
    tracker = AlertTracker(timedelta(hours=6))
    tracker.observe([_jobs_reading(12)], NOW)

    assert tracker.observe([_jobs_reading(12)], NOW + timedelta(hours=5, minutes=59)) == []
    assert _states(tracker.observe([_jobs_reading(12)], NOW + timedelta(hours=6))) == [
        NoticeState.REMINDER
    ]
    # Hatırlatma sayacı en son bildirimden başlar.
    assert tracker.observe([_jobs_reading(12)], NOW + timedelta(hours=11)) == []
    assert _states(tracker.observe([_jobs_reading(12)], NOW + timedelta(hours=12))) == [
        NoticeState.REMINDER
    ]


def test_an_alert_is_cleared_only_below_the_clear_ratio_and_can_be_raised_again() -> None:
    tracker = AlertTracker(timedelta(hours=6))
    tracker.observe([_jobs_reading(10)], NOW)

    # Eşiğin hemen altındaki dalgalanma (9 ≥ 10 × 0,9) uyarıyı ne giderir ne yeniden çıkarır.
    assert tracker.observe([_jobs_reading(9)], NOW + timedelta(minutes=1)) == []
    assert tracker.observe([_jobs_reading(10)], NOW + timedelta(minutes=2)) == []
    (cleared,) = tracker.observe([_jobs_reading(8)], NOW + timedelta(minutes=3))
    assert cleared.state is NoticeState.CLEARED
    assert cleared.reading.value == 8
    assert tracker.active == frozenset()
    assert tracker.observe([_jobs_reading(8)], NOW + timedelta(minutes=4)) == []
    assert _states(tracker.observe([_jobs_reading(10)], NOW + timedelta(minutes=5))) == [
        NoticeState.RAISED
    ]


def test_each_kind_is_tracked_on_its_own() -> None:
    tracker = AlertTracker(timedelta(hours=6))
    errors = Reading(AlertKind.ERRORS, 3, 3, "hata")
    disk = Reading(AlertKind.DISK, 50, 85, "disk")

    notices = tracker.observe([errors, disk], NOW)

    assert [(n.reading.kind, n.state) for n in notices] == [(AlertKind.ERRORS, NoticeState.RAISED)]
    assert tracker.active == {AlertKind.ERRORS}


# --- izleyici: ölçüm sıklığı, log, uçtan uca -------------------------------------------------


def _watch(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    thresholds: AlertThresholds = THRESHOLDS,
) -> AlertWatch:
    return AlertWatch(session_factory, tmp_path, thresholds)


def test_each_of_the_three_conditions_produces_its_alert(
    session_factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """13.6.1 kabul: hata, disk doluluğu ve kuyruk uzunluğu için uyarı üretilir."""
    _disk(monkeypatch, used=95 * GIB, free=5 * GIB)
    _failures(session_factory, 3, at=utcnow())
    _jobs(session_factory, JobStatus.QUEUED, 4)
    watch = _watch(session_factory, tmp_path)

    notices = watch.check()

    assert {notice.reading.kind: notice.state for notice in notices} == {
        AlertKind.ERRORS: NoticeState.RAISED,
        AlertKind.DISK: NoticeState.RAISED,
        AlertKind.JOB_QUEUE: NoticeState.RAISED,
    }
    assert {notice.message for notice in notices} == {
        "Uyarı — hata: son 60 dakikada 3 parti işlenemedi (eşik 3). "
        "Panelde başarısız partilere bakın.",
        "Uyarı — disk: veri diski %95 dolu, 5,0 GB boş (eşik %85). Yer açın ya da diski büyütün.",
        "Uyarı — iş kuyruğu: 4 parti işlenmeyi bekliyor (eşik 4). "
        "İşleyicinin ve yapay zekâ sağlayıcısının çalıştığını kontrol edin.",
    }
    assert watch.active == {AlertKind.ERRORS, AlertKind.DISK, AlertKind.JOB_QUEUE}


def test_the_review_queue_alerts_too(
    session_factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _disk(monkeypatch, used=1 * GIB, free=99 * GIB)
    _queue_items(session_factory, open_current=5, resolved=0, superseded=0)

    (notice,) = _watch(session_factory, tmp_path).check()

    assert notice.reading.kind is AlertKind.REVIEW_QUEUE
    assert notice.message == "Uyarı — kuyruk: 5 öğe karar bekliyor (eşik 5). Panelde kuyruğa bakın."


def test_a_healthy_system_produces_no_alert(
    session_factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _disk(monkeypatch, used=10 * GIB, free=90 * GIB)
    _failures(session_factory, 2, at=utcnow())
    _jobs(session_factory, JobStatus.QUEUED, 3)

    assert _watch(session_factory, tmp_path).check() == []


def test_the_watch_measures_only_when_the_interval_has_passed(
    session_factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _disk(monkeypatch, used=10 * GIB, free=90 * GIB)
    thresholds = AlertThresholds(job_queue_length=2, interval=timedelta(seconds=60))
    watch = _watch(session_factory, tmp_path, thresholds)
    assert watch.check(NOW) == []
    _jobs(session_factory, JobStatus.QUEUED, 2)

    assert watch.check(NOW + timedelta(seconds=59)) == []  # ölçüm sırası gelmedi
    (notice,) = watch.check(NOW + timedelta(seconds=60))
    assert notice.reading.kind is AlertKind.JOB_QUEUE


def test_the_watch_logs_raised_alerts_as_warnings_and_cleared_ones_as_info(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _disk(monkeypatch, used=10 * GIB, free=90 * GIB)
    thresholds = AlertThresholds(job_queue_length=2, interval=timedelta(0))
    watch = _watch(session_factory, tmp_path, thresholds)
    ids = _jobs(session_factory, JobStatus.QUEUED, 2)

    with caplog.at_level(logging.INFO, logger=monitor.__name__):
        watch.check(NOW)
        with session_factory() as session:
            for upload_id in ids:
                job = session.query(UploadJob).filter_by(upload_id=upload_id).one()
                job.status = JobStatus.FINISHED.value
            session.commit()
        watch.check(NOW + timedelta(minutes=1))

    warning, info = caplog.records
    assert (warning.levelno, warning.getMessage()) == (
        logging.WARNING,
        "Uyarı — iş kuyruğu: 2 parti işlenmeyi bekliyor (eşik 2). "
        "İşleyicinin ve yapay zekâ sağlayıcısının çalıştığını kontrol edin.",
    )
    assert (info.levelno, info.getMessage()) == (
        logging.INFO,
        "Uyarı giderildi — iş kuyruğu: 0 parti işlenmeyi bekliyor (eşik 2).",
    )


def test_alert_texts_carry_only_counts_never_personal_values(
    session_factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _disk(monkeypatch, used=95 * GIB, free=5 * GIB)
    with session_factory() as session:
        record_event(
            session,
            EventType.PIPELINE_FAILED,
            message=SECRET,
            data={"stage": "analyzing", "error": SECRET},
        )
        session.commit()
    thresholds = AlertThresholds(error_count=1)

    notices = _watch(session_factory, tmp_path, thresholds).check()

    assert notices
    for notice in notices:
        assert "Ornekova" not in notice.message
        assert "0000001" not in notice.message


def test_a_failing_measurement_reaches_the_caller(
    tmp_path: Path, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError(SECRET)

    monkeypatch.setattr(monitor, "measure", broken)

    with pytest.raises(RuntimeError):
        _watch(session_factory, tmp_path).check()


def test_the_watch_can_be_built_from_settings(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    settings = Settings(
        _env_file=None,
        database_url="sqlite://",
        data_dir=tmp_path / "ayar",
        alert_job_queue_length=1,
        alert_check_seconds=0.001,
    )
    _jobs(session_factory, JobStatus.QUEUED, 1)

    watch = AlertWatch.from_settings(session_factory, settings)
    (notice,) = [n for n in watch.check() if n.reading.kind is AlertKind.JOB_QUEUE]

    assert notice.state is NoticeState.RAISED
    assert AlertWatch.from_settings(session_factory, settings, tmp_path)._data_dir == tmp_path


# --- panel sürecinin işleyicisi --------------------------------------------------------------


def test_the_worker_loop_logs_alerts_between_scans(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(Worker, "run_once", lambda self: False)  # kuyruğu tüketmesin
    _jobs(session_factory, JobStatus.QUEUED, 2)
    settings = Settings(
        _env_file=None,
        database_url="sqlite://",
        worker_poll_seconds=0.01,
        alert_job_queue_length=2,
        alert_check_seconds=0.01,
    )
    worker = Worker(session_factory, layout, settings=settings, provider=None)  # type: ignore[arg-type]

    with caplog.at_level(logging.WARNING, logger=monitor.__name__):
        worker.start()
        try:
            _wait_for(lambda: "iş kuyruğu: 2 parti işlenmeyi bekliyor" in caplog.text)
        finally:
            worker.stop()


def test_a_failing_measurement_does_not_stop_the_worker_loop_and_logs_only_its_type(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls = 0
    second_call = threading.Event()

    def flaky(self: AlertWatch, now: datetime | None = None) -> list[Notice]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError(SECRET)
        second_call.set()
        return []

    monkeypatch.setattr(Worker, "run_once", lambda self: False)
    monkeypatch.setattr(AlertWatch, "check", flaky)
    worker = Worker(
        session_factory,
        layout,
        settings=Settings(_env_file=None, database_url="sqlite://", worker_poll_seconds=0.01),
        provider=None,  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.ERROR):
        worker.start()
        try:
            assert second_call.wait(10)
        finally:
            worker.stop()

    assert "İzleme ölçümü başarısız (RuntimeError)" in caplog.text
    assert "Ornekova" not in caplog.text


def _wait_for(condition: Any, timeout: float = 10.0) -> None:
    done = threading.Event()
    deadline = timeout
    while deadline > 0 and not condition():
        done.wait(0.02)
        deadline -= 0.02
    assert condition(), "koşul zamanında gerçekleşmedi"
