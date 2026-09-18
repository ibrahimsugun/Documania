"""08.2.1 — `POST /api/queue/{id}/assign`: kuyruk öğesini çalışana atama ve 08.4.1 —
`POST /api/queue/documents/{id}/archive`: belgeyi arşive taşıma (K16, §20.6).

Kuyruk öğesi gerçek planlayıcıdan (06.1) ve kuyruğa yönlendirmeden (08.1) geçer; sayfa analizleri
saklanmış sentetik yanıtlardır, sağlayıcı çağrılmaz. İki aşamalı onay (10.8.1) henüz yok: onaylanmış
kullanıcı adı bağımlılığı testte değiştirilir.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import app.ai.provider as provider_module
from app.catalog import import_catalog
from app.db.models import Document, DocumentStatus, Employee, Event, KnownDocumentType, QueueItem
from app.events import EventType
from app.pipeline.plan import create_plan, read_plan
from app.pipeline.route import route_queue_item
from app.storage import DataLayout, sha256_file
from app.web.routers.queue import get_confirmed_actor
from tests.pipeline.test_orchestrate import _forbid_ai
from tests.pipeline.test_plan import CATALOG, MODEL, PERMIT, RECORDINGS, _page, _pdf
from tests.pipeline.test_plan import _upload as _upload_with_analyses

TARGET = "E0042"
TARGET_FOLDER = "Kayitli_Kisi_E0042"
ACTOR = "ik.ayse"


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


@pytest.fixture
def confirmed(app: FastAPI) -> None:
    # 10.8.1'in yerine: iki aşamalı onayı tamamlamış kullanıcı.
    app.dependency_overrides[get_confirmed_actor] = lambda: ACTOR


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


def test_assignment_without_two_step_confirmation_changes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    # K16: onay mekanizması (10.8.1) bağlanana kadar manuel işlem yapılmaz.
    queue_item_id = _queued_item(session_factory, layout)

    response = client.post(f"/api/queue/{queue_item_id}/assign", json={"employee_id": TARGET})

    assert response.status_code == 503
    assert "İki aşamalı onay" in response.json()["detail"]
    _unchanged(session_factory, queue_item_id)
    assert list(layout.ready_dir(TARGET_FOLDER).iterdir()) == []


@pytest.mark.usefixtures("confirmed")
def test_assignment_commits_the_output_without_calling_ai(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue_item_id = _queued_item(session_factory, layout)
    _refuse_provider(monkeypatch)

    response = client.post(f"/api/queue/{queue_item_id}/assign", json={"employee_id": TARGET})

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


@pytest.mark.usefixtures("confirmed")
def test_second_assignment_is_a_conflict(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    queue_item_id = _queued_item(session_factory, layout)
    assert (
        client.post(f"/api/queue/{queue_item_id}/assign", json={"employee_id": TARGET}).status_code
        == 200
    )

    response = client.post(f"/api/queue/{queue_item_id}/assign", json={"employee_id": TARGET})

    assert response.status_code == 409
    assert "zaten çözülmüş" in response.json()["detail"]
    with session_factory() as session:
        assert len(session.scalars(select(Document)).all()) == 1


@pytest.mark.usefixtures("confirmed")
def test_item_that_cannot_be_assigned_is_a_conflict_and_commits_nothing(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    queue_item_id = _queued_item(session_factory, layout, unknown=True)

    response = client.post(f"/api/queue/{queue_item_id}/assign", json={"employee_id": TARGET})

    assert response.status_code == 409
    assert "belge türü belirlenmedi" in response.json()["detail"]
    _unchanged(session_factory, queue_item_id)


@pytest.mark.usefixtures("confirmed")
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

    response = client.post(
        f"/api/queue/{queue_item_id + path_offset}/assign", json={"employee_id": employee_id}
    )

    assert response.status_code == 404
    assert detail in response.json()["detail"]
    _unchanged(session_factory, queue_item_id)


@pytest.mark.usefixtures("confirmed")
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

    response = client.post(f"/api/queue/{queue_item_id}/assign", json=payload)

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


def test_archive_without_two_step_confirmation_changes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    document_id = _archivable_document(session_factory, layout)

    response = client.post(f"/api/queue/documents/{document_id}/archive")

    assert response.status_code == 503
    assert "İki aşamalı onay" in response.json()["detail"]
    with session_factory() as session:
        document = session.get_one(Document, document_id)
        assert document.status == DocumentStatus.ACTIVE.value
        assert session.scalars(select(Event).where(Event.type == EventType.ARCHIVED)).all() == []


@pytest.mark.usefixtures("confirmed")
def test_archive_moves_the_document_and_updates_its_status(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    document_id = _archivable_document(session_factory, layout)

    response = client.post(f"/api/queue/documents/{document_id}/archive")

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


@pytest.mark.usefixtures("confirmed")
def test_second_archive_is_a_conflict(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    document_id = _archivable_document(session_factory, layout)
    assert client.post(f"/api/queue/documents/{document_id}/archive").status_code == 200

    response = client.post(f"/api/queue/documents/{document_id}/archive")

    assert response.status_code == 409
    assert "yalnız etkin belge arşivlenir" in response.json()["detail"]


@pytest.mark.usefixtures("confirmed")
def test_unknown_document_is_not_found(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    document_id = _archivable_document(session_factory, layout)

    response = client.post(f"/api/queue/documents/{document_id + 100}/archive")

    assert response.status_code == 404
    assert "Belge bulunamadı" in response.json()["detail"]
