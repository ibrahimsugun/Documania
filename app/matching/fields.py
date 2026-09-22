"""Profil alanlarını belgelerden tamamlama — PRD 05.7.3 (PLAN.md §C82; §8.3
`EMPLOYEE_FIELD_FILLED`).

Eşleşen (§20.2.2 satır 1/3) ya da yeni açılan (satır 6) çalışanın profil alanları belgenin kişi
anahtarıyla (`PersonKey`, 05.4.1) karşılaştırılır: ad, soyad, diğer isimler, orijinal yazım, doğum
tarihi ve uyruk (`ProfileField`). Belge numarası (05.7.2) ve iletişim bilgisi (05.8.1) kendi birikim
yollarındadır.

**Değer.** Belgenin değeri yeni çalışan kaydına yazılan değerle aynıdır
(`PersonKey.employee_fields()`): ad, soyad ve diğer isimler Latin yazımdır (05.2.2, §C81), Latin
yazımı olmayan parça yazılmaz; orijinal yazım Latin olmayan yazımdır. Anahtar yalnız okunaklı
değeri taşır — `fields` okuması `legible: false` diyen sayfanın değeri anahtara girmez (K1) — ve
MRZ'si okunmuş sayfanın değeri görünen metinden önce gelir (K6, 05.3.3). Adayın sayfaları bir alanı
farklı okuyorsa (çelişki) alanın değeri yoktur.

**Kural.** Değeri olan her alan için:

- alan boşsa (`None` ya da boş metin) belgedeki değerle doldurulur → `filled`;
- alan doluysa **hiçbir durumda değiştirilmez**: değerler aynıysa `same`, farklıysa `conflict`.
  İsim alanlarında aynılık §20.2.1 normalizasyonudur (`normalize_name`: harf çevirisi, aksan,
  büyük/küçük harf, noktalama, kelime sırası); doğum tarihinde takvim günü, uyrukta ICAO kodu.
  `conflict` profil kartında "<alan>: belgede farklı değer okundu" uyarısıdır (10.5.1).

Yeni açılan çalışanın alanlarını `create_employee` aynı anahtardan yazmıştır; `created` çağrısı
bunları `filled` kaydeder.

**Kaynak.** Her karşılaştırma `employee_field_observations`'a yazılır: çalışan, alan, kaynak ve
sonuç — değer yazılmaz (CONVENTIONS §6). Kaynak belgenin ilk sayfasıdır (`file_id`,
`page_index`; planın adayı, çıktının `source_refs_json`'unun ilk sayfası). Bir alan aynı kaynaktan
bir kez gözlenir: aynı kaynak yeniden işlenirse (yeniden analiz, geçmiş veri komutu) o alan
atlanır — alan zaten o kaynaktan doldu ya da karşılaştırıldı. Doldurulan her alan için
`EMPLOYEE_FIELD_FILLED` olayı yazılır: veri `field`, `source: document`, `rule: 05.7.3`; kaynak
olayın `file_id`/`page_index`/`document_id` sütunlarıdır, değer yazılmaz.

Profilden yüklemede kişi denetimi (10.5.5) `different` dediği belgede bu adım çağrılmaz; o karar
çağıranındır. Oturum commit edilmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Employee, EmployeeFieldObservation, FieldOutcome, ProfileField
from app.events import EventType, record_event
from app.matching.match import PersonKey
from app.matching.names import EmptyNameError, normalize_name

FILL_RULE = "05.7.3"
FILL_SOURCE = "document"
_NAME_FIELDS = (
    ProfileField.GIVEN_NAMES,
    ProfileField.SURNAME,
    ProfileField.OTHER_NAMES,
    ProfileField.ORIGINAL_SCRIPT_NAME,
)


@dataclass(frozen=True, slots=True)
class FieldCompletion:
    """Bir belgenin profil alanlarıyla karşılaştırması (05.7.3): sonuç başına alan adları,
    `ProfileField` sırasıyla. Kaynaktan daha önce gözlenmiş alan hiçbirinde yoktur. Kişisel değer
    taşımaz."""

    employee_id: str
    filled: tuple[str, ...] = ()
    same: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


def document_field_values(key: PersonKey) -> dict[ProfileField, str | date]:
    """Anahtarın profil alanı değerleri (`PersonKey.employee_fields()`), `ProfileField` sırasıyla;
    değeri olmayan alan yoktur."""
    values = key.employee_fields()
    return {field: value for field in ProfileField if (value := values[field.value]) is not None}


def complete_profile_fields(
    session: Session,
    key: PersonKey,
    *,
    employee_id: str,
    file_id: int,
    page_index: int,
    document_id: int | None = None,
    actor: str = "system",
    created: bool = False,
) -> FieldCompletion:
    """Belgenin kişi anahtarıyla çalışanın boş profil alanlarını doldurur, dolu alanları
    karşılaştırır (05.7.3); kurallar modül açıklamasındadır.

    `file_id`/`page_index` kaynak belgenin ilk sayfasıdır; `document_id` çıktı belgesi varsa
    (geçmiş veri) olaya yazılır. `created`: çalışan bu anahtardan az önce açıldı (satır 6) —
    alanları `create_employee` yazdı, `filled` kaydedilir. Olaylar `actor` adıyla yazılır; olayın
    parti bağlamı verilmezse etkin `event_context`ten alınır. Oturum commit edilmez.
    """
    employee = session.get_one(Employee, employee_id)
    observed = set(
        session.scalars(
            select(EmployeeFieldObservation.field).where(
                EmployeeFieldObservation.employee_id == employee_id,
                EmployeeFieldObservation.file_id == file_id,
                EmployeeFieldObservation.page_index == page_index,
            )
        )
    )
    outcomes: dict[FieldOutcome, list[str]] = {outcome: [] for outcome in FieldOutcome}
    for field, value in document_field_values(key).items():
        if field.value in observed:
            continue
        current = getattr(employee, field.value)
        if _is_empty(current):
            setattr(employee, field.value, value)
            outcome = FieldOutcome.FILLED
        elif _same(field, current, value):
            outcome = FieldOutcome.FILLED if created else FieldOutcome.SAME
        else:
            outcome = FieldOutcome.CONFLICT
        session.add(
            EmployeeFieldObservation(
                employee_id=employee_id,
                field=field.value,
                outcome=outcome.value,
                file_id=file_id,
                page_index=page_index,
            )
        )
        outcomes[outcome].append(field.value)
    for field_name in outcomes[FieldOutcome.FILLED]:
        record_event(
            session,
            EventType.EMPLOYEE_FIELD_FILLED,
            file_id=file_id,
            page_index=page_index,
            document_id=document_id,
            employee_id=employee_id,
            actor=actor,
            data={"field": field_name, "source": FILL_SOURCE, "rule": FILL_RULE},
        )
    session.flush()
    return FieldCompletion(
        employee_id,
        filled=tuple(outcomes[FieldOutcome.FILLED]),
        same=tuple(outcomes[FieldOutcome.SAME]),
        conflicts=tuple(outcomes[FieldOutcome.CONFLICT]),
    )


def _is_empty(value: str | date | None) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _same(field: ProfileField, current: str | date, value: str | date) -> bool:
    # Dolu alanla belgenin değeri aynı kişi bilgisi mi (§20.2.1; modül açıklaması).
    if field in _NAME_FIELDS:
        return _name_key(str(current)) == _name_key(str(value))
    if field is ProfileField.NATIONALITY:
        return str(current).strip().upper() == str(value).strip().upper()
    return current == value


def _name_key(text: str) -> str | None:
    try:
        return normalize_name(text)
    except EmptyNameError:
        return None
