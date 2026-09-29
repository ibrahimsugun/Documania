"""İki aşamalı onay mekanizması (PRD 10.8.1; K16, §20.6, §20.6.1).

K16'nın manuel işlemleri — belgeyi başka çalışana taşı, kuyruk öğesini ata, onay bekleyen profili
onayla, yeni türü onayla, arşive taşı, taramayı yoksay, çalışan profilini düzenle, çalışanı pasife
al ve yeniden etkinleştir (§D61) — iki onay ister. Onay metinleri §20.6 tablosundan **birebir**
buradadır (`CONFIRMATION_TEXTS`); `<Ad Soyad>`, `<Tür adı>`, `<N>` ve `<M>` yer tutucuları çalışma
zamanında `fill` ile doldurulur, pencere kendi cümlesini yazmaz.

Metni göstermek tek başına yetmez — istemci atlanabilir. Sunucu tarafı akış (§20.6.1):

1. İstemci birinci onaydan sonra "hazırlık" isteği gönderir; sunucu `issue_confirmation` ile tek
   kullanımlık bir belirteç üretir: rastgele (`secrets`), oturuma, kullanıcıya, işleme ve hedef
   kayda bağlı, `CONFIRMATION_TTL` (10 dakika) geçerli. Belirtecin yalnız SHA-256 özeti
   `confirmation_tokens`'ta durur; üretim anı birinci onayın zamanıdır.
2. İstemci ikinci onaydan sonra asıl isteği belirteçle gönderir; `confirm_operation` belirteci
   doğrular, **tüketir** ve `USER_CONFIRMED` olayını (kullanıcı adı, işlem, hedef, iki onayın
   zamanı) yazar. Ardından çağıran işlemin kendi olayını düşer (`MANUAL_MOVE`, `MANUAL_ASSIGN`…).
3. Belirteçsiz, tanınmayan, süresi geçmiş, tüketilmiş ya da başka oturuma, kullanıcıya, işleme
   veya hedefe ait belirteç `ConfirmationRefusedError`'dır; çağıran bunu 400'e çevirir ve işlem
   yapılmaz.

Tüketme, onay olayı ve işlemin kendisi çağıranın **tek işlemindedir**: işlem düşer ve geri alınırsa
belirteç de tüketilmemiş kalır (aynı onaylanmış işlem süresi içinde yeniden denenebilir); başarılı
işlemden sonra aynı belirteçle gelen istek reddedilir. Tüketme koşullu bir güncellemedir
(`consumed_at IS NULL`): aynı belirteçle eşzamanlı iki istekten yalnız biri geçer.
"""

from __future__ import annotations

import enum
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import ConfirmationToken, utcnow
from app.events import EventType, record_event
from app.web.auth import SESSION_COOKIE, PanelUser

CONFIRMATION_TTL = timedelta(minutes=10)  # §20.6.1 adım 2
# JSON API'de belirteç bu başlıkla gelir; panel formları `confirmation` alanını kullanır.
CONFIRMATION_HEADER = "X-Confirmation-Token"
CONFIRMATION_REFUSED = (
    "Onay geçersiz: belirteç yok, süresi geçmiş, daha önce kullanılmış ya da bu işleme ait değil."
)
TARGET_MAX_LENGTH = 255  # `confirmation_tokens.target`


class Operation(enum.StrEnum):
    """Onay belirtecinin bağlandığı işlem; `USER_CONFIRMED` olayının `operation` değeri."""

    MOVE = "move"
    ASSIGN = "assign"
    APPROVE_PROFILE = "approve_profile"
    APPROVE_TYPE = "approve_type"
    ARCHIVE = "archive"
    DISMISS = "dismiss"  # taramayı (partiyi) yoksay, 10.3.4
    EDIT_EMPLOYEE = "edit_employee"  # çalışan profilini düzenle, 10.5.6 (§D61)
    DEACTIVATE_EMPLOYEE = "deactivate_employee"  # çalışanı pasife al, 10.5.7 (§D61)
    REACTIVATE_EMPLOYEE = "reactivate_employee"  # çalışanı yeniden etkinleştir, 10.5.7 (§D61)
    # §20.6'nın dışında: yeniden analizin onayı (10.3.2, metinler PLAN.md §D23).
    REANALYZE = "reanalyze"
    # §20.6'nın dışında (K16 dışı, PLAN.md §D58): eğitim örneğini başka türe taşı ve örneklerden
    # çıkar (11.9.4); metinler `app.web.routers.training`'dedir.
    TRAINING_MOVE = "training_move"
    TRAINING_REMOVE = "training_remove"
    # §20.6'nın dışında (PLAN.md §D58): harita ile toplu taramayı başlat (11.9.5).
    TRAINING_MAP = "training_map"


@dataclass(frozen=True, slots=True)
class ConfirmationTexts:
    first: str
    second: str


NAME_PLACEHOLDER = "<Ad Soyad>"
TYPE_PLACEHOLDER = "<Tür adı>"
# `<N>`: taramayı yoksaymada kuyruk öğesi sayısı (`queue_items`), profil düzenlemede yeniden
# adlandırılacak belge dosyası sayısı (`count`).
COUNT_PLACEHOLDER = "<N>"
DOCUMENT_COUNT_PLACEHOLDER = "<M>"

# §20.6 — metinler BİREBİR, değiştirilmez; `tests/web/test_confirm.py` PRD tablosuyla karşılaştırır.
CONFIRMATION_TEXTS: dict[Operation, ConfirmationTexts] = {
    Operation.MOVE: ConfirmationTexts(
        "Bu belgeyi başka bir çalışana taşımak üzeresiniz. Emin misiniz?",
        "Bu işlem sistemdeki belge organizasyonunu değiştirecektir. Son kararınız mı?",
    ),
    Operation.ASSIGN: ConfirmationTexts(
        "Bu belgeyi <Ad Soyad> çalışanına atamak üzeresiniz. Emin misiniz?",
        "Bu işlem sistemdeki belge organizasyonunu değiştirecektir. Son kararınız mı?",
    ),
    Operation.APPROVE_PROFILE: ConfirmationTexts(
        "<Ad Soyad> için yeni bir çalışan profili oluşturmak üzeresiniz. Emin misiniz?",
        "Bu işlem sistemde kalıcı bir çalışan kaydı oluşturacaktır. Son kararınız mı?",
    ),
    Operation.APPROVE_TYPE: ConfirmationTexts(
        "<Tür adı> belge türünü standart türler arasına eklemek üzeresiniz. Emin misiniz?",
        "Bu işlem bundan sonraki tüm belge analizlerini etkileyecektir. Son kararınız mı?",
    ),
    Operation.ARCHIVE: ConfirmationTexts(
        "Bu belgeyi arşive taşımak üzeresiniz. Emin misiniz?",
        "Belge çalışanın Hazır klasöründen çıkacaktır. Son kararınız mı?",
    ),
    Operation.DISMISS: ConfirmationTexts(
        "Bu taramayı yoksaymak üzeresiniz. Emin misiniz?",
        "Parti ve bekleyen <N> kuyruk öğesi listelerden kalkacaktır; üretilmiş <M> belge yerinde "
        "kalır. Son kararınız mı?",
    ),
    Operation.EDIT_EMPLOYEE: ConfirmationTexts(
        "Bu çalışanın profil bilgilerini değiştirmek üzeresiniz. Emin misiniz?",
        "Ad ya da soyad değiştiyse klasör ve <N> belge dosyası yeniden adlandırılacaktır. Son "
        "kararınız mı?",
    ),
    Operation.DEACTIVATE_EMPLOYEE: ConfirmationTexts(
        "<Ad Soyad> çalışanını pasife almak üzeresiniz. Emin misiniz?",
        "Bu çalışana gelen yeni belgeler otomatik yerleşmeyecek, kuyruğa düşecektir. Son "
        "kararınız mı?",
    ),
    Operation.REACTIVATE_EMPLOYEE: ConfirmationTexts(
        "<Ad Soyad> çalışanını yeniden etkinleştirmek üzeresiniz. Emin misiniz?",
        "Çalışan listeye dönecek ve yeni belgeleri yeniden otomatik yerleşecektir. Son kararınız "
        "mı?",
    ),
}


def fill(
    text: str,
    *,
    name: str | None = None,
    type_name: str | None = None,
    queue_items: int | None = None,
    documents: int | None = None,
    count: int | None = None,
) -> str:
    """Onay metninin yer tutucularını doldurur; metinde olup değeri verilmeyen yer tutucu
    `ValueError`'dır (yer tutuculu metin kullanıcıya gitmesin). `<N>` `queue_items` ya da `count`
    ile dolar; ikisi birden verilemez."""
    if queue_items is not None and count is not None:
        raise ValueError("<N> yer tutucusu queue_items ya da count ile dolar, ikisi birden değil")
    number = queue_items if queue_items is not None else count
    for placeholder, value in (
        (NAME_PLACEHOLDER, name),
        (TYPE_PLACEHOLDER, type_name),
        (COUNT_PLACEHOLDER, None if number is None else str(number)),
        (DOCUMENT_COUNT_PLACEHOLDER, None if documents is None else str(documents)),
    ):
        if placeholder in text:
            if value is None:
                raise ValueError(f"Onay metninin {placeholder} yer tutucusu doldurulmadı")
            text = text.replace(placeholder, value)
    return text


def first_text(operation: Operation, **values: Any) -> str:
    return fill(CONFIRMATION_TEXTS[operation].first, **values)


def second_text(operation: Operation, **values: Any) -> str:
    return fill(CONFIRMATION_TEXTS[operation].second, **values)


class ConfirmationRefusedError(ValueError):
    """Onay belirteci doğrulanamadı ya da üretilemedi; işlem yapılmaz (§20.6.1 adım 5)."""


@dataclass(frozen=True, slots=True)
class IssuedConfirmation:
    """`issue_confirmation` sonucu: istemciye verilecek belirteç ve son geçerlilik anı."""

    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ConfirmedAction:
    """Tüketilen belirtecin onayladığı işlem ve iki onayın zamanı."""

    operation: Operation
    target: str
    first_confirmed_at: datetime
    second_confirmed_at: datetime


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _session_hash(request: Request) -> str:
    """İsteğin panel oturumunun kimliği: oturum çerezinin SHA-256 özeti (`user_sessions`
    satırının `token_hash`'iyle aynı değer). Çerez yoksa belirteç ne üretilir ne kabul edilir."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        raise ConfirmationRefusedError("Oturum çerezi yok.")
    return _digest(cookie)


def issue_confirmation(
    session: Session, request: Request, user: PanelUser, operation: Operation, target: str
) -> IssuedConfirmation:
    """Birinci onaydan sonra tek kullanımlık belirteç üretir (§20.6.1 adım 2).

    `target` işlemin hedef kaydını adlandırır (ör. `"<belge>:<çalışan>"`); yalnız aynı işlem ve
    aynı hedefle tüketilebilir. Oturum commit edilmez — hazırlık isteği commit eder.
    """
    if not target or len(target) > TARGET_MAX_LENGTH:
        raise ValueError(f"Onay hedefi boş ya da {TARGET_MAX_LENGTH} karakterden uzun olamaz")
    session_hash = _session_hash(request)
    token = secrets.token_urlsafe(32)
    issued = utcnow()
    row = ConfirmationToken(
        token_hash=_digest(token),
        session_hash=session_hash,
        username=user.username,
        operation=operation.value,
        target=target,
        created_at=issued,
        expires_at=issued + CONFIRMATION_TTL,
    )
    session.add(row)
    session.flush()
    return IssuedConfirmation(token=token, expires_at=row.expires_at)


def consume_confirmation(
    session: Session,
    request: Request,
    user: PanelUser,
    operation: Operation,
    target: str,
    token: str | None,
) -> ConfirmedAction:
    """İkinci onayla gelen belirteci doğrular ve tüketir (§20.6.1 adım 4–5).

    Geçersizse `ConfirmationRefusedError` — hiçbir şey yazılmaz. Tüketme çağıranın işlemindedir:
    işlem geri alınırsa belirteç de tüketilmemiş kalır.
    """
    if not token:
        raise ConfirmationRefusedError("Belirteç yok.")
    session_hash = _session_hash(request)
    token_hash = _digest(token)
    now = utcnow()
    # Doğrulama ve tüketme tek koşullu güncellemedir: aynı belirteçle eşzamanlı iki istekten
    # yalnız biri satırı günceller (ikincisi `consumed_at`'i dolu bulur).
    consumed = session.execute(
        update(ConfirmationToken)
        .where(
            ConfirmationToken.token_hash == token_hash,
            ConfirmationToken.session_hash == session_hash,
            ConfirmationToken.username == user.username,
            ConfirmationToken.operation == operation.value,
            ConfirmationToken.target == target,
            ConfirmationToken.consumed_at.is_(None),
            ConfirmationToken.created_at <= now,
            ConfirmationToken.expires_at >= now,
        )
        .values(consumed_at=now)
        .execution_options(synchronize_session=False)
    )
    row = session.scalar(
        select(ConfirmationToken)
        .where(ConfirmationToken.token_hash == token_hash)
        .execution_options(populate_existing=True)
    )
    if consumed.rowcount == 1 and row is not None:
        return ConfirmedAction(operation, target, row.created_at, now)
    # Ret: nedeni yalnız sunucu tarafında ayırt edilir, istemciye tek genel metin gider.
    if row is None:
        raise ConfirmationRefusedError("Belirteç tanınmıyor.")
    if row.session_hash != session_hash or row.username != user.username:
        raise ConfirmationRefusedError("Belirteç bu oturuma ait değil.")
    if row.operation != operation.value or row.target != target:
        raise ConfirmationRefusedError("Belirteç bu işleme ait değil.")
    if row.consumed_at is not None:
        raise ConfirmationRefusedError("Belirteç daha önce kullanılmış.")
    raise ConfirmationRefusedError("Belirtecin süresi geçmiş.")


def confirm_operation(
    session: Session,
    request: Request,
    user: PanelUser,
    operation: Operation,
    target: str,
    token: str | None,
    *,
    event_target: dict[str, Any],
    upload_id: str | None = None,
    document_id: int | None = None,
    employee_id: str | None = None,
) -> ConfirmedAction:
    """Belirteci tüketir ve `USER_CONFIRMED`'ı yazar (§20.6.1): kullanıcı adı, işlem, hedef
    (`event_target`; kişisel değer taşımaz) ve iki onayın zamanı. İşlemin kendi olayı bundan sonra
    çağıranca düşülür; hepsi çağıranın tek işlemindedir."""
    confirmed = consume_confirmation(session, request, user, operation, target, token)
    record_event(
        session,
        EventType.USER_CONFIRMED,
        upload_id=upload_id,
        document_id=document_id,
        employee_id=employee_id,
        actor=user.username,
        data={
            "operation": operation.value,
            "target": event_target,
            "first_confirmed_at": confirmed.first_confirmed_at.isoformat(),
            "second_confirmed_at": confirmed.second_confirmed_at.isoformat(),
        },
    )
    return confirmed
