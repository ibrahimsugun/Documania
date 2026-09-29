"""10.7.4 — kuyruk öğesini kapatma ve yeniden açma: öğe detayında iki aşamalı onayla (§20.6)
gerekçeyle kapanır, "Çözülen" görünümünde gerekçesiyle durur ve tek adımda yeniden açılır (K16,
§D61, PLAN.md §C91).

Parti gerçek boru hattından geçer (`process_upload`, kayıtlı yanıt sağlayıcısı): sentetik pasaport
Hazır'a belge üretir, katalogda olmayan diploma Unknown kuyruğuna düşer (kaynak kopyası ve
`reason.json` Unknown klasöründe) ve aday tür olarak görülür. Yapay zekâ canlı çağrılmaz. Kapatma
ve yeniden açma dosya sistemine dokunmaz, aday tür görülmesini silmez; onay sunucuda sınanır: yalnız
birinci onayla gelen istek hiçbir şey değiştirmez (S16), belirteçsiz, kullanılmış, süresi geçmiş ya
da başka öğeye, gerekçeye, nota, işleme veya oturuma ait belirteç 400 (§20.6.2).
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

import app.web.confirm as confirm
from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import (
    CandidateDocumentType,
    Event,
    KnownDocumentType,
    Plan,
    QueueCloseReason,
    QueueItem,
    QueueResolution,
    Upload,
    utcnow,
)
from app.events import EventType
from app.pipeline.orchestrate import process_upload
from app.pipeline.queue_close import ALREADY_RESOLVED, NOT_CLOSED, NOTE_REQUIRED, NOTE_TOO_LONG
from app.storage import DataLayout
from app.web.auth import SESSION_COOKIE, get_current_user
from app.web.confirm import CONFIRMATION_REFUSED, CONFIRMATION_TEXTS, Operation
from app.web.routers import queue as queue_router
from app.web.routers.queue import (
    BAD_CLOSE_REASON,
    CLOSE_NOTICES,
    QUEUE_ITEM_NOT_FOUND,
    RESOLVED_NOTE,
    SUPERSEDED_NOTE,
    close_subject,
)
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_PRUEBA,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
    unknown_document_page,
)
from tests.web.conftest import issue_token

SETTINGS = Settings(_env_file=None, database_url="sqlite://")
USER = "test-yonetici"
DIPLOMA_NAME = "Peruvian Diploma"
# §20.6 "Kuyruk öğesini kapat" — birebir.
FIRST_TEXT = "Bu kuyruk öğesini kapatmak üzeresiniz. Emin misiniz?"
SECOND_TEXT = (
    "Öğe çözülmüş sayılacak, dosya kopyası ve gerekçesi yerinde kalacaktır. Son kararınız mı?"
)


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    """Onay belirteci oturum çerezinden türetilir; oturum bağımlılığı geçersiz kılındığı için çerez
    testte elle konur."""
    client.cookies.set(SESSION_COOKIE, "oturum-bir")


def _batch(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    directory: Path,
    *,
    passport_number: str = "00 0000001",
    diploma_number: str = "DIP-0000077",
) -> str:
    """Pasaport (Hazır'a belge) ve katalog dışı diploma (Unknown + aday tür) yükler ve gerçek boru
    hattından geçirir; parti kimliğini döner."""
    passport = [
        passport_page(
            PERSON_ORNEKOVA, document_number=passport_number, expiry_date=date(2030, 1, 1)
        )
    ]
    diploma = [
        unknown_document_page(
            PERSON_PRUEBA,
            candidate_type_name=DIPLOMA_NAME,
            title="DIPLOMA",
            document_number=diploma_number,
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
            provider=recorded_provider(directory, passport, diploma),
        )
    return upload_id


@pytest.fixture
def item_id(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> int:
    upload_id = _batch(client, session_factory, layout, tmp_path / "kayit")
    with session_factory() as session:
        (item,) = session.scalars(select(QueueItem).where(QueueItem.upload_id == upload_id))
        assert item.resolved_at is None
        return item.id


def _token(response_text: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', response_text)
    assert match is not None, response_text
    return match.group(1)


def _prepare(
    client: TestClient, item_id: int, reason: str = "not_a_document", note: str = ""
) -> str:
    response = client.post(
        f"/queues/{item_id}/close/prepare", data={"reason": reason, "note": note}
    )
    assert response.status_code == 200, response.text
    return _token(response.text)


def _close(
    client: TestClient,
    item_id: int,
    token: str | None,
    reason: str = "not_a_document",
    note: str = "",
) -> object:
    data = {"reason": reason, "note": note}
    if token is not None:
        data["confirmation"] = token
    return client.post(f"/queues/{item_id}/close", data=data, follow_redirects=False)


def _events(session_factory: sessionmaker[Session]) -> list[tuple[int, str]]:
    with session_factory() as session:
        return [(row.id, row.type) for row in session.scalars(select(Event).order_by(Event.id))]


def _state(session_factory: sessionmaker[Session]) -> list[tuple[object, ...]]:
    with session_factory() as session:
        return [
            (
                item.id,
                item.resolved_at,
                item.resolved_by,
                item.resolution,
                item.resolution_reason,
                item.resolution_note,
            )
            for item in session.scalars(select(QueueItem).order_by(QueueItem.id))
        ]


def _files(layout: DataLayout) -> dict[str, str]:
    return {
        path.relative_to(layout.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(layout.root.rglob("*"))
        if path.is_file()
    }


def _tab_counters(html: str) -> dict[str, int]:
    tabs = re.search(r'<nav class="tabs".*?</nav>', html, re.S)
    assert tabs is not None
    return {
        label: int(count)
        for label, count in re.findall(
            r'>([^<>]+?) <span class="counter" title="Bekleyen öğe">(\d+)</span>', tabs.group(0)
        )
    }


def _queue_rows(html: str) -> list[int]:
    return [int(number) for number in re.findall(r'<td><a href="/queues/(\d+)">', html)]


# --- detay: kapatma bağlantısı ve birinci onay ----------------------------------------------------


def test_the_detail_page_of_a_pending_item_links_to_the_close_flow(
    client: TestClient, item_id: int
) -> None:
    page = client.get(f"/queues/{item_id}")

    assert page.status_code == 200
    assert '<h2 id="close-title">Öğeyi kapat</h2>' in page.text
    assert f'href="/queues/{item_id}/close/confirm"' in page.text
    # Kapatma doğrudan tetiklenmez; yeniden açma düğmesi yok.
    assert f'action="/queues/{item_id}/close"' not in page.text
    assert f'action="/queues/{item_id}/reopen"' not in page.text


def test_the_first_step_offers_the_three_reasons_a_note_and_the_first_text(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, item_id: int
) -> None:
    events, state, files = _events(session_factory), _state(session_factory), _files(layout)

    page = client.get(f"/queues/{item_id}/close/confirm")

    assert page.status_code == 200
    assert CONFIRMATION_TEXTS[Operation.CLOSE_QUEUE_ITEM].first == FIRST_TEXT
    assert f'<p class="confirm-text" role="alert">{FIRST_TEXT}</p>' in page.text
    assert f'action="/queues/{item_id}/close/prepare"' in page.text
    reasons = re.findall(
        r'<input type="radio" name="reason" value="([a-z_]+)" required> ([^<]+)', page.text
    )
    assert [(value, label.strip()) for value, label in reasons] == [
        ("not_a_document", "Belge değil / çöp sayfa"),
        ("already_exists", "Zaten var"),
        ("other", "Diğer"),
    ]
    assert re.search(r'<input id="close-note" name="note" type="text" maxlength="200"', page.text)
    assert "<textarea" not in page.text
    assert "<dt>Kuyruk gerekçesi</dt>" in page.text
    assert 'href="/uploads/' in page.text
    assert (_events(session_factory), _state(session_factory), _files(layout)) == (
        events,
        state,
        files,
    )


# --- ikinci onay: hiçbir şey değişmez (S16) -------------------------------------------------------


def test_prepare_gives_the_second_text_and_a_token_and_changes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, item_id: int
) -> None:
    events, state, files = _events(session_factory), _state(session_factory), _files(layout)

    response = client.post(
        f"/queues/{item_id}/close/prepare",
        data={"reason": "other", "note": "  müşterinin eski evrakı  "},
    )

    assert response.status_code == 200, response.text
    assert CONFIRMATION_TEXTS[Operation.CLOSE_QUEUE_ITEM].second == SECOND_TEXT
    assert f'<p class="confirm-text" role="alert">{SECOND_TEXT}</p>' in response.text
    assert f'action="/queues/{item_id}/close"' in response.text
    assert "Kapatma gerekçesi: Diğer — müşterinin eski evrakı" in response.text
    assert '<input type="hidden" name="reason" value="other">' in response.text
    assert '<input type="hidden" name="note" value="müşterinin eski evrakı">' in response.text
    assert _token(response.text)
    # Yalnız belirteç yazıldı: olay, öğe ve dosyalar aynı.
    assert _events(session_factory) == events
    assert _state(session_factory) == state
    assert _files(layout) == files


@pytest.mark.parametrize(
    ("reason", "note", "message"),
    [
        ("", "", BAD_CLOSE_REASON),
        ("silindi", "", BAD_CLOSE_REASON),
        ("other", "   ", NOTE_REQUIRED),
        ("not_a_document", "x" * 201, NOTE_TOO_LONG),
    ],
)
def test_an_invalid_reason_or_note_is_422_with_the_form_again(
    client: TestClient,
    session_factory: sessionmaker[Session],
    item_id: int,
    reason: str,
    note: str,
    message: str,
) -> None:
    events, state = _events(session_factory), _state(session_factory)

    response = client.post(
        f"/queues/{item_id}/close/prepare", data={"reason": reason, "note": note}
    )
    final = _close(client, item_id, "x", reason=reason, note=note)

    assert response.status_code == 422
    assert message in unescape(response.text)
    assert f'action="/queues/{item_id}/close/prepare"' in response.text
    assert 'name="confirmation"' not in response.text
    assert final.status_code == 422
    assert _events(session_factory) == events
    assert _state(session_factory) == state


def test_the_chosen_reason_and_note_survive_a_422(client: TestClient, item_id: int) -> None:
    response = client.post(f"/queues/{item_id}/close/prepare", data={"reason": "other", "note": ""})

    assert response.status_code == 422
    assert '<input type="radio" name="reason" value="other" required checked>' in response.text


# --- belirteç: 400 ve hiçbir şey ------------------------------------------------------------------


def test_closing_without_a_valid_token_is_400_and_does_nothing(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    events, state = _events(session_factory), _state(session_factory)

    for token in (None, "", "x.y"):
        response = _close(client, item_id, token)
        assert response.status_code == 400
        assert CONFIRMATION_REFUSED in unescape(response.text)
        assert f'href="/queues/{item_id}/close/confirm"' in response.text  # yeniden başlat
    assert _events(session_factory) == events
    assert _state(session_factory) == state


def test_an_expired_token_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    session_factory: sessionmaker[Session],
    item_id: int,
) -> None:
    token = _prepare(client, item_id)
    state = _state(session_factory)
    later = utcnow() + confirm.CONFIRMATION_TTL + timedelta(seconds=5)
    monkeypatch.setattr(confirm, "utcnow", lambda: later)

    assert _close(client, item_id, token).status_code == 400
    assert _state(session_factory) == state


def test_a_token_is_bound_to_its_item_reason_note_operation_and_session(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    item_id: int,
) -> None:
    other_upload = _batch(
        client,
        session_factory,
        layout,
        tmp_path / "ikinci",
        passport_number="00 0000002",
        diploma_number="DIP-0000078",
    )
    with session_factory() as session:
        other_item = session.scalars(
            select(QueueItem.id).where(QueueItem.upload_id == other_upload)
        ).one()
    subject = close_subject(item_id, QueueCloseReason.NOT_A_DOCUMENT, None)
    tokens = {
        "başka öğe": _prepare(client, other_item),
        "başka gerekçe": _prepare(client, item_id, reason="already_exists"),
        "başka not": _prepare(client, item_id, note="arka yüz"),
        "başka işlem": issue_token(session_factory, Operation.ARCHIVE, subject),
        "başka oturum": issue_token(
            session_factory, Operation.CLOSE_QUEUE_ITEM, subject, cookie="baska"
        ),
    }
    events, state = _events(session_factory), _state(session_factory)

    for label, token in tokens.items():
        response = _close(client, item_id, token, reason="not_a_document", note="")
        assert response.status_code == 400, label
    assert _events(session_factory) == events
    assert _state(session_factory) == state


# --- kapatma --------------------------------------------------------------------------------------


def test_a_confirmed_close_resolves_the_item_logs_the_user_and_keeps_every_file(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, item_id: int
) -> None:
    token = _prepare(client, item_id, reason="other", note="ikinci tarama")
    events_before, files_before = _events(session_factory), _files(layout)
    with session_factory() as session:
        seen_before = session.scalars(select(CandidateDocumentType.seen_count)).one()
    before = utcnow()

    response = _close(client, item_id, token, reason="other", note="ikinci tarama")

    assert response.status_code == 303
    assert response.headers["location"] == f"/queues/{item_id}?notice=closed"
    with session_factory() as session:
        item = session.get_one(QueueItem, item_id)
        assert item.resolved_at is not None and before <= item.resolved_at <= utcnow()
        assert item.resolved_by == USER
        assert item.resolution == QueueResolution.CLOSED
        assert (item.resolution_reason, item.resolution_note) == ("other", "ikinci tarama")
        new = session.scalars(
            select(Event).where(Event.id > events_before[-1][0]).order_by(Event.id)
        ).all()
        assert [event.type for event in new] == [
            EventType.USER_CONFIRMED,
            EventType.QUEUE_ITEM_CLOSED,
        ]
        confirmed, closed = new
        assert confirmed.actor == closed.actor == USER
        assert confirmed.upload_id == closed.upload_id == item.upload_id
        assert confirmed.data_json is not None
        assert confirmed.data_json["operation"] == "close_queue_item"
        assert confirmed.data_json["target"] == {"queue_item_id": item_id, "reason": "other"}
        assert closed.data_json == {"queue_item_id": item_id, "reason": "other"}
        # Aday tür görülmesi ve örnekleri kalır (§C80).
        assert session.scalars(select(CandidateDocumentType.seen_count)).one() == seen_before
    # Silme yok: kuyruk kopyası ve reason.json dahil dosya sistemi bayt bayt aynı.
    assert _files(layout) == files_before
    assert any(
        path.startswith("Unknown/") and path.endswith("reason.json") for path in files_before
    )
    assert any(path.startswith("Unknown/") and path.endswith(".pdf") for path in files_before)
    assert _events(session_factory)[: len(events_before)] == events_before
    assert DIPLOMA_NAME in client.get("/document-types/candidate-types").text


def test_a_closed_item_leaves_the_counters_and_shows_its_reason_among_the_resolved(
    client: TestClient, item_id: int
) -> None:
    open_before = client.get("/queues?tab=unknown").text
    assert _queue_rows(open_before) == [item_id]
    assert _tab_counters(open_before)["Tür bilinmiyor"] == 1

    token = _prepare(client, item_id)
    assert _close(client, item_id, token).status_code == 303

    pending = client.get("/queues?tab=unknown").text
    assert _queue_rows(pending) == []
    assert _tab_counters(pending)["Tür bilinmiyor"] == 0
    resolved = client.get("/queues?tab=unknown&state=resolved").text
    assert _queue_rows(resolved) == [item_id]
    assert _tab_counters(resolved)["Tür bilinmiyor"] == 0
    assert re.search(
        rf"\d{{4}}-\d\d-\d\d \d\d:\d\d:\d\d UTC · {USER} · kapatıldı: Belge değil / çöp sayfa",
        resolved,
    )
    assert f'action="/queues/{item_id}/reopen"' in resolved
    assert "Yeniden aç</button>" in resolved
    # Detay: bildirim, çözüm metni, yeniden açma düğmesi ve olaylar; kapatma bağlantısı yok.
    page = client.get(f"/queues/{item_id}?notice=closed").text
    assert CLOSE_NOTICES["closed"] in page
    assert "kapatıldı: Belge değil / çöp sayfa" in page
    assert f'action="/queues/{item_id}/reopen"' in page
    assert f'href="/queues/{item_id}/close/confirm"' not in page
    assert "QUEUE_ITEM_CLOSED" in page
    # Tanınmayan bildirim kodu yok sayılır.
    assert CLOSE_NOTICES["closed"] not in client.get(f"/queues/{item_id}?notice=yok").text


def test_the_note_is_shown_with_the_reason(client: TestClient, item_id: int) -> None:
    token = _prepare(client, item_id, reason="already_exists", note="E0001'de var")
    closed = _close(client, item_id, token, reason="already_exists", note="E0001'de var")
    assert closed.status_code == 303

    resolved = unescape(client.get("/queues?tab=unknown&state=resolved").text)

    assert "kapatıldı: Zaten var — E0001'de var" in resolved


def test_a_closed_item_is_neither_closed_again_nor_assigned(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    first, second = _prepare(client, item_id), _prepare(client, item_id)
    assert _close(client, item_id, first).status_code == 303
    events, state = _events(session_factory), _state(session_factory)

    responses = [
        client.get(f"/queues/{item_id}/close/confirm"),
        client.post(
            f"/queues/{item_id}/close/prepare", data={"reason": "not_a_document", "note": ""}
        ),
        _close(client, item_id, second),
    ]

    for response in responses:
        assert response.status_code == 409
        assert ALREADY_RESOLVED in unescape(response.text)
    assign = client.post(f"/queues/{item_id}/assign/prepare", data={"employee_id": "E0001"})
    assert assign.status_code == 409 and RESOLVED_NOTE in unescape(assign.text)
    assert _events(session_factory) == events  # USER_CONFIRMED geri alındı
    assert _state(session_factory) == state


def test_an_item_of_an_old_plan_version_can_be_closed(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    with session_factory() as session:
        upload_id = session.get_one(QueueItem, item_id).upload_id
        # Partiye yeni plan sürümü açıldı: öğe eski sürüm oldu (K18) — atanamaz, kapatılabilir.
        session.add(Plan(upload_id=upload_id, version=2, json={}, plan_hash="2" * 64))
        session.commit()
    page = client.get(f"/queues/{item_id}").text
    assert SUPERSEDED_NOTE in page
    assert f'href="/queues/{item_id}/close/confirm"' in page

    token = _prepare(client, item_id)
    assert _close(client, item_id, token).status_code == 303

    assert _queue_rows(client.get("/queues?tab=unknown&state=superseded").text) == []
    assert _queue_rows(client.get("/queues?tab=unknown&state=resolved").text) == [item_id]


def test_prepare_without_a_session_cookie_issues_no_token(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    client.cookies.clear()

    response = client.post(
        f"/queues/{item_id}/close/prepare", data={"reason": "not_a_document", "note": ""}
    )

    assert response.status_code == 400
    assert 'name="confirmation"' not in response.text
    assert "<dt>Kuyruk gerekçesi</dt>" in response.text


def test_a_close_that_loses_a_race_is_409_and_keeps_the_token_unused(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    session_factory: sessionmaker[Session],
    item_id: int,
) -> None:
    token = _prepare(client, item_id)
    events, state = _events(session_factory), _state(session_factory)

    def _lost(*_args: object, **_kwargs: object) -> None:
        # Öğe onaydan sonra, kapatmadan önce başka bir işlemle çözüldü.
        raise queue_router.QueueItemNotClosableError(ALREADY_RESOLVED)

    monkeypatch.setattr(queue_router, "close_queue_item", _lost)
    response = _close(client, item_id, token)

    assert response.status_code == 409
    assert ALREADY_RESOLVED in unescape(response.text)
    assert _events(session_factory) == events  # USER_CONFIRMED geri alındı
    assert _state(session_factory) == state
    monkeypatch.undo()
    assert _close(client, item_id, token).status_code == 303  # belirteç tüketilmemişti


def test_an_unknown_item_is_404(client: TestClient) -> None:
    responses = [
        client.get("/queues/999999/close/confirm"),
        client.post("/queues/999999/close/prepare", data={"reason": "other", "note": "n"}),
        _close(client, 999999, "x"),
        client.post("/queues/999999/reopen", follow_redirects=False),
    ]

    for response in responses:
        assert response.status_code == 404
        assert QUEUE_ITEM_NOT_FOUND in response.text


def test_close_and_reopen_need_a_session(app: FastAPI, client: TestClient, item_id: int) -> None:
    app.dependency_overrides.pop(get_current_user)

    requests = [
        client.get(f"/queues/{item_id}/close/confirm", follow_redirects=False),
        client.post(f"/queues/{item_id}/close/prepare", follow_redirects=False),
        client.post(f"/queues/{item_id}/close", follow_redirects=False),
        client.post(f"/queues/{item_id}/reopen", follow_redirects=False),
    ]

    for response in requests:
        assert response.status_code in (303, 401)
        assert response.headers.get("location", "/login").startswith("/login")


# --- yeniden açma ---------------------------------------------------------------------------------


def test_reopening_is_one_step_logs_the_user_and_brings_the_item_back(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, item_id: int
) -> None:
    token = _prepare(client, item_id, reason="other", note="yanlış")
    assert _close(client, item_id, token, reason="other", note="yanlış").status_code == 303
    events_before, files_before = _events(session_factory), _files(layout)

    response = client.post(f"/queues/{item_id}/reopen", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/queues/{item_id}?notice=reopened"
    with session_factory() as session:
        item = session.get_one(QueueItem, item_id)
        assert (item.resolved_at, item.resolved_by, item.resolution) == (None, None, None)
        assert (item.resolution_reason, item.resolution_note) == (None, None)
        (event,) = session.scalars(select(Event).where(Event.id > events_before[-1][0])).all()
        # Tek adım: onay olayı yok, yalnız işlemin kendi olayı kullanıcı adıyla.
        assert event.type == EventType.QUEUE_ITEM_REOPENED
        assert event.actor == USER
        assert event.data_json == {"queue_item_id": item_id, "reason": "other"}
    assert _files(layout) == files_before
    pending = client.get("/queues?tab=unknown").text
    assert _queue_rows(pending) == [item_id]
    assert _tab_counters(pending)["Tür bilinmiyor"] == 1
    page = client.get(f"/queues/{item_id}?notice=reopened").text
    assert CLOSE_NOTICES["reopened"] in page
    assert f'href="/queues/{item_id}/close/confirm"' in page
    assert "QUEUE_ITEM_REOPENED" in page
    # Açılan öğe yeniden kapatılabilir.
    assert _close(client, item_id, _prepare(client, item_id)).status_code == 303


def test_only_a_closed_item_is_reopened(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    events, state = _events(session_factory), _state(session_factory)

    response = client.post(f"/queues/{item_id}/reopen", follow_redirects=False)

    assert response.status_code == 409
    assert NOT_CLOSED in unescape(response.text)
    assert _events(session_factory) == events
    assert _state(session_factory) == state
