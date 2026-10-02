"""12.1.1 geliştirme modu: `run()` gerçekten polling'e girer, beyaz listeyi uygular.

Telegram'a çıkan çağrılar sahte aktarıcıya düşer: `getUpdates` bir kez güncelleme döndürür, sonra
boş liste. Yanıt gidince botu durduran bir işleyici `run()`'ı geri döndürür.
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, TypeHandler
from telegram.request import RequestData

from app.telegram.bot import HANDLER_GROUP, build_application, run
from tests.telegram.conftest import (
    LISTED_ID,
    OTHER_ID,
    FakeTelegram,
    message_update,
    polling_config,
)


class PollingTelegram(FakeTelegram):
    """`getUpdates` ilk çağrıda bekleyen güncellemeleri verir, sonrakilerde boş döner."""

    def __init__(self, pending: list[dict[str, Any]]) -> None:
        super().__init__()
        self.pending = pending

    async def do_request(
        self, url: str, method: str, request_data: RequestData | None = None, **_timeouts: Any
    ) -> tuple[int, bytes]:
        if url.rsplit("/", 1)[-1] != "getUpdates":
            return await super().do_request(url, method, request_data)
        self.calls.append(("getUpdates", {}))
        updates, self.pending = self.pending, []
        if not updates:
            await asyncio.sleep(0.05)
        return 200, json.dumps({"ok": True, "result": updates}).encode()


# python-telegram-bot `run_polling` olay döngüsünü kendisi kurar; bu uyarı kütüphanenindir.
@pytest.mark.filterwarnings("ignore:There is no current event loop:DeprecationWarning")
def test_run_polls_answers_the_listed_user_and_ignores_the_rest(
    session_factory: sessionmaker[Session], whitelist: Callable[..., None]
) -> None:
    whitelist(LISTED_ID)
    telegram = PollingTelegram(
        # `/yardim`: kodsuz `/start` bağlı olmayana kimliğini söyler (12.1.7); burada kapı sınanır.
        [message_update(1, OTHER_ID, "/yardim"), message_update(2, LISTED_ID, "/yardim")]
    )
    application = build_application(
        polling_config(),
        session_factory,
        builder=ApplicationBuilder().request(telegram).get_updates_request(telegram),
    )

    async def stop_after_the_last_update(
        _update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        context.application.stop_running()

    # Kapıdan geçen her güncellemeden sonra durdurur; listede olmayan hiçbir zaman buraya gelmez.
    application.add_handler(
        TypeHandler(Update, stop_after_the_last_update), group=HANDLER_GROUP + 1
    )

    run(application, polling_config())

    assert "getUpdates" in telegram.methods()
    replies = [parameters for name, parameters in telegram.calls if name == "sendMessage"]
    assert [reply["chat_id"] for reply in replies] == [LISTED_ID]
