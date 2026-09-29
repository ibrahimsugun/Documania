"""Çalışan profilini düzenleme — PRD 10.5.6 (PLAN.md §C90-a, §D61; K8, K16, K17).

İK profil sayfasından ad, soyad, diğer isimler, orijinal yazım, doğum tarihi ve uyruğu değiştirir.
Değerler onaylanan profilin kuralıyla denetlenir (`check_profile_fields`, 10.7.3): ad ve soyad
zorunlu, yalnız Latin harfli (05.2.2) ve klasör adına çevrilebilir (00.4.2); doğum tarihi gelecekte
olamaz, uyruk ICAO kodudur. Yalnız çalışan kaydı değişir — belge içeriği, sayfa okumaları ve köken
kaydı değişmez (K11, K17, R12).

`update_employee_fields` iki aşamalı onaydan (K16, §20.6) sonra çağrılır ve tek işlemde:

- değişen alanları çalışana yazar; her değişen alan için `employee_field_observations`'a
  `source=manual`, `actor` satırı ekler (değer yok). 05.7.3 dolgusu dolu alanı zaten ezmez
  (`app.matching.fields`): elle girilen değer sonraki belgelerle değişmez, farklı okuyan belge
  profilde uyarı olur;
- ad-soyad ya da orijinal yazım değiştiyse yeni yazımı `employee_aliases`'a ekler (onaylanan
  profildeki gibi, `_employee_aliases`): isim eşleştirmesi (§20.2.2 satır 3–5) yeni yazımla da
  bulur, eski yazımlar kalır;
- ad ya da soyad klasör adını değiştiriyorsa klasörü ve `Hazir/`'daki etkin belge dosyalarını K8
  adına yeniden adlandırır (`app.storage.rename`); E numarası ve çalışanın kimliği değişmez;
- `EMPLOYEE_EDITED` olayını kullanıcı adıyla yazar: `fields` (değişen alan adları), `renamed`
  (klasör yeniden adlandırıldı mı), `documents` (dosyası yeniden adlandırılan belge kimlikleri) —
  değer yazılmaz (PRD §8.3, D51).

Satırlar önce yazılıp `flush` edilir, dosyalar en son taşınır; taşıma yarıda kalırsa dosyalar geri
alınır ve `EmployeeRenameError` yükselir — çağıran oturumu geri alır, hiçbir şey değişmemiş olur.
`profil.md` commit'ten sonra çağıranca yeniden üretilir (09.1.1, `app.profiles.write_profile`).
Birleştirilmiş (`merged`) çalışan düzenlenmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Employee,
    EmployeeAlias,
    EmployeeFieldObservation,
    Event,
    FieldOutcome,
    FieldSource,
)
from app.events import EventType, record_event
from app.matching.match import (
    GIVEN_NAMES,
    ORIGINAL_SCRIPT_NAME,
    PROFILE_FIELDS,
    SURNAME,
    ProfileFields,
    ProfileFieldsError,
    check_profile_fields,
)
from app.matching.names import detect_script, normalize_name
from app.storage import (
    DataLayout,
    EmployeeRenamePlan,
    plan_employee_rename,
    rename_employee_folder,
)

# Birleştirilen çalışanın durumu (10.5.9, tm 129): kaydı kapanır, düzenlenmez.
MERGED_STATUS = "merged"


class EmployeeEditRefusedError(ValueError):
    """Düzenleme yapılmaz; hiçbir şey yazılmadı. Mesaj kişisel değer taşımaz."""


class EmployeeNotEditableError(EmployeeEditRefusedError):
    """Çalışan birleştirilmiş; kalan kayıt düzenlenir."""


class NoFieldChangesError(EmployeeEditRefusedError):
    """Formdaki değerler çalışanın kaydıyla aynı; değişecek alan yok."""


@dataclass(frozen=True, slots=True)
class EditPreview:
    """Onaydan önce düzenlemenin sonucu (ikinci onay metninin `<N>`'i): değişen alan adları
    (`PROFILE_FIELDS` sırasıyla), klasörün yeniden adlandırılıp adlandırılmayacağı ve dosyası
    yeniden adlandırılacak belge sayısı. Kişisel değer taşımaz."""

    changed: tuple[str, ...]
    renamed: bool
    documents: int


@dataclass(frozen=True, slots=True)
class EditedEmployee:
    """`update_employee_fields` sonucu: çalışan, değişen alanlar, klasörün yeniden adlandırılıp
    adlandırılmadığı, dosyası yeniden adlandırılan belgeler ve `EMPLOYEE_EDITED` olayı."""

    employee: Employee
    changed: tuple[str, ...]
    renamed: bool
    documents: tuple[int, ...]
    event: Event


def current_profile_fields(employee: Employee) -> ProfileFields:
    """Çalışan kaydının düzenlenebilir alanları; boş metin `None`'dır."""
    return ProfileFields(
        given_names=employee.given_names,
        surname=employee.surname,
        other_names=_text(employee.other_names),
        original_script_name=_text(employee.original_script_name),
        date_of_birth=employee.date_of_birth,
        nationality=_text(employee.nationality),
    )


def changed_fields(employee: Employee, fields: ProfileFields) -> tuple[str, ...]:
    """Kayıttan farklı alanların adları (`PROFILE_FIELDS` sırasıyla); karşılaştırma birebirdir."""
    current, wanted = current_profile_fields(employee).values(), fields.values()
    return tuple(name for name in PROFILE_FIELDS if current[name] != wanted[name])


def preview_employee_edit(
    session: Session,
    layout: DataLayout,
    employee: Employee,
    fields: ProfileFields,
    *,
    today: date | None = None,
) -> EditPreview:
    """Düzenlemenin denetimi ve sonucu; hiçbir şey yazmaz.

    Birleştirilmiş çalışan `EmployeeNotEditableError`, geçersiz alan `ProfileFieldsError`,
    değişiklik yoksa `NoFieldChangesError`.
    """
    changed, plan = _checked(session, layout, employee, fields, today=today)
    return EditPreview(
        changed=changed,
        renamed=plan is not None,
        documents=0 if plan is None else len(plan.files),
    )


def update_employee_fields(
    session: Session,
    layout: DataLayout,
    employee: Employee,
    changes: ProfileFields,
    *,
    actor: str,
    today: date | None = None,
) -> EditedEmployee:
    """10.5.6 — `changes`'ın kayıttan farklı alanlarını çalışana uygular; kurallar modül
    açıklamasındadır.

    `actor` iki aşamalı onayı (K16, §20.6.1) tamamlamış kullanıcının adıdır; boşsa `ValueError`.
    Denetim hataları `preview_employee_edit`'inkilerdir; dosya taşıması yarıda kalırsa
    `EmployeeRenameError` (dosyalar geri alındı, oturumu geri almak çağıranın). Oturum commit
    edilmez.
    """
    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")
    changed, plan = _checked(session, layout, employee, changes, today=today)
    aliases = _new_aliases(session, employee, changes, changed)

    for name in changed:
        # `ProfileFields` alan adları `employees` sütun adlarıdır.
        setattr(employee, name, getattr(changes, name))
        session.add(
            EmployeeFieldObservation(
                employee_id=employee.id,
                field=name,
                outcome=FieldOutcome.FILLED.value,
                source=FieldSource.MANUAL.value,
                actor=actor,
            )
        )
    for raw_name, normalized in aliases.items():
        session.add(
            EmployeeAlias(
                employee_id=employee.id,
                raw_name=raw_name,
                normalized_name=normalized,
                script=detect_script(raw_name),
            )
        )
    documents = () if plan is None else plan.renamed_document_ids
    event = record_event(
        session,
        EventType.EMPLOYEE_EDITED,
        employee_id=employee.id,
        actor=actor,
        data={"fields": list(changed), "renamed": plan is not None, "documents": list(documents)},
    )
    session.flush()
    if plan is not None:
        rename_employee_folder(session, layout, employee, plan)
    return EditedEmployee(employee, changed, plan is not None, documents, event)


def _checked(
    session: Session,
    layout: DataLayout,
    employee: Employee,
    fields: ProfileFields,
    *,
    today: date | None,
) -> tuple[tuple[str, ...], EmployeeRenamePlan | None]:
    if employee.status == MERGED_STATUS:
        raise EmployeeNotEditableError(
            f"Çalışan {employee.id} birleştirilmiş; profili düzenlenmez (10.5.9)"
        )
    errors = check_profile_fields(fields, today=today)
    if errors:
        raise ProfileFieldsError(errors)
    changed = changed_fields(employee, fields)
    if not changed:
        raise NoFieldChangesError(f"Çalışan {employee.id}: hiçbir alan değişmedi")
    plan = plan_employee_rename(
        session, layout, employee, given_names=fields.given_names, surname=fields.surname
    )
    return changed, plan


def _new_aliases(
    session: Session, employee: Employee, fields: ProfileFields, changed: tuple[str, ...]
) -> dict[str, str]:
    # Değişen ad-soyad ve orijinal yazım (ham → normalize anahtar, §20.2.1); çalışanda aynı ham
    # yazım varsa eklenmez.
    known = set(
        session.scalars(select(EmployeeAlias.raw_name).where(EmployeeAlias.employee == employee))
    )
    aliases: dict[str, str] = {}
    if {GIVEN_NAMES, SURNAME} & set(changed):
        aliases[f"{fields.given_names} {fields.surname}"] = normalize_name(
            fields.given_names, fields.surname
        )
    original = fields.original_script_name
    if ORIGINAL_SCRIPT_NAME in changed and original is not None:
        aliases.setdefault(original, normalize_name(original))
    return {raw: key for raw, key in aliases.items() if raw not in known}


def _text(value: str | None) -> str | None:
    return value if value is not None and value.strip() else None
