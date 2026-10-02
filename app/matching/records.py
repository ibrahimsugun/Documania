"""Profil alt kayıtları — PRD 10.5.8 (PLAN.md §C90-c, §D61, §D68; K16, R11, K6, 05.7.2, 05.8.2).

Çalışanın üç alt kaydı vardır: belgelerde görülen isim yazımları (`employee_aliases`), belge
numaraları (`employee_identifiers`) ve iletişim bilgileri (`employee_contacts`). İK bunları profil
sayfasında görür ve yanlış olanı **kaldırır**: satır silinmez (R11), `removed_at` (UTC) ve
`removed_by` (kullanıcı adı) dolar. Kaldırılmış kayıt

- eşleştirmeye girmez (K6): belge numarası (§20.2.2 satır 1–2, `number_owners`) ve isim + doğum
  tarihi (satır 3–5, `ACTIVE_ALIAS`) yalnız etkin kayıtlarla karar verir; profilden yüklemenin kişi
  denetimi (10.5.5, `app.matching.context`) de öyle,
- çalışan aramasında (10.4.2), botun kişi aramasında, profil kartında ve `profil.md`'de görünmez,
- belgeden yeniden gelirse **geri açılmaz ve yeni satır açılmaz** (`accumulate_identity`,
  `record_contact_sighting`): yalnız `seen_after_removal_at` dolar ve profil "Belgede görülen <tür>
  kaldırılmış bir kayda uyuyor" uyarısını gösterir (değer profilde zaten görünür, olaya yazılmaz).

Kaldırma iki aşamalıdır (K16, §20.6 "Profil alt kaydını kaldır"; belirteç hedefi `kind:rid`),
geri alma tek adımdır (§D61-b: salt geri alma). İletişim bilgisi (telefon, e-posta, adres) elle
eklenir (`add_contact`, tek adım): yeni satır güncel olur, aynı türün öteki satırları güncel
olmaktan çıkar (05.8.2), `source_document_id` boş, `added_by` ekleyendir. İsim yazımı ve belge
numarası elle eklenmez — belgeden gelir (K7 ruhu); iletişim değeri düzenlenmez (kaldır + ekle).

Olaylar `PROFILE_RECORD_REMOVED`, `PROFILE_RECORD_RESTORED` (`kind`, `record_id`) ve
`CONTACT_ADDED` (`kind` — iletişimin türü —, `record_id`) kullanıcı adıyla yazılır; kaydın değeri
olaya girmez (D51/D52, CONVENTIONS §6).
Birleştirilmiş (`merged`, 10.5.9) çalışanın kayıtları buradan değişmez. Oturum commit edilmez.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from app.db.models import (
    ContactKind,
    Employee,
    EmployeeAlias,
    EmployeeContact,
    EmployeeIdentifier,
    EmployeeStatus,
    Event,
    utcnow,
)
from app.events import EventType, record_event
from app.i18n import N_, Translatable


class RecordKind(enum.StrEnum):
    """Profil alt kaydının türü: yoldaki `{kind}` ve olay verisindeki `kind`."""

    ALIAS = "alias"
    IDENTIFIER = "identifier"
    CONTACT = "contact"


type ProfileRecord = EmployeeAlias | EmployeeIdentifier | EmployeeContact

RECORD_MODELS: dict[RecordKind, type[EmployeeAlias | EmployeeIdentifier | EmployeeContact]] = {
    RecordKind.ALIAS: EmployeeAlias,
    RecordKind.IDENTIFIER: EmployeeIdentifier,
    RecordKind.CONTACT: EmployeeContact,
}

# Etkin (kaldırılmamış) kayıt süzgeçleri: eşleştirme, arama, profil kartı ve `profil.md` bunları
# kullanır. Kaldırılmış kaydı sayan tek yer birikimdir (aynı değer geri açılmasın).
ACTIVE_ALIAS: ColumnElement[bool] = EmployeeAlias.removed_at.is_(None)
ACTIVE_IDENTIFIER: ColumnElement[bool] = EmployeeIdentifier.removed_at.is_(None)
ACTIVE_CONTACT: ColumnElement[bool] = EmployeeContact.removed_at.is_(None)

# Uyarı ve onay sayfasındaki tür adları ("Belgede görülen <tür> …").
KIND_LABELS = {
    RecordKind.ALIAS: N_("isim yazımı"),
    RecordKind.IDENTIFIER: N_("belge numarası"),
}
CONTACT_KIND_LABELS = {
    ContactKind.PHONE.value: N_("telefon"),
    ContactKind.EMAIL.value: N_("e-posta"),
    ContactKind.ADDRESS.value: N_("adres"),
}
SEEN_AFTER_REMOVAL_WARNING = N_("Belgede görülen {label} kaldırılmış bir kayda uyuyor")

CONTACT_VALUE_MAX_LENGTH = 500
# Biçim denetimi hafiftir (§C90-c): yazım hatasını yakalar, geçerliliği kanıtlamaz.
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_PHONE = re.compile(r"\+?[0-9 ()./-]+")
PHONE_DIGITS = (5, 20)


class ProfileRecordError(ValueError):
    """Alt kayıt işlemi yapılmadı; hiçbir şey yazılmadı. Mesaj kişisel değer taşımaz."""


class ProfileRecordStateError(ProfileRecordError):
    """Kayıt zaten istenen durumda (kaldırılmış kayıt yeniden kaldırılmaz, etkin kayıt geri
    alınmaz) ya da çalışan birleştirilmiş."""


class ContactFormError(ProfileRecordError):
    """Elle eklenen iletişim bilgisi kurala uymuyor; `problems` alan adına göre iletilerdir."""

    def __init__(self, problems: dict[str, list[str]]) -> None:
        super().__init__(
            "; ".join(message for messages in problems.values() for message in messages)
        )
        self.problems = problems


@dataclass(frozen=True, slots=True)
class EmployeeRecords:
    """Çalışanın bütün alt kayıtları (etkin ve kaldırılmış), eklenme sırasıyla."""

    aliases: Sequence[EmployeeAlias] = ()
    identifiers: Sequence[EmployeeIdentifier] = ()
    contacts: Sequence[EmployeeContact] = ()
    removed: list[tuple[RecordKind, ProfileRecord]] = field(default_factory=list)


def record_kind(value: str) -> RecordKind | None:
    """Yoldaki `{kind}`; tanınmayan değer `None`."""
    return next((kind for kind in RecordKind if kind.value == value), None)


def record_label(kind: RecordKind, record: ProfileRecord) -> str:
    """Kaydın tür adı: "isim yazımı", "belge numarası", "telefon", "e-posta", "adres"."""
    if isinstance(record, EmployeeContact):
        return CONTACT_KIND_LABELS.get(record.kind, record.kind)
    return KIND_LABELS[kind]


def record_value(record: ProfileRecord) -> str:
    return record.raw_name if isinstance(record, EmployeeAlias) else record.value


def seen_after_removal_warning(kind: RecordKind, record: ProfileRecord) -> str | None:
    """Kaldırılmış kayıt belgede yeniden görüldüyse profil uyarısı; değilse `None`."""
    if record.removed_at is None or record.seen_after_removal_at is None:
        return None
    return SEEN_AFTER_REMOVAL_WARNING.format(label=record_label(kind, record))


# --- sorgular: kaldırılmış kaydı saymayan tek yer ------------------------------------------------


def number_owners(session: Session, numbers: Iterable[str]) -> set[str]:
    """Bu numaralardan birini **etkin** kaydında taşıyan çalışanlar (§20.2.2 satır 1–2).

    "Aynı numara birden fazla çalışana ait" hükmü kaldırılmış satırı saymaz: numarayı bir
    çalışandan kaldırmak onu öteki çalışanın tek sahipliğine bırakır. Birleştirilmiş (`merged`,
    10.5.9) çalışan sahip sayılmaz: numaraları kalan kayda taşınmıştır, süzgeç güvenlik içindir.
    """
    values = list(dict.fromkeys(numbers))
    if not values:
        return set()
    return set(
        session.scalars(
            select(EmployeeIdentifier.employee_id)
            .join(Employee, Employee.id == EmployeeIdentifier.employee_id)
            .where(
                EmployeeIdentifier.value.in_(values),
                ACTIVE_IDENTIFIER,
                Employee.status != EmployeeStatus.MERGED.value,
            )
        )
    )


def active_numbers(session: Session, employee_id: str) -> frozenset[str]:
    """Çalışanın etkin belge numaraları."""
    return frozenset(
        session.scalars(
            select(EmployeeIdentifier.value).where(
                EmployeeIdentifier.employee_id == employee_id, ACTIVE_IDENTIFIER
            )
        )
    )


def active_alias_keys(session: Session, employee_id: str) -> list[str]:
    """Çalışanın etkin isim yazımlarının normalize anahtarları, eklenme sırasıyla."""
    return list(
        session.scalars(
            select(EmployeeAlias.normalized_name)
            .where(EmployeeAlias.employee_id == employee_id, ACTIVE_ALIAS)
            .order_by(EmployeeAlias.id)
        )
    )


def employee_records(session: Session, employee_id: str) -> EmployeeRecords:
    """Profil sayfasının alt kayıt bölümü için çalışanın bütün kayıtları; `removed` kaldırılanlar,
    en son kaldırılan önce."""

    def rows[R: (EmployeeAlias, EmployeeIdentifier, EmployeeContact)](model: type[R]) -> list[R]:
        return list(
            session.scalars(
                select(model).where(model.employee_id == employee_id).order_by(model.id)
            )
        )

    aliases = rows(EmployeeAlias)
    identifiers = rows(EmployeeIdentifier)
    contacts = rows(EmployeeContact)
    removed: list[tuple[RecordKind, ProfileRecord]] = [
        (kind, record)
        for kind, records in (
            (RecordKind.ALIAS, aliases),
            (RecordKind.IDENTIFIER, identifiers),
            (RecordKind.CONTACT, contacts),
        )
        for record in records
        if record.removed_at is not None
    ]
    removed.sort(key=lambda pair: _removed_order(pair[1]), reverse=True)
    return EmployeeRecords(aliases, identifiers, contacts, removed)


def _removed_order(record: ProfileRecord) -> tuple[datetime, int]:
    assert record.removed_at is not None
    return (record.removed_at, record.id)


def find_record(
    session: Session, employee_id: str, kind: RecordKind, record_id: int
) -> ProfileRecord | None:
    """Çalışanın `kind` türündeki `record_id` kaydı; başka çalışanınsa ya da yoksa `None`."""
    model = RECORD_MODELS[kind]
    record = session.get(model, record_id)
    if record is None or record.employee_id != employee_id:
        return None
    return record


def note_seen_after_removal(records: Iterable[ProfileRecord]) -> None:
    """Belgede yeniden görülen kaldırılmış kayıtları işaretler (satır geri açılmaz, yeni satır
    açılmaz); profil uyarısı buradan gelir. Olay yazılmaz."""
    now = utcnow()
    for record in records:
        if record.removed_at is not None:
            record.seen_after_removal_at = now


# --- İK işlemleri ------------------------------------------------------------------------------


def _check_employee(employee: Employee, actor: str) -> None:
    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")
    if employee.status == EmployeeStatus.MERGED.value:
        raise ProfileRecordStateError(
            f"Çalışan {employee.id} birleştirilmiş; kayıtları kalan kayıtta yönetilir (10.5.9)"
        )


def remove_record(
    session: Session, employee: Employee, kind: RecordKind, record: ProfileRecord, *, actor: str
) -> Event:
    """10.5.8 — kaydı kaldırır (iki aşamalı onaydan sonra): `removed_at`/`removed_by` dolar,
    satır silinmez; `PROFILE_RECORD_REMOVED` kullanıcı adıyla yazılır. Kaldırılmış kayıt
    `ProfileRecordStateError`."""
    _check_employee(employee, actor)
    if record.removed_at is not None:
        raise ProfileRecordStateError(f"Kayıt {kind.value}:{record.id} zaten kaldırılmış")
    record.removed_at = utcnow()
    record.removed_by = actor
    record.seen_after_removal_at = None
    return _record_event(
        session, EventType.PROFILE_RECORD_REMOVED, employee, kind.value, record.id, actor
    )


def restore_record(
    session: Session, employee: Employee, kind: RecordKind, record: ProfileRecord, *, actor: str
) -> Event:
    """10.5.8 — kaldırılmış kaydı geri alır (tek adım): kayıt yeniden eşleştirmeye ve aramaya
    girer; `PROFILE_RECORD_RESTORED` kullanıcı adıyla yazılır. Etkin kayıt
    `ProfileRecordStateError`.

    Geri alınan iletişim bilgisi ancak kaldırıldığı sırada güncelse ve o türde sonradan yeni değer
    gelmediyse güncel olur (yeni değer türün öteki satırlarını güncel olmaktan çıkarır)."""
    _check_employee(employee, actor)
    if record.removed_at is None:
        raise ProfileRecordStateError(f"Kayıt {kind.value}:{record.id} kaldırılmamış")
    record.removed_at = None
    record.removed_by = None
    record.seen_after_removal_at = None
    return _record_event(
        session, EventType.PROFILE_RECORD_RESTORED, employee, kind.value, record.id, actor
    )


def normalized_contact(kind: str, value: str | None) -> str:
    """Elle girilen iletişim bilgisinin denetimi (§C90-c): tür `phone|email|address`, değer boş
    değil, en çok 500 karakter, e-posta ve telefon hafif biçim denetiminden geçer. Boşluklar
    sadeleşir. Uymazsa `ContactFormError`."""
    problems: dict[str, list[str]] = {}
    if kind not in CONTACT_KIND_LABELS:
        problems["kind"] = [N_("Tür telefon, e-posta ya da adres olmalı.")]
    text = " ".join((value or "").split())
    if not text:
        problems["value"] = [N_("Değer boş olamaz.")]
    elif len(text) > CONTACT_VALUE_MAX_LENGTH:
        problems["value"] = [
            Translatable(
                N_("Değer en çok {limit} karakter olabilir."), limit=CONTACT_VALUE_MAX_LENGTH
            )
        ]
    elif kind == ContactKind.EMAIL.value and not _EMAIL.fullmatch(text):
        problems["value"] = [N_("E-posta adresi ad@alan.uzantı biçiminde olmalı.")]
    elif kind == ContactKind.PHONE.value and not _valid_phone(text):
        low, high = PHONE_DIGITS
        problems["value"] = [
            Translatable(
                N_(
                    "Telefon rakam, boşluk, +, -, nokta ve parantezden oluşmalı; "
                    "{low}–{high} rakam."
                ),
                low=low,
                high=high,
            )
        ]
    if problems:
        raise ContactFormError(problems)
    return text


def _valid_phone(text: str) -> bool:
    low, high = PHONE_DIGITS
    return bool(_PHONE.fullmatch(text)) and low <= sum(char.isdigit() for char in text) <= high


def add_contact(
    session: Session, employee: Employee, kind: str, value: str | None, *, actor: str
) -> EmployeeContact:
    """10.5.8 — İK'nın elle eklediği iletişim bilgisi (tek adım, 05.8.2 kuralı): yeni satır güncel,
    aynı türün öteki satırları (kaldırılmışlar dahil) güncel olmaktan çıkar; `source_document_id`
    boş, `added_by` ekleyen. `CONTACT_ADDED` (`kind`, `record_id`) kullanıcı adıyla yazılır.

    Değer türün güncel kaydıyla aynıysa ya da kaldırılmış bir kayıtla aynıysa (geri alınmalı)
    `ContactFormError`; hiçbir şey yazılmaz."""
    _check_employee(employee, actor)
    text = normalized_contact(kind, value)
    rows = session.scalars(
        select(EmployeeContact)
        .where(EmployeeContact.employee_id == employee.id, EmployeeContact.kind == kind)
        .order_by(EmployeeContact.id)
    ).all()
    if any(row.value == text and row.is_current and row.removed_at is None for row in rows):
        raise ContactFormError({"value": [N_("Bu değer zaten güncel kayıt.")]})
    if any(row.value == text and row.removed_at is not None for row in rows):
        raise ContactFormError(
            {"value": [N_("Bu değer kaldırılanlar arasında; eklemek yerine “Geri al”ı kullanın.")]}
        )
    for row in rows:
        if row.is_current:
            row.is_current = False
    now = utcnow()
    contact = EmployeeContact(
        employee_id=employee.id,
        kind=kind,
        value=text,
        source_document_id=None,
        first_seen_at=now,
        last_seen_at=now,
        is_current=True,
        added_by=actor,
    )
    session.add(contact)
    session.flush()
    # `kind` burada iletişimin türüdür (telefon, e-posta, adres).
    _record_event(session, EventType.CONTACT_ADDED, employee, kind, contact.id, actor)
    return contact


def _record_event(
    session: Session,
    event_type: EventType,
    employee: Employee,
    kind: str,
    record_id: int,
    actor: str,
) -> Event:
    # Değer olaya girmez (CONVENTIONS §6): tür ve kimlik yeter.
    return record_event(
        session,
        event_type,
        employee_id=employee.id,
        actor=actor,
        data={"kind": kind, "record_id": record_id},
    )
