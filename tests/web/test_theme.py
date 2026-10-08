"""10.1.7 — panel teması (PLAN.md §D111): `theme.css` panel.css'ten sonra yüklenir, açık/koyu
tema düğmesi her sayfanın üst çubuğundadır, seçim ilk boyamadan önce uygulanır. Yalnız görünüm."""

from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
THEME = ROOT / "app" / "web" / "static" / "theme.css"


def test_every_page_loads_the_theme_after_the_panel_styles(client: TestClient) -> None:
    page = client.get("/employees").text

    assert page.index('href="/static/panel.css"') < page.index('href="/static/theme.css"')
    assert '<script src="/static/theme.js" defer></script>' in page
    # Seçim ilk boyamadan önce: satır içi betik theme.js'ten önce ve başlıkta.
    head = page[: page.index("</head>")]
    assert 'localStorage.getItem("documania-theme")' in head


def test_the_topbar_has_a_labelled_theme_toggle(client: TestClient) -> None:
    page = client.get("/employees").text

    assert 'class="theme-toggle" data-theme-toggle aria-pressed="false"' in page
    assert 'aria-label="Açık ya da koyu tema"' in page


def test_the_login_page_gets_the_theme_without_a_toggle(app) -> None:  # noqa: ANN001
    from app.web.auth import get_current_user

    del app.dependency_overrides[get_current_user]
    page = TestClient(app).get("/login").text

    assert 'href="/static/theme.css"' in page
    assert "data-theme-toggle" not in page
    app.dependency_overrides.clear()


def test_theme_files_are_served_without_a_session(app) -> None:  # noqa: ANN001
    from app.web.auth import get_current_user

    del app.dependency_overrides[get_current_user]
    anonymous = TestClient(app)

    for path in ("/static/theme.css", "/static/theme.js"):
        assert anonymous.get(path).status_code == 200, path
    app.dependency_overrides.clear()


def test_the_theme_defines_light_and_dark_tokens_and_respects_reduced_motion() -> None:
    css = THEME.read_text(encoding="utf-8")

    assert css.count("--accent:") == 2  # açık ve koyu
    assert 'html[data-theme="dark"]' in css
    assert "prefers-reduced-motion: reduce" in css
