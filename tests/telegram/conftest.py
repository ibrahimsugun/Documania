"""Bot testleri için ağsız kurulum: Telegram'a giden her istek `FakeTelegram`'a düşer.

Gerçek `Application` kurulur (kapı ve işleyiciler gerçek), yalnız HTTP aktarıcısı sahtedir;
güncelleme Telegram'dan gelmiş gibi `process_update` ile verilir ve botun gönderdiği Bot API
çağrıları okunur. Dosya indirme de sahtedir: `FakeTelegram.files` (`file_id` → bayt) `getFile` ve
dosya adresinden döner. Botun yüklediği dosyalar (`sendDocument`) `FakeTelegram.uploads`'a
(dosya adı, bayt) olarak düşer.
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

import app.telegram.bot as bot_module
from app.ai.provider import AnalysisProvider, ProviderConfigError
from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import Base, TelegramUser, User
from app.db.session import create_db_engine, create_session_factory
from app.i18n import use_language
from app.storage import DataLayout, prepare_data_dir
from app.telegram.bot import BotConfig, BotMode, build_application
from app.telegram.handlers import DocumentIntake, ProviderFactory
from app.telegram.intent import ChoiceStore, DocumentRequests


@pytest.fixture(autouse=True)
def turkish_bot(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Bot testleri metni kaynak dilde (Türkçe msgid) denetler: tercihi olmayan kullanıcının yanıt
    dili test sürecinde Türkçedir (panel testlerindeki `PANEL_DEFAULT_LANGUAGE=tr` gibi). Dil
    davranışını sınayan testler dili açıkça verir (`test_bot_language.py`)."""
    monkeypatch.setattr(bot_module, "FALLBACK_LANGUAGE", "tr")
    # Bot dışından doğrudan çağrılan işlevler (`resolve_query`, `build_summary`) de Türkçe görür;
    # botun kendisi her güncellemede dili yeniden yazar.
    with use_language("tr"):
        yield


TOKEN = "123456:TEST-token-degeri"
LISTED_ID = 5_000_000_001
OTHER_ID = 5_000_000_002


@dataclass
class FakeTelegram(BaseRequest):
    """Bot API'yi taklit eder: her çağrıyı `(yöntem, parametreler)` olarak kaydeder."""

    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    # `file_id` → indirilecek bayt. Kaydı olmayan kimlik için `getFile` "file is too big" döner.
    files: dict[str, bytes] = field(default_factory=dict)
    # `file_id` → indirme (dosya adresi) isteğinde dönülecek Bot API hata iletisi.
    download_errors: dict[str, str] = field(default_factory=dict)
    # Botun `sendDocument` ile yüklediği dosyalar: (dosya adı, bayt), gönderim sırasıyla.
    uploads: list[tuple[str, bytes]] = field(default_factory=list)
    fail_send: bool = False
    # Bot API hatası (400) dönecek yöntemler (`sendDocument`, `answerCallbackQuery` …).
    failing: set[str] = field(default_factory=set)

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
        if "/file/bot" in url:  # `getFile`'ın döndürdüğü adresten indirme: ham bayt
            if name in self.download_errors:
                return 400, _error(self.download_errors[name])
            return 200, self.files[name]
        if name == "getFile":
            file_id = parameters["file_id"]
            if file_id not in self.files:
                return 400, _error("Bad Request: file is too big")
            result: Any = {
                "file_id": file_id,
                "file_unique_id": f"u-{file_id}",
                "file_size": len(self.files[file_id]),
                "file_path": f"documents/{file_id}",
            }
            return 200, json.dumps({"ok": True, "result": result}).encode()
        if (name == "sendMessage" and self.fail_send) or name in self.failing:
            return 400, _error("Bad Request: chat not found")
        if name == "sendDocument":
            assert request_data is not None
            for file_name, content, _mime in request_data.multipart_data.values():
                self.uploads.append((file_name, bytes(content)))
        return 200, json.dumps({"ok": True, "result": _result(name, parameters)}).encode()

    def sent_texts(self) -> list[str]:
        """Botun gönderdiği ileti metinleri, gönderim sırasıyla."""
        return [parameters["text"] for name, parameters in self.calls if name == "sendMessage"]

    def sent(self, method: str) -> list[dict[str, Any]]:
        """`method` çağrılarının parametreleri, gönderim sırasıyla."""
        return [parameters for name, parameters in self.calls if name == method]

    def methods(self) -> list[str]:
        """`getMe` (başlatma) dışında botun Telegram'a yaptığı çağrılar."""
        return [name for name, _ in self.calls if name != "getMe"]


def _error(description: str) -> bytes:
    return json.dumps({"ok": False, "error_code": 400, "description": description}).encode()


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
    if name == "sendDocument":
        return {
            "message_id": 2,
            "date": 1_700_000_000,
            "chat": {"id": parameters["chat_id"], "type": "private"},
            "document": {"file_id": "gonderilen", "file_unique_id": "u-gonderilen"},
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


def _media_message(
    user_id: int,
    message_id: int,
    media: dict[str, Any],
    *,
    media_group_id: str | None,
    chat_type: str,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "message_id": message_id,
        "date": 1_700_000_000,
        "chat": {"id": user_id, "type": chat_type},
        "from": {"id": user_id, "is_bot": False, "first_name": "Deneme"},
        **media,
    }
    if media_group_id is not None:
        body["media_group_id"] = media_group_id
    return body


def document_update(
    update_id: int,
    user_id: int,
    file_id: str,
    file_name: str | None = "belge.pdf",
    *,
    message_id: int | None = None,
    media_group_id: str | None = None,
    mime_type: str | None = "application/pdf",
    file_size: int | None = None,
    chat_type: str = "private",
) -> dict[str, Any]:
    """Dosya eki (belge) içeren mesaj; albüm dosyası için `media_group_id` verilir."""
    document: dict[str, Any] = {"file_id": file_id, "file_unique_id": f"u-{file_id}"}
    optional = {"file_name": file_name, "mime_type": mime_type, "file_size": file_size}
    document.update({key: value for key, value in optional.items() if value is not None})
    message = _media_message(
        user_id,
        message_id if message_id is not None else update_id,
        {"document": document},
        media_group_id=media_group_id,
        chat_type=chat_type,
    )
    return {"update_id": update_id, "message": message}


def photo_update(
    update_id: int,
    user_id: int,
    file_id: str,
    *,
    message_id: int | None = None,
    media_group_id: str | None = None,
) -> dict[str, Any]:
    """Fotoğraf mesajı: Telegram aynı görüntünün küçükten büyüğe iki boyutunu gönderir."""
    sizes = [
        {"file_id": f"{file_id}-k", "file_unique_id": f"u-{file_id}-k", "width": 90, "height": 90},
        {"file_id": file_id, "file_unique_id": f"u-{file_id}", "width": 800, "height": 800},
    ]
    message = _media_message(
        user_id,
        message_id if message_id is not None else update_id,
        {"photo": sizes},
        media_group_id=media_group_id,
        chat_type="private",
    )
    return {"update_id": update_id, "message": message}


def callback_update(
    update_id: int, user_id: int, data: str = "x", *, chat_id: int | None = None
) -> dict[str, Any]:
    """Satır içi düğmeye basış: `data` düğmenin verisi, `chat_id` sorunun sohbeti (varsayılan
    kullanıcının özel sohbeti)."""
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb-{update_id}",
            "from": {"id": user_id, "is_bot": False, "first_name": "Deneme"},
            "chat_instance": "ci-1",
            "data": data,
            "message": {
                "message_id": 1,
                "date": 1_700_000_000,
                "chat": {"id": chat_id if chat_id is not None else user_id, "type": "private"},
                "text": "seçim",
            },
        },
    }


@dataclass
class BotHarness:
    application: Application
    telegram: FakeTelegram
    intake: DocumentIntake | None = None
    requests: DocumentRequests | None = None

    def feed(self, *updates: dict[str, Any], pause: float = 0.0) -> None:
        """Güncellemeleri sırayla işletir (başlatma/kapatma dahil, tek olay döngüsünde).

        `pause` iki güncelleme arasında beklenen saniyedir (albüm dosyalarının gecikmeli gelmesi).
        Belge alma ve belge isteği arka plan işi başlatır; kapatmadan önce bitmesi beklenir. Seçim
        düğmesinin verisi soru gönderildikten sonra bilinir: basış ayrı bir `feed` çağrısıdır."""

        async def _run() -> None:
            await self.application.initialize()
            try:
                for index, body in enumerate(updates):
                    if index and pause:
                        await asyncio.sleep(pause)
                    update = Update.de_json(body, self.application.bot)
                    await self.application.process_update(update)
                if self.intake is not None:
                    await self.intake.join()
                if self.requests is not None:
                    await self.requests.join()
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


@dataclass
class IntakeBot(BotHarness):
    """Belge alma bağlı bot: partiler `layout` altına yazılır."""

    layout: DataLayout | None = None


@pytest.fixture
def make_intake_bot(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> Callable[..., IntakeBot]:
    """`DocumentIntake` bağlı bot: katalog yüklü, veri dizini geçici, ağ yok.

    `provider` verilmezse sağlayıcı hiç kurulamaz (`ProviderConfigError`)."""
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()

    def _make(
        provider: AnalysisProvider | None = None,
        *,
        provider_factory: ProviderFactory | None = None,
        group_wait: float = 0.05,
        **settings_overrides: object,
    ) -> IntakeBot:
        layout = prepare_data_dir(tmp_path / "data")
        settings = bot_settings(data_dir=layout.root, **settings_overrides)
        telegram = FakeTelegram()
        intake = DocumentIntake(
            session_factory,
            layout,
            settings,
            provider_factory=provider_factory or _factory_of(provider),
            group_wait=group_wait,
        )
        application = build_application(
            polling_config(),
            session_factory,
            builder=ApplicationBuilder().request(telegram).get_updates_request(telegram),
            intake=intake,
        )
        return IntakeBot(application, telegram, intake, layout=layout)

    return _make


@pytest.fixture
def make_request_bot(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> Callable[..., IntakeBot]:
    """Belge alma ve belge isteği bağlı bot (12.2 + 12.3): ikisi aynı sağlayıcıyı, veritabanını ve
    veri dizinini kullanır; katalog yüklü, ağ yok.

    `provider` verilmezse sağlayıcı hiç kurulamaz (`ProviderConfigError`)."""
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()

    def _make(
        provider: AnalysisProvider | None = None,
        *,
        provider_factory: ProviderFactory | None = None,
        choices: ChoiceStore | None = None,
        group_wait: float = 0.05,
    ) -> IntakeBot:
        layout = prepare_data_dir(tmp_path / "data")
        settings = bot_settings(data_dir=layout.root)
        factory = provider_factory or _factory_of(provider)
        telegram = FakeTelegram()
        intake = DocumentIntake(
            session_factory, layout, settings, provider_factory=factory, group_wait=group_wait
        )
        requests = DocumentRequests(
            session_factory, layout, settings, provider_factory=factory, choices=choices
        )
        application = build_application(
            polling_config(),
            session_factory,
            builder=ApplicationBuilder().request(telegram).get_updates_request(telegram),
            intake=intake,
            document_requests=requests,
        )
        return IntakeBot(application, telegram, intake, requests, layout)

    return _make


def _factory_of(provider: AnalysisProvider | None) -> ProviderFactory:
    def factory(_settings: Settings) -> AnalysisProvider:
        if provider is None:
            raise ProviderConfigError("Sağlayıcı kurulamadı (test).")
        return provider

    return factory


def bot_settings(**overrides: object) -> Settings:
    """Gerçek `.env`/ortamdan bağımsız ayar."""
    values: dict[str, object] = {"database_url": "sqlite://", "telegram_bot_token": TOKEN}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]
