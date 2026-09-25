"""13.5.2 — web uploads enqueue work; only the separate worker consumes it."""

from __future__ import annotations

import re
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai import PROVIDER_FACTORIES
from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings, get_settings
from app.db.models import JobStatus, Upload, UploadJob, UploadStatus
from app.db.session import get_session_factory
from app.storage import DataLayout
from app.worker import Worker
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
)


def test_web_request_leaves_job_for_the_separate_worker(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path,
    monkeypatch,
) -> None:
    settings = Settings(_env_file=None, database_url="sqlite://", ai_provider="workertest")
    provider = recorded_provider(
        tmp_path / "worker-provider",
        [
            passport_page(
                PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1)
            )
        ],
    )
    monkeypatch.setitem(PROVIDER_FACTORIES, "workertest", lambda _settings: provider)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()

    response = client.post(
        "/upload",
        files=[
            (
                "files",
                (
                    "pasaport.pdf",
                    make_document_pdf_bytes(
                        [
                            passport_page(
                                PERSON_ORNEKOVA,
                                document_number="00 0000001",
                                expiry_date=date(2030, 1, 1),
                            )
                        ]
                    ),
                    "application/pdf",
                ),
            )
        ],
    )
    assert response.status_code == 201
    assert 'hx-trigger="every 2s"' in response.text
    match = re.search(r"Parti (u_\w+)", response.text)
    assert match is not None
    upload_id = match.group(1)

    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        job = session.scalars(select(UploadJob).where(UploadJob.upload_id == upload_id)).one()
        assert upload.status == UploadStatus.RECEIVED
        assert (job.status, job.attempts, job.claimed_by) == (JobStatus.QUEUED, 0, None)

    worker = Worker(session_factory, layout, settings=settings, provider=provider)
    assert worker.run_once() is True

    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        job = session.scalars(select(UploadJob).where(UploadJob.upload_id == upload_id)).one()
        assert upload.status == UploadStatus.DONE
        assert (job.status, job.attempts) == (JobStatus.FINISHED, 1)
    progress = client.get(f"/upload/{upload_id}/progress")
    assert "Tamamlandı" in progress.text
    assert 'hx-trigger="every 2s"' not in progress.text
