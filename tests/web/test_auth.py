"""10.1.1 panel iskeleti ve gezinme · 10.1.2 oturum tabanlı giriş.

Parola argon2 özetiyle, oturum sunucuda (`user_sessions`, belirtecin yalnız özeti) tutulur; girişsiz
hiçbir panel yolu açılmaz: sayfalar giriş sayfasına yönlendirir, API 401 döner.
"""

import re
from collections.abc import Iterator
from datetime import timedelta

import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db.models import User, UserRole, UserSession, utcnow
from app.web.auth import (
    SESSION_COOKIE,
    PanelUser,
    UserCreationError,
    UserStatusError,
    authenticate,
    close_session,
    close_user_sessions,
    create_user,
    get_current_user,
    login_url,
    open_session,
    resolve_session,
    safe_next_path,
    set_user_active,
)
from app.web.templating import PANEL_MENU

USERNAME = "yonetici"
PASSWORD = "gizli-parola-1"
# PRD 10.1.1 menüsü; "Belge Grupları" tm 124 (14.1.1) ile, "Kullanıcılar" tm 134 (10.1.4) ile geldi
# (§D62).
MENU_LABELS = [
    "Çalışanlar",
    "Yükle",
    "Belge Türleri",
    "Belge Grupları",
    "Kuyruklar",
    "Yüklemeler",
    "Eğitim modu",
    "Kullanıcılar",
]
MENU_PATHS = [
    "/employees",
    "/upload",
    "/document-types",
    "/document-groups",
    "/queues",
    "/uploads",
    "/training",
    "/users",
]
# Oturumsuz açılabilen tek yollar (10.1.2): giriş/çıkış, giriş sayfasındaki dil seçici (10.10.2)
# ve kapsayıcı sağlık denetimi.
PUBLIC_OPERATIONS = {
    ("GET", "/login"),
    ("POST", "/login"),
    ("POST", "/logout"),
    ("POST", "/language"),
    ("GET", "/health"),
}


@pytest.fixture
def admin(session_factory: sessionmaker[Session]) -> User:
    with session_factory() as session:
        user = create_user(session, USERNAME, PASSWORD)
        session.commit()
        return user


@pytest.fixture
def anonymous(app: FastAPI) -> Iterator[TestClient]:
    """Gerçek oturum denetimiyle istemci: conftest'in hazır kullanıcısı kaldırılır."""
    del app.dependency_overrides[get_current_user]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _login(client: TestClient, password: str = PASSWORD, next_path: str = "/upload") -> str:
    response = client.post(
        "/login",
        data={"username": USERNAME, "password": password, "next": next_path},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return response.headers["location"]


def _sessions(session_factory: sessionmaker[Session]) -> list[UserSession]:
    with session_factory() as session:
        return list(session.scalars(select(UserSession).order_by(UserSession.id)))


def _operations(app: FastAPI) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }


# --- parola ve kullanıcı ----------------------------------------------------------------------


def test_create_user_stores_only_an_argon2_hash(
    session_factory: sessionmaker[Session], admin: User
) -> None:
    with session_factory() as session:
        stored = session.scalars(select(User)).one()

    assert stored.username == USERNAME
    assert stored.role == UserRole.HR
    assert stored.password_hash.startswith("$argon2id$")
    assert PASSWORD not in stored.password_hash
    assert PasswordHasher().verify(stored.password_hash, PASSWORD)


@pytest.mark.parametrize(
    ("username", "password", "message"),
    [
        (USERNAME, PASSWORD, "zaten kullanılıyor"),
        (f"  {USERNAME} ", PASSWORD, "zaten kullanılıyor"),
        ("   ", PASSWORD, "boş olamaz"),
        ("ad soyad", PASSWORD, "boşluk"),
        ("ad\x00", PASSWORD, "denetim"),
        ("a" * 151, PASSWORD, "en çok 150"),
        ("baska", "kisa", "en az 12"),
        ("baska", "on-bir-harf", "en az 12"),
        ("ab", PASSWORD, "en az 3"),
    ],
)
def test_create_user_rejects_invalid_or_taken_names_and_short_passwords(
    session_factory: sessionmaker[Session],
    admin: User,
    username: str,
    password: str,
    message: str,
) -> None:
    with session_factory() as session, pytest.raises(UserCreationError, match=message):
        create_user(session, username, password)


def test_authenticate_accepts_only_the_right_password(
    session_factory: sessionmaker[Session], admin: User
) -> None:
    with session_factory() as session:
        found = authenticate(session, f" {USERNAME} ", PASSWORD)
        assert found is not None and found.id == admin.id
        assert authenticate(session, USERNAME, PASSWORD + "x") is None
        assert authenticate(session, USERNAME, "") is None
        assert authenticate(session, "olmayan", PASSWORD) is None
        assert authenticate(session, USERNAME.upper(), PASSWORD) is None


def test_authenticate_rehashes_a_hash_made_with_outdated_parameters(
    session_factory: sessionmaker[Session],
) -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    with session_factory() as session:
        session.add(User(username=USERNAME, password_hash=weak, role=UserRole.HR.value))
        session.commit()
        user = authenticate(session, USERNAME, PASSWORD)
        assert user is not None
        session.commit()

    with session_factory() as session:
        rehashed = session.scalars(select(User.password_hash)).one()
    assert rehashed != weak
    assert not PasswordHasher().check_needs_rehash(rehashed)
    assert PasswordHasher().verify(rehashed, PASSWORD)


def test_a_broken_stored_hash_fails_closed(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(User(username=USERNAME, password_hash="bozuk", role="hr"))
        session.commit()
        assert authenticate(session, USERNAME, PASSWORD) is None


def test_authenticate_refuses_an_inactive_user_even_with_the_right_password(
    session_factory: sessionmaker[Session], admin: User
) -> None:
    # 10.1.4: pasif kullanıcı giriş yapamaz; sonuç yanlış parolanınkiyle aynıdır (`None`).
    with session_factory() as session:
        stored = session.get(User, admin.id)
        assert stored is not None
        stored.active = False
        session.commit()
        assert authenticate(session, USERNAME, PASSWORD) is None


# --- oturum -----------------------------------------------------------------------------------


def test_session_of_an_inactive_user_does_not_resolve(
    session_factory: sessionmaker[Session], admin: User
) -> None:
    # Oturum denetimi `users.active`'i her istekte okur: kapanmamış oturum da geçersizdir.
    with session_factory() as session:
        token = open_session(session, admin, max_age_seconds=3600)
        session.commit()
        assert resolve_session(session, token) is not None
        stored = session.get(User, admin.id)
        assert stored is not None
        stored.active = False
        session.commit()
        assert resolve_session(session, token) is None


def test_close_user_sessions_keeps_only_the_given_token(
    session_factory: sessionmaker[Session], admin: User
) -> None:
    with session_factory() as session:
        other = create_user(session, "baska", PASSWORD)
        kept = open_session(session, admin, max_age_seconds=3600)
        closed = open_session(session, admin, max_age_seconds=3600)
        foreign = open_session(session, other, max_age_seconds=3600)
        session.commit()

        assert close_user_sessions(session, admin.id, keep_token=kept) == 1
        session.commit()

        assert resolve_session(session, kept) is not None
        assert resolve_session(session, closed) is None
        assert resolve_session(session, foreign) is not None
        assert close_user_sessions(session, admin.id) == 1


def test_last_active_admin_rule_holds_even_for_another_actor(
    session_factory: sessionmaker[Session], admin: User
) -> None:
    # Kural koşullu güncellemededir: işlemi yapan (burada zaten pasif) başka biri olsa da son etkin
    # İK pasife alınamaz.
    with session_factory() as session:
        other = create_user(session, "baska", PASSWORD)
        other.active = False
        session.commit()
        actor = PanelUser(id=other.id, username=other.username, role=other.role)
        target = session.get(User, admin.id)
        assert target is not None

        with pytest.raises(UserStatusError, match="Son etkin İK"):
            set_user_active(session, target, False, actor=actor)
        assert target.active is True


def test_session_keeps_only_the_token_hash_and_resolves_until_closed(
    session_factory: sessionmaker[Session], admin: User
) -> None:
    with session_factory() as session:
        token = open_session(session, admin, max_age_seconds=3600)
        session.commit()
        (stored,) = session.scalars(select(UserSession))
        assert token not in stored.token_hash and len(stored.token_hash) == 64
        assert stored.expires_at - stored.created_at == timedelta(hours=1)

        user = resolve_session(session, token)
        assert user is not None
        assert (user.id, user.username, user.role) == (admin.id, USERNAME, "hr")
        assert resolve_session(session, token + "x") is None

        assert close_session(session, token) is True
        session.commit()
        assert resolve_session(session, token) is None
        assert close_session(session, token) is False
        assert close_session(session, "olmayan") is False
        # Kapanan oturum silinmez.
        assert session.scalars(select(UserSession)).one().revoked_at is not None


def test_session_expires(session_factory: sessionmaker[Session], admin: User) -> None:
    now = utcnow()
    with session_factory() as session:
        token = open_session(session, admin, max_age_seconds=60, now=now)
        session.commit()

        assert resolve_session(session, token, now=now + timedelta(seconds=59)) is not None
        assert resolve_session(session, token, now=now + timedelta(seconds=60)) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/queues", "/queues"),
        ("/employees?q=ivan&page=2", "/employees?q=ivan&page=2"),
        (None, "/"),
        ("", "/"),
        ("queues", "/"),
        ("https://kotu.example/", "/"),
        ("//kotu.example/", "/"),
        ("/\\kotu.example/", "/"),
        ("/upload\r\nSet-Cookie: x=1", "/"),
    ],
)
def test_safe_next_path_allows_only_local_paths(value: str | None, expected: str) -> None:
    assert safe_next_path(value) == expected


def test_login_url_carries_the_requested_page() -> None:
    assert login_url("/") == "/login"
    assert login_url("//kotu.example") == "/login"
    assert login_url("/queues?tab=unknown") == "/login?next=%2Fqueues%3Ftab%3Dunknown"


# --- 10.1.2: girişsiz hiçbir panel yolu açılmaz -----------------------------------------------


def test_every_route_except_login_logout_and_health_requires_a_session(
    app: FastAPI, anonymous: TestClient
) -> None:
    operations = _operations(app)
    # Sayım boş kalmasın: menü sayfaları ve API uç noktaları gerçekten listede.
    assert {("GET", path) for path in MENU_PATHS} <= operations
    assert ("POST", "/api/uploads") in operations
    assert PUBLIC_OPERATIONS <= operations

    for method, path in sorted(operations - PUBLIC_OPERATIONS):
        url = re.sub(r"\{[^}]+\}", "1", path)
        response = anonymous.request(method, url, follow_redirects=False)
        if path.startswith("/api/"):
            assert response.status_code == 401, (method, path, response.text)
        else:
            assert response.status_code == 303, (method, path, response.text)
            assert response.headers["location"] == login_url(url), (method, path)


def test_panel_page_redirects_to_login_and_returns_there_after_login(
    anonymous: TestClient, admin: User
) -> None:
    response = anonymous.get("/queues?tab=unknown", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=%2Fqueues%3Ftab%3Dunknown"

    form = anonymous.get(response.headers["location"])
    assert form.status_code == 200
    assert 'name="next" value="/queues?tab=unknown"' in form.text
    assert "Ana menü" not in form.text  # girişsiz sayfada menü çizilmez

    assert _login(anonymous, next_path="/queues?tab=unknown") == "/queues?tab=unknown"
    page = anonymous.get("/queues?tab=unknown", follow_redirects=False)
    assert page.status_code == 200
    assert "<h1>Kuyruklar</h1>" in page.text


def test_login_sets_an_http_only_same_site_session_cookie(
    app: FastAPI, anonymous: TestClient, admin: User, session_factory: sessionmaker[Session]
) -> None:
    # Varsayılan ayarlar: geliştirme ortamı, 12 saatlik oturum (yerel `.env` karışmasın).
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, database_url="sqlite://"
    )

    response = anonymous.post(
        "/login", data={"username": USERNAME, "password": PASSWORD}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=43200" in cookie
    assert "Secure" not in cookie  # geliştirme: düz HTTP
    token = anonymous.cookies[SESSION_COOKIE]
    (stored,) = _sessions(session_factory)
    assert stored.user_id == admin.id and stored.revoked_at is None
    assert token not in stored.token_hash


def test_session_cookie_is_secure_in_production(
    app: FastAPI, anonymous: TestClient, admin: User
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        database_url="sqlite://",
        app_env="production",
        session_max_age_seconds=600,
    )

    response = anonymous.post(
        "/login", data={"username": USERNAME, "password": PASSWORD}, follow_redirects=False
    )

    assert response.status_code == 303
    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie
    assert "Max-Age=600" in cookie


@pytest.mark.parametrize(
    ("username", "password"),
    [(USERNAME, PASSWORD + "x"), ("olmayan", PASSWORD), (USERNAME, ""), ("", "")],
)
def test_failed_login_opens_nothing_and_does_not_tell_which_field_was_wrong(
    anonymous: TestClient,
    admin: User,
    session_factory: sessionmaker[Session],
    username: str,
    password: str,
) -> None:
    response = anonymous.post(
        "/login",
        data={"username": username, "password": password, "next": "/employees"},
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert "Kullanıcı adı veya parola hatalı." in response.text
    assert 'name="next" value="/employees"' in response.text
    assert "set-cookie" not in response.headers
    assert _sessions(session_factory) == []
    assert anonymous.get("/employees", follow_redirects=False).status_code == 303


def test_login_page_escapes_what_the_user_typed(anonymous: TestClient, admin: User) -> None:
    response = anonymous.post(
        "/login", data={"username": "<script>x</script>", "password": PASSWORD}
    )

    assert response.status_code == 401
    assert "<script>x</script>" not in response.text
    assert "&lt;script&gt;x&lt;/script&gt;" in response.text


@pytest.mark.parametrize("next_path", ["//kotu.example/", "https://kotu.example/", "/\\kotu"])
def test_login_never_redirects_off_site(anonymous: TestClient, admin: User, next_path: str) -> None:
    assert _login(anonymous, next_path=next_path) == "/"


def test_login_form_skips_to_the_page_when_already_signed_in(
    anonymous: TestClient, admin: User
) -> None:
    _login(anonymous)

    response = anonymous.get("/login?next=/employees", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/employees"


def test_api_answers_once_signed_in(anonymous: TestClient, admin: User) -> None:
    assert anonymous.get("/api/uploads/u_yok").status_code == 401

    _login(anonymous)

    response = anonymous.get("/api/uploads/u_yok")
    assert response.status_code == 404
    assert response.json() == {"detail": "Parti bulunamadı."}


def test_logout_closes_the_session_and_the_old_cookie_no_longer_opens_anything(
    anonymous: TestClient, admin: User, session_factory: sessionmaker[Session]
) -> None:
    _login(anonymous)
    token = anonymous.cookies[SESSION_COOKIE]
    assert anonymous.get("/upload", follow_redirects=False).status_code == 200

    response = anonymous.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert f'{SESSION_COOKIE}=""' in response.headers["set-cookie"]
    assert SESSION_COOKIE not in anonymous.cookies
    (stored,) = _sessions(session_factory)
    assert stored.revoked_at is not None
    # Çalınmış/eski çerez de artık hiçbir şey açmaz.
    anonymous.cookies.set(SESSION_COOKIE, token)
    assert anonymous.get("/upload", follow_redirects=False).status_code == 303
    assert anonymous.get("/api/uploads/u_yok").status_code == 401


def test_logout_without_a_session_just_returns_to_login(anonymous: TestClient) -> None:
    response = anonymous.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_signing_in_again_closes_the_previous_session(
    anonymous: TestClient, admin: User, session_factory: sessionmaker[Session]
) -> None:
    _login(anonymous)
    first = anonymous.cookies[SESSION_COOKIE]
    _login(anonymous)

    assert anonymous.cookies[SESSION_COOKIE] != first
    old, new = _sessions(session_factory)
    assert old.revoked_at is not None and new.revoked_at is None
    with session_factory() as session:
        assert resolve_session(session, first) is None


def test_expired_session_sends_back_to_login(
    anonymous: TestClient, admin: User, session_factory: sessionmaker[Session]
) -> None:
    _login(anonymous)
    with session_factory() as session:
        stored = session.scalars(select(UserSession)).one()
        stored.expires_at = utcnow() - timedelta(seconds=1)
        session.commit()

    response = anonymous.get("/upload", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=%2Fupload"


def test_forged_cookie_is_treated_as_no_session(anonymous: TestClient, admin: User) -> None:
    anonymous.cookies.set(SESSION_COOKIE, "uydurma-belirtec")

    assert anonymous.get("/employees", follow_redirects=False).status_code == 303
    assert anonymous.get("/api/uploads/u_yok").status_code == 401


def test_api_documentation_pages_are_not_served(anonymous: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
        assert anonymous.get(path).status_code == 404, path


def test_stylesheet_is_served_without_a_session(anonymous: TestClient) -> None:
    response = anonymous.get("/static/panel.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


def test_tab_icon_is_linked_and_served_without_a_session(anonymous: TestClient) -> None:
    # 10.1.5: giriş sayfası dahil her panel sayfası sekme simgesini gösterir; simge dosyaları
    # oturumsuz açıktır (giriş sayfasında da görünsün diye).
    page = anonymous.get("/login").text

    assert '<link rel="icon" type="image/png" sizes="32x32" href="/static/favicon.png">' in page
    assert '<link rel="apple-touch-icon" href="/static/icon-512.png">' in page
    for path in ("/static/favicon.png", "/static/icon-512.png"):
        response = anonymous.get(path)
        assert response.status_code == 200, path
        assert response.headers["content-type"] == "image/png", path
        assert response.content.startswith(b"\x89PNG\r\n\x1a\n"), path


# --- 10.1.1: panel iskeleti ve gezinme --------------------------------------------------------


def test_menu_lists_the_sections_in_order() -> None:
    assert [entry.label for entry in PANEL_MENU] == MENU_LABELS
    assert [entry.path for entry in PANEL_MENU] == MENU_PATHS


def test_every_menu_entry_opens_its_page_after_login(anonymous: TestClient, admin: User) -> None:
    _login(anonymous)

    home = anonymous.get("/", follow_redirects=False)
    assert home.status_code == 303
    assert home.headers["location"] == "/employees"  # ana sayfa Çalışanlar (§D85)

    for label, path in zip(MENU_LABELS, MENU_PATHS, strict=True):
        page = anonymous.get(path, follow_redirects=False)
        assert page.status_code == 200, path
        assert page.headers["content-type"].startswith("text/html")
        assert f"<title>{label} · Documania</title>" in page.text
        assert f"<h1>{label}</h1>" in page.text
        # Menü her sayfada; bulunulan bölüm işaretli, diğerleri değil.
        for other_label, other_path in zip(MENU_LABELS, MENU_PATHS, strict=True):
            link = f'<a href="{other_path}"'
            assert link in page.text, (path, other_path)
            active = f'{link} class="active" aria-current="page">{other_label}</a>'
            assert (active in page.text) == (other_path == path), (path, other_path)
        assert USERNAME in page.text
        assert 'action="/logout"' in page.text
