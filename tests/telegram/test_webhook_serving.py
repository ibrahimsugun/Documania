"""12.1.1 üretim modu: webhook gerçekten dinlenir; gizli değersiz istek bota ulaşmadan reddedilir.

`run()`'ın `run_webhook`'a verdiği ayarların aynısıyla python-telegram-bot'un webhook sunucusu yerel
bir portta kaldırılır (Telegram'a çıkan çağrılar `FakeTelegram`'a düşer); istekler yerel `httpx` ile
atılır. `run()` süreci bloke ettiği için burada onun yerine `updater.start_webhook` çağrılır.
"""

import asyncio
import socket
from collections.abc import Callable
from typing import Any

import httpx
from telegram.ext import ApplicationBuilder

from app.telegram.bot import HANDLED_UPDATES, BotConfig, BotMode, build_application
from tests.telegram.conftest import (
    LISTED_ID,
    OTHER_ID,
    TOKEN,
    FakeTelegram,
    message_update,
)

SECRET = "webhook-gizli-degeri"
HEADER = "X-Telegram-Bot-Api-Secret-Token"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def wait_for(condition: Callable[[], bool], timeout: float = 5.0) -> bool:
    for _ in range(int(timeout / 0.05)):
        if condition():
            return True
        await asyncio.sleep(0.05)
    return condition()


def test_webhook_serves_only_requests_carrying_the_secret(
    session_factory: Any, whitelist: Callable[..., None]
) -> None:
    whitelist(LISTED_ID)
    port = free_port()
    config = BotConfig(
        mode=BotMode.WEBHOOK,
        token=TOKEN,
        webhook_url="https://belge.example.com/telegram/webhook",
        secret_token=SECRET,
        listen="127.0.0.1",
        port=port,
    )
    telegram = FakeTelegram()
    application = build_application(
        config,
        session_factory,
        builder=ApplicationBuilder().request(telegram).get_updates_request(telegram),
    )
    url = f"http://127.0.0.1:{port}/{config.url_path}"

    async def scenario() -> list[int]:
        await application.initialize()
        await application.updater.start_webhook(  # type: ignore[union-attr]
            listen=config.listen,
            port=config.port,
            url_path=config.url_path,
            webhook_url=config.webhook_url,
            secret_token=config.secret_token,
            allowed_updates=list(HANDLED_UPDATES),
        )
        await application.start()
        try:
            async with httpx.AsyncClient() as client:
                forged = await client.post(url, json=message_update(1, LISTED_ID))
                wrong = await client.post(
                    url, json=message_update(2, LISTED_ID), headers={HEADER: "yanlis"}
                )
                assert telegram.methods() == ["setWebhook"]  # sahte istekler bota ulaşmadı
                unlisted = await client.post(
                    url, json=message_update(3, OTHER_ID), headers={HEADER: SECRET}
                )
                genuine = await client.post(
                    url, json=message_update(4, LISTED_ID), headers={HEADER: SECRET}
                )
                await wait_for(lambda: "sendMessage" in telegram.methods())
                await asyncio.sleep(0.2)
        finally:
            await application.updater.stop()  # type: ignore[union-attr]
            await application.stop()
            await application.shutdown()
        return [response.status_code for response in (forged, wrong, unlisted, genuine)]

    statuses = asyncio.run(scenario())

    assert statuses == [403, 403, 200, 200]  # gizli değersiz ve yanlış değerli istek reddedilir
    # Gizli değerli iki istekten yalnız listedeki kullanıcınınki yanıtlandı.
    assert telegram.methods().count("sendMessage") == 1
    _, parameters = next(call for call in telegram.calls if call[0] == "sendMessage")
    assert parameters["chat_id"] == LISTED_ID
    setwebhook = next(call for call in telegram.calls if call[0] == "setWebhook")[1]
    assert setwebhook["url"] == "https://belge.example.com/telegram/webhook"
    assert setwebhook["secret_token"] == SECRET
