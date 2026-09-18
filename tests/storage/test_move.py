"""10.8.2 — belgeyi başka çalışana taşıma: dosya yeni sahibin K8 adıyla onun `Hazir/`'ına taşınır,
içerik bayt bayt aynı kalır, kaynak orijinal yeni sahibin `Alinan/`'ına kopyalanır ve `MANUAL_MOVE`
kullanıcı adıyla loglanır (K8, K10, K11, K16).

Veriler sentetiktir: çalışanlar, tür, yükleme dosyası (Inbox'ta gerçek baytlarla) ve çıktı satırı
elle yazılır. Gerçek kimlik belgesi kullanılmaz.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import (
    Base,
    Document,
    DocumentStatus,
    Employee,
    Event,
    KnownDocumentType,
    Upload,
    UploadFile,
)
from app.db.session import create_db_engine, create_session_factory
from app.events import EventType
from app.storage import (
    DataLayout,
    DocumentNotFoundError,
    DocumentNotMovableError,
    MovedDocument,
    MoveTargetNotFoundError,
    move_document,
    prepare_data_dir,
)

ACTOR = "ik.ayse"
TYPE_SLUG = "test_passport"
OWNER, OWNER_FOLDER = "E0001", "Eski_Sahip_E0001"
TARGET, TARGET_FOLDER = "E0002", "Yeni_Sahip_E0002"
UPLOAD_ID = "u_tasima1"
CONTENT = b"%PDF-1.4 cikti belgesi"
ORIGINAL = b"%PDF-1.4 yuklenen orijinal"


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine: Engine = create_db_engine(f"sqlite:///{(tmp_path / 'move-test.db').as_posix()}")
    Base.metadata.create_all(engine)
    try:
        with create_session_factory(engine)() as db_session:
            yield db_session
    finally:
        engine.dispose()


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


def _employees(session: Session, layout: DataLayout) -> None:
    session.add(Employee(id=OWNER, folder_name=OWNER_FOLDER, given_names="Eski", surname="Sahip"))
    session.add(Employee(id=TARGET, folder_name=TARGET_FOLDER, given_names="Yeni", surname="Sahip"))
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
    session.add(Upload(id=UPLOAD_ID, channel="web"))
    session.flush()
    layout.ensure_employee_tree(OWNER_FOLDER)


def _source(
    session: Session, layout: DataLayout, name: str = "tarama.pdf", content: bytes = ORIGINAL
) -> UploadFile:
    """Inbox'ta gerçek baytları olan yükleme dosyası (K10: SHA-256 yüklemede kaydedilir)."""
    directory = layout.upload_inbox_dir(UPLOAD_ID)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(content)
    upload_file = UploadFile(
        upload_id=UPLOAD_ID,
        original_name=name,
        stored_path=layout.relative(path),
        sha256=hashlib.sha256(content).hexdigest(),
        mime="application/pdf",
        page_count=2,
    )
    session.add(upload_file)
    session.flush()
    return upload_file


def _document(
    session: Session,
    layout: DataLayout,
    refs: Any,
    *,
    name: str = "Eski_Sahip-Passport.pdf",
    status: DocumentStatus = DocumentStatus.ACTIVE,
    owner: str = OWNER,
    folder: str = OWNER_FOLDER,
) -> Document:
    directory = layout.ensure_employee_tree(folder) / "Hazir"
    path = directory / name
    path.write_bytes(CONTENT)
    document = Document(
        employee_id=owner,
        type_slug=TYPE_SLUG,
        path=layout.relative(path),
        format=path.suffix.removeprefix("."),
        source_refs_json=refs,
        status=status.value,
    )
    session.add(document)
    session.flush()
    return document


@pytest.fixture
def document(session: Session, layout: DataLayout) -> Document:
    _employees(session, layout)
    source = _source(session, layout)
    return _document(session, layout, [{"file_id": source.id, "pages": [1]}])


def _move(session: Session, layout: DataLayout, document_id: int) -> MovedDocument:
    return move_document(session, layout, document_id, TARGET, actor=ACTOR)


def _file_name(relative: str) -> str:
    return Path(relative).name


def _events(session: Session) -> list[Event]:
    return list(session.scalars(select(Event).where(Event.type == EventType.MANUAL_MOVE)))


# --- taşıma ---------------------------------------------------------------------------------------


def test_the_file_moves_under_the_new_owners_k8_name_with_the_same_bytes(
    session: Session, layout: DataLayout, document: Document
) -> None:
    old_path = layout.resolve(document.path)
    created_at, plan_id, refs = document.created_at, document.plan_id, document.source_refs_json

    moved = _move(session, layout, document.id)

    new_path = layout.ready_dir(TARGET_FOLDER) / "Yeni_Sahip-Passport.pdf"
    assert layout.resolve(moved.document.path) == new_path
    assert new_path.read_bytes() == CONTENT  # K11: yalnız yeniden adlandırma ve taşıma
    assert not old_path.exists()  # kopya bırakılmaz
    assert list(layout.ready_dir(OWNER_FOLDER).iterdir()) == []
    row = session.get_one(Document, document.id)
    assert (row.employee_id, row.sequence_no, row.status) == (TARGET, 1, "active")
    # Satır aynı kalır: kimliği, türü, biçimi, kökeni ve oluşturulma anı değişmez.
    assert (row.type_slug, row.format, row.plan_id, row.created_at) == (
        TYPE_SLUG,
        "pdf",
        plan_id,
        created_at,
    )
    assert row.source_refs_json == refs
    assert (moved.previous_owner.id, moved.new_owner.id) == (OWNER, TARGET)


def test_the_source_original_is_copied_to_the_new_owners_received_folder(
    session: Session, layout: DataLayout, document: Document
) -> None:
    old_received = layout.received_dir(OWNER_FOLDER) / "tarama.pdf"
    old_received.write_bytes(ORIGINAL)

    moved = _move(session, layout, document.id)

    (copy,) = moved.received
    assert copy.copied is True
    assert copy.stored.path == layout.received_dir(TARGET_FOLDER) / "tarama.pdf"
    assert copy.stored.path.read_bytes() == ORIGINAL
    # Eski sahibin Alinan kopyası silinmez (K16: silme yok).
    assert old_received.read_bytes() == ORIGINAL


def test_the_same_original_already_received_is_not_copied_again(
    session: Session, layout: DataLayout, document: Document
) -> None:
    layout.ensure_employee_tree(TARGET_FOLDER)
    (layout.received_dir(TARGET_FOLDER) / "onceki-ad.pdf").write_bytes(ORIGINAL)

    moved = _move(session, layout, document.id)

    (copy,) = moved.received
    assert copy.copied is False
    assert sorted(p.name for p in layout.received_dir(TARGET_FOLDER).iterdir()) == ["onceki-ad.pdf"]


def test_a_taken_name_gets_the_next_k8_suffix(
    session: Session, layout: DataLayout, document: Document
) -> None:
    layout.ensure_employee_tree(TARGET_FOLDER)
    taken = layout.ready_dir(TARGET_FOLDER) / "Yeni_Sahip-Passport.pdf"
    taken.write_bytes(b"yeni sahibin kendi pasaportu")

    moved = _move(session, layout, document.id)

    assert _file_name(moved.document.path) == "Yeni_Sahip-Passport-2.pdf"
    assert moved.document.sequence_no == 2
    assert taken.read_bytes() == b"yeni sahibin kendi pasaportu"  # üzerine yazılmaz


def test_the_extension_of_the_moved_file_is_kept(session: Session, layout: DataLayout) -> None:
    _employees(session, layout)
    source = _source(session, layout, "foto.jpg", b"\xff\xd8\xff jpeg")
    photo = _document(
        session, layout, [{"file_id": source.id, "pages": []}], name="Eski_Sahip-Passport.jpg"
    )

    moved = _move(session, layout, photo.id)

    assert _file_name(moved.document.path) == "Yeni_Sahip-Passport.jpg"
    assert moved.document.format == "jpg"


def test_manual_move_is_logged_with_the_user_and_both_employees_but_no_names(
    session: Session, layout: DataLayout, document: Document
) -> None:
    moved = _move(session, layout, document.id)

    (event,) = _events(session)
    assert event is moved.event
    assert event.actor == ACTOR
    assert (event.document_id, event.employee_id) == (document.id, TARGET)
    (source_id,) = [ref["file_id"] for ref in document.source_refs_json]
    assert (event.upload_id, event.file_id, event.page_index) == (UPLOAD_ID, source_id, 1)
    assert event.data_json == {
        "document_id": document.id,
        "from_employee_id": OWNER,
        "to_employee_id": TARGET,
        "document_type_slug": TYPE_SLUG,
        "sequence_no": 1,
        "sha256": hashlib.sha256(CONTENT).hexdigest(),
        "received": [{"file_id": source_id, "copied": True}],
    }
    # Yol ve ad kişi adı taşır; olaya girmez (CONVENTIONS §6).
    assert "Sahip" not in str(event.data_json) and event.message is None


def test_a_source_listed_twice_is_copied_once_and_empty_refs_copy_nothing(
    session: Session, layout: DataLayout
) -> None:
    _employees(session, layout)
    source = _source(session, layout)
    twice = _document(
        session,
        layout,
        [{"file_id": source.id, "pages": [0]}, {"file_id": source.id, "pages": [1]}],
    )
    bare = _document(session, layout, [], name="Eski_Sahip-Passport-2.pdf")

    first = _move(session, layout, twice.id)
    second = _move(session, layout, bare.id)

    assert len(first.received) == 1
    assert second.received == ()
    assert (second.event.upload_id, second.event.file_id) == (None, None)
    assert _file_name(second.document.path) == "Yeni_Sahip-Passport-2.pdf"


# --- ret: hiçbir şey taşınmaz ---------------------------------------------------------------------


def _untouched(session: Session, layout: DataLayout, document: Document) -> None:
    session.rollback()
    row = session.get_one(Document, document.id)
    assert row.employee_id == OWNER
    assert layout.resolve(row.path).read_bytes() == CONTENT
    target_ready = layout.ready_dir(TARGET_FOLDER)
    assert not target_ready.exists() or list(target_ready.iterdir()) == []
    assert _events(session) == []


@pytest.mark.parametrize("status", [DocumentStatus.SUPERSEDED, DocumentStatus.ARCHIVED])
def test_only_an_active_document_is_moved(
    session: Session, layout: DataLayout, status: DocumentStatus
) -> None:
    _employees(session, layout)
    source = _source(session, layout)
    document = _document(session, layout, [{"file_id": source.id, "pages": [0]}], status=status)
    session.commit()

    with pytest.raises(DocumentNotMovableError, match="yalnız etkin belge"):
        _move(session, layout, document.id)
    _untouched(session, layout, document)


def test_the_current_owner_is_not_a_move_target(
    session: Session, layout: DataLayout, document: Document
) -> None:
    session.commit()

    with pytest.raises(DocumentNotMovableError, match=f"zaten {OWNER}"):
        move_document(session, layout, document.id, OWNER, actor=ACTOR)
    _untouched(session, layout, document)


def test_unknown_document_or_employee_is_not_found(
    session: Session, layout: DataLayout, document: Document
) -> None:
    session.commit()

    with pytest.raises(DocumentNotFoundError):
        _move(session, layout, document.id + 100)
    with pytest.raises(MoveTargetNotFoundError):
        move_document(session, layout, document.id, "E9999", actor=ACTOR)
    _untouched(session, layout, document)


def test_an_empty_actor_is_refused(
    session: Session, layout: DataLayout, document: Document
) -> None:
    session.commit()

    with pytest.raises(ValueError, match="actor"):
        move_document(session, layout, document.id, TARGET, actor="  ")
    _untouched(session, layout, document)


def test_a_missing_file_or_a_path_outside_the_data_dir_is_refused(
    session: Session, layout: DataLayout, document: Document
) -> None:
    session.commit()
    path = layout.resolve(document.path)
    path.unlink()

    with pytest.raises(DocumentNotMovableError, match="dosyası bulunamadı"):
        _move(session, layout, document.id)

    path.write_bytes(CONTENT)
    session.get_one(Document, document.id).path = "../disarida.pdf"
    session.commit()
    with pytest.raises(DocumentNotMovableError, match="veri dizininin dışında"):
        _move(session, layout, document.id)
    assert _events(session) == []


def test_a_file_name_without_an_extension_is_refused(session: Session, layout: DataLayout) -> None:
    _employees(session, layout)
    source = _source(session, layout)
    document = _document(
        session, layout, [{"file_id": source.id, "pages": [0]}], name="Eski_Sahip-Passport"
    )
    session.commit()

    with pytest.raises(DocumentNotMovableError, match="uzantısı"):
        _move(session, layout, document.id)
    _untouched(session, layout, document)


def test_a_changed_or_missing_source_original_is_refused_before_anything_moves(
    session: Session, layout: DataLayout, document: Document
) -> None:
    session.commit()
    (ref,) = document.source_refs_json
    original = layout.resolve(session.get_one(UploadFile, ref["file_id"]).stored_path)
    original.write_bytes(b"degistirildi")

    with pytest.raises(DocumentNotMovableError, match="SHA-256"):
        _move(session, layout, document.id)
    _untouched(session, layout, document)
    assert not layout.received_dir(TARGET_FOLDER).exists()

    original.unlink()
    with pytest.raises(DocumentNotMovableError, match="SHA-256"):
        _move(session, layout, document.id)
    _untouched(session, layout, document)


@pytest.mark.parametrize(
    "refs",
    [
        {"file_id": 1},
        ["bozuk"],
        [{"file_id": "1", "pages": [0]}],
        [{"file_id": 1, "pages": [True]}],
        [{"file_id": 999, "pages": [0]}],
    ],
    ids=["not-a-list", "not-a-dict", "text-id", "bool-page", "unknown-file"],
)
def test_a_broken_source_record_is_refused(session: Session, layout: DataLayout, refs: Any) -> None:
    _employees(session, layout)
    _source(session, layout)
    document = _document(session, layout, refs)
    session.commit()

    with pytest.raises(DocumentNotMovableError, match="köken kaydı bozuk|kaynak dosya kaydı"):
        _move(session, layout, document.id)
    _untouched(session, layout, document)


def test_a_source_path_outside_the_data_dir_is_refused(
    session: Session, layout: DataLayout, document: Document
) -> None:
    (ref,) = document.source_refs_json
    session.get_one(UploadFile, ref["file_id"]).stored_path = "../disarida.pdf"
    session.commit()

    with pytest.raises(DocumentNotMovableError, match="SHA-256"):
        _move(session, layout, document.id)
    _untouched(session, layout, document)
