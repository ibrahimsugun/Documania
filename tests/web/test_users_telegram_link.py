"""12.1.4 — Kullanıcılar sayfasında "Telegram'ı bağla": tek kullanımlık bot bağlantısı üretilir,
kişi açınca bot kimliği o kullanıcıya bağlar ve kimlik panelde görünür (PLAN.md §D87-b).

Bağlantı yalnız üretildiği yanıtta görünür; bot veri dizinine adını hiç yazmadıysa düğme kapalıdır.
Kimlikler sentetiktir.
"""

import hashlib
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Event, TelegramLinkCode
from app.storage import DataLayout
from app.telegram.link import LinkOutcome, redeem_link_code, write_bot_info
from app.web.auth import PanelUser, create_user, get_current_user
from tests.web.conftest import SIGNED_IN

PASSWORD = "sentetik-parola-1"
BOT = "belgeee_test_bot"
TELEGRAM_ID = 5_000_000_201
LINK = re.compile(r"https://t\.me/belgeee_test_bot\?start=([A-Za-z0-9_-]{22})")


def _add_user(session_factory: sessionmaker[Session], username: str, *, active: bool = True) -> int:
    with session_factory() as session:
        user = create_user(session, username, PASSWORD)
        user.active = active
        session.commit()
        return user.id


def _codes(session_factory: sessionmaker[Session]) -> list[tuple[int, str, bool]]:
    with session_factory() as session:
        return [
            (row.user_id, row.code_hash, row.revoked_at is not None)
            for row in session.scalars(select(TelegramLinkCode).order_by(TelegramLinkCode.id))
        ]


def _events(session_factory: sessionmaker[Session]) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event).where(Event.type == "TELEGRAM_LINK_CREATED").order_by(Event.id)
            )
        )


def _telegram_rows(html: str) -> dict[int, str]:
    return {
        int(match.group(1)): match.group(2)
        for match in re.finditer(
            r'<tr class="telegram-row[^"]*" id="telegram-(\d+)">(.*?)</tr>', html, re.S
        )
    }


def test_the_button_is_off_until_the_bot_has_run(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    ayse = _add_user(session_factory, "ayse")

    page = client.get("/users").text

    row = _telegram_rows(page)[ayse]
    assert f'action="/users/{ayse}/telegram/link"' in row
    assert '<button type="submit" disabled aria-describedby="telegram-bot-missing">' in row
    assert 'id="telegram-bot-missing"' in page
    assert "Telegram botu bu kurulumda hiç çalışmadı" in page
    assert "TELEGRAM_BOT_TOKEN" in page

    write_bot_info(layout, BOT)
    page = client.get("/users").text

    row = _telegram_rows(page)[ayse]
    assert '<button type="submit">Telegram\'ı bağla</button>' in row
    assert "disabled" not in row
    assert 'id="telegram-bot-missing"' not in page


def test_a_passive_user_gets_no_link_button(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    write_bot_info(layout, BOT)
    mehmet = _add_user(session_factory, "mehmet", active=False)

    row = _telegram_rows(client.get("/users").text)[mehmet]

    assert "/telegram/link" not in row
    # Elle ekleme yedek yol olarak kalır.
    assert f'action="/users/{mehmet}/telegram"' in row


def test_the_page_explains_the_link_and_keeps_the_manual_way(client: TestClient) -> None:
    page = client.get("/users").text

    assert "10 dakika geçerli, tek kullanımlık" in page
    assert "Bağlantıyı yalnız o kişiye iletin" in page
    assert "@userinfobot" in page


def test_making_a_link_shows_it_once_for_that_user_and_logs_who_made_it(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    write_bot_info(layout, BOT)
    ayse = _add_user(session_factory, "ayse")
    mehmet = _add_user(session_factory, "mehmet")

    response = client.post(f"/users/{ayse}/telegram/link", follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    rows = _telegram_rows(response.text)
    match = LINK.search(rows[ayse])
    assert match is not None
    code = match.group(1)
    assert f'value="{match.group(0)}" readonly' in rows[ayse]
    assert f'data-copy-target="telegram-link-url-{ayse}"' in rows[ayse]
    assert "Bağlantıyı kopyala" in rows[ayse]
    assert "10 dakika geçerli" in rows[ayse]
    assert "/static/copy-link.js" in response.text
    assert LINK.search(rows[mehmet]) is None
    assert _codes(session_factory) == [(ayse, hashlib.sha256(code.encode()).hexdigest(), False)]
    [event] = _events(session_factory)
    assert event.actor == SIGNED_IN.username
    assert event.data_json["target_user_id"] == ayse
    assert code not in str(event.data_json)
    # Sayfa yeniden açılınca bağlantı görünmez: düz kod saklanmaz.
    assert LINK.search(client.get("/users").text) is None


def test_a_new_link_makes_the_previous_one_invalid(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    write_bot_info(layout, BOT)
    ayse = _add_user(session_factory, "ayse")

    first = LINK.search(client.post(f"/users/{ayse}/telegram/link").text)
    second = LINK.search(client.post(f"/users/{ayse}/telegram/link").text)

    assert first is not None and second is not None and first.group(1) != second.group(1)
    assert [revoked for _user, _hash, revoked in _codes(session_factory)] == [True, False]
    with session_factory() as session:
        old = redeem_link_code(session, first.group(1), TELEGRAM_ID)
        new = redeem_link_code(session, second.group(1), TELEGRAM_ID)
        session.commit()
    assert (old.outcome, new.outcome) == (LinkOutcome.INVALID, LinkOutcome.LINKED)


def test_the_bot_binds_the_id_and_the_page_then_shows_it(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    write_bot_info(layout, BOT)
    ayse = _add_user(session_factory, "ayse")
    match = LINK.search(client.post(f"/users/{ayse}/telegram/link").text)
    assert match is not None

    # Kişi bağlantıyı açıp «Başlat»a basar: bot `/start <kod>`'u bu işlevle uygular.
    with session_factory() as session:
        result = redeem_link_code(session, match.group(1), TELEGRAM_ID)
        session.commit()

    assert result.outcome is LinkOutcome.LINKED
    row = _telegram_rows(client.get("/users").text)[ayse]
    assert f"<code>{TELEGRAM_ID}</code>" in row and "İzinli" in row


def test_no_link_for_a_passive_user(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    write_bot_info(layout, BOT)
    mehmet = _add_user(session_factory, "mehmet", active=False)

    response = client.post(f"/users/{mehmet}/telegram/link")

    assert response.status_code == 409
    assert "Pasif kullanıcıya Telegram bağlantısı üretilmez" in response.text
    assert LINK.search(response.text) is None
    assert _codes(session_factory) == []
    assert _events(session_factory) == []


def test_no_link_while_the_bot_has_never_run(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")

    response = client.post(f"/users/{ayse}/telegram/link")

    assert response.status_code == 409
    assert "Telegram botu bu kurulumda hiç çalışmadı" in response.text
    assert _codes(session_factory) == []
    assert _events(session_factory) == []


def test_a_link_for_an_unknown_user_is_not_found(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    write_bot_info(layout, BOT)

    assert client.post("/users/999/telegram/link").status_code == 404
    assert _codes(session_factory) == []


def test_only_an_admin_makes_links(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    write_bot_info(layout, BOT)
    ayse = _add_user(session_factory, "ayse")
    app.dependency_overrides[get_current_user] = lambda: PanelUser(
        id=SIGNED_IN.id, username=SIGNED_IN.username, role="izleyici"
    )

    assert client.post(f"/users/{ayse}/telegram/link").status_code == 403
    assert _codes(session_factory) == []


def test_making_a_link_needs_a_session(app: FastAPI, layout: DataLayout) -> None:
    write_bot_info(layout, BOT)
    del app.dependency_overrides[get_current_user]
    anonymous = TestClient(app)

    assert anonymous.post("/users/1/telegram/link", follow_redirects=False).status_code == 303
    app.dependency_overrides.clear()
