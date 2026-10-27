"""15.1.1, 15.1.2, 15.1.4 — Hazır Şablonlar sekmesi: menü, liste ve durum süzgeci, yükleme (PDF,
görüntü kayıpsız sarılır, Word reddi, SHA-256 tekrarı, ad tekrarı), incelemeye alma ve listede
sebep, yeniden inceleme, arşiv/geri al, orijinali açma/indirme ve erişim kaydı, sayfa önizlemesi,
Kullanıcı'nın salt okunur görünümü (PLAN.md §D123).

Sağlayıcının ayarlı olup olmadığı ortama (`.env`) bağlı kalmasın diye `provider_available` her
testte ayarlı sayılır; ayarsız durumu kendi testi değiştirir."""

import io
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AccessAction,
    AccessLog,
    Document,
    Event,
    OutputTemplate,
    Upload,
    UserRole,
)
from app.events import EventType
from app.storage import DataLayout
from app.web.access import record_access
from app.web.auth import PanelUser, get_current_user
from app.web.routers.output_templates import provider_available
from app.web.templating import PANEL_MENU
from tests.fixtures.gen import make_docx_bytes, make_pdf_bytes
from tests.web.conftest import SIGNED_IN
from tests.web.flash import flashed, toasts

READER = PanelUser(SIGNED_IN.id, SIGNED_IN.username, UserRole.USER.value)


@pytest.fixture(autouse=True)
def _provider_configured(app: FastAPI) -> None:
    app.dependency_overrides[provider_available] = lambda: True


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 60), (200, 210, 220)).save(buffer, "PNG")
    return buffer.getvalue()


def _upload(
    client: TestClient,
    content: bytes,
    *,
    name: str = "Work contract",
    filename: str = "contract.pdf",
    mime: str = "application/pdf",
):
    return client.post(
        "/output-templates",
        data={"name": name, "description": "Two-page contract"},
        files={"file": (filename, content, mime)},
        follow_redirects=False,
    )


def _created_id(response) -> int:
    assert response.status_code == 303, response.text
    match = re.fullmatch(r"/output-templates/(\d+)", response.headers["location"])
    assert match, response.headers["location"]
    return int(match.group(1))


def _events(session_factory: sessionmaker[Session], *types: EventType) -> list[Event]:
    with session_factory() as session:
        rows = session.scalars(
            select(Event).where(Event.type.in_([t.value for t in types])).order_by(Event.id)
        )
        return list(rows)


def test_menu_lists_templates_after_document_groups() -> None:
    keys = [entry.key for entry in PANEL_MENU]
    assert keys.index("output_templates") == keys.index("document_groups") + 1
    assert PANEL_MENU[keys.index("output_templates")].path == "/output-templates"


def test_pdf_upload_stores_the_file_unchanged_with_previews_and_an_event(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    content = make_pdf_bytes(2)

    response = _upload(client, content)

    template_id = _created_id(response)
    assert flashed(response) == ("templates.uploaded", {"count": 2})
    with session_factory() as session:
        template = session.get_one(OutputTemplate, template_id)
        assert (template.status, template.page_count, template.file_label) == (
            "draft",
            2,
            "Work-contract",
        )
        assert template.uploaded_by == SIGNED_IN.username
        assert template.file_path == f"KnownDocuments/_sablonlar/{template_id}/sablon.pdf"
        # Şablon çalışan belgesi değildir: parti ve belge satırı açılmaz.
        assert session.scalar(select(func.count()).select_from(Upload)) == 0
        assert session.scalar(select(func.count()).select_from(Document)) == 0
    assert layout.template_original_path(template_id).read_bytes() == content
    assert layout.template_page_image_path(template_id, 1).is_file()
    (event,) = _events(session_factory, EventType.TEMPLATE_UPLOADED)
    assert event.actor == SIGNED_IN.username
    assert event.data_json["template_id"] == template_id
    assert event.data_json["wrapped"] is False

    page = client.get(f"/output-templates/{template_id}")
    assert page.status_code == 200
    # 11.9.9: sayfalar küçük önizlemeyle görünür (kademe 1: içeriğe bağlı adres, uzun önbellek).
    assert f'src="/output-templates/{template_id}/pages/1/previews/small?v=' in page.text
    assert f'href="/output-templates/{template_id}/pages/1/previews/large?v=' in page.text
    listed = client.get("/output-templates").text
    assert f'src="/output-templates/{template_id}/pages/0/previews/small?v=' in listed
    image = client.get(f"/output-templates/{template_id}/pages/0")
    assert (image.status_code, image.headers["content-type"]) == (200, "image/jpeg")
    assert client.get(f"/output-templates/{template_id}/pages/2").status_code == 404


def test_image_upload_is_wrapped_into_a_single_page_pdf(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    template_id = _created_id(_upload(client, _png(), filename="form.png", mime="image/png"))

    assert layout.template_original_path(template_id).read_bytes().startswith(b"%PDF-")
    with session_factory() as session:
        assert session.get_one(OutputTemplate, template_id).page_count == 1
    (event,) = _events(session_factory, EventType.TEMPLATE_UPLOADED)
    assert (event.data_json["source_format"], event.data_json["wrapped"]) == ("png", True)


def test_word_file_is_refused_and_nothing_is_written(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    response = _upload(client, make_docx_bytes(), filename="contract.docx", mime="application/zip")

    assert response.status_code == 422
    assert "Word ve Excel" in response.text
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(OutputTemplate)) == 0
    assert not layout.templates_dir.exists()


def test_same_file_twice_is_a_409_with_a_warning_and_the_same_name_too(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    content = make_pdf_bytes(1)
    first = _created_id(_upload(client, content))

    duplicate = _upload(client, content, name="Another name")
    assert duplicate.status_code == 409
    # Önceki yüklemenin yönlendirme bildirimi de çerezde: son bildirim bu isteğinkidir.
    assert toasts(duplicate.text)[-1] == (
        "Bu dosya zaten bir şablon; aynı dosya ikinci kez yüklenmez."
    )
    assert f'href="/output-templates/{first}"' in duplicate.text

    same_name = _upload(client, make_pdf_bytes(2), name="WORK  contract")
    assert same_name.status_code == 409
    assert "Bu adla bir şablon zaten var" in same_name.text
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(OutputTemplate)) == 1


def test_archive_hides_the_template_from_the_default_list_and_restore_brings_it_back(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    template_id = _created_id(_upload(client, make_pdf_bytes(1)))

    archived = client.post(f"/output-templates/{template_id}/archive", follow_redirects=False)
    assert archived.status_code == 303
    assert flashed(archived) == ("templates.archived", {})
    assert "Work contract" not in client.get("/output-templates").text
    assert "Work contract" in client.get("/output-templates?status=archived").text

    restored = client.post(f"/output-templates/{template_id}/restore", follow_redirects=False)
    assert flashed(restored) == ("templates.restored", {})
    with session_factory() as session:
        template = session.get_one(OutputTemplate, template_id)
        assert (template.status, template.archived_at) == ("draft", None)
    events = _events(session_factory, EventType.TEMPLATE_ARCHIVED, EventType.TEMPLATE_RESTORED)
    assert [(e.type, e.actor) for e in events] == [
        ("TEMPLATE_ARCHIVED", SIGNED_IN.username),
        ("TEMPLATE_RESTORED", SIGNED_IN.username),
    ]


def test_open_and_download_serve_the_original_and_write_the_access_log(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    content = make_pdf_bytes(1)
    template_id = _created_id(_upload(client, content))

    opened = client.get(f"/output-templates/{template_id}/file")
    downloaded = client.get(f"/output-templates/{template_id}/download")

    assert opened.content == downloaded.content == content
    assert opened.headers["content-disposition"].startswith("inline")
    assert downloaded.headers["content-disposition"].startswith("attachment")
    assert "Work-contract.pdf" in downloaded.headers["content-disposition"]
    with session_factory() as session:
        rows = session.scalars(select(AccessLog).order_by(AccessLog.id)).all()
        assert [(r.template_id, r.document_id, r.action) for r in rows] == [
            (template_id, None, "view"),
            (template_id, None, "download"),
        ]
    assert client.get("/output-templates/999/file").status_code == 404


def test_an_access_row_has_exactly_one_target(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session, pytest.raises(ValueError):
        record_access(session, user_id=1, action=AccessAction.VIEW, document_id=1, template_id=1)


def test_a_read_only_user_sees_the_list_and_preview_but_cannot_write(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    template_id = _created_id(_upload(client, make_pdf_bytes(1)))
    app.dependency_overrides[get_current_user] = lambda: READER

    listing = client.get("/output-templates")
    assert listing.status_code == 200
    assert "Work contract" in listing.text
    assert 'href="/output-templates/new"' not in listing.text
    page = client.get(f"/output-templates/{template_id}")
    assert "/archive" not in page.text
    assert client.get(f"/output-templates/{template_id}/file").status_code == 200
    assert client.get("/output-templates/new").status_code == 403
    assert _upload(client, make_pdf_bytes(2), name="Other").status_code == 403
    assert client.post(f"/output-templates/{template_id}/archive").status_code == 403
    with session_factory() as session:
        assert session.get_one(OutputTemplate, template_id).status == "draft"
    assert client.post(f"/output-templates/{template_id}/examine").status_code == 403


def test_upload_queues_the_examination_and_the_list_says_so(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    template_id = _created_id(_upload(client, make_pdf_bytes(1)))

    with session_factory() as session:
        template = session.get_one(OutputTemplate, template_id)
        assert template.examine_requested_at is not None
        assert template.examine_error is None
    assert "İnceleniyor" in client.get("/output-templates").text
    page = client.get(f"/output-templates/{template_id}")
    assert 'id="template-examining"' in page.text
    assert "Henüz alan haritası yok." not in page.text


def test_without_a_provider_the_list_shows_the_reason_and_reexamine_requeues(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    app.dependency_overrides[provider_available] = lambda: False
    response = _upload(client, make_pdf_bytes(1))
    template_id = _created_id(response)

    assert flashed(response) == ("templates.uploaded_unexamined", {"count": 1})
    assert "İncelenmedi: yapay zekâ ayarlı değil" in client.get("/output-templates").text
    (event,) = _events(session_factory, EventType.TEMPLATE_EXAMINED)
    assert event.data_json["error"] == "provider_unavailable"

    app.dependency_overrides[provider_available] = lambda: True
    again = client.post(f"/output-templates/{template_id}/examine", follow_redirects=False)
    assert again.status_code == 303
    assert flashed(again) == ("templates.examine_requested", {})
    with session_factory() as session:
        template = session.get_one(OutputTemplate, template_id)
        assert (template.examine_error, template.examine_requested_at is not None) == (None, True)

    client.post(f"/output-templates/{template_id}/archive")
    assert client.post(f"/output-templates/{template_id}/examine").status_code == 409
