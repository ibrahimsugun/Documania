"""10.7.2 — kuyruktan çalışana atama: arama ile çalışan seçilir, iki aşamalı onayla atanır (K16,
§20.6, §20.6.1, §20.6.2).

Kuyruk öğesi gerçek planlayıcıdan (06.1) ve kuyruğa yönlendirmeden (08.1) geçer (`_queued_item`:
zorunlu alanı okunamayan sentetik çalışma izni, Unreadable); sayfa analizleri saklanmış sentetik
yanıtlardır, yapay zekâ sağlayıcısı çağrılmaz. Onay belirteci 10.8.1'in tek kullanımlık
belirtecidir ve oturum çerezine bağlıdır; oturum bağımlılığı testte geçersiz kılındığı için çerez
elle konur. Gerçek kimlik belgesi kullanılmaz.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

import app.web.confirm as confirm
from app.db.models import Document, Employee, Event, QueueItem, QueueKind, utcnow
from app.events import EventType
from app.storage import DataLayout, sha256_file
from app.web.auth import SESSION_COOKIE, get_current_user
from app.web.confirm import CONFIRMATION_REFUSED, Operation, second_text
from app.web.routers.queue import (
    ASSIGNEE_NOT_FOUND,
    QUEUE_ITEM_NOT_FOUND,
    RESOLVED_NOTE,
    SUPERSEDED_NOTE,
    TYPELESS_NOTE,
    assignment_subject,
)
from app.web.routers.upload_page import reanalysis_subject
from tests.web.conftest import SESSION, SIGNED_IN, issue_token
from tests.web.test_queue import PERMIT, TARGET, TARGET_FOLDER, _queued_item, _refuse_provider
from tests.web.test_queue_page import _payload, _plan, _queue_item, _source_file, _upload

TARGET_NAME = "Kayitli Kisi"
OTHER = "E0043"
# §20.6 — birebir; `<Ad Soyad>` seçilen çalışanın adıyla dolar.
FIRST_TEXT = f"Bu belgeyi {TARGET_NAME} çalışanına atamak üzeresiniz. Emin misiniz?"
SECOND_TEXT = "Bu işlem sistemdeki belge organizasyonunu değiştirecektir. Son kararınız mı?"


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, SESSION)


@pytest.fixture
def item_id(session_factory: sessionmaker[Session], layout: DataLayout) -> int:
    """Bekleyen, türü belli (Unreadable çalışma izni) öğe ve iki kayıtlı çalışan."""
    queue_item_id = _queued_item(session_factory, layout)
    with session_factory() as session:
        session.add(
            Employee(id=OTHER, folder_name="Baska_Biri_E0043", given_names="Baska", surname="Biri")
        )
        session.commit()
    layout.ensure_employee_tree("Baska_Biri_E0043")
    return queue_item_id


def _synthetic_open_item(session_factory: sessionmaker[Session], upload_id: str) -> int:
    """Türü belli, bekleyen ama saklı planı bozuk (boş JSON) öğe: panel adımlarını geçer, atamanın
    kendisi `PlanIntegrityError` ile düşer."""
    with session_factory() as session:
        upload = _upload(session, upload_id)
        plan = _plan(session, upload, 1)
        source = _source_file(session, upload, "izin.pdf", page_count=1)
        row = _queue_item(
            session,
            upload,
            plan,
            QueueKind.UNRESOLVED,
            payload=_payload(source.id, [0], slug=PERMIT),
        )
        session.commit()
        return row.id


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match is not None, html
    return match.group(1)


def _prepare(client: TestClient, queue_item_id: int, employee_id: str = TARGET) -> str:
    response = client.post(
        f"/queues/{queue_item_id}/assign/prepare", data={"employee_id": employee_id}
    )
    assert response.status_code == 200, response.text
    return _token(response.text)


def _assign(
    client: TestClient, queue_item_id: int, token: str | None, employee_id: str = TARGET
) -> Any:  # TestClient yanıtı
    data = {"employee_id": employee_id}
    if token is not None:
        data["confirmation"] = token
    return client.post(f"/queues/{queue_item_id}/assign", data=data)


def _count(session: Session, event_type: EventType) -> int:
    return session.scalar(select(func.count()).where(Event.type == event_type.value)) or 0


def _unchanged(session_factory: sessionmaker[Session], queue_item_id: int) -> None:
    """Hiçbir şey olmadı: öğe çözülmedi, çıktı yok, onay ve atama olayı yazılmadı."""
    with session_factory() as session:
        queue_item = session.get_one(QueueItem, queue_item_id)
        assert (queue_item.resolved_at, queue_item.resolved_by) == (None, None)
        assert session.scalars(select(Document)).all() == []
        assert _count(session, EventType.USER_CONFIRMED) == 0
        assert _count(session, EventType.MANUAL_ASSIGN) == 0


def _section(html: str, section_id: str) -> str:
    match = re.search(rf'<section id="{section_id}".*?</section>', html, re.S)
    assert match is not None, html
    return match.group(0)


# --- öğe detayındaki atama bölümü ---------------------------------------------------------------


def test_open_item_with_a_type_offers_the_employee_search(client: TestClient, item_id: int) -> None:
    html = client.get(f"/queues/{item_id}").text

    section = _section(html, "assign")
    assert "Çalışana ata" in section
    assert f'hx-get="/queues/{item_id}/assign/employees"' in section
    assert 'name="q"' in section
    assert '<div id="assign-results"' in section and '<div id="assign-step"' in section


def test_item_without_a_type_says_it_cannot_be_assigned(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    queue_item_id = _queued_item(session_factory, layout, unknown=True)

    html = client.get(f"/queues/{queue_item_id}").text

    section = _section(html, "assign")
    assert TYPELESS_NOTE in section
    assert "/assign/employees" not in section


def test_superseded_or_resolved_item_has_no_assignment_section(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        upload = _upload(session)
        old_plan, _new_plan = _plan(session, upload, 1), _plan(session, upload, 2)
        superseded = _queue_item(
            session, upload, old_plan, QueueKind.UNRESOLVED, payload=_payload(1, [0], slug=PERMIT)
        )
        resolved = _queue_item(
            session,
            upload,
            _new_plan,
            QueueKind.UNRESOLVED,
            item_id="i2",
            payload=_payload(1, [0], slug=PERMIT),
            resolved_by="ik.ayse",
        )
        session.commit()
        ids = (superseded.id, resolved.id)

    for queue_item_id in ids:
        html = client.get(f"/queues/{queue_item_id}").text
        assert '<section id="assign"' not in html
        assert "/assign/" not in html


# --- arama ile seçim ------------------------------------------------------------------------------


def test_search_finds_the_employee_and_offers_to_select_them(
    client: TestClient, item_id: int
) -> None:
    response = client.get(f"/queues/{item_id}/assign/employees", params={"q": "kayitli"})

    assert response.status_code == 200
    html = response.text
    assert "1 çalışan bulundu" in html
    assert f"<td>{TARGET}</td>" in html and TARGET_NAME in html
    assert OTHER not in html  # arama daraltır
    assert f'hx-get="/queues/{item_id}/assign/confirm?employee_id={TARGET}"' in html
    assert 'hx-target="#assign-step"' in html


def test_search_uses_the_employee_search_fields(client: TestClient, item_id: int) -> None:
    # 10.4.2'nin araması: terimler "ve", alanlar "veya" — soyad + ad sırasıyla da bulur.
    html = client.get(f"/queues/{item_id}/assign/employees", params={"q": "biri baska"}).text

    assert f"<td>{OTHER}</td>" in html
    assert f"<td>{TARGET}</td>" not in html


def test_empty_search_lists_nobody_and_no_match_says_so(client: TestClient, item_id: int) -> None:
    empty = client.get(f"/queues/{item_id}/assign/employees", params={"q": "  "})
    missing = client.get(f"/queues/{item_id}/assign/employees", params={"q": "yokboyle"})

    assert empty.status_code == 200 and missing.status_code == 200
    assert "<table" not in empty.text and "Atanacak çalışanı bulmak için" in empty.text
    assert "<table" not in missing.text and "“yokboyle” ile eşleşen çalışan yok." in missing.text


def test_long_result_lists_are_cut_and_say_so(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    with session_factory() as session:
        for number in range(100, 130):
            session.add(
                Employee(
                    id=f"E0{number}",
                    folder_name=f"Ortak_Ad_E0{number}",
                    given_names="Ortak",
                    surname=f"Ad{number}",
                )
            )
        session.commit()

    html = client.get(f"/queues/{item_id}/assign/employees", params={"q": "ortak"}).text

    assert "30 çalışan bulundu; ilk 25 gösteriliyor, aramayı daraltın" in html
    assert html.count('class="select-assignee"') == 25


# --- iki aşamalı onay -----------------------------------------------------------------------------


def test_selecting_an_employee_shows_the_first_confirmation_verbatim_and_changes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    response = client.get(f"/queues/{item_id}/assign/confirm", params={"employee_id": TARGET})

    assert response.status_code == 200
    html = response.text
    assert f'<p class="confirm-text" role="alert">{FIRST_TEXT}</p>' in html
    assert f"Seçilen çalışan: {TARGET_NAME} ({TARGET})" in html
    assert f'hx-post="/queues/{item_id}/assign/prepare"' in html
    assert f'<input type="hidden" name="employee_id" value="{TARGET}">' in html
    assert 'name="confirmation"' not in html  # belirteç birinci onaydan sonra gelir
    _unchanged(session_factory, item_id)


def test_first_confirmation_gives_the_second_one_with_a_token_and_changes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    response = client.post(f"/queues/{item_id}/assign/prepare", data={"employee_id": TARGET})

    assert response.status_code == 200
    html = response.text
    assert SECOND_TEXT == second_text(Operation.ASSIGN)
    assert f'<p class="confirm-text" role="alert">{SECOND_TEXT}</p>' in html
    assert f'hx-post="/queues/{item_id}/assign"' in html
    assert f'<input type="hidden" name="employee_id" value="{TARGET}">' in html
    assert _token(html)
    _unchanged(session_factory, item_id)


def test_confirmed_assignment_writes_the_output_and_logs_the_user_with_both_timestamps(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    item_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _prepare(client, item_id)
    _refuse_provider(monkeypatch)  # K9: atama yapay zekâya sorulmaz

    response = _assign(client, item_id, token)

    assert response.status_code == 200, response.text
    with session_factory() as session:
        queue_item = session.get_one(QueueItem, item_id)
        (document,) = session.scalars(select(Document)).all()
        (upload_file,) = queue_item.upload.files
        assert queue_item.resolved_by == SIGNED_IN.username
        assert document.employee_id == TARGET
        output = layout.resolve(document.path)
        assert output == layout.ready_dir(TARGET_FOLDER) / "Kayitli_Kisi-Work-Permit.pdf"
        assert sha256_file(output) == upload_file.sha256  # içerik değişmez (K11)
        events = list(
            session.scalars(
                select(Event)
                .where(Event.upload_id == queue_item.upload_id)
                .order_by(Event.ts, Event.id)
            )
        )
        types = [event.type for event in events]
        assert types.index(EventType.USER_CONFIRMED) < types.index(EventType.MANUAL_ASSIGN)
        confirmed = next(e for e in events if e.type == EventType.USER_CONFIRMED)
        manual = next(e for e in events if e.type == EventType.MANUAL_ASSIGN)
        # §20.6.1 / §20.6.2: kullanıcı adı, işlem, hedef ve iki onayın zamanı.
        assert confirmed.actor == manual.actor == SIGNED_IN.username
        data = confirmed.data_json
        assert data is not None
        assert data["operation"] == "assign"
        assert data["target"] == {"queue_item_id": item_id, "employee_id": TARGET}
        first = datetime.fromisoformat(data["first_confirmed_at"])
        second = datetime.fromisoformat(data["second_confirmed_at"])
        assert first <= second <= utcnow()
        assert TARGET_NAME not in str(data)  # olay kişisel değer taşımaz (CONVENTIONS §6)
    html = response.text
    assert f"Öğe {TARGET_NAME} ({TARGET}) çalışanına atandı: Kayitli_Kisi-Work-Permit.pdf" in html
    assert f'<a href="/documents/{document.id}/history">Çıktının geçmişi</a>' in html
    assert '<div id="assign-results" hx-swap-oob="true"></div>' in html


def test_after_assignment_the_item_is_resolved_and_the_counter_drops(
    client: TestClient, item_id: int
) -> None:
    assert _assign(client, item_id, _prepare(client, item_id)).status_code == 200

    detail = client.get(f"/queues/{item_id}").text
    listing = client.get("/queues?tab=unreadable").text

    assert "<dt>Durum</dt><dd>Çözülen</dd>" in detail
    assert '<section id="assign"' not in detail
    timeline = _section(detail, "timeline")
    assert EventType.USER_CONFIRMED.value in timeline
    assert EventType.MANUAL_ASSIGN.value in timeline and SIGNED_IN.username in timeline
    assert 'title="Bekleyen öğe">0</span>' in listing


# --- belirteç kuralları (§20.6.1 adım 4–5, §20.6.2) -----------------------------------------------


@pytest.mark.parametrize("token", [None, "", "abc", "123.deadbeef"], ids=repr)
def test_assignment_without_a_valid_token_changes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    item_id: int,
    token: str | None,
) -> None:
    # S16: yalnız birinci onayla (ya da hiç onaysız) gelen istek hiçbir değişiklik yapmaz.
    response = _assign(client, item_id, token)

    assert response.status_code == 400
    assert CONFIRMATION_REFUSED in response.text
    _unchanged(session_factory, item_id)
    assert list(layout.ready_dir(TARGET_FOLDER).iterdir()) == []


def test_the_same_token_twice_is_refused(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    token = _prepare(client, item_id)
    assert _assign(client, item_id, token).status_code == 200

    replay = _assign(client, item_id, token)

    assert replay.status_code == 409
    assert RESOLVED_NOTE in replay.text
    with session_factory() as session:
        assert len(session.scalars(select(Document)).all()) == 1
        assert _count(session, EventType.USER_CONFIRMED) == 1
        assert _count(session, EventType.MANUAL_ASSIGN) == 1


def test_an_expired_token_is_refused(
    client: TestClient,
    session_factory: sessionmaker[Session],
    item_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _prepare(client, item_id)
    later = utcnow() + confirm.CONFIRMATION_TTL + timedelta(seconds=5)
    monkeypatch.setattr(confirm, "utcnow", lambda: later)

    response = _assign(client, item_id, token)

    assert response.status_code == 400
    _unchanged(session_factory, item_id)


def test_a_token_is_bound_to_its_employee_its_item_and_its_session(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    token = _prepare(client, item_id)
    other_item = _synthetic_open_item(session_factory, "u_baska")

    other_employee = _assign(client, item_id, token, employee_id=OTHER)
    wrong_item = _assign(client, other_item, token)
    client.cookies.set(SESSION_COOKIE, "oturum-iki")
    other_session = _assign(client, item_id, token)

    for response in (other_employee, wrong_item, other_session):
        assert response.status_code == 400, response.text
    _unchanged(session_factory, item_id)
    with session_factory() as session:
        assert session.get_one(QueueItem, other_item).resolved_at is None


def test_a_token_of_another_operation_is_refused(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    # Aynı oturumun yeniden analiz belirteci (10.3.2) ve aynı hedefe başka işlem belirteci
    # atamada geçmez: belirteç işleme bağlıdır.
    with session_factory() as session:
        upload_id = session.get_one(QueueItem, item_id).upload_id
    foreign = issue_token(session_factory, Operation.REANALYZE, reanalysis_subject(upload_id, 1))
    same_target = issue_token(session_factory, Operation.MOVE, assignment_subject(item_id, TARGET))
    own = issue_token(session_factory, Operation.ASSIGN, assignment_subject(item_id, TARGET))

    for token in (foreign, same_target):
        response = _assign(client, item_id, token)
        assert response.status_code == 400
    _unchanged(session_factory, item_id)
    assert _assign(client, item_id, own).status_code == 200


def test_prepare_needs_a_session_cookie(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    client.cookies.clear()

    response = client.post(f"/queues/{item_id}/assign/prepare", data={"employee_id": TARGET})

    assert response.status_code == 400
    assert "Oturum çerezi yok." in response.text
    _unchanged(session_factory, item_id)


def test_a_failed_assignment_does_not_keep_the_confirmation_event(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    # Onay olayı ve atama tek işlemdedir: atama düşerse `USER_CONFIRMED` de geri alınır.
    broken = _synthetic_open_item(session_factory, "u_bozuk")
    token = _prepare(client, broken)

    response = _assign(client, broken, token)

    assert response.status_code == 409
    _unchanged(session_factory, broken)
    # Belirteç de tüketilmedi: aynı onaylanmış işlem yeniden denenince yine atamaya ulaşır (409).
    assert _assign(client, broken, token).status_code == 409


# --- atanamayan öğe, bilinmeyen kayıt -------------------------------------------------------------


def _steps(client: TestClient, queue_item_id: int, employee_id: str = TARGET) -> list[Any]:
    return [
        client.get(f"/queues/{queue_item_id}/assign/employees", params={"q": "kayitli"}),
        client.get(f"/queues/{queue_item_id}/assign/confirm", params={"employee_id": employee_id}),
        client.post(f"/queues/{queue_item_id}/assign/prepare", data={"employee_id": employee_id}),
        client.post(
            f"/queues/{queue_item_id}/assign",
            data={"employee_id": employee_id, "confirmation": "1.x"},
        ),
    ]


def test_every_step_refuses_an_item_without_a_type(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    queue_item_id = _queued_item(session_factory, layout, unknown=True)

    for response in _steps(client, queue_item_id):
        assert response.status_code == 409
        assert TYPELESS_NOTE in response.text
    _unchanged(session_factory, queue_item_id)


def test_every_step_refuses_a_superseded_item(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    with session_factory() as session:
        upload = _upload(session)
        old_plan, _new_plan = _plan(session, upload, 1), _plan(session, upload, 2)
        superseded = _queue_item(
            session, upload, old_plan, QueueKind.UNRESOLVED, payload=_payload(1, [0], slug=PERMIT)
        ).id
        session.commit()

    for response in _steps(client, superseded):
        assert response.status_code == 409
        assert SUPERSEDED_NOTE in response.text
    _unchanged(session_factory, superseded)


def test_every_step_reports_a_missing_item(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    for response in _steps(client, item_id + 100):
        assert response.status_code == 404
        assert QUEUE_ITEM_NOT_FOUND in response.text
    _unchanged(session_factory, item_id)


def test_an_unknown_employee_is_not_found(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    confirm = client.get(f"/queues/{item_id}/assign/confirm", params={"employee_id": "E9999"})
    prepare = client.post(f"/queues/{item_id}/assign/prepare", data={"employee_id": "E9999"})

    for response in (confirm, prepare):
        assert response.status_code == 404
        assert ASSIGNEE_NOT_FOUND in response.text
    _unchanged(session_factory, item_id)


def test_missing_employee_field_is_rejected(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    token = _prepare(client, item_id)

    response = client.post(f"/queues/{item_id}/assign", data={"confirmation": token})

    assert response.status_code == 422
    _unchanged(session_factory, item_id)


def test_assignment_steps_require_a_session(app: FastAPI, item_id: int) -> None:
    app.dependency_overrides.pop(get_current_user)  # oturumsuz istemci
    anonymous = TestClient(app)
    requests = [
        ("GET", f"/queues/{item_id}/assign/employees?q=kayitli"),
        ("GET", f"/queues/{item_id}/assign/confirm?employee_id={TARGET}"),
        ("POST", f"/queues/{item_id}/assign/prepare"),
        ("POST", f"/queues/{item_id}/assign"),
    ]
    for method, path in requests:
        response = anonymous.request(method, path, follow_redirects=False)
        assert response.status_code == 303, (method, path)
        assert response.headers["location"].startswith("/login?next="), (method, path)
