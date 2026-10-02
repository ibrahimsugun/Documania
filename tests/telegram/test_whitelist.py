"""12.1.2 — listede olmayan kullanıcıya yanıt verilmez; kapı her güncelleme türünü ve her işleyiciyi
kapsar ve hata durumunda kapalı kalır."""

import logging
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker
from telegram import Update
from telegram.ext import CommandHandler, TypeHandler

from app.db.models import TelegramUser
from app.telegram.bot import (
    GATE_GROUP,
    HANDLER_GROUP,
    LINK_GROUP,
    IdentityStart,
    LinkStart,
    help_reply,
    is_whitelisted,
)
from tests.telegram.conftest import (
    LISTED_ID,
    OTHER_ID,
    TOKEN,
    BotHarness,
    callback_update,
    message_update,
)


def add_probe(harness: BotHarness) -> list[int]:
    """Kapıdan sonra çalışan bir işleyici: hangi güncellemelerin kapıyı geçtiğini toplar."""
    reached: list[int] = []

    async def probe(update: Update, _context: Any) -> None:
        reached.append(update.update_id)

    harness.application.add_handler(TypeHandler(Update, probe), group=HANDLER_GROUP + 1)
    return reached


def test_whitelisted_user_gets_a_reply(bot: BotHarness, whitelist: Callable[..., None]) -> None:
    whitelist(LISTED_ID)

    bot.feed(message_update(1, LISTED_ID, "/start"))

    assert bot.telegram.methods() == ["sendMessage"]
    _, parameters = bot.telegram.calls[-1]
    assert parameters["chat_id"] == LISTED_ID
    assert parameters["text"] == help_reply(LISTED_ID)


def test_yardim_command_also_replies(bot: BotHarness, whitelist: Callable[..., None]) -> None:
    whitelist(LISTED_ID)

    bot.feed(message_update(1, LISTED_ID, "/yardim"))

    assert bot.telegram.methods() == ["sendMessage"]


def test_user_not_on_the_list_gets_no_reply(
    bot: BotHarness, whitelist: Callable[..., None]
) -> None:
    whitelist(LISTED_ID)

    # Kodsuz `/start` bağlı olmayana kimliğini söyler (12.1.7, `test_identity.py`); öbürü sessiz.
    bot.feed(message_update(1, OTHER_ID, "/yardim"), message_update(2, OTHER_ID, "merhaba"))

    assert bot.telegram.methods() == []


def test_user_with_allowed_false_gets_no_reply(
    bot: BotHarness, whitelist: Callable[..., None]
) -> None:
    whitelist(LISTED_ID, allowed=False)

    bot.feed(message_update(1, LISTED_ID, "/yardim"))

    assert bot.telegram.methods() == []


def test_empty_whitelist_answers_nobody(bot: BotHarness) -> None:
    bot.feed(message_update(1, LISTED_ID, "/yardim"))

    assert bot.telegram.methods() == []


def test_gate_runs_before_every_later_handler(
    bot: BotHarness, whitelist: Callable[..., None]
) -> None:
    whitelist(LISTED_ID)
    reached = add_probe(bot)

    bot.feed(
        message_update(1, OTHER_ID, "/start"),
        message_update(2, OTHER_ID, "herhangi bir metin"),
        callback_update(3, OTHER_ID),
        message_update(4, OTHER_ID, "kenar", key="edited_message"),
        message_update(5, LISTED_ID, "/start"),
        callback_update(6, LISTED_ID),
    )

    assert reached == [5, 6]


def test_callback_from_unlisted_user_is_not_answered(bot: BotHarness) -> None:
    bot.feed(callback_update(1, OTHER_ID))

    assert bot.telegram.methods() == []


def test_update_without_a_sender_is_dropped(
    bot: BotHarness, whitelist: Callable[..., None]
) -> None:
    whitelist(LISTED_ID)
    reached = add_probe(bot)

    bot.feed(message_update(1, None, "/start", key="channel_post"))

    assert reached == []
    assert bot.telegram.methods() == []


@pytest.mark.parametrize("chat_type", ["group", "supergroup", "channel"])
def test_listed_user_is_not_answered_outside_a_private_chat(
    bot: BotHarness, whitelist: Callable[..., None], chat_type: str
) -> None:
    """Yanıt sohbetteki herkese görünür; listede olmayan üyelere gitmemeli."""
    whitelist(LISTED_ID)

    bot.feed(message_update(1, LISTED_ID, "/start", chat_type=chat_type))

    assert bot.telegram.methods() == []


def test_list_changes_apply_to_the_next_update(
    bot: BotHarness, session_factory: sessionmaker[Session], whitelist: Callable[..., None]
) -> None:
    bot.feed(message_update(1, LISTED_ID, "/yardim"))
    assert bot.telegram.methods() == []

    whitelist(LISTED_ID)
    bot.feed(message_update(2, LISTED_ID, "/yardim"))
    assert bot.telegram.methods() == ["sendMessage"]

    with session_factory() as session:
        session.get_one(TelegramUser, LISTED_ID).allowed = False
        session.commit()
    bot.feed(message_update(3, LISTED_ID, "/yardim"))
    assert bot.telegram.methods() == ["sendMessage"]  # üçüncü güncellemeye yanıt yok


def test_gate_fails_closed_when_the_database_is_unreadable(
    make_bot: Callable[..., BotHarness], caplog: pytest.LogCaptureFixture
) -> None:
    def broken_factory() -> Session:
        raise RuntimeError(f"veritabanı yok (kullanıcı {LISTED_ID})")

    harness = make_bot(broken_factory)
    reached = add_probe(harness)

    with caplog.at_level(logging.INFO):
        # `/yardim`: kodsuz `/start` kapıdan önce `IdentityStart`'ta durur (`test_identity.py`).
        harness.feed(message_update(1, LISTED_ID, "/yardim"))

    assert reached == []
    assert harness.telegram.methods() == []
    assert "RuntimeError" in caplog.text
    assert str(LISTED_ID) not in caplog.text  # kimlik hata metniyle loga sızmaz


def test_ignored_update_log_carries_no_identity(
    bot: BotHarness, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        bot.feed(message_update(7, OTHER_ID, "gizli metin"))

    assert "update_id=7" in caplog.text
    assert str(OTHER_ID) not in caplog.text
    assert "gizli metin" not in caplog.text


def test_gate_is_registered_before_every_other_handler(bot: BotHarness) -> None:
    # İki istisna yalnız özel sohbetteki `/start`'ı alır: 12.1.4'ün `/start <kod>` işleyicisi (§D87)
    # ve 12.1.7'nin argümansız `/start`'ı (§D97 b) — kişi henüz listede değilken çalışmalıdır.
    before_gate = {group for group in bot.application.handlers if group < GATE_GROUP}
    assert before_gate == {LINK_GROUP}
    link, identity = bot.application.handlers[LINK_GROUP]
    assert isinstance(link, CommandHandler) and isinstance(link.callback, LinkStart)
    assert link.commands == frozenset({"start"}) and link.has_args is True
    assert isinstance(identity, CommandHandler) and isinstance(identity.callback, IdentityStart)
    assert identity.commands == frozenset({"start"}) and identity.has_args is False
    assert GATE_GROUP < HANDLER_GROUP


def test_handler_errors_are_logged_without_the_token(
    bot: BotHarness, whitelist: Callable[..., None], caplog: pytest.LogCaptureFixture
) -> None:
    whitelist(LISTED_ID)

    async def failing(_update: Update, _context: Any) -> None:
        raise RuntimeError(f"aktarıcı hatası: https://api.telegram.org/bot{TOKEN}/sendMessage")

    bot.application.add_handler(TypeHandler(Update, failing), group=HANDLER_GROUP + 1)

    with caplog.at_level(logging.ERROR):
        bot.feed(message_update(1, LISTED_ID, "merhaba"))

    assert "RuntimeError" in caplog.text
    assert TOKEN not in caplog.text
    assert "***" in caplog.text


def test_is_whitelisted_reads_the_table(
    session_factory: sessionmaker[Session], whitelist: Callable[..., None]
) -> None:
    whitelist(LISTED_ID)
    whitelist(OTHER_ID, allowed=False)

    assert is_whitelisted(session_factory, LISTED_ID) is True
    assert is_whitelisted(session_factory, OTHER_ID) is False
    assert is_whitelisted(session_factory, 999) is False
