"""11.2.1 — Belge Türleri ekranından türe örnek belge yükleme: örnekler `KnownDocuments/examples/
<slug>/` altında dosya olarak durur, çalışan verisinden ayrıdır ve aramada görünmez. 11.9.6:
yüklenen örnek `example_files` kaydı alır (elle, doğrulanmış; olay yok), aynı içerik aynı türde
409'dur, örnek listesi kaydın kimliğiyle taşı/çıkar akışına bağlanır, çıkarılmış kaydın adı 404'tür.

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

from app.catalog.schema import CatalogError
from app.config import Settings, get_settings
from app.db.models import Document, Employee, Event, ExampleFileRecord, Upload, UploadFile
from app.storage import DataLayout, find_original_by_sha256, sha256_bytes
from app.training.cleanup import UPLOADED_NOTE
from app.web.auth import SESSION_COOKIE
from app.web.confirm import Operation
from app.web.routers import catalog as catalog_router
from app.web.routers.catalog import EXAMPLE_RECORD_CLASH
from app.web.routers.training import decision_subject
from tests.fixtures.gen import make_docx_bytes, make_pdf_bytes, make_portrait_image_bytes
from tests.web.conftest import SESSION, issue_token

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


def test_the_same_content_twice_is_a_409_and_nothing_is_written(
    client: TestClient, layout: DataLayout, session_factory: sessionmaker[Session]
) -> None:
    # 11.9.2 kuralı (11.9.6): aynı içerik aynı türde ikinci kez eklenmez; yüklemenin hiçbir dosyası
    # yazılmaz.
    content = make_portrait_image_bytes("PNG")
    _upload(client, ("bir.png", content))

    response = _upload(client, ("yeni.pdf", make_pdf_bytes(1)), ("iki.png", content))

    assert response.status_code == 409
    assert "hiçbir dosya kaydedilmedi" in response.text
    assert (
        "&#39;iki.png&#39; bu türde zaten örnek (aynı içerik: bir.png); yüklenmedi."
        in response.text
    )
    assert _stored_names(layout) == ["bir.png"]
    assert _row_counts(session_factory)["ExampleFileRecord"] == 1


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

    # Veritabanında yükleme, dosya, belge ya da olay kaydı açılmaz; el ile yüklenen örnek yalnız
    # `example_files` kaydı alır (11.9.6), olay yazmaz (§D58 e — olayı eğitim modu yazar).
    assert before == {
        "Upload": 0,
        "UploadFile": 0,
        "Document": 0,
        "Event": 0,
        "ExampleFileRecord": 0,
    }
    assert _row_counts(session_factory) == before | {"ExampleFileRecord": 2}
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


def test_the_examples_section_shows_no_edit_or_delete_control(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload(client, ("sayfa.png", make_portrait_image_bytes("PNG")))
    (record_id,) = _record_ids(session_factory)

    page = client.get(f"/document-types/{SLUG}").text
    section = page[page.index('id="examples"') :]

    form = (
        f'<form class="example-form" method="post" action="{EXAMPLES_URL}" '
        'enctype="multipart/form-data">'
    )
    # 11.9.6: kaydı olan örneğin tek kararları 11.9.4'ün iki aşamalı taşı/çıkar akışıdır; ikisinin
    # de ilk adımı yalnız onay metnini gösterir.
    assert re.findall(r"<form[^>]*>", section) == [
        f'<form class="inline-form" method="post" action="/training/examples/{record_id}/move/'
        'confirm">',
        f'<form class="inline-form" method="post" action="/training/examples/{record_id}/remove/'
        'confirm">',
        form,
    ]
    assert "delete" not in section.lower()
    assert not re.search(r"\bsil\b", re.sub(r"<[^>]+>", " ", section), re.IGNORECASE)


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


# --- elle kontrol ikonu (11.9.4) ------------------------------------------------------------------


def _list_item(page: str, name: str) -> str:
    match = re.search(
        rf'<li[^>]*>\s*<a href="[^"]*/examples/{re.escape(name)}".*?</li>', page, re.S
    )
    assert match is not None, name
    return match.group(0)


def test_an_ai_decision_example_shows_the_manual_check_icon_in_the_type_page_list(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    """11.9.4: "AI kararı" etiketli örnek tür sayfasının örnek listesinde elle kontrol ikonuyla ve
    eğitim sekmesine bağlantıyla görünür; doğrulanmış örnek ikonsuz, kaydı olmayan etiketsiz."""
    _upload(
        client,
        ("ai.png", make_portrait_image_bytes("PNG", (200, 300))),
        ("dogru.png", make_portrait_image_bytes("PNG", (210, 300))),
    )
    # Kaydı olmayan eski dosya (eğitimden ve 11.9.6'dan önce el ile konmuş).
    (_example_dir(layout) / "elle.pdf").write_bytes(make_pdf_bytes(1))
    with session_factory() as session:
        record = session.scalars(
            select(ExampleFileRecord).where(ExampleFileRecord.name == "ai.png")
        ).one()
        record.method, record.label = "ai", "ai_decision"
        session.commit()

    page = client.get(f"/document-types/{SLUG}").text

    ai, verified, manual = (_list_item(page, name) for name in ("ai.png", "dogru.png", "elle.pdf"))
    assert 'aria-label="Elle kontrol gerekli"' in ai and 'class="needs-check"' in ai
    assert "AI kararı" in ai and f'href="/training/known/{SLUG}"' in ai
    assert "Elle kontrol gerekli" not in verified and "Doğrulandı" in verified
    assert "badge" not in manual and "Elle kontrol" not in manual
    assert '1 örnek "AI kararı" etiketli ve elle kontrol bekliyor' in page


# --- example_files kaydı, taşı/çıkar bağlantıları ve çıkarılan örnek (11.9.6) --------------------


def _records(session_factory: sessionmaker[Session]) -> list[ExampleFileRecord]:
    with session_factory() as session:
        records = list(session.scalars(select(ExampleFileRecord).order_by(ExampleFileRecord.id)))
        session.expunge_all()
        return records


def _record_ids(session_factory: sessionmaker[Session]) -> list[int]:
    return [record.id for record in _records(session_factory)]


def test_an_uploaded_example_gets_a_manual_verified_record_and_no_event(
    client: TestClient, layout: DataLayout, session_factory: sessionmaker[Session]
) -> None:
    png, pdf = make_portrait_image_bytes("PNG"), make_pdf_bytes(2)

    response = _upload(client, ("Ön Yüz.png", png), ("sablon.pdf", pdf))

    assert response.status_code == 200
    records = _records(session_factory)
    assert [(r.type_slug, r.name, r.sha256) for r in records] == [
        (SLUG, "On-Yuz.png", sha256_bytes(png)),
        (SLUG, "sablon.pdf", sha256_bytes(pdf)),
    ]
    for record in records:
        assert (record.method, record.label) == ("manual", "verified")
        assert record.training_item_id is None
        assert record.note == UPLOADED_NOTE
        assert record.removed_at is None
    assert _row_counts(session_factory)["Event"] == 0
    item = _list_item(response.text, "On-Yuz.png")
    assert "Doğrulandı" in item and "Elle kontrol" not in item


def test_the_same_content_in_one_upload_is_a_409(
    client: TestClient, layout: DataLayout, session_factory: sessionmaker[Session]
) -> None:
    content = make_portrait_image_bytes("PNG")

    response = _upload(client, ("bir.png", content), ("iki.png", content))

    assert response.status_code == 409
    assert (
        "&#39;iki.png&#39; aynı yüklemede &#39;bir.png&#39; ile aynı içerikte; yüklenmedi."
        in response.text
    )
    assert _stored_names(layout) == []
    assert _records(session_factory) == []


def test_an_unregistered_file_with_the_same_content_is_a_409_too(
    client: TestClient, layout: DataLayout, session_factory: sessionmaker[Session]
) -> None:
    content = make_portrait_image_bytes("PNG")
    directory = _example_dir(layout)
    directory.mkdir(parents=True)
    (directory / "eski.png").write_bytes(content)

    response = _upload(client, ("yeni.png", content))

    assert response.status_code == 409
    assert "(aynı içerik: eski.png)" in response.text
    assert _stored_names(layout) == ["eski.png"]
    assert _records(session_factory) == []


def test_the_same_content_in_another_type_is_allowed(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    other = {**_type_data(), "slug": "other_card", "name": "Other Card"}
    assert client.post("/document-types", data=other, follow_redirects=False).status_code == 303
    content = make_portrait_image_bytes("PNG")
    _upload(client, ("bir.png", content))

    response = _upload(client, ("bir.png", content), slug="other_card")

    assert response.status_code == 200
    assert sorted((r.type_slug, r.name) for r in _records(session_factory)) == [
        ("other_card", "bir.png"),
        (SLUG, "bir.png"),
    ]


def test_a_stale_active_record_with_the_written_name_is_a_409_and_writes_no_row(
    client: TestClient, layout: DataLayout, session_factory: sessionmaker[Session]
) -> None:
    # Kaydı etkin ama dosyası elle kaldırılmış eski örnek: yeni dosya aynı adı alır, kısmi tekil
    # dizin kaydı reddeder. Yazılan dosya kalır (silme yok) ve kayıtsız görünür.
    with session_factory() as session:
        session.add(
            ExampleFileRecord(
                type_slug=SLUG, name="ad.png", sha256="0" * 64, method="manual", label="verified"
            )
        )
        session.commit()

    response = _upload(client, ("ad.png", make_portrait_image_bytes("PNG")))

    assert response.status_code == 409
    assert EXAMPLE_RECORD_CLASH in response.text
    assert _stored_names(layout) == ["ad.png"]
    assert len(_records(session_factory)) == 1


def test_registered_examples_link_to_move_and_remove_unregistered_ones_say_so(
    client: TestClient, layout: DataLayout, session_factory: sessionmaker[Session]
) -> None:
    _upload(client, ("kayitli.png", make_portrait_image_bytes("PNG")))
    (_example_dir(layout) / "eski.pdf").write_bytes(make_pdf_bytes(1))
    (record_id,) = _record_ids(session_factory)

    page = client.get(f"/document-types/{SLUG}").text

    registered, unregistered = _list_item(page, "kayitli.png"), _list_item(page, "eski.pdf")
    assert f'action="/training/examples/{record_id}/move/confirm"' in registered
    assert f'action="/training/examples/{record_id}/remove/confirm"' in registered
    assert 'name="slug" list="move-type-options" required' in registered
    assert "Başka türe taşı" in registered and "Örneklerden çıkar" in registered
    assert "<form" not in unregistered
    assert "kayıtsız" in unregistered and "register-examples" in unregistered
    datalist = page[page.index('<datalist id="move-type-options">') :].split("</datalist>")[0]
    assert '<option value="albanian_passport">' in datalist
    assert f'<option value="{SLUG}">' not in datalist


def test_a_type_without_registered_examples_has_no_move_list(
    client: TestClient, layout: DataLayout
) -> None:
    directory = _example_dir(layout)
    directory.mkdir(parents=True)
    (directory / "eski.pdf").write_bytes(make_pdf_bytes(1))

    page = client.get(f"/document-types/{SLUG}").text

    assert "move-type-options" not in page
    assert "kayıtsız" in _list_item(page, "eski.pdf")


def test_removing_an_example_from_the_type_page_archives_it_and_its_file_is_404(
    client: TestClient, layout: DataLayout, session_factory: sessionmaker[Session]
) -> None:
    content = make_portrait_image_bytes("PNG")
    _upload(client, ("cikacak.png", content))
    (record_id,) = _record_ids(session_factory)

    first = client.post(f"/training/examples/{record_id}/remove/confirm")
    assert first.status_code == 200
    assert "cikacak.png örneğini Sample Card örneklerinden çıkarmak üzeresiniz." in first.text
    (record,) = _records(session_factory)
    token = issue_token(
        session_factory, Operation.TRAINING_REMOVE, decision_subject(record), cookie=SESSION
    )
    client.cookies.set(SESSION_COOKIE, SESSION)
    done = client.post(
        f"/training/examples/{record_id}/remove",
        data={"confirmation": token},
        follow_redirects=False,
    )

    assert done.status_code == 303, done.text
    (removed,) = _records(session_factory)
    assert removed.removed_at is not None
    assert (layout.root / (removed.removed_path or "")).read_bytes() == content
    assert _stored_names(layout) == []
    assert client.get(f"{EXAMPLES_URL}/cikacak.png").status_code == 404
    page = client.get(f"/document-types/{SLUG}").text
    assert "cikacak.png" not in page
    # Aynı adla dosya klasöre elle geri konsa da çıkarılmış kaydın adı 404'tür.
    (_example_dir(layout) / "cikacak.png").write_bytes(content)
    assert client.get(f"{EXAMPLES_URL}/cikacak.png").status_code == 404
    # Çıkarılan içerik yeniden yüklenebilir (çıkarılan kayıt tekrar sayılmaz).
    (_example_dir(layout) / "cikacak.png").unlink()
    assert _upload(client, ("cikacak.png", content)).status_code == 200
    assert client.get(f"{EXAMPLES_URL}/cikacak.png").content == content


def test_the_move_link_starts_the_two_step_move(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload(client, ("tasinacak.png", make_portrait_image_bytes("PNG")))
    (record_id,) = _record_ids(session_factory)

    first = client.post(
        f"/training/examples/{record_id}/move/confirm", data={"slug": "albanian_passport"}
    )

    assert first.status_code == 200
    assert (
        "tasinacak.png örneğini Sample Card türünden Albanian Passport türüne taşımak üzeresiniz."
        in first.text
    )
    assert _records(session_factory)[0].type_slug == SLUG


def test_the_move_list_is_empty_when_the_known_types_cannot_be_read(
    client: TestClient, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Kayıtlı katalog okunamazsa (`CatalogError`) taşıma formu yine çıkar; hedef onay adımında
    # denetlenir, seçenek listesi boştur.
    _upload(client, ("tasinacak.png", make_portrait_image_bytes("PNG")))
    (record_id,) = _record_ids(session_factory)

    def unreadable(_session: Session) -> None:
        raise CatalogError("katalog okunamadı")

    monkeypatch.setattr(catalog_router, "load_known_types", unreadable)
    page = client.get(f"/document-types/{SLUG}").text

    assert f'action="/training/examples/{record_id}/move/confirm"' in page
    assert 'move-type-options">' not in page
