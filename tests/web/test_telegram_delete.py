"""12.1.10 — Telegram kaydını silme (PLAN.md §D107; tm 163): yönetici Kullanıcılar sayfasından
herhangi bir kullanıcının, kişi Hesabım → Telegram'dan kendi kimliğinin kaydını siler. Satır
veritabanından kalkar (R11'in tek istisnası); numara serbest kalır ve aynı ya da başka bir hesaba
bağlantıyla (12.1.4) ya da elle (12.1.8) yeniden bağlanabilir. İz olay logundadır
(`TELEGRAM_USER_CHANGED` {…, removed: true}); eski olaylar ve kullanılmış kodlar değişmez.
Kimlikler sentetiktir.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Event, TelegramLinkCode, TelegramUser, User
from app.telegram.bot import Admission, admission
from app.telegram.link import LinkOutcome, create_link_code, redeem_link_code
from app.telegram.whitelist import add_telegram_id, permitted_ids, remove_telegram_id
from app.web.auth import PanelUser, create_user, get_current_user
from tests.web.conftest import SIGNED_IN

PASSWORD = "sentetik-parola-1"
FIRST_ID = 5_000_000_101
SECOND_ID = 5_000_000_102
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


def _events(session_factory: sessionmaker[Session]) -> list[tuple[str, dict]]:
    with session_factory() as session:
        return [
            (event.actor, event.data_json)
            for event in session.scalars(
                select(Event).where(Event.type == EVENT).order_by(Event.id)
            )
        ]


def _removed(user_id: int, telegram_id: int, *, allowed: bool = True, **extra: object) -> dict:
    return {
        "target_user_id": user_id,
        "telegram_id": telegram_id,
        "allowed": allowed,
        "added": False,
        "removed": True,
        **extra,
    }


# --- Kullanıcılar sayfası ---------------------------------------------------------------------


def test_the_admin_deletes_a_users_record_and_the_page_no_longer_lists_it(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    _bind(session_factory, ayse, FIRST_ID)
    _bind(session_factory, ayse, SECOND_ID)
    before = client.get("/users").text
    assert f'action="/users/{ayse}/telegram/{FIRST_ID}/delete"' in before
    assert "Kaydı sil" in before

    response = client.post(f"/users/{ayse}/telegram/{FIRST_ID}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/users?notice=telegram_removed"
    assert _accounts(session_factory) == [(SECOND_ID, ayse, True)]
    assert _events(session_factory) == [(SIGNED_IN.username, _removed(ayse, FIRST_ID))]
    page = client.get(response.headers["location"]).text
    assert "Telegram kaydı silindi." in page
    assert str(FIRST_ID) not in page and str(SECOND_ID) in page


def test_a_blocked_record_of_an_inactive_user_can_be_deleted_too(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    mehmet = _add_user(session_factory, "mehmet", active=False)
    _bind(session_factory, mehmet, FIRST_ID, allowed=False)

    response = client.post(f"/users/{mehmet}/telegram/{FIRST_ID}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert _accounts(session_factory) == []
    assert _events(session_factory) == [
        (SIGNED_IN.username, _removed(mehmet, FIRST_ID, allowed=False))
    ]


def test_the_admin_may_delete_their_own_record_from_the_users_page(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _bind(session_factory, SIGNED_IN.id, FIRST_ID)

    response = client.post(
        f"/users/{SIGNED_IN.id}/telegram/{FIRST_ID}/delete", follow_redirects=False
    )

    assert response.status_code == 303
    assert _accounts(session_factory) == []


def test_a_delete_needs_the_id_to_belong_to_that_user(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    mehmet = _add_user(session_factory, "mehmet")
    _bind(session_factory, ayse, FIRST_ID)

    other_user = client.post(f"/users/{mehmet}/telegram/{FIRST_ID}/delete")
    unknown_id = client.post(f"/users/{ayse}/telegram/{SECOND_ID}/delete")
    unknown_user = client.post(f"/users/999/telegram/{FIRST_ID}/delete")
    out_of_range = [
        client.post(f"/users/{ayse}/telegram/{value}/delete").status_code
        for value in ("0", "-1", str(2**63), "abc")
    ]

    assert (other_user.status_code, unknown_id.status_code, unknown_user.status_code) == (
        404,
        404,
        404,
    )
    assert out_of_range == [422] * 4
    assert _accounts(session_factory) == [(FIRST_ID, ayse, True)]
    assert _events(session_factory) == []


def test_deleting_twice_is_a_404_the_second_time(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    _bind(session_factory, ayse, FIRST_ID)
    path = f"/users/{ayse}/telegram/{FIRST_ID}/delete"

    assert client.post(path, follow_redirects=False).status_code == 303
    assert client.post(path, follow_redirects=False).status_code == 404
    assert len(_events(session_factory)) == 1


def test_only_an_admin_deletes_from_the_users_page(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    _bind(session_factory, ayse, FIRST_ID)
    app.dependency_overrides[get_current_user] = lambda: PanelUser(
        id=SIGNED_IN.id, username=SIGNED_IN.username, role="izleyici"
    )

    response = client.post(f"/users/{ayse}/telegram/{FIRST_ID}/delete")

    assert response.status_code == 403
    assert _accounts(session_factory) == [(FIRST_ID, ayse, True)]


def test_delete_routes_need_a_session(app: FastAPI) -> None:
    del app.dependency_overrides[get_current_user]
    anonymous = TestClient(app)

    for path in (f"/users/1/telegram/{FIRST_ID}/delete", f"/account/telegram/{FIRST_ID}/delete"):
        assert anonymous.post(path, follow_redirects=False).status_code == 303, path
    app.dependency_overrides.clear()


# --- Hesabım → Telegram -----------------------------------------------------------------------


def test_a_user_deletes_their_own_record_from_the_account_page(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _bind(session_factory, SIGNED_IN.id, FIRST_ID)
    before = client.get("/account/telegram").text
    assert f'action="/account/telegram/{FIRST_ID}/delete"' in before

    response = client.post(f"/account/telegram/{FIRST_ID}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/account/telegram?notice=telegram_removed"
    assert _accounts(session_factory) == []
    assert _events(session_factory) == [
        (SIGNED_IN.username, _removed(SIGNED_IN.id, FIRST_ID, via="account"))
    ]
    assert "Telegram kaydı silindi." in client.get(response.headers["location"]).text


def test_someone_elses_record_cannot_be_deleted_from_the_account_page(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    _bind(session_factory, ayse, FIRST_ID)

    other = client.post(f"/account/telegram/{FIRST_ID}/delete")
    smuggled = client.post(
        f"/account/telegram/{FIRST_ID}/delete?user_id={ayse}", data={"user_id": str(ayse)}
    )

    assert (other.status_code, smuggled.status_code) == (404, 404)
    assert _accounts(session_factory) == [(FIRST_ID, ayse, True)]
    assert _events(session_factory) == []


# --- numara yeniden bağlanabilir --------------------------------------------------------------


def test_a_deleted_number_can_be_linked_to_another_account_by_link(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    mehmet = _add_user(session_factory, "mehmet")
    _bind(session_factory, ayse, FIRST_ID, allowed=False)
    with session_factory() as session:
        before = create_link_code(session, session.get(User, mehmet), actor="mehmet")
        session.commit()
    with session_factory() as session:
        assert redeem_link_code(session, before.code, FIRST_ID).outcome is LinkOutcome.TAKEN
        session.commit()

    client.post(f"/users/{ayse}/telegram/{FIRST_ID}/delete")
    with session_factory() as session:
        after = create_link_code(session, session.get(User, mehmet), actor="mehmet")
        session.commit()
    with session_factory() as session:
        assert redeem_link_code(session, after.code, FIRST_ID).outcome is LinkOutcome.LINKED
        session.commit()

    assert _accounts(session_factory) == [(FIRST_ID, mehmet, True)]
    with session_factory() as session:
        used = session.scalars(
            select(TelegramLinkCode.used_telegram_id).where(TelegramLinkCode.user_id == mehmet)
        ).all()
        assert FIRST_ID in used


def test_a_deleted_number_can_be_added_by_hand_on_the_account_page(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ayse = _add_user(session_factory, "ayse")
    _bind(session_factory, ayse, FIRST_ID)
    refused = client.post("/account/telegram", data={"telegram_id": str(FIRST_ID)})
    assert refused.status_code == 409
    assert "Önce o kullanıcının kaydı silinmeli." in refused.text

    client.post(f"/users/{ayse}/telegram/{FIRST_ID}/delete")
    added = client.post(
        "/account/telegram", data={"telegram_id": str(FIRST_ID)}, follow_redirects=False
    )

    assert added.status_code == 303
    assert _accounts(session_factory) == [(FIRST_ID, SIGNED_IN.id, True)]
    # Eski olaylar yerinde: silme ve yeni ekleme sırasıyla.
    assert [data.get("removed", False) for _, data in _events(session_factory)] == [True, False]


def test_a_deleted_number_is_no_longer_permitted(session_factory: sessionmaker[Session]) -> None:
    ayse = _add_user(session_factory, "ayse")
    with session_factory() as session:
        add_telegram_id(session, session.get(User, ayse), FIRST_ID, actor="test")
        session.commit()
    with session_factory() as session:
        assert FIRST_ID in session.scalars(permitted_ids()).all()
        remove_telegram_id(session, ayse, FIRST_ID, actor="test")
        session.commit()
    with session_factory() as session:
        assert FIRST_ID not in session.scalars(permitted_ids()).all()
        assert session.get(TelegramUser, FIRST_ID) is None


def test_the_bot_gate_stops_a_deleted_number_and_admits_it_again_on_the_new_account(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _add_user(session_factory, "ayse")
    mehmet = _add_user(session_factory, "mehmet")
    with session_factory() as session:
        session.get(User, mehmet).language = "sr"
        add_telegram_id(session, session.get(User, ayse), FIRST_ID, actor="test")
        session.commit()
    assert admission(session_factory, FIRST_ID) == Admission(None)

    with session_factory() as session:
        remove_telegram_id(session, ayse, FIRST_ID, actor="test")
        session.commit()
    assert admission(session_factory, FIRST_ID) is None

    with session_factory() as session:
        add_telegram_id(session, session.get(User, mehmet), FIRST_ID, actor="test")
        session.commit()
    # Yeni hesabın dili; eski hesaptan kalan bir şey yok.
    assert admission(session_factory, FIRST_ID) == Admission("sr")
