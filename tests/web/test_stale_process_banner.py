"""13.5.3 — eski süreç uyarısı: kod ya da şablon açılıştan sonra değiştiyse her panel sayfasının
üstünde "Sunucu eski sürümle çalışıyor — yeniden başlatın" yazar (tm 141, PLAN.md §D77)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web.auth import get_current_user
from app.web.code_watch import CodeWatch

BANNER = "Sunucu eski sürümle çalışıyor — yeniden başlatın"


@pytest.fixture
def code_tree(tmp_path: Path) -> Path:
    root = tmp_path / "kod"
    (root / "web" / "templates").mkdir(parents=True)
    (root / "main.py").write_text("x = 1\n", encoding="utf-8")
    (root / "web" / "templates" / "profile.html").write_text("<p>a</p>\n", encoding="utf-8")
    return root


def _touch(path: Path) -> None:
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))


def _watch(app: FastAPI, root: Path) -> None:
    # Testte 30 sn beklenmez: her istek yeniden hesaplar.
    app.state.code_watch = CodeWatch(root, recheck_seconds=0)


@pytest.mark.parametrize("path", ["/employees", "/users", "/queues"])
def test_unchanged_code_shows_no_banner(
    app: FastAPI, client: TestClient, code_tree: Path, path: str
) -> None:
    _watch(app, code_tree)

    response = client.get(path)

    assert response.status_code == 200
    assert BANNER not in response.text


@pytest.mark.parametrize("path", ["/employees", "/users", "/queues"])
def test_a_template_changed_after_startup_shows_the_banner_on_every_page(
    app: FastAPI, client: TestClient, code_tree: Path, path: str
) -> None:
    _watch(app, code_tree)
    _touch(code_tree / "web" / "templates" / "profile.html")

    response = client.get(path)

    assert response.status_code == 200
    assert BANNER in response.text
    assert "baslat.bat" in response.text
    assert 'class="stale-process" role="alert"' in response.text


def test_a_changed_module_shows_the_banner(
    app: FastAPI, client: TestClient, code_tree: Path
) -> None:
    _watch(app, code_tree)
    _touch(code_tree / "main.py")

    assert BANNER in client.get("/employees").text


def test_the_login_page_shows_the_banner_too(
    app: FastAPI, client: TestClient, code_tree: Path
) -> None:
    app.dependency_overrides[get_current_user] = lambda: None
    _watch(app, code_tree)
    _touch(code_tree / "main.py")

    response = client.get("/login")

    assert response.status_code == 200
    assert BANNER in response.text


def test_a_failing_check_does_not_break_the_page(app: FastAPI, client: TestClient) -> None:
    class BrokenWatch:
        def is_stale(self) -> bool:
            raise RuntimeError("parmak izi okunamadı")

    app.state.code_watch = BrokenWatch()

    response = client.get("/employees")

    assert response.status_code == 200
    assert BANNER not in response.text


def test_the_real_app_package_is_not_stale_right_after_startup(client: TestClient) -> None:
    response = client.get("/employees")

    assert response.status_code == 200
    assert BANNER not in response.text
