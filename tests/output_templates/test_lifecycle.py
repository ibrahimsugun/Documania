"""15.2.2, 15.2.3 — üretilen belgenin yaşam döngüsü: yeniden üretim öncekini `superseded` yapar
(K18 kalıbı), arşivle/geri al (tek adım, olaylı), çalışan yeniden adlandırılınca `Uretilen/`
dosyaları K8 adını alır (10.5.6), birleştirmede kalan kayda taşınır (10.5.9), kalıcı silmede
diskten kalkar ve satır `deleted` olur (10.5.13). Profil.md "Üretilen belgeler" bölümünü taşır.

Şablon ve çalışanlar sentetiktir (`tests/output_templates/factory.py`)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Employee,
    EmployeeStatus,
    Event,
    GeneratedDocument,
    GeneratedDocumentStatus,
)
from app.events import EventType
from app.matching.edit import current_profile_fields, update_employee_fields
from app.matching.merge import merge_employees
from app.output_templates.generate import generate_document
from app.output_templates.lifecycle import OutputNotFoundError, set_output_archived
from app.profiles import render_profile
from app.storage import DataLayout
from app.storage.delete_employee import delete_employee, remove_employee_files
from tests.output_templates.factory import ready_template

ACTOR = "ik-ayse"
ACTIVE = GeneratedDocumentStatus.ACTIVE.value
SUPERSEDED = GeneratedDocumentStatus.SUPERSEDED.value
ARCHIVED = GeneratedDocumentStatus.ARCHIVED.value


def _employee(session: Session, layout: DataLayout, number: str, given: str, surname: str):
    folder = f"{given}_{surname}_{number}"
    employee = Employee(
        id=number,
        folder_name=folder,
        given_names=given,
        surname=surname,
        date_of_birth=date(1990, 3, 7),
    )
    session.add(employee)
    layout.ensure_employee_tree(folder)
    session.flush()
    return employee


def _generate(session: Session, layout: DataLayout, template, employee) -> GeneratedDocument:
    return generate_document(session, layout, template, employee, actor=ACTOR).document


def _names(layout: DataLayout, folder: str) -> list[str]:
    return sorted(path.name for path in layout.generated_dir(folder).iterdir())


def _events(session: Session, kind: EventType) -> list[Event]:
    return list(session.scalars(select(Event).where(Event.type == kind.value).order_by(Event.id)))


def test_regeneration_supersedes_the_previous_output_and_keeps_its_file(
    session: Session, layout: DataLayout
) -> None:
    employee = _employee(session, layout, "E0001", "Ivan", "Petrov")
    template = ready_template(session, layout)
    first = _generate(session, layout, template, employee)
    first_bytes = layout.resolve(first.path).read_bytes()

    second = _generate(session, layout, template, employee)

    assert (first.status, second.status) == (SUPERSEDED, ACTIVE)
    assert second.sequence_no == 2
    assert _names(layout, employee.folder_name) == [
        "Ivan_Petrov-Work-contract-2.pdf",
        "Ivan_Petrov-Work-contract.pdf",
    ]
    assert layout.resolve(first.path).read_bytes() == first_bytes
    assert _events(session, EventType.OUTPUT_GENERATED)[-1].data_json["superseded"] == [first.id]


def test_archive_and_restore_are_single_steps_with_events_and_restore_the_right_status(
    session: Session, layout: DataLayout
) -> None:
    employee = _employee(session, layout, "E0001", "Ivan", "Petrov")
    template = ready_template(session, layout)
    first = _generate(session, layout, template, employee)
    second = _generate(session, layout, template, employee)

    assert set_output_archived(session, "E0001", first.id, True, actor=ACTOR)
    assert not set_output_archived(session, "E0001", first.id, True, actor=ACTOR)
    assert (first.status, first.archived_by) == (ARCHIVED, ACTOR)
    assert layout.resolve(first.path).is_file()
    # Daha yeni belge varken geri alınan eski sürüm olur; en yenisi etkin döner.
    assert set_output_archived(session, "E0001", first.id, False, actor=ACTOR)
    set_output_archived(session, "E0001", second.id, True, actor=ACTOR)
    set_output_archived(session, "E0001", second.id, False, actor=ACTOR)
    assert (first.status, first.archived_at, second.status) == (SUPERSEDED, None, ACTIVE)

    archived = _events(session, EventType.OUTPUT_ARCHIVED)
    restored = _events(session, EventType.OUTPUT_RESTORED)
    assert [event.data_json for event in archived] == [
        {"generated_document_id": first.id, "template_id": template.id, "status": ARCHIVED},
        {"generated_document_id": second.id, "template_id": template.id, "status": ARCHIVED},
    ]
    assert [event.data_json["status"] for event in restored] == [SUPERSEDED, ACTIVE]
    assert {event.actor for event in archived + restored} == {ACTOR}
    with pytest.raises(OutputNotFoundError):
        set_output_archived(session, "E0002", first.id, True, actor=ACTOR)


def test_renaming_the_employee_renames_the_generated_files(
    session: Session, layout: DataLayout
) -> None:
    employee = _employee(session, layout, "E0001", "Ivan", "Petrov")
    template = ready_template(session, layout)
    first = _generate(session, layout, template, employee)
    second = _generate(session, layout, template, employee)
    set_output_archived(session, "E0001", first.id, True, actor=ACTOR)
    content = layout.resolve(second.path).read_bytes()

    edited = update_employee_fields(
        session,
        layout,
        employee,
        replace(current_profile_fields(employee), surname="Petrova"),
        actor=ACTOR,
    )

    assert employee.folder_name == "Ivan_Petrova_E0001"
    assert (first.path, second.path) == (
        "Employees/Ivan_Petrova_E0001/Uretilen/Ivan_Petrova-Work-contract.pdf",
        "Employees/Ivan_Petrova_E0001/Uretilen/Ivan_Petrova-Work-contract-2.pdf",
    )
    assert _names(layout, "Ivan_Petrova_E0001") == [
        "Ivan_Petrova-Work-contract-2.pdf",
        "Ivan_Petrova-Work-contract.pdf",
    ]
    assert layout.resolve(second.path).read_bytes() == content
    assert edited.event.data_json["outputs"] == [first.id, second.id]


def test_merging_moves_the_generated_documents_to_the_kept_record_with_its_k8_name(
    session: Session, layout: DataLayout
) -> None:
    keep = _employee(session, layout, "E0001", "Ivan", "Petrov")
    merge = _employee(session, layout, "E0002", "Ivan", "Petrow")
    template = ready_template(session, layout)
    kept_output = _generate(session, layout, template, keep)
    moved = _generate(session, layout, template, merge)

    result = merge_employees(session, layout, keep, merge, actor=ACTOR)

    assert (moved.employee_id, moved.sequence_no, moved.status) == ("E0001", 2, ACTIVE)
    assert moved.path == "Employees/Ivan_Petrov_E0001/Uretilen/Ivan_Petrov-Work-contract-2.pdf"
    assert kept_output.path.endswith("/Ivan_Petrov-Work-contract.pdf")
    assert _names(layout, "Ivan_Petrov_E0001") == [
        "Ivan_Petrov-Work-contract-2.pdf",
        "Ivan_Petrov-Work-contract.pdf",
    ]
    assert _names(layout, "Ivan_Petrow_E0002") == []
    assert result.outputs == (moved.id,)
    assert result.event.data_json["outputs"] == [moved.id]


def test_permanent_deletion_removes_generated_files_and_leaves_deleted_rows(
    session: Session, layout: DataLayout
) -> None:
    employee = _employee(session, layout, "E0001", "Ivan", "Petrov")
    template = ready_template(session, layout)
    outputs = [_generate(session, layout, template, employee) for _ in range(2)]
    files = [layout.resolve(output.path) for output in outputs]
    original = layout.resolve(template.file_path)
    employee.status = EmployeeStatus.INACTIVE.value
    session.commit()

    deleted = delete_employee(session, layout, "E0001", actor=ACTOR)
    session.commit()
    assert remove_employee_files(session, deleted) == 0

    assert not any(path.exists() for path in files)
    assert original.is_file()
    rows = session.scalars(select(GeneratedDocument)).all()
    assert {(row.status, row.path) for row in rows} == {("deleted", None)}
    assert deleted.event.data_json["outputs"] == 2
    assert deleted.event.data_json["files_deleted"] == 2


def test_profile_md_lists_generated_documents_but_not_deleted_ones(
    session: Session, layout: DataLayout
) -> None:
    employee = _employee(session, layout, "E0001", "Ivan", "Petrov")
    template = ready_template(session, layout)
    first = _generate(session, layout, template, employee)
    _generate(session, layout, template, employee)
    set_output_archived(session, "E0001", first.id, True, actor=ACTOR)
    on = first.generated_at.date().isoformat()

    outputs = render_profile(session, employee).split("## Üretilen belgeler\n\n", 1)[1]

    assert outputs == (
        "| Şablon | Dosya | Durum | Tarih |\n|---|---|---|---|\n"
        f"| Work contract | Ivan_Petrov-Work-contract.pdf | archived | {on} |\n"
        f"| Work contract | Ivan_Petrov-Work-contract-2.pdf | active | {on} |\n"
    )
