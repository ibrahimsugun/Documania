"""12.1.8 — Telegram'ı yalnız hesabın sahibi bağlar: Hesabım → Telegram (`/account/telegram`)
sayfasında kişi kendi kimliklerini görür, "Telegram'ı bağla" ile kendisi için tek kullanımlık bot
bağlantısı üretir (12.1.4), kimliğini elle ekler ve kendi kimliğinin iznini kapatıp açar. Yollarda
kullanıcı kimliği yoktur: hedef her zaman oturumdaki kullanıcıdır. Kullanıcılar sayfasındaki ekleme
ve bağlantı yolları kaldırıldı (PLAN.md §D97 c, d; tm 159).

Bağlantı yalnız üretildiği yanıtta görünür; bot veri dizinine adını hiç yazmadıysa düğme kapalıdır.
Kimlikler sentetiktir.
"""

import hashlib
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Event, TelegramLinkCode, TelegramUser
from app.storage import DataLayout
from app.telegram.link import LinkOutcome, redeem_link_code, write_bot_info
from app.web.auth import PanelUser, create_user, get_current_user
from tests.i18n.residue import assert_no_turkish
from tests.web.conftest import SIGNED_IN

PASSWORD = "sentetik-parola-1"
BOT = "belgeee_test_bot"
FIRST_ID = 5_000_000_101
SECOND_ID = 5_000_000_102
THIRD_ID = 5_000_000_103
LINK = re.compile(r"https://t\.me/belgeee_test_bot\?start=([A-Za-z0-9_-]{22})")
PAGE = "/account/telegram"
OWN = SIGNED_IN.id


def _add_user(session_factory: sessionmaker[Session], username: str, *, active: bool = True) -> int:
    with session_factory() as session:
        user = create_user(session, username, PASSWORD)
        user.active = active
        session.commit()
        return user.id


def _bind(
    session_factory: sessionmaker[Session], user_id: int, telegram_id: int, *, allowed: bool = True
) -> None:
    with session_factory() as session:
        session.add(TelegramUser(telegram_id=telegram_id, user_id=user_id, allowed=allowed))
        session.commit()


def _accounts(session_factory: sessionmaker[Session]) -> list[tuple[int, int, bool]]:
    with session_factory() as session:
        return [
            (row.telegram_id, row.user_id, row.allowed)
            for row in session.scalars(select(TelegramUser).order_by(TelegramUser.telegram_id))
        ]


def _events(session_factory: sessionmaker[Session], kind: str) -> list[Event]:
    with session_factory() as session:
        return list(session.scalars(select(Event).where(Event.type == kind).order_by(Event.id)))


def _codes(session_factory: sessionmaker[Session]) -> list[tuple[int, str, bool]]:
    with session_factory() as session:
        return [
            (row.user_id, row.code_hash, row.revoked_at is not None)
            for row in session.scalars(select(TelegramLinkCode).order_by(TelegramLinkCode.id))
        ]


def _own_ids(html: str) -> str:
    found = re.search(r'<ul class="telegram-ids" id="own-telegram-ids">(.*?)</ul>', html, re.S)
    return found.group(1) if found else ""


def _as(app: FastAPI, user_id: int, username: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: PanelUser(
        id=user_id, username=username, role="admin"
    )


# --- sayfa ------------------------------------------------------------------------------------


def test_the_page_shows_only_the_signed_in_users_ids(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    _bind(session_factory, OWN, SECOND_ID, allowed=False)
    _bind(session_factory, OWN, FIRST_ID)
    _bind(session_factory, ayse, THIRD_ID)

    page = client.get(PAGE)

    assert page.status_code == 200
    ids = _own_ids(page.text)
    assert ids.index(str(FIRST_ID)) < ids.index(str(SECOND_ID))
    first, second = ids.split("<li>")[1:3]
    assert "İzinli" in first and 'value="false"' in first
    assert f'action="/account/telegram/{FIRST_ID}/status"' in first
    assert "Engelli" in second and 'value="true"' in second
    assert str(THIRD_ID) not in page.text  # başkasının kimliği sayfada yok
    assert 'action="/account/telegram"' in page.text
    assert 'action="/account/telegram/link"' in page.text
    assert "/users/" not in re.sub(r'href="/users"', "", page.text.split("<main", 1)[1])


def test_the_page_explains_the_link_the_bot_and_the_manual_way(client: TestClient) -> None:
    page = client.get(PAGE).text

    assert "10 dakika geçerli, tek kullanımlık" in page
    assert "Bağlantıyı kimseyle paylaşmayın" in page
    assert "bota <code>/start</code> yazın; bot kimliğinizi söyler" in page
    assert '<a href="https://t.me/userinfobot" target="_blank" rel="noopener noreferrer">' in page
    assert "telefon numarası değil" in page
    assert 'placeholder="örn. 123456789"' in page
    assert "pattern=" not in page  # kopyalanan `Id: …` satırını sunucu denetler


def test_an_empty_page_says_no_id_is_linked(client: TestClient) -> None:
    assert "Bağlı Telegram kimliği yok." in client.get(PAGE).text


def test_every_signed_in_user_opens_it_and_anonymous_is_sent_to_sign_in(app: FastAPI) -> None:
    app.dependency_overrides[get_current_user] = lambda: PanelUser(
        id=SIGNED_IN.id, username=SIGNED_IN.username, role="izleyici"
    )
    assert TestClient(app).get(PAGE).status_code == 200  # rol fark etmez (§D97 c)
    del app.dependency_overrides[get_current_user]
    anonymous = TestClient(app)
    for method, path in (
        ("get", PAGE),
        ("post", PAGE),
        ("post", f"{PAGE}/link"),
        ("post", f"{PAGE}/{FIRST_ID}/status"),
    ):
        response = getattr(anonymous, method)(path, follow_redirects=False)
        assert response.status_code == 303, path
        assert response.headers["location"].startswith("/login")
    app.dependency_overrides.clear()


@pytest.mark.parametrize("language", ["en", "sr"])
def test_the_page_has_no_turkish_residue(
    app: FastAPI, client: TestClient, layout: DataLayout, language: str
) -> None:
    write_bot_info(layout, BOT)
    app.dependency_overrides[get_current_user] = lambda: PanelUser(
        id=SIGNED_IN.id, username=SIGNED_IN.username, role=SIGNED_IN.role, language=language
    )

    page = client.post(f"{PAGE}/link").text

    assert_no_turkish(page, language)
    assert ("My Telegram" if language == "en" else "Moj Telegram") in page


# --- elle ekleme ------------------------------------------------------------------------------


def test_adding_an_own_id_binds_it_allowed_and_logs_it_as_from_the_account(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = client.post(PAGE, data={"telegram_id": f" {FIRST_ID} "}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/account/telegram?notice=telegram_added"
    assert _accounts(session_factory) == [(FIRST_ID, OWN, True)]
    (event,) = _events(session_factory, "TELEGRAM_USER_CHANGED")
    assert (event.actor, event.data_json) == (
        SIGNED_IN.username,
        {
            "target_user_id": OWN,
            "telegram_id": FIRST_ID,
            "allowed": True,
            "added": True,
            "via": "account",
        },
    )
    page = client.get(response.headers["location"]).text
    assert "Telegram kimliği eklendi ve izni açıldı." in page
    assert str(FIRST_ID) in _own_ids(page)


def test_the_line_copied_from_a_bot_is_accepted_and_several_ids_are_allowed(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    for value in (f"Id: {FIRST_ID}", str(SECOND_ID), str(2**63 - 1)):
        assert (
            client.post(PAGE, data={"telegram_id": value}, follow_redirects=False).status_code
            == 303
        )

    assert _accounts(session_factory) == [
        (FIRST_ID, OWN, True),
        (SECOND_ID, OWN, True),
        (2**63 - 1, OWN, True),
    ]


@pytest.mark.parametrize(
    "value",
    ["", "   ", "abc", "-5", "+5", "0", "000", "12.5", "1e9", "5 000", "٣٤٥", "9" * 20, str(2**63)],
)
def test_a_value_that_is_not_a_positive_whole_number_is_refused(
    client: TestClient, session_factory: sessionmaker[Session], value: str
) -> None:
    response = client.post(PAGE, data={"telegram_id": value})

    assert response.status_code == 422
    assert 'id="account-telegram-error"' in response.text
    assert _accounts(session_factory) == []
    assert _events(session_factory, "TELEGRAM_USER_CHANGED") == []


def test_a_refused_value_comes_back_escaped(client: TestClient) -> None:
    response = client.post(PAGE, data={"telegram_id": '"><script>x</script>'})

    assert response.status_code == 422
    assert "<script>x</script>" not in response.text
    assert 'value="&#34;&gt;&lt;script&gt;x&lt;/script&gt;"' in response.text


def test_an_id_bound_to_someone_else_or_already_own_is_refused(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    _bind(session_factory, ayse, FIRST_ID)
    _bind(session_factory, OWN, SECOND_ID, allowed=False)

    taken = client.post(PAGE, data={"telegram_id": str(FIRST_ID)})
    again = client.post(PAGE, data={"telegram_id": str(SECOND_ID)})

    assert taken.status_code == 409 and "başka bir kullanıcıya bağlı" in taken.text
    assert again.status_code == 409 and "zaten bu kullanıcıya bağlı" in again.text
    assert _accounts(session_factory) == [(FIRST_ID, ayse, True), (SECOND_ID, OWN, False)]
    assert _events(session_factory, "TELEGRAM_USER_CHANGED") == []


# --- kendi kimliğinin izni --------------------------------------------------------------------


def test_blocking_and_allowing_an_own_id(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _bind(session_factory, OWN, FIRST_ID)
    path = f"{PAGE}/{FIRST_ID}/status"

    blocked = client.post(path, data={"allowed": "false"}, follow_redirects=False)
    allowed = client.post(path, data={"allowed": "true"}, follow_redirects=False)
    same = client.post(path, data={"allowed": "true"})
    unknown = client.post(path, data={"allowed": "sil"})

    assert blocked.headers["location"] == "/account/telegram?notice=telegram_blocked"
    assert allowed.headers["location"] == "/account/telegram?notice=telegram_allowed"
    assert same.status_code == 409 and "zaten izinli" in same.text
    assert unknown.status_code == 422
    assert _accounts(session_factory) == [(FIRST_ID, OWN, True)]
    assert [
        event.data_json["allowed"] for event in _events(session_factory, "TELEGRAM_USER_CHANGED")
    ] == [
        False,
        True,
    ]


def test_someone_elses_id_cannot_be_changed_from_the_account(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    _bind(session_factory, ayse, FIRST_ID)

    other = client.post(f"{PAGE}/{FIRST_ID}/status", data={"allowed": "false"})
    unknown = client.post(f"{PAGE}/{SECOND_ID}/status", data={"allowed": "false"})
    out_of_range = [
        client.post(f"{PAGE}/{value}/status", data={"allowed": "false"}).status_code
        for value in ("0", "-1", str(2**63), "abc")
    ]

    assert (other.status_code, unknown.status_code) == (404, 404)
    assert out_of_range == [422] * 4
    assert _accounts(session_factory) == [(FIRST_ID, ayse, True)]
    assert _events(session_factory, "TELEGRAM_USER_CHANGED") == []


# --- "Telegram'ı bağla" (12.1.4) ---------------------------------------------------------------


def test_the_button_is_off_until_the_bot_has_run(client: TestClient, layout: DataLayout) -> None:
    page = client.get(PAGE).text

    assert '<button type="submit" disabled aria-describedby="telegram-bot-missing">' in page
    assert "Telegram botu bu kurulumda hiç çalışmadı" in page and "TELEGRAM_BOT_TOKEN" in page

    write_bot_info(layout, BOT)
    page = client.get(PAGE).text

    assert '<button type="submit">Telegram\'ı bağla</button>' in page
    assert 'id="telegram-bot-missing"' not in page


def test_making_a_link_shows_it_once_and_logs_it_under_the_users_own_name(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    write_bot_info(layout, BOT)

    response = client.post(f"{PAGE}/link", follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    match = LINK.search(response.text)
    assert match is not None
    code = match.group(1)
    assert f'value="{match.group(0)}" readonly' in response.text
    assert 'data-copy-target="telegram-link-url"' in response.text
    assert "/static/copy-link.js" in response.text
    assert _codes(session_factory) == [(OWN, hashlib.sha256(code.encode()).hexdigest(), False)]
    [event] = _events(session_factory, "TELEGRAM_LINK_CREATED")
    assert event.actor == SIGNED_IN.username
    assert event.data_json["target_user_id"] == OWN
    assert code not in str(event.data_json)
    assert LINK.search(client.get(PAGE).text) is None  # düz kod saklanmaz


def test_a_user_makes_a_link_only_for_themselves(
    app: FastAPI, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    write_bot_info(layout, BOT)
    ayse = _add_user(session_factory, "ayse")
    _as(app, ayse, "ayse")
    client = TestClient(app)

    match = LINK.search(client.post(f"{PAGE}/link").text)
    assert match is not None
    with session_factory() as session:
        result = redeem_link_code(session, match.group(1), FIRST_ID)
        session.commit()

    assert result.outcome is LinkOutcome.LINKED
    assert [user_id for user_id, _hash, _revoked in _codes(session_factory)] == [ayse]
    [event] = _events(session_factory, "TELEGRAM_LINK_CREATED")
    assert (event.actor, event.data_json["target_user_id"]) == ("ayse", ayse)
    assert _accounts(session_factory) == [(FIRST_ID, ayse, True)]
    assert f"<code>{FIRST_ID}</code>" in _own_ids(client.get(PAGE).text)
    app.dependency_overrides.clear()


def test_a_new_link_makes_the_previous_one_invalid(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    write_bot_info(layout, BOT)

    first = LINK.search(client.post(f"{PAGE}/link").text)
    second = LINK.search(client.post(f"{PAGE}/link").text)

    assert first is not None and second is not None and first.group(1) != second.group(1)
    assert [revoked for _user, _hash, revoked in _codes(session_factory)] == [True, False]
    with session_factory() as session:
        old = redeem_link_code(session, first.group(1), FIRST_ID)
        new = redeem_link_code(session, second.group(1), FIRST_ID)
        session.commit()
    assert (old.outcome, new.outcome) == (LinkOutcome.INVALID, LinkOutcome.LINKED)


def test_no_link_while_the_bot_has_never_run(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = client.post(f"{PAGE}/link")

    assert response.status_code == 409
    assert "Telegram botu bu kurulumda hiç çalışmadı" in response.text
    assert _codes(session_factory) == []


# --- Kullanıcılar sayfasından başkası adına ekleme ve bağlama yok (§D97 d) --------------------


@pytest.mark.parametrize("target", ["other", "self", "unknown"])
def test_the_removed_users_routes_change_nothing(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, target: str
) -> None:
    write_bot_info(layout, BOT)
    ayse = _add_user(session_factory, "ayse")
    user_id = {"other": ayse, "self": OWN, "unknown": 999}[target]

    added = client.post(f"/users/{user_id}/telegram", data={"telegram_id": str(FIRST_ID)})
    linked = client.post(f"/users/{user_id}/telegram/link")

    assert added.status_code in (404, 405) and linked.status_code in (404, 405)
    assert _accounts(session_factory) == [] and _codes(session_factory) == []
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Event)) == 0


def test_the_target_is_always_the_signed_in_user_whatever_the_request_says(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    write_bot_info(layout, BOT)
    ayse = _add_user(session_factory, "ayse")
    smuggled = {"user": ayse, "user_id": ayse, "target_user_id": ayse}

    added = client.post(
        PAGE,
        params=smuggled,
        data={"telegram_id": str(FIRST_ID), **smuggled},
        follow_redirects=False,
    )
    linked = client.post(f"{PAGE}/link", params=smuggled, data=smuggled)

    assert added.status_code == 303 and linked.status_code == 200
    assert _accounts(session_factory) == [(FIRST_ID, OWN, True)]
    assert [user_id for user_id, _hash, _revoked in _codes(session_factory)] == [OWN]
