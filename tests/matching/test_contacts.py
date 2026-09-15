"""05.8.1, 05.8.2 — adayın sayfalarından okunan telefon/e-posta/adres eşleşen çalışana eklenir;
aynı türün en son görülen değeri alınır, farklı değer eskisini silmeden güncel işaretini devralır.

Sayfalar `tests.ai.payloads.analysis_payload` sentetik yanıtından kurulur. Gerçek kişi/belge yok.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import PageAnalysis
from app.db.models import Employee, EmployeeContact
from app.matching.contacts import accumulate_contacts, collect_contacts
from tests.ai.payloads import analysis_payload

EMPLOYEE_ID = "E0001"


def _page(*, contact: dict[str, str | None] | None = None, **top: Any) -> PageAnalysis:
    payload = analysis_payload(**top)
    payload["person"]["contact"] = {"phone": None, "email": None, "address": None} | (contact or {})
    return PageAnalysis.model_validate(payload)


@pytest.fixture(autouse=True)
def _employee(session: Session) -> None:
    session.add(
        Employee(id=EMPLOYEE_ID, folder_name="Test_Kisi_E0001", given_names="Test", surname="Kisi")
    )
    session.flush()


# --- collect_contacts (05.8.1) -----------------------------------------------------------------


def test_collect_contacts_reads_every_kind_written_on_the_document() -> None:
    page = _page(contact={"phone": "+90 555 1", "email": "a@b.c", "address": "Adres 1"})

    assert collect_contacts([page]) == {
        "phone": "+90 555 1",
        "email": "a@b.c",
        "address": "Adres 1",
    }


def test_collect_contacts_omits_kinds_never_written() -> None:
    page = _page(contact={"phone": "+90 555 1"})

    assert collect_contacts([page]) == {"phone": "+90 555 1"}


def test_collect_contacts_takes_the_last_seen_value_across_pages() -> None:
    first = _page(page_index=0, contact={"phone": "+90 555 1"})
    second = _page(page_index=1, contact={"phone": "+90 555 2"})

    assert collect_contacts([first, second]) == {"phone": "+90 555 2"}


def test_collect_contacts_keeps_a_kind_last_written_on_an_earlier_page() -> None:
    # İkinci sayfa telefonu boş bırakıyor (yazılı değil) — ilk sayfanın okuması kaybolmaz.
    first = _page(page_index=0, contact={"phone": "+90 555 1"})
    second = _page(page_index=1, contact={"email": "a@b.c"})

    assert collect_contacts([first, second]) == {"phone": "+90 555 1", "email": "a@b.c"}


@pytest.mark.parametrize("top", [{"is_blank": True}, {"is_readable": False}])
def test_collect_contacts_ignores_blank_or_unreadable_pages(top: dict[str, Any]) -> None:
    unreadable = _page(contact={"phone": "+90 555 1"}, **top)

    assert collect_contacts([unreadable]) == {}


def test_collect_contacts_of_no_pages_is_empty() -> None:
    assert collect_contacts([]) == {}


# --- accumulate_contacts (05.8.1, 05.8.2) -------------------------------------------------------


def test_accumulate_contacts_writes_every_kind_to_the_employee(session: Session) -> None:
    page = _page(contact={"phone": "+90 555 1", "email": "a@b.c", "address": "Adres 1"})

    changed = accumulate_contacts(session, EMPLOYEE_ID, [page])

    assert set(changed) == {"phone", "email", "address"}
    session.commit()
    rows = {row.kind: row.value for row in session.scalars(select(EmployeeContact))}
    assert rows == {"phone": "+90 555 1", "email": "a@b.c", "address": "Adres 1"}
    assert all(row.is_current for row in session.scalars(select(EmployeeContact)))


def test_accumulate_contacts_with_nothing_written_changes_nothing(session: Session) -> None:
    page = _page()

    changed = accumulate_contacts(session, EMPLOYEE_ID, [page])

    assert changed == ()
    session.commit()
    assert session.scalars(select(EmployeeContact)).all() == []


def test_accumulate_contacts_same_value_again_reports_no_change(session: Session) -> None:
    page = _page(contact={"phone": "+90 555 1"})
    accumulate_contacts(session, EMPLOYEE_ID, [page])
    session.commit()

    changed = accumulate_contacts(session, EMPLOYEE_ID, [page])

    assert changed == ()
    session.commit()
    rows = session.scalars(select(EmployeeContact)).all()
    assert len(rows) == 1
    assert rows[0].is_current is True


def test_accumulate_contacts_different_value_keeps_history_and_flips_current(
    session: Session,
) -> None:
    accumulate_contacts(session, EMPLOYEE_ID, [_page(contact={"phone": "+90 555 1"})])
    session.commit()

    changed = accumulate_contacts(session, EMPLOYEE_ID, [_page(contact={"phone": "+90 555 2"})])

    assert changed == ("phone",)
    session.commit()
    rows = session.scalars(select(EmployeeContact).order_by(EmployeeContact.id)).all()
    assert [row.value for row in rows] == ["+90 555 1", "+90 555 2"]
    assert [row.is_current for row in rows] == [False, True]


def test_accumulate_contacts_leaves_source_document_id_unset_by_default(session: Session) -> None:
    # Bu aşamada (05.5-05.7) çıktı belgesi henüz yok; `employee_identifiers`/`employee_aliases`
    # ile aynı örüntü (D11).
    page = _page(contact={"phone": "+90 555 1"})

    accumulate_contacts(session, EMPLOYEE_ID, [page])

    session.commit()
    stored = session.scalars(select(EmployeeContact)).one()
    assert stored.source_document_id is None
