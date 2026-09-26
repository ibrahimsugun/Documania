"""11.2.1 — Belge Türleri ekranından türe örnek belge yükleme: örnekler `KnownDocuments/examples/
<slug>/` altında dosya olarak durur, çalışan verisinden ayrıdır ve aramada görünmez.

Veri sentetiktir (`tests/fixtures/gen.py`); gerçek kimlik belgesi ya da yapay zekâ çağrısı yoktur.
Yalnız `TestClient`: tarayıcıda çizim görülmedi."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db.models import Document, Employee, Event, ExampleFileRecord, Upload, UploadFile
from app.storage import DataLayout, find_original_by_sha256, sha256_bytes
from tests.fixtures.gen import make_docx_bytes, make_pdf_bytes, make_portrait_image_bytes

SLUG = "sample_card"
EXAMPLES_URL = f"/document-types/{SLUG}/examples"
LIMIT = 1024 * 1024
# Örnek listesindeki bağlantı dosyayı yeni sekmede açar.
NEW_TAB = 'target="_blank" rel="noopener"'


def _type_data() -> dict[str, Any]:
    return {
        "slug": SLUG,
        "name": "Sample Card",
        "file_label": "Sample Card",
        "country": "RS",
        "expected_file_types": ["pdf", "jpeg"],
        "pages_min": "1",
        "pages_max": "2",
        "sides": "single",
        "analyze": "on",
        "required_fields": "surname, document_number",
        "allowed_conversions": ["merge"],
        "output_format": "pdf",
    }


@pytest.fixture(autouse=True)
def sample_type(client: TestClient) -> None:
    response = client.post("/document-types", data=_type_data(), follow_redirects=False)
    assert response.status_code == 303, response.text


def _upload(client: TestClient, *files: tuple[str, bytes], slug: str = SLUG) -> Any:
    return client.post(
        f"/document-types/{slug}/examples",
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
    )


def _example_dir(layout: DataLayout) -> Path:
    return layout.type_examples_dir(SLUG)


def _stored_names(layout: DataLayout) -> list[str]:
    directory = _example_dir(layout)
    return sorted(path.name for path in directory.iterdir()) if directory.is_dir() else []


def _row_counts(session_factory: sessionmaker[Session]) -> dict[str, int]:
    with session_factory() as session:
        return {
            model.__name__: session.scalar(select(func.count()).select_from(model)) or 0
            for model in (Upload, UploadFile, Document, Event, ExampleFileRecord)
        }


# --- yükleme --------------------------------------------------------------------------------------


def test_edit_page_offers_the_examples_section_only_for_an_existing_type(
    client: TestClient,
) -> None:
    edit = client.get(f"/document-types/{SLUG}")
    new = client.get("/document-types/new")

    assert 'id="examples"' in edit.text
    assert "Bu türe henüz örnek yüklenmedi." in edit.text
    assert f'method="post" action="{EXAMPLES_URL}" enctype="multipart/form-data"' in edit.text
    assert 'name="files" type="file" multiple' in edit.text
    assert 'id="examples"' not in new.text


def test_an_uploaded_example_is_stored_listed_and_served_unchanged(
    client: TestClient, layout: DataLayout
) -> None:
    content = make_portrait_image_bytes("PNG")

    response = _upload(client, ("Ön Yüz.png", content))

    assert response.status_code == 200
    assert "Örnek yüklendi:" in response.text
    assert "<code>On-Yuz.png</code>" in response.text
    assert (
        layout.root / "KnownDocuments" / "examples" / SLUG / "On-Yuz.png"
    ).read_bytes() == content
    listed = client.get(f"/document-types/{SLUG}")
    assert f'<a href="{EXAMPLES_URL}/On-Yuz.png" {NEW_TAB}>On-Yuz.png</a>' in listed.text
    assert "Bu türe henüz örnek yüklenmedi." not in listed.text
    served = client.get(f"{EXAMPLES_URL}/On-Yuz.png")
    assert served.status_code == 200
    assert served.content == content
    assert served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"


def test_several_files_can_be_uploaded_at_once(client: TestClient, layout: DataLayout) -> None:
    pdf, jpeg = make_pdf_bytes(2), make_portrait_image_bytes("JPEG")

    response = _upload(client, ("sablon.pdf", pdf), ("foto.jpg", jpeg))

    assert response.status_code == 200
    assert _stored_names(layout) == ["foto.jpg", "sablon.pdf"]
    assert client.get(f"{EXAMPLES_URL}/sablon.pdf").headers["content-type"] == "application/pdf"
    assert client.get(f"{EXAMPLES_URL}/foto.jpg").content == jpeg


def test_the_same_content_twice_is_reported_and_not_written_again(
    client: TestClient, layout: DataLayout
) -> None:
    content = make_portrait_image_bytes("PNG")
    _upload(client, ("bir.png", content))

    response = _upload(client, ("iki.png", content))

    assert response.status_code == 200
    assert "Aynı içerik zaten örnek olarak kayıtlı:" in response.text
    assert "<code>bir.png</code>" in response.text
    assert _stored_names(layout) == ["bir.png"]


def test_one_rejected_file_writes_nothing_and_says_which(
    client: TestClient, layout: DataLayout
) -> None:
    response = _upload(
        client,
        ("gecerli.png", make_portrait_image_bytes("PNG")),
        ("kaynak.docx", make_docx_bytes()),
        ("bozuk.pdf", b"%PDF-1.4\nbozuk"),
    )

    assert response.status_code == 422
    assert "hiçbir dosya kaydedilmedi" in response.text
    assert (
        "&#39;kaynak.docx&#39; örnek olamaz: yalnız PDF, JPEG ve PNG kabul edilir." in response.text
    )
    assert "&#39;bozuk.pdf&#39; dosyası açılamadı; bozuk olabilir." in response.text
    assert "gecerli.png" not in response.text
    assert _stored_names(layout) == []


def test_no_file_chosen_is_a_400_for_a_missing_or_an_empty_browser_part(
    client: TestClient, layout: DataLayout
) -> None:
    missing = client.post(EXAMPLES_URL)
    # Tarayıcı dosya seçilmemişken adı boş tek bir parça gönderir.
    empty = client.post(EXAMPLES_URL, files={"files": ("", b"", "application/octet-stream")})

    for response in (missing, empty):
        assert response.status_code == 400
        assert "Dosya seçilmedi." in response.text
    assert _stored_names(layout) == []


def test_the_size_limit_applies_to_every_file(
    app: FastAPI, client: TestClient, layout: DataLayout
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="sqlite://", max_upload_file_size_bytes=LIMIT
    )
    too_big = make_pdf_bytes() + b"\n" * (LIMIT + 1000)

    response = _upload(
        client, ("kucuk.png", make_portrait_image_bytes("PNG")), ("buyuk.pdf", too_big)
    )

    assert response.status_code == 422
    assert "&#39;buyuk.pdf&#39; dosyası 1 MB sınırını aşıyor." in response.text
    assert _stored_names(layout) == []


def test_a_rejected_upload_still_shows_the_examples_already_stored(client: TestClient) -> None:
    _upload(client, ("var.png", make_portrait_image_bytes("PNG")))

    response = _upload(client, ("kaynak.docx", make_docx_bytes()))

    assert response.status_code == 422
    assert f'<a href="{EXAMPLES_URL}/var.png" {NEW_TAB}>var.png</a>' in response.text


def test_examples_placed_by_hand_are_listed_and_a_rejected_edit_still_shows_them(
    client: TestClient, layout: DataLayout
) -> None:
    directory = _example_dir(layout)
    directory.mkdir(parents=True)
    (directory / "RUS-specimen-2010.JPG").write_bytes(make_portrait_image_bytes("JPEG"))
    (directory / "notlar.txt").write_text("örnek değil", encoding="utf-8")

    rejected = client.post(f"/document-types/{SLUG}", data={**_type_data(), "name": ""})

    assert rejected.status_code == 422
    assert "RUS-specimen-2010.JPG</a>" in rejected.text
    assert "notlar.txt" not in rejected.text
    assert client.get(f"{EXAMPLES_URL}/RUS-specimen-2010.JPG").status_code == 200
    assert client.get(f"{EXAMPLES_URL}/notlar.txt").status_code == 404


def test_uploading_an_example_does_not_touch_the_type_record(client: TestClient) -> None:
    # Form alanları karşılaştırılır; düğmeler değil — örnek varken "Örneklerden açıklama üret"
    # düğmesi çıkar (11.3.1).
    before = client.get(f"/document-types/{SLUG}").text.split('class="form-actions"')[0]

    _upload(client, ("sayfa.png", make_portrait_image_bytes("PNG")))

    after = client.get(f"/document-types/{SLUG}").text.split('class="form-actions"')[0]
    assert after == before


# --- bulunamayan tür / dosya ----------------------------------------------------------------------


def test_examples_of_an_unknown_type_are_a_404_and_nothing_is_written(
    client: TestClient, layout: DataLayout
) -> None:
    response = _upload(
        client, ("sayfa.png", make_portrait_image_bytes("PNG")), slug="yok_boyle_tur"
    )

    assert response.status_code == 404
    assert client.get("/document-types/yok_boyle_tur/examples/sayfa.png").status_code == 404
    assert not (layout.examples / "yok_boyle_tur").exists()


def test_an_unlisted_file_cannot_be_fetched_through_the_example_route(
    client: TestClient, layout: DataLayout
) -> None:
    _upload(client, ("sayfa.png", make_portrait_image_bytes("PNG")))
    (layout.known_documents / "catalog.yaml").write_text("- slug: x\n", encoding="utf-8")

    for name in (
        "yok.png",
        "catalog.yaml",
        "..%2Fcatalog.yaml",
        "..%2F..%2Fcatalog.yaml",
        "SAYFA.PNG",
    ):
        response = client.get(f"{EXAMPLES_URL}/{name}")
        assert response.status_code == 404, name
        assert "slug: x" not in response.text


def test_example_routes_refuse_the_methods_that_would_change_an_example(
    client: TestClient, layout: DataLayout
) -> None:
    content = make_portrait_image_bytes("PNG")
    _upload(client, ("sayfa.png", content))
    url = f"{EXAMPLES_URL}/sayfa.png"

    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, url, content=b"yeni").status_code == 405, method
    assert (_example_dir(layout) / "sayfa.png").read_bytes() == content


# --- çalışan verisinden ayrı, aramada görünmez ----------------------------------------------------


def test_examples_are_kept_apart_from_employee_data(
    client: TestClient, layout: DataLayout, session_factory: sessionmaker[Session]
) -> None:
    before = _row_counts(session_factory)
    inbox_before = sorted(layout.inbox.rglob("*"))
    content = make_portrait_image_bytes("PNG")

    _upload(client, ("kimlik.png", content), ("sablon.pdf", make_pdf_bytes()))

    # Veritabanında yükleme, dosya, belge ya da olay kaydı açılmaz; el ile yüklenen örnek
    # `example_files`'a da girmez, etiketsizdir (§D58 e — kaydı ve olayı eğitim modu yazar).
    assert (
        _row_counts(session_factory)
        == before
        == {"Upload": 0, "UploadFile": 0, "Document": 0, "Event": 0, "ExampleFileRecord": 0}
    )
    with session_factory() as session:
        assert find_original_by_sha256(session, sha256_bytes(content)) is None
    # Disk: yalnız örnek dizini değişir; Inbox, çalışan, kuyruk ve arşiv dizinleri boş kalır.
    assert sorted(layout.inbox.rglob("*")) == inbox_before
    written = sorted(
        path.relative_to(layout.root).as_posix()
        for path in layout.root.rglob("*")
        if path.is_file()
    )
    assert written == [
        f"KnownDocuments/examples/{SLUG}/kimlik.png",
        f"KnownDocuments/examples/{SLUG}/sablon.pdf",
    ]


def test_examples_do_not_appear_in_any_search_or_list(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.add(
            Employee(
                id="E0001",
                folder_name="Ivan_Petrov_E0001",
                given_names="Ivan",
                surname="Petrov",
                status="active",
            )
        )
        session.commit()

    _upload(client, ("ivan-petrov-pasaport.png", make_portrait_image_bytes("PNG")))

    by_name = client.get("/employees?q=petrov")
    by_example_name = client.get("/employees?q=ivan-petrov-pasaport")
    assert "Ivan Petrov" in by_name.text
    assert "ivan-petrov-pasaport" not in by_name.text
    assert "eşleşen çalışan yok" in by_example_name.text
    for path in ("/employees", "/queues", "/uploads", "/upload"):
        assert "ivan-petrov-pasaport" not in client.get(path).text, path


def test_a_real_upload_of_an_example_s_bytes_is_not_a_duplicate(client: TestClient) -> None:
    content = make_portrait_image_bytes("PNG")
    _upload(client, ("sablon.png", content))

    created = client.post("/api/uploads", files=[("files", ("gercek.png", content, "image/png"))])

    assert created.status_code == 201
    status = client.get(f"/api/uploads/{created.json()['upload_id']}").json()
    assert [file["is_duplicate"] for file in status["files"]] == [False]


def test_the_examples_section_shows_no_edit_or_delete_control(client: TestClient) -> None:
    _upload(client, ("sayfa.png", make_portrait_image_bytes("PNG")))

    page = client.get(f"/document-types/{SLUG}").text
    section = page[page.index('id="examples"') :]

    form = (
        f'<form class="example-form" method="post" action="{EXAMPLES_URL}" '
        'enctype="multipart/form-data">'
    )
    assert re.findall(r"<form[^>]*>", section) == [form]
    assert "delete" not in section.lower()
    assert not re.search(r"sil", re.sub(r"<[^>]+>", " ", section), re.IGNORECASE)


def test_sizes_are_shown_in_kb_and_mb(client: TestClient, layout: DataLayout) -> None:
    directory = _example_dir(layout)
    directory.mkdir(parents=True)
    (directory / "kucuk.png").write_bytes(b"x" * 10)
    (directory / "orta.png").write_bytes(b"x" * (300 * 1024))
    (directory / "buyuk.pdf").write_bytes(b"x" * (2 * 1024 * 1024 + 512 * 1024))

    page = client.get(f"/document-types/{SLUG}").text

    assert "(1 KB)" in page
    assert "(300 KB)" in page
    assert "(2.5 MB)" in page
