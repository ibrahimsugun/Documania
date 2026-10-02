"""Telegram beyaz listesi: kime yanıt verilir, panelden nasıl yönetilir (PRD 12.1.2, 12.1.3; K13;
PLAN.md §C92-e).

Bot yalnız **izinli** kimliğe yanıt verir: `telegram_users.allowed` doğru ve kimliğin bağlı olduğu
panel kullanıcısı etkin (`users.active`, 10.1.4). Pasife alınan panel kullanıcısının kimlikleri,
izinleri açık kalsa da yanıt almaz; kullanıcı yeniden etkinleşince yanıt yeniden başlar. Kapı
(`bot.admission`), belge gönderimi (`intent.DocumentRequests._release`) ve bildirim alıcıları
(`notify.Notifier`) bu tek tanımı kullanır — `permitted_ids` sorgu, `is_permitted` yüklü satır için.

Yönetim panelin Kullanıcılar sayfasındadır (`app.web.routers.users`): kullanıcıya kimlik eklenir
(`allowed=True`), izin kapatılıp açılır. **Kayıt silinmez** (R11): engellemek `allowed=False`'tur.
Kimlik tablonun birincil anahtarıdır; bu yüzden bir kez bir kullanıcıya bağlanan kimlik başka bir
kullanıcıya bağlanamaz (409). İşlemler tek adımlıdır (§D61-b) ve kullanıcı adıyla
`TELEGRAM_USER_CHANGED` yazar (`target_user_id`, `telegram_id`, `allowed`, `added`). Commit her
zaman çağırana aittir. Kimliği elle girmek yerine yönetici tek kullanımlık bir bot bağlantısı da
üretebilir; kişi bağlantıyı açınca bot kimliği aynı `add_telegram_id` ile bağlar (`via: "link"`,
12.1.4, `app.telegram.link`). Bot kendiliğinden kimseyi listeye almaz: kod yöneticiden gelir.

**Kimlik nereden gelir (PLAN §D86).** Kimlik telefon numarası değil, Telegram'ın hesaba verdiği
değişmez sayıdır; bot gönderenin `user.id`'sini bununla karşılaştırır. Kişi kendi kimliğini
Telegram'da @userinfobot'a yazarak öğrenir; bot `Id: 123456789` satırıyla yanıt verir. Panel bu
satırı kopyalanmış hâliyle de kabul eder (`parse_telegram_id`).
"""

from __future__ import annotations

import re

from sqlalchemy import Select, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import TelegramUser, User
from app.events import EventType, record_event
from app.i18n import N_, Translatable

# `telegram_users.telegram_id` `BigInteger`'dır: işaretli 64 bit. Telegram kullanıcı kimlikleri
# pozitiftir (grup ve kanal kimlikleri negatif; beyaz liste yalnız özel sohbettir).
TELEGRAM_ID_MAX = 2**63 - 1
TELEGRAM_ID_MAX_DIGITS = len(str(TELEGRAM_ID_MAX))


INVALID_TELEGRAM_ID = N_(
    "Telegram kimliği yalnız rakamlardan oluşan pozitif bir sayı olmalı (örn. 123456789). Telefon "
    "numarası değildir: kişi kimliğini Telegram'da @userinfobot'a yazarak öğrenir."
)

USERINFOBOT_URL = "https://t.me/userinfobot"
"""Kişinin kendi Telegram kimliğini öğrendiği bot; yanıtı `Id: 123456789` satırını taşır."""

# @userinfobot yanıtından kopyalanan satır: `Id: 123456789` (harf büyüklüğü, iki nokta ve boşluk
# isteğe bağlı; Türkçe klavyede `İd`/`ıd` da). Sayı kısmı aşağıdaki kuralla ayrıca denetlenir.
_PASTED_ID = re.compile(r"[iIİı][dD]\s*:?\s*(\S+)")


class TelegramIdError(ValueError):
    """Verilen değer pozitif bir Telegram kullanıcı kimliği değil (panelde 422)."""


class TelegramIdTakenError(ValueError):
    """Kimlik zaten bir kullanıcıya bağlı — bu kullanıcıya ya da başkasına (panelde 409)."""


class TelegramStatusError(ValueError):
    """Kimlik zaten istenen durumda (panelde 409)."""


# --- kime yanıt verilir (12.1.2) --------------------------------------------------------------


def permitted_ids() -> Select[tuple[int]]:
    """Botun yanıt verdiği Telegram kimlikleri: izin açık ve panel kullanıcısı etkin."""
    return (
        select(TelegramUser.telegram_id)
        .join(User, User.id == TelegramUser.user_id)
        .where(TelegramUser.allowed.is_(True), User.active.is_(True))
    )


def is_permitted(account: TelegramUser | None) -> bool:
    """Yüklü satır için `permitted_ids` ile aynı kural."""
    return account is not None and bool(account.allowed) and bool(account.user.active)


# --- panelden yönetim (12.1.3) ----------------------------------------------------------------


def parse_telegram_id(value: str) -> int:
    """Formdan gelen kimlik: yalnız ASCII rakam, 1 ile `TELEGRAM_ID_MAX` arası. @userinfobot
    yanıtından kopyalanan `Id: 123456789` satırı da kabul edilir; sayı kısmı aynı kurala uyar."""
    text = value.strip()
    if not text:
        raise TelegramIdError(N_("Telegram kimliği boş olamaz."))
    pasted = _PASTED_ID.fullmatch(text)
    if pasted is not None:
        text = pasted.group(1)
    if not (text.isascii() and text.isdigit()) or len(text) > TELEGRAM_ID_MAX_DIGITS:
        raise TelegramIdError(INVALID_TELEGRAM_ID)
    telegram_id = int(text)
    if not 1 <= telegram_id <= TELEGRAM_ID_MAX:
        raise TelegramIdError(INVALID_TELEGRAM_ID)
    return telegram_id


def _record(
    session: Session, account: TelegramUser, *, actor: str, added: bool, via: str | None = None
) -> None:
    data: dict[str, object] = {
        "target_user_id": account.user_id,
        "telegram_id": account.telegram_id,
        "allowed": account.allowed,
        "added": added,
    }
    if via is not None:
        data["via"] = via
    record_event(session, EventType.TELEGRAM_USER_CHANGED, actor=actor, data=data)


def _owner_id(session: Session, telegram_id: int) -> int | None:
    return session.scalar(
        select(TelegramUser.user_id).where(TelegramUser.telegram_id == telegram_id)
    )


def _taken(telegram_id: int, owner_id: int | None, target: User) -> TelegramIdTakenError:
    if owner_id == target.id:
        return TelegramIdTakenError(
            Translatable(N_("{id} Telegram kimliği zaten bu kullanıcıya bağlı."), id=telegram_id)
        )
    return TelegramIdTakenError(
        Translatable(
            N_(
                "{id} Telegram kimliği başka bir kullanıcıya bağlı; kayıt silinmediği için "
                "taşınamaz."
            ),
            id=telegram_id,
        )
    )


def add_telegram_id(
    session: Session, target: User, telegram_id: int, *, actor: str, via: str | None = None
) -> TelegramUser:
    """`target` kullanıcıya izinli (`allowed=True`) Telegram kimliği bağlar ve
    `TELEGRAM_USER_CHANGED` (`added: true`) yazar. Kimlik zaten bağlıysa `TelegramIdTakenError`.
    Karar birincil anahtarındır: ön denetim yapılmaz, aynı anda iki istek aynı kimliği eklerse biri
    kazanır; kaybedenin işlemi kullanılabilir kalır (kayıt noktası geri alınır). `via` verilirse
    olaya yazılır (bağlantıyla bağlamada `"link"`, 12.1.4); panelden elle eklemede yazılmaz."""
    if not 1 <= telegram_id <= TELEGRAM_ID_MAX:
        raise TelegramIdError(INVALID_TELEGRAM_ID)
    account = TelegramUser(telegram_id=telegram_id, user_id=target.id, allowed=True)
    try:
        with session.begin_nested():
            session.add(account)
    except IntegrityError:
        raise _taken(telegram_id, _owner_id(session, telegram_id), target) from None
    _record(session, account, actor=actor, added=True, via=via)
    return account


def set_telegram_allowed(
    session: Session, account: TelegramUser, allowed: bool, *, actor: str
) -> None:
    """İzni açar ya da kapatır; satır silinmez (R11). Zaten o durumdaysa `TelegramStatusError`.
    Koşullu güncellemeyle yapılır: aynı anda iki istek aynı geçişi isterse biri olay yazar."""
    result = session.execute(
        update(TelegramUser)
        .where(
            TelegramUser.telegram_id == account.telegram_id, TelegramUser.allowed.is_(not allowed)
        )
        .values(allowed=allowed)
        .execution_options(synchronize_session=False)
    )
    session.refresh(account)
    if result.rowcount != 1:
        template = (
            N_("{id} Telegram kimliği zaten izinli.")
            if allowed
            else N_("{id} Telegram kimliği zaten engelli.")
        )
        raise TelegramStatusError(Translatable(template, id=account.telegram_id))
    _record(session, account, actor=actor, added=False)
