"""10.5.7 — çalışanı pasife alma ve yeniden etkinleştirme çekirdeği: durum çevrilir, olay kullanıcı
adıyla ve kişisel değer taşımadan yazılır, not isteğe bağlıdır (≤ 200); birleştirilmiş ya da zaten
o durumdaki çalışan değişmez; klasör ve belgeler yerinde kalır (PLAN.md §C90-b; K16, R11).

Birim testleri `change_employee_status`'ı geçici SQLite ve geçici veri dizinindeki sentetik
çalışanla sınar; gerçek kişi ya da belge ve ağ çağrısı yoktur. İki aşamalı onay ve sayfa
`tests/web/test_employee_status.py`'de, pasif çalışanın rotası `tests/pipeline/test_plan.py`'dedir.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Employee, EmployeeStatus, Event
from app.events import EventType
from app.matching.status import (
    INACTIVE_EMPLOYEE_CODE,
    INACTIVE_SUFFIX,
    REASON_MAX_LENGTH,
    STATUS_LABELS,
    EmployeeMergedError,
    StatusReasonError,
    StatusUnchangedError,
    change_employee_status,
    inactive_employee_reason,
    is_inactive_employee_reason,
    last_deactivation,
    normalized_reason,
    status_label,
    status_suffix,
    status_target,
)
from app.storage import DataLayout, sha256_file
from tests.fixtures.gen import make_pdf_bytes

ACTOR = "ik-yonetici"
EMPLOYEE_ID = "E0001"
FOLDER = "Ivan_Petrov_E0001"


def _employee(session: Session, status: str = EmployeeStatus.ACTIVE.value) -> Employee:
    employee = Employee(
        id=EMPLOYEE_ID,
        folder_name=FOLDER,
        given_names="Ivan",
        surname="Petrov",
        date_of_birth=date(1990, 1, 1),
        status=status,
    )
    session.add(employee)
    session.flush()
    return employee


def _events(session: Session) -> list[Event]:
    return list(session.scalars(select(Event).order_by(Event.id)))


def test_every_status_has_a_turkish_label_and_unknown_shows_raw() -> None:
    assert STATUS_LABELS == {
        "active": "Aktif",
        "inactive": "Pasif",
        "merged": "Birleşti",
        "deleted": "Silindi",  # 10.5.13
    }
    assert set(STATUS_LABELS) == {status.value for status in EmployeeStatus}
    assert status_label("pending") == "pending"


def test_only_the_inactive_status_gets_the_suffix() -> None:
    assert status_suffix("inactive") == INACTIVE_SUFFIX == " (pasif)"
    assert status_suffix("active") == status_suffix("merged") == ""


def test_the_inactive_reason_carries_the_code_and_the_number_only() -> None:
    reason = inactive_employee_reason("E0042")

    assert reason.startswith("Pasif çalışan (E0042) ile eşleşti (inactive_employee)")
    assert INACTIVE_EMPLOYEE_CODE in reason and "R7" in reason
    assert is_inactive_employee_reason(reason)
    assert is_inactive_employee_reason("Okunamayan alanlar: x " + reason)
    assert not is_inactive_employee_reason("İsim eşleşti ama doğum tarihi doğrulanamadı")
    assert not is_inactive_employee_reason(None)


def test_deactivation_flips_the_status_and_logs_the_user(session: Session) -> None:
    employee = _employee(session)

    event = change_employee_status(
        session, employee, EmployeeStatus.INACTIVE, actor=ACTOR, reason="  işten   ayrıldı "
    )

    assert employee.status == "inactive"
    assert (event.type, event.actor, event.employee_id) == (
        "EMPLOYEE_DEACTIVATED",
        ACTOR,
        EMPLOYEE_ID,
    )
    assert event.data_json == {"from": "active", "to": "inactive", "reason": "işten ayrıldı"}
    assert last_deactivation(session, EMPLOYEE_ID) is event


def test_reactivation_logs_its_own_event_without_a_note(session: Session) -> None:
    employee = _employee(session, EmployeeStatus.INACTIVE.value)

    event = change_employee_status(session, employee, EmployeeStatus.ACTIVE, actor=ACTOR)

    assert employee.status == "active"
    assert (event.type, event.data_json) == (
        EventType.EMPLOYEE_REACTIVATED.value,
        {"from": "inactive", "to": "active"},
    )
    assert last_deactivation(session, EMPLOYEE_ID) is None


def test_the_latest_deactivation_is_found_after_a_round_trip(session: Session) -> None:
    employee = _employee(session)
    change_employee_status(session, employee, EmployeeStatus.INACTIVE, actor=ACTOR, reason="bir")
    change_employee_status(session, employee, EmployeeStatus.ACTIVE, actor=ACTOR)
    second = change_employee_status(
        session, employee, EmployeeStatus.INACTIVE, actor="baska", reason="iki"
    )

    assert last_deactivation(session, EMPLOYEE_ID) is second
    assert [event.type for event in _events(session)] == [
        "EMPLOYEE_DEACTIVATED",
        "EMPLOYEE_REACTIVATED",
        "EMPLOYEE_DEACTIVATED",
    ]


@pytest.mark.parametrize(
    ("status", "target", "error"),
    [
        ("inactive", EmployeeStatus.INACTIVE, StatusUnchangedError),
        ("active", EmployeeStatus.ACTIVE, StatusUnchangedError),
        ("merged", EmployeeStatus.ACTIVE, EmployeeMergedError),
        ("merged", EmployeeStatus.INACTIVE, EmployeeMergedError),
    ],
)
def test_a_refused_change_writes_nothing(
    session: Session, status: str, target: EmployeeStatus, error: type[Exception]
) -> None:
    employee = _employee(session, status)

    with pytest.raises(error):
        change_employee_status(session, employee, target, actor=ACTOR)

    assert employee.status == status
    assert _events(session) == []


def test_merged_is_not_a_target_and_the_actor_is_required(session: Session) -> None:
    employee = _employee(session)

    with pytest.raises(ValueError, match="active ya da inactive"):
        change_employee_status(session, employee, EmployeeStatus.MERGED, actor=ACTOR)
    with pytest.raises(ValueError, match="actor"):
        change_employee_status(session, employee, EmployeeStatus.INACTIVE, actor="  ")
    assert (employee.status, _events(session)) == ("active", [])


def test_the_note_is_optional_and_bounded(session: Session) -> None:
    employee = _employee(session)

    assert normalized_reason(None) is None
    assert normalized_reason("   ") is None
    assert normalized_reason("x" * REASON_MAX_LENGTH) == "x" * REASON_MAX_LENGTH
    with pytest.raises(StatusReasonError, match="200"):
        change_employee_status(
            session,
            employee,
            EmployeeStatus.INACTIVE,
            actor=ACTOR,
            reason="x" * (REASON_MAX_LENGTH + 1),
        )
    assert (employee.status, _events(session)) == ("active", [])


def test_the_button_target_follows_the_current_status(session: Session) -> None:
    employee = _employee(session)
    assert status_target(employee) is EmployeeStatus.INACTIVE
    employee.status = "inactive"
    assert status_target(employee) is EmployeeStatus.ACTIVE
    employee.status = "merged"
    with pytest.raises(EmployeeMergedError):
        status_target(employee)


def test_the_folder_and_the_documents_stay_in_place(session: Session, layout: DataLayout) -> None:
    # R11: pasife alma dosyaya dokunmaz — klasör ve içindeki dosya bayt bayt aynı yerde kalır.
    employee = _employee(session)
    ready = layout.ensure_employee_tree(FOLDER) / "Hazir"
    (ready / "Ivan_Petrov-Passport.pdf").write_bytes(make_pdf_bytes())
    before = {
        path.relative_to(layout.root).as_posix(): sha256_file(path)
        for path in sorted(Path(layout.root).rglob("*"))
        if path.is_file()
    }

    change_employee_status(session, employee, EmployeeStatus.INACTIVE, actor=ACTOR)
    change_employee_status(session, employee, EmployeeStatus.ACTIVE, actor=ACTOR)

    after = {
        path.relative_to(layout.root).as_posix(): sha256_file(path)
        for path in sorted(Path(layout.root).rglob("*"))
        if path.is_file()
    }
    assert after == before
    assert employee.folder_name == FOLDER
