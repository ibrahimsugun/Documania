"""10.1.4 — Kullanıcılar sayfası: liste, yeni kullanıcı, parola sıfırlama, kendi parolasını
değiştirme, pasife alma ve yeniden etkinleştirme (PLAN.md §C92-d).

Parolalar sentetiktir (MASTER-PROMPT §8). Oturumun gerçekten kapandığını sınayan testler conftest'in
hazır kullanıcısını kaldırır ve `/login` üzerinden gerçek oturum açar.
"""

import json
import re
from collections.abc import Callable, Iterator

import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import ConfirmationToken, Event, TelegramUser, User, UserSession
from app.web.auth import SESSION_COOKIE, PanelUser, create_user, get_current_user
from app.web.confirm import CONFIRMATION_HEADER, Operation
from app.web.routers.auth import LOGIN_FAILED
from tests.web.conftest import SIGNED_IN, issue_token

PASSWORD = "sentetik-parola-1"
NEW_PASSWORD = "yeni-sentetik-parola-2"
USER_EVENTS = {"USER_CREATED", "USER_DEACTIVATED", "USER_REACTIVATED", "USER_PASSWORD_CHANGED"}
PASSWORD_INPUT = re.compile(r"<input[^>]*type=\"password\"[^>]*>")


def _add_user(
    session_factory: sessionmaker[Session],
    username: str,
    *,
    password: str = PASSWORD,
    active: bool = True,
) -> int:
    with session_factory() as session:
        user = create_user(session, username, password)
        user.active = active
        session.commit()
        return user.id


def _user(session_factory: sessionmaker[Session], user_id: int) -> User:
    with session_factory() as session:
        user = session.get(User, user_id)
        assert user is not None
        return user


def _events(session_factory: sessionmaker[Session]) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(select(Event).where(Event.type.in_(USER_EVENTS)).order_by(Event.id))
        )


def _open_sessions(session_factory: sessionmaker[Session], user_id: int) -> int:
    with session_factory() as session:
        rows = session.scalars(
            select(UserSession).where(
                UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
            )
        )
        return len(list(rows))


@pytest.fixture
def real(app: FastAPI) -> Iterator[Callable[[str, str], TestClient]]:
    """Gerçek oturum denetimi: dönen işlev verilen adla giriş yapmış yeni bir istemci açar."""
    del app.dependency_overrides[get_current_user]

    def _login(username: str, password: str = PASSWORD) -> TestClient:
        client = TestClient(app)
        response = client.post(
            "/login",
            data={"username": username, "password": password, "next": "/users"},
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
        return client

    yield _login
    app.dependency_overrides.clear()


def _signed_in(client: TestClient) -> bool:
    return client.get("/upload", follow_redirects=False).status_code == 200


# --- liste ------------------------------------------------------------------------------------


def test_page_lists_users_with_role_status_and_allowed_telegram_count(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    _add_user(session_factory, "mehmet", active=False)
    with session_factory() as session:
        session.add_all(
            [
                TelegramUser(telegram_id=1001, user_id=ayse, allowed=True),
                TelegramUser(telegram_id=1002, user_id=ayse, allowed=True),
                TelegramUser(telegram_id=1003, user_id=ayse, allowed=False),
            ]
        )
        session.commit()

    page = client.get("/users")

    assert page.status_code == 200
    assert "<title>Kullanıcılar · Documania</title>" in page.text
    assert '<a href="/users" class="active" aria-current="page">Kullanıcılar</a>' in page.text
    rows = {
        match.group(1): match.group(2)
        for match in re.finditer(r'<tr id="user-(\d+)"[^>]*>(.*?)</tr>', page.text, re.S)
    }
    assert set(rows) == {str(SIGNED_IN.id), str(ayse), str(ayse + 1)}
    own = rows[str(SIGNED_IN.id)]
    assert "test-yonetici" in own and "(siz)" in own
    assert "/password" not in own and "/status" not in own  # kendi satırında işlem yok
    assert "<td>İK</td>" in rows[str(ayse)] and "Etkin" in rows[str(ayse)]
    assert 'data-allowed="2">2 izinli kimlik' in rows[str(ayse)]  # engelli kimlik sayılmaz
    assert "Pasif" in rows[str(ayse + 1)] and "Yeniden etkinleştir" in rows[str(ayse + 1)]
    assert "Pasife al" in rows[str(ayse)]
    assert 'href="/account/password"' in page.text
    # Kullanıcı silinmez (R11); silinebilen tek kayıt Telegram kimliğidir (12.1.10).
    assert re.search(r'action="/users/\d+/delete"', page.text) is None


def test_password_fields_are_empty_and_not_autofilled(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _add_user(session_factory, "ayse")

    for path in ("/users", "/account/password"):
        html = client.get(path).text
        inputs = PASSWORD_INPUT.findall(html)
        assert inputs, path
        for field in inputs:
            assert "value=" not in field, field
            assert re.search(r'autocomplete="(off|new-password)"', field), field
        for form in re.findall(r"<form[^>]*>", html):
            if "password" in form:
                assert 'autocomplete="off"' in form, form


def test_a_read_only_user_sees_the_list_without_forms_and_cannot_write(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    # 10.1.8: Kullanıcı listeyi görür; yazan her istek 403, veri değişmez.
    ayse = _add_user(session_factory, "ayse")
    app.dependency_overrides[get_current_user] = lambda: PanelUser(
        id=SIGNED_IN.id, username=SIGNED_IN.username, role="user"
    )

    page = client.get("/users")
    assert page.status_code == 200
    assert f'id="user-{ayse}"' in page.text
    assert re.findall(r'method="post" action="([^"]+)"', page.text) == ["/language", "/logout"]
    assert client.post("/users", data={"username": "mehmet"}).status_code == 403
    assert client.post(f"/users/{ayse}/status", data={"status": "inactive"}).status_code == 403
    assert client.post(f"/users/{ayse}/role", data={"role": "user"}).status_code == 403
    assert _user(session_factory, ayse).active is True
    assert _events(session_factory) == []


def test_the_page_needs_a_session(app: FastAPI) -> None:
    del app.dependency_overrides[get_current_user]
    anonymous = TestClient(app)

    response = anonymous.get("/users", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=%2Fusers"
    for path in ("/users", "/users/1/password", "/users/1/status", "/account/password"):
        assert anonymous.post(path, follow_redirects=False).status_code == 303, path
    app.dependency_overrides.clear()


# --- yeni kullanıcı ---------------------------------------------------------------------------


def test_new_user_is_created_hashed_active_and_logged_without_the_password(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = client.post(
        "/users",
        data={"username": " ayse ", "password": PASSWORD, "role": "hr"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/users?notice=created"
    with session_factory() as session:
        user = session.scalars(select(User).where(User.username == "ayse")).one()
    assert (user.role, user.active) == ("hr", True)
    assert PasswordHasher().verify(user.password_hash, PASSWORD)
    (event,) = _events(session_factory)
    assert (event.type, event.actor) == ("USER_CREATED", SIGNED_IN.username)
    assert event.data_json == {"target_user_id": user.id, "role": "hr"}
    assert "Kullanıcı oluşturuldu." in client.get(response.headers["location"]).text


@pytest.mark.parametrize(
    ("data", "code", "message"),
    [
        ({"username": "ayse", "password": "on-bir-harf"}, 422, "en az 12"),
        ({"username": "ab", "password": PASSWORD}, 422, "en az 3"),
        ({"username": "ad soyad", "password": PASSWORD}, 422, "boşluk"),
        ({"username": "a" * 151, "password": PASSWORD}, 422, "en çok 150"),
        ({"username": "ayse", "password": PASSWORD, "role": "patron"}, 422, "Bilinmeyen rol"),
        ({"username": "test-yonetici", "password": PASSWORD}, 409, "zaten kullanılıyor"),
    ],
)
def test_invalid_or_taken_new_user_is_refused_and_nothing_is_written(
    client: TestClient,
    session_factory: sessionmaker[Session],
    data: dict[str, str],
    code: int,
    message: str,
) -> None:
    response = client.post("/users", data=data)

    assert response.status_code == code
    assert message in response.text
    assert data["password"] not in response.text
    with session_factory() as session:
        assert session.scalars(select(User.username)).all() == ["test-yonetici"]
    assert _events(session_factory) == []


# --- parola sıfırlama -------------------------------------------------------------------------


def test_admin_resets_another_users_password_and_closes_their_sessions(
    real: Callable[..., TestClient], session_factory: sessionmaker[Session]
) -> None:
    _add_user(session_factory, "yonetici")
    ayse = _add_user(session_factory, "ayse")
    admin_client = real("yonetici")
    ayse_client = real("ayse")

    response = admin_client.post(
        f"/users/{ayse}/password", data={"password": NEW_PASSWORD}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/users?notice=password_reset"
    assert not _signed_in(ayse_client)
    assert _signed_in(admin_client)
    assert _open_sessions(session_factory, ayse) == 0
    assert PasswordHasher().verify(_user(session_factory, ayse).password_hash, NEW_PASSWORD)
    real("ayse", NEW_PASSWORD)
    old = TestClient(admin_client.app).post(
        "/login", data={"username": "ayse", "password": PASSWORD}, follow_redirects=False
    )
    assert old.status_code == 401
    (event,) = _events(session_factory)
    assert (event.type, event.actor) == ("USER_PASSWORD_CHANGED", "yonetici")
    assert event.data_json == {"target_user_id": ayse, "self": False}


def test_reset_refuses_own_account_short_password_and_unknown_user(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")

    own = client.post(f"/users/{SIGNED_IN.id}/password", data={"password": NEW_PASSWORD})
    short = client.post(f"/users/{ayse}/password", data={"password": "kisa"})
    unknown = client.post("/users/999/password", data={"password": NEW_PASSWORD})

    assert own.status_code == 409 and "Parolamı değiştir" in own.text
    assert short.status_code == 422 and "en az 12" in short.text
    assert unknown.status_code == 404
    assert PasswordHasher().verify(_user(session_factory, ayse).password_hash, PASSWORD)
    assert _events(session_factory) == []


# --- kendi parolası ---------------------------------------------------------------------------


def test_own_password_change_keeps_this_session_and_closes_the_others(
    real: Callable[..., TestClient], session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    here = real("ayse")
    elsewhere = real("ayse")

    response = here.post(
        "/account/password",
        data={
            "current_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "new_password_repeat": NEW_PASSWORD,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/users?notice=own_password"
    assert _signed_in(here)
    assert not _signed_in(elsewhere)
    assert _open_sessions(session_factory, ayse) == 1
    real("ayse", NEW_PASSWORD)
    (event,) = _events(session_factory)
    assert (event.type, event.actor) == ("USER_PASSWORD_CHANGED", "ayse")
    assert event.data_json == {"target_user_id": ayse, "self": True}


@pytest.mark.parametrize(
    ("current", "new", "repeat", "code", "message"),
    [
        ("yanlis-eski-parola", NEW_PASSWORD, NEW_PASSWORD, 400, "Şu anki parola hatalı."),
        (PASSWORD, NEW_PASSWORD, NEW_PASSWORD + "x", 422, "tekrarı eşleşmiyor"),
        (PASSWORD, "kisa-parola", "kisa-parola", 422, "en az 12"),
    ],
)
def test_own_password_change_is_refused_without_the_right_old_password(
    real: Callable[..., TestClient],
    session_factory: sessionmaker[Session],
    current: str,
    new: str,
    repeat: str,
    code: int,
    message: str,
) -> None:
    ayse = _add_user(session_factory, "ayse")
    here = real("ayse")
    elsewhere = real("ayse")

    response = here.post(
        "/account/password",
        data={"current_password": current, "new_password": new, "new_password_repeat": repeat},
    )

    assert response.status_code == code
    assert message in response.text
    for value in {current, new, repeat}:
        assert value not in response.text
    assert PasswordHasher().verify(_user(session_factory, ayse).password_hash, PASSWORD)
    assert _signed_in(elsewhere)
    assert _events(session_factory) == []


# --- pasife alma ve yeniden etkinleştirme -----------------------------------------------------


def test_deactivated_user_loses_open_sessions_and_cannot_log_in(
    app: FastAPI, real: Callable[..., TestClient], session_factory: sessionmaker[Session]
) -> None:
    _add_user(session_factory, "yonetici")
    ayse = _add_user(session_factory, "ayse")
    admin_client = real("yonetici")
    ayse_client = real("ayse")
    assert _signed_in(ayse_client)
    cookie = ayse_client.cookies[SESSION_COOKIE]
    ayse_user = PanelUser(id=ayse, username="ayse", role="hr")
    token = issue_token(session_factory, Operation.DISMISS, "u_yok", cookie=cookie, user=ayse_user)

    response = admin_client.post(
        f"/users/{ayse}/status", data={"status": "inactive"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/users?notice=deactivated"
    assert _user(session_factory, ayse).active is False
    assert _open_sessions(session_factory, ayse) == 0
    # Açık oturum ve onun onay belirteci geçersiz: sayfa girişe, API 401.
    assert ayse_client.get("/upload", follow_redirects=False).status_code == 303
    assert ayse_client.get("/api/uploads/u_yok").status_code == 401
    refused = ayse_client.post(
        "/uploads/u_yok/dismiss", headers={CONFIRMATION_HEADER: token}, follow_redirects=False
    )
    assert refused.status_code == 303
    with session_factory() as session:
        assert session.scalars(select(ConfirmationToken.consumed_at)).all() == [None]
    # Giriş reddi yanlış parolanınkiyle aynı: kullanıcının pasif olduğu söylenmez.
    login = TestClient(app).post(
        "/login", data={"username": "ayse", "password": PASSWORD}, follow_redirects=False
    )
    wrong = TestClient(app).post(
        "/login", data={"username": "ayse", "password": "yanlis-parola"}, follow_redirects=False
    )
    assert login.status_code == wrong.status_code == 401
    assert LOGIN_FAILED in login.text
    assert login.text == wrong.text
    (event,) = _events(session_factory)
    assert (event.type, event.actor) == ("USER_DEACTIVATED", "yonetici")
    assert event.data_json == {"target_user_id": ayse}

    again = admin_client.post(
        f"/users/{ayse}/status", data={"status": "active"}, follow_redirects=False
    )

    assert again.headers["location"] == "/users?notice=reactivated"
    assert _user(session_factory, ayse).active is True
    assert _signed_in(real("ayse"))
    assert not _signed_in(ayse_client)  # kapanan oturum geri açılmaz
    assert [(e.type, e.data_json) for e in _events(session_factory)][-1] == (
        "USER_REACTIVATED",
        {"target_user_id": ayse},
    )


def test_user_cannot_deactivate_themselves(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _add_user(session_factory, "ayse")

    response = client.post(f"/users/{SIGNED_IN.id}/status", data={"status": "inactive"})

    assert response.status_code == 409
    assert "Kendi hesabınızı pasife alamazsınız." in response.text
    assert _user(session_factory, SIGNED_IN.id).active is True
    assert _events(session_factory) == []


def test_last_active_admin_cannot_be_deactivated(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    # Oturumdaki yönetici veritabanında pasifse ayşe son etkin yöneticidir.
    with session_factory() as session:
        signed_in = session.get(User, SIGNED_IN.id)
        assert signed_in is not None
        signed_in.active = False
        session.commit()
    ayse = _add_user(session_factory, "ayse")

    response = client.post(f"/users/{ayse}/status", data={"status": "inactive"})

    assert response.status_code == 409
    assert "Son etkin İK pasife alınamaz ve rolü düşürülemez." in response.text
    assert _user(session_factory, ayse).active is True
    assert _events(session_factory) == []


def test_status_change_refuses_same_state_unknown_value_and_unknown_user(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    mehmet = _add_user(session_factory, "mehmet", active=False)

    assert client.post(f"/users/{ayse}/status", data={"status": "active"}).status_code == 409
    assert client.post(f"/users/{mehmet}/status", data={"status": "inactive"}).status_code == 409
    unknown_value = client.post(f"/users/{ayse}/status", data={"status": "silindi"})
    assert unknown_value.status_code == 422
    assert client.post("/users/999/status", data={"status": "inactive"}).status_code == 404
    assert _events(session_factory) == []


def test_no_user_event_carries_a_password(
    real: Callable[..., TestClient], session_factory: sessionmaker[Session]
) -> None:
    _add_user(session_factory, "yonetici")
    admin_client = real("yonetici")
    passwords = [PASSWORD, NEW_PASSWORD, "ucuncu-sentetik-parola", "dorduncu-sentetik-parola"]
    admin_client.post("/users", data={"username": "ayse", "password": passwords[2]})
    with session_factory() as session:
        ayse = session.scalars(select(User.id).where(User.username == "ayse")).one()
    admin_client.post(f"/users/{ayse}/password", data={"password": passwords[3]})
    admin_client.post(f"/users/{ayse}/status", data={"status": "inactive"})
    admin_client.post(f"/users/{ayse}/status", data={"status": "active"})
    admin_client.post(
        "/account/password",
        data={
            "current_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "new_password_repeat": NEW_PASSWORD,
        },
    )

    events = _events(session_factory)
    assert [event.type for event in events] == [
        "USER_CREATED",
        "USER_PASSWORD_CHANGED",
        "USER_DEACTIVATED",
        "USER_REACTIVATED",
        "USER_PASSWORD_CHANGED",
    ]
    with session_factory() as session:
        dumped = json.dumps(
            [(e.message, e.data_json) for e in session.scalars(select(Event))], ensure_ascii=False
        )
    for password in passwords:
        assert password not in dumped
    assert "argon2" not in dumped
