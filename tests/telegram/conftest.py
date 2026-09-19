"""Bot testleri için ağsız kurulum: Telegram'a giden her istek `FakeTelegram`'a düşer.

Gerçek `Application` kurulur (kapı ve işleyiciler gerçek), yalnız HTTP aktarıcısı sahtedir;
güncelleme Telegram'dan gelmiş gibi `process_update` ile verilir ve botun gönderdiği Bot API
çağrıları okunur.
"""

import asyncio
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from telegram import Update
from telegram.ext import Application, ApplicationBuilder
from telegram.request import BaseRequest, RequestData

from app.config import Settings
from app.db.models import Base, TelegramUser, User
from app.db.session import create_db_engine, create_session_factory
from app.telegram.bot import BotConfig, BotMode, build_application

TOKEN = "123456:TEST-token-degeri"
LISTED_ID = 5_000_000_001
OTHER_ID = 5_000_000_002


@dataclass
class FakeTelegram(BaseRequest):
    """Bot API'yi taklit eder: her çağrıyı `(yöntem, parametreler)` olarak kaydeder."""

    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    @property
    def read_timeout(self) -> float:
        return 5.0

    async def initialize(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def do_request(
        self, url: str, method: str, request_data: RequestData | None = None, **_timeouts: Any
    ) -> tuple[int, bytes]:
        name = url.rsplit("/", 1)[-1]
        parameters = dict(request_data.parameters) if request_data else {}
        self.calls.append((name, parameters))
        return 200, json.dumps({"ok": True, "result": _result(name, parameters)}).encode()

    def methods(self) -> list[str]:
        """`getMe` (başlatma) dışında botun Telegram'a yaptığı çağrılar."""
        return [name for name, _ in self.calls if name != "getMe"]


def _result(name: str, parameters: dict[str, Any]) -> Any:
    if name == "getMe":
        return {"id": 1, "is_bot": True, "first_name": "belgeee", "username": "belgeee_test_bot"}
    if name == "sendMessage":
        chat_id = parameters["chat_id"]
        return {
            "message_id": 1,
            "date": 1_700_000_000,
            "chat": {"id": chat_id, "type": "private"},
            "text": parameters["text"],
        }
    return True


def message_update(
    update_id: int,
    user_id: int | None,
    text: str = "/start",
    *,
    chat_type: str = "private",
    key: str = "message",
) -> dict[str, Any]:
    """Telegram'ın `Update` gövdesi: `user_id` boşsa gönderen bilinmiyor (kanal gönderisi gibi)."""
    body: dict[str, Any] = {
        "message_id": 1,
        "date": 1_700_000_000,
        "chat": {"id": user_id or 1, "type": chat_type},
        "text": text,
    }
    if user_id is not None:
        body["from"] = {"id": user_id, "is_bot": False, "first_name": "Deneme"}
    if text.startswith("/"):
        body["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
    return {"update_id": update_id, key: body}


def callback_update(update_id: int, user_id: int) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": "cb-1",
            "from": {"id": user_id, "is_bot": False, "first_name": "Deneme"},
            "chat_instance": "ci-1",
            "data": "x",
            "message": {
                "message_id": 1,
                "date": 1_700_000_000,
                "chat": {"id": user_id, "type": "private"},
                "text": "seçim",
            },
        },
    }


@dataclass
class BotHarness:
    application: Application
    telegram: FakeTelegram

    def feed(self, *updates: dict[str, Any]) -> None:
        """Güncellemeleri sırayla işletir (başlatma/kapatma dahil, tek olay döngüsünde)."""

        async def _run() -> None:
            await self.application.initialize()
            try:
                for body in updates:
                    update = Update.de_json(body, self.application.bot)
                    await self.application.process_update(update)
            finally:
                await self.application.shutdown()

        asyncio.run(_run())


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    db_engine = create_db_engine(f"sqlite:///{(tmp_path / 'bot-test.db').as_posix()}")
    Base.metadata.create_all(db_engine)
    yield db_engine
    db_engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def whitelist(session_factory: sessionmaker[Session]) -> Callable[..., None]:
    """`telegram_users`'a satır ekler (gerekirse bağlı panel kullanıcısıyla birlikte)."""

    def _add(telegram_id: int, *, allowed: bool = True) -> None:
        with session_factory() as session:
            user = User(username=f"ik-{telegram_id}", password_hash="x", role="admin")
            session.add(TelegramUser(telegram_id=telegram_id, user=user, allowed=allowed))
            session.commit()

    return _add


def polling_config() -> BotConfig:
    return BotConfig(mode=BotMode.POLLING, token=TOKEN)


@pytest.fixture
def make_bot(session_factory: sessionmaker[Session]) -> Callable[..., BotHarness]:
    def _make(factory: Any = None) -> BotHarness:
        telegram = FakeTelegram()
        application = build_application(
            polling_config(),
            factory or session_factory,
            builder=ApplicationBuilder().request(telegram).get_updates_request(telegram),
        )
        return BotHarness(application, telegram)

    return _make


@pytest.fixture
def bot(make_bot: Callable[..., BotHarness]) -> BotHarness:
    return make_bot()


def bot_settings(**overrides: object) -> Settings:
    """Gerçek `.env`/ortamdan bağımsız ayar."""
    values: dict[str, object] = {"database_url": "sqlite://", "telegram_bot_token": TOKEN}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]
