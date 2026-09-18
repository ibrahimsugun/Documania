"""`profil.md` üretimi — çalışan kimliği, iletişim bilgisi ve belge listesi
(PRD 09.1.1, 09.1.2, 09.1.3; §8.2 `Employees/<Ad_Soyad_E0001>/profil.md`).

İçerik her çağrıda veritabanının güncel durumundan baştan kurulur — hiçbir alan önceki
`profil.md`'den okunmaz, kısmi güncelleme yoktur. Bu yüzden herhangi bir değişiklikten sonra
`write_profile` çağrısı güncel hâli üretir (09.1.1); ne zaman çağrılacağı çağıranın işidir, bu
modül yalnız üretir.

YAML ön blok ve kimlik tablosu aynı alanları taşır: `given_names`/`surname` belgeden okunan
(genelde Latin) yazımdır, `original_script_name` doluysa Latin olmayan asıl yazımdır — ikisi
birlikte göründüğü için Latin olmayan isimlerde ayrı bir dönüştürme adımı gerekmez (09.1.2).
Okunmamış alan `—` ile gösterilir; içerik üretilmez, yalnız var olan veritabanı satırı
görüntülenir (K11, K17).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import PurePosixPath
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, Employee, EmployeeContact, EmployeeIdentifier, KnownDocumentType
from app.storage import DataLayout, StoredFile, replace_file

# §8.1 `employee_contacts.kind` → kimlik tablosu satır etiketi.
_CONTACT_LABELS = {"phone": "Telefon", "email": "E-posta", "address": "Adres"}
_EMPTY = "—"


def calculate_age(date_of_birth: date, *, today: date) -> int:
    """`date_of_birth`'ten `today` gününe göre tam yaş (09.1.3)."""
    had_birthday_this_year = (today.month, today.day) >= (date_of_birth.month, date_of_birth.day)
    return today.year - date_of_birth.year - (0 if had_birthday_this_year else 1)


def render_profile(session: Session, employee: Employee, *, today: date | None = None) -> str:
    """`profil.md` içeriğini çalışanın güncel veritabanı kaydından üretir (09.1.1-09.1.3).

    Sıra: YAML ön blok, kimlik tablosu, belge listesi. `today` yaş hesaplamasının referans
    günüdür (verilmezse bugün); testler belirlenebilirlik için verir.
    """
    reference_date = today if today is not None else date.today()
    identifiers = _identifiers(session, employee.id)
    contacts = _current_contacts(session, employee.id)
    documents = _documents(session, employee.id)
    age = (
        None
        if employee.date_of_birth is None
        else calculate_age(employee.date_of_birth, today=reference_date)
    )
    front_matter = yaml.safe_dump(
        _front_matter_data(employee, identifiers, contacts, age),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return (
        f"---\n{front_matter}---\n\n"
        f"# {employee.given_names} {employee.surname}\n\n"
        f"{_identity_table(employee, identifiers, contacts, age)}\n"
        f"{_document_list(documents)}"
    )


def write_profile(
    session: Session, layout: DataLayout, employee: Employee, *, today: date | None = None
) -> StoredFile:
    """`render_profile`'ın çıktısını çalışanın `profil.md`'sine atomik olarak yazar (09.1.1).

    Dosya varsa baştan üretilir (`replace_file`), yoksa oluşturulur; elle düzenleme beklenmez
    (§8.2).
    """
    content = render_profile(session, employee, today=today)
    return replace_file(layout.profile_path(employee.folder_name), content.encode("utf-8"))


def _identifiers(session: Session, employee_id: str) -> Sequence[EmployeeIdentifier]:
    return session.scalars(
        select(EmployeeIdentifier)
        .where(EmployeeIdentifier.employee_id == employee_id)
        .order_by(EmployeeIdentifier.id)
    ).all()


def _current_contacts(session: Session, employee_id: str) -> Sequence[EmployeeContact]:
    return session.scalars(
        select(EmployeeContact)
        .where(EmployeeContact.employee_id == employee_id, EmployeeContact.is_current.is_(True))
        .order_by(EmployeeContact.kind)
    ).all()


def _documents(session: Session, employee_id: str) -> Sequence[tuple[Document, KnownDocumentType]]:
    return session.execute(
        select(Document, KnownDocumentType)
        .join(KnownDocumentType, KnownDocumentType.slug == Document.type_slug)
        .where(Document.employee_id == employee_id)
        .order_by(Document.created_at, Document.id)
    ).all()


def _front_matter_data(
    employee: Employee,
    identifiers: Sequence[EmployeeIdentifier],
    contacts: Sequence[EmployeeContact],
    age: int | None,
) -> dict[str, Any]:
    return {
        "employee_id": employee.id,
        "folder_name": employee.folder_name,
        "given_names": employee.given_names,
        "surname": employee.surname,
        "other_names": employee.other_names,
        "original_script_name": employee.original_script_name,
        "nationality": employee.nationality,
        "date_of_birth": employee.date_of_birth,
        "age": age,
        "document_numbers": [
            {"kind": identifier.kind, "value": identifier.value} for identifier in identifiers
        ],
        "contacts": [{"kind": contact.kind, "value": contact.value} for contact in contacts],
    }


def _identity_table(
    employee: Employee,
    identifiers: Sequence[EmployeeIdentifier],
    contacts: Sequence[EmployeeContact],
    age: int | None,
) -> str:
    numbers = ", ".join(f"{i.kind}: {i.value}" for i in identifiers) or _EMPTY
    contact_by_kind = {contact.kind: contact.value for contact in contacts}
    rows = [
        ("Çalışan no", employee.id),
        ("Ad", employee.given_names),
        ("Soyad", employee.surname),
        ("Diğer isimler", employee.other_names or _EMPTY),
        ("Orijinal yazım", employee.original_script_name or _EMPTY),
        ("Vatandaşlık", employee.nationality or _EMPTY),
        ("Doğum tarihi", employee.date_of_birth.isoformat() if employee.date_of_birth else _EMPTY),
        ("Yaş", str(age) if age is not None else _EMPTY),
        ("Belge numaraları", numbers),
        *((label, contact_by_kind.get(kind, _EMPTY)) for kind, label in _CONTACT_LABELS.items()),
    ]
    header = "## Kimlik\n\n| Alan | Değer |\n|---|---|\n"
    body = "".join(f"| {field} | {value} |\n" for field, value in rows)
    return header + body


def _document_list(documents: Sequence[tuple[Document, KnownDocumentType]]) -> str:
    header = "## Belgeler\n\n"
    if not documents:
        return header + "Henüz belge yok.\n"
    header += "| Tür | Dosya | Durum | Tarih |\n|---|---|---|---|\n"
    rows = "".join(
        f"| {document_type.name} | {PurePosixPath(document.path).name} | {document.status} | "
        f"{document.created_at.date().isoformat()} |\n"
        for document, document_type in documents
    )
    return header + rows
