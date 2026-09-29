"""12.1.3 — panelden yönetilen beyaz liste botta: yalnız izinli kimliğe ve etkin panel kullanıcısına
bağlı kimliğe yanıt gider (S17'nin "yalnız izinli kimlik" koşulu); `app.telegram.whitelist`
çekirdeği.

Kimlikler panelin kullandığı işlevlerle (`add_telegram_id`, `set_telegram_allowed`,
`set_user_active`) değiştirilir; bot gerçek `Application`'dır, yalnız Telegram aktarıcısı sahtedir
(`FakeTelegram`). `allowed=False` ile pasif panel kullanıcısı ayrı senaryolardır.
"""

from collections.abc import Callable

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Event, TelegramUser, User
from app.telegram.bot import HELP_TEXT, is_whitelisted
from app.telegram.whitelist import (
    TELEGRAM_ID_MAX,
    TelegramIdError,
    TelegramIdTakenError,
    TelegramStatusError,
    add_telegram_id,
    is_permitted,
    parse_telegram_id,
    permitted_ids,
    set_telegram_allowed,
)
from app.web.auth import PanelUser, create_user, set_user_active
from tests.telegram.conftest import (
    LISTED_ID,
    OTHER_ID,
    BotHarness,
    callback_update,
    document_update,
    message_update,
)

ADMIN = "ik-yonetici"
PASSWORD = "sentetik-parola-1"


def _user(session_factory: sessionmaker[Session], username: str) -> int:
    with session_factory() as session:
        user = create_user(session, username, PASSWORD)
        session.commit()
        return user.id


def _actor(session_factory: sessionmaker[Session]) -> PanelUser:
    """`set_user_active` kendini pasife almayı reddeder: işlemi ayrı bir yönetici yapar."""
    user_id = _user(session_factory, ADMIN)
    return PanelUser(id=user_id, username=ADMIN, role="admin")


def _add(session_factory: sessionmaker[Session], user_id: int, telegram_id: int) -> None:
    with session_factory() as session:
        target = session.get_one(User, user_id)
        add_telegram_id(session, target, telegram_id, actor=ADMIN)
        session.commit()


def _allow(session_factory: sessionmaker[Session], telegram_id: int, allowed: bool) -> None:
    with session_factory() as session:
        account = session.get_one(TelegramUser, telegram_id)
        set_telegram_allowed(session, account, allowed, actor=ADMIN)
        session.commit()


def _activate(
    session_factory: sessionmaker[Session], user_id: int, active: bool, actor: PanelUser
) -> None:
    with session_factory() as session:
        set_user_active(session, session.get_one(User, user_id), active, actor=actor)
        session.commit()


def _replies(bot: BotHarness, update_id: int, telegram_id: int) -> list[str]:
    before = len(bot.telegram.methods())
    bot.feed(message_update(update_id, telegram_id, "/start"))
    return bot.telegram.methods()[before:]


# --- botta: izin (allowed) ---------------------------------------------------------------------


def test_an_id_added_from_the_panel_gets_replies_and_blocking_it_silences_the_bot(
    bot: BotHarness, session_factory: sessionmaker[Session]
) -> None:
    ayse = _user(session_factory, "ayse")
    assert _replies(bot, 1, LISTED_ID) == []  # henüz listede değil

    _add(session_factory, ayse, LISTED_ID)
    assert _replies(bot, 2, LISTED_ID) == ["sendMessage"]
    assert bot.telegram.sent_texts()[-1] == HELP_TEXT

    _allow(session_factory, LISTED_ID, False)
    assert _replies(bot, 3, LISTED_ID) == []
    assert is_whitelisted(session_factory, LISTED_ID) is False

    _allow(session_factory, LISTED_ID, True)
    assert _replies(bot, 4, LISTED_ID) == ["sendMessage"]


def test_blocking_one_id_leaves_the_users_other_ids_answered(
    bot: BotHarness, session_factory: sessionmaker[Session]
) -> None:
    ayse = _user(session_factory, "ayse")
    _add(session_factory, ayse, LISTED_ID)
    _add(session_factory, ayse, OTHER_ID)

    _allow(session_factory, LISTED_ID, False)

    assert _replies(bot, 1, LISTED_ID) == []
    assert _replies(bot, 2, OTHER_ID) == ["sendMessage"]


# --- botta: pasif panel kullanıcısı (User.active) ---------------------------------------------


def test_ids_of_a_deactivated_panel_user_get_no_reply_until_reactivation(
    bot: BotHarness, session_factory: sessionmaker[Session]
) -> None:
    actor = _actor(session_factory)
    ayse = _user(session_factory, "ayse")
    _add(session_factory, ayse, LISTED_ID)
    _add(session_factory, ayse, OTHER_ID)

    _activate(session_factory, ayse, False, actor)

    # İzinler açık kaldı; yine de hiçbir kimliğe yanıt yok.
    with session_factory() as session:
        assert all(session.scalars(select(TelegramUser.allowed)))
    assert _replies(bot, 1, LISTED_ID) == []
    assert _replies(bot, 2, OTHER_ID) == []
    assert is_whitelisted(session_factory, LISTED_ID) is False

    _activate(session_factory, ayse, True, actor)

    assert _replies(bot, 3, LISTED_ID) == ["sendMessage"]
    assert is_whitelisted(session_factory, LISTED_ID) is True


def test_a_deactivated_panel_users_id_is_stopped_for_every_kind_of_update(
    bot: BotHarness, session_factory: sessionmaker[Session]
) -> None:
    actor = _actor(session_factory)
    ayse = _user(session_factory, "ayse")
    _add(session_factory, ayse, LISTED_ID)
    _activate(session_factory, ayse, False, actor)

    bot.feed(
        message_update(1, LISTED_ID, "/yardim"),
        message_update(2, LISTED_ID, "Ahmet Çakar'ın ehliyetini göster"),
        document_update(3, LISTED_ID, "d1"),
        callback_update(4, LISTED_ID),
    )

    assert bot.telegram.methods() == []


def test_another_users_deactivation_does_not_affect_this_users_ids(
    bot: BotHarness, session_factory: sessionmaker[Session]
) -> None:
    actor = _actor(session_factory)
    ayse = _user(session_factory, "ayse")
    mehmet = _user(session_factory, "mehmet")
    _add(session_factory, ayse, LISTED_ID)
    _add(session_factory, mehmet, OTHER_ID)

    _activate(session_factory, mehmet, False, actor)

    assert _replies(bot, 1, LISTED_ID) == ["sendMessage"]
    assert _replies(bot, 2, OTHER_ID) == []


# --- çekirdek: kime yanıt verilir ---------------------------------------------------------------


def test_permitted_ids_need_both_the_permission_and_an_active_panel_user(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        active = User(username="etkin", password_hash="x", role="admin", active=True)
        passive = User(username="pasif", password_hash="x", role="admin", active=False)
        session.add_all(
            [
                TelegramUser(telegram_id=1, user=active, allowed=True),
                TelegramUser(telegram_id=2, user=active, allowed=False),
                TelegramUser(telegram_id=3, user=passive, allowed=True),
                TelegramUser(telegram_id=4, user=passive, allowed=False),
            ]
        )
        session.commit()
        assert list(session.scalars(permitted_ids())) == [1]
        verdicts = {
            account.telegram_id: is_permitted(account)
            for account in session.scalars(select(TelegramUser))
        }
    assert verdicts == {1: True, 2: False, 3: False, 4: False}
    assert is_permitted(None) is False
    assert [is_whitelisted(session_factory, number) for number in (1, 2, 3, 4, 5)] == [
        True,
        False,
        False,
        False,
        False,
    ]


# --- çekirdek: kimlik ayrıştırma ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", 1), (" 5000000001 ", 5_000_000_001), (str(TELEGRAM_ID_MAX), TELEGRAM_ID_MAX)],
)
def test_parse_accepts_positive_whole_numbers(value: str, expected: int) -> None:
    assert parse_telegram_id(value) == expected


@pytest.mark.parametrize(
    "value", ["", " ", "0", "-1", "+1", "1.0", "1_000", "١٢٣", "²", str(TELEGRAM_ID_MAX + 1)]
)
def test_parse_refuses_everything_else(value: str) -> None:
    with pytest.raises(TelegramIdError):
        parse_telegram_id(value)


# --- çekirdek: ekleme ve izin -------------------------------------------------------------------


def test_add_refuses_an_out_of_range_id_even_without_the_form(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _user(session_factory, "ayse")
    with session_factory() as session:
        target = session.get_one(User, ayse)
        for number in (0, -5, TELEGRAM_ID_MAX + 1):
            with pytest.raises(TelegramIdError):
                add_telegram_id(session, target, number, actor=ADMIN)
        assert session.scalars(select(TelegramUser)).all() == []


def test_the_primary_key_decides_a_taken_id_and_the_transaction_stays_usable(
    session_factory: sessionmaker[Session],
) -> None:
    """Ön denetim yoktur: aynı anda iki istek aynı kimliği eklerse birincil anahtar karar verir.
    Kaybeden 409'luk hatayı alır, işlemi kullanılabilir kalır, olay yazılmaz."""
    ayse = _user(session_factory, "ayse")
    mehmet = _user(session_factory, "mehmet")
    _add(session_factory, mehmet, LISTED_ID)

    with session_factory() as session:
        target = session.get_one(User, ayse)
        with pytest.raises(TelegramIdTakenError, match="başka bir kullanıcıya bağlı"):
            add_telegram_id(session, target, LISTED_ID, actor=ADMIN)
        add_telegram_id(session, target, OTHER_ID, actor=ADMIN)  # işlem hâlâ kullanılabilir
        with pytest.raises(TelegramIdTakenError, match="zaten bu kullanıcıya bağlı"):
            add_telegram_id(session, target, OTHER_ID, actor=ADMIN)  # işlem içinde de
        session.commit()

    with session_factory() as session:
        owners = dict(session.execute(select(TelegramUser.telegram_id, TelegramUser.user_id)).all())
        events = session.scalars(select(Event).where(Event.type == "TELEGRAM_USER_CHANGED")).all()
    assert owners == {LISTED_ID: mehmet, OTHER_ID: ayse}
    assert [event.data_json["telegram_id"] for event in events] == [LISTED_ID, OTHER_ID]


def test_a_stale_permission_change_is_refused_without_an_event(
    session_factory: sessionmaker[Session],
) -> None:
    """Koşullu güncelleme: nesne yüklendikten sonra izin başka yoldan zaten kapandıysa ikinci
    kapatma olay yazmaz; nesne veritabanındaki değere yenilenir. (SQLite yazma kilidi iki açık
    işleme izin vermez; "başka istek" aynı işlemde, nesneyi eşitlemeyen bir güncellemedir.)"""
    ayse = _user(session_factory, "ayse")
    _add(session_factory, ayse, LISTED_ID)

    with session_factory() as stale:
        account = stale.get_one(TelegramUser, LISTED_ID)
        assert account.allowed is True
        stale.execute(
            update(TelegramUser)
            .where(TelegramUser.telegram_id == LISTED_ID)
            .values(allowed=False)
            .execution_options(synchronize_session=False)
        )
        assert account.allowed is True  # nesne bayat
        with pytest.raises(TelegramStatusError, match="zaten engelli"):
            set_telegram_allowed(stale, account, False, actor=ADMIN)
        assert account.allowed is False  # yenilendi
        stale.commit()

    with session_factory() as session:
        events = session.scalars(select(Event).where(Event.type == "TELEGRAM_USER_CHANGED")).all()
    assert [(event.data_json["allowed"], event.data_json["added"]) for event in events] == [
        (True, True)
    ]


def test_the_event_names_the_actor_and_carries_no_personal_value(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _user(session_factory, "ayse")
    _add(session_factory, ayse, LISTED_ID)
    _allow(session_factory, LISTED_ID, False)

    with session_factory() as session:
        events = session.scalars(select(Event).where(Event.type == "TELEGRAM_USER_CHANGED")).all()
        for event in events:
            assert event.actor == ADMIN
            assert set(event.data_json) == {"target_user_id", "telegram_id", "allowed", "added"}
            assert event.upload_id is None and event.message is None
            assert "ayse" not in str(event.data_json)


def test_the_whitelist_fixture_still_opens_an_active_panel_user(
    whitelist: Callable[..., None], session_factory: sessionmaker[Session]
) -> None:
    """Eski fikstür (`whitelist`) de etkin kullanıcı açar: var olan bot testleri değişmeden
    yeni kurala uyar."""
    whitelist(LISTED_ID)
    whitelist(OTHER_ID, allowed=False)

    with session_factory() as session:
        assert list(session.scalars(permitted_ids())) == [LISTED_ID]
