"""Telegram hesabını bağlantıyla bağlama (PRD 12.1.4; PLAN.md §D87).

Web paneli bir kişinin Telegram kimliğini kendi başına bilemez; kimliği Telegram yalnız kişi bota
yazdığında verir. Bu yüzden yönetici Kullanıcılar sayfasında bir panel kullanıcısı için **tek
kullanımlık** bir bot bağlantısı üretir (`https://t.me/<bot>?start=<kod>`, `link_url`); kişi
bağlantıyı açıp «Başlat»a basınca bot `/start <kod>` alır ve gönderenin kimliğini o kullanıcıya
izinli bağlar (`redeem_link_code`). Elle kimlik girme (12.1.3) yedek yol olarak kalır.

**Kod.** `secrets.token_urlsafe(16)`: 22 karakter, 128 bit; Telegram'ın `start` sınırına (1–64,
`[A-Za-z0-9_-]`) uyar. Veritabanında yalnız SHA-256 özeti durur (`telegram_link_codes`), düz kod
bir kez döner. Kod 10 dakika (`LINK_CODE_TTL`) ve bir kez geçerlidir; aynı kullanıcıya üretilen
yeni kod öncekini `revoked_at` ile geçersiz kılar; pasif kullanıcıya kod üretilmez. Satır silinmez
(R11). Üretim `TELEGRAM_LINK_CREATED` {target_user_id, expires_at} yazar — kod olaya girmez.

**Bağlama.** Kod bulunur, kullanılmamış, iptal edilmemiş, süresi dolmamış ve kullanıcısı etkin
olmalıdır; değilse `INVALID` (bot tek bir genel yanıt verir). Sonra kimliğin durumu:

- kayıtlı değil → `add_telegram_id` ile izinli bağlanır, kod aynı işlemde kullanılmış yazılır,
  `TELEGRAM_USER_CHANGED` {…, added: true, via: "link"} kodu üreten yöneticinin adıyla (`LINKED`);
- aynı kullanıcıda izinli → değişiklik yok, kod kullanılır (`ALREADY_LINKED`);
- aynı kullanıcıda engelli → açılmaz, yöneticinin kararıdır (`BLOCKED`); kod kullanılmaz;
- başka kullanıcıya bağlı → reddedilir, kod kullanılmaz (`TAKEN`).

Kod koşullu güncellemeyle tüketilir: aynı kod iki kez aynı anda gelirse biri kazanır. Reddedilen
bağlama kodu tüketmez; doğru kişi aynı bağlantıyı yine kullanabilir (§D89). Commit çağırana aittir.

**Kaba kuvvet.** 128 bitlik kod tahmin edilemez; yine de bot sohbet başına art arda geçersiz kod
denemesini sayar (`LinkAttempts`, bellekte) ve 5'ten sonra bir saat o sohbete yanıt vermez.

**Bot adı.** Bağlantı botun Telegram kullanıcı adını ister; elle ayar yoktur. Bot açılışta `getMe`
yanıtındaki adı veri dizinine yazar (`write_bot_info` → `telegram/bot.json`), panel oradan okur
(`read_bot_info`); dosya yoksa bot bu kurulumda hiç çalışmamıştır.

Kod, Telegram kimliği ve kullanıcı adı loga yazılmaz (CONVENTIONS §6).
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import TelegramLinkCode, TelegramUser, User, utcnow
from app.events import EventType, record_event
from app.i18n import N_
from app.storage import DataLayout, replace_file
from app.telegram.whitelist import TELEGRAM_ID_MAX, TelegramIdTakenError, add_telegram_id

LINK_CODE_TTL = timedelta(minutes=10)
LINK_CODE_BYTES = 16
"""`secrets.token_urlsafe(16)` → 22 karakter (128 bit)."""
LINK_VIA = "link"
"""`TELEGRAM_USER_CHANGED` olayında kimliğin bağlantıyla bağlandığını söyleyen `via` değeri."""

LINK_ATTEMPT_LIMIT = 5
LINK_SILENCE = timedelta(hours=1)

INACTIVE_TARGET = N_(
    "Pasif kullanıcıya Telegram bağlantısı üretilmez; önce kullanıcıyı etkinleştirin."
)

TELEGRAM_LINK_BASE = "https://t.me/"

# Telegram'ın `start` parametresi: 1–64 karakter, yalnız A-Z a-z 0-9 _ -.
_START_PAYLOAD = re.compile(r"[A-Za-z0-9_-]{1,64}")
# Telegram kullanıcı adı: 5–32 karakter, harfle başlar, harf, rakam ve alt çizgi.
_BOT_USERNAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{4,31}")


class LinkTargetInactiveError(ValueError):
    """Pasif panel kullanıcısına bağlantı üretilmez (panelde 409)."""


class LinkOutcome(enum.StrEnum):
    LINKED = "linked"
    ALREADY_LINKED = "already_linked"
    BLOCKED = "blocked"
    TAKEN = "taken"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class IssuedLinkCode:
    """Üretilen kod: düz kod yalnız burada, bir kez döner; `repr`'a girmez."""

    code: str = field(repr=False)
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class LinkRedemption:
    """Bağlama sonucu; `username` bağlanan panel kullanıcısının adıdır (`LINKED`,
    `ALREADY_LINKED`), öbür sonuçlarda boştur. `language` kodun kullanıcısının arayüz dili
    (`users.language`; 12.1.6, §D92 k): yanıt o dilde yazılır. Geçersiz kodda ve tercihi
    olmayan kullanıcıda boştur."""

    outcome: LinkOutcome
    username: str | None = None
    language: str | None = None


@dataclass(frozen=True, slots=True)
class BotInfo:
    username: str
    updated_at: datetime | None = None


def hash_link_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def link_url(bot_username: str, code: str) -> str:
    """Kişinin açacağı bağlantı: `https://t.me/<bot>?start=<kod>`."""
    return f"{TELEGRAM_LINK_BASE}{bot_username}?start={code}"


# --- kod üretimi (panel) ------------------------------------------------------------------------


def create_link_code(
    session: Session, target: User, *, actor: str, now: datetime | None = None
) -> IssuedLinkCode:
    """`target` için yeni bağlantı kodu üretir; bu kullanıcının süresi dolmamış, kullanılmamış
    kodlarını iptal eder ve `TELEGRAM_LINK_CREATED` yazar. Pasif kullanıcıda
    `LinkTargetInactiveError`."""
    if not target.active:
        raise LinkTargetInactiveError(INACTIVE_TARGET)
    now = now or utcnow()
    session.execute(
        update(TelegramLinkCode)
        .where(
            TelegramLinkCode.user_id == target.id,
            TelegramLinkCode.used_at.is_(None),
            TelegramLinkCode.revoked_at.is_(None),
            TelegramLinkCode.expires_at > now,
        )
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    code = secrets.token_urlsafe(LINK_CODE_BYTES)
    expires_at = now + LINK_CODE_TTL
    session.add(
        TelegramLinkCode(
            code_hash=hash_link_code(code),
            user_id=target.id,
            created_by=actor,
            created_at=now,
            expires_at=expires_at,
        )
    )
    record_event(
        session,
        EventType.TELEGRAM_LINK_CREATED,
        actor=actor,
        data={"target_user_id": target.id, "expires_at": expires_at.isoformat()},
    )
    return IssuedLinkCode(code=code, expires_at=expires_at)


# --- bağlama (bot) ------------------------------------------------------------------------------


def _usable(link: TelegramLinkCode, now: datetime) -> bool:
    return link.used_at is None and link.revoked_at is None and link.expires_at > now


def _account(session: Session, telegram_id: int) -> TelegramUser | None:
    return session.get(TelegramUser, telegram_id, populate_existing=True)


def _consume(session: Session, link: TelegramLinkCode, telegram_id: int, now: datetime) -> bool:
    """Kodu koşullu güncellemeyle kullanılmış yazar; aynı anda başka istek tükettiyse `False`."""
    result = session.execute(
        update(TelegramLinkCode)
        .where(
            TelegramLinkCode.id == link.id,
            TelegramLinkCode.used_at.is_(None),
            TelegramLinkCode.revoked_at.is_(None),
            TelegramLinkCode.expires_at > now,
        )
        .values(used_at=now, used_telegram_id=telegram_id)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def redeem_link_code(
    session: Session, code: str, telegram_id: int, *, now: datetime | None = None
) -> LinkRedemption:
    """`/start <kod>` ile gelen kodu `telegram_id`'ye uygular (modül açıklamasındaki kurallar)."""
    now = now or utcnow()
    invalid = LinkRedemption(LinkOutcome.INVALID)
    if not _START_PAYLOAD.fullmatch(code) or not 1 <= telegram_id <= TELEGRAM_ID_MAX:
        return invalid
    link = session.scalar(
        select(TelegramLinkCode).where(TelegramLinkCode.code_hash == hash_link_code(code))
    )
    if link is None or not _usable(link, now) or not link.user.active:
        return invalid
    target = link.user
    account = _account(session, telegram_id)
    if account is None:
        try:
            with session.begin_nested():
                if not _consume(session, link, telegram_id, now):
                    return invalid
                add_telegram_id(session, target, telegram_id, actor=link.created_by, via=LINK_VIA)
        except TelegramIdTakenError:
            # Bu arada kimliği başka bir yol bağladı: kodun tüketimi kayıt noktasıyla geri alındı;
            # yanıt kimliğin şimdiki durumuna göre verilir.
            account = _account(session, telegram_id)
        else:
            return LinkRedemption(LinkOutcome.LINKED, target.username, target.language)
    if account is None or account.user_id != target.id:
        return LinkRedemption(LinkOutcome.TAKEN, language=target.language)
    if not account.allowed:
        return LinkRedemption(LinkOutcome.BLOCKED, language=target.language)
    if not _consume(session, link, telegram_id, now):
        return invalid
    return LinkRedemption(LinkOutcome.ALREADY_LINKED, target.username, target.language)


class LinkAttempts:
    """Sohbet başına art arda geçersiz kod denemesi (bellekte, §D87-d).

    `limit` geçersiz denemeden sonra sohbet `silence` boyunca sessizdir: bot o sohbetten gelen
    `/start <kod>`'u hiç işlemez. Başarılı bağlama sayacı sıfırlar; son geçersiz denemeden
    `silence` kadar sonra sayaç kendiliğinden unutulur. Bot yeniden başlarsa sayaç sıfırlanır."""

    def __init__(
        self,
        *,
        limit: int = LINK_ATTEMPT_LIMIT,
        silence: timedelta = LINK_SILENCE,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._silence = silence.total_seconds()
        self._clock = clock
        # sohbet → (art arda geçersiz deneme sayısı, son denemenin anı)
        self._failures: dict[int, tuple[int, float]] = {}
        # sohbet → sessizliğin bittiği an
        self._silenced_until: dict[int, float] = {}

    def silenced(self, chat_id: int) -> bool:
        self._forget_old(self._clock())
        return chat_id in self._silenced_until

    def failed(self, chat_id: int) -> None:
        now = self._clock()
        self._forget_old(now)
        count = self._failures.get(chat_id, (0, now))[0] + 1
        if count >= self._limit:
            self._failures.pop(chat_id, None)
            self._silenced_until[chat_id] = now + self._silence
        else:
            self._failures[chat_id] = (count, now)

    def succeeded(self, chat_id: int) -> None:
        self._failures.pop(chat_id, None)

    def _forget_old(self, now: float) -> None:
        for chat_id in [c for c, until in self._silenced_until.items() if until <= now]:
            del self._silenced_until[chat_id]
        cutoff = now - self._silence
        for chat_id in [c for c, (_n, at) in self._failures.items() if at <= cutoff]:
            del self._failures[chat_id]


# --- botun kullanıcı adı (veri dizini) ----------------------------------------------------------


def write_bot_info(layout: DataLayout, username: str, *, now: datetime | None = None) -> None:
    """Botun Telegram kullanıcı adını `telegram/bot.json`'a atomik yazar (bot açılışı)."""
    if not _BOT_USERNAME.fullmatch(username):
        raise ValueError("Geçersiz bot kullanıcı adı.")
    payload = {"username": username, "updated_at": (now or utcnow()).isoformat()}
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    replace_file(layout.telegram_bot_info_path, content.encode())


def read_bot_info(layout: DataLayout) -> BotInfo | None:
    """`telegram/bot.json`; dosya yoksa, okunamıyorsa ya da adı geçersizse `None`."""
    try:
        data = json.loads(layout.telegram_bot_info_path.read_bytes())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    username = data.get("username")
    if not isinstance(username, str) or not _BOT_USERNAME.fullmatch(username):
        return None
    updated_at = data.get("updated_at")
    try:
        parsed = datetime.fromisoformat(updated_at) if isinstance(updated_at, str) else None
    except ValueError:
        parsed = None
    return BotInfo(username=username, updated_at=parsed)
