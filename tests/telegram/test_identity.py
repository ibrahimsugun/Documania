"""12.1.7 — bot, bağlı olmayan kişiye Telegram numarasını söyler: argümansız `/start` beyaz liste
kapısından önce işlenir; izinli değilse (kayıtsız, izni kapalı, pasif kullanıcıya bağlı — ayrım
yok) tek sade yanıt ve son satırda yalnız rakamlarla numara; sohbet başına saatte bir. İzinlinin
yardım yanıtı ve bağlantı yanıtı da numarayı söyler (PLAN.md §D97 b; tm 160).

Ağsız: gerçek `Application`, sahte Telegram aktarıcısı (`conftest.py`). Kimlikler sentetiktir.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from telegram.ext import ApplicationBuilder

from app.db.models import TelegramUser, Upload, User
from app.i18n import use_language
from app.telegram.bot import (
    LINKED_TEXT,
    IdentityReplies,
    build_application,
    help_reply,
    not_linked_reply,
)
from app.telegram.link import create_link_code
from app.telegram.whitelist import parse_telegram_id
from app.web.auth import create_user
from tests.fixtures.gen import make_docx_bytes
from tests.telegram.conftest import (
    LISTED_ID,
    OTHER_ID,
    BotHarness,
    FakeTelegram,
    IntakeBot,
    document_update,
    message_update,
    polling_config,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _bot(
    session_factory: sessionmaker[Session],
    replies: IdentityReplies | None = None,
    default_language: str | None = None,
) -> BotHarness:
    telegram = FakeTelegram()
    application = build_application(
        polling_config(),
        session_factory,
        builder=ApplicationBuilder().request(telegram).get_updates_request(telegram),
        identity_replies=replies,
        default_language=default_language,
    )
    return BotHarness(application, telegram)


def _user(session_factory: sessionmaker[Session], username: str, *, active: bool = True) -> int:
    with session_factory() as session:
        user = create_user(session, username, "sentetik-parola-1")
        user.active = active
        session.commit()
        return user.id


def _bind(
    session_factory: sessionmaker[Session], user_id: int, telegram_id: int, *, allowed: bool = True
) -> None:
    with session_factory() as session:
        session.add(TelegramUser(telegram_id=telegram_id, user_id=user_id, allowed=allowed))
        session.commit()


# --- 1, 2: bağlı olmayana tek yanıt --------------------------------------------------------------


def test_a_stranger_gets_one_plain_reply_ending_with_only_the_number(
    session_factory: sessionmaker[Session],
) -> None:
    bot = _bot(session_factory, default_language="en")

    bot.feed(message_update(1, OTHER_ID, "/start"))

    [text] = bot.telegram.sent_texts()
    first, last = text.rsplit("\n", 1)
    assert last == str(OTHER_ID) and last.isdigit()
    assert parse_telegram_id(last) == OTHER_ID
    assert first == (
        "This Telegram is not linked to Documania yet. To link it, open My account → Telegram "
        "in the panel. Your Telegram number:"
    )
    assert "Id:" not in text
    assert [p["chat_id"] for p in bot.telegram.sent("sendMessage")] == [OTHER_ID]


def test_blocked_passive_and_unknown_ids_get_byte_identical_text(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _user(session_factory, "ayse")
    mehmet = _user(session_factory, "mehmet", active=False)
    _bind(session_factory, ayse, LISTED_ID, allowed=False)
    _bind(session_factory, mehmet, OTHER_ID)
    unknown = 5_000_000_009
    bot = _bot(session_factory)

    bot.feed(
        *(
            message_update(n, tid, "/start")
            for n, tid in enumerate((LISTED_ID, OTHER_ID, unknown), 1)
        )
    )

    texts = bot.telegram.sent_texts()
    assert texts == [
        not_linked_reply(LISTED_ID),
        not_linked_reply(OTHER_ID),
        not_linked_reply(unknown),
    ]
    assert len({text.rsplit("\n", 1)[0] for text in texts}) == 1


def test_the_reply_is_in_the_default_language_whatever_the_bound_user_prefers(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _user(session_factory, "ayse")
    with session_factory() as session:
        session.get_one(User, ayse).language = "sr"
        session.commit()
    _bind(session_factory, ayse, LISTED_ID, allowed=False)
    bot = _bot(session_factory, default_language="en")

    bot.feed(message_update(1, LISTED_ID, "/start"))

    assert bot.telegram.sent_texts()[0].startswith("This Telegram is not linked")


# --- 3: öbür her şey sessiz ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "update",
    [
        message_update(1, OTHER_ID, "/yardim"),
        message_update(1, OTHER_ID, "merhaba"),
        message_update(1, OTHER_ID, "/start", chat_type="group"),
        message_update(1, OTHER_ID, "/start", chat_type="supergroup"),
        message_update(1, OTHER_ID, "/start", key="edited_message"),
        message_update(1, None, "/start", key="channel_post"),
    ],
)
def test_everything_else_from_a_stranger_stays_silent(
    session_factory: sessionmaker[Session], update: dict
) -> None:
    bot = _bot(session_factory)

    bot.feed(update)

    assert bot.telegram.methods() == []


def test_a_strangers_document_is_neither_answered_nor_processed(
    make_intake_bot: Callable[..., IntakeBot], session_factory: sessionmaker[Session]
) -> None:
    bot = make_intake_bot()
    bot.telegram.files["f1"] = make_docx_bytes()

    bot.feed(document_update(1, OTHER_ID, "f1", "cv.docx"))

    assert bot.telegram.methods() == []
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Upload)) == 0


# --- 4: saatte bir -------------------------------------------------------------------------------


def test_one_reply_per_chat_per_hour(session_factory: sessionmaker[Session]) -> None:
    clock = Clock()
    bot = _bot(session_factory, IdentityReplies(clock=clock))

    bot.feed(message_update(1, OTHER_ID, "/start"), message_update(2, OTHER_ID, "/start"))
    assert len(bot.telegram.sent_texts()) == 1

    clock.now += 3599
    bot.feed(message_update(3, OTHER_ID, "/start"))
    assert len(bot.telegram.sent_texts()) == 1
    # Başka sohbet etkilenmez.
    bot.feed(message_update(4, LISTED_ID, "/start"))
    assert len(bot.telegram.sent_texts()) == 2

    clock.now += 1
    bot.feed(message_update(5, OTHER_ID, "/start"))
    assert bot.telegram.sent_texts()[-1] == not_linked_reply(OTHER_ID)
    assert len(bot.telegram.sent_texts()) == 3


def test_the_limiter_forgets_old_chats() -> None:
    clock = Clock()
    replies = IdentityReplies(interval=timedelta(minutes=1), clock=clock)

    assert replies.take(1) and not replies.take(1) and replies.take(2)
    clock.now += 60
    assert replies.take(1) and replies.take(2)


# --- 5: izinli kişi ----------------------------------------------------------------------------


def test_a_listed_user_gets_the_help_ending_with_their_number(
    session_factory: sessionmaker[Session], whitelist: Callable[..., None]
) -> None:
    whitelist(LISTED_ID)
    bot = _bot(session_factory)

    bot.feed(message_update(1, LISTED_ID, "/start"), message_update(2, LISTED_ID, "/yardim"))

    assert bot.telegram.sent_texts() == [help_reply(LISTED_ID)] * 2
    assert bot.telegram.sent_texts()[0].endswith(f"\n\nTelegram numaranız:\n{LISTED_ID}")


def test_the_link_with_a_code_still_works_and_its_reply_tells_the_number(
    session_factory: sessionmaker[Session],
) -> None:
    ayse = _user(session_factory, "ayse")
    with session_factory() as session:
        issued = create_link_code(session, session.get_one(User, ayse), actor="ayse")
        session.commit()
    bot = _bot(session_factory)

    bot.feed(message_update(1, OTHER_ID, f"/start {issued.code}"))

    with use_language("tr"):
        expected = LINKED_TEXT.format(username="ayse") + f"\n\nTelegram numaranız:\n{OTHER_ID}"
    assert bot.telegram.sent_texts() == [expected]


# --- 6, 7: hata ve log ---------------------------------------------------------------------------


def test_no_reply_when_the_database_is_unreadable(
    make_bot: Callable[..., BotHarness], caplog: pytest.LogCaptureFixture
) -> None:
    def broken_factory() -> Session:
        raise RuntimeError(f"veritabanı yok (kullanıcı {OTHER_ID})")

    bot = make_bot(broken_factory)

    with caplog.at_level(logging.ERROR):
        bot.feed(message_update(1, OTHER_ID, "/start"))

    assert bot.telegram.methods() == []
    assert "RuntimeError" in caplog.text
    assert str(OTHER_ID) not in caplog.text


def test_ids_and_names_do_not_reach_the_log(
    session_factory: sessionmaker[Session], caplog: pytest.LogCaptureFixture
) -> None:
    bot = _bot(session_factory)

    with caplog.at_level(logging.DEBUG, logger="app.telegram"):
        bot.feed(message_update(1, OTHER_ID, "/start"), message_update(2, OTHER_ID, "/start"))

    assert "update_id=1" in caplog.text and "update_id=2" in caplog.text
    assert str(OTHER_ID) not in caplog.text
    assert "Deneme" not in caplog.text  # `message_update`'in gönderen adı


def test_a_failed_send_is_logged_without_the_id_and_the_update_still_stops(
    session_factory: sessionmaker[Session], caplog: pytest.LogCaptureFixture
) -> None:
    bot = _bot(session_factory)
    bot.telegram.fail_send = True

    with caplog.at_level(logging.ERROR):
        bot.feed(message_update(1, OTHER_ID, "/start"))

    assert bot.telegram.methods() == ["sendMessage"]  # tek deneme, başka işleyiciye geçilmez
    assert "Bağlı olmayana yanıt gönderilemedi" in caplog.text
    assert str(OTHER_ID) not in caplog.text
