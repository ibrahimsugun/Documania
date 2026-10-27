"""11.9.8 — önizleme ön yükleme (PLAN.md §D131).

Liste ucu (`/previews/thumbs`) oturum ister, yalnız tür sayfasının gösterdiği küçük önizleme
adreslerini ve liste sürümünü sayfalı verir (orijinal dosya adresi yok), oturum başına hız
sınırlıdır. Ön yükleme isteği üretim yeri bulamazsa `503 Retry-After` alır. Tür ve katalog
sayfaları büyük önizleme adresini `data-preview-large` ile taşır; betik yalnız girişli sayfadadır.
Çıkış yanıtı tarayıcı önbelleğini temizler. Veri sentetiktir; yalnız `TestClient`.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.storage import DataLayout
from app.storage import previews as previews_module
from app.storage.examples import store_example
from app.storage.filetype import FileKind
from app.web.auth import get_current_user
from app.web.previews import ListRateLimit
from app.web.routers import previews as previews_router
from tests.fixtures.gen import make_half_filled_image_bytes

SLUG = "russian_passport"
OTHER = "russian_internal_passport"
STATIC = Path(__file__).resolve().parents[2] / "app" / "web" / "static"


@pytest.fixture(autouse=True)
def catalog(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()


@pytest.fixture(autouse=True)
def fresh_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(previews_router, "LIST_RATE", ListRateLimit(limit=30, window=60.0))


def _example(layout: DataLayout, slug: str, name: str, width: int) -> None:
    content = make_half_filled_image_bytes("JPEG", (width, 300))
    store_example(layout, slug, name, content, FileKind.JPEG)


def test_list_returns_the_type_pages_thumb_urls_and_a_version(
    client: TestClient, layout: DataLayout
) -> None:
    _example(layout, SLUG, "a.jpg", 400)
    _example(layout, SLUG, "b.jpg", 401)
    _example(layout, OTHER, "c.jpg", 402)

    response = client.get("/previews/thumbs")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert set(body) == {"version", "items", "next"}
    assert re.fullmatch(r"[0-9a-f]{20}", body["version"])
    assert body["next"] is None
    assert len(body["items"]) == 3
    # Adresler tür sayfasındaki küçük resim adreslerinin aynısı: sayfa açılınca ağa gitmez.
    page = client.get(f"/training/known/{SLUG}").text
    for url in body["items"]:
        assert re.fullmatch(r"/training/known/[a-z_]+/previews/small/[a-z]\.jpg\?v=[0-9a-f]+", url)
        assert "/examples/" not in url  # orijinal dosya adresi listede yok
    assert all(f'src="{url}"' in page for url in body["items"] if f"/{SLUG}/" in url)
    for url in body["items"]:
        assert client.get(url).headers["content-type"] == "image/jpeg"


def test_list_is_paged_and_its_version_follows_the_examples(
    client: TestClient, layout: DataLayout
) -> None:
    for index in range(5):
        _example(layout, SLUG, f"{'abcde'[index]}.jpg", 400 + index)

    first = client.get("/previews/thumbs?limit=2").json()
    second = client.get(f"/previews/thumbs?after={first['next']}&limit=2").json()
    last = client.get(f"/previews/thumbs?after={second['next']}&limit=2").json()

    assert (first["next"], second["next"], last["next"]) == (2, 4, None)
    assert len(first["items"] + second["items"] + last["items"]) == 5
    assert len(set(first["items"] + second["items"] + last["items"])) == 5
    assert first["version"] == second["version"] == last["version"]
    assert client.get("/previews/thumbs").json()["version"] == first["version"]
    # Yeni örnek eklenince sürüm değişir (istemci yalnız yenileri ağdan alır).
    _example(layout, SLUG, "f.jpg", 450)
    assert client.get("/previews/thumbs").json()["version"] != first["version"]


@pytest.mark.parametrize("query", ["limit=201", "limit=0", "after=-1", "after=x"])
def test_list_bounds_are_enforced(client: TestClient, query: str) -> None:
    assert client.get(f"/previews/thumbs?{query}").status_code == 422


def test_list_needs_a_session(app: FastAPI, client: TestClient) -> None:
    del app.dependency_overrides[get_current_user]

    response = client.get("/previews/thumbs", follow_redirects=False)

    assert response.status_code == 303
    assert "items" not in response.text


def test_list_is_rate_limited_per_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(previews_router, "LIST_RATE", ListRateLimit(limit=2, window=60.0))
    client.cookies.set("belgeee_session", "oturum-bir")

    assert client.get("/previews/thumbs").status_code == 200
    assert client.get("/previews/thumbs").status_code == 200
    limited = client.get("/previews/thumbs")

    assert limited.status_code == 429
    assert 1 <= int(limited.headers["retry-after"]) <= 60
    # Başka oturumun payı ayrı.
    client.cookies.set("belgeee_session", "oturum-iki")
    assert client.get("/previews/thumbs").status_code == 200


def test_rate_limit_window_slides_and_memory_stays_bounded() -> None:
    limit = ListRateLimit(limit=1, window=10.0, capacity=3)

    assert limit.retry_after("a", now=0.0) is None
    assert limit.retry_after("a", now=5.0) == 6
    assert limit.retry_after("a", now=10.5) is None
    for token in ("b", "c", "d", "e"):
        assert limit.retry_after(token, now=11.0) is None
    assert len(limit._hits) <= 3


@pytest.mark.parametrize("base", [f"/training/known/{SLUG}", f"/document-types/{SLUG}"])
def test_prefetch_gets_503_with_retry_after_when_rendering_is_busy(
    client: TestClient, layout: DataLayout, monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    _example(layout, SLUG, "a.jpg", 400)
    monkeypatch.setattr(previews_module, "_slots", threading.BoundedSemaphore(1))
    previews_module._slots.acquire()

    busy = client.get(f"{base}/previews/large/a.jpg", headers={"X-Preview-Prefetch": "1"})

    assert busy.status_code == 503
    assert busy.headers["retry-after"] == "2"
    assert busy.headers["cache-control"] == "no-store"
    previews_module._slots.release()
    # Yer açılınca ön yükleme de üretir; kullanıcının isteği (işaretsiz) aynı önizlemeyi alır.
    ready = client.get(f"{base}/previews/large/a.jpg", headers={"X-Preview-Prefetch": "1"})
    assert ready.status_code == 200
    assert client.get(f"{base}/previews/large/a.jpg").content == ready.content


@pytest.mark.parametrize("page", [f"/training/known/{SLUG}", f"/document-types/{SLUG}"])
def test_pages_mark_their_large_previews_and_load_the_script(
    client: TestClient, layout: DataLayout, page: str
) -> None:
    _example(layout, SLUG, "a.jpg", 400)

    html = client.get(page).text

    (large,) = re.findall(r'data-preview-large="([^"]+)"', html)
    assert re.fullmatch(r"/[^\"]+/previews/large/a\.jpg\?v=[0-9a-f]+", large)
    assert f'href="{large}"' in html
    assert re.search(r'<script src="/static/preview-prefetch\.js\?v=[0-9a-f]{12}" defer>', html)


def test_login_page_does_not_load_the_script(app: FastAPI, client: TestClient) -> None:
    del app.dependency_overrides[get_current_user]

    assert "preview-prefetch.js" not in client.get("/login").text


def test_logout_clears_the_browser_cache(app: FastAPI, client: TestClient) -> None:
    del app.dependency_overrides[get_current_user]

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["clear-site-data"] == '"cache"'


def test_script_follows_the_prefetch_contract() -> None:
    script = (STATIC / "preview-prefetch.js").read_text(encoding="utf-8")

    for needle in (
        'priority: "low"',
        "AbortController",
        '"pointerdown"',
        '"htmx:beforeRequest"',
        '"pagehide"',
        "document.hidden",
        "saveData",
        '"slow-2g"',
        "Retry-After",
        "requestIdleCallback",
        "IntersectionObserver",
        "[data-preview-large]",
        "var WORKERS = 2;",
        'var LIST_URL = "/previews/thumbs";',
    ):
        assert needle in script, needle
    # Web depolamaya yalnız sürüm ve imleç yazılır; harici kaynak, service worker, Cache API yok.
    assert re.findall(r"write\(\"(\w+)\", (\w+)", script) and {
        key for _, key in re.findall(r"write\(\"(\w+)\", (\w+)", script)
    } == {"VERSION_KEY", "CURSOR_KEY"}
    assert script.count("setItem(") == 1
    for forbidden in ("serviceWorker", "caches.", "http://", "https://", "/examples/", "innerHTML"):
        assert forbidden not in script, forbidden
