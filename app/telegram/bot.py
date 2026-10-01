"""Telegram botu iskeleti ve kullanıcı beyaz listesi (PRD 12.1.1, 12.1.2; K13).

Bot panelden ayrı bir süreçtir (`python -m app.telegram.bot`, Docker Compose'ta `bot` servisi):
geliştirmede (`APP_ENV=development`) polling, üretimde (`APP_ENV=production`) webhook çalışır.
Üretimde webhook adresine gelen isteğin Telegram'dan geldiği `TELEGRAM_WEBHOOK_SECRET` ile
doğrulanır (python-telegram-bot başlığı denetler); beyaz liste güncellemedeki kullanıcı kimliğine
güvendiği için bu gizli değer olmadan webhook açılmaz.

Beyaz liste `telegram_users` tablosudur: `allowed` doğru ve bağlı panel kullanıcısı etkin olan
satırlar (`app.telegram.whitelist`; panelden yönetimi 12.1.3). Her güncelleme, öteki
tüm işleyicilerden önce `GATE_GROUP` grubundaki `WhitelistGate`'ten geçer; listede olmayan, kimliği
belirsiz ya da özel sohbet dışından gelen güncelleme için `ApplicationHandlerStop` fırlatılır ve
hiçbir işleyici çalışmaz — yani hiçbir yanıt gitmez. Kapı hata durumunda da kapalıdır (veritabanı
okunamazsa güncelleme reddedilir). **Yeni işleyici `GATE_GROUP`'tan büyük bir gruba eklenir**;
kapıdan önceki bir gruba konan işleyici beyaz listeyi atlar.

Tek istisna `LINK_GROUP`'taki `LinkStart`'tır (12.1.4, PLAN.md §D87): yöneticinin ürettiği
bağlantıyla gelen `/start <kod>` kişi henüz listede değilken çalışmalıdır. Yalnız özel sohbette ve
yalnız argümanlı `/start`'ı alır, kodu `app.telegram.link.redeem_link_code`'a verir ve her durumda
`ApplicationHandlerStop` ile güncellemeyi bitirir; başka hiçbir işleyiciye geçmez. Kodsuz `/start`
ve öbür mesajlar eskisi gibi kapıdan geçer. Bot açılışta (`post_init`) `getMe` yanıtındaki
kullanıcı adını veri dizinine yazar (`write_bot_info`); panel bağlantıyı onunla kurar.

Belge alma (12.2) `app.telegram.handlers.DocumentIntake`'te, doğal dil belge istekleri (12.3)
`app.telegram.intent.DocumentRequests`'tedir; `build_application`'a verilenler `HANDLER_GROUP`'a
eklenir. Kuyruk ve hata bildirimleri (12.4) `app.telegram.notify.Notifier`'dır: güncelleme
işleyicisi değil, botla birlikte başlayıp duran bir arka plan taramasıdır. Hiçbiri verilmezse bot
yalnız komutlara yanıt verir.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker
from telegram import Update
from telegram.constants import ChatType, UpdateType
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ApplicationHandlerStop,
    CommandHandler,
    ContextTypes,
    TypeHandler,
    filters,
)

from app.catalog import load_catalog_on_startup
from app.config import Settings, get_settings
from app.db.models import TelegramUser
from app.db.schema_check import ensure_schema_current
from app.db.session import get_session_factory
from app.storage import DataLayout, prepare_data_dir
from app.telegram.handlers import DocumentIntake
from app.telegram.intent import DocumentRequests
from app.telegram.link import (
    LinkAttempts,
    LinkOutcome,
    LinkRedemption,
    redeem_link_code,
    write_bot_info,
)
from app.telegram.notify import Notifier
from app.telegram.whitelist import permitted_ids
from app.worker.monitor import AlertWatch

logger = logging.getLogger(__name__)

GATE_GROUP = -1
LINK_GROUP = GATE_GROUP - 1
HANDLER_GROUP = 0
# Bot yalnız mesaj ve satır içi klavye yanıtı alır (12.2 belge/mesaj, 12.3 seçim); Telegram'dan
# başka güncelleme türü istenmez, dolayısıyla işlenecek yüzey de büyümez.
HANDLED_UPDATES = (UpdateType.MESSAGE, UpdateType.CALLBACK_QUERY)

HELP_TEXT = (
    "Merhaba, belgeee botuna hoş geldiniz.\n\n"
    "Belge göndermek: belgeyi dosya olarak gönderin. Fotoğraf olarak gönderilen görüntüyü "
    "Telegram sıkıştırır; kimlik belgelerini dosya olarak gönderin. Birlikte (albüm olarak) "
    "gönderilen dosyalar tek parti sayılır; işlem bitince sonucu yazarım.\n\n"
    "Belge istemek: kimin hangi belgesini istediğinizi yazın, örneğin “Ahmet Çakar'ın ehliyetini "
    "göster”. Birden çok sonuç bulunursa hangisini istediğinizi sorarım.\n\n"
    "Bildirimler: kuyruğa yeni öğe düşünce ya da bir parti işlenemeyince size kendiliğimden "
    "yazarım.\n\n"
    "Komutlar:\n"
    "/start, /yardim — bu mesaj"
)

LINKED_TEXT = "Bağlandı: {username}. Belge göndermek ve istemek için /yardim yazın."
ALREADY_LINKED_TEXT = "Bu Telegram hesabı zaten {username} kullanıcısına bağlı."
LINK_BLOCKED_TEXT = "Bu Telegram hesabının izni kapalı; yöneticinize başvurun."
LINK_TAKEN_TEXT = "Bu Telegram hesabı başka bir panel kullanıcısına bağlı; yöneticinize başvurun."
INVALID_LINK_TEXT = "Bağlantı geçersiz ya da süresi dolmuş; yöneticinizden yenisini isteyin."
LINK_FAILED_TEXT = "Bağlantı şu anda işlenemedi; biraz sonra yeniden deneyin."

# Telegram'ın `secret_token` kuralı: 1–256 karakter, yalnız A-Z a-z 0-9 _ -.
_SECRET_TOKEN = re.compile(r"[A-Za-z0-9_-]{1,256}")

# python-telegram-bot'un aktarıcısı (httpx) her isteği INFO'da `.../bot<TOKEN>/getUpdates` diye
# yazar; token loga düşmesin diye bu kayıtçılar uyarı düzeyine çekilir.
_TRANSPORT_LOGGERS = ("httpx", "httpcore")


class BotMode(StrEnum):
    POLLING = "polling"
    WEBHOOK = "webhook"


class BotConfigError(RuntimeError):
    """Bot ayarı eksik ya da geçersiz; ileti ayar adını söyler, değeri asla söylemez."""


@dataclass(frozen=True, slots=True)
class BotConfig:
    """`Settings`'ten doğrulanmış bot ayarı. Token ve gizli değer `repr`'a girmez."""

    mode: BotMode
    token: str = field(repr=False)
    webhook_url: str | None = None
    secret_token: str | None = field(default=None, repr=False)
    listen: str = "127.0.0.1"
    port: int = 8443

    @property
    def url_path(self) -> str:
        """Webhook dinleyicisinin yolu: genel adresin yol kısmı."""
        if self.webhook_url is None:
            return ""
        return urlsplit(self.webhook_url).path.lstrip("/")

    def secrets(self) -> tuple[str, ...]:
        return tuple(value for value in (self.token, self.secret_token) if value)


def _reveal(value: SecretStr | None) -> str:
    return value.get_secret_value().strip() if value is not None else ""


def load_bot_config(settings: Settings) -> BotConfig:
    """Modu (`APP_ENV`'e göre) seçer ve o moda özgü ayarları doğrular; eksik ya da geçersizse
    `BotConfigError`. Geliştirmede yalnız token gerekir; webhook ayarları yok sayılır."""
    token = _reveal(settings.telegram_bot_token)
    if not token:
        raise BotConfigError(
            "Eksik zorunlu ortam değişkeni: TELEGRAM_BOT_TOKEN. Bkz. .env.example dosyasındaki "
            "açıklama."
        )
    if settings.app_env != "production":
        return BotConfig(mode=BotMode.POLLING, token=token)

    url = (settings.telegram_webhook_url or "").strip()
    if not url:
        raise BotConfigError(
            "Üretimde webhook için TELEGRAM_WEBHOOK_URL zorunlu (Telegram'ın çağıracağı genel "
            "https adresi)."
        )
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise BotConfigError("TELEGRAM_WEBHOOK_URL geçerli bir https adresi olmalı.")
    secret = _reveal(settings.telegram_webhook_secret)
    if not secret:
        raise BotConfigError(
            "Üretimde webhook için TELEGRAM_WEBHOOK_SECRET zorunlu: bu gizli değer olmadan "
            "webhook'a herkes sahte güncelleme gönderip beyaz listeyi atlayabilir."
        )
    if not _SECRET_TOKEN.fullmatch(secret):
        raise BotConfigError(
            "TELEGRAM_WEBHOOK_SECRET 1–256 karakter olmalı ve yalnız harf, rakam, '_' ve '-' "
            "içermeli."
        )
    return BotConfig(
        mode=BotMode.WEBHOOK,
        token=token,
        webhook_url=url,
        secret_token=secret,
        listen=settings.telegram_webhook_listen,
        port=settings.telegram_webhook_port,
    )


def is_whitelisted(session_factory: sessionmaker[Session], telegram_id: int) -> bool:
    """`telegram_users`'ta `allowed` satırı olan ve panel kullanıcısı etkin olan kimlik listededir
    (K13, 12.1.3: pasif panel kullanıcısının kimlikleri yanıt almaz)."""
    with session_factory() as session:
        found = session.scalar(permitted_ids().where(TelegramUser.telegram_id == telegram_id))
    return found is not None


class WhitelistGate:
    """Her güncellemeyi öteki işleyicilerden önce süzer (12.1.2): izin yoksa sessizce durdurur."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    async def __call__(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._permits(update):
            # Kimlik ve içerik loga yazılmaz (CONVENTIONS §6); yalnız güncelleme numarası.
            logger.info("Beyaz liste dışı güncelleme yok sayıldı (update_id=%s)", update.update_id)
            raise ApplicationHandlerStop

    async def _permits(self, update: Update) -> bool:
        user, chat = update.effective_user, update.effective_chat
        # Yanıt sohbetteki herkese görünür: yalnız listedeki kullanıcıyla özel sohbette konuşulur,
        # grupta listedeki biri yazsa bile listede olmayan üyelere yanıt gitmez.
        if user is None or chat is None or chat.type != ChatType.PRIVATE:
            return False
        try:
            return await asyncio.to_thread(is_whitelisted, self._session_factory, user.id)
        except Exception as exc:
            # python-telegram-bot işleyicideki hatadan sonra sonraki gruplara geçer; kapı hata
            # verince açık kalmasın diye hata "izin yok" sayılır. Hata metni (SQL parametreleri
            # kullanıcı kimliğini taşır) loga yazılmaz, yalnız türü.
            logger.error("Beyaz liste okunamadı; güncelleme reddedildi (%s)", type(exc).__name__)
            return False


def link_reply(result: LinkRedemption) -> str:
    """Bağlama sonucunun yanıtı; geçersiz, süresi dolmuş ya da kullanılmış kod ve pasif kullanıcı
    için tek genel yanıt."""
    match result.outcome:
        case LinkOutcome.LINKED:
            return LINKED_TEXT.format(username=result.username)
        case LinkOutcome.ALREADY_LINKED:
            return ALREADY_LINKED_TEXT.format(username=result.username)
        case LinkOutcome.BLOCKED:
            return LINK_BLOCKED_TEXT
        case LinkOutcome.TAKEN:
            return LINK_TAKEN_TEXT
        case _:
            return INVALID_LINK_TEXT


class LinkStart:
    """`/start <kod>` (12.1.4): beyaz liste kapısından önce, yalnız özel sohbette çalışır; kodu
    gönderenin kimliğine uygular ve sonucu yanıtlar. Sohbet art arda `LINK_ATTEMPT_LIMIT` geçersiz
    kod gönderdiyse bir saat hiç yanıt almaz (`LinkAttempts`). Güncelleme her durumda burada biter.
    Kod, kimlik ve kullanıcı adı loga yazılmaz; yalnız sonuç ve güncelleme numarası."""

    def __init__(
        self, session_factory: sessionmaker[Session], attempts: LinkAttempts | None = None
    ) -> None:
        self._session_factory = session_factory
        self._attempts = attempts or LinkAttempts()

    def register(self, application: Application) -> None:
        application.add_handler(
            CommandHandler("start", self, filters=filters.ChatType.PRIVATE, has_args=True),
            group=LINK_GROUP,
        )

    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            await self._handle(update, list(context.args or ()))
        except Exception as exc:
            # Yanıt gönderilemedi (Telegram hatası): hata metni sohbet kimliğini taşıyabilir.
            logger.error("Telegram bağlantısı yanıtlanamadı (%s)", type(exc).__name__)
        raise ApplicationHandlerStop

    async def _handle(self, update: Update, args: list[str]) -> None:
        user, chat, message = update.effective_user, update.effective_chat, update.message
        if user is None or chat is None or message is None:
            return
        if self._attempts.silenced(chat.id):
            logger.info(
                "Bağlantı denemesi yok sayıldı: sohbet sessiz (update_id=%s)", update.update_id
            )
            return
        code = args[0] if len(args) == 1 else ""
        try:
            result = await asyncio.to_thread(self._redeem, code, user.id)
        except Exception as exc:
            # Hata metni (SQL parametreleri) kodu ve kimliği taşır; yalnız türü yazılır.
            logger.error("Telegram bağlantı kodu işlenemedi (%s)", type(exc).__name__)
            await message.reply_text(LINK_FAILED_TEXT)
            return
        if result.outcome is LinkOutcome.INVALID:
            self._attempts.failed(chat.id)
        elif result.outcome in (LinkOutcome.LINKED, LinkOutcome.ALREADY_LINKED):
            self._attempts.succeeded(chat.id)
        logger.info("Telegram bağlantı kodu: %s (update_id=%s)", result.outcome, update.update_id)
        await message.reply_text(link_reply(result))

    def _redeem(self, code: str, telegram_id: int) -> LinkRedemption:
        with self._session_factory() as session:
            result = redeem_link_code(session, code, telegram_id)
            session.commit()
        return result


def register_bot_info(application: Application, layout: DataLayout) -> None:
    """Bot açılışında (`post_init`, `getMe`'den sonra) botun kullanıcı adını veri dizinine
    yazar (12.1.4). Yazılamazsa bot yine çalışır; panelde bağlantı düğmesi kapalı kalır."""
    previous_init = application.post_init

    async def _write(app: Application) -> None:
        if previous_init is not None:
            await previous_init(app)
        try:
            await asyncio.to_thread(write_bot_info, layout, app.bot.username)
        except Exception as exc:
            logger.error("Botun kullanıcı adı veri dizinine yazılamadı (%s)", type(exc).__name__)

    application.post_init = _write


async def _send_help(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is not None:
        await update.effective_message.reply_text(HELP_TEXT)


def _redact(text: str, secrets: Iterable[str]) -> str:
    for secret in secrets:
        text = text.replace(secret, "***")
    return text


def build_application(
    config: BotConfig,
    session_factory: sessionmaker[Session],
    *,
    builder: ApplicationBuilder | None = None,
    layout: DataLayout | None = None,
    link_attempts: LinkAttempts | None = None,
    intake: DocumentIntake | None = None,
    document_requests: DocumentRequests | None = None,
    notifier: Notifier | None = None,
) -> Application:
    """Bağlantı kodu (`/start <kod>`, 12.1.4), beyaz liste kapısı, komut, (`intake` verilirse)
    belge alma ve (`document_requests` verilirse) belge isteği işleyicileriyle bot uygulamasını
    kurar (ağa çıkmaz); `layout` verilirse bot başlarken kullanıcı adını veri dizinine yazar,
    `notifier` verilirse bot başlarken bildirim taraması açılır, dururken kapanır (12.4).

    `builder` testte sahte bir aktarıcıyla ön ayarlı gelir; verilmezse varsayılan kurulur.
    `link_attempts` testte saati elle ilerleyen bir sayaçtır."""
    application = (builder or ApplicationBuilder()).token(config.token).build()
    LinkStart(session_factory, link_attempts).register(application)
    application.add_handler(
        TypeHandler(Update, WhitelistGate(session_factory), block=True), group=GATE_GROUP
    )
    application.add_handler(CommandHandler(["start", "yardim"], _send_help), group=HANDLER_GROUP)
    if intake is not None:
        intake.register(application, group=HANDLER_GROUP)
    if document_requests is not None:
        document_requests.register(application, group=HANDLER_GROUP)
    if layout is not None:
        register_bot_info(application, layout)
    if notifier is not None:
        notifier.register(application)

    secrets = config.secrets()

    async def _log_error(_update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        # Hata iletisi token'ı taşıyabilir (aktarıcı adresleri); yazılmadan önce maskelenir.
        error = context.error
        logger.error("Bot hatası: %s: %s", type(error).__name__, _redact(str(error), secrets))

    application.add_error_handler(_log_error)
    return application


def run(application: Application, config: BotConfig) -> None:
    """Botu çalıştırır ve süreç durdurulana kadar bloke eder: polling ya da webhook (12.1.1)."""
    allowed_updates = list(HANDLED_UPDATES)
    if config.mode is BotMode.WEBHOOK:
        application.run_webhook(
            listen=config.listen,
            port=config.port,
            url_path=config.url_path,
            webhook_url=config.webhook_url,
            secret_token=config.secret_token,
            allowed_updates=allowed_updates,
        )
    else:
        application.run_polling(allowed_updates=allowed_updates)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    for name in _TRANSPORT_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    try:
        settings = get_settings()
        config = load_bot_config(settings)
        # 13.5.3: göç koşulmamış (ya da kodun bilmediği ileri) şemayla bot açılmaz.
        ensure_schema_current(settings)
    except RuntimeError as exc:  # BotConfigError, eksik DATABASE_URL (00.2.2), SchemaVersionError
        print(exc, file=sys.stderr)
        return 1
    logger.info("Bot başlıyor (mod: %s)", config.mode)
    session_factory = get_session_factory()
    layout = prepare_data_dir(settings.data_dir)
    # 00.6.2: bot panelsiz de kalkabilir; katalog tablosu boşsa tohumdan yüklenir.
    load_catalog_on_startup(settings.database_url, layout)
    intake = DocumentIntake(session_factory, layout, settings)
    document_requests = DocumentRequests(session_factory, layout, settings)
    application = build_application(
        config,
        session_factory,
        layout=layout,
        intake=intake,
        document_requests=document_requests,
        notifier=Notifier(
            session_factory,
            watch=AlertWatch.from_settings(session_factory, settings, layout.root),
        ),
    )
    run(application, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
