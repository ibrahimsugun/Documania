"""12.1.3 — Telegram beyaz listesini panelden yönetme: Kullanıcılar sayfasında her kullanıcının
altında kimlikleri, izni kapatma ve açma (PLAN.md §C92-e). Kimlik ekleme ve "Telegram'ı bağla"
12.1.8'den beri yalnız kişinin kendi hesabındadır (`test_account_telegram.py`, §D97 d).

İzni kapatmak kaydı silmez: engellemek `allowed=False`'tur. Kaydı silme 12.1.10'dur
(`test_telegram_delete.py`). Her değişiklik kullanıcı adıyla
`TELEGRAM_USER_CHANGED` yazar. Kimlikler sentetiktir.
"""

import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Event, TelegramUser
from app.web.auth import PanelUser, create_user, get_current_user
from tests.web.conftest import SIGNED_IN

PASSWORD = "sentetik-parola-1"
FIRST_ID = 5_000_000_101
SECOND_ID = 5_000_000_102
THIRD_ID = 5_000_000_103
EVENT = "TELEGRAM_USER_CHANGED"


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


def _events(session_factory: sessionmaker[Session]) -> list[Event]:
    with session_factory() as session:
        return list(session.scalars(select(Event).where(Event.type == EVENT).order_by(Event.id)))


def _telegram_rows(html: str) -> dict[int, str]:
    return {
        int(match.group(1)): match.group(2)
        for match in re.finditer(
            r'<td class="telegram-cell" id="telegram-(\d+)">(.*?)</td>', html, re.S
        )
    }


# --- sayfa ------------------------------------------------------------------------------------


def test_every_user_row_lists_its_telegram_ids_without_an_add_form(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    mehmet = _add_user(session_factory, "mehmet", active=False)
    _bind(session_factory, ayse, SECOND_ID, allowed=False)
    _bind(session_factory, ayse, FIRST_ID)
    _bind(session_factory, mehmet, THIRD_ID)

    page = client.get("/users")

    assert page.status_code == 200
    rows = _telegram_rows(page.text)
    assert set(rows) == {SIGNED_IN.id, ayse, mehmet}  # kendi satırı dahil
    own, of_ayse, of_mehmet = rows[SIGNED_IN.id], rows[ayse], rows[mehmet]
    assert "Bağlı Telegram kimliği yok." in own
    # §D97 d: başkası adına (kendi satırı için de) ekleme ve bağlantı yok.
    for row in rows.values():
        assert "telegram-add" not in row and "/telegram/link" not in row
        assert not re.search(r'action="/users/\d+/telegram"', row)
    # Kimlikler sırayla, izin durumu ve tek düğmeyle.
    assert of_ayse.index(str(FIRST_ID)) < of_ayse.index(str(SECOND_ID))
    first, second = of_ayse.split("<li>")[1:3]
    assert "İzinli" in first and "İzni kapat" in first and 'value="false"' in first
    assert f'action="/users/{ayse}/telegram/{FIRST_ID}/status"' in first
    assert "Engelli" in second and "İzni aç" in second and 'value="true"' in second
    assert f'action="/users/{ayse}/telegram/{SECOND_ID}/status"' in second
    assert "Kullanıcı pasif" not in of_ayse
    # Pasif kullanıcının izinli kimliği de listelenir ama bot ona yanıt vermez; sayfa bunu söyler.
    assert "Kullanıcı pasif: bot bu kimliklerin hiçbirine yanıt vermez." in of_mehmet
    # Sayaç yalnız izinli kimlikleri sayar (10.1.4, §D74-f).
    assert 'data-allowed="1">1 izinli kimlik' in of_ayse
    # Kayıt silme düğmesi her kimliktedir (12.1.10, `test_telegram_delete.py`).
    assert f'action="/users/{ayse}/telegram/{FIRST_ID}/delete"' in of_ayse


def test_the_page_points_to_the_own_telegram_page(client: TestClient) -> None:
    page = client.get("/users").text

    assert '<a class="button-link" href="/account/telegram">Telegram\'ım</a>' in page
    assert "Telegram'ı herkes yalnız kendi hesabına bağlar" in page
    assert "/static/copy-link.js" not in page


# --- izni kapatma ve açma ---------------------------------------------------------------------


def test_blocking_and_allowing_flip_the_permission_keep_the_row_and_log_each_change(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    _bind(session_factory, ayse, FIRST_ID)
    path = f"/users/{ayse}/telegram/{FIRST_ID}/status"

    blocked = client.post(path, data={"allowed": "false"}, follow_redirects=False)

    assert blocked.status_code == 303
    assert blocked.headers["location"] == "/users?notice=telegram_blocked"
    assert _accounts(session_factory) == [(FIRST_ID, ayse, False)]  # silinmedi
    page = client.get(blocked.headers["location"]).text
    assert "Telegram kimliğinin izni kapatıldı; bot bu kimliğe yanıt vermeyecek." in page
    assert "Engelli" in _telegram_rows(page)[ayse]

    allowed = client.post(path, data={"allowed": "true"}, follow_redirects=False)

    assert allowed.status_code == 303
    assert allowed.headers["location"] == "/users?notice=telegram_allowed"
    assert _accounts(session_factory) == [(FIRST_ID, ayse, True)]
    assert "Telegram kimliğinin izni açıldı." in client.get(allowed.headers["location"]).text
    assert [(event.actor, event.data_json) for event in _events(session_factory)] == [
        (
            SIGNED_IN.username,
            {"target_user_id": ayse, "telegram_id": FIRST_ID, "allowed": False, "added": False},
        ),
        (
            SIGNED_IN.username,
            {"target_user_id": ayse, "telegram_id": FIRST_ID, "allowed": True, "added": False},
        ),
    ]


def test_a_status_change_to_the_same_state_or_with_an_unknown_value_is_refused(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    _bind(session_factory, ayse, FIRST_ID)
    _bind(session_factory, ayse, SECOND_ID, allowed=False)

    already_allowed = client.post(
        f"/users/{ayse}/telegram/{FIRST_ID}/status", data={"allowed": "true"}
    )
    already_blocked = client.post(
        f"/users/{ayse}/telegram/{SECOND_ID}/status", data={"allowed": "false"}
    )
    for value in ("", "yes", "1", "sil"):
        unknown = client.post(f"/users/{ayse}/telegram/{FIRST_ID}/status", data={"allowed": value})
        assert unknown.status_code == 422, value
        assert "İzin &#39;true&#39; ya da &#39;false&#39; olmalı." in unknown.text

    assert already_allowed.status_code == 409 and "zaten izinli" in already_allowed.text
    assert already_blocked.status_code == 409 and "zaten engelli" in already_blocked.text
    assert _accounts(session_factory) == [(FIRST_ID, ayse, True), (SECOND_ID, ayse, False)]
    assert _events(session_factory) == []


def test_a_status_change_needs_the_id_to_belong_to_that_user(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    mehmet = _add_user(session_factory, "mehmet")
    _bind(session_factory, ayse, FIRST_ID)

    other_users = client.post(
        f"/users/{mehmet}/telegram/{FIRST_ID}/status", data={"allowed": "false"}
    )
    unknown_id = client.post(
        f"/users/{ayse}/telegram/{SECOND_ID}/status", data={"allowed": "false"}
    )
    unknown_user = client.post(f"/users/999/telegram/{FIRST_ID}/status", data={"allowed": "false"})
    out_of_range = [
        client.post(f"/users/{ayse}/telegram/{value}/status", data={"allowed": "false"})
        for value in ("0", "-1", str(2**63), "abc")
    ]

    assert other_users.status_code == 404
    assert unknown_id.status_code == 404
    assert unknown_user.status_code == 404
    assert [response.status_code for response in out_of_range] == [422] * 4
    assert _accounts(session_factory) == [(FIRST_ID, ayse, True)]
    assert _events(session_factory) == []


# --- erişim -----------------------------------------------------------------------------------


def test_only_an_admin_manages_the_whitelist(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    _bind(session_factory, ayse, FIRST_ID)
    app.dependency_overrides[get_current_user] = lambda: PanelUser(
        id=SIGNED_IN.id, username=SIGNED_IN.username, role="izleyici"
    )

    blocked = client.post(f"/users/{ayse}/telegram/{FIRST_ID}/status", data={"allowed": "false"})

    assert blocked.status_code == 403
    assert _accounts(session_factory) == [(FIRST_ID, ayse, True)]
    assert _events(session_factory) == []


def test_whitelist_routes_need_a_session(app: FastAPI) -> None:
    del app.dependency_overrides[get_current_user]
    anonymous = TestClient(app)

    for path in (f"/users/1/telegram/{FIRST_ID}/status",):
        assert anonymous.post(path, follow_redirects=False).status_code == 303, path
    app.dependency_overrides.clear()


def test_permission_changes_never_delete_the_row(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    _bind(session_factory, ayse, FIRST_ID)
    for value in ("true", "false", "true", "false"):
        client.post(f"/users/{ayse}/telegram/{FIRST_ID}/status", data={"allowed": value})
    client.post(f"/users/{ayse}/status", data={"status": "inactive"})

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TelegramUser)) == 1
    assert _accounts(session_factory) == [(FIRST_ID, ayse, False)]
    # İlk istek (zaten izinli) 409'dur ve olay yazmaz.
    assert [event.data_json["allowed"] for event in _events(session_factory)] == [
        False,
        True,
        False,
    ]
