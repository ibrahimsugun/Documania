"""15.2.1 — çıktıya hazırla: şablonun kopyasına yalnız profil değerleri, değer biçimleri, eksik ve
taşan alan, imza kutusu boş, Kiril yazım, döndürülmüş sayfa, K8 adı, kayıt ve olay; orijinal şablon
değişmez (PLAN.md §D123 d).

Şablonlar ve çalışanlar sentetiktir (`tests/fixtures/gen.py`); harita işçi yerine doğrudan
`store_map` ile yazılıp onaylanır. Yazılan metin PyMuPDF ile kutunun içinden geri okunur."""

from __future__ import annotations

from datetime import date

import pymupdf
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ContactKind,
    Document,
    Employee,
    EmployeeContact,
    EmployeeIdentifier,
    EmployeeStatus,
    Event,
    GeneratedDocument,
    KnownDocumentType,
    OutputTemplateStatus,
)
from app.events import EventType
from app.output_templates.generate import (
    EmployeeNotEligibleError,
    TemplateNotReadyError,
    fill_template,
    generate_document,
    profile_values,
)
from app.storage import DataLayout
from app.storage.atomic import sha256_file
from tests.fixtures.gen import make_text_pdf_bytes
from tests.output_templates.factory import (
    BIRTH,
    FIXED_TEXT,
    MOTHER,
    NAME,
    SIGNATURE,
    SKIPPED,
    ready_template,
)

TODAY = date(2026, 10, 23)


def _employee(session: Session, **fields: object) -> Employee:
    employee = Employee(
        id="E0001",
        folder_name="Ivan_Petrov_E0001",
        given_names="Ivan",
        surname="Petrov",
        date_of_birth=date(1990, 3, 7),
        **fields,
    )
    session.add(employee)
    session.flush()
    return employee


def _box_text(content: bytes, box: tuple[float, float, float, float], page: int = 0) -> str:
    with pymupdf.open(stream=content, filetype="pdf") as document:
        shown = document[page].rect
        x0, y0, x1, y1 = box
        clip = pymupdf.Rect(
            x0 * shown.width, y0 * shown.height, x1 * shown.width, y1 * shown.height
        )
        target = document[page]
        return target.get_text("text", clip=clip * target.derotation_matrix).strip()


def test_generation_writes_profile_values_into_a_copy_and_leaves_the_rest_empty(
    session: Session, layout: DataLayout
) -> None:
    employee = _employee(session)
    template = ready_template(session, layout)
    original = layout.resolve(template.file_path)
    original_sha = sha256_file(original)

    result = generate_document(session, layout, template, employee, actor="ik", today=TODAY)

    row = result.document
    assert row.path == "Employees/Ivan_Petrov_E0001/Uretilen/Ivan_Petrov-Work-contract.pdf"
    assert row.sequence_no == 1
    assert row.filled_fields_json == ["full_name", "date_of_birth"]
    # Profilde boş alan uydurulmaz: kutu boş, adı eksiklerde. "Boş bırak" kutusu eksik sayılmaz.
    assert row.missing_fields_json == ["mother_name"]
    assert result.truncated == ()
    content = layout.resolve(row.path).read_bytes()
    assert _box_text(content, NAME.box) == "Ivan Petrov"
    assert _box_text(content, BIRTH.box) == "07.03.1990"
    assert _box_text(content, MOTHER.box) == ""
    assert _box_text(content, SKIPPED.box) == ""
    assert _box_text(content, SIGNATURE.box) == ""
    with pymupdf.open(stream=content, filetype="pdf") as document:
        assert FIXED_TEXT in document[0].get_text()
    # R2: orijinal şablon değişmedi; çalışan belgesi açılmadı.
    assert sha256_file(original) == original_sha
    assert session.scalar(select(func.count()).select_from(Document)) == 0

    event = session.scalars(select(Event).where(Event.type == EventType.OUTPUT_GENERATED)).one()
    assert event.actor == "ik"
    assert event.employee_id == "E0001"
    assert event.data_json == {
        "template_id": template.id,
        "map_version": 1,
        "generated_document_id": row.id,
        "filled_fields": ["full_name", "date_of_birth"],
        "missing_fields": ["mother_name"],
        "truncated_fields": [],
    }
    assert "Ivan" not in str(event.data_json) and "1990" not in str(event.data_json)


def test_a_second_generation_takes_the_next_number(session: Session, layout: DataLayout) -> None:
    employee = _employee(session)
    template = ready_template(session, layout)
    generate_document(session, layout, template, employee, actor="ik", today=TODAY)

    second = generate_document(session, layout, template, employee, actor="ik", today=TODAY)

    assert second.document.sequence_no == 2
    assert second.document.path.endswith("/Ivan_Petrov-Work-contract-2.pdf")
    assert session.scalar(select(func.count()).select_from(GeneratedDocument)) == 2


def test_profile_values_use_the_documented_formats(session: Session, layout: DataLayout) -> None:
    session.add(
        KnownDocumentType(
            slug="serbian_passport",
            name="Serbian passport",
            file_label="Passport",
            sides="single",
            direct=True,
            analyze=True,
            output_format="pdf",
        )
    )
    employee = _employee(session, nationality="SRB", other_names=None)
    session.add_all(
        [
            EmployeeIdentifier(employee_id="E0001", kind="serbian_passport", value="012345678"),
            EmployeeContact(employee_id="E0001", kind=ContactKind.PHONE.value, value="+381 11"),
            EmployeeContact(
                employee_id="E0001",
                kind=ContactKind.EMAIL.value,
                value="old@x.test",
                is_current=False,
            ),
        ]
    )
    session.flush()

    values = profile_values(session, employee, today=TODAY)

    assert values["full_name"] == "Ivan Petrov"
    assert values["date_of_birth"] == "07.03.1990"
    assert values["nationality"] == "Serbia"
    assert values["passport_number"] == "012345678"
    assert values["phone"] == "+381 11"
    assert values["email"] is None
    assert values["other_names"] is None
    assert values["today"] == "23.10.2026"


def test_cyrillic_original_spelling_is_written_with_the_embedded_font() -> None:
    field = NAME.model_copy(update={"source": "original_script_name"})

    filled = fill_template(
        make_text_pdf_bytes([FIXED_TEXT]), [field], {"original_script_name": "Иван Петров"}
    )

    assert _box_text(filled.content, field.box) == "Иван Петров"


def test_rotated_page_gets_the_text_inside_the_shown_box() -> None:
    with pymupdf.open() as document:
        document.new_page(width=595, height=842).set_rotation(90)
        pdf = document.tobytes()

    filled = fill_template(pdf, [NAME], {"full_name": "Ivan Petrov"})

    assert _box_text(filled.content, NAME.box) == "Ivan Petrov"


def test_text_too_long_for_its_box_is_written_whole_and_reported() -> None:
    small = NAME.model_copy(update={"box": (0.3, 0.1, 0.35, 0.12)})
    value = "Aleksandar Konstantinovic-Petrovic"

    filled = fill_template(make_text_pdf_bytes([FIXED_TEXT]), [small], {"full_name": value})

    assert filled.truncated == ("full_name",)
    assert filled.filled == ("full_name",)
    with pymupdf.open(stream=filled.content, filetype="pdf") as document:
        assert value in document[0].get_text()


def test_inactive_employee_and_unapproved_template_are_refused(
    session: Session, layout: DataLayout
) -> None:
    employee = _employee(session, status=EmployeeStatus.INACTIVE.value)
    template = ready_template(session, layout)
    with pytest.raises(EmployeeNotEligibleError):
        generate_document(session, layout, template, employee, actor="ik")

    employee.status = EmployeeStatus.ACTIVE.value
    template.status = OutputTemplateStatus.ARCHIVED.value
    with pytest.raises(TemplateNotReadyError):
        generate_document(session, layout, template, employee, actor="ik")
    assert session.scalar(select(func.count()).select_from(GeneratedDocument)) == 0
