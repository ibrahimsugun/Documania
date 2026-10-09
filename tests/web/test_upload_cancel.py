"""10.3.6, 10.3.7 — yükleme detayında süren partiyi iki aşamalı onayla iptal etme ve takılan
partinin panel açılırken otomatik iptali (K16, §20.6, §20.6.1; PLAN.md §D114; S16 kalıbı).

Parti `POST /api/uploads` ile açılır ve işleyici çalışmadığı için `received`'da bekler (§D114 a);
işlenmiş parti gerçek boru hattından kayıtlı yanıt sağlayıcısıyla geçer. Otomatik iptalin saati
`get_clock` bağımlılığıyla enjekte edilir — test 10 dakika beklemez. Veri sentetiktir.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import (
    ConfirmationToken,
    Event,
    JobStatus,
    KnownDocumentType,
    Upload,
    UploadJob,
    UploadStatus,
)
from app.events import EventType
from app.pipeline.orchestrate import process_upload
from app.storage import DataLayout
from app.web.auth import SESSION_COOKIE, PanelUser, get_current_user
from app.web.confirm import Operation
from app.web.routers import upload_page
from app.web.routers.upload_page import get_clock
from app.web.routers.uploads import CANCELLED_MESSAGE
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
)
from tests.i18n.residue import assert_no_turkish
from tests.web.conftest import SESSION, SIGNED_IN, issue_token

SETTINGS = Settings(_env_file=None, database_url="sqlite://")
USER = "test-yonetici"
# §20.6 "Partiyi iptal et" — birebir.
FIRST_TEXT = "Bu partiyi iptal etmek üzeresiniz. Emin misiniz?"
SECOND_TEXT = (
    "Partinin işlenmesi durdurulacak; dosyalar ve o ana kadar üretilen belgeler silinmez. İptal "
    "geri alınamaz ama dosyalar yeniden yüklenebilir. Son kararınız mı?"
)
MANUAL_NOTICE = re.compile(
    r"Bu parti \d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC tarihinde test-yonetici tarafından iptal edildi\."
)
TIMEOUT_NOTICE = re.compile(
    r"Bu parti 10 dakikada tamamlanamadığı için \d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC tarihinde "
    r"otomatik iptal edildi\."
)


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    """Onay belirteci oturum çerezinden türetilir; oturum bağımlılığı geçersiz kılındığı için çerez
    testte elle konur."""
    client.cookies.set(SESSION_COOKIE, SESSION)


def _passport_pdf(number: str = "00 0000001") -> bytes:
    page = passport_page(PERSON_ORNEKOVA, document_number=number, expiry_date=date(2030, 1, 1))
    return make_document_pdf_bytes([page])


def _upload(client: TestClient, content: bytes | None = None) -> str:
    response = client.post(
        "/api/uploads",
        files=[("files", ("pasaport.pdf", content or _passport_pdf(), "application/pdf"))],
    )
    assert response.status_code == 201, response.text
    upload_id: str = response.json()["upload_id"]
    return upload_id


@pytest.fixture
def running(client: TestClient) -> str:
    """İşleyici çalışmıyor: parti `received`'da, işi kuyrukta (§D114 a)."""
    return _upload(client)


@pytest.fixture
def processed(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> str:
    with session_factory() as session:
        if session.get(KnownDocumentType, "russian_passport") is None:
            import_catalog(session, load_seed_catalog())
            session.commit()
    content = _passport_pdf("00 0000009")
    upload_id = _upload(client, content)
    with session_factory() as session:
        process_upload(
            session,
            layout,
            session.get_one(Upload, upload_id),
            settings=SETTINGS,
            provider=recorded_provider(
                tmp_path / "kayit",
                [
                    passport_page(
                        PERSON_ORNEKOVA, document_number="00 0000009", expiry_date=date(2030, 1, 1)
                    )
                ],
            ),
        )
        assert session.get_one(Upload, upload_id).status == UploadStatus.DONE
    return upload_id


def _set_clock(app: FastAPI, moment: datetime) -> None:
    app.dependency_overrides[get_clock] = lambda: moment


def _created_at(session_factory: sessionmaker[Session], upload_id: str) -> datetime:
    with session_factory() as session:
        return session.get_one(Upload, upload_id).created_at


def _token(response_text: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', response_text)
    assert match is not None, response_text
    return match.group(1)


def _prepare(client: TestClient, upload_id: str) -> str:
    response = client.post(f"/uploads/{upload_id}/cancel/prepare")
    assert response.status_code == 200, response.text
    return _token(response.text)


def _cancel(client: TestClient, upload_id: str) -> None:
    response = client.post(
        f"/uploads/{upload_id}/cancel", data={"confirmation": _prepare(client, upload_id)}
    )
    assert response.status_code == 200, response.text


def _events(session_factory: sessionmaker[Session]) -> list[Event]:
    with session_factory() as session:
        return list(session.scalars(select(Event).order_by(Event.id)))


def _state(session_factory: sessionmaker[Session], upload_id: str) -> tuple[str, str]:
    with session_factory() as session:
        job = session.scalars(select(UploadJob).where(UploadJob.upload_id == upload_id)).one()
        return session.get_one(Upload, upload_id).status, job.status


def _files(layout: DataLayout) -> dict[str, str]:
    return {
        path.relative_to(layout.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(layout.root.rglob("*"))
        if path.is_file()
    }


def _cancel_step(html: str) -> str | None:
    match = re.search(
        r'<details class="reanalyze dismiss" id="cancel-step">(.*?)</details>', html, re.S
    )
    return match.group(1) if match else None


# --- düğme: yalnız süren partide (10.3.6) ---------------------------------------------------------


def test_a_running_batch_offers_cancel_with_the_first_text_while_rerun_stays_closed(
    client: TestClient, running: str
) -> None:
    page = client.get(f"/uploads/{running}")

    step = _cancel_step(page.text)
    assert step is not None
    assert "Partiyi iptal et" in step
    assert FIRST_TEXT in step
    assert f'hx-post="/uploads/{running}/cancel/prepare"' in step
    assert upload_page.BUSY_MESSAGE in page.text
    assert 'id="rerun-button"' not in page.text
    assert 'id="reanalyze-step"' not in page.text


def test_a_final_batch_offers_no_cancel_and_refuses_it_without_using_the_token(
    client: TestClient, session_factory: sessionmaker[Session], processed: str
) -> None:
    token = issue_token(session_factory, Operation.CANCEL_UPLOAD, processed)
    before = [event.id for event in _events(session_factory)]

    page = client.get(f"/uploads/{processed}")
    prepared = client.post(f"/uploads/{processed}/cancel/prepare")
    cancelled = client.post(f"/uploads/{processed}/cancel", data={"confirmation": token})

    assert _cancel_step(page.text) is None
    assert prepared.status_code == cancelled.status_code == 409
    assert upload_page.NOT_CANCELLABLE_MESSAGE in cancelled.text
    assert [event.id for event in _events(session_factory)] == before
    with session_factory() as session:
        assert session.get_one(Upload, processed).status == UploadStatus.DONE
        row = session.scalars(select(ConfirmationToken)).one()
        assert row.consumed_at is None


def test_an_unknown_batch_is_404(client: TestClient) -> None:
    assert client.post("/uploads/u_yok/cancel/prepare").status_code == 404
    assert client.post("/uploads/u_yok/cancel", data={"confirmation": "x"}).status_code == 404


# --- iki aşamalı onay (K16, §20.6.1; S16) ---------------------------------------------------------


def test_prepare_gives_the_second_text_and_changes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], running: str
) -> None:
    before = [event.id for event in _events(session_factory)]

    response = client.post(f"/uploads/{running}/cancel/prepare")

    assert response.status_code == 200
    assert SECOND_TEXT in response.text
    assert f'hx-post="/uploads/{running}/cancel"' in response.text
    assert [event.id for event in _events(session_factory)] == before
    assert _state(session_factory, running) == (UploadStatus.RECEIVED, JobStatus.QUEUED)


def test_one_confirmation_changes_nothing_and_two_cancel_the_batch_keeping_every_file(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, running: str
) -> None:
    files = _files(layout)
    assert any(name.startswith("Inbox/") for name in files)

    refused = client.post(f"/uploads/{running}/cancel")
    assert refused.status_code == 400
    assert _state(session_factory, running) == (UploadStatus.RECEIVED, JobStatus.QUEUED)
    assert [event.type for event in _events(session_factory)][-1] != EventType.UPLOAD_CANCELLED

    token = _prepare(client, running)
    response = client.post(f"/uploads/{running}/cancel", data={"confirmation": token})

    assert response.status_code == 200
    assert "Parti iptal edildi" in response.text
    assert _state(session_factory, running) == (UploadStatus.CANCELLED, JobStatus.CANCELLED)
    confirmed, cancelled = _events(session_factory)[-2:]
    assert (confirmed.type, confirmed.actor) == (EventType.USER_CONFIRMED, USER)
    assert confirmed.data_json["operation"] == "cancel_upload"
    assert (cancelled.type, cancelled.actor, cancelled.upload_id) == (
        EventType.UPLOAD_CANCELLED,
        USER,
        running,
    )
    assert cancelled.data_json["reason"] == "manual"
    assert cancelled.data_json["stage"] == "received"
    assert _files(layout) == files  # K10: iptal hiçbir dosyayı silmez, değiştirmez


def test_a_token_works_once_and_only_for_its_own_batch(
    client: TestClient, session_factory: sessionmaker[Session], running: str
) -> None:
    other = _upload(client, _passport_pdf("00 0000002"))
    foreign = issue_token(session_factory, Operation.CANCEL_UPLOAD, other)
    dismiss_token = issue_token(session_factory, Operation.DISMISS, running)

    assert (
        client.post(f"/uploads/{running}/cancel", data={"confirmation": foreign}).status_code == 400
    )
    assert (
        client.post(f"/uploads/{running}/cancel", data={"confirmation": dismiss_token}).status_code
        == 400
    )
    token = _prepare(client, running)
    assert (
        client.post(f"/uploads/{running}/cancel", data={"confirmation": token}).status_code == 200
    )
    again = client.post(f"/uploads/{running}/cancel", data={"confirmation": token})
    assert again.status_code == 400
    assert _state(session_factory, other) == (UploadStatus.RECEIVED, JobStatus.QUEUED)
    types = [event.type for event in _events(session_factory)]
    assert types.count(EventType.UPLOAD_CANCELLED) == 1


# --- iptal edilen partinin sayfası ----------------------------------------------------------------


def test_the_cancelled_batch_says_who_cancelled_it_and_refuses_rerun_but_can_be_dismissed(
    client: TestClient, session_factory: sessionmaker[Session], running: str
) -> None:
    _cancel(client, running)

    page = client.get(f"/uploads/{running}")

    assert MANUAL_NOTICE.search(page.text)
    assert 'class="status status-cancelled"' in page.text
    assert "İptal edildi" in page.text
    assert _cancel_step(page.text) is None
    assert CANCELLED_MESSAGE in page.text
    assert 'id="dismiss-step"' in page.text  # 10.3.4: iptal edilen parti yoksayılabilir
    for path in (f"/uploads/{running}/rerun", f"/uploads/{running}/reanalyze/prepare"):
        response = client.post(path)
        assert response.status_code == 409
        assert CANCELLED_MESSAGE in response.text
    assert client.post(f"/uploads/{running}/dismiss/prepare").status_code == 200


def test_the_api_reports_cancelled_and_refuses_rerun(client: TestClient, running: str) -> None:
    _cancel(client, running)

    assert client.get(f"/api/uploads/{running}").json()["status"] == "cancelled"
    rerun = client.post(f"/api/uploads/{running}/rerun")
    assert rerun.status_code == 409
    assert rerun.json()["detail"] == CANCELLED_MESSAGE


def test_the_list_shows_and_filters_cancelled_batches(client: TestClient, running: str) -> None:
    waiting = _upload(client, _passport_pdf("00 0000003"))
    _cancel(client, running)

    page = client.get("/uploads", params={"status": "cancelled"})

    assert '<option value="cancelled" selected>İptal</option>' in page.text
    assert f'href="/uploads/{running}"' in page.text
    assert f'href="/uploads/{waiting}"' not in page.text
    assert 'class="status-cancelled">İptal edildi' in page.text


# --- tekrar tespiti (01.4.1, §D114 g) -------------------------------------------------------------


def test_the_same_file_uploaded_after_a_cancellation_is_not_a_duplicate(
    client: TestClient, running: str
) -> None:
    # Önce kural: süren partinin dosyası özgündür, aynı baytlar tekrar sayılır.
    duplicate = _upload(client)
    assert client.get(f"/api/uploads/{duplicate}").json()["files"][0]["is_duplicate"] is True
    _cancel(client, duplicate)
    _cancel(client, running)

    again = _upload(client)

    assert client.get(f"/api/uploads/{again}").json()["files"][0]["is_duplicate"] is False


# --- otomatik iptal: panel açılırken (10.3.7) -----------------------------------------------------


@pytest.mark.parametrize("path", ["/uploads", "/uploads/{id}"], ids=["liste", "detay"])
def test_opening_the_panel_cancels_a_batch_stuck_for_more_than_ten_minutes(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    running: str,
    path: str,
) -> None:
    created = _created_at(session_factory, running)
    url = path.format(id=running)

    _set_clock(app, created + timedelta(minutes=9, seconds=59))
    assert client.get(url).status_code == 200
    assert _state(session_factory, running) == (UploadStatus.RECEIVED, JobStatus.QUEUED)

    _set_clock(app, created + timedelta(minutes=10, seconds=1))
    assert client.get(url).status_code == 200

    assert _state(session_factory, running) == (UploadStatus.CANCELLED, JobStatus.CANCELLED)
    (event,) = [e for e in _events(session_factory) if e.type == EventType.UPLOAD_CANCELLED]
    assert (event.actor, event.data_json["reason"]) == ("system", "timeout")
    assert event.data_json["waited_seconds"] == 601
    assert TIMEOUT_NOTICE.search(client.get(f"/uploads/{running}").text)


def test_the_live_progress_fragment_does_not_cancel(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session], running: str
) -> None:
    _set_clock(app, _created_at(session_factory, running) + timedelta(hours=1))

    response = client.get(f"/upload/{running}/progress")

    assert response.status_code == 200
    assert _state(session_factory, running) == (UploadStatus.RECEIVED, JobStatus.QUEUED)


def test_the_progress_fragment_of_a_cancelled_batch_stops_polling(
    client: TestClient, running: str
) -> None:
    _cancel(client, running)

    response = client.get(f"/upload/{running}/progress")

    assert "İptal edildi" in response.text
    assert "hx-trigger" not in response.text
    assert "step-done" not in response.text


# --- üç dil (10.10.4) -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", ["You are about to cancel this batch. Are you sure?", "Cancelled"]),
        ("sr", ["Upravo ćete otkazati ovu seriju. Da li ste sigurni?", "Otkazan"]),
    ],
    ids=["en", "sr"],
)
def test_the_cancel_texts_follow_the_language_without_turkish_residue(
    app: FastAPI,
    client: TestClient,
    running: str,
    language: str,
    expected: list[str],
) -> None:
    user = PanelUser(SIGNED_IN.id, SIGNED_IN.username, SIGNED_IN.role, language=language)
    app.dependency_overrides[get_current_user] = lambda: user

    page = client.get(f"/uploads/{running}")
    prepared = client.post(f"/uploads/{running}/cancel/prepare")
    done = client.post(f"/uploads/{running}/cancel", data={"confirmation": _token(prepared.text)})
    cancelled = client.get(f"/uploads/{running}")

    assert expected[0] in page.text
    assert expected[1] in cancelled.text
    for response in (page, prepared, done, cancelled):
        assert_no_turkish(response.text, language)
