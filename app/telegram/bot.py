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

İki istisna `LINK_GROUP`'tadır ve yalnız özel sohbetteki `/start`'ı alır:

- `LinkStart` (12.1.4, PLAN.md §D87): kişinin kendi hesabından ürettiği bağlantıyla gelen
  `/start <kod>` kişi henüz listede değilken çalışmalıdır. Yalnız argümanlı `/start`'ı alır, kodu
  `app.telegram.link.redeem_link_code`'a verir ve her durumda `ApplicationHandlerStop` ile
  güncellemeyi bitirir; başka hiçbir işleyiciye geçmez.
- `IdentityStart` (12.1.7, §D97 b): argümansız `/start`. Gönderen izinliyse güncellemeye dokunmaz
  (kapı ve yardım bugünkü gibi çalışır; yardımın son satırı Telegram numarasıdır). İzinli değilse
  — kayıtsız, izni kapalı ya da pasif kullanıcıya bağlı, ayrım yapılmaz — tek yanıt verir: bağlı
  değil, panelde Hesabım → Telegram; son satırda yalnız rakamlarla Telegram numarası. Sohbet başına
  saatte bir yanıt (`IdentityReplies`, bellekte); veritabanı okunamazsa yanıt yok. Kimlik loga
  yazılmaz, olay yazılmaz.

Öbür mesajlar eskisi gibi kapıdan geçer; listede olmayana yanıt gitmez. Bot açılışta
(`post_init`) `getMe` yanıtındaki kullanıcı adını veri dizinine yazar (`write_bot_info`); panel
bağlantıyı onunla kurar.

Belge alma (12.2) `app.telegram.handlers.DocumentIntake`'te, doğal dil belge istekleri (12.3)
`app.telegram.intent.DocumentRequests`'tedir; `build_application`'a verilenler `HANDLER_GROUP`'a
eklenir. Kuyruk ve hata bildirimleri (12.4) `app.telegram.notify.Notifier`'dır: güncelleme
işleyicisi değil, botla birlikte başlayıp duran bir arka plan taramasıdır. Hiçbiri verilmezse bot
yalnız komutlara yanıt verir.

**Yanıt dili (12.1.6, PLAN.md §D92 k).** Bot metinleri panelle aynı katalogdadır (msgid Türkçe,
`app.i18n`). Kapı izin verdiği güncellemede kimliğin bağlı olduğu panel kullanıcısının dilini
(`users.language`) her güncellemede yeniden okur ve context değişkenine yazar; tercih boşsa
`default_language` (üretimde `PANEL_DEFAULT_LANGUAGE`, varsayılan `en`). Böylece panelde dil
değişince botun sonraki yanıtı yeni dildedir, yeniden başlatma gerekmez. Arka plan işleri
(`asyncio.create_task`, `asyncio.to_thread`) dili oluşturuldukları anki bağlamdan alır.
`/start <kod>` yanıtı kodun kullanıcısının dilindedir; geçersiz kod ve kişisi bilinmeyen yanıt
varsayılan dildedir. Belge türü ve çalışan adları veridir, çevrilmez.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import timedelta
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
from app.db.models import TelegramUser, User
from app.db.schema_check import ensure_schema_current
from app.db.session import get_session_factory
from app.i18n import DEFAULT_LANGUAGE, N_, activate_language, gettext, is_supported
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

HELP_TEXT = N_(
    "Merhaba, Documania botuna hoş geldiniz.\n\n"
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

LINKED_TEXT = N_("Bağlandı: {username}. Belge göndermek ve istemek için /yardim yazın.")
ALREADY_LINKED_TEXT = N_("Bu Telegram hesabı zaten {username} kullanıcısına bağlı.")
LINK_BLOCKED_TEXT = N_("Bu Telegram hesabının izni kapalı; yöneticinize başvurun.")
LINK_TAKEN_TEXT = N_(
    "Bu Telegram hesabı başka bir panel kullanıcısına bağlı; yöneticinize başvurun."
)
INVALID_LINK_TEXT = N_("Bağlantı geçersiz ya da süresi dolmuş; yöneticinizden yenisini isteyin.")
LINK_FAILED_TEXT = N_("Bağlantı şu anda işlenemedi; biraz sonra yeniden deneyin.")
# 12.1.7 (§D97 b, §D98): bağlı olmayana tek yanıt; numara ayrı satırda, yalnız rakam (uzun basınca
# tek başına kopyalanır, `parse_telegram_id` düz sayıyı kabul eder).
NOT_LINKED_TEXT = N_(
    "Bu Telegram henüz Documania'ya bağlı değil. Bağlamak için panelde Hesabım → Telegram'ı açın. "
    "Telegram numaranız:"
)
YOUR_NUMBER_TEXT = N_("Telegram numaranız:")
# Aynı sohbete en çok bu sıklıkla "bağlı değil" yanıtı gider; aradaki `/start` sessizdir.
IDENTITY_REPLY_INTERVAL = timedelta(hours=1)

# `build_application`'a dil verilmezse tercihi olmayan kullanıcının ve kişisi bilinmeyen yanıtın
# dili (12.1.6). `main` ayardaki `PANEL_DEFAULT_LANGUAGE`'ı açıkça verir; bot testleri bunu `tr`
# yapar (`tests/telegram/conftest.py`), panel testlerindeki gibi.
FALLBACK_LANGUAGE = DEFAULT_LANGUAGE

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


@dataclass(frozen=True, slots=True)
class Admission:
    """Kapıdan geçen kimlik: bağlı panel kullanıcısının arayüz dili (`users.language`, boş
    olabilir; 12.1.6)."""

    language: str | None = None


def admission(session_factory: sessionmaker[Session], telegram_id: int) -> Admission | None:
    """Kimlik listedeyse (`allowed` satırı ve etkin panel kullanıcısı; K13, 12.1.3) bağlı
    kullanıcının diliyle `Admission`, değilse `None`. İzin ve dil tek sorguda okunur."""
    query = (
        permitted_ids().add_columns(User.language).where(TelegramUser.telegram_id == telegram_id)
    )
    with session_factory() as session:
        row = session.execute(query).first()
    return None if row is None else Admission(row.language)


def is_whitelisted(session_factory: sessionmaker[Session], telegram_id: int) -> bool:
    """`telegram_users`'ta `allowed` satırı olan ve panel kullanıcısı etkin olan kimlik listededir
    (K13, 12.1.3: pasif panel kullanıcısının kimlikleri yanıt almaz)."""
    return admission(session_factory, telegram_id) is not None


def reply_language(language: str | None, default: str) -> str:
    """Yanıtın dili: geçerli tercih, değilse `default`."""
    return language if language is not None and is_supported(language) else default


class WhitelistGate:
    """Her güncellemeyi öteki işleyicilerden önce süzer (12.1.2): izin yoksa sessizce durdurur.
    İzin verdiği güncellemenin dilini (12.1.6) yazar: kullanıcının tercihi ya da varsayılan."""

    def __init__(
        self, session_factory: sessionmaker[Session], default_language: str = DEFAULT_LANGUAGE
    ) -> None:
        self._session_factory = session_factory
        self._default_language = default_language

    async def __call__(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        # Önceki güncellemenin dili sızmasın: kişi bilinene kadar varsayılan dil.
        activate_language(self._default_language)
        language = await self._admit(update)
        if language is None:
            # Kimlik ve içerik loga yazılmaz (CONVENTIONS §6); yalnız güncelleme numarası.
            logger.info("Beyaz liste dışı güncelleme yok sayıldı (update_id=%s)", update.update_id)
            raise ApplicationHandlerStop
        activate_language(language)

    async def _admit(self, update: Update) -> str | None:
        """İzin varsa yanıtın dili, yoksa `None`; liste ve dil tek sorguda okunur (kapı sıradaki
        güncellemeyi bekletmesin)."""
        user, chat = update.effective_user, update.effective_chat
        # Yanıt sohbetteki herkese görünür: yalnız listedeki kullanıcıyla özel sohbette konuşulur,
        # grupta listedeki biri yazsa bile listede olmayan üyelere yanıt gitmez.
        if user is None or chat is None or chat.type != ChatType.PRIVATE:
            return None
        try:
            return await asyncio.to_thread(self._read, user.id)
        except Exception as exc:
            # python-telegram-bot işleyicideki hatadan sonra sonraki gruplara geçer; kapı hata
            # verince açık kalmasın diye hata "izin yok" sayılır. Hata metni (SQL parametreleri
            # kullanıcı kimliğini taşır) loga yazılmaz, yalnız türü.
            logger.error("Beyaz liste okunamadı; güncelleme reddedildi (%s)", type(exc).__name__)
            return None

    def _read(self, telegram_id: int) -> str | None:
        admitted = admission(self._session_factory, telegram_id)
        if admitted is None:
            return None
        return reply_language(admitted.language, self._default_language)


def with_number(text: str, telegram_id: int) -> str:
    """Metnin sonuna Telegram numarasını ekler: "Telegram numaranız:" ve ayrı satırda yalnız
    rakamlar (12.1.7)."""
    return f"{text}\n\n{gettext(YOUR_NUMBER_TEXT)}\n{telegram_id}"


def help_reply(telegram_id: int) -> str:
    """İzinli kişinin `/start`/`/yardim` yanıtı: yardım ve son satırda Telegram numarası."""
    return with_number(gettext(HELP_TEXT), telegram_id)


def not_linked_reply(telegram_id: int) -> str:
    """Bağlı olmayana tek yanıt (12.1.7): kayıtsız, izni kapalı, pasif — hepsi aynı metin."""
    return f"{gettext(NOT_LINKED_TEXT)}\n{telegram_id}"


class IdentityReplies:
    """Sohbet başına "bağlı değil" yanıtının sıklık sınırı (bellekte; bot yeniden başlarsa
    sıfırlanır). `interval` içindeki tekrar sessizdir."""

    def __init__(
        self,
        *,
        interval: timedelta = IDENTITY_REPLY_INTERVAL,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._interval = interval.total_seconds()
        self._clock = clock
        self._last: dict[int, float] = {}

    def take(self, chat_id: int) -> bool:
        """Bu sohbete şimdi yanıt verilebilir mi; verilebilirse anı kaydeder."""
        now = self._clock()
        for chat in [c for c, at in self._last.items() if now - at >= self._interval]:
            del self._last[chat]
        if chat_id in self._last:
            return False
        self._last[chat_id] = now
        return True


class IdentityStart:
    """Argümansız `/start` (12.1.7): beyaz liste kapısından önce, yalnız özel sohbette çalışır.
    İzinliyse güncellemeyi kapıya bırakır; değilse (sıklık sınırı içinde) bir kez "bağlı değil"
    yanıtını varsayılan dilde verir ve güncellemeyi bitirir. Kimlik ve ad loga yazılmaz."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        replies: IdentityReplies | None = None,
        default_language: str = DEFAULT_LANGUAGE,
    ) -> None:
        self._session_factory = session_factory
        self._replies = replies or IdentityReplies()
        self._default_language = default_language

    def register(self, application: Application) -> None:
        application.add_handler(
            CommandHandler(
                "start",
                self,
                filters=filters.ChatType.PRIVATE & filters.UpdateType.MESSAGE,
                has_args=False,
            ),
            group=LINK_GROUP,
        )

    async def __call__(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        user, chat, message = update.effective_user, update.effective_chat, update.message
        if user is None or chat is None or message is None:
            raise ApplicationHandlerStop
        try:
            permitted = await asyncio.to_thread(is_whitelisted, self._session_factory, user.id)
        except Exception as exc:
            # Kapı gibi kapalı: okunamazsa yanıt yok. Hata metni kimliği taşır, yalnız türü.
            logger.error("Beyaz liste okunamadı; /start yanıtlanmadı (%s)", type(exc).__name__)
            raise ApplicationHandlerStop from None
        if permitted:
            return  # kapı ve yardım işleyicisi bugünkü gibi
        if not self._replies.take(chat.id):
            logger.info(
                "Bağlı olmayan /start yok sayıldı: sıklık sınırı (update_id=%s)", update.update_id
            )
            raise ApplicationHandlerStop
        activate_language(self._default_language)
        try:
            await message.reply_text(not_linked_reply(user.id))
        except Exception as exc:
            logger.error("Bağlı olmayana yanıt gönderilemedi (%s)", type(exc).__name__)
        logger.info("Bağlı olmayan /start yanıtlandı (update_id=%s)", update.update_id)
        raise ApplicationHandlerStop


def link_reply(result: LinkRedemption) -> str:
    """Bağlama sonucunun yanıtı; geçersiz, süresi dolmuş ya da kullanılmış kod ve pasif kullanıcı
    için tek genel yanıt."""
    match result.outcome:
        case LinkOutcome.LINKED:
            return gettext(LINKED_TEXT).format(username=result.username)
        case LinkOutcome.ALREADY_LINKED:
            return gettext(ALREADY_LINKED_TEXT).format(username=result.username)
        case LinkOutcome.BLOCKED:
            return gettext(LINK_BLOCKED_TEXT)
        case LinkOutcome.TAKEN:
            return gettext(LINK_TAKEN_TEXT)
        case _:
            return gettext(INVALID_LINK_TEXT)


class LinkStart:
    """`/start <kod>` (12.1.4): beyaz liste kapısından önce, yalnız özel sohbette çalışır; kodu
    gönderenin kimliğine uygular ve sonucu kodun kullanıcısının dilinde yanıtlar (12.1.6; geçersiz
    kod varsayılan dilde). Sohbet art arda `LINK_ATTEMPT_LIMIT` geçersiz
    kod gönderdiyse bir saat hiç yanıt almaz (`LinkAttempts`). Güncelleme her durumda burada biter.
    Kod, kimlik ve kullanıcı adı loga yazılmaz; yalnız sonuç ve güncelleme numarası."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        attempts: LinkAttempts | None = None,
        default_language: str = DEFAULT_LANGUAGE,
    ) -> None:
        self._session_factory = session_factory
        self._attempts = attempts or LinkAttempts()
        self._default_language = default_language

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
        # Kodun kişisi bilinene kadar (ve geçersiz kodda) varsayılan dil.
        activate_language(self._default_language)
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
            await message.reply_text(gettext(LINK_FAILED_TEXT))
            return
        if result.outcome is LinkOutcome.INVALID:
            self._attempts.failed(chat.id)
        elif result.outcome in (LinkOutcome.LINKED, LinkOutcome.ALREADY_LINKED):
            self._attempts.succeeded(chat.id)
        logger.info("Telegram bağlantı kodu: %s (update_id=%s)", result.outcome, update.update_id)
        activate_language(reply_language(result.language, self._default_language))
        text = link_reply(result)
        if result.outcome in (LinkOutcome.LINKED, LinkOutcome.ALREADY_LINKED):
            text = with_number(text, user.id)  # 12.1.7: bağlandı yanıtı numarayı da söyler
        await message.reply_text(text)

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
    message, user = update.effective_message, update.effective_user
    if message is not None:
        text = help_reply(user.id) if user is not None else gettext(HELP_TEXT)
        await message.reply_text(text)


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
    identity_replies: IdentityReplies | None = None,
    intake: DocumentIntake | None = None,
    document_requests: DocumentRequests | None = None,
    notifier: Notifier | None = None,
    default_language: str | None = None,
) -> Application:
    """Bağlantı kodu (`/start <kod>`, 12.1.4), beyaz liste kapısı, komut, (`intake` verilirse)
    belge alma ve (`document_requests` verilirse) belge isteği işleyicileriyle bot uygulamasını
    kurar (ağa çıkmaz); `layout` verilirse bot başlarken kullanıcı adını veri dizinine yazar,
    `notifier` verilirse bot başlarken bildirim taraması açılır, dururken kapanır (12.4).

    `builder` testte sahte bir aktarıcıyla ön ayarlı gelir; verilmezse varsayılan kurulur.
    `link_attempts` ve `identity_replies` testte saati elle ilerleyen sayaçlardır.
    `default_language` tercihi olmayan kullanıcının ve kişisi bilinmeyen yanıtın dilidir (12.1.6;
    üretimde `PANEL_DEFAULT_LANGUAGE`, verilmezse `FALLBACK_LANGUAGE`)."""
    default_language = default_language or FALLBACK_LANGUAGE
    if not is_supported(default_language):
        raise ValueError(f"desteklenmeyen dil: {default_language!r}")
    application = (builder or ApplicationBuilder()).token(config.token).build()
    LinkStart(session_factory, link_attempts, default_language).register(application)
    IdentityStart(session_factory, identity_replies, default_language).register(application)
    application.add_handler(
        TypeHandler(Update, WhitelistGate(session_factory, default_language), block=True),
        group=GATE_GROUP,
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
        default_language=settings.panel_default_language,
    )
    run(application, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
