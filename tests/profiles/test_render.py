"""09.1.1-09.1.3 — `profil.md` üretimi: YAML ön blok, kimlik tablosu, belge listesi.

Kabul kriterleri: YAML ön blok + kimlik tablosu + belge listesi içerir (09.1.1); Latin olmayan
isimlerde hem Latin hem orijinal yazım görünür (09.1.2); ad, soyad, diğer isimler, orijinal
yazım, vatandaşlık, doğum tarihi ve hesaplanan yaş, belge numaraları, iletişim bilgileri, belge
listesi eksiksiz taşınır (09.1.3).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
import yaml
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeContact,
    EmployeeIdentifier,
    KnownDocumentType,
)
from app.profiles import calculate_age, render_profile, write_profile
from app.storage import DataLayout

EMPLOYEE_ID = "E0001"
FOLDER = "Dmitry_Vasiliev_E0001"
ORIGINAL_NAME = "Васильев Дмитрий Иванович"
TYPE_SLUG = "russian_passport"
TODAY = date(2026, 9, 18)


def _employee(
    session: Session,
    *,
    other_names: str | None = "IVANOVICH",
    original_script_name: str | None = ORIGINAL_NAME,
    nationality: str | None = "RUS",
    date_of_birth: date | None = date(1990, 4, 12),
) -> Employee:
    employee = Employee(
        id=EMPLOYEE_ID,
        folder_name=FOLDER,
        given_names="DMITRY",
        surname="VASILIEV",
        other_names=other_names,
        original_script_name=original_script_name,
        nationality=nationality,
        date_of_birth=date_of_birth,
    )
    session.add(employee)
    session.flush()
    return employee


def _identifier(session: Session, *, kind: str = TYPE_SLUG, value: str = "711234567") -> None:
    session.add(EmployeeIdentifier(employee_id=EMPLOYEE_ID, kind=kind, value=value))
    session.flush()


def _contact(
    session: Session, *, kind: str, value: str, is_current: bool = True
) -> EmployeeContact:
    contact = EmployeeContact(
        employee_id=EMPLOYEE_ID, kind=kind, value=value, is_current=is_current
    )
    session.add(contact)
    session.flush()
    return contact


def _catalog_entry(
    session: Session, *, slug: str = TYPE_SLUG, name: str = "Russian Passport"
) -> None:
    session.add(
        KnownDocumentType(
            slug=slug,
            name=name,
            file_label="Passport",
            sides="single",
            direct=True,
            analyze=True,
            output_format="keep",
        )
    )
    session.flush()


def _document(
    session: Session,
    layout: DataLayout,
    *,
    name: str = "Dmitry_Vasiliev-Passport.pdf",
    created_at: datetime = datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
    status: DocumentStatus = DocumentStatus.ACTIVE,
) -> Document:
    directory = layout.ready_dir(FOLDER)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(b"belge icerigi")
    document = Document(
        employee_id=EMPLOYEE_ID,
        type_slug=TYPE_SLUG,
        path=layout.relative(path),
        format="pdf",
        source_refs_json=[{"file_id": 1, "pages": [0]}],
        status=status.value,
        created_at=created_at,
    )
    session.add(document)
    session.flush()
    return document


# --- 09.1.1: YAML ön blok + kimlik tablosu + belge listesi -------------------------------------


def test_profile_has_front_matter_identity_table_and_document_list(
    session: Session, layout: DataLayout
) -> None:
    _employee(session)
    _identifier(session)
    _contact(session, kind="phone", value="+7 900 000 00 00")
    _contact(session, kind="email", value="dmitry@example.com")
    _catalog_entry(session)
    _document(session, layout)

    content = render_profile(session, session.get_one(Employee, EMPLOYEE_ID), today=TODAY)

    assert content.startswith("---\n")
    front_matter, _, body = content.removeprefix("---\n").partition("\n---\n")
    parsed = yaml.safe_load(front_matter)
    assert parsed == {
        "employee_id": "E0001",
        "folder_name": FOLDER,
        "given_names": "DMITRY",
        "surname": "VASILIEV",
        "other_names": "IVANOVICH",
        "original_script_name": ORIGINAL_NAME,
        "nationality": "RUS",
        "date_of_birth": date(1990, 4, 12),
        "age": 36,
        "document_numbers": [{"kind": TYPE_SLUG, "value": "711234567"}],
        "contacts": [
            {"kind": "email", "value": "dmitry@example.com"},
            {"kind": "phone", "value": "+7 900 000 00 00"},
        ],
    }
    assert "## Kimlik" in body
    assert "## Belgeler" in body
    assert "| Russian Passport | Dmitry_Vasiliev-Passport.pdf | active | 2026-09-10 |" in body


# --- 09.1.2: Latin olmayan isimlerde hem Latin hem orijinal yazım -------------------------------


def test_non_latin_name_shows_both_latin_and_original_script(
    session: Session, layout: DataLayout
) -> None:
    _employee(session, original_script_name=ORIGINAL_NAME)

    content = render_profile(session, session.get_one(Employee, EMPLOYEE_ID), today=TODAY)

    assert "DMITRY" in content and "VASILIEV" in content
    assert ORIGINAL_NAME in content


def test_latin_only_name_leaves_original_script_placeholder(
    session: Session, layout: DataLayout
) -> None:
    _employee(session, original_script_name=None)

    content = render_profile(session, session.get_one(Employee, EMPLOYEE_ID), today=TODAY)

    assert "| Orijinal yazım | — |" in content
    parsed = yaml.safe_load(content.removeprefix("---\n").partition("\n---\n")[0])
    assert parsed["original_script_name"] is None


# --- 09.1.3: eksiksizlik -------------------------------------------------------------------------


def test_all_required_fields_are_present_when_read(session: Session, layout: DataLayout) -> None:
    _employee(session)
    _identifier(session)
    _contact(session, kind="address", value="ул. Ленина, д. 5")
    _catalog_entry(session)
    _document(session, layout)

    content = render_profile(session, session.get_one(Employee, EMPLOYEE_ID), today=TODAY)

    for expected in (
        "DMITRY",
        "VASILIEV",
        "IVANOVICH",
        ORIGINAL_NAME,
        "RUS",
        "1990-04-12",
        "36",
        "711234567",
        "ул. Ленина, д. 5",
        "Russian Passport",
    ):
        assert expected in content


def test_missing_optional_fields_render_as_placeholder(
    session: Session, layout: DataLayout
) -> None:
    _employee(
        session,
        other_names=None,
        original_script_name=None,
        nationality=None,
        date_of_birth=None,
    )

    content = render_profile(session, session.get_one(Employee, EMPLOYEE_ID), today=TODAY)

    assert "| Diğer isimler | — |" in content
    assert "| Orijinal yazım | — |" in content
    assert "| Vatandaşlık | — |" in content
    assert "| Doğum tarihi | — |" in content
    assert "| Yaş | — |" in content
    assert "| Belge numaraları | — |" in content
    assert "| Telefon | — |" in content
    assert "| E-posta | — |" in content
    assert "| Adres | — |" in content
    assert "Henüz belge yok." in content


def test_only_current_contact_is_shown(session: Session, layout: DataLayout) -> None:
    _employee(session)
    _contact(session, kind="phone", value="+7 900 111 11 11", is_current=False)
    _contact(session, kind="phone", value="+7 900 222 22 22", is_current=True)

    content = render_profile(session, session.get_one(Employee, EMPLOYEE_ID), today=TODAY)

    assert "+7 900 222 22 22" in content
    assert "+7 900 111 11 11" not in content


# --- calculate_age --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("date_of_birth", "today", "expected"),
    [
        (date(1990, 4, 12), date(2026, 9, 18), 36),
        (date(1990, 4, 12), date(2026, 4, 12), 36),
        (date(1990, 4, 12), date(2026, 4, 11), 35),
        (date(2026, 9, 18), date(2026, 9, 18), 0),
    ],
    ids=["after-birthday", "on-birthday", "day-before-birthday", "born-today"],
)
def test_calculate_age(date_of_birth: date, today: date, expected: int) -> None:
    assert calculate_age(date_of_birth, today=today) == expected


# --- write_profile: atomik yazma ve yeniden üretim (09.1.1) ------------------------------------


def test_write_profile_publishes_to_the_employee_profile_path(
    session: Session, layout: DataLayout
) -> None:
    employee = _employee(session)

    stored = write_profile(session, layout, employee, today=TODAY)

    assert stored.path == layout.profile_path(FOLDER)
    assert stored.path.read_text(encoding="utf-8") == render_profile(session, employee, today=TODAY)


def test_write_profile_regenerates_the_whole_file_after_a_change(
    session: Session, layout: DataLayout
) -> None:
    employee = _employee(session, original_script_name=None)
    write_profile(session, layout, employee, today=TODAY)

    _contact(session, kind="phone", value="+7 900 000 00 00")
    employee.original_script_name = ORIGINAL_NAME
    session.flush()
    stored = write_profile(session, layout, employee, today=TODAY)

    content = stored.path.read_text(encoding="utf-8")
    assert "+7 900 000 00 00" in content
    assert ORIGINAL_NAME in content
    assert content == render_profile(session, employee, today=TODAY)


def test_write_profile_overwrites_without_leaving_stale_content(
    session: Session, layout: DataLayout
) -> None:
    employee = _employee(session)
    _identifier(session)
    write_profile(session, layout, employee, today=TODAY)

    for identifier in session.query(EmployeeIdentifier).all():
        session.delete(identifier)
    session.flush()
    stored = write_profile(session, layout, employee, today=TODAY)

    content = stored.path.read_text(encoding="utf-8")
    assert "711234567" not in content
    profile_dir = layout.employee_dir(FOLDER)
    assert [p.name for p in profile_dir.iterdir() if p.is_file()] == ["profil.md"]


def test_document_list_shows_every_document_with_its_status(
    session: Session, layout: DataLayout
) -> None:
    _employee(session)
    _catalog_entry(session)
    _document(session, layout, name="Dmitry_Vasiliev-Passport.pdf", status=DocumentStatus.ACTIVE)
    _document(
        session,
        layout,
        name="Dmitry_Vasiliev-Passport-2.pdf",
        status=DocumentStatus.SUPERSEDED,
    )

    content = render_profile(session, session.get_one(Employee, EMPLOYEE_ID), today=TODAY)

    assert "| Russian Passport | Dmitry_Vasiliev-Passport.pdf | active |" in content
    assert "| Russian Passport | Dmitry_Vasiliev-Passport-2.pdf | superseded |" in content
