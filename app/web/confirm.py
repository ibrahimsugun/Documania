"""İki aşamalı onay mekanizması (PRD 10.8.1; K16, §20.6, §20.6.1).

K16'nın manuel işlemleri — belgeyi başka çalışana taşı, kuyruk öğesini ata, onay bekleyen profili
onayla, yeni türü onayla, arşive taşı, taramayı yoksay, çalışan profilini düzenle, çalışanı pasife
al ve yeniden etkinleştir, profil alt kaydını kaldır, iki çalışanı birleştir, belgeyi arşivden geri
al, kuyruk öğesini kapat (§D61) — iki onay ister. Onay metinleri §20.6 tablosundan **birebir**
buradadır (`CONFIRMATION_TEXTS`); `<Ad Soyad>`, `<Birleşen Ad Soyad>`, `<Kalan Ad Soyad>`,
`<Tür adı>`, `<N>` ve `<M>` yer tutucuları çalışma zamanında `fill` ile doldurulur, pencere kendi
cümlesini yazmaz. İngilizce ve Sırpça (Latin) karşılıklar PRD §20.6.3'ten **birebir** kopyadır
(`CONFIRMATION_TEXTS_EN`, `CONFIRMATION_TEXTS_SR`; gettext kataloğuna girmez, §D96): `first_text` ve
`second_text` isteğin dilindeki metni verir, yer tutucular her dilde aynıdır ve aynı değerle
dolar. `USER_CONFIRMED` olayı metin taşımaz, dilden bağımsızdır.

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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import ConfirmationToken, utcnow
from app.events import EventType, record_event
from app.i18n import N_, SOURCE_LANGUAGE, SUPPORTED_LANGUAGES, current_language
from app.web.auth import SESSION_COOKIE, PanelUser

CONFIRMATION_TTL = timedelta(minutes=10)  # §20.6.1 adım 2
# JSON API'de belirteç bu başlıkla gelir; panel formları `confirmation` alanını kullanır.
CONFIRMATION_HEADER = "X-Confirmation-Token"
# Kaynak dildeki (Türkçe) metin: JSON API'nin `detail`'i böyle kalır, panel `translate` ile çevirir.
CONFIRMATION_REFUSED = N_(
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
    REMOVE_PROFILE_RECORD = "remove_profile_record"  # profil alt kaydını kaldır, 10.5.8 (§D61)
    MERGE_EMPLOYEES = "merge_employees"  # iki çalışanı birleştir, 10.5.9 (§D61)
    UNARCHIVE = "unarchive"  # belgeyi arşivden geri al, 10.5.10 (§D61)
    CLOSE_QUEUE_ITEM = "close_queue_item"  # kuyruk öğesini kapat, 10.7.4 (§D61)
    # §20.6'nın dışında: yeniden analizin onayı (10.3.2, metinler PLAN.md §D23).
    REANALYZE = "reanalyze"
    # §20.6'nın dışında (K16 dışı, PLAN.md §D58): eğitim örneğini başka türe taşı ve örneklerden
    # çıkar (11.9.4); metinler `app.web.routers.training`'dedir.
    TRAINING_MOVE = "training_move"
    TRAINING_REMOVE = "training_remove"
    # §20.6'nın dışında (PLAN.md §D58): harita ile toplu taramayı başlat (11.9.5).
    TRAINING_MAP = "training_map"
    # §20.6'nın dışında (K16 dışı, PLAN.md §C92-a, §D61-d): belge türünü arşivle, tekil ve toplu
    # (11.1.6); metinler `app.web.routers.catalog`'dadır.
    TYPE_ARCHIVE = "type_archive"
    TYPE_ARCHIVE_BULK = "type_archive_bulk"


@dataclass(frozen=True, slots=True)
class ConfirmationTexts:
    first: str
    second: str


NAME_PLACEHOLDER = "<Ad Soyad>"
# 10.5.9: birleştirmede kapanan (`merged_name`) ve kalan (`kept_name`) kaydın adı.
MERGED_NAME_PLACEHOLDER = "<Birleşen Ad Soyad>"
KEPT_NAME_PLACEHOLDER = "<Kalan Ad Soyad>"
TYPE_PLACEHOLDER = "<Tür adı>"
# `<N>`: taramayı yoksaymada kuyruk öğesi sayısı (`queue_items`), profil düzenlemede yeniden
# adlandırılacak belge dosyası sayısı, birleştirmede taşınacak belge sayısı (`count`).
COUNT_PLACEHOLDER = "<N>"
DOCUMENT_COUNT_PLACEHOLDER = "<M>"

# §20.6 — Türkçe (kaynak dil) metinler BİREBİR, değiştirilmez; `tests/web/test_confirm.py` PRD
# tablosuyla karşılaştırır. İngilizce ve Sırpça karşılıklar aşağıda (§20.6.3).
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
    Operation.REMOVE_PROFILE_RECORD: ConfirmationTexts(
        "Bu kaydı çalışan profilinden kaldırmak üzeresiniz. Emin misiniz?",
        "Kayıt eşleştirmede ve aramada kullanılmayacak, geçmişte kalacaktır. Son kararınız mı?",
    ),
    Operation.MERGE_EMPLOYEES: ConfirmationTexts(
        "<Birleşen Ad Soyad> kaydını <Kalan Ad Soyad> kaydıyla birleştirmek üzeresiniz. Emin "
        "misiniz?",
        "<N> belge taşınacak ve birleşen kayıt kapanacaktır; bu işlem geri alınamaz. Son "
        "kararınız mı?",
    ),
    Operation.UNARCHIVE: ConfirmationTexts(
        "Bu belgeyi arşivden geri almak üzeresiniz. Emin misiniz?",
        "Belge çalışanın Hazır klasörüne dönecektir. Son kararınız mı?",
    ),
    Operation.CLOSE_QUEUE_ITEM: ConfirmationTexts(
        "Bu kuyruk öğesini kapatmak üzeresiniz. Emin misiniz?",
        "Öğe çözülmüş sayılacak, dosya kopyası ve gerekçesi yerinde kalacaktır. Son kararınız mı?",
    ),
}


# §20.6.3 — İngilizce (`en`) ve Sırpça (`sr`, Latin) metinler PRD'den BİREBİR kopyadır,
# değiştirilmez; `tests/web/test_confirm.py` PRD tablosuyla karşılaştırır. Yer tutucular Türkçe
# kaynaktaki gibi yazılır (`<Ad Soyad>`…) ve aynı değerle dolar; `Hazir` çalışanın fiziksel
# klasörünün adıdır.
CONFIRMATION_TEXTS_EN: dict[Operation, ConfirmationTexts] = {
    Operation.MOVE: ConfirmationTexts(
        "You are about to move this document to another employee. Are you sure?",
        "This action will change the document organization in the system. Is this your final "
        "decision?",
    ),
    Operation.ASSIGN: ConfirmationTexts(
        "You are about to assign this document to employee <Ad Soyad>. Are you sure?",
        "This action will change the document organization in the system. Is this your final "
        "decision?",
    ),
    Operation.APPROVE_PROFILE: ConfirmationTexts(
        "You are about to create a new employee profile for <Ad Soyad>. Are you sure?",
        "This action will create a permanent employee record in the system. Is this your final "
        "decision?",
    ),
    Operation.APPROVE_TYPE: ConfirmationTexts(
        "You are about to add the document type <Tür adı> to the standard types. Are you sure?",
        "This action will affect all future document analyses. Is this your final decision?",
    ),
    Operation.ARCHIVE: ConfirmationTexts(
        "You are about to move this document to the archive. Are you sure?",
        "The document will leave the employee's Hazir folder. Is this your final decision?",
    ),
    Operation.DISMISS: ConfirmationTexts(
        "You are about to dismiss this scan. Are you sure?",
        "The batch and its pending queue items (<N>) will be removed from the lists; generated "
        "documents (<M>) stay in place. Is this your final decision?",
    ),
    Operation.EDIT_EMPLOYEE: ConfirmationTexts(
        "You are about to change this employee's profile information. Are you sure?",
        "If the first or last name changed, the folder and the document files (<N>) will be "
        "renamed. Is this your final decision?",
    ),
    Operation.DEACTIVATE_EMPLOYEE: ConfirmationTexts(
        "You are about to deactivate employee <Ad Soyad>. Are you sure?",
        "New documents for this employee will not be placed automatically; they will go to the "
        "queue. Is this your final decision?",
    ),
    Operation.REACTIVATE_EMPLOYEE: ConfirmationTexts(
        "You are about to reactivate employee <Ad Soyad>. Are you sure?",
        "The employee will return to the list and new documents will again be placed "
        "automatically. Is this your final decision?",
    ),
    Operation.REMOVE_PROFILE_RECORD: ConfirmationTexts(
        "You are about to remove this record from the employee profile. Are you sure?",
        "The record will no longer be used for matching or search and will remain in the history. "
        "Is this your final decision?",
    ),
    Operation.MERGE_EMPLOYEES: ConfirmationTexts(
        "You are about to merge the record <Birleşen Ad Soyad> into the record <Kalan Ad Soyad>. "
        "Are you sure?",
        "The documents (<N>) will be moved and the merged record will be closed; this action "
        "cannot be undone. Is this your final decision?",
    ),
    Operation.UNARCHIVE: ConfirmationTexts(
        "You are about to restore this document from the archive. Are you sure?",
        "The document will return to the employee's Hazir folder. Is this your final decision?",
    ),
    Operation.CLOSE_QUEUE_ITEM: ConfirmationTexts(
        "You are about to close this queue item. Are you sure?",
        "The item will be considered resolved; its file copy and reason will stay in place. Is "
        "this your final decision?",
    ),
}

CONFIRMATION_TEXTS_SR: dict[Operation, ConfirmationTexts] = {
    Operation.MOVE: ConfirmationTexts(
        "Upravo ćete premestiti ovaj dokument drugom zaposlenom. Da li ste sigurni?",
        "Ova radnja će promeniti organizaciju dokumenata u sistemu. Da li je to vaša konačna "
        "odluka?",
    ),
    Operation.ASSIGN: ConfirmationTexts(
        "Upravo ćete dodeliti ovaj dokument zaposlenom <Ad Soyad>. Da li ste sigurni?",
        "Ova radnja će promeniti organizaciju dokumenata u sistemu. Da li je to vaša konačna "
        "odluka?",
    ),
    Operation.APPROVE_PROFILE: ConfirmationTexts(
        "Upravo ćete kreirati novi profil zaposlenog za <Ad Soyad>. Da li ste sigurni?",
        "Ova radnja će kreirati trajni zapis o zaposlenom u sistemu. Da li je to vaša konačna "
        "odluka?",
    ),
    Operation.APPROVE_TYPE: ConfirmationTexts(
        "Upravo ćete dodati tip dokumenta <Tür adı> među standardne tipove. Da li ste sigurni?",
        "Ova radnja će uticati na sve buduće analize dokumenata. Da li je to vaša konačna odluka?",
    ),
    Operation.ARCHIVE: ConfirmationTexts(
        "Upravo ćete premestiti ovaj dokument u arhivu. Da li ste sigurni?",
        "Dokument će biti uklonjen iz fascikle Hazir zaposlenog. Da li je to vaša konačna odluka?",
    ),
    Operation.DISMISS: ConfirmationTexts(
        "Upravo ćete zanemariti ovo skeniranje. Da li ste sigurni?",
        "Serija i njene stavke reda na čekanju (<N>) biće uklonjene sa spiskova; generisani "
        "dokumenti (<M>) ostaju na mestu. Da li je to vaša konačna odluka?",
    ),
    Operation.EDIT_EMPLOYEE: ConfirmationTexts(
        "Upravo ćete izmeniti podatke profila ovog zaposlenog. Da li ste sigurni?",
        "Ako je ime ili prezime promenjeno, fascikla i datoteke dokumenata (<N>) biće "
        "preimenovane. Da li je to vaša konačna odluka?",
    ),
    Operation.DEACTIVATE_EMPLOYEE: ConfirmationTexts(
        "Upravo ćete deaktivirati zaposlenog <Ad Soyad>. Da li ste sigurni?",
        "Novi dokumenti za ovog zaposlenog neće se automatski raspoređivati, već će ići u red. Da "
        "li je to vaša konačna odluka?",
    ),
    Operation.REACTIVATE_EMPLOYEE: ConfirmationTexts(
        "Upravo ćete ponovo aktivirati zaposlenog <Ad Soyad>. Da li ste sigurni?",
        "Zaposleni će se vratiti na spisak, a novi dokumenti će se ponovo automatski "
        "raspoređivati. Da li je to vaša konačna odluka?",
    ),
    Operation.REMOVE_PROFILE_RECORD: ConfirmationTexts(
        "Upravo ćete ukloniti ovaj zapis iz profila zaposlenog. Da li ste sigurni?",
        "Zapis se više neće koristiti za uparivanje i pretragu i ostaće u istoriji. Da li je to "
        "vaša konačna odluka?",
    ),
    Operation.MERGE_EMPLOYEES: ConfirmationTexts(
        "Upravo ćete spojiti zapis <Birleşen Ad Soyad> sa zapisom <Kalan Ad Soyad>. Da li ste "
        "sigurni?",
        "Dokumenti (<N>) biće premešteni, a spojeni zapis biće zatvoren; ova radnja se ne može "
        "poništiti. Da li je to vaša konačna odluka?",
    ),
    Operation.UNARCHIVE: ConfirmationTexts(
        "Upravo ćete vratiti ovaj dokument iz arhive. Da li ste sigurni?",
        "Dokument će se vratiti u fasciklu Hazir zaposlenog. Da li je to vaša konačna odluka?",
    ),
    Operation.CLOSE_QUEUE_ITEM: ConfirmationTexts(
        "Upravo ćete zatvoriti ovu stavku reda. Da li ste sigurni?",
        "Stavka će se smatrati rešenom; kopija datoteke i obrazloženje ostaju na mestu. Da li je "
        "to vaša konačna odluka?",
    ),
}

# Dil kodu → onay metinleri (`SUPPORTED_LANGUAGES` ile aynı küme): Türkçe kaynaktır.
CONFIRMATION_TEXTS_BY_LANGUAGE: Mapping[str, Mapping[Operation, ConfirmationTexts]] = (
    MappingProxyType(
        {
            SOURCE_LANGUAGE: CONFIRMATION_TEXTS,
            "en": CONFIRMATION_TEXTS_EN,
            "sr": CONFIRMATION_TEXTS_SR,
        }
    )
)


def confirmation_texts(operation: Operation, language: str | None = None) -> ConfirmationTexts:
    """`operation`'ın iki onay metni (yer tutucular henüz dolmamış): `language` dilinde, verilmezse
    isteğin dilinde. Yalnız §20.6'nın 13 işlemi vardır; başka işlem `KeyError`'dır."""
    code = current_language() if language is None else language
    if code not in SUPPORTED_LANGUAGES:
        raise ValueError(f"desteklenmeyen dil: {code!r}")
    return CONFIRMATION_TEXTS_BY_LANGUAGE[code][operation]


def fill(
    text: str,
    *,
    name: str | None = None,
    merged_name: str | None = None,
    kept_name: str | None = None,
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
        (MERGED_NAME_PLACEHOLDER, merged_name),
        (KEPT_NAME_PLACEHOLDER, kept_name),
        (TYPE_PLACEHOLDER, type_name),
        (COUNT_PLACEHOLDER, None if number is None else str(number)),
        (DOCUMENT_COUNT_PLACEHOLDER, None if documents is None else str(documents)),
    ):
        if placeholder in text:
            if value is None:
                raise ValueError(f"Onay metninin {placeholder} yer tutucusu doldurulmadı")
            text = text.replace(placeholder, value)
    return text


def first_text(operation: Operation, *, language: str | None = None, **values: Any) -> str:
    """Birinci onay metni, yer tutucuları doldurulmuş: `language` dilinde, verilmezse isteğin
    dilinde (istek dışında `en`; makine arayüzü olan JSON API kaynak dili ister)."""
    return fill(confirmation_texts(operation, language).first, **values)


def second_text(operation: Operation, *, language: str | None = None, **values: Any) -> str:
    """İkinci onay metni; `first_text` ile aynı dil kuralı."""
    return fill(confirmation_texts(operation, language).second, **values)


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
