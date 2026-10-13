"""10.10.6 — gerekçe kayıtta İngilizce, panelde kullanıcının dilinde (PLAN.md §D121).

Gerçek boru hattı (kayıtlı yanıt sağlayıcısı; canlı yapay zekâ çağrısı yok): katalogda olmayan
belge Unknown'a düşer. Plan öğesinin gerekçesi, kuyruk gerekçesi, olay mesajı ve `reason.json`
İngilizcedir; parti detayı ve kuyruk öğesi aynı gerekçeyi `en`, `tr`, `sr` isteğinde o dilde
gösterir. Yapay zekânın serbest notu İngilizcedir ve çevrilmez. Bu görevden önce yazılmış Türkçe
gerekçe kırılmadan, olduğu gibi görünür.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings, get_settings
from app.db.models import Event, Page, QueueItem, Upload
from app.events import EventType
from app.pipeline.orchestrate import current_plan, process_upload
from app.pipeline.plan import read_plan
from app.storage import DataLayout
from app.web.auth import SESSION_COOKIE
from tests.fixtures.gen import (
    PERSON_PRUEBA,
    make_document_pdf_bytes,
    recorded_provider,
    unknown_document_page,
)

SETTINGS = Settings(_env_file=None, database_url="sqlite://")
NOTES = "No Peruvian diploma type in the catalog; the document was proposed as a candidate type."
SUBJECT = {
    "en": "Unknown document type (04.6.1): the type of this candidate (file 1, page 1) is not in "
    'the catalog; proposed candidate type: "Peruvian Diploma".',
    "tr": "Bilinmeyen belge türü (04.6.1): bu adayın (dosya 1, sayfa 1) türü katalogda yok; "
    'önerilen aday tür: "Peruvian Diploma".',
    "sr": "Nepoznat tip dokumenta (04.6.1): tip ovog kandidata (datoteka 1, stranica 1) nije u "
    'katalogu; predloženi kandidat tip: "Peruvian Diploma".',
}
LEGACY = "Okunamayan alanlar: document_number"


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, "oturum-bir")


def _processed(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> str:
    pages = [
        unknown_document_page(
            PERSON_PRUEBA,
            candidate_type_name="Peruvian Diploma",
            title="DIPLOMA",
            document_number="DIP-0000077",
            notes=NOTES,
        )
    ]
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()
    response = client.post(
        "/api/uploads",
        files=[("files", ("diploma.pdf", make_document_pdf_bytes(pages), "application/pdf"))],
    )
    assert response.status_code == 201, response.text
    upload_id: str = response.json()["upload_id"]
    provider = recorded_provider(tmp_path / "kayit", pages)
    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        process_upload(session, layout, upload, settings=SETTINGS, provider=provider)
    return upload_id


def _html(app: FastAPI, client: TestClient, url: str, language: str) -> str:
    """Sayfa `language` dilinde (tercihsiz hesap: panelin açılış dili, 10.10.2); metin kaçışsız."""
    settings = Settings(_env_file=None, database_url="sqlite://", panel_default_language=language)
    app.dependency_overrides[get_settings] = lambda: settings
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert f'<html lang="{"sr-Latn" if language == "sr" else language}">' in response.text
    return html.unescape(" ".join(response.text.split()))


def test_unknown_type_reason_is_english_in_every_record(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)

    with session_factory() as session:
        plan = current_plan(session, session.get_one(Upload, upload_id))
        assert plan is not None
        (item,) = read_plan(plan).items
        (queued,) = session.scalars(select(QueueItem)).all()
        (event,) = session.scalars(
            select(Event).where(Event.type == EventType.QUEUED_UNKNOWN.value)
        ).all()
        (page,) = session.scalars(select(Page)).all()

        assert item.route_reason is not None
        assert item.route_reason.startswith(SUBJECT["en"])
        assert queued.reason == event.message == item.route_reason
        assert page.analysis_json is not None and page.analysis_json["notes"] == NOTES
    reason_file = layout.queue_dir("unknown", upload_id) / "reason.json"
    (entry,) = json.loads(reason_file.read_text(encoding="utf-8"))["items"]
    assert entry["reason"] == item.route_reason


@pytest.mark.parametrize("language", ["en", "tr", "sr"])
def test_batch_detail_and_queue_item_show_the_reason_in_the_users_language(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    language: str,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)
    with session_factory() as session:
        (queued,) = session.scalars(select(QueueItem)).all()
        queue_id = queued.id

    detail = _html(app, client, f"/uploads/{upload_id}", language)
    item = _html(app, client, f"/queues/{queue_id}", language)
    listing = _html(app, client, "/queues?tab=unknown", language)

    for page in (detail, item, listing):
        assert SUBJECT[language] in page
        for other in {"en", "tr", "sr"} - {language}:
            assert SUBJECT[other] not in page


def test_old_turkish_reason_is_shown_unchanged_and_not_machine_translated(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    # Bu görevden önce yazılmış kayıt: kaynağı bilinmeyen düz Türkçe metin. Geriye dönük çeviri
    # yok; metin olduğu gibi ve tarayıcı çevirisine kapalı (`translate="no"`) görünür.
    upload_id = _processed(client, session_factory, layout, tmp_path)
    with session_factory() as session:
        (queued,) = session.scalars(select(QueueItem)).all()
        queued.reason = LEGACY
        queue_id = queued.id
        session.commit()

    for language in ("en", "sr"):
        detail = _html(app, client, f"/uploads/{upload_id}", language)
        item = _html(app, client, f"/queues/{queue_id}", language)
        assert f'<td translate="no">{LEGACY}</td>' in detail
        assert f'<dd class="reason-text" translate="no">{LEGACY}</dd>' in item
