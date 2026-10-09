"""10.3.6, 10.3.7 — iptal ile işleyici: kök neden, işleyici turunda otomatik iptal ve adımın
ortasındaki iptal (PLAN.md §D114 a, c, e).

Kök neden (§D114 a): partiyi yalnız ayrı işleyici işler; işleyici kapalıyken parti `received`'da,
işi `queued`'da sonsuza dek bekler. İşleyici her turda iş almadan önce süresi dolan partileri iptal
eder. Adımın ortasında iptal edilen parti `failed` olmaz, `cancelled` kalır. Veri sentetiktir,
yapay zekâ kayıtlı yanıt sağlayıcısıyla çağrılır (canlı çağrı yok).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import Catalog
from app.config import Settings
from app.db.models import Event, JobStatus, Page, Upload, UploadJob, UploadStatus, utcnow
from app.events import EventType
from app.pipeline import orchestrate
from app.pipeline.cancel import CancelReason, cancel_upload
from app.storage import DataLayout
from app.web.routers.uploads import IncomingFile, store_upload
from app.worker import Claim, Worker, claim_upload, run_claimed_upload
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
USER = "ik-kullanici"


def _batch(session_factory: sessionmaker[Session], layout: DataLayout, *, age: timedelta) -> str:
    with session_factory() as session:
        upload_id = store_upload(
            session,
            layout,
            SETTINGS,
            [IncomingFile("pasaport.pdf", make_document_pdf_bytes([ORNEKOVA]), "application/pdf")],
            channel="web",
        )
    with session_factory() as session:
        created = utcnow() - age
        session.execute(update(Upload).where(Upload.id == upload_id).values(created_at=created))
        session.commit()
    return upload_id


def _claim(session_factory: sessionmaker[Session], upload_id: str) -> Claim:
    with session_factory() as session:
        claim = claim_upload(session, upload_id, token="isleyici-a", lease_seconds=LEASE)
        session.commit()
    assert claim is not None
    return claim


def _cancel(session_factory: sessionmaker[Session], upload_id: str) -> None:
    with session_factory() as session:
        cancel_upload(
            session,
            session.get_one(Upload, upload_id),
            actor=USER,
            reason=CancelReason.MANUAL,
        )
        session.commit()


def _state(session_factory: sessionmaker[Session], upload_id: str) -> tuple[str, str]:
    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        job = session.scalars(select(UploadJob).where(UploadJob.upload_id == upload_id)).one()
        return upload.status, job.status


def _event_types(session_factory: sessionmaker[Session]) -> list[str]:
    with session_factory() as session:
        return list(session.scalars(select(Event.type).order_by(Event.id)))


def _worker(
    session_factory: sessionmaker[Session], layout: DataLayout, tmp_path: Path, **settings: Any
) -> tuple[Worker, Any]:
    provider = recorded_provider(tmp_path / "kayit", [ORNEKOVA])
    worker = Worker(
        session_factory, layout, settings=SETTINGS.model_copy(update=settings), provider=provider
    )
    return worker, provider


# --- kök neden ve işleyici turu (§D114 a, e) ----------------------------------------------------


def test_without_a_worker_the_batch_waits_received_with_its_job_queued(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    # Kök neden: HTTP uygulaması işi almaz; işleyici yoksa hiçbir şey partiyi ilerletmez.
    upload_id = _batch(session_factory, layout, age=timedelta(hours=3))

    assert _state(session_factory, upload_id) == (UploadStatus.RECEIVED, JobStatus.QUEUED)


@pytest.mark.usefixtures("catalog")
def test_the_worker_turn_cancels_a_stale_batch_before_taking_work(
    session_factory: sessionmaker[Session], layout: DataLayout, tmp_path: Path
) -> None:
    stale = _batch(session_factory, layout, age=timedelta(minutes=10, seconds=1))
    worker, provider = _worker(session_factory, layout, tmp_path)

    assert worker.run_once() is False  # iptal edilen partinin işi alınmaz; başka iş yok

    assert _state(session_factory, stale) == (UploadStatus.CANCELLED, JobStatus.CANCELLED)
    assert provider.requests == []
    with session_factory() as session:
        event = session.scalars(
            select(Event).where(Event.type == EventType.UPLOAD_CANCELLED.value)
        ).one()
    assert (event.actor, event.data_json["reason"]) == ("system", "timeout")


@pytest.mark.usefixtures("catalog")
def test_the_worker_turn_processes_a_young_batch(
    session_factory: sessionmaker[Session], layout: DataLayout, tmp_path: Path
) -> None:
    young = _batch(session_factory, layout, age=timedelta(minutes=9))
    worker, _provider = _worker(session_factory, layout, tmp_path)

    assert worker.run_once() is True

    assert _state(session_factory, young) == (UploadStatus.DONE, JobStatus.FINISHED)
    assert EventType.UPLOAD_CANCELLED not in _event_types(session_factory)


@pytest.mark.usefixtures("catalog")
def test_the_worker_turn_uses_the_configured_timeout(
    session_factory: sessionmaker[Session], layout: DataLayout, tmp_path: Path
) -> None:
    upload_id = _batch(session_factory, layout, age=timedelta(minutes=2))
    worker, _provider = _worker(session_factory, layout, tmp_path, upload_timeout_seconds=60)

    worker.run_once()

    assert _state(session_factory, upload_id)[0] == UploadStatus.CANCELLED


# --- işleyici adımın ortasındayken iptal (§D114 c) ---------------------------------------------


@pytest.mark.usefixtures("catalog")
def test_a_cancellation_in_the_middle_of_a_step_withdraws_the_worker_and_keeps_it_cancelled(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_id = _batch(session_factory, layout, age=timedelta(minutes=1))
    claim = _claim(session_factory, upload_id)
    real_export = orchestrate.export_catalog

    def export_after_cancel(session: Session) -> Catalog:
        # `analyzing` geçişi commit edildi, analiz adımı başlıyor: İK partiyi iptal eder. Kira
        # dolmadı; işleyici adımı bitirir ama sonucunu commit edemez.
        _cancel(session_factory, upload_id)
        return real_export(session)

    monkeypatch.setattr(orchestrate, "export_catalog", export_after_cancel)
    provider = recorded_provider(tmp_path / "kayit", [ORNEKOVA])

    result = run_claimed_upload(
        session_factory, layout, claim, settings=SETTINGS, provider=provider
    )

    assert result is None
    assert len(provider.requests) == 1  # iptal anlık durdurma değildir: adım sürdü, geri alındı
    assert _state(session_factory, upload_id) == (UploadStatus.CANCELLED, JobStatus.CANCELLED)
    with session_factory() as session:
        assert list(session.scalars(select(Page.analysis_status))) == ["pending"]
    types = _event_types(session_factory)
    assert EventType.PAGE_ANALYZED not in types
    assert EventType.PIPELINE_FAILED not in types
    assert types.count(EventType.UPLOAD_CANCELLED) == 1


@pytest.mark.usefixtures("catalog")
def test_a_step_that_fails_after_the_cancellation_does_not_mark_the_batch_failed(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_id = _batch(session_factory, layout, age=timedelta(minutes=1))
    claim = _claim(session_factory, upload_id)

    def cancel_then_fail(*_args: Any, **_kwargs: Any) -> None:
        _cancel(session_factory, upload_id)
        raise RuntimeError("planlama durdu")

    monkeypatch.setattr(orchestrate, "create_plan", cancel_then_fail)

    result = run_claimed_upload(
        session_factory,
        layout,
        claim,
        settings=SETTINGS,
        provider=recorded_provider(tmp_path / "kayit", [ORNEKOVA]),
    )

    assert result is None
    assert _state(session_factory, upload_id) == (UploadStatus.CANCELLED, JobStatus.CANCELLED)
    assert EventType.PIPELINE_FAILED not in _event_types(session_factory)


def test_a_batch_cancelled_after_it_was_claimed_is_not_processed(
    session_factory: sessionmaker[Session], layout: DataLayout, tmp_path: Path
) -> None:
    upload_id = _batch(session_factory, layout, age=timedelta(minutes=1))
    claim = _claim(session_factory, upload_id)
    _cancel(session_factory, upload_id)
    provider = recorded_provider(tmp_path / "kayit", [ORNEKOVA])

    result = run_claimed_upload(
        session_factory, layout, claim, settings=SETTINGS, provider=provider
    )

    assert result is None
    assert provider.requests == []
    assert _state(session_factory, upload_id) == (UploadStatus.CANCELLED, JobStatus.CANCELLED)
