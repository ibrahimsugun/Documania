"""11.9.10 — ham dosyası silinmiş örnek panelde (PLAN.md §D135 c).

Ham dosya silinip kalıcı örnek dizini eşitlendikten sonra eğitim tür sayfası ve katalog örnek
listesi örneği adı, kaydı ve kalıcı önizlemesiyle gösterir; "İndir" yerine "Ham dosya silindi"
yazar, dosya ucu 404'tür, ön yükleme listesi önizleme adresini verir ve aynı içerik yeniden
yüklenince tekrar sayılır. Veri sentetiktir; yalnız `TestClient`.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.storage import DataLayout
from app.storage.examples import store_example, sync_example_index
from app.storage.filetype import FileKind
from app.training.cleanup import record_uploaded_example
from app.web.previews import ListRateLimit
from app.web.routers import previews as previews_router
from tests.fixtures.gen import make_half_filled_image_bytes

SLUG = "russian_passport"
TRAINING = f"/training/known/{SLUG}"
CATALOG = f"/document-types/{SLUG}"
IMMUTABLE = "private, max-age=31536000, immutable"


@pytest.fixture(autouse=True)
def catalog(session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(previews_router, "LIST_RATE", ListRateLimit(limit=30, window=60.0))
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()


@pytest.fixture
def content() -> bytes:
    return make_half_filled_image_bytes("JPEG", (900, 600))


@pytest.fixture
def removed(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    content: bytes,
) -> str:
    """Kayıtlı bir örnek: önizlemesi üretilmiş, sonra ham dosyası silinmiş ve dizin eşitlenmiş."""
    with session_factory() as session:
        stored = store_example(layout, SLUG, "silinen.jpg", content, FileKind.JPEG, session=session)
        record_uploaded_example(session, SLUG, stored)
        session.commit()
    for size in ("small", "large"):
        assert client.get(f"{TRAINING}/previews/{size}/silinen.jpg").status_code == 200
    (layout.type_examples_dir(SLUG) / "silinen.jpg").unlink()
    with session_factory() as session:
        assert sync_example_index(session, layout).removed == 1
        session.commit()
    return stored.name


@pytest.mark.parametrize("page", [TRAINING, CATALOG])
def test_pages_show_the_removed_example_with_its_preview_and_no_download(
    client: TestClient, removed: str, page: str
) -> None:
    html = client.get(page).text

    assert removed in html and "Ham dosya silindi" in html
    assert not re.search(rf'href="[^"]*/examples/{removed}" download', html)
    (large,) = set(re.findall(rf'"([^"]*/previews/large/{removed}\?v=[0-9a-f]+)"', html))
    response = client.get(large)
    assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == IMMUTABLE


def test_training_page_keeps_the_record_of_the_removed_example(
    client: TestClient, removed: str
) -> None:
    html = client.get(TRAINING).text

    assert "tür sayfasından yüklendi" in html  # kaydın notu (example_files) yerinde


@pytest.mark.parametrize("base", [TRAINING, CATALOG])
def test_original_file_endpoint_is_404_after_removal(
    client: TestClient, removed: str, base: str
) -> None:
    assert client.get(f"{base}/examples/{removed}").status_code == 404


def test_prefetch_list_still_gives_the_removed_examples_thumb(
    client: TestClient, removed: str
) -> None:
    items = client.get("/previews/thumbs").json()["items"]

    assert [url for url in items if f"/previews/small/{removed}?v=" in url]


def test_uploading_the_same_content_again_is_a_duplicate(
    client: TestClient, removed: str, content: bytes, layout: DataLayout
) -> None:
    response = client.post(
        f"{CATALOG}/examples",
        files=[("files", ("yeniden.jpg", content, "application/octet-stream"))],
    )

    assert response.status_code == 409
    assert not layout.type_examples_dir(SLUG).joinpath("yeniden.jpg").exists()
