"""00.5.1/00.5.2 — olay logu altyapısı ve olay bağlamı yöneticisi."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import Base, Event, Upload, UploadFile
from app.db.session import create_db_engine, create_session_factory
from app.events import EventType, event_context, record_event


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    db_engine = create_db_engine(f"sqlite:///{(tmp_path / 'events-test.db').as_posix()}")
    Base.metadata.create_all(db_engine)
    yield db_engine
    db_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with create_session_factory(engine)() as db_session:
        yield db_session


def test_all_prd_event_types_are_present() -> None:
    """PRD §8.3'teki olay türleri sabit listede olmalı, fazlası/eksiği olmamalı. PRD'nin
    eğitim modu olayları (`TRAINING_*`, 11.9) kendi görevleriyle eklendi: yerleştirme olayları
    tm 115'le, etiket, taşıma ve çıkarma olayları tm 119'la, harita olayı tm 120'yle; belge
    grubu olayı (`GROUP_CHANGED`, 14.1) tm 124'le; belge paketi olayları (`PACKAGE_*`, 14.2)
    tm 125'le; profil düzenleme olayı (`EMPLOYEE_EDITED`, 10.5.6) tm 126'yla; pasife alma ve
    yeniden etkinleştirme olayları (`EMPLOYEE_DEACTIVATED`, `EMPLOYEE_REACTIVATED`, 10.5.7) tm
    127'yle; profil alt kaydı olayları (`PROFILE_RECORD_REMOVED`, `PROFILE_RECORD_RESTORED`,
    `CONTACT_ADDED`, 10.5.8) tm 128'le."""
    expected = {
        "FILE_UPLOADED",
        "FILE_DUPLICATE",
        "PAGE_RENDERED",
        "PAGE_BLANK",
        "PAGE_ANALYZED",
        "PAGE_ANALYSIS_FAILED",
        "PAGE_UNREADABLE",
        "DOC_TYPE_DETERMINED",
        "DOC_TYPE_UNKNOWN",
        "CANDIDATE_TYPE_PROPOSED",
        "PERSON_IDENTIFIED",
        "PERSON_MATCHED",
        "PERSON_NOT_MATCHED",
        "PERSON_AMBIGUOUS",
        "EMPLOYEE_CREATED",
        "EMPLOYEE_PENDING",
        "EMPLOYEE_FIELD_FILLED",
        "PLAN_CREATED",
        "VALIDATION_FAILED",
        "DIRECT_DOC_CHECK",
        "PAGE_EXTRACTED",
        "PAGES_MERGED",
        "IMAGE_WRAPPED",
        "IMAGE_EXTRACTED",
        "IMAGE_RENDERED",
        "OUTPUT_SAVED",
        "OUTPUT_SKIPPED",
        "QUEUED_UNKNOWN",
        "QUEUED_UNREADABLE",
        "QUEUED_UNRESOLVED",
        "MANUAL_MOVE",
        "MANUAL_ASSIGN",
        "MANUAL_APPROVE",
        "TYPE_APPROVED",
        "TYPE_REJECTED",
        "USER_CONFIRMED",
        "PLAN_RERUN",
        "PLAN_REANALYZED",
        "ARCHIVED",
        "UPLOAD_DISMISSED",
        "PIPELINE_FAILED",
        "CANDIDATE_TYPE_EXAMINED",
        "TRAINING_EXAMPLE_PLACED",
        "TRAINING_ITEM_UNPLACED",
        "TRAINING_LABEL_VERIFIED",
        "TRAINING_EXAMPLE_MOVED",
        "TRAINING_EXAMPLE_REMOVED",
        "TRAINING_MAP_STARTED",
        "GROUP_CHANGED",
        "PACKAGE_ASSIGNED",
        "PACKAGE_COMPLETED",
        "PACKAGE_REOPENED",
        "PACKAGE_CANCELLED",
        "EMPLOYEE_EDITED",
        "EMPLOYEE_DEACTIVATED",
        "EMPLOYEE_REACTIVATED",
        "PROFILE_RECORD_REMOVED",
        "PROFILE_RECORD_RESTORED",
        "CONTACT_ADDED",
    }
    assert {member.value for member in EventType} == expected


def test_record_event_writes_row_to_database(session: Session) -> None:
    row = record_event(session, EventType.PIPELINE_FAILED, message="beklenmeyen hata")
    session.commit()

    stored = session.scalar(select(Event).where(Event.id == row.id))
    assert stored is not None
    assert stored.type == "PIPELINE_FAILED"
    assert stored.message == "beklenmeyen hata"
    assert stored.actor == "system"


def test_record_event_stores_explicit_fields_and_data(session: Session) -> None:
    session.add(Upload(id="U1", channel="web"))
    session.flush()

    row = record_event(
        session,
        EventType.FILE_UPLOADED,
        upload_id="U1",
        actor="ik@example.com",
        data={"size": 1024},
    )
    session.commit()

    stored = session.get(Event, row.id)
    assert stored is not None
    assert stored.upload_id == "U1"
    assert stored.actor == "ik@example.com"
    assert stored.data_json == {"size": 1024}


def test_event_context_carries_upload_and_file_and_page(session: Session) -> None:
    session.add(Upload(id="U1", channel="web"))
    session.flush()
    session.add(
        UploadFile(
            upload_id="U1",
            original_name="dosya.pdf",
            stored_path="Inbox/U1/dosya.pdf",
            sha256="0" * 64,
            mime="application/pdf",
        )
    )
    session.flush()
    file_row = session.scalar(select(UploadFile).where(UploadFile.upload_id == "U1"))
    assert file_row is not None

    with event_context(upload_id="U1", file_id=file_row.id, page_index=2):
        row = record_event(session, EventType.PAGE_RENDERED)
    session.commit()

    stored = session.get(Event, row.id)
    assert stored is not None
    assert stored.upload_id == "U1"
    assert stored.file_id == file_row.id
    assert stored.page_index == 2


def test_event_context_does_not_leak_outside_block(session: Session) -> None:
    session.add(Upload(id="U1", channel="web"))
    session.flush()

    with event_context(upload_id="U1", page_index=0):
        pass
    row = record_event(session, EventType.PIPELINE_FAILED)
    session.commit()

    stored = session.get(Event, row.id)
    assert stored is not None
    assert stored.upload_id is None
    assert stored.page_index is None


def test_event_context_explicit_argument_overrides_context(session: Session) -> None:
    session.add(Upload(id="U1", channel="web"))
    session.add(Upload(id="U2", channel="web"))
    session.flush()

    with event_context(upload_id="U1"):
        row = record_event(session, EventType.FILE_UPLOADED, upload_id="U2")
    session.commit()

    stored = session.get(Event, row.id)
    assert stored is not None
    assert stored.upload_id == "U2"


def test_event_context_nesting_inherits_unset_fields(session: Session) -> None:
    session.add(Upload(id="U1", channel="web"))
    session.flush()

    with event_context(upload_id="U1"):
        with event_context(page_index=5):
            row = record_event(session, EventType.PAGE_RENDERED)
    session.commit()

    stored = session.get(Event, row.id)
    assert stored is not None
    assert stored.upload_id == "U1"
    assert stored.page_index == 5
