"""10.5.10 — belgeyi arşivden geri alma: arşivdeki belge sahibinin `Hazir/`'ına K8 adıyla döner,
durumu etkin olur, içeriği ve kökeni değişmez; olay kullanıcı adıyla yazılır (K8, K11, K16, §D61).

Belgeler sentetiktir (bayt dizgesi); gerçek kimlik belgesi kullanılmaz.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

import app.groups
from app.db.models import (
    Base,
    Document,
    DocumentStatus,
    Employee,
    EmployeeStatus,
    Event,
    KnownDocumentType,
)
from app.db.session import create_db_engine, create_session_factory
from app.events import EventType
from app.profiles import render_profile
from app.storage import (
    DataLayout,
    DocumentNotFoundError,
    DocumentNotRestorableError,
    UnarchivedDocument,
    archive_document,
    prepare_data_dir,
    unarchive_document,
)

ACTOR = "ik.ayse"
TYPE_SLUG = "test_passport"
EMPLOYEE_ID = "E0001"
FOLDER = "Test_Kisi_E0001"
ARCHIVE_DAY = date(2026, 3, 5)
SOURCE_REFS = [{"file_id": 1, "pages": [0]}]


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine: Engine = create_db_engine(f"sqlite:///{(tmp_path / 'unarchive-test.db').as_posix()}")
    Base.metadata.create_all(engine)
    try:
        with create_session_factory(engine)() as db_session:
            yield db_session
    finally:
        engine.dispose()


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


@pytest.fixture
def employee(session: Session) -> Employee:
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
    sequence_no: int = 1,
    owner: str = EMPLOYEE_ID,
    folder: str = FOLDER,
) -> Document:
    directory = layout.ready_dir(folder)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(content)
    document = Document(
        employee_id=owner,
        type_slug=TYPE_SLUG,
        path=layout.relative(path),
        format="pdf",
        source_refs_json=SOURCE_REFS,
        status=status.value,
        sequence_no=sequence_no,
        plan_id=None,
    )
    session.add(document)
    session.flush()
    return document


def _archived(session: Session, layout: DataLayout, **kwargs: object) -> Document:
    document = _document(session, layout, **kwargs)  # type: ignore[arg-type]
    archive_document(session, layout, document.id, actor=ACTOR, today=ARCHIVE_DAY)
    return document


@pytest.mark.usefixtures("employee")
def test_the_archived_document_returns_to_hazir_under_its_k8_name(
    session: Session, layout: DataLayout
) -> None:
    document = _archived(session, layout, content=b"gizli icerik")
    archived_path = layout.resolve(document.path)
    archived_relative = document.path
    assert archived_path.parent == layout.archive_dir(ARCHIVE_DAY)

    restored = unarchive_document(session, layout, document.id, actor=ACTOR)

    assert isinstance(restored, UnarchivedDocument)
    assert restored.document is document
    assert document.status == DocumentStatus.ACTIVE.value
    new_path = layout.resolve(document.path)
    assert new_path == layout.ready_dir(FOLDER) / "Test_Kisi-Passport.pdf"
    # K11: içerik bayt bayt aynı; gerçek taşıma, arşivde kopya kalmaz.
    assert new_path.read_bytes() == b"gizli icerik"
    assert hashlib.sha256(new_path.read_bytes()).hexdigest() == (
        hashlib.sha256(b"gizli icerik").hexdigest()
    )
    assert not archived_path.exists()
    # Boş kalan ay dizini silinmez.
    assert layout.archive_dir(ARCHIVE_DAY).is_dir()
    # Köken ve sıra değişmez.
    assert document.source_refs_json == SOURCE_REFS
    assert document.sequence_no == 1
    assert (restored.previous_path, restored.previous_sequence_no) == (archived_relative, 1)

    event = restored.event
    assert event.type == EventType.UNARCHIVED
    assert (event.actor, event.document_id, event.employee_id) == (ACTOR, document.id, EMPLOYEE_ID)
    assert event.data_json == {
        "document_id": document.id,
        "from": archived_relative,
        "to": document.path,
        "previous_sequence_no": 1,
        "sequence_no": 1,
    }


@pytest.mark.usefixtures("employee")
def test_a_taken_name_gets_the_next_free_sequence_suffix(
    session: Session, layout: DataLayout
) -> None:
    document = _archived(session, layout, content=b"eski pasaport")
    # Arada aynı türden yeni belge geldi ve boşalan adı aldı.
    newer = _document(session, layout, content=b"yeni pasaport")

    restored = unarchive_document(session, layout, document.id, actor=ACTOR)

    assert layout.resolve(document.path).name == "Test_Kisi-Passport-2.pdf"
    assert layout.resolve(document.path).read_bytes() == b"eski pasaport"
    assert document.sequence_no == 2
    assert layout.resolve(newer.path).read_bytes() == b"yeni pasaport"  # üzerine yazılmadı
    assert restored.event.data_json["previous_sequence_no"] == 1
    assert restored.event.data_json["sequence_no"] == 2


@pytest.mark.usefixtures("employee")
def test_the_document_returns_to_its_own_suffix_when_it_is_free(
    session: Session, layout: DataLayout
) -> None:
    first = _archived(session, layout, content=b"birinci")
    second = _archived(
        session, layout, content=b"ikinci", name="Test_Kisi-Passport-2.pdf", sequence_no=2
    )

    unarchive_document(session, layout, second.id, actor=ACTOR)
    unarchive_document(session, layout, first.id, actor=ACTOR)

    # İkinci belge boş duran birinci eke kaymaz; ikisi de kendi ekine döner.
    assert layout.resolve(second.path).name == "Test_Kisi-Passport-2.pdf"
    assert layout.resolve(first.path).name == "Test_Kisi-Passport.pdf"
    assert (first.sequence_no, second.sequence_no) == (1, 2)


def test_the_name_follows_the_current_owner_after_a_merge(
    session: Session, layout: DataLayout, employee: Employee
) -> None:
    kept = Employee(id="E0002", folder_name="Kalan_Kisi_E0002", given_names="Kalan", surname="Kisi")
    session.add(kept)
    session.flush()
    document = _archived(session, layout)
    # 10.5.9: birleştirme arşivdeki belgeyi taşımaz, yalnız sahibini kalan kayda bağlar.
    employee.status = EmployeeStatus.MERGED.value
    document.employee_id = kept.id
    session.flush()

    unarchive_document(session, layout, document.id, actor=ACTOR)

    assert layout.resolve(document.path) == (
        layout.ready_dir("Kalan_Kisi_E0002") / "Kalan_Kisi-Passport.pdf"
    )
    assert not any(layout.ready_dir(FOLDER).iterdir())


@pytest.mark.usefixtures("employee")
def test_the_owners_profile_is_regenerated(session: Session, layout: DataLayout) -> None:
    document = _archived(session, layout)
    profile = layout.profile_path(FOLDER)
    profile.write_text("bayat profil", encoding="utf-8")

    unarchive_document(session, layout, document.id, actor=ACTOR)

    text = profile.read_text(encoding="utf-8")
    assert text == render_profile(session, session.get_one(Employee, EMPLOYEE_ID))
    assert "| Test Passport | Test_Kisi-Passport.pdf | active |" in text


@pytest.mark.usefixtures("employee")
@pytest.mark.parametrize(
    "status", [DocumentStatus.ACTIVE, DocumentStatus.SUPERSEDED], ids=["active", "superseded"]
)
def test_only_an_archived_document_is_restored(
    session: Session, layout: DataLayout, status: DocumentStatus
) -> None:
    document = _document(session, layout, status=status)
    before = layout.resolve(document.path)

    with pytest.raises(DocumentNotRestorableError, match="yalnız arşivdeki belge"):
        unarchive_document(session, layout, document.id, actor=ACTOR)

    assert document.status == status.value
    assert before.read_bytes() == b"belge icerigi"
    assert session.scalars(select(Event).where(Event.type == "UNARCHIVED")).all() == []


def test_a_missing_document_is_reported(session: Session, layout: DataLayout) -> None:
    with pytest.raises(DocumentNotFoundError):
        unarchive_document(session, layout, 404, actor=ACTOR)


@pytest.mark.usefixtures("employee")
def test_the_user_name_is_required(session: Session, layout: DataLayout) -> None:
    document = _archived(session, layout)
    archived_path = layout.resolve(document.path)

    with pytest.raises(ValueError, match="actor"):
        unarchive_document(session, layout, document.id, actor="  ")

    assert archived_path.exists()
    assert document.status == DocumentStatus.ARCHIVED.value


def test_a_merged_owner_is_refused(
    session: Session, layout: DataLayout, employee: Employee
) -> None:
    document = _archived(session, layout)
    employee.status = EmployeeStatus.MERGED.value
    session.flush()

    with pytest.raises(DocumentNotRestorableError, match="birleştirildi"):
        unarchive_document(session, layout, document.id, actor=ACTOR)

    assert layout.resolve(document.path).exists()
    assert not any(layout.ready_dir(FOLDER).iterdir())


@pytest.mark.usefixtures("employee")
def test_a_missing_archive_file_is_refused(session: Session, layout: DataLayout) -> None:
    document = _archived(session, layout)
    layout.resolve(document.path).unlink()
    archived_relative = document.path

    with pytest.raises(DocumentNotRestorableError, match="arşivde bulunamadı"):
        unarchive_document(session, layout, document.id, actor=ACTOR)

    assert (document.status, document.path) == (DocumentStatus.ARCHIVED.value, archived_relative)


@pytest.mark.usefixtures("employee")
def test_an_unreadable_extension_or_outside_path_is_refused(
    session: Session, layout: DataLayout
) -> None:
    document = _archived(session, layout)
    archived = layout.resolve(document.path)
    odd = archived.with_name("uzantisiz")
    archived.rename(odd)
    document.path = layout.relative(odd)
    session.flush()
    with pytest.raises(DocumentNotRestorableError, match="uzantısı"):
        unarchive_document(session, layout, document.id, actor=ACTOR)

    document.path = "../disarida.pdf"
    session.flush()
    with pytest.raises(DocumentNotRestorableError, match="veri dizininin dışında"):
        unarchive_document(session, layout, document.id, actor=ACTOR)
    assert not any(layout.ready_dir(FOLDER).iterdir())


@pytest.mark.usefixtures("employee")
def test_a_failure_after_publishing_leaves_the_archive_file_in_place(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = _archived(session, layout)
    session.commit()
    archived_path = layout.resolve(document.path)

    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("paket yenilenemedi")

    monkeypatch.setattr(app.groups, "refresh_employee_packages", broken)
    with pytest.raises(RuntimeError, match="paket yenilenemedi"):
        unarchive_document(session, layout, document.id, actor=ACTOR)
    session.rollback()

    assert archived_path.read_bytes() == b"belge icerigi"
    assert not any(layout.ready_dir(FOLDER).iterdir())  # yayınlanan kopya kaldırıldı
    restored = session.get_one(Document, document.id)
    assert restored.status == DocumentStatus.ARCHIVED.value


@pytest.mark.usefixtures("employee")
def test_the_transaction_is_left_to_the_caller(session: Session, layout: DataLayout) -> None:
    document = _archived(session, layout)
    session.commit()

    unarchive_document(session, layout, document.id, actor=ACTOR)
    session.rollback()

    assert session.get_one(Document, document.id).status == DocumentStatus.ARCHIVED.value
