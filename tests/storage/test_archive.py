"""08.4.1 — belgeyi arşive taşıma: belge silinmez, `Archive/<yyyy-mm>/` altına taşınır ve durumu
güncellenir (K11, K16, R11)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import Base, Document, DocumentStatus, Employee, Event, KnownDocumentType
from app.db.session import create_db_engine, create_session_factory
from app.events import EventType
from app.storage import (
    ArchivedDocument,
    DataLayout,
    DocumentNotArchivableError,
    DocumentNotFoundError,
    archive_document,
    prepare_data_dir,
)

ACTOR = "ik.ayse"
TYPE_SLUG = "test_passport"
EMPLOYEE_ID = "E0001"
FOLDER = "Test_Kisi_E0001"


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine: Engine = create_db_engine(f"sqlite:///{(tmp_path / 'archive-test.db').as_posix()}")
    Base.metadata.create_all(engine)
    try:
        with create_session_factory(engine)() as db_session:
            yield db_session
    finally:
        engine.dispose()


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


def _employee(session: Session) -> Employee:
    employee = Employee(id=EMPLOYEE_ID, folder_name=FOLDER, given_names="Test", surname="Kisi")
    session.add(employee)
    session.add(
        KnownDocumentType(
            slug=TYPE_SLUG,
            name="Test Passport",
            file_label="Passport",
            sides="single",
            direct=True,
            analyze=True,
            output_format="keep",
        )
    )
    session.flush()
    return employee


def _document(
    session: Session,
    layout: DataLayout,
    *,
    content: bytes = b"belge icerigi",
    status: DocumentStatus = DocumentStatus.ACTIVE,
    name: str = "Test_Kisi-Passport.pdf",
) -> Document:
    directory = layout.ready_dir(FOLDER)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(content)
    document = Document(
        employee_id=EMPLOYEE_ID,
        type_slug=TYPE_SLUG,
        path=layout.relative(path),
        format="pdf",
        source_refs_json=[{"file_id": 1, "pages": [0]}],
        status=status.value,
    )
    session.add(document)
    session.flush()
    return document


def test_archives_the_active_document_and_moves_it_off_disk(
    session: Session, layout: DataLayout
) -> None:
    _employee(session)
    document = _document(session, layout, content=b"gizli icerik")
    source = layout.resolve(document.path)
    assert source.exists()

    archived = archive_document(session, layout, document.id, actor=ACTOR, today=date(2026, 3, 5))

    assert isinstance(archived, ArchivedDocument)
    assert archived.document is document
    assert document.status == DocumentStatus.ARCHIVED.value
    new_path = layout.resolve(document.path)
    assert new_path == layout.archive_dir(date(2026, 3, 5)) / "Test_Kisi-Passport.pdf"
    assert new_path.read_bytes() == b"gizli icerik"
    assert not source.exists()  # K11: gerçek taşıma, kopya bırakılmaz.

    assert archived.event.type == EventType.ARCHIVED
    assert (archived.event.actor, archived.event.document_id, archived.event.employee_id) == (
        ACTOR,
        document.id,
        EMPLOYEE_ID,
    )
    assert archived.event.data_json == {"document_id": document.id, "path": document.path}


def test_document_not_found_is_reported(session: Session, layout: DataLayout) -> None:
    with pytest.raises(DocumentNotFoundError):
        archive_document(session, layout, 999, actor=ACTOR)


@pytest.mark.parametrize(
    "status",
    [DocumentStatus.SUPERSEDED, DocumentStatus.ARCHIVED],
    ids=["superseded", "already-archived"],
)
def test_non_active_document_cannot_be_archived(
    session: Session, layout: DataLayout, status: DocumentStatus
) -> None:
    _employee(session)
    document = _document(session, layout, status=status)
    source = layout.resolve(document.path)

    with pytest.raises(DocumentNotArchivableError, match="yalnız etkin belge arşivlenir"):
        archive_document(session, layout, document.id, actor=ACTOR)

    assert document.status == status.value
    assert source.exists()
    assert session.scalars(select(Event).where(Event.type == EventType.ARCHIVED)).all() == []


def test_archiving_twice_is_refused(session: Session, layout: DataLayout) -> None:
    _employee(session)
    document = _document(session, layout)

    archive_document(session, layout, document.id, actor=ACTOR)

    with pytest.raises(DocumentNotArchivableError, match="yalnız etkin belge arşivlenir"):
        archive_document(session, layout, document.id, actor=ACTOR)


@pytest.mark.parametrize("actor", ["", "   "])
def test_manual_archiving_needs_the_user_name(
    session: Session, layout: DataLayout, actor: str
) -> None:
    _employee(session)
    document = _document(session, layout)
    source = layout.resolve(document.path)

    with pytest.raises(ValueError, match="K16"):
        archive_document(session, layout, document.id, actor=actor)

    assert document.status == DocumentStatus.ACTIVE.value
    assert source.exists()


def test_archiving_leaves_the_transaction_to_the_caller(
    session: Session, layout: DataLayout
) -> None:
    _employee(session)
    document = _document(session, layout)
    session.commit()

    archive_document(session, layout, document.id, actor=ACTOR)
    session.rollback()

    assert session.get_one(Document, document.id).status == DocumentStatus.ACTIVE.value
    assert session.scalars(select(Event).where(Event.type == EventType.ARCHIVED)).all() == []
