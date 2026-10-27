"""Genel önizleme katmanı (PRD 11.9.9; PLAN.md §D132 b, c, d, e) — panelin belge gösterdiği her yer.

- Listeler yalnız küçük JPEG çeker; orijinal (`/file`) hiçbir sayfadan bağlanmaz, yalnız İndir.
- Her önizleme ucu kaynağın mevcut yetki kuralındadır: başka çalışanın/partinin adresi 404.
- Kademe 2 (gerçek belge): `private, max-age=900` + `ETag`/304; kademe 1 (şablon): `immutable`.
- Erişim logu: önizleme sayfasının açılışı `view`; küçük/büyük JPEG'ler kayıt yazmaz.
- Ön yükleme listesi (`/previews/thumbs`) çalışan belgesi adresi taşımaz.

Veri sentetiktir (`tests/fixtures/gen.py`); yapay zekâ kayıtlı yanıtla çalışır.
"""

from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AccessLog, Page
from app.storage import DataLayout, sha256_file
from tests.fixtures.gen import make_docx_bytes, make_portrait_image_bytes, make_sized_pdf_bytes
from tests.web.test_output_templates import _created_id, _upload
from tests.web.test_profile import PASSPORT, PHOTO, _catalog, _document, _employee
from tests.web.test_upload_detail import _processed

A4 = (595.0, 842.0)
PERSONAL = "private, max-age=900"
IMMUTABLE = "private, max-age=31536000, immutable"


def _seed(session_factory: sessionmaker[Session], layout: DataLayout) -> dict[str, int]:
    """İki çalışan: E0001'in üç sayfalı pasaportu, Word eki ve fotoğrafı; E0002'nin bir belgesi."""
    with session_factory() as session:
        _catalog(session)
        dmitry = _employee(session)
        anna = _employee(session, 2, "Anna", "Zeta")
        pdf = make_sized_pdf_bytes([A4, (A4[1], A4[0]), A4])
        passport = _document(session, layout, dmitry, PASSPORT, "Pasaport.pdf", pdf)
        word = _document(session, layout, dmitry, PASSPORT, "Not.docx", make_docx_bytes())
        photo = _document(session, layout, dmitry, PHOTO, "Foto.jpg", make_portrait_image_bytes())
        foreign = _document(session, layout, anna, PASSPORT, "Anna.pdf", make_sized_pdf_bytes([A4]))
        session.commit()
        return {
            "passport": passport.id,
            "word": word.id,
            "photo": photo.id,
            "foreign": foreign.id,
        }


def _access_rows(session_factory: sessionmaker[Session]) -> list[tuple[int | None, str]]:
    with session_factory() as session:
        rows = session.scalars(select(AccessLog).order_by(AccessLog.id)).all()
        return [(row.document_id, row.action) for row in rows]


def _jpeg_size(content: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(content)) as image:
        assert image.format == "JPEG"
        return image.size


def test_profile_lists_only_small_previews_and_never_links_the_original(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    ids = _seed(session_factory, layout)
    base = f"/employees/E0001/documents/{ids['passport']}"

    page = client.get("/employees/E0001").text

    assert f'<img class="doc-thumb" src="{base}/previews/small?v=' in page
    assert 'loading="lazy" decoding="async"' in page
    assert f'data-preview-large="{base}/previews/large?v=' in page
    assert f'href="{base}/preview" target="_blank"' in page
    assert f'href="{base}/download"' in page
    assert "/file" not in page
    # Word eki önizlenemez: küçük resmi yok, önizleme sayfası İndir'e yönlendirir.
    assert f"/documents/{ids['word']}/previews/" not in page
    word = client.get(f"/employees/E0001/documents/{ids['word']}/preview")
    assert word.status_code == 200 and "Bu dosya biçimi önizlenemez" in word.text
    # Liste açmak erişim logu yazmaz.
    assert _access_rows(session_factory) == [(ids["word"], "view")]


def test_preview_page_shows_every_page_large_and_only_its_opening_is_logged(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    ids = _seed(session_factory, layout)
    base = f"/employees/E0001/documents/{ids['passport']}"
    original = layout.root / "Employees"
    before = {path: sha256_file(path) for path in original.rglob("*") if path.is_file()}

    page = client.get(f"{base}/preview")
    small = client.get(f"{base}/previews/small")
    first = client.get(f"{base}/previews/large")
    second = client.get(f"{base}/previews/large?page=2")

    assert page.status_code == 200
    assert f'src="{base}/previews/large?v=' in page.text
    assert f'src="{base}/previews/large?page=2&amp;v=' in page.text
    assert f'src="{base}/previews/large?page=3&amp;v=' in page.text
    assert f'href="{base}/download"' in page.text
    assert max(_jpeg_size(small.content)) == 320
    width, height = _jpeg_size(first.content)
    assert height == 1280 and width < height
    width, height = _jpeg_size(second.content)
    assert width == 1280 and height < width  # sayfa sayfa: ikinci sayfa yatay
    assert client.get(f"{base}/previews/large?page=21").status_code == 404
    assert client.get(f"{base}/previews/huge").status_code == 404
    assert _access_rows(session_factory) == [(ids["passport"], "view")]
    after = {path: sha256_file(path) for path in original.rglob("*") if path.is_file()}
    assert after == before  # orijinaller değişmez (K10, K11)


def test_personal_previews_are_cached_briefly_and_revalidate_with_an_etag(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    ids = _seed(session_factory, layout)
    url = f"/employees/E0001/documents/{ids['passport']}/previews/small"

    response = client.get(url)
    again = client.get(url, headers={"If-None-Match": response.headers["etag"]})

    assert response.status_code == 200
    assert response.headers["cache-control"] == PERSONAL
    assert response.headers["x-content-type-options"] == "nosniff"
    assert again.status_code == 304 and not again.content


def test_previews_of_someone_elses_or_deleted_documents_are_not_found(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    ids = _seed(session_factory, layout)
    foreign = ids["foreign"]

    for url in (
        f"/employees/E0001/documents/{foreign}/previews/small",
        f"/employees/E0001/documents/{foreign}/preview",
        "/employees/E0001/documents/9999/previews/large",
        f"/employees/E0002/documents/{ids['passport']}/previews/small",
        f"/employees/E0001/documents/{ids['word']}/previews/small",
        "/employees/E0002/photo/previews/small",
    ):
        assert client.get(url).status_code == 404, url
    assert _access_rows(session_factory) == []


def test_profile_photo_is_a_small_preview_with_a_large_one_on_click(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    _seed(session_factory, layout)

    page = client.get("/employees/E0001").text
    small = client.get("/employees/E0001/photo/previews/small")
    large = client.get("/employees/E0001/photo/previews/large")

    assert '<img src="/employees/E0001/photo/previews/small?v=' in page
    assert 'href="/employees/E0001/photo/previews/large?v=' in page
    assert small.headers["cache-control"] == large.headers["cache-control"] == PERSONAL
    assert max(_jpeg_size(small.content)) <= 320
    assert _access_rows(session_factory) == []


def test_upload_page_previews_follow_the_upload_and_come_from_the_original(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)
    with session_factory() as session:
        page = session.scalars(select(Page)).one()
        page_id, analysis = page.id, layout.resolve(page.image_path or "")
    analysis_digest = sha256_file(analysis)
    base = f"/uploads/{upload_id}/pages/{page_id}"

    small = client.get(f"{base}/previews/small")
    large = client.get(f"{base}/previews/large")

    assert small.status_code == large.status_code == 200
    assert max(_jpeg_size(small.content)) == 320
    assert max(_jpeg_size(large.content)) == 1280
    assert small.headers["cache-control"] == PERSONAL
    assert client.get(f"/uploads/u_baska/pages/{page_id}/previews/small").status_code == 404
    assert client.get(f"/uploads/{upload_id}/pages/99999/previews/small").status_code == 404
    assert sha256_file(analysis) == analysis_digest  # analiz görüntüsü (cache/pages) değişmez
    assert _access_rows(session_factory) == []


def test_template_page_previews_are_immutable_specimens(
    client: TestClient, layout: DataLayout
) -> None:
    template_id = _created_id(_upload(client, make_sized_pdf_bytes([A4, A4])))
    page = client.get(f"/output-templates/{template_id}").text
    start = page.index(f"/output-templates/{template_id}/pages/0/previews/small?v=")
    url = page[start : page.index('"', start)]

    current = client.get(url)
    unversioned = client.get(url.split("?")[0])

    assert current.status_code == 200
    assert current.headers["cache-control"] == IMMUTABLE
    assert unversioned.headers["cache-control"] == "private, no-cache"
    assert client.get(f"/output-templates/{template_id}/pages/5/previews/small").status_code == 404
    assert client.get("/output-templates/9999/pages/0/previews/small").status_code == 404


def test_the_prefetch_list_carries_no_employee_document_address(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    """Gerçek boru hattından geçen parti çalışan belgesi ve yükleme sayfası üretir; toplu ısıtma
    listesi (kademe 1) yine de bunların hiçbirini taşımaz (§D132 e)."""
    _processed(client, session_factory, layout, tmp_path)

    listed = client.get("/previews/thumbs").json()

    assert all(not url.startswith(("/employees", "/uploads")) for url in listed["items"])
