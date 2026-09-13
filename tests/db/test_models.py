"""00.3.1 — §8.1 tabloları SQLAlchemy modeli olarak vardır ve ilişkiler doğrulanır."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.db.models import (
    AccessLog,
    Base,
    CandidateDocumentType,
    Document,
    Employee,
    EmployeeAlias,
    EmployeeContact,
    EmployeeIdentifier,
    Event,
    KnownDocumentType,
    Page,
    Plan,
    QueueItem,
    TelegramUser,
    Upload,
    UploadFile,
    User,
)
from app.db.session import create_session_factory

SECTION_8_1_TABLES = {
    "employees",
    "employee_identifiers",
    "employee_aliases",
    "employee_contacts",
    "uploads",
    "upload_files",
    "pages",
    "plans",
    "documents",
    "queue_items",
    "known_document_types",
    "candidate_document_types",
    "events",
    "access_log",
    "users",
    "telegram_users",
}


def _employee(number: str = "E0001") -> Employee:
    return Employee(
        id=number, folder_name=f"Test_Kisi_{number}", given_names="Test", surname="Kisi"
    )


def _document_type(slug: str = "test_passport") -> KnownDocumentType:
    return KnownDocumentType(
        slug=slug,
        name="Test Passport",
        file_label="Passport",
        sides="single",
        direct=True,
        analyze=True,
        output_format="keep",
    )


def test_metadata_defines_every_section_8_1_table() -> None:
    assert set(Base.metadata.tables) == SECTION_8_1_TABLES


def test_relationships_navigate_in_both_directions(engine: Engine) -> None:
    ts = datetime(2026, 9, 5, 9, 30, tzinfo=UTC)
    with create_session_factory(engine)() as session:
        employee = _employee()
        employee.date_of_birth = date(1990, 4, 12)
        doc_type = _document_type()
        upload = Upload(id="u_20260905_0001", channel="web", context_employee=employee)
        original = UploadFile(
            upload=upload,
            original_name="pasaport.pdf",
            stored_path="Inbox/u_20260905_0001/pasaport.pdf",
            sha256="a" * 64,
            mime="application/pdf",
            page_count=2,
        )
        duplicate = UploadFile(
            upload=upload,
            original_name="pasaport-kopya.pdf",
            stored_path="Inbox/u_20260905_0001/pasaport-kopya.pdf",
            sha256="a" * 64,
            mime="application/pdf",
            duplicate_of=original,
        )
        pages = [Page(file=original, index=1), Page(file=original, index=0)]
        plan_v1 = Plan(upload=upload, version=1, json={"items": []}, plan_hash="1" * 64)
        plan_v2 = Plan(upload=upload, version=2, json={"items": []}, plan_hash="2" * 64)
        document = Document(
            employee=employee,
            document_type=doc_type,
            plan=plan_v2,
            path="Employees/Test_Kisi_E0001/Hazir/Test_Kisi-Passport.pdf",
            format="pdf",
            source_refs_json=[{"file_id": 1, "pages": [0]}],
        )
        identifier = EmployeeIdentifier(
            employee=employee, kind="passport", value="T0000001", source_document=document
        )
        alias = EmployeeAlias(employee=employee, raw_name="TEST KISI", normalized_name="kisi test")
        contact = EmployeeContact(
            employee=employee, kind="email", value="test@example.invalid", source_document=document
        )
        queue_item = QueueItem(upload=upload, plan_item_id="i2", kind="unresolved", reason="R6")
        candidate = CandidateDocumentType(
            proposed_name="Test Card", normalized_name="test card", first_seen_upload=upload
        )
        user = User(username="ik", password_hash="hash", role="admin")
        telegram = TelegramUser(telegram_id=9_000_000_001, user=user)
        access = AccessLog(user=user, document=document, action="view", channel="web")
        event = Event(
            ts=ts,
            upload=upload,
            file=original,
            page_index=0,
            document=document,
            employee=employee,
            type="OUTPUT_SAVED",
        )
        session.add_all(
            [original, duplicate, *pages, plan_v1, identifier, alias, contact, queue_item]
        )
        session.add_all([candidate, telegram, access, event])
        session.commit()

    with create_session_factory(engine)() as session:
        employee = session.get_one(Employee, "E0001")
        assert [i.value for i in employee.identifiers] == ["T0000001"]
        assert [a.raw_name for a in employee.aliases] == ["TEST KISI"]
        assert [c.kind for c in employee.contacts] == ["email"]
        assert employee.date_of_birth == date(1990, 4, 12)

        document = employee.documents[0]
        assert document.employee is employee
        assert document.document_type.slug == "test_passport"
        assert document.plan is not None and document.plan.version == 2
        assert document.plan.documents == [document]
        assert employee.identifiers[0].source_document is document
        assert employee.contacts[0].source_document is document

        upload = session.get_one(Upload, "u_20260905_0001")
        assert upload.context_employee is employee
        assert [p.version for p in upload.plans] == [1, 2]
        assert all(p.upload is upload for p in upload.plans)
        assert [q.plan_item_id for q in upload.queue_items] == ["i2"]
        assert upload.queue_items[0].upload is upload

        original, duplicate = upload.files
        assert original.upload is upload
        assert duplicate.duplicate_of is original
        assert duplicate.is_duplicate_of == original.id
        assert [p.index for p in original.pages] == [0, 1]
        assert original.pages[0].file is original

        candidate = session.scalars(select(CandidateDocumentType)).one()
        assert candidate.first_seen_upload is upload

        user = session.scalars(select(User)).one()
        assert [t.telegram_id for t in user.telegram_accounts] == [9_000_000_001]
        assert user.telegram_accounts[0].user is user

        access = session.scalars(select(AccessLog)).one()
        assert access.user is user and access.document is document

        event = session.scalars(select(Event)).one()
        assert event.upload is upload and event.file is original
        assert event.document is document and event.employee is employee
        assert event.ts == ts


def test_defaults_are_applied(session: Session) -> None:
    employee = _employee()
    upload = Upload(id="u_20260905_0002", channel="web")
    doc_type = _document_type()
    session.add_all([employee, upload, doc_type])
    session.commit()

    assert employee.status == "active"
    assert employee.created_at.tzinfo is UTC
    assert upload.status == "received"
    assert doc_type.active is True
    assert doc_type.acceptance_criteria == []
    assert doc_type.allowed_conversions == []


def test_foreign_keys_are_enforced(session: Session) -> None:
    session.add(EmployeeAlias(employee_id="E9999", raw_name="YOK", normalized_name="yok"))
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    "build",
    [
        lambda: Upload(id="u_x", channel="web", status="bitti"),
        lambda: EmployeeContact(employee_id="E0001", kind="fax", value="1"),
        lambda: QueueItem(upload_id="u_ok", kind="hazir", reason="yanlış kuyruk"),
    ],
    ids=["upload-status", "contact-kind", "queue-kind"],
)
def test_check_constraints_reject_values_outside_the_prd_sets(session: Session, build) -> None:
    session.add_all([_employee(), Upload(id="u_ok", channel="web")])
    session.commit()

    session.add(build())
    with pytest.raises(IntegrityError):
        session.commit()


def test_plan_version_is_unique_per_upload(session: Session) -> None:
    session.add(Upload(id="u_1", channel="web"))
    session.add(Plan(upload_id="u_1", version=1, json={}, plan_hash="a" * 64))
    session.commit()

    session.add(Plan(upload_id="u_1", version=1, json={}, plan_hash="b" * 64))
    with pytest.raises(IntegrityError):
        session.commit()


def test_page_index_is_unique_per_file(session: Session) -> None:
    upload = Upload(id="u_1", channel="web")
    file = UploadFile(upload=upload, original_name="a.pdf", stored_path="a", sha256="a", mime="m")
    session.add_all([file, Page(file=file, index=0)])
    session.commit()

    session.add(Page(file=file, index=0))
    with pytest.raises(IntegrityError):
        session.commit()


def test_timestamps_are_stored_and_returned_as_utc(engine: Engine) -> None:
    istanbul = timezone(timedelta(hours=3))
    with create_session_factory(engine)() as session:
        employee = _employee()
        employee.created_at = datetime(2026, 9, 5, 12, 0, tzinfo=istanbul)
        session.add(employee)
        session.commit()

    with create_session_factory(engine)() as session:
        stored = session.get_one(Employee, "E0001").created_at
        assert stored == datetime(2026, 9, 5, 9, 0, tzinfo=UTC)
        assert stored.tzinfo is UTC


def test_naive_timestamp_is_rejected(session: Session) -> None:
    employee = _employee()
    employee.created_at = datetime(2026, 9, 5, 12, 0)
    session.add(employee)
    with pytest.raises(StatementError, match="Saat dilimsiz"):
        session.commit()
