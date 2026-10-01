"""12.1.3 — Telegram beyaz listesini panelden yönetme: Kullanıcılar sayfasında her kullanıcının
altında kimlikleri, kimlik ekleme, izni kapatma ve açma (PLAN.md §C92-e).

Kayıt silinmez (R11): engellemek `allowed=False`'tur. Her değişiklik kullanıcı adıyla
`TELEGRAM_USER_CHANGED` yazar. Kimlikler sentetiktir.
"""

import re

import pytest
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
            r'<tr class="telegram-row[^"]*" id="telegram-(\d+)">(.*?)</tr>', html, re.S
        )
    }


# --- sayfa ------------------------------------------------------------------------------------


def test_every_user_row_is_followed_by_its_telegram_ids_and_an_add_form(
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
    assert f'action="/users/{SIGNED_IN.id}/telegram"' in own
    # Kimlikler sırayla, izin durumu ve tek düğmeyle.
    assert of_ayse.index(str(FIRST_ID)) < of_ayse.index(str(SECOND_ID))
    first, second = of_ayse.split("<li>")[1:3]
    assert "İzinli" in first and "İzni kapat" in first and 'value="false"' in first
    assert f'action="/users/{ayse}/telegram/{FIRST_ID}/status"' in first
    assert "Engelli" in second and "İzni aç" in second and 'value="true"' in second
    assert f'action="/users/{ayse}/telegram/{SECOND_ID}/status"' in second
    assert f'action="/users/{ayse}/telegram"' in of_ayse
    assert "Kullanıcı pasif" not in of_ayse
    # Pasif kullanıcının izinli kimliği de listelenir ama bot ona yanıt vermez; sayfa bunu söyler.
    assert "Kullanıcı pasif: bot bu kimliklerin hiçbirine yanıt vermez." in of_mehmet
    # Sayaç sütunu yalnız izinli kimlikleri sayar (10.1.4, §D74-f).
    user_row = re.search(rf'<tr id="user-{ayse}"[^>]*>(.*?)</tr>', page.text, re.S)
    assert user_row is not None and "<td>1</td>" in user_row.group(1)
    assert "sil" not in re.sub(r"<[^>]+>", " ", page.text).lower().split()


def test_the_page_explains_how_to_get_an_id_from_userinfobot(client: TestClient) -> None:
    # §D86: kimlik telefon numarası değildir; kişi onu @userinfobot'tan öğrenir.
    page = client.get("/users").text

    assert '<a href="https://t.me/userinfobot" target="_blank" rel="noopener noreferrer">' in page
    assert "telefon numarası değil" in page
    form = _telegram_rows(page)[SIGNED_IN.id]
    # Kopyalanan `Id: …` satırı tarayıcıda reddedilmesin: biçimi sunucu denetler.
    assert "pattern=" not in form
    assert 'placeholder="örn. 123456789"' in form


# --- kimlik ekleme ----------------------------------------------------------------------------


def test_adding_an_id_binds_it_allowed_and_logs_who_did_it(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")

    response = client.post(
        f"/users/{ayse}/telegram", data={"telegram_id": f" {FIRST_ID} "}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/users?notice=telegram_added"
    assert _accounts(session_factory) == [(FIRST_ID, ayse, True)]
    (event,) = _events(session_factory)
    assert (event.actor, event.data_json) == (
        SIGNED_IN.username,
        {"target_user_id": ayse, "telegram_id": FIRST_ID, "allowed": True, "added": True},
    )
    page = client.get(response.headers["location"]).text
    assert "Telegram kimliği eklendi ve izni açıldı." in page
    assert str(FIRST_ID) in _telegram_rows(page)[ayse]


def test_the_line_copied_from_userinfobot_is_accepted(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")

    response = client.post(
        f"/users/{ayse}/telegram", data={"telegram_id": f"Id: {FIRST_ID}"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert _accounts(session_factory) == [(FIRST_ID, ayse, True)]


def test_a_user_may_hold_several_ids_and_the_admin_may_add_to_their_own_account(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")

    for user_id, telegram_id in ((ayse, FIRST_ID), (ayse, SECOND_ID), (SIGNED_IN.id, THIRD_ID)):
        response = client.post(
            f"/users/{user_id}/telegram",
            data={"telegram_id": str(telegram_id)},
            follow_redirects=False,
        )
        assert response.status_code == 303

    assert _accounts(session_factory) == [
        (FIRST_ID, ayse, True),
        (SECOND_ID, ayse, True),
        (THIRD_ID, SIGNED_IN.id, True),
    ]
    assert len(_events(session_factory)) == 3


def test_an_id_can_be_added_to_a_passive_user_but_stays_silent_until_reactivation(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    mehmet = _add_user(session_factory, "mehmet", active=False)

    response = client.post(
        f"/users/{mehmet}/telegram", data={"telegram_id": str(FIRST_ID)}, follow_redirects=False
    )

    assert response.status_code == 303
    assert _accounts(session_factory) == [(FIRST_ID, mehmet, True)]


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "abc",
        "-5",
        "+5",
        "0",
        "000",
        "12.5",
        "1e9",
        "5 000",
        "٣٤٥",  # Arapça-Hint rakamları: `isdigit` doğru, ASCII değil
        "9" * 20,
        str(2**63),
    ],
)
def test_a_value_that_is_not_a_positive_whole_number_is_refused(
    client: TestClient, session_factory: sessionmaker[Session], value: str
) -> None:
    ayse = _add_user(session_factory, "ayse")

    response = client.post(f"/users/{ayse}/telegram", data={"telegram_id": value})

    assert response.status_code == 422
    assert 'id="users-error"' in response.text
    assert "Telegram kimliği" in response.text
    assert _accounts(session_factory) == []
    assert _events(session_factory) == []


def test_the_largest_database_id_is_accepted(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")

    response = client.post(
        f"/users/{ayse}/telegram", data={"telegram_id": str(2**63 - 1)}, follow_redirects=False
    )

    assert response.status_code == 303
    assert _accounts(session_factory) == [(2**63 - 1, ayse, True)]


def test_a_refused_value_comes_back_escaped_in_that_users_form_only(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")

    response = client.post(f"/users/{ayse}/telegram", data={"telegram_id": '"><script>x</script>'})

    assert response.status_code == 422
    assert "<script>x</script>" not in response.text
    rows = _telegram_rows(response.text)
    assert "&#34;&gt;&lt;script&gt;x&lt;/script&gt;" in rows[ayse]
    assert "has-error" in response.text.split(f'id="telegram-{ayse}"')[0].rsplit("<tr", 1)[1]
    assert 'value=""' in rows[SIGNED_IN.id]


def test_an_id_bound_to_another_user_cannot_be_added_or_moved(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    mehmet = _add_user(session_factory, "mehmet")
    _bind(session_factory, ayse, FIRST_ID)
    _bind(session_factory, ayse, SECOND_ID, allowed=False)  # engelli kimlik de taşınmaz

    for telegram_id in (FIRST_ID, SECOND_ID):
        response = client.post(f"/users/{mehmet}/telegram", data={"telegram_id": str(telegram_id)})
        assert response.status_code == 409
        assert "başka bir kullanıcıya bağlı" in response.text

    assert _accounts(session_factory) == [(FIRST_ID, ayse, True), (SECOND_ID, ayse, False)]
    assert _events(session_factory) == []


def test_an_id_already_on_the_same_user_is_refused(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    _bind(session_factory, ayse, FIRST_ID, allowed=False)

    response = client.post(f"/users/{ayse}/telegram", data={"telegram_id": str(FIRST_ID)})

    assert response.status_code == 409
    assert "zaten bu kullanıcıya bağlı" in response.text
    assert _accounts(session_factory) == [(FIRST_ID, ayse, False)]  # izin kendiliğinden açılmaz
    assert _events(session_factory) == []


def test_adding_to_an_unknown_user_is_not_found(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = client.post("/users/999/telegram", data={"telegram_id": str(FIRST_ID)})

    assert response.status_code == 404
    assert _accounts(session_factory) == [] and _events(session_factory) == []


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

    added = client.post(f"/users/{ayse}/telegram", data={"telegram_id": str(SECOND_ID)})
    blocked = client.post(f"/users/{ayse}/telegram/{FIRST_ID}/status", data={"allowed": "false"})

    assert (added.status_code, blocked.status_code) == (403, 403)
    assert _accounts(session_factory) == [(FIRST_ID, ayse, True)]
    assert _events(session_factory) == []


def test_whitelist_routes_need_a_session(app: FastAPI) -> None:
    del app.dependency_overrides[get_current_user]
    anonymous = TestClient(app)

    for path in ("/users/1/telegram", f"/users/1/telegram/{FIRST_ID}/status"):
        assert anonymous.post(path, follow_redirects=False).status_code == 303, path
    app.dependency_overrides.clear()


def test_no_telegram_row_is_ever_deleted(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    client.post(f"/users/{ayse}/telegram", data={"telegram_id": str(FIRST_ID)})
    for value in ("false", "true", "false"):
        client.post(f"/users/{ayse}/telegram/{FIRST_ID}/status", data={"allowed": value})
    client.post(f"/users/{ayse}/status", data={"status": "inactive"})

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TelegramUser)) == 1
    assert _accounts(session_factory) == [(FIRST_ID, ayse, False)]
    assert [event.data_json["allowed"] for event in _events(session_factory)] == [
        True,
        False,
        True,
        False,
    ]
