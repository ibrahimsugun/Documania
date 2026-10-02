"""10.10.2 kullanıcının dil tercihi — hesapta saklama, dil seçici, girişte otomatik dil (PLAN.md
§D92 c, d; tm 153).

Girişli kullanıcı dil seçicide dil seçince tercih `users.language`'e yazılır,
`USER_LANGUAGE_CHANGED` kullanıcının kendi adıyla düşer (dil aynıysa olay yok) ve aynı sayfaya
dönülür. Sonraki her girişte panel o dilde açılır — çerezden bağımsız, yani cihazdan bağımsız.
Tercihi olmayan hesap varsayılan dilde açılır; giriş sayfasında seçilmiş dil (çerez) tercihi
olmayan hesaba girişte kaydedilir. Açılış dili her testte açıkça İngilizce verilir (test süreci
Türkçe varsayar).
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.config import Settings, get_settings
from app.db.models import Event, User
from app.events import EventType
from app.i18n import LANGUAGE_COOKIE, SUPPORTED_LANGUAGES
from app.i18n.request import LANGUAGE_COOKIE_MAX_AGE
from app.web.auth import (
    LANGUAGE_VIA_LOGIN,
    LANGUAGE_VIA_SELECTOR,
    SESSION_COOKIE,
    create_user,
    get_current_user,
    open_session,
    resolve_session,
    set_user_language,
)
from app.web.templating import language_return_path
from tests.i18n.residue import assert_no_turkish

USERNAME = "dil-kullanici"
PASSWORD = "gizli-parola-12"
OTHER = "diger-kullanici"
HTML_LANG = {"en": "en", "tr": "tr", "sr": "sr-Latn"}
SIGN_OUT = {"en": "Sign out", "tr": "Çıkış", "sr": "Odjava"}
SELECTOR_LABEL = {"en": "Language", "tr": "Dil", "sr": "Jezik"}
LOGIN_BUTTON = {"en": "Sign in", "tr": "Giriş yap", "sr": "Prijavi se"}


def _settings(app: FastAPI, **overrides: object) -> None:
    settings = Settings(
        _env_file=None, database_url="sqlite://", panel_default_language="en", **overrides
    )
    app.dependency_overrides[get_settings] = lambda: settings


@pytest.fixture
def user(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        created = create_user(session, USERNAME, PASSWORD)
        create_user(session, OTHER, PASSWORD)
        session.commit()
        return created.id


@pytest.fixture
def browser(app: FastAPI, user: int) -> Iterator[TestClient]:
    """Gerçek oturum denetimiyle, çerezsiz bir tarayıcı; açılış dili İngilizce."""
    del app.dependency_overrides[get_current_user]
    _settings(app)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _new_browser(app: FastAPI) -> TestClient:
    """Aynı uygulamaya başka bir cihaz: çerez kavanozu boş."""
    return TestClient(app)


def _login(client: TestClient, next_path: str = "/employees"):
    response = client.post(
        "/login",
        data={"username": USERNAME, "password": PASSWORD, "next": next_path},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return response


def _choose(client: TestClient, language: str, next_path: str = "/employees"):
    return client.post(
        "/language", data={"language": language, "next": next_path}, follow_redirects=False
    )


def _account_language(session_factory: sessionmaker[Session], username: str = USERNAME):
    with session_factory() as session:
        return session.scalar(select(User.language).where(User.username == username))


def _language_events(session_factory: sessionmaker[Session]) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event)
                .where(Event.type == EventType.USER_LANGUAGE_CHANGED.value)
                .order_by(Event.id)
            )
        )


def _language_cookies(response) -> list[str]:
    return [
        header
        for header in response.headers.get_list("set-cookie")
        if header.startswith(f"{LANGUAGE_COOKIE}=")
    ]


def _page_language(html: str) -> str:
    match = re.search(r'<html lang="([^"]+)">', html)
    assert match is not None
    return {value: code for code, value in HTML_LANG.items()}[match.group(1)]


def _selector(html: str) -> str:
    match = re.search(r'<form class="language-selector".*?</form>', html, re.DOTALL)
    assert match is not None, "dil seçici yok"
    return match.group(0)


# --- seçici: girişli kullanıcı ------------------------------------------------------------------


def test_signed_in_user_switches_to_serbian_and_stays_on_the_same_page(
    browser: TestClient, session_factory: sessionmaker[Session], user: int
) -> None:
    _login(browser)
    assert _page_language(browser.get("/employees?q=ana").text) == "en"

    response = _choose(browser, "sr", "/employees?q=ana")

    assert response.status_code == 303
    assert response.headers["location"] == "/employees?q=ana"
    page = browser.get(response.headers["location"])
    assert _page_language(page.text) == "sr"
    # Sayfa içeriğinin çevirisi 10.10-c'nin işi; üst çubuk bu görevde çevrili.
    assert f'<button type="submit">{SIGN_OUT["sr"]}</button>' in page.text
    assert _account_language(session_factory) == "sr"
    assert _account_language(session_factory, OTHER) is None
    (event,) = _language_events(session_factory)
    assert event.actor == USERNAME
    assert event.data_json == {"target_user_id": user, "language": "sr", "via": "selector"}


def test_choosing_the_same_language_again_writes_no_event(
    browser: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _login(browser)
    assert _choose(browser, "tr").status_code == 303

    again = _choose(browser, "tr")

    assert again.status_code == 303
    assert _language_cookies(again)  # çerez yine yenilenir
    assert _account_language(session_factory) == "tr"
    assert [e.data_json["language"] for e in _language_events(session_factory)] == ["tr"]


def test_each_change_is_an_event_and_the_last_choice_wins(
    browser: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _login(browser)

    for language in ("sr", "en", "tr"):
        assert _choose(browser, language).status_code == 303

    assert _account_language(session_factory) == "tr"
    events = _language_events(session_factory)
    assert [e.data_json["language"] for e in events] == ["sr", "en", "tr"]
    assert {e.data_json["via"] for e in events} == {LANGUAGE_VIA_SELECTOR}
    assert _page_language(browser.get("/employees").text) == "tr"


def test_selector_cookie_is_http_only_lax_for_a_year_and_not_secure_in_development(
    browser: TestClient,
) -> None:
    response = _choose(browser, "sr", "/login")

    (cookie,) = _language_cookies(response)
    assert cookie.startswith(f"{LANGUAGE_COOKIE}=sr;")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert f"Max-Age={LANGUAGE_COOKIE_MAX_AGE}" in cookie and LANGUAGE_COOKIE_MAX_AGE == 31536000
    assert "Path=/" in cookie
    assert "Secure" not in cookie


def test_selector_cookie_is_secure_in_production(app: FastAPI, browser: TestClient) -> None:
    _settings(app, app_env="production")

    (cookie,) = _language_cookies(_choose(browser, "tr", "/login"))

    assert "Secure" in cookie


# --- girişte dil (cihazdan bağımsız) ------------------------------------------------------------


def test_next_sign_in_on_a_fresh_browser_opens_in_the_chosen_language(
    app: FastAPI, browser: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _login(browser)
    _choose(browser, "sr")
    browser.post("/logout")

    device = _new_browser(app)
    assert _page_language(device.get("/login").text) == "en"  # çerezsiz: açılış İngilizce
    response = _login(device)

    assert _language_cookies(response) and _language_cookies(response)[0].startswith(
        f"{LANGUAGE_COOKIE}=sr;"
    )
    page = device.get("/employees")
    assert _page_language(page.text) == "sr"
    assert f'<button type="submit">{SIGN_OUT["sr"]}</button>' in page.text
    # Girişte yeniden yazılmadı: tek olay seçicinin olayı.
    assert [e.data_json["via"] for e in _language_events(session_factory)] == ["selector"]
    # Çıkıştan sonra giriş sayfası kullanıcının dilinde açılır (çerez hesabın diliyle yenilendi).
    device.post("/logout")
    assert _page_language(device.get("/login").text) == "sr"


def test_login_page_choice_is_saved_to_an_account_without_a_preference(
    browser: TestClient, session_factory: sessionmaker[Session], user: int
) -> None:
    chosen = _choose(browser, "tr", "/login")
    assert chosen.status_code == 303
    assert _language_events(session_factory) == []  # oturumsuz: yalnız çerez

    response = _login(browser)

    assert _account_language(session_factory) == "tr"
    (event,) = _language_events(session_factory)
    assert event.actor == USERNAME
    assert event.data_json == {"target_user_id": user, "language": "tr", "via": LANGUAGE_VIA_LOGIN}
    assert _language_cookies(response)[0].startswith(f"{LANGUAGE_COOKIE}=tr;")
    assert _page_language(browser.get("/employees").text) == "tr"


def test_account_without_preference_and_without_cookie_opens_in_english_and_stays_empty(
    browser: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = _login(browser)

    assert _language_cookies(response) == []
    page = browser.get("/employees")
    assert _page_language(page.text) == "en"
    assert f'<button type="submit">{SIGN_OUT["en"]}</button>' in page.text
    assert _account_language(session_factory) is None
    assert _language_events(session_factory) == []


@pytest.mark.parametrize("cookie", ["de", "SR", "sr-Latn", "", "english"])
def test_invalid_cookie_is_not_saved_on_sign_in(
    browser: TestClient, session_factory: sessionmaker[Session], cookie: str
) -> None:
    browser.cookies.set(LANGUAGE_COOKIE, cookie)

    _login(browser)

    assert _account_language(session_factory) is None
    assert _language_events(session_factory) == []
    assert _page_language(browser.get("/employees").text) == "en"


def test_account_preference_beats_the_cookie_and_refreshes_it(
    browser: TestClient, session_factory: sessionmaker[Session], user: int
) -> None:
    with session_factory() as session:
        session.get_one(User, user).language = "tr"
        session.commit()
    browser.cookies.set(LANGUAGE_COOKIE, "sr")

    response = _login(browser)

    assert _language_cookies(response)[0].startswith(f"{LANGUAGE_COOKIE}=tr;")
    assert _page_language(browser.get("/employees").text) == "tr"
    assert _account_language(session_factory) == "tr"
    assert _language_events(session_factory) == []


def test_sign_in_language_cookie_is_secure_in_production(app: FastAPI, browser: TestClient) -> None:
    _settings(app, app_env="production")
    browser.cookies.set(LANGUAGE_COOKIE, "sr")

    (cookie,) = _language_cookies(_login(browser))

    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie


def test_failed_sign_in_saves_nothing(
    browser: TestClient, session_factory: sessionmaker[Session]
) -> None:
    browser.cookies.set(LANGUAGE_COOKIE, "sr")

    response = browser.post("/login", data={"username": USERNAME, "password": "yanlis-parola-9"})

    assert response.status_code == 401
    assert _language_cookies(response) == []
    assert _account_language(session_factory) is None
    assert _language_events(session_factory) == []


# --- seçici: oturumsuz --------------------------------------------------------------------------


@pytest.mark.parametrize("language", list(SUPPORTED_LANGUAGES))
def test_anonymous_choice_writes_only_the_cookie_and_the_login_page_follows_it(
    browser: TestClient, session_factory: sessionmaker[Session], language: str
) -> None:
    response = _choose(browser, language, "/login?next=%2Fqueues")

    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=%2Fqueues"
    assert browser.cookies[LANGUAGE_COOKIE] == language
    assert _language_events(session_factory) == []
    assert _account_language(session_factory) is None
    login = browser.get(response.headers["location"])
    assert _page_language(login.text) == language
    assert f'<button type="submit">{LOGIN_BUTTON[language]}</button>' in login.text
    assert 'name="next" value="/queues"' in login.text


# --- açık yönlendirme yok -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "next_path",
    [
        "//evil.example",
        "//evil.example/employees",
        "https://evil.example",
        "http://evil.example/login",
        "/\\evil.example",
        "/\\\\evil.example",
        "\\\\evil.example",
        "evil.example",
        "javascript:alert(1)",
        "",
        "/employees\r\nLocation: https://evil.example",
    ],
)
def test_selector_never_redirects_off_site(browser: TestClient, next_path: str) -> None:
    response = _choose(browser, "sr", next_path)

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_missing_next_returns_home(browser: TestClient) -> None:
    response = browser.post("/language", data={"language": "sr"}, follow_redirects=False)

    assert (response.status_code, response.headers["location"]) == (303, "/")


# --- geçersiz dil -------------------------------------------------------------------------------


@pytest.mark.parametrize("language", ["de", "SR", "sr-Latn", "", "tr-TR", "english", "en "])
def test_invalid_language_is_422_and_changes_nothing(
    browser: TestClient, session_factory: sessionmaker[Session], language: str
) -> None:
    _login(browser)
    _choose(browser, "tr")
    before = len(_language_events(session_factory))

    response = _choose(browser, language)

    assert response.status_code == 422
    assert _language_cookies(response) == []
    assert browser.cookies[LANGUAGE_COOKIE] == "tr"
    assert _account_language(session_factory) == "tr"
    assert len(_language_events(session_factory)) == before


def test_missing_language_is_422(browser: TestClient) -> None:
    response = browser.post("/language", data={"next": "/"}, follow_redirects=False)

    assert response.status_code == 422
    assert _language_cookies(response) == []


# --- başkasının dili değiştirilemez -------------------------------------------------------------


def test_only_the_signed_in_users_own_language_changes(
    browser: TestClient, session_factory: sessionmaker[Session], user: int
) -> None:
    with session_factory() as session:
        other_id = session.scalar(select(User.id).where(User.username == OTHER))
    _login(browser)

    # Hedef kullanıcıyı seçen bir alan yoktur; uydurma alanlar yok sayılır.
    response = browser.post(
        "/language",
        data={"language": "sr", "next": "/", "user_id": str(other_id), "username": OTHER},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert _account_language(session_factory) == "sr"
    assert _account_language(session_factory, OTHER) is None
    (event,) = _language_events(session_factory)
    assert event.data_json["target_user_id"] == user and event.actor == USERNAME


# --- seçicinin görünümü ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", list(SUPPORTED_LANGUAGES))
def test_topbar_selector_lists_languages_in_their_own_names_and_marks_the_current_one(
    browser: TestClient, language: str
) -> None:
    _login(browser)
    _choose(browser, language)

    page = browser.get("/employees?q=ana&page=2")

    selector = _selector(page.text)
    buttons = re.findall(
        r'<button type="submit" name="language" value="([a-z]+)" lang="([^"]+)"'
        r' translate="no"( aria-current="true" class="current")?>([^<]+)</button>',
        selector,
    )
    assert [(code, lang, name) for code, lang, _, name in buttons] == [
        ("en", "en", "English"),
        ("tr", "tr", "Türkçe"),
        ("sr", "sr-Latn", "Srpski"),
    ]
    assert [code for code, _, current, _ in buttons if current] == [language]
    assert '<form class="language-selector" method="post" action="/language">' in selector
    assert '<input type="hidden" name="next" value="/employees?q=ana&amp;page=2">' in selector
    assert SELECTOR_LABEL[language] in selector
    assert "<script" not in selector and "onclick" not in selector and "hx-" not in selector
    # Üst çubukta kullanıcı adının yanında.
    topbar = re.search(r'<header class="topbar">.*?</header>', page.text, re.DOTALL)
    assert topbar is not None and selector in topbar.group(0)
    assert topbar.group(0).index(selector) < topbar.group(0).index('class="username"')


@pytest.mark.parametrize("language", list(SUPPORTED_LANGUAGES))
def test_login_page_selector_sits_under_the_box_and_returns_to_the_login_page(
    browser: TestClient, language: str
) -> None:
    browser.cookies.set(LANGUAGE_COOKIE, language)

    page = browser.get("/login?next=%2Fqueues%3Ftab%3Dunknown")

    selector = _selector(page.text)
    login_box = re.search(r'<section class="login">.*?</section>', page.text, re.DOTALL)
    assert login_box is not None and selector in login_box.group(0)
    assert login_box.group(0).index('action="/login"') < login_box.group(0).index(selector)
    assert 'name="next" value="/login?next=%2Fqueues%3Ftab%3Dunknown"' in selector
    assert f'value="{language}" lang="{HTML_LANG[language]}" translate="no" aria-current' in (
        selector
    )


def test_failed_login_page_selector_keeps_the_requested_page(browser: TestClient) -> None:
    page = browser.post(
        "/login", data={"username": USERNAME, "password": "yanlis-parola-9", "next": "/queues"}
    )

    assert page.status_code == 401
    assert 'name="next" value="/login?next=%2Fqueues"' in _selector(page.text)


def test_htmx_fragments_have_no_selector(browser: TestClient) -> None:
    _login(browser)

    fragment = browser.get("/employees", params={"q": "ana"}, headers={"HX-Request": "true"})

    assert fragment.status_code == 200
    assert "language-selector" not in fragment.text
    assert "language-selector" in browser.get("/employees").text


@pytest.mark.parametrize("language", ["en", "sr"])
def test_pages_with_the_selector_have_no_turkish_residue(
    browser: TestClient, language: str
) -> None:
    browser.cookies.set(LANGUAGE_COOKIE, language)
    assert_no_turkish(browser.get("/login").text, language)


def test_stylesheet_styles_the_selector(browser: TestClient) -> None:
    css = browser.get("/static/panel.css").text

    assert 'form.language-selector button[type="submit"]' in css
    assert '[aria-current="true"]' in css


# --- çekirdek -----------------------------------------------------------------------------------


def _request(method: str, path: str, query: str = "") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query.encode(),
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )


def test_return_path_is_the_get_page_itself_and_home_after_a_form_post() -> None:
    assert language_return_path(_request("GET", "/employees")) == "/employees"
    assert language_return_path(_request("GET", "/employees", "q=a&page=2")) == (
        "/employees?q=a&page=2"
    )
    assert language_return_path(_request("POST", "/users")) == "/"


def test_session_carries_the_account_language(
    session_factory: sessionmaker[Session], user: int
) -> None:
    with session_factory() as session:
        account = session.get_one(User, user)
        token = open_session(session, account, max_age_seconds=600)
        session.commit()
        assert resolve_session(session, token).language is None

        assert set_user_language(session, account, "sr", via=LANGUAGE_VIA_SELECTOR)
        session.commit()
        resolved = resolve_session(session, token)
        assert resolved is not None and resolved.language == "sr"


def test_set_user_language_rejects_unknown_languages_and_sources(
    session_factory: sessionmaker[Session], user: int
) -> None:
    with session_factory() as session:
        account = session.get_one(User, user)
        with pytest.raises(ValueError, match="dil"):
            set_user_language(session, account, "de", via=LANGUAGE_VIA_SELECTOR)
        with pytest.raises(ValueError, match="kaynağı"):
            set_user_language(session, account, "sr", via="admin")
        assert account.language is None
        assert set_user_language(session, account, "en", via=LANGUAGE_VIA_LOGIN) is True
        assert set_user_language(session, account, "en", via=LANGUAGE_VIA_LOGIN) is False


def test_session_cookie_name_is_unchanged() -> None:
    # Dil çerezi oturum çerezinden ayrıdır; ikisi aynı adı paylaşmaz.
    assert LANGUAGE_COOKIE == "documania_lang" and SESSION_COOKIE != LANGUAGE_COOKIE
