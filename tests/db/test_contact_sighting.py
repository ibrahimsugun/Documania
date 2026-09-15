"""05.8.1, 05.8.2 — `record_contact_sighting` çalışanın iletişim bilgisini `employee_contacts`'a
yazar; aynı türün farklı bir değeri eski kaydı silmeden güncel işaretini devreder (K16)."""

from datetime import UTC, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ContactKind, Employee, EmployeeContact, record_contact_sighting

EMPLOYEE_ID = "E0001"


@pytest.fixture(autouse=True)
def _employee(session: Session) -> None:
    session.add(
        Employee(id=EMPLOYEE_ID, folder_name="Test_Kisi_E0001", given_names="Test", surname="Kisi")
    )
    session.flush()


def test_first_sighting_creates_a_current_row(session: Session) -> None:
    sighting = record_contact_sighting(
        session, employee_id=EMPLOYEE_ID, kind=ContactKind.PHONE.value, value="+90 555 000 0000"
    )

    assert sighting.changed is True
    session.commit()
    stored = session.scalars(select(EmployeeContact)).one()
    assert stored is sighting.contact
    assert stored.value == "+90 555 000 0000"
    assert stored.is_current is True
    assert stored.source_document_id is None
    assert stored.first_seen_at == stored.last_seen_at


def test_source_document_id_is_stored_when_given(session: Session) -> None:
    sighting = record_contact_sighting(
        session,
        employee_id=EMPLOYEE_ID,
        kind=ContactKind.EMAIL.value,
        value="test@example.invalid",
        source_document_id=None,
    )

    assert sighting.contact.source_document_id is None


def test_same_value_again_only_advances_last_seen_and_opens_no_new_row(session: Session) -> None:
    record_contact_sighting(
        session, employee_id=EMPLOYEE_ID, kind=ContactKind.EMAIL.value, value="a@b.c"
    )
    session.commit()
    stored = session.scalars(select(EmployeeContact)).one()
    first_seen = stored.first_seen_at
    stored.last_seen_at = first_seen - timedelta(days=1)
    session.commit()

    sighting = record_contact_sighting(
        session, employee_id=EMPLOYEE_ID, kind=ContactKind.EMAIL.value, value="a@b.c"
    )

    assert sighting.changed is False
    session.commit()
    rows = session.scalars(select(EmployeeContact)).all()
    assert len(rows) == 1
    assert rows[0].value == "a@b.c"
    assert rows[0].is_current is True
    assert rows[0].first_seen_at == first_seen
    assert rows[0].last_seen_at > first_seen - timedelta(days=1)


def test_different_value_keeps_the_old_row_as_history_and_opens_a_new_current_row(
    session: Session,
) -> None:
    record_contact_sighting(
        session, employee_id=EMPLOYEE_ID, kind=ContactKind.ADDRESS.value, value="Eski adres"
    )
    session.commit()

    sighting = record_contact_sighting(
        session, employee_id=EMPLOYEE_ID, kind=ContactKind.ADDRESS.value, value="Yeni adres"
    )

    assert sighting.changed is True
    session.commit()
    rows = session.scalars(select(EmployeeContact).order_by(EmployeeContact.id)).all()
    assert [row.value for row in rows] == ["Eski adres", "Yeni adres"]
    assert [row.is_current for row in rows] == [False, True]


def test_different_kinds_are_tracked_independently(session: Session) -> None:
    record_contact_sighting(
        session, employee_id=EMPLOYEE_ID, kind=ContactKind.PHONE.value, value="1"
    )
    record_contact_sighting(
        session, employee_id=EMPLOYEE_ID, kind=ContactKind.EMAIL.value, value="a@b.c"
    )
    session.commit()

    sighting = record_contact_sighting(
        session, employee_id=EMPLOYEE_ID, kind=ContactKind.PHONE.value, value="2"
    )

    assert sighting.changed is True
    session.commit()
    phone_rows = session.scalars(
        select(EmployeeContact).where(EmployeeContact.kind == ContactKind.PHONE.value)
    ).all()
    email_rows = session.scalars(
        select(EmployeeContact).where(EmployeeContact.kind == ContactKind.EMAIL.value)
    ).all()
    assert [row.value for row in phone_rows] == ["1", "2"]
    assert [row.is_current for row in email_rows] == [True]


def test_timestamps_are_timezone_aware_utc(session: Session) -> None:
    record_contact_sighting(
        session, employee_id=EMPLOYEE_ID, kind=ContactKind.PHONE.value, value="1"
    )

    session.commit()
    session.expire_all()
    stored = session.scalars(select(EmployeeContact)).one()
    assert stored.first_seen_at.tzinfo is not None
    assert stored.first_seen_at.astimezone(UTC) == stored.first_seen_at
