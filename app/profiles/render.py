"""`profil.md` üretimi — çalışan kimliği, iletişim bilgisi, belge listesi ve belge paketleri
(PRD 09.1.1, 09.1.2, 09.1.3, 14.3.1; §8.2 `Employees/<Ad_Soyad_E0001>/profil.md`).

İçerik her çağrıda veritabanının güncel durumundan baştan kurulur — hiçbir alan önceki
`profil.md`'den okunmaz, kısmi güncelleme yoktur. Bu yüzden herhangi bir değişiklikten sonra
`write_profile` çağrısı güncel hâli üretir (09.1.1); ne zaman çağrılacağı çağıranın işidir, bu
modül yalnız üretir.

Kimlik tablosunun "Durum" satırı çalışanın durumunu gösterir (Aktif, Pasif, Birleşti; 10.5.7): pasif
çalışanın klasörü ve belgeleri yerinde kalır, yalnız yeni belgeleri otomatik yerleşmez. YAML ön blok
ve kimlik tablosu aynı kimlik alanlarını taşır: `given_names`/`surname` Latin yazımdır
(05.2.2), `original_script_name` ismin belgede basılı hâlidir — alfabesi ne olursa olsun, Latin
belgede de dolu. İkisi birlikte göründüğü için ayrı bir dönüştürme adımı gerekmez (09.1.2).
Okunmamış alan `—` ile gösterilir; içerik üretilmez, yalnız var olan veritabanı satırı
görüntülenir (K11, K17). İK'nın profilden kaldırdığı belge numarası ve iletişim bilgisi (10.5.8)
ve kalıcı silinen belge (10.5.12) dosyaya girmez.

"Belge paketleri" bölümü (14.3.1) çalışana tanımlı paketleri panelin profil sayfasıyla aynı
hesapla (`app.groups.employee_packages`) gösterir: iptal edilmemiş her paket için grup adı, durum
("Açık — k/n zorunlu kalem" ya da "Tamamlandı — başvuru başlatılabilir") ve kalem tablosu (✓/○,
zorunlu/isteğe bağlı, karşılayan belgenin dosya adı); iptal edilenler ayrı listede. Üretim paket
durumunu yazmaz (yenileme noktalarının işi). Tanımlama notu ve iptal nedeni dosyaya girmez.

Başka bir kayıtla birleştirilen çalışanın (`merged`, 10.5.9) belgeleri, alt kayıtları ve paketleri
kalan kayda taşınmıştır; `profil.md`'si yalnız yönlendirme notudur: kısa YAML ön blok (numara,
klasör, durum, kalan kaydın numarası ve klasörü), başlık ve "Bu kayıt <E> ile birleştirildi" notu.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import PurePosixPath
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeContact,
    EmployeeIdentifier,
    EmployeeStatus,
    KnownDocumentType,
)
from app.groups import PackageView, employee_packages
from app.matching.records import ACTIVE_CONTACT, ACTIVE_IDENTIFIER
from app.matching.status import status_label
from app.storage import DataLayout, StoredFile, replace_file

# §8.1 `employee_contacts.kind` → kimlik tablosu satır etiketi.
_CONTACT_LABELS = {"phone": "Telefon", "email": "E-posta", "address": "Adres"}
_EMPTY = "—"
# 10.5.9: birleştirilen kaydın profil.md'si yalnız bu notu taşır.
MERGED_NOTE = (
    "Bu kayıt {kept} ile birleştirildi. Belgeleri, belge numaraları, isim yazımları, iletişim "
    "bilgileri ve belge paketleri kalan kayıttadır: {folder}. Bu klasörde yalnız bu not durur."
)


def calculate_age(date_of_birth: date, *, today: date) -> int:
    """`date_of_birth`'ten `today` gününe göre tam yaş (09.1.3)."""
    had_birthday_this_year = (today.month, today.day) >= (date_of_birth.month, date_of_birth.day)
    return today.year - date_of_birth.year - (0 if had_birthday_this_year else 1)


def render_profile(session: Session, employee: Employee, *, today: date | None = None) -> str:
    """`profil.md` içeriğini çalışanın güncel veritabanı kaydından üretir (09.1.1-09.1.3).

    Sıra: YAML ön blok, kimlik tablosu, belge listesi, belge paketleri. `today` yaş hesaplamasının
    referans günüdür (verilmezse bugün); testler belirlenebilirlik için verir.
    """
    if employee.status == EmployeeStatus.MERGED.value and employee.merged_into_id is not None:
        return _merged_profile(session, employee, employee.merged_into_id)
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
        f"{_document_list(documents)}\n"
        f"{_package_list(employee_packages(session, employee.id))}"
    )


def write_profile(
    session: Session, layout: DataLayout, employee: Employee, *, today: date | None = None
) -> StoredFile | None:
    """`render_profile`'ın çıktısını çalışanın `profil.md`'sine atomik olarak yazar (09.1.1).

    Dosya varsa baştan üretilir (`replace_file`), yoksa oluşturulur; elle düzenleme beklenmez
    (§8.2). Kalıcı silinen çalışanın (10.5.13) klasörü yoktur: hiçbir şey yazılmaz, `None` döner —
    sonradan bir yeniden çalıştırma ya da grup değişikliği klasörü geri açmasın.
    """
    if employee.status == EmployeeStatus.DELETED.value:
        return None
    content = render_profile(session, employee, today=today)
    return replace_file(layout.profile_path(employee.folder_name), content.encode("utf-8"))


def _merged_profile(session: Session, employee: Employee, kept_id: str) -> str:
    """10.5.9 — birleştirilen kaydın yönlendirme notu; kalan kaydın klasörüne işaret eder."""
    kept = session.get(Employee, kept_id)
    folder = kept.folder_name if kept is not None else _EMPTY
    front_matter = yaml.safe_dump(
        {
            "employee_id": employee.id,
            "folder_name": employee.folder_name,
            "status": employee.status,
            "merged_into": kept_id,
            "merged_into_folder": folder,
        },
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return (
        f"---\n{front_matter}---\n\n"
        f"# {employee.given_names} {employee.surname}\n\n"
        f"{MERGED_NOTE.format(kept=kept_id, folder=folder)}\n"
    )


def _identifiers(session: Session, employee_id: str) -> Sequence[EmployeeIdentifier]:
    # İK'nın kaldırdığı numara (10.5.8) dosyaya girmez.
    return session.scalars(
        select(EmployeeIdentifier)
        .where(EmployeeIdentifier.employee_id == employee_id, ACTIVE_IDENTIFIER)
        .order_by(EmployeeIdentifier.id)
    ).all()


def _current_contacts(session: Session, employee_id: str) -> Sequence[EmployeeContact]:
    return session.scalars(
        select(EmployeeContact)
        .where(
            EmployeeContact.employee_id == employee_id,
            EmployeeContact.is_current.is_(True),
            ACTIVE_CONTACT,
        )
        .order_by(EmployeeContact.kind)
    ).all()


def _documents(session: Session, employee_id: str) -> Sequence[tuple[Document, KnownDocumentType]]:
    return session.execute(
        select(Document, KnownDocumentType)
        .join(KnownDocumentType, KnownDocumentType.slug == Document.type_slug)
        .where(
            Document.employee_id == employee_id,
            # 10.5.12: kalıcı silinen belge listeden kalkar; iskeleti yalnız veritabanındadır.
            Document.status != DocumentStatus.DELETED.value,
        )
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
        ("Durum", status_label(employee.status)),
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


def _cell(value: str) -> str:
    # Tablo hücresindeki `|` sütunu bölmesin.
    return value.replace("|", "\\|")


def _package_list(packages: Sequence[PackageView]) -> str:
    header = "## Belge paketleri\n\n"
    if not packages:
        return header + "Tanımlı paket yok.\n"
    sections = []
    for package in packages:
        if package.cancelled:
            continue
        section = f"### {package.group_name} — {package.state_label}\n\n"
        section += f"Tanımlayan: {package.requested_by} · {package.requested_at.date().isoformat()}"
        if package.completed_at is not None and package.complete:
            section += f" · Tamamlandı: {package.completed_at.date().isoformat()}"
        section += "\n\n"
        if not package.items:
            section += "Grubun kalemi yok.\n"
        else:
            section += "| Kalem | Zorunlu | Durum | Belge |\n|---|---|---|---|\n"
            section += "".join(
                f"| {_cell(item.title)} | {'evet' if item.required else 'isteğe bağlı'} | "
                f"{'✓' if item.satisfied else '○'} | "
                f"{_cell(item.document.file_name) if item.document else _EMPTY} |\n"
                for item in package.items
            )
        sections.append(section)
    cancelled = [package for package in packages if package.cancelled]
    if cancelled:
        sections.append(
            "### İptal edilen paketler\n\n"
            + "".join(
                f"- {package.group_name} — iptal: {package.cancelled_by or _EMPTY}, "
                f"{package.cancelled_at.date().isoformat() if package.cancelled_at else _EMPTY}\n"
                for package in cancelled
            )
        )
    return header + "\n".join(sections)
