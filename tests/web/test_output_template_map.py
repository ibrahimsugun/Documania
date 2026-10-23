"""15.1.3 — Alan haritası önizlemesi ve onayı: kutular sayfa görüntüsünün üstünde, doldurulabilir
kutuda açılır liste, imza kutusu seçimsiz; onay atamaları doğrular, değişen atamayı yeni sürüm
olarak yazar, şablonu hazır yapar ve olay kaydeder; bağlı kutu yoksa 422; Kullanıcı yalnız onaylı
haritayı salt okunur görür ve onaylayamaz (PLAN.md §D123 c, m).

Harita işçi yerine doğrudan `store_map` ile yazılır (incelemenin kendisi 15.1.2'nin testindedir)."""

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.schemas import TemplateField, TemplateFieldMap
from app.db.models import Event, OutputTemplate, OutputTemplateMap, UserRole
from app.events import EventType
from app.output_templates.examine import store_map
from app.web.auth import PanelUser, get_current_user
from app.web.routers.output_templates import provider_available
from tests.fixtures.gen import make_pdf_bytes
from tests.web.conftest import SIGNED_IN
from tests.web.flash import flashed

READER = PanelUser(SIGNED_IN.id, SIGNED_IN.username, UserRole.USER.value)
FIELDS = (
    TemplateField(
        field_id="f1",
        page=0,
        box=(0.3, 0.1, 0.8, 0.15),
        kind="text",
        label_text="Ime i prezime",
        source="full_name",
        font_size=10,
        max_chars=40,
    ),
    TemplateField(
        field_id="f2",
        page=0,
        box=(0.3, 0.2, 0.6, 0.25),
        kind="date",
        label_text="Datum rodjenja",
        source="date_of_birth",
        font_size=10,
        max_chars=10,
    ),
    TemplateField(field_id="f3", page=0, box=(0.6, 0.8, 0.9, 0.9), kind="signature"),
)


@pytest.fixture(autouse=True)
def _provider_configured(app: FastAPI) -> None:
    app.dependency_overrides[provider_available] = lambda: True


@pytest.fixture
def template_id(client: TestClient, session_factory: sessionmaker[Session]) -> int:
    response = client.post(
        "/output-templates",
        data={"name": "Work contract", "description": ""},
        files={"file": ("contract.pdf", make_pdf_bytes(1), "application/pdf")},
        follow_redirects=False,
    )
    template_id = int(re.fullmatch(r"/output-templates/(\d+)", response.headers["location"])[1])
    with session_factory() as session:
        template = session.get_one(OutputTemplate, template_id)
        template.examine_requested_at = None
        store_map(session, template, TemplateFieldMap(fields=FIELDS, notes=""), model="m-1")
        session.commit()
    return template_id


def _approve(client: TestClient, template_id: int, version: int = 1, **sources: str):
    data = {"source-f1": "full_name", "source-f2": "date_of_birth"} | {
        f"source-{key}": value for key, value in sources.items()
    }
    return client.post(
        f"/output-templates/{template_id}/maps/{version}/approve",
        data=data,
        follow_redirects=False,
    )


def _maps(session_factory: sessionmaker[Session], template_id: int) -> list[OutputTemplateMap]:
    with session_factory() as session:
        query = select(OutputTemplateMap).where(OutputTemplateMap.template_id == template_id)
        return list(session.scalars(query.order_by(OutputTemplateMap.version)))


def _events(session_factory: sessionmaker[Session]) -> list[Event]:
    with session_factory() as session:
        return list(session.scalars(select(Event)))


def _status(session_factory: sessionmaker[Session], template_id: int) -> str:
    with session_factory() as session:
        return session.get_one(OutputTemplate, template_id).status


def test_preview_draws_the_boxes_with_selects_and_a_locked_signature(
    client: TestClient, template_id: int
) -> None:
    page = client.get(f"/output-templates/{template_id}").text

    assert 'class="map-boxes"' in page
    # Kutular normalize kutunun sayfa görüntüsüyle çarpımıdır; koordinatlar değişmeden gelir.
    width, height = map(int, re.search(r'viewBox="0 0 (\d+) (\d+)"', page).groups())
    assert f'x="{round(0.3 * width, 1)}" y="{round(0.1 * height, 1)}"' in page
    assert 'class="map-box map-box-locked" href="#map-row-f3"' in page
    assert '<label for="map-source-f1" translate="no">Ime i prezime</label>' in page
    assert '<option value="full_name" selected>' in page
    assert '<option value="unassigned">Boş bırak</option>' in page
    assert 'name="source-f3"' not in page
    assert f'action="/output-templates/{template_id}/maps/1/approve"' in page


def test_approving_unchanged_assignments_approves_the_version_and_readies_the_template(
    client: TestClient, session_factory: sessionmaker[Session], template_id: int
) -> None:
    response = _approve(client, template_id)

    assert response.status_code == 303
    assert flashed(response) == ("templates.map_approved", {"version": 1})
    (row,) = _maps(session_factory, template_id)
    assert (row.approved_by, row.approved_at is not None) == (SIGNED_IN.username, True)
    assert _status(session_factory, template_id) == "ready"
    with session_factory() as session:
        event = session.scalar(select(Event).where(Event.type == "TEMPLATE_MAP_APPROVED"))
        assert event.actor == SIGNED_IN.username
        assert event.data_json == {
            "template_id": template_id,
            "version": 1,
            "based_on": 1,
            "field_count": 2,
            "bound_count": 2,
            "changed_count": 0,
        }
    assert flashed(_approve(client, template_id)) == ("templates.map_unchanged", {})


def test_changed_assignments_open_a_new_approved_version_and_keep_the_old_one(
    client: TestClient, session_factory: sessionmaker[Session], template_id: int
) -> None:
    response = _approve(client, template_id, f2="unassigned")

    assert flashed(response) == ("templates.map_approved_edited", {"count": 1, "version": 2})
    first, second = _maps(session_factory, template_id)
    assert first.approved_at is None
    assert [f["source"] for f in second.json["fields"]] == ["full_name", "unassigned", None]
    assert [f["box"] for f in second.json["fields"]] == [f["box"] for f in first.json["fields"]]
    assert (second.model, second.approved_by) == ("m-1", SIGNED_IN.username)
    assert second.map_hash != first.map_hash
    # Eski sürüm artık son sürüm değil: onu onaylamak 409.
    assert _approve(client, template_id, version=1).status_code == 409
    page = client.get(f"/output-templates/{template_id}").text
    assert 'class="map-box map-box-unassigned" href="#map-row-f2"' in page


def test_a_map_with_no_bound_field_is_refused_with_the_choices_kept(
    client: TestClient, session_factory: sessionmaker[Session], template_id: int
) -> None:
    response = _approve(client, template_id, f1="unassigned", f2="unassigned")

    assert response.status_code == 422
    assert "en az bir kutu bir profil alanına bağlı olmalı" in response.text
    assert '<option value="unassigned" selected>' in response.text
    assert len(_maps(session_factory, template_id)) == 1
    assert _status(session_factory, template_id) == "draft"


def test_unknown_or_locked_assignments_are_refused(
    client: TestClient, session_factory: sessionmaker[Session], template_id: int
) -> None:
    assert _approve(client, template_id, f1="salary").status_code == 422
    assert _approve(client, template_id, f3="full_name").status_code == 422
    assert _approve(client, template_id, version=9).status_code == 404
    assert _status(session_factory, template_id) == "draft"


def test_a_reader_sees_only_the_approved_map_read_only_and_cannot_approve(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session], template_id: int
) -> None:
    app.dependency_overrides[get_current_user] = lambda: READER

    before = client.get(f"/output-templates/{template_id}").text
    assert "Henüz onaylı alan haritası yok" in before
    assert 'class="map-boxes"' not in before
    assert _approve(client, template_id).status_code == 403

    app.dependency_overrides[get_current_user] = lambda: SIGNED_IN
    assert _approve(client, template_id).status_code == 303
    app.dependency_overrides[get_current_user] = lambda: READER
    after = client.get(f"/output-templates/{template_id}").text
    assert 'class="map-boxes"' in after
    assert "<select" not in after
    assert "/approve" not in after
    assert _status(session_factory, template_id) == "ready"


def test_an_archived_template_is_not_approved(
    client: TestClient, session_factory: sessionmaker[Session], template_id: int
) -> None:
    client.post(f"/output-templates/{template_id}/archive")

    assert _approve(client, template_id).status_code == 409
    assert "<select" not in client.get(f"/output-templates/{template_id}").text
    assert EventType.TEMPLATE_MAP_APPROVED.value not in {e.type for e in _events(session_factory)}
