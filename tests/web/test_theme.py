"""10.1.7 — panel teması (PLAN.md §D111): `theme.css` panel.css'ten sonra yüklenir, açık/koyu
tema düğmesi her sayfada dil seçicinin yanında, üst çubuğun altındaki araç alanındadır; seçim
ilk boyamadan önce uygulanır. Yalnız görünüm."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
THEME = ROOT / "app" / "web" / "static" / "theme.css"


def test_every_page_loads_the_theme_after_the_panel_styles(client: TestClient) -> None:
    page = client.get("/employees").text

    assert page.index('href="/static/panel.css?v=') < page.index('href="/static/theme.css?v=')
    assert re.search(r'<script src="/static/theme\.js\?v=[0-9a-f]{12}" defer></script>', page)
    # Seçim ilk boyamadan önce: engelleyici (defer'siz) betik başlıkta; satır içi betik yok.
    head = page[: page.index("</head>")]
    assert re.search(r'<script src="/static/theme-init\.js\?v=[0-9a-f]{12}"></script>', head)
    assert "<script>" not in page


def test_the_page_tools_have_a_labelled_theme_toggle(client: TestClient) -> None:
    page = client.get("/employees").text
    topbar = page[page.index('<header class="topbar">') : page.index("</header>")]
    tools = page[page.index('<div class="page-tools">') : page.index("<main")]

    assert "data-theme-toggle" not in topbar
    assert 'class="theme-toggle" data-theme-toggle aria-pressed="false"' in tools
    assert 'aria-label="Açık ya da koyu tema"' in page


def test_the_login_page_gets_the_theme_without_a_toggle(app) -> None:  # noqa: ANN001
    from app.web.auth import get_current_user

    del app.dependency_overrides[get_current_user]
    page = TestClient(app).get("/login").text

    assert 'href="/static/theme.css?v=' in page
    assert "data-theme-toggle" not in page
    app.dependency_overrides.clear()


def test_theme_files_are_served_without_a_session(app) -> None:  # noqa: ANN001
    from app.web.auth import get_current_user

    del app.dependency_overrides[get_current_user]
    anonymous = TestClient(app)

    for path in ("/static/theme.css", "/static/theme.js", "/static/theme-init.js"):
        assert anonymous.get(path).status_code == 200, path
    app.dependency_overrides.clear()


def test_the_theme_defines_light_and_dark_tokens_and_respects_reduced_motion() -> None:
    css = THEME.read_text(encoding="utf-8")

    assert css.count("--accent:") == 2  # açık ve koyu
    assert 'html[data-theme="dark"]' in css
    assert "prefers-reduced-motion: reduce" in css


def test_own_assets_carry_a_content_version_so_caches_refresh(client: TestClient) -> None:
    from app.web.templating import VERSIONED_ASSETS

    page = client.get("/employees").text
    versions = {
        name: re.search(rf'/static/{re.escape(name)}\?v=([0-9a-f]{{12}})"', page)
        for name in VERSIONED_ASSETS
    }

    assert all(versions.values()), versions
    assert len({match.group(1) for match in versions.values() if match}) == 1


# --- 10.1.12: yaşlı ve az gören kullanıcı için okunabilirlik -----------------------------------

PANEL_CSS = ROOT / "app" / "web" / "static" / "panel.css"


def test_the_page_tools_have_a_labelled_large_text_toggle(client: TestClient) -> None:
    page = client.get("/employees").text
    tools = page[page.index('<div class="page-tools">') : page.index("<main")]

    assert 'class="text-toggle" data-text-toggle aria-pressed="false"' in tools
    assert 'aria-label="Büyük yazı"' in tools
    # Seçim ilk boyamadan önce uygulanır; düğme theme.js'te okunur.
    init = (ROOT / "app" / "web" / "static" / "theme-init.js").read_text(encoding="utf-8")
    script = (ROOT / "app" / "web" / "static" / "theme.js").read_text(encoding="utf-8")
    assert 'localStorage.getItem("documania-text")' in init
    assert "data-text-toggle" in script


def test_every_page_offers_a_skip_link_to_the_content(client: TestClient) -> None:
    page = client.get("/employees").text

    assert '<a class="skip-link" href="#content-start">İçeriğe atla</a>' in page
    assert page.index('class="skip-link"') < page.index('<header class="topbar">')
    assert '<span id="content-start" class="content-start" tabindex="-1"></span>' in page


def test_the_styles_keep_text_and_targets_readable() -> None:
    css = PANEL_CSS.read_text(encoding="utf-8")
    root = css[css.index(":root {") : css.index("}", css.index(":root {"))]
    sizes = dict(re.findall(r"(--text-[a-z]+):\s*([\d.]+)rem", root))

    assert float(sizes["--text-base"]) >= 1.0  # gövde 16 px
    assert float(sizes["--text-xs"]) >= 0.8125  # en küçük metin 13 px
    assert 'html[data-text="large"] { font-size: 120%; }' in css
    assert re.search(r"--target:\s*2\.5rem", root)  # tıklama hedefi 40 px
    assert "prefers-contrast: more" in css
    # Odak halkası düz ve kalın; yalnız gölgeye bırakılmaz.
    assert "outline: 3px solid var(--focus-ring)" in css
    theme = THEME.read_text(encoding="utf-8")
    assert theme.count("--focus-ring:") == 2
