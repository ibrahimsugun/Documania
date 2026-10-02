"""10.10.1 arayüz dili — iskelet sayfalar: giriş sayfası, menü ve üst çubuk, eski sürüm uyarısı
(PLAN.md §D92 b, e, g; tm 152).

Açılış dili `Settings.panel_default_language`'tır (varsayılan İngilizce; test süreci Türkçe verir,
bu dosya ayarı her testte açıkça koyar). Girişsiz istekte geçerli `documania_lang` çerezi seçer;
tarayıcının `Accept-Language`'ı okunmaz. Girişli istekte hesabın tercihi geçerlidir; tercihi
olmayan hesapta varsayılan dil (hesap tercihi ve dil seçici `tests/web/test_language_preference.py`,
10.10.2).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.i18n import LANGUAGE_COOKIE
from app.i18n.request import use_request_language
from app.main import create_app
from app.web.auth import PanelUser, get_current_user, require_api_user, require_panel_user
from app.web.templating import PANEL_MENU, render_page, templates
from tests.i18n.residue import assert_no_turkish, turkish_residue
from tests.web.conftest import SIGNED_IN

MENU = {
    "en": [
        "Employees",
        "Upload",
        "Document types",
        "Document groups",
        "Queues",
        "Uploads",
        "Training mode",
        "Users",
    ],
    "tr": [
        "Çalışanlar",
        "Yükle",
        "Belge Türleri",
        "Belge Grupları",
        "Kuyruklar",
        "Yüklemeler",
        "Eğitim modu",
        "Kullanıcılar",
    ],
    "sr": [
        "Zaposleni",
        "Otpremi",
        "Tipovi dokumenata",
        "Grupe dokumenata",
        "Redovi",
        "Otpremanja",
        "Režim obuke",
        "Korisnici",
    ],
}
LOGIN = {
    "en": ("Sign in", "Username", "Password", "Incorrect username or password."),
    "tr": ("Giriş", "Kullanıcı adı", "Parola", "Kullanıcı adı veya parola hatalı."),
    "sr": ("Prijava", "Korisničko ime", "Lozinka", "Pogrešno korisničko ime ili lozinka."),
}
LOGIN_BUTTON = {"en": "Sign in", "tr": "Giriş yap", "sr": "Prijavi se"}
TOPBAR = {
    "en": ("Main menu", "Access log", "Sign out"),
    "tr": ("Ana menü", "Erişim logu", "Çıkış"),
    "sr": ("Glavni meni", "Dnevnik pristupa", "Odjava"),
}
BANNER = {
    "en": "The server is running an outdated version — restart it (<code>baslat.bat</code>).",
    "tr": "Sunucu eski sürümle çalışıyor — yeniden başlatın (<code>baslat.bat</code>).",
    "sr": "Server radi sa zastarelom verzijom — ponovo ga pokrenite (<code>baslat.bat</code>).",
}
HTML_LANG = {"en": "en", "tr": "tr", "sr": "sr-Latn"}
LANGUAGES = ["en", "tr", "sr"]
SKELETON = "/_dil-iskelet"
UNMARKED = "/_dil-isaretsiz"


class _StaleCode:
    def is_stale(self) -> bool:
        return True


def _default_language(app: FastAPI, language: str | None) -> None:
    """Açılış dilini koyar; `None`: ayar verilmemiş (`.env` ve ortam okunmaz)."""
    overrides = {} if language is None else {"panel_default_language": language}
    settings = Settings(_env_file=None, database_url="sqlite://", **overrides)
    app.dependency_overrides[get_settings] = lambda: settings


@pytest.fixture
def anonymous(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Gerçek oturum denetimiyle istemci; açılış dili ayarsız (varsayılan)."""
    monkeypatch.delenv("PANEL_DEFAULT_LANGUAGE", raising=False)
    del app.dependency_overrides[get_current_user]
    _default_language(app, None)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def probe(app: FastAPI) -> FastAPI:
    """Panel yönlendiricileriyle aynı bağımlılıklarla iki deneme yolu: yalnız iskelet
    (`base.html`, boş içerik, eski sürüm uyarısı açık) ve içeriği testin verdiği şablon parçası
    olan bir sayfa (`app.state.probe_content`)."""
    router = APIRouter()

    @router.get(SKELETON, response_class=HTMLResponse)
    def skeleton(
        request: Request, user: Annotated[PanelUser, Depends(require_panel_user)]
    ) -> HTMLResponse:
        return render_page(request, "base.html", user=user, active="employees")

    @router.get(UNMARKED, response_class=HTMLResponse)
    def unmarked(
        request: Request, user: Annotated[PanelUser, Depends(require_panel_user)]
    ) -> HTMLResponse:
        page = templates.env.from_string(
            '{% extends "base.html" %}{% block content %}'
            + request.app.state.probe_content
            + "{% endblock %}"
        )
        return templates.TemplateResponse(request, page, {"user": user, "active": None})

    app.include_router(router, dependencies=[Depends(use_request_language)])
    app.state.code_watch = _StaleCode()
    return app


def _menu(html: str) -> list[tuple[str, str]]:
    nav = re.search(r'<nav class="menu"[^>]*>(.*?)</nav>', html, re.DOTALL)
    assert nav is not None
    return re.findall(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', nav.group(1))


# --- açılış dili --------------------------------------------------------------------------------


def test_login_page_opens_in_english_when_no_language_is_configured(
    anonymous: TestClient,
) -> None:
    response = anonymous.get("/login")

    assert response.status_code == 200
    assert '<html lang="en">' in response.text
    assert "<title>Sign in · Documania</title>" in response.text
    assert '<label for="username">Username</label>' in response.text
    assert '<label for="password">Password</label>' in response.text
    assert '<button type="submit">Sign in</button>' in response.text
    assert_no_turkish(response.text, "en")


@pytest.mark.parametrize("language", LANGUAGES)
def test_login_page_in_the_configured_default_language(
    app: FastAPI, anonymous: TestClient, language: str
) -> None:
    _default_language(app, language)

    response = anonymous.get("/login")

    title, username, password, _ = LOGIN[language]
    assert f'<html lang="{HTML_LANG[language]}">' in response.text
    assert f"<title>{title} · Documania</title>" in response.text
    assert f'<label for="username">{username}</label>' in response.text
    assert f'<label for="password">{password}</label>' in response.text
    assert f'<button type="submit">{LOGIN_BUTTON[language]}</button>' in response.text


@pytest.mark.parametrize("accept", ["tr", "sr", "sr-Latn,sr;q=0.9", "tr-TR,tr;q=0.9,en;q=0.5"])
def test_browser_language_is_ignored(anonymous: TestClient, accept: str) -> None:
    response = anonymous.get("/login", headers={"Accept-Language": accept})

    assert '<html lang="en">' in response.text
    assert '<button type="submit">Sign in</button>' in response.text


# --- dil çerezi ---------------------------------------------------------------------------------


@pytest.mark.parametrize("language", LANGUAGES)
def test_language_cookie_chooses_the_login_page_language(
    anonymous: TestClient, language: str
) -> None:
    anonymous.cookies.set(LANGUAGE_COOKIE, language)

    response = anonymous.get("/login", headers={"Accept-Language": "tr"})

    assert f'<html lang="{HTML_LANG[language]}">' in response.text
    assert f'<button type="submit">{LOGIN_BUTTON[language]}</button>' in response.text


@pytest.mark.parametrize("cookie", ["de", "SR", "sr-Latn", "", "tr-TR", "english"])
def test_invalid_language_cookie_falls_back_to_the_default(
    app: FastAPI, anonymous: TestClient, cookie: str
) -> None:
    anonymous.cookies.set(LANGUAGE_COOKIE, cookie)

    assert '<html lang="en">' in anonymous.get("/login").text

    _default_language(app, "sr")
    assert '<html lang="sr-Latn">' in anonymous.get("/login").text


@pytest.mark.parametrize("language", LANGUAGES)
def test_failed_login_message_is_in_the_page_language(anonymous: TestClient, language: str) -> None:
    anonymous.cookies.set(LANGUAGE_COOKIE, language)

    response = anonymous.post(
        "/login", data={"username": "yok-kullanici", "password": "yanlis-parola-1", "next": "/"}
    )

    assert response.status_code == 401
    assert f'<p class="error" role="alert">{LOGIN[language][3]}</p>' in response.text
    assert f'<html lang="{HTML_LANG[language]}">' in response.text


def test_signed_in_request_uses_the_default_not_the_cookie(
    app: FastAPI, client: TestClient
) -> None:
    # Tercihi olmayan hesap (10.10.2): girişli istekte dil varsayılandır, çerez okunmaz.
    _default_language(app, "en")
    client.cookies.set(LANGUAGE_COOKIE, "sr")

    response = client.get("/employees")

    assert response.status_code == 200
    assert '<html lang="en">' in response.text
    assert [label for _, label in _menu(response.text)] == MENU["en"]


# --- menü ve üst çubuk --------------------------------------------------------------------------


@pytest.mark.parametrize("language", LANGUAGES)
def test_menu_labels_in_each_language_keep_the_order(
    app: FastAPI, client: TestClient, language: str
) -> None:
    _default_language(app, language)

    response = client.get("/employees")

    assert response.status_code == 200
    assert _menu(response.text) == list(
        zip([entry.path for entry in PANEL_MENU], MENU[language], strict=True)
    )
    assert f'<html lang="{HTML_LANG[language]}">' in response.text


@pytest.mark.parametrize("language", LANGUAGES)
def test_topbar_and_stale_banner_in_each_language(
    probe: FastAPI, client: TestClient, language: str
) -> None:
    _default_language(probe, language)

    response = client.get(SKELETON)

    assert response.status_code == 200
    menu_label, access_log, sign_out = TOPBAR[language]
    assert f'<nav class="menu" aria-label="{menu_label}">' in response.text
    assert f'href="/access-log">{access_log}</a>' in response.text
    assert f'<button type="submit">{sign_out}</button>' in response.text
    assert f'<span class="username" translate="no">{SIGNED_IN.username}</span>' in response.text
    assert f'<div class="stale-process" role="alert">{BANNER[language]}</div>' in response.text
    assert "<title>Panel · Documania</title>" in response.text


# --- Türkçe kalıntı taraması (§D92 g) -----------------------------------------------------------


@pytest.mark.parametrize("language", ["en", "sr"])
def test_skeleton_has_no_turkish_residue(probe: FastAPI, client: TestClient, language: str) -> None:
    _default_language(probe, language)

    response = client.get(SKELETON)

    assert response.status_code == 200
    assert_no_turkish(response.text, language)


@pytest.mark.parametrize("language", ["en", "sr"])
def test_login_pages_have_no_turkish_residue(anonymous: TestClient, language: str) -> None:
    anonymous.cookies.set(LANGUAGE_COOKIE, language)

    login = anonymous.get("/login")
    failed = anonymous.post("/login", data={"username": "yok-kullanici", "password": "x" * 12})

    assert (login.status_code, failed.status_code) == (200, 401)
    assert_no_turkish(login.text, language)
    assert_no_turkish(failed.text, language)


@pytest.mark.parametrize(
    "unmarked", ["<p>Çalışan bulunamadı</p>", "<button>Kaydet</button>", "<p>{{ _('Yeni') }}</p>"]
)
def test_unmarked_turkish_text_on_an_english_page_turns_the_scan_red(
    probe: FastAPI, client: TestClient, unmarked: str
) -> None:
    _default_language(probe, "en")
    # İşaretli ve çevrilmiş metin geçer; `translate="no"` öğesindeki veri taranmaz.
    probe.state.probe_content = '<p>{{ _("Çıkış") }}</p><p translate="no">Ayşe Yılmaz</p>'
    clean = client.get(UNMARKED)
    assert "<p>Sign out</p>" in clean.text
    assert turkish_residue(clean.text) == []

    # İşaretlenmemiş (ya da işaretli ama kataloğa girmemiş) Türkçe metin eklenince kırmızı.
    probe.state.probe_content = clean_content = unmarked
    red = client.get(UNMARKED)
    assert red.status_code == 200
    assert turkish_residue(red.text) != [], clean_content


# --- bağlanış -----------------------------------------------------------------------------------


def _routes(application: FastAPI) -> dict[str, list[object]]:
    """Uygulamanın her yolu → bağımlılık fonksiyonları. FastAPI içerilen yönlendiricileri ayrı
    tutar (`_IncludedRouter`); yönlendirici düzeyindeki bağımlılıklar yolun etkin bağlamındadır."""
    routes: dict[str, list[object]] = {}
    for route in application.routes:
        contexts = (
            route.effective_route_contexts()
            if hasattr(route, "effective_route_contexts")
            else [route]
            if isinstance(route, APIRoute)
            else []
        )
        for context in contexts:
            key = f"{','.join(sorted(context.methods))} {context.path}"
            routes[key] = [dependency.call for dependency in context.dependant.dependencies]
    return routes


def test_every_page_route_resolves_the_request_language() -> None:
    # Sayfa sunan her yol (giriş dahil) dili çözer; JSON API (`require_api_user`) ve `/health`
    # çevrilmez, dili çözmez.
    routes = _routes(create_app())
    pages = {key: calls for key, calls in routes.items() if require_api_user not in calls}
    api = {key: calls for key, calls in routes.items() if require_api_user in calls}

    assert len(pages) > 100 and len(api) >= 6
    assert {"GET /login", "POST /login", "POST /logout", "GET /users", "GET /employees"} <= set(
        pages
    )
    assert [key for key, calls in pages.items() if use_request_language not in calls] == [
        "GET /health"
    ]
    assert [key for key, calls in api.items() if use_request_language in calls] == []
    assert routes["GET /health"] == []
