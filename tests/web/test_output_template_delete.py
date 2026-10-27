"""15.1.5 — arşivdeki hazır şablonu kalıcı silme (PLAN.md §D134 a, c, d, e).

Şablon panelden yüklenir ve arşivlenir (gerçek dosya ve sayfa önizlemeleri). Silme iki aşamalıdır;
önce dosyalar (`_sablonlar/<id>/` ve `cache/previews` karşılığı), sonra kayıt: alan haritası gider,
satır `deleted` iskeleti olarak kalır (erişim logu ona bağlıdır). Üretilmiş belgesi olan şablon
silinmez. Belgeler sentetiktir.

Yalnız `TestClient`: tarayıcıda çizim görülmedi."""

from __future__ import annotations

import re
from html import unescape

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AccessAction,
    AccessLog,
    Employee,
    Event,
    GeneratedDocument,
    OutputTemplate,
    OutputTemplateMap,
)
from app.events import EventType
from app.storage import DataLayout
from app.web.access import record_access
from app.web.auth import SESSION_COOKIE, PanelUser, get_current_user
from app.web.routers.output_templates import provider_available
from tests.fixtures.gen import make_pdf_bytes
from tests.web.conftest import SIGNED_IN
from tests.web.flash import flashed

BASE = "/output-templates"
FIRST = "Work contract şablonunu kalıcı olarak silmek üzeresiniz. Emin misiniz?"


@pytest.fixture(autouse=True)
def _setup(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[provider_available] = lambda: False
    client.cookies.set(SESSION_COOKIE, "oturum-bir")


def _template(client: TestClient, *, archived: bool = True) -> int:
    response = client.post(
        BASE,
        data={"name": "Work contract", "description": ""},
        files={"file": ("contract.pdf", make_pdf_bytes(), "application/pdf")},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    template_id = int(re.fullmatch(rf"{BASE}/(\d+)", response.headers["location"]).group(1))
    if archived:
        assert client.post(f"{BASE}/{template_id}/archive").status_code in (200, 303)
    return template_id


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match, html
    return match.group(1)


def _events(session_factory: sessionmaker[Session], kind: EventType) -> list[Event]:
    with session_factory() as session:
        return list(session.scalars(select(Event).where(Event.type == kind.value)))


def test_an_archived_template_is_deleted_files_first_and_its_row_stays_a_skeleton(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    template_id = _template(client)
    with session_factory() as session:
        session.add(OutputTemplateMap(template_id=template_id, version=1, json={}, map_hash="h"))
        record_access(
            session, user_id=SIGNED_IN.id, template_id=template_id, action=AccessAction.DOWNLOAD
        )
        session.commit()
    assert client.get(f"{BASE}/{template_id}/pages/0/previews/small").status_code == 200
    cached = layout.preview_cache / "template-pages"
    assert any(cached.iterdir())
    target = f"{BASE}/{template_id}/delete"

    listing = client.get(f"{BASE}?status=archived").text
    assert f'method="get" action="{target}/confirm"' in listing
    assert f'action="{target}/confirm"' in client.get(f"{BASE}/{template_id}").text
    first = client.get(f"{target}/confirm")
    assert first.status_code == 200
    assert FIRST in unescape(first.text)
    second = client.post(f"{target}/prepare")
    assert "geri alınamaz" in unescape(second.text)
    done = client.post(target, data={"confirmation": _token(second.text)}, follow_redirects=False)

    assert done.status_code == 303
    assert done.headers["location"] == f"{BASE}?status=archived"
    assert flashed(done) == ("templates.deleted", {})
    assert not layout.template_dir(template_id).exists()
    assert not any(cached.iterdir())
    with session_factory() as session:
        row = session.get_one(OutputTemplate, template_id)
        assert (row.status, row.file_path, row.deleted_by) == (
            "deleted",
            None,
            SIGNED_IN.username,
        )
        assert session.scalar(select(func.count()).select_from(OutputTemplateMap)) == 0
        assert session.scalar(select(func.count()).select_from(AccessLog)) == 1
    (event,) = _events(session_factory, EventType.OUTPUT_TEMPLATE_DELETED)
    assert event.actor == SIGNED_IN.username
    assert event.data_json["template_id"] == template_id
    assert event.data_json["page_count"] == 1 and event.data_json["map_count"] == 1
    assert client.get(f"{BASE}/{template_id}").status_code == 404
    assert "Work contract" not in client.get(f"{BASE}?status=archived").text
    # Ad ve dosya yeniden yüklenebilir.
    assert _template(client, archived=False) != template_id


def test_an_active_template_is_not_deleted(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    template_id = _template(client, archived=False)

    assert client.get(f"{BASE}/{template_id}/delete/confirm").status_code == 409
    refused = client.post(f"{BASE}/{template_id}/delete/prepare")

    assert refused.status_code == 409
    assert "Yalnız arşivdeki şablon silinir" in refused.text
    assert client.get(f"{BASE}/9999/delete/confirm").status_code == 404
    assert layout.template_dir(template_id).is_dir()
    assert _events(session_factory, EventType.OUTPUT_TEMPLATE_DELETED) == []


def test_a_template_with_generated_documents_is_not_deleted_and_says_why(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    template_id = _template(client)
    with session_factory() as session:
        session.add(
            Employee(id="E0001", folder_name="Test_Kisi_E0001", given_names="Test", surname="Kisi")
        )
        template_map = OutputTemplateMap(template_id=template_id, version=1, json={}, map_hash="h")
        session.add(template_map)
        session.flush()
        session.add(
            GeneratedDocument(
                employee_id="E0001",
                template_id=template_id,
                map_id=template_map.id,
                path="Employees/Test_Kisi_E0001/Uretilen/Test_Kisi-Work-contract.pdf",
                filled_fields_json=[],
                missing_fields_json=[],
                generated_by="ik",
            )
        )
        session.commit()

    page = client.get(f"{BASE}/{template_id}/delete/confirm")
    token = client.post(f"{BASE}/{template_id}/delete", data={"confirmation": "x"})

    assert page.status_code == token.status_code == 409
    assert "Bu şablondan 1 üretilmiş belge var" in unescape(page.text)
    assert layout.template_dir(template_id).is_dir()
    with session_factory() as session:
        assert session.get_one(OutputTemplate, template_id).status == "archived"
        assert session.scalar(select(func.count()).select_from(GeneratedDocument)) == 1


def test_a_missing_token_deletes_nothing_and_a_reader_has_no_button(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    template_id = _template(client)
    target = f"{BASE}/{template_id}/delete"

    assert client.post(target).status_code == 400
    app.dependency_overrides[get_current_user] = lambda: PanelUser(
        id=SIGNED_IN.id, username=SIGNED_IN.username, role="user"
    )
    assert "/delete/confirm" not in client.get(f"{BASE}?status=archived").text
    assert "/delete/confirm" not in client.get(f"{BASE}/{template_id}").text
    assert client.get(f"{target}/confirm").status_code == 403
    assert client.post(target, data={"confirmation": "x"}).status_code == 403
    assert layout.template_dir(template_id).is_dir()
    assert _events(session_factory, EventType.OUTPUT_TEMPLATE_DELETED) == []


def test_when_a_file_cannot_be_deleted_the_record_stays_and_the_delete_can_be_retried(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template_id = _template(client)
    target = f"{BASE}/{template_id}/delete"
    token = _token(client.post(f"{target}/prepare").text)

    def locked(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("kilitli")

    monkeypatch.setattr("app.output_templates.service.shutil.rmtree", locked)
    failed = client.post(target, data={"confirmation": token})

    assert failed.status_code == 500
    assert "Şablonun dosyaları silinemedi" in unescape(failed.text)
    with session_factory() as session:
        assert session.get_one(OutputTemplate, template_id).status == "archived"
    assert _events(session_factory, EventType.OUTPUT_TEMPLATE_DELETED) == []

    monkeypatch.undo()
    retried = client.post(target, data={"confirmation": token}, follow_redirects=False)
    assert retried.status_code == 303
    assert not layout.template_dir(template_id).exists()
