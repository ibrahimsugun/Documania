"""10.3.5 — yoksanan partiyi geri alma: yükleme detayındaki bildirimin yanındaki "Yoksaymayı geri
al" tek adımda partiyi listeye döndürür ve yalnız yoksaymayla kapanan kuyruk öğelerini yeniden açar
(§D61, PLAN.md §C91).

Parti gerçek boru hattından geçer (`process_upload`, kayıtlı yanıt sağlayıcısı): sentetik pasaport
Hazır'a belge üretir, katalogda olmayan diploma Unknown kuyruğuna düşer. Yapay zekâ canlı çağrılmaz.
Partinin güncel planına ayrıca yoksaymadan önce çözülmüş iki öğe eklenir — biri atanmış gibi
(nedeni boş), biri gerekçeyle kapatılmış: geri alma ikisini açmaz.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from html import unescape
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import (
    Event,
    KnownDocumentType,
    Plan,
    QueueItem,
    QueueKind,
    QueueResolution,
    Upload,
    utcnow,
)
from app.events import EventType
from app.pipeline.orchestrate import process_upload
from app.storage import DataLayout
from app.web.auth import SESSION_COOKIE, get_current_user
from app.web.routers.upload_page import (
    DISMISSED_MESSAGE,
    NOT_DISMISSED_MESSAGE,
    UPLOAD_NOT_FOUND,
)
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_PRUEBA,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
    unknown_document_page,
)

SETTINGS = Settings(_env_file=None, database_url="sqlite://")
USER = "test-yonetici"


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    """Yoksaymanın onay belirteci oturum çerezinden türetilir; çerez testte elle konur."""
    client.cookies.set(SESSION_COOKIE, "oturum-bir")


@pytest.fixture
def batch(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> dict[str, object]:
    """Gerçek boru hattından geçmiş parti (Unknown'da bekleyen diploma) ve güncel planına eklenen
    iki çözülmüş öğe: atanmış (`resolution` boş) ve kapatılmış (`closed`)."""
    passport = [
        passport_page(PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1))
    ]
    diploma = [
        unknown_document_page(
            PERSON_PRUEBA,
            candidate_type_name="Peruvian Diploma",
            title="DIPLOMA",
            document_number="DIP-0000077",
        )
    ]
    with session_factory() as session:
        if session.get(KnownDocumentType, "russian_passport") is None:
            import_catalog(session, load_seed_catalog())
            session.commit()
    response = client.post(
        "/api/uploads",
        files=[
            ("files", ("pasaport.pdf", make_document_pdf_bytes(passport), "application/pdf")),
            ("files", ("diploma.pdf", make_document_pdf_bytes(diploma), "application/pdf")),
        ],
    )
    assert response.status_code == 201, response.text
    upload_id: str = response.json()["upload_id"]
    with session_factory() as session:
        process_upload(
            session,
            layout,
            session.get_one(Upload, upload_id),
            settings=SETTINGS,
            provider=recorded_provider(tmp_path / "kayit", passport, diploma),
        )
        (pending,) = session.scalars(select(QueueItem).where(QueueItem.upload_id == upload_id))
        plan_id = session.scalars(select(Plan.id).where(Plan.upload_id == upload_id)).one()
        earlier = utcnow() - timedelta(hours=1)
        assigned, closed = (
            QueueItem(
                upload_id=upload_id,
                plan_id=plan_id,
                plan_item_id=item_id,
                kind=QueueKind.UNRESOLVED.value,
                reason="Sahibi belirsiz",
                payload_json={},
                resolved_at=earlier,
                resolved_by="onceki-kullanici",
                resolution=resolution,
                resolution_reason=reason,
            )
            for item_id, resolution, reason in (
                ("x1", None, None),
                ("x2", QueueResolution.CLOSED.value, "already_exists"),
            )
        )
        session.add_all([assigned, closed])
        session.commit()
        return {
            "upload_id": upload_id,
            "pending": pending.id,
            "assigned": assigned.id,
            "closed": closed.id,
        }


def _dismiss(client: TestClient, upload_id: str) -> None:
    prepared = client.post(f"/uploads/{upload_id}/dismiss/prepare")
    match = re.search(r'name="confirmation" value="([^"]+)"', prepared.text)
    assert match is not None, prepared.text
    response = client.post(f"/uploads/{upload_id}/dismiss", data={"confirmation": match.group(1)})
    assert response.status_code == 200, response.text


def _items(session_factory: sessionmaker[Session]) -> dict[int, tuple[object, ...]]:
    with session_factory() as session:
        return {
            item.id: (item.resolved_at, item.resolved_by, item.resolution, item.plan_id)
            for item in session.scalars(select(QueueItem))
        }


def _events(session_factory: sessionmaker[Session]) -> list[tuple[int, str]]:
    with session_factory() as session:
        return [(row.id, row.type) for row in session.scalars(select(Event).order_by(Event.id))]


def _files(layout: DataLayout) -> dict[str, str]:
    return {
        path.relative_to(layout.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(layout.root.rglob("*"))
        if path.is_file()
    }


def _undismiss_button(html: str) -> str | None:
    match = re.search(r'<button type="button" id="undismiss-button".*?</button>', html, re.S)
    return match.group(0) if match else None


def test_only_a_dismissed_batch_shows_the_restore_button_next_to_its_notice(
    client: TestClient, batch: dict[str, object]
) -> None:
    upload_id = batch["upload_id"]
    assert _undismiss_button(client.get(f"/uploads/{upload_id}").text) is None

    _dismiss(client, str(upload_id))
    page = client.get(f"/uploads/{upload_id}").text

    row = re.search(r'<div class="dismissed-row" id="dismissed-row">.*?</div>', page, re.S)
    assert row is not None
    assert 'id="dismissed-notice"' in row.group(0)
    button = _undismiss_button(row.group(0))
    assert button is not None and "Yoksaymayı geri al" in button
    # Tek adım: hazırlık isteği ya da onay metni yok.
    assert f'hx-post="/uploads/{upload_id}/undismiss"' in button
    assert 'hx-target="#action-result"' in button


def test_restoring_brings_back_the_batch_and_only_the_items_the_dismissal_closed(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    batch: dict[str, object],
) -> None:
    upload_id = str(batch["upload_id"])
    before = _items(session_factory)
    _dismiss(client, upload_id)
    events_before, files_before = _events(session_factory), _files(layout)
    assert f'href="/uploads/{upload_id}"' not in client.get("/uploads").text

    response = client.post(f"/uploads/{upload_id}/undismiss")

    assert response.status_code == 200, response.text
    assert (
        "Yoksayma geri alındı: parti yükleme listesine döndü; 1 kuyruk öğesi yeniden açıldı."
        in response.text
    )
    assert '<div id="dismissed-row" hx-swap-oob="true"></div>' in response.text
    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        assert (upload.dismissed_at, upload.dismissed_by) == (None, None)
        (event,) = session.scalars(select(Event).where(Event.id > events_before[-1][0])).all()
        # Tek adım: onay olayı yok, işlemin olayı kullanıcı adıyla ve yalnız kimliklerle.
        assert event.type == EventType.UPLOAD_RESTORED
        assert event.actor == USER
        assert event.upload_id == upload_id
        assert event.data_json == {"queue_item_ids": [batch["pending"]]}
    # Bekleyen öğe yoksaymadan önceki hâline döndü; atanmış ve kapatılmış öğe çözülmüş kaldı.
    assert _items(session_factory) == before
    assert _files(layout) == files_before
    # Parti listede, öğe kuyrukta; parti yeniden işlenebilir ve yoksayılabilir.
    assert f'href="/uploads/{upload_id}"' in client.get("/uploads").text
    pending = client.get("/queues?tab=unknown").text
    assert f'<td><a href="/queues/{batch["pending"]}">' in pending
    page = client.get(f"/uploads/{upload_id}").text
    assert 'id="dismissed-notice"' not in page and _undismiss_button(page) is None
    assert 'id="rerun-button"' in page and 'id="dismiss-step"' in page
    assert DISMISSED_MESSAGE not in page
    resolved = client.get("/queues?tab=unresolved&state=resolved").text
    assert f'<td><a href="/queues/{batch["closed"]}">' in resolved
    assert f'<td><a href="/queues/{batch["assigned"]}">' in resolved


def test_a_restored_batch_can_be_dismissed_and_restored_again(
    client: TestClient, session_factory: sessionmaker[Session], batch: dict[str, object]
) -> None:
    upload_id = str(batch["upload_id"])
    _dismiss(client, upload_id)
    assert client.post(f"/uploads/{upload_id}/undismiss").status_code == 200

    _dismiss(client, upload_id)
    again = client.post(f"/uploads/{upload_id}/undismiss")

    assert again.status_code == 200
    assert "1 kuyruk öğesi yeniden açıldı" in again.text
    with session_factory() as session:
        assert session.get_one(QueueItem, batch["pending"]).resolved_at is None


def test_a_batch_that_is_not_dismissed_is_409_and_nothing_changes(
    client: TestClient, session_factory: sessionmaker[Session], batch: dict[str, object]
) -> None:
    upload_id = str(batch["upload_id"])
    events, items = _events(session_factory), _items(session_factory)

    response = client.post(f"/uploads/{upload_id}/undismiss")

    assert response.status_code == 409
    assert NOT_DISMISSED_MESSAGE in unescape(response.text)
    assert _events(session_factory) == events
    assert _items(session_factory) == items


def test_restoring_twice_is_409_the_second_time(
    client: TestClient, session_factory: sessionmaker[Session], batch: dict[str, object]
) -> None:
    upload_id = str(batch["upload_id"])
    _dismiss(client, upload_id)
    assert client.post(f"/uploads/{upload_id}/undismiss").status_code == 200
    events = _events(session_factory)

    assert client.post(f"/uploads/{upload_id}/undismiss").status_code == 409
    assert _events(session_factory) == events


def test_an_unknown_batch_is_404(client: TestClient) -> None:
    response = client.post("/uploads/u_yoktur/undismiss")

    assert response.status_code == 404
    assert UPLOAD_NOT_FOUND in response.text


def test_undismiss_needs_a_session(
    app: FastAPI, client: TestClient, batch: dict[str, object]
) -> None:
    app.dependency_overrides.pop(get_current_user)

    response = client.post(f"/uploads/{batch['upload_id']}/undismiss", follow_redirects=False)

    assert response.status_code in (303, 401)
