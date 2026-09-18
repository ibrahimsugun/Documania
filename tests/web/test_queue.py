"""08.2.1 — `POST /api/queue/{id}/assign`: kuyruk öğesini çalışana atama ve 08.4.1 —
`POST /api/queue/documents/{id}/archive`: belgeyi arşive taşıma (K16, §20.6).

Kuyruk öğesi gerçek planlayıcıdan (06.1) ve kuyruğa yönlendirmeden (08.1) geçer; sayfa analizleri
saklanmış sentetik yanıtlardır, sağlayıcı çağrılmaz. İki aşamalı onay 10.8.1'in tek kullanımlık
belirtecidir: hazırlık isteği (`.../prepare`) belirteci verir, asıl istek onu `X-Confirmation-Token`
başlığında taşır. Oturum bağımlılığı testte geçersiz kılındığı için çerez elle konur.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import app.ai.provider as provider_module
import app.web.confirm as confirm
from app.catalog import import_catalog
from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    Event,
    KnownDocumentType,
    QueueItem,
    utcnow,
)
from app.events import EventType
from app.pipeline.plan import create_plan, read_plan
from app.pipeline.route import route_queue_item
from app.storage import DataLayout, sha256_file
from app.web.auth import SESSION_COOKIE, PanelUser, get_current_user
from app.web.confirm import CONFIRMATION_HEADER, CONFIRMATION_REFUSED, Operation
from app.web.routers.queue import (
    RESOLVED_NOTE,
    TYPELESS_NOTE,
    archive_subject,
    assignment_subject,
)
from tests.pipeline.test_orchestrate import _forbid_ai
from tests.pipeline.test_plan import CATALOG, MODEL, PERMIT, RECORDINGS, _page, _pdf
from tests.pipeline.test_plan import _upload as _upload_with_analyses
from tests.web.conftest import SESSION, issue_token

TARGET = "E0042"
TARGET_FOLDER = "Kayitli_Kisi_E0042"
ACTOR = "ik.ayse"
USER = PanelUser(id=7, username=ACTOR, role="admin")


def _queued_item(
    session_factory: sessionmaker[Session], layout: DataLayout, *, unknown: bool = False
) -> int:
    """Kuyrukta tek öğesi olan parti (Unreadable çalışma izni ya da bilinmeyen tür) ve atanacak
    çalışan; commit edilir, kuyruk kaydının kimliği döner."""
    with session_factory() as session:
        import_catalog(session, CATALOG)
        if unknown:
            text = (RECORDINGS / "s14_peruvian_diploma" / "0.json").read_text(encoding="utf-8")
            page = json.loads(text)
        else:
            page = _page(PERMIT, illegible=("surname",))
        upload = _upload_with_analyses(session, layout, _pdf(page))
        plan = create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)
        (item,) = read_plan(plan).items
        queue_item = route_queue_item(session, layout, plan, item).queue_item
        session.add(
            Employee(id=TARGET, folder_name=TARGET_FOLDER, given_names="Kayitli", surname="Kisi")
        )
        session.commit()
        layout.ensure_employee_tree(TARGET_FOLDER)
        return queue_item.id


@pytest.fixture(autouse=True)
def signed_in(app: FastAPI, client: TestClient) -> None:
    # Oturumu açık kullanıcı `ACTOR`; belirteç oturum çerezine bağlıdır (10.8.1).
    app.dependency_overrides[get_current_user] = lambda: USER
    client.cookies.set(SESSION_COOKIE, SESSION)


def _prepare(client: TestClient, path: str, **body: Any) -> dict[str, Any]:
    response = client.post(f"{path}/prepare", json=body or None)
    assert response.status_code == 200, response.text
    prepared: dict[str, Any] = response.json()
    return prepared


def _assign(client: TestClient, queue_item_id: int, token: str | None) -> Any:
    headers = {CONFIRMATION_HEADER: token} if token is not None else {}
    return client.post(
        f"/api/queue/{queue_item_id}/assign", json={"employee_id": TARGET}, headers=headers
    )


def _confirmed_assign(client: TestClient, queue_item_id: int) -> Any:
    """Hazırlık + belirteçle atama (iki onay tamamlanmış)."""
    prepared = _prepare(client, f"/api/queue/{queue_item_id}/assign", employee_id=TARGET)
    return _assign(client, queue_item_id, prepared["confirmation"])


def _user_confirmed(session: Session) -> list[Event]:
    return list(
        session.scalars(
            select(Event).where(Event.type == EventType.USER_CONFIRMED).order_by(Event.id)
        )
    )


def _refuse_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    def _create(*args: object, **kwargs: object) -> object:
        raise AssertionError("atama yapay zekâ sağlayıcısı kurmamalı")

    monkeypatch.setattr(provider_module, "create_provider", _create)
    _forbid_ai(monkeypatch)


def _unchanged(session_factory: sessionmaker[Session], queue_item_id: int) -> None:
    with session_factory() as session:
        queue_item = session.get_one(QueueItem, queue_item_id)
        assert (queue_item.resolved_at, queue_item.resolved_by) == (None, None)
        assert session.scalars(select(Document)).all() == []
        assert (
            session.scalars(select(Event).where(Event.type == EventType.MANUAL_ASSIGN)).all() == []
        )


@pytest.mark.parametrize("token", [None, "", "uydurma-belirtec"], ids=repr)
def test_assignment_without_a_valid_token_changes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    token: str | None,
) -> None:
    # K16 / 10.8.1: belirteçsiz (ya da tanınmayan belirteçle) istek reddedilir, hiçbir şey olmaz.
    queue_item_id = _queued_item(session_factory, layout)

    response = _assign(client, queue_item_id, token)

    assert response.status_code == 400
    assert response.json()["detail"] == CONFIRMATION_REFUSED
    _unchanged(session_factory, queue_item_id)
    assert list(layout.ready_dir(TARGET_FOLDER).iterdir()) == []
    with session_factory() as session:
        assert _user_confirmed(session) == []


def test_prepare_gives_both_texts_and_a_token_and_changes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    queue_item_id = _queued_item(session_factory, layout)

    before = utcnow()
    prepared = _prepare(client, f"/api/queue/{queue_item_id}/assign", employee_id=TARGET)

    assert prepared["operation"] == "assign"
    assert prepared["first_confirmation"] == (
        "Bu belgeyi Kayitli Kisi çalışanına atamak üzeresiniz. Emin misiniz?"
    )
    assert prepared["second_confirmation"] == (
        "Bu işlem sistemdeki belge organizasyonunu değiştirecektir. Son kararınız mı?"
    )
    assert prepared["confirmation"]
    expires = datetime.fromisoformat(prepared["expires_at"])
    assert before + confirm.CONFIRMATION_TTL <= expires <= utcnow() + confirm.CONFIRMATION_TTL
    _unchanged(session_factory, queue_item_id)


def test_assignment_commits_the_output_without_calling_ai(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue_item_id = _queued_item(session_factory, layout)
    _refuse_provider(monkeypatch)

    response = _confirmed_assign(client, queue_item_id)

    assert response.status_code == 200
    body = response.json()
    with session_factory() as session:
        queue_item = session.get_one(QueueItem, queue_item_id)
        (document,) = session.scalars(select(Document)).all()
        (manual,) = session.scalars(
            select(Event).where(Event.type == EventType.MANUAL_ASSIGN)
        ).all()
        (upload_file,) = queue_item.upload.files
        assert body == {
            "queue_item_id": queue_item_id,
            "upload_id": queue_item.upload_id,
            "plan_id": queue_item.plan_id,
            "plan_item_id": "i1",
            "kind": "unreadable",
            "employee_id": TARGET,
            "document_id": document.id,
            "document_type_slug": PERMIT,
            "operation": "passthrough",
            "resolved_at": body["resolved_at"],
            "resolved_by": ACTOR,
        }
        assert queue_item.resolved_at == datetime.fromisoformat(body["resolved_at"])
        assert queue_item.resolved_by == ACTOR
        assert (manual.actor, manual.document_id) == (ACTOR, document.id)
        assert manual.employee_id == TARGET
        output = layout.resolve(document.path)
        assert output == layout.ready_dir(TARGET_FOLDER) / "Kayitli_Kisi-Work-Permit.pdf"
        assert sha256_file(output) == upload_file.sha256
        # §20.6.1: önce onay olayı (kullanıcı adı, işlem, hedef, iki zaman), sonra atama.
        (confirmed,) = _user_confirmed(session)
        assert confirmed.id < manual.id and confirmed.actor == ACTOR
        assert confirmed.upload_id == queue_item.upload_id
        data = confirmed.data_json
        assert data is not None
        assert data["operation"] == "assign"
        assert data["target"] == {"queue_item_id": queue_item_id, "employee_id": TARGET}
        first = datetime.fromisoformat(data["first_confirmed_at"])
        second = datetime.fromisoformat(data["second_confirmed_at"])
        assert first <= second <= utcnow()


def test_the_same_token_twice_is_refused_and_a_new_preparation_is_a_conflict(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    queue_item_id = _queued_item(session_factory, layout)
    prepared = _prepare(client, f"/api/queue/{queue_item_id}/assign", employee_id=TARGET)
    assert _assign(client, queue_item_id, prepared["confirmation"]).status_code == 200

    replay = _assign(client, queue_item_id, prepared["confirmation"])
    again = client.post(f"/api/queue/{queue_item_id}/assign/prepare", json={"employee_id": TARGET})

    assert replay.status_code == 400
    assert replay.json()["detail"] == CONFIRMATION_REFUSED
    assert again.status_code == 409
    assert again.json()["detail"] == RESOLVED_NOTE
    with session_factory() as session:
        assert len(session.scalars(select(Document)).all()) == 1
        assert len(_user_confirmed(session)) == 1


def test_an_expired_token_is_refused(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue_item_id = _queued_item(session_factory, layout)
    prepared = _prepare(client, f"/api/queue/{queue_item_id}/assign", employee_id=TARGET)
    later = utcnow() + confirm.CONFIRMATION_TTL + timedelta(seconds=5)
    monkeypatch.setattr(confirm, "utcnow", lambda: later)

    response = _assign(client, queue_item_id, prepared["confirmation"])

    assert response.status_code == 400
    _unchanged(session_factory, queue_item_id)


def test_a_token_of_another_employee_or_session_is_refused(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    queue_item_id = _queued_item(session_factory, layout)
    other_employee = issue_token(
        session_factory, Operation.ASSIGN, assignment_subject(queue_item_id, "E0043"), user=USER
    )
    other_session = issue_token(
        session_factory,
        Operation.ASSIGN,
        assignment_subject(queue_item_id, TARGET),
        cookie="oturum-iki",
        user=USER,
    )

    for token in (other_employee, other_session):
        response = _assign(client, queue_item_id, token)
        assert response.status_code == 400, response.text
    _unchanged(session_factory, queue_item_id)


def test_item_that_cannot_be_assigned_is_a_conflict_and_commits_nothing(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    queue_item_id = _queued_item(session_factory, layout, unknown=True)
    # Hazırlık türsüz öğeyi reddeder; hazırlığı atlayan belirteçle de çekirdek atamaz.
    prepare = client.post(
        f"/api/queue/{queue_item_id}/assign/prepare", json={"employee_id": TARGET}
    )
    token = issue_token(
        session_factory, Operation.ASSIGN, assignment_subject(queue_item_id, TARGET), user=USER
    )

    response = _assign(client, queue_item_id, token)

    assert prepare.status_code == 409
    assert prepare.json()["detail"] == TYPELESS_NOTE
    assert response.status_code == 409
    assert "belge türü belirlenmedi" in response.json()["detail"]
    _unchanged(session_factory, queue_item_id)
    with session_factory() as session:
        # Atama düştü: onay olayı da geri alındı, belirteç tüketilmedi.
        assert _user_confirmed(session) == []
    assert _assign(client, queue_item_id, token).status_code == 409


@pytest.mark.parametrize(
    ("path_offset", "employee_id", "detail"),
    [(100, TARGET, "Kuyruk öğesi bulunamadı"), (0, "E9999", "Çalışan bulunamadı")],
    ids=["queue-item", "employee"],
)
def test_unknown_queue_item_or_employee_is_not_found(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    path_offset: int,
    employee_id: str,
    detail: str,
) -> None:
    queue_item_id = _queued_item(session_factory, layout)
    target = queue_item_id + path_offset
    token = issue_token(
        session_factory, Operation.ASSIGN, assignment_subject(target, employee_id), user=USER
    )

    prepare = client.post(f"/api/queue/{target}/assign/prepare", json={"employee_id": employee_id})
    response = client.post(
        f"/api/queue/{target}/assign",
        json={"employee_id": employee_id},
        headers={CONFIRMATION_HEADER: token},
    )

    for each in (prepare, response):
        assert each.status_code == 404
        assert detail in each.json()["detail"]
    _unchanged(session_factory, queue_item_id)


def test_prepare_needs_a_session_cookie(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    queue_item_id = _queued_item(session_factory, layout)
    client.cookies.clear()

    response = client.post(
        f"/api/queue/{queue_item_id}/assign/prepare", json={"employee_id": TARGET}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Oturum çerezi yok."


@pytest.mark.parametrize(
    "payload",
    [{}, {"employee_id": TARGET, "document_type_slug": PERMIT}],
    ids=["missing-employee", "unexpected-field"],
)
def test_malformed_request_is_rejected(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    payload: dict[str, str],
) -> None:
    # Atama yalnız sahibi seçer: tür ya da başka alan gövdeye girmez.
    queue_item_id = _queued_item(session_factory, layout)

    for path in ("assign/prepare", "assign"):
        response = client.post(f"/api/queue/{queue_item_id}/{path}", json=payload)
        assert response.status_code == 422
    _unchanged(session_factory, queue_item_id)


# --- 08.4.1: POST /api/queue/documents/{id}/archive -----------------------------------------

ARCHIVE_TYPE = "test_passport"


def _archivable_document(session_factory: sessionmaker[Session], layout: DataLayout) -> int:
    """Çalışanın `Hazir/`'ında fiziksel dosyası olan, etkin tek bir belge; commit edilir."""
    with session_factory() as session:
        session.add(
            Employee(id=TARGET, folder_name=TARGET_FOLDER, given_names="Kayitli", surname="Kisi")
        )
        session.add(
            KnownDocumentType(
                slug=ARCHIVE_TYPE,
                name="Test Passport",
                file_label="Passport",
                sides="single",
                direct=True,
                analyze=True,
                output_format="keep",
            )
        )
        session.flush()
        layout.ensure_employee_tree(TARGET_FOLDER)
        path = layout.ready_dir(TARGET_FOLDER) / "Kayitli_Kisi-Passport.pdf"
        path.write_bytes(b"belge icerigi")
        document = Document(
            employee_id=TARGET,
            type_slug=ARCHIVE_TYPE,
            path=layout.relative(path),
            format="pdf",
            source_refs_json=[{"file_id": 1, "pages": [0]}],
        )
        session.add(document)
        session.commit()
        return document.id


def _archive(client: TestClient, document_id: int, token: str | None) -> Any:
    headers = {CONFIRMATION_HEADER: token} if token is not None else {}
    return client.post(f"/api/queue/documents/{document_id}/archive", headers=headers)


def _confirmed_archive(client: TestClient, document_id: int) -> Any:
    prepared = _prepare(client, f"/api/queue/documents/{document_id}/archive")
    return _archive(client, document_id, prepared["confirmation"])


def _not_archived(session_factory: sessionmaker[Session], document_id: int) -> None:
    with session_factory() as session:
        document = session.get_one(Document, document_id)
        assert document.status == DocumentStatus.ACTIVE.value
        assert session.scalars(select(Event).where(Event.type == EventType.ARCHIVED)).all() == []
        assert _user_confirmed(session) == []


@pytest.mark.parametrize("token", [None, "uydurma-belirtec"], ids=repr)
def test_archive_without_two_step_confirmation_changes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    token: str | None,
) -> None:
    document_id = _archivable_document(session_factory, layout)

    response = _archive(client, document_id, token)

    assert response.status_code == 400
    assert response.json()["detail"] == CONFIRMATION_REFUSED
    _not_archived(session_factory, document_id)


def test_archive_prepare_gives_the_section_20_6_texts_and_archives_nothing(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    document_id = _archivable_document(session_factory, layout)

    prepared = _prepare(client, f"/api/queue/documents/{document_id}/archive")

    assert prepared["operation"] == "archive"
    assert prepared["first_confirmation"] == "Bu belgeyi arşive taşımak üzeresiniz. Emin misiniz?"
    assert prepared["second_confirmation"] == (
        "Belge çalışanın Hazır klasöründen çıkacaktır. Son kararınız mı?"
    )
    _not_archived(session_factory, document_id)


def test_an_assignment_token_does_not_archive(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    # Belirteç işleme bağlıdır: aynı kimlikli hedefin başka işlem belirteci geçmez.
    document_id = _archivable_document(session_factory, layout)
    foreign = issue_token(
        session_factory, Operation.ASSIGN, archive_subject(document_id), user=USER
    )

    response = _archive(client, document_id, foreign)

    assert response.status_code == 400
    _not_archived(session_factory, document_id)


def test_archive_moves_the_document_and_updates_its_status(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    document_id = _archivable_document(session_factory, layout)

    response = _confirmed_archive(client, document_id)

    assert response.status_code == 200
    body = response.json()
    with session_factory() as session:
        document = session.get_one(Document, document_id)
        (manual,) = session.scalars(select(Event).where(Event.type == EventType.ARCHIVED)).all()
        assert body == {
            "document_id": document_id,
            "employee_id": TARGET,
            "type_slug": ARCHIVE_TYPE,
            "path": document.path,
            "status": DocumentStatus.ARCHIVED.value,
            "archived_by": ACTOR,
            "archived_at": body["archived_at"],
        }
        assert document.status == DocumentStatus.ARCHIVED.value
        archived_path = layout.resolve(document.path)
        assert archived_path.read_bytes() == b"belge icerigi"
        assert archived_path.parent.parent == layout.archive
        assert list(layout.ready_dir(TARGET_FOLDER).iterdir()) == []
        assert (manual.actor, manual.document_id, manual.employee_id) == (
            ACTOR,
            document_id,
            TARGET,
        )
        (confirmed,) = _user_confirmed(session)
        assert confirmed.id < manual.id
        assert (confirmed.actor, confirmed.document_id, confirmed.employee_id) == (
            ACTOR,
            document_id,
            TARGET,
        )
        data = confirmed.data_json
        assert data is not None
        assert (data["operation"], data["target"]) == ("archive", {"document_id": document_id})
        first = datetime.fromisoformat(data["first_confirmed_at"])
        assert first <= datetime.fromisoformat(data["second_confirmed_at"]) <= utcnow()


def test_second_archive_is_a_conflict(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    document_id = _archivable_document(session_factory, layout)
    prepared = _prepare(client, f"/api/queue/documents/{document_id}/archive")
    assert _archive(client, document_id, prepared["confirmation"]).status_code == 200

    replay = _archive(client, document_id, prepared["confirmation"])
    again = client.post(f"/api/queue/documents/{document_id}/archive/prepare")
    token = issue_token(session_factory, Operation.ARCHIVE, archive_subject(document_id), user=USER)
    core = _archive(client, document_id, token)

    assert replay.status_code == 400
    for response in (again, core):
        assert response.status_code == 409
        assert "yalnız etkin belge arşivlenir" in response.json()["detail"]
    with session_factory() as session:
        assert len(_user_confirmed(session)) == 1


def test_unknown_document_is_not_found(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    document_id = _archivable_document(session_factory, layout) + 100
    token = issue_token(session_factory, Operation.ARCHIVE, archive_subject(document_id), user=USER)

    prepare = client.post(f"/api/queue/documents/{document_id}/archive/prepare")
    response = _archive(client, document_id, token)

    for each in (prepare, response):
        assert each.status_code == 404
        assert "Belge bulunamadı" in each.json()["detail"]
