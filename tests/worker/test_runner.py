"""13.3.1 — işleyici: işi yürütme, iş devrinde eski işleyicinin susması, kalp atışı, kuyruk döngüsü
ve panel açılışında başlama (`app.worker.runner`, `app.main`).

Yapay zekâ canlı çağrılmaz: sağlayıcı kayıtlı yanıtlardan kurulur, belgeler sentetiktir.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.ai import PROVIDER_FACTORIES
from app.catalog import Catalog
from app.config import Settings, load_settings
from app.db.models import (
    Event,
    JobStatus,
    Page,
    Upload,
    UploadJob,
    UploadStatus,
    utcnow,
)
from app.events import EventType
from app.main import create_app
from app.pipeline import orchestrate
from app.storage import DataLayout
from app.web.routers.uploads import IncomingFile, store_upload
from app.worker import (
    Claim,
    Worker,
    claim_and_run,
    claim_upload,
    enqueue_upload,
    lease_checkpoint,
    run_claimed_upload,
    start_worker,
)
from app.worker import runner as worker_runner
from app.worker.runner import _Heartbeat
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
)

LEASE = 60
SETTINGS = Settings(_env_file=None, database_url="sqlite://", worker_lease_seconds=LEASE)
ORNEKOVA = passport_page(
    PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1)
)
SECRET = "Ekaterina Ornekova 00 0000001"


def _batch(session_factory: sessionmaker[Session], layout: DataLayout) -> str:
    with session_factory() as session:
        return store_upload(
            session,
            layout,
            SETTINGS,
            [IncomingFile("pasaport.pdf", make_document_pdf_bytes([ORNEKOVA]), "application/pdf")],
            channel="web",
        )


def _claim(session_factory: sessionmaker[Session], upload_id: str, token: str = "a") -> Claim:
    with session_factory() as session:
        claim = claim_upload(session, upload_id, token=token, lease_seconds=LEASE)
        session.commit()
    assert claim is not None
    return claim


def _job(session_factory: sessionmaker[Session], upload_id: str) -> UploadJob:
    with session_factory() as session:
        return session.scalars(select(UploadJob).where(UploadJob.upload_id == upload_id)).one()


def _take_over(session_factory: sessionmaker[Session], upload_id: str, token: str = "b") -> None:
    """Kirası dolduğunda başka bir işleyicinin işi alması."""
    with session_factory() as session:
        session.execute(
            update(UploadJob).where(UploadJob.upload_id == upload_id).values(claimed_by=token)
        )
        session.commit()


def _event_types(session_factory: sessionmaker[Session]) -> list[str]:
    with session_factory() as session:
        return list(session.scalars(select(Event.type).order_by(Event.id)))


def _wait_until(condition: Callable[[], bool], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "koşul zamanında gerçekleşmedi"
        time.sleep(0.02)


# --- işi yürütme --------------------------------------------------------------------------


@pytest.mark.usefixtures("catalog")
def test_a_claimed_batch_is_processed_and_its_job_finished_in_the_same_commit(
    session_factory: sessionmaker[Session], layout: DataLayout, tmp_path: Path
) -> None:
    upload_id = _batch(session_factory, layout)
    provider = recorded_provider(tmp_path / "kayit", [ORNEKOVA])

    result = claim_and_run(session_factory, layout, upload_id, settings=SETTINGS, provider=provider)

    assert result is not None and result.status == UploadStatus.DONE
    job = _job(session_factory, upload_id)
    assert (job.status, job.attempts, job.lease_expires_at) == (JobStatus.FINISHED, 1, None)
    assert job.finished_at is not None


def test_the_checkpoint_renews_on_every_transition_and_finishes_on_the_last(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(Upload(id="u_20260919_001", channel="web"))
        session.flush()
        enqueue_upload(session, "u_20260919_001")
        claim = claim_upload(
            session,
            "u_20260919_001",
            token="a",
            lease_seconds=LEASE,
            now=utcnow() - timedelta(hours=1),
        )
        assert claim is not None
        checkpoint = lease_checkpoint(claim, lease_seconds=LEASE)

        checkpoint(session, UploadStatus.ANALYZING)
        job = session.scalars(select(UploadJob)).one()
        assert job.lease_expires_at is not None and job.lease_expires_at > utcnow()
        assert job.status == JobStatus.RUNNING

        checkpoint(session, UploadStatus.PARTIAL)
        assert (job.status, job.lease_expires_at) == (JobStatus.FINISHED, None)


def test_claiming_a_batch_that_is_not_waiting_does_nothing(
    session_factory: sessionmaker[Session], layout: DataLayout, tmp_path: Path
) -> None:
    upload_id = _batch(session_factory, layout)
    _claim(session_factory, upload_id, token="baska")

    assert (
        claim_and_run(session_factory, layout, upload_id, settings=SETTINGS, provider=None)  # type: ignore[arg-type]
        is None
    )
    assert claim_and_run(session_factory, layout, "u_yok", settings=SETTINGS, provider=None) is None  # type: ignore[arg-type]
    assert _job(session_factory, upload_id).claimed_by == "baska"


def test_a_job_whose_batch_already_ended_is_just_finished(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    upload_id = _batch(session_factory, layout)
    claim = _claim(session_factory, upload_id)
    with session_factory() as session:
        session.get_one(Upload, upload_id).status = UploadStatus.DONE.value
        session.commit()

    result = run_claimed_upload(
        session_factory,
        layout,
        claim,
        settings=SETTINGS,
        provider=None,  # type: ignore[arg-type]
    )

    assert result is None
    assert _job(session_factory, upload_id).status == JobStatus.FINISHED
    assert EventType.PIPELINE_FAILED not in _event_types(session_factory)


# --- iş devri: eski işleyici partiye bir daha yazmaz --------------------------------------


@pytest.mark.usefixtures("catalog")
def test_a_worker_whose_job_was_taken_over_before_it_started_writes_nothing(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    upload_id = _batch(session_factory, layout)
    claim = _claim(session_factory, upload_id)
    _take_over(session_factory, upload_id)
    before = _event_types(session_factory)
    provider = recorded_provider(tmp_path / "kayit", [ORNEKOVA])

    with caplog.at_level(logging.WARNING):
        result = run_claimed_upload(
            session_factory, layout, claim, settings=SETTINGS, provider=provider
        )

    assert result is None
    with session_factory() as session:
        assert session.get_one(Upload, upload_id).status == UploadStatus.RECEIVED
    assert _event_types(session_factory) == before
    assert provider.requests == []
    assert _job(session_factory, upload_id).claimed_by == "b"
    assert f"Parti {upload_id} bu işleyicide bırakıldı" in caplog.text


@pytest.mark.usefixtures("catalog")
def test_a_takeover_between_transitions_discards_the_old_worker_s_step(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_id = _batch(session_factory, layout)
    claim = _claim(session_factory, upload_id)
    real_export = orchestrate.export_catalog

    def export_after_takeover(session: Session) -> Catalog:
        # `analyzing` geçişi commit edildi, analiz işlemi henüz açılmadı: iş başkasına geçer.
        _take_over(session_factory, upload_id)
        return real_export(session)

    monkeypatch.setattr(orchestrate, "export_catalog", export_after_takeover)
    provider = recorded_provider(tmp_path / "kayit", [ORNEKOVA])

    result = run_claimed_upload(
        session_factory, layout, claim, settings=SETTINGS, provider=provider
    )

    # Analiz yapıldı ama `planning` geçişi commit edilemedi: işi geri alındı, parti `failed` olmadı.
    assert result is None
    assert len(provider.requests) == 1
    with session_factory() as session:
        assert session.get_one(Upload, upload_id).status == UploadStatus.ANALYZING
        assert list(session.scalars(select(Page.analysis_status))) == ["pending"]
    types = _event_types(session_factory)
    assert EventType.PAGE_ANALYZED not in types
    assert EventType.PIPELINE_FAILED not in types


@pytest.mark.usefixtures("catalog")
def test_a_worker_that_lost_its_job_does_not_record_the_batch_as_failed(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_id = _batch(session_factory, layout)
    claim = _claim(session_factory, upload_id)

    def plan_and_fail(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(SECRET)

    real_mark_failed = orchestrate._mark_failed

    def take_over_then_mark(*args: Any, **kwargs: Any) -> None:
        # Planlama hatası geri alındı; hata kaydı yazılmadan önce iş başkasına geçer.
        _take_over(session_factory, upload_id)
        real_mark_failed(*args, **kwargs)

    monkeypatch.setattr(orchestrate, "create_plan", plan_and_fail)

    monkeypatch.setattr(orchestrate, "_mark_failed", take_over_then_mark)

    result = run_claimed_upload(
        session_factory,
        layout,
        claim,
        settings=SETTINGS,
        provider=recorded_provider(tmp_path / "kayit", [ORNEKOVA]),
    )

    assert result is None
    with session_factory() as session:
        assert session.get_one(Upload, upload_id).status == UploadStatus.PLANNING
    assert EventType.PIPELINE_FAILED not in _event_types(session_factory)


# --- kalp atışı --------------------------------------------------------------------------


def test_the_heartbeat_keeps_renewing_the_lease_while_the_batch_runs(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    upload_id = _batch(session_factory, layout)
    with session_factory() as session:
        claim = claim_upload(
            session, upload_id, token="a", lease_seconds=LEASE, now=utcnow() - timedelta(hours=1)
        )
        session.commit()
    assert claim is not None
    first = _job(session_factory, upload_id).lease_expires_at
    assert first is not None and first < utcnow()
    heartbeat = _Heartbeat(session_factory, claim, lease_seconds=LEASE, interval=0.02)

    heartbeat.start()
    try:
        _wait_until(
            lambda: (
                (lease := _job(session_factory, upload_id).lease_expires_at) is not None
                and lease > utcnow()
            )
        )
    finally:
        heartbeat.stop()


def test_the_heartbeat_stops_by_itself_once_the_job_is_no_longer_its_own(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    upload_id = _batch(session_factory, layout)
    claim = _claim(session_factory, upload_id)
    _take_over(session_factory, upload_id)
    heartbeat = _Heartbeat(session_factory, claim, lease_seconds=LEASE, interval=0.01)

    heartbeat.start()
    heartbeat._thread.join(timeout=10)

    assert not heartbeat._thread.is_alive()
    heartbeat.stop()


def test_a_heartbeat_that_cannot_write_keeps_trying_and_logs_only_the_error_type(
    caplog: pytest.LogCaptureFixture,
) -> None:
    attempts = threading.Event()
    count = 0

    def locked_database() -> Session:
        nonlocal count
        count += 1
        if count >= 3:
            attempts.set()
        raise OperationalError("UPDATE upload_jobs", {}, Exception(SECRET))

    heartbeat = _Heartbeat(
        locked_database,  # type: ignore[arg-type]
        Claim("u_20260919_001", "a"),
        lease_seconds=LEASE,
        interval=0.01,
    )
    with caplog.at_level(logging.WARNING):
        heartbeat.start()
        assert attempts.wait(10)
        heartbeat.stop()

    assert "iş kirası yenilenemedi (OperationalError)" in caplog.text
    assert "Ornekova" not in caplog.text


# --- kuyruk döngüsü --------------------------------------------------------------------------


@pytest.mark.usefixtures("catalog")
def test_the_worker_loop_processes_a_waiting_batch(
    session_factory: sessionmaker[Session], layout: DataLayout, tmp_path: Path
) -> None:
    first = _batch(session_factory, layout)
    worker = Worker(
        session_factory,
        layout,
        settings=SETTINGS.model_copy(update={"worker_poll_seconds": 0.02}),
        provider=recorded_provider(tmp_path / "kayit", [ORNEKOVA]),
    )

    worker.start()
    worker.start()  # ikinci başlatma ikinci döngü açmaz
    try:
        assert worker.running
        _wait_until(lambda: _job(session_factory, first).status == JobStatus.FINISHED)
    finally:
        worker.stop()

    assert not worker.running
    with session_factory() as session:
        assert session.get_one(Upload, first).status == UploadStatus.DONE
    alive = [thread.name for thread in threading.enumerate()]
    assert alive.count("belgeee-worker") == 0


def test_the_worker_loop_survives_a_failing_scan_and_logs_only_its_type(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    scans = 0
    second_scan = threading.Event()

    def failing_then_idle(self: Worker) -> bool:
        nonlocal scans
        scans += 1
        if scans == 1:
            raise RuntimeError(SECRET)
        second_scan.set()
        return False

    monkeypatch.setattr(Worker, "run_once", failing_then_idle)
    worker = Worker(
        session_factory,
        layout,
        settings=SETTINGS.model_copy(update={"worker_poll_seconds": 0.01}),
        provider=None,  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.ERROR):
        worker.start()
        try:
            assert second_scan.wait(10)
        finally:
            worker.stop()

    assert "İşçi kuyruğu taranamadı (RuntimeError)" in caplog.text
    assert "Ornekova" not in caplog.text


def test_the_worker_logs_batches_it_gave_up_on(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    caplog: pytest.LogCaptureFixture,
) -> None:
    upload_id = _batch(session_factory, layout)
    with session_factory() as session:
        session.execute(
            update(UploadJob).values(
                status=JobStatus.RUNNING.value,
                attempts=3,
                claimed_by="olen",
                lease_expires_at=utcnow() - timedelta(seconds=1),
            )
        )
        session.commit()
    worker = Worker(
        session_factory,
        layout,
        settings=SETTINGS.model_copy(update={"worker_max_attempts": 3}),
        provider=None,  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.ERROR):
        assert worker.run_once() is False

    assert f"Parti {upload_id} bırakıldı" in caplog.text
    assert _job(session_factory, upload_id).status == JobStatus.ABANDONED


def test_stopping_the_worker_disposes_its_own_engine(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    disposed: list[bool] = []

    class _Engine:
        def dispose(self) -> None:
            disposed.append(True)

    worker = Worker(
        session_factory,
        layout,
        settings=SETTINGS,
        provider=None,  # type: ignore[arg-type]
        engine=_Engine(),  # type: ignore[arg-type]
    )

    worker.stop()  # hiç başlamamış işleyici de durdurulabilir

    assert disposed == [True]


# --- panel açılışı ------------------------------------------------------------------------


@pytest.fixture
def recorded_app_settings(
    database_url: str, layout: DataLayout, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Settings]:
    provider = recorded_provider(tmp_path / "kayit", [ORNEKOVA])
    monkeypatch.setitem(PROVIDER_FACTORIES, "kayitli", lambda settings: provider)
    yield load_settings(
        _env_file=None,
        database_url=database_url,
        data_dir=layout.root,
        ai_provider="kayitli",
        worker_poll_seconds=0.02,
    )


@pytest.mark.usefixtures("catalog")
def test_the_app_resumes_waiting_batches_as_soon_as_it_starts(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    recorded_app_settings: Settings,
) -> None:
    upload_id = _batch(session_factory, layout)  # uygulama kapalıyken kalmış parti

    with TestClient(create_app(recorded_app_settings)):
        _wait_until(lambda: _job(session_factory, upload_id).status == JobStatus.FINISHED)

    with session_factory() as session:
        assert session.get_one(Upload, upload_id).status == UploadStatus.DONE
    assert "belgeee-worker" not in [thread.name for thread in threading.enumerate()]


def test_without_a_provider_the_app_starts_but_batches_keep_waiting(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    database_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    upload_id = _batch(session_factory, layout)
    settings = load_settings(
        _env_file=None,
        database_url=database_url,
        data_dir=layout.root,
        ai_provider="anthropic",
        anthropic_api_key=None,
    )

    with caplog.at_level(logging.WARNING), TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200

    assert "İşçi kuyruğu başlatılmadı" in caplog.text
    assert "ANTHROPIC_API_KEY" in caplog.text
    assert _job(session_factory, upload_id).status == JobStatus.QUEUED


def test_the_worker_can_be_turned_off(layout: DataLayout, monkeypatch: pytest.MonkeyPatch) -> None:
    def no_provider(settings: Settings) -> Any:
        raise AssertionError("kapalı işleyici sağlayıcı kurmamalı")

    monkeypatch.setattr(worker_runner, "create_provider", no_provider)

    assert start_worker(SETTINGS.model_copy(update={"worker_enabled": False}), layout) is None
