"""11.9.7 — örnek önizlemelerinin uçları ve sayfaları (PLAN.md §D130).

Eğitim tür sayfası ve katalog örnek listesi orijinali çekmez: küçük resim içeriğe bağlı önizleme
adresidir (`?v=<anahtar>`), ad büyük önizlemeye bağlanır, orijinal yalnız "İndir" ile iner
(`attachment`). Önizleme yanıtı `nosniff`, `private` uzun önbellek, `ETag` ve 304 taşır; oturumsuz
istek reddedilir, listede olmayan ad 404'tür, bozuk örnekte yer tutucu döner. Veri sentetiktir;
yalnız `TestClient`.
"""

from __future__ import annotations

import re
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.storage import DataLayout, sha256_bytes
from app.storage.examples import store_example
from app.storage.filetype import FileKind
from app.storage.previews import placeholder_jpeg
from app.web.auth import get_current_user
from tests.fixtures.gen import make_half_filled_image_bytes, make_pdf_bytes

SLUG = "russian_passport"
BASES = (f"/training/known/{SLUG}", f"/document-types/{SLUG}")
IMMUTABLE = "private, max-age=31536000, immutable"


@pytest.fixture(autouse=True)
def catalog(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()


@pytest.fixture
def photo(layout: DataLayout) -> bytes:
    content = make_half_filled_image_bytes("JPEG", (2400, 1600))
    store_example(layout, SLUG, "ornek.jpg", content, FileKind.JPEG)
    return content


def _preview_urls(html: str, size: str) -> list[str]:
    pattern = rf'"(/[^"]*/previews/{size}/[^"?]+\?v=[0-9a-f]+)"'
    return sorted(set(re.findall(pattern, html)))


@pytest.mark.parametrize("page", [BASES[0], BASES[1]])
def test_pages_load_previews_not_originals(client: TestClient, photo: bytes, page: str) -> None:
    html = client.get(page).text

    (small,) = _preview_urls(html, "small")
    (large,) = _preview_urls(html, "large")
    assert f'<img src="{small}"' in html
    assert 'loading="lazy" decoding="async"' in html
    assert f'href="{large}"' in html
    # Orijinal yalnız İndir bağlantısında; görüntü kaynağı değil.
    assert re.search(r'href="[^"]*/examples/ornek\.jpg" download>', html)
    assert not re.search(r'src="[^"]*/examples/ornek\.jpg"', html)

    small_body = client.get(small).content
    assert len(small_body) < len(photo) * 0.05
    with Image.open(BytesIO(client.get(large).content)) as image:
        assert max(image.size) == 1280


@pytest.mark.parametrize("base", BASES)
def test_preview_headers_etag_and_304(client: TestClient, photo: bytes, base: str) -> None:
    (small,) = _preview_urls(client.get(base).text, "small")

    first = client.get(small)

    assert first.status_code == 200
    assert first.headers["content-type"] == "image/jpeg"
    assert first.headers["x-content-type-options"] == "nosniff"
    assert first.headers["cache-control"] == IMMUTABLE
    etag = first.headers["etag"]
    again = client.get(small, headers={"If-None-Match": etag})
    assert again.status_code == 304 and not again.content
    # Sürümsüz adres aynı baytları verir ama uzun önbelleklenmez.
    unversioned = client.get(small.split("?")[0])
    assert unversioned.content == first.content
    assert unversioned.headers["cache-control"] == "private, no-cache"


@pytest.mark.parametrize("base", BASES)
def test_original_is_download_only_and_byte_identical(
    client: TestClient, photo: bytes, base: str
) -> None:
    response = client.get(f"{base}/examples/ornek.jpg")

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert sha256_bytes(response.content) == sha256_bytes(photo)


@pytest.mark.parametrize("base", BASES)
@pytest.mark.parametrize(
    "tail",
    ["small/yok.jpg", "huge/ornek.jpg", "small/..%2F..%2Fcatalog.yaml", "small/..%5Ccatalog.yaml"],
)
def test_unlisted_names_and_sizes_are_404(
    client: TestClient, photo: bytes, base: str, tail: str
) -> None:
    assert client.get(f"{base}/previews/{tail}").status_code == 404


@pytest.mark.parametrize("base", BASES)
def test_preview_needs_a_session(app: FastAPI, client: TestClient, photo: bytes, base: str) -> None:
    del app.dependency_overrides[get_current_user]

    response = client.get(f"{base}/previews/small/ornek.jpg", follow_redirects=False)

    assert response.status_code in {303, 401}
    assert response.headers.get("content-type", "") != "image/jpeg"


@pytest.mark.parametrize("base", BASES)
def test_corrupt_example_shows_a_placeholder_and_still_downloads(
    client: TestClient, layout: DataLayout, base: str
) -> None:
    directory = layout.type_examples_dir(SLUG)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "bozuk.jpg").write_bytes(b"\xff\xd8\xff bozuk")

    preview = client.get(f"{base}/previews/large/bozuk.jpg")
    download = client.get(f"{base}/examples/bozuk.jpg")

    assert preview.status_code == 200 and preview.content == placeholder_jpeg()
    assert preview.headers["cache-control"] == "no-store"
    assert download.status_code == 200 and download.content == b"\xff\xd8\xff bozuk"


def test_pdf_example_gets_a_first_page_thumbnail(client: TestClient, layout: DataLayout) -> None:
    store_example(layout, SLUG, "pasaport.pdf", make_pdf_bytes(2), FileKind.PDF)

    (small,) = _preview_urls(client.get(BASES[0]).text, "small")
    response = client.get(small)

    assert "pasaport.pdf" in small
    with Image.open(BytesIO(response.content)) as image:
        assert image.format == "JPEG" and max(image.size) == 320
