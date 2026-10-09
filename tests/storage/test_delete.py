"""10.5.12 — belgeyi kalıcı silme çekirdeği: hangi dosya gider, hangisi kalır; iskelet kayıt,
`DOCUMENT_DELETED` ve dosyaların commit'ten sonra kaldırılması (K10, K15, K16, R11; PLAN.md
§D110 a, b, g; §D113).

Veriler sentetiktir: çalışanlar, tür, partiler (Inbox'ta gerçek baytlarla), sayfa görüntüleri,
çıktı satırları, Alinan ve kuyruk kopyaları elle yazılır. Gerçek kimlik belgesi kullanılmaz.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import (
    Base,
    Document,
    DocumentGroup,
    DocumentStatus,
    Employee,
    EmployeePackage,
    Event,
    KnownDocumentType,
    PackageStatus,
    Page,
    Plan,
    QueueItem,
    Upload,
    UploadFile,
    UploadStatus,
)
from app.db.session import create_db_engine, create_session_factory
from app.events import EventType, record_event
from app.groups import add_item, assign_package, create_group
from app.storage import (
    DataLayout,
    DeletedDocument,
    DeletionChangedError,
    DocumentNotDeletableError,
    DocumentNotFoundError,
    archive_document,
    copy_to_received,
    delete_document,
    plan_document_deletion,
    prepare_data_dir,
    remove_document_files,
)
from app.storage.delete import FileRole

ACTOR = "ik.ayse"
TYPE_SLUG = "test_passport"
OWNER, OWNER_FOLDER = "E0001", "Test_Kisi_E0001"
OTHER, OTHER_FOLDER = "E0002", "Baska_Kisi_E0002"
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
# Kişisel değer: sayfa metin katmanı ve analizinde durur, silmeden sonra hiçbir yerde kalmamalı.
PERSON = "TESTOVA SAMPLE"


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine: Engine = create_db_engine(f"sqlite:///{(tmp_path / 'delete-test.db').as_posix()}")
    Base.metadata.create_all(engine)
    try:
        with create_session_factory(engine)() as db_session:
            yield db_session
    finally:
        engine.dispose()


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


@pytest.fixture(autouse=True)
def _world(session: Session, layout: DataLayout) -> None:
    session.add(Employee(id=OWNER, folder_name=OWNER_FOLDER, given_names="Test", surname="Kisi"))
    session.add(Employee(id=OTHER, folder_name=OTHER_FOLDER, given_names="Baska", surname="Kisi"))
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
    layout.ensure_employee_tree(OWNER_FOLDER)
    layout.ensure_employee_tree(OTHER_FOLDER)


def _upload(
    session: Session,
    layout: DataLayout,
    upload_id: str,
    content: bytes,
    *,
    pages: int = 2,
    status: UploadStatus = UploadStatus.DONE,
    duplicate_of: UploadFile | None = None,
) -> UploadFile:
    """Inbox'ta gerçek baytlarıyla yüklenen dosya, planı ve (tekrar değilse) sayfa görüntüleri."""
    session.add(Upload(id=upload_id, channel="web", status=status.value))
    session.add(Plan(upload_id=upload_id, version=1, json={}, plan_hash=upload_id))
    directory = layout.upload_inbox_dir(upload_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "tarama.pdf"
    path.write_bytes(content)
    upload_file = UploadFile(
        upload_id=upload_id,
        original_name="tarama.pdf",
        stored_path=layout.relative(path),
        sha256=hashlib.sha256(content).hexdigest(),
        mime="application/pdf",
        page_count=pages,
        is_duplicate_of=duplicate_of.id if duplicate_of is not None else None,
    )
    session.add(upload_file)
    session.flush()
    if duplicate_of is None:
        for index in range(pages):
            image = layout.page_image_path(upload_file.id, index)
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(b"jpeg " + content + bytes([index]))
            session.add(
                Page(
                    file_id=upload_file.id,
                    index=index,
                    image_path=layout.relative(image),
                    text_layer=f"{PERSON} sayfa {index}",
                    analysis_json={"person": {"surname": PERSON}},
                    analysis_status="done",
                )
            )
        session.flush()
    return upload_file


def _plan_id(session: Session, upload_id: str) -> int:
    return session.scalars(select(Plan.id).where(Plan.upload_id == upload_id)).one()


def _document(
    session: Session,
    layout: DataLayout,
    source: UploadFile,
    pages: list[int],
    *,
    name: str,
    owner: str = OWNER,
    folder: str = OWNER_FOLDER,
    status: DocumentStatus = DocumentStatus.ACTIVE,
    received: bool = True,
) -> Document:
    """Çıktı satırı, `Hazir/`'daki dosyası ve (istenirse) kaynağın Alinan kopyası."""
    path = layout.ready_dir(folder) / name
    path.write_bytes(b"%PDF cikti " + name.encode())
    document = Document(
        employee_id=owner,
        type_slug=TYPE_SLUG,
        path=layout.relative(path),
        format="pdf",
        plan_id=_plan_id(session, source.upload_id),
        source_refs_json=[{"file_id": source.id, "pages": pages}],
        status=status.value,
    )
    session.add(document)
    session.flush()
    if received:
        inbox = layout.resolve(source.stored_path)
        copy_to_received(layout, folder, inbox, sha256=source.sha256)
    return document


def _queue_item(
    session: Session,
    layout: DataLayout,
    source: UploadFile,
    pages: list[int],
    *,
    resolved: bool = False,
) -> QueueItem:
    """Aynı dosyanın sayfasından kuyruk öğesi ve `Unresolved/<parti>/` kopyası."""
    directory = layout.queue_dir("unresolved", source.upload_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "tarama.pdf").write_bytes(layout.resolve(source.stored_path).read_bytes())
    (directory / "reason.json").write_text("{}", encoding="utf-8")
    item = QueueItem(
        upload_id=source.upload_id,
        plan_id=_plan_id(session, source.upload_id),
        plan_item_id="i9",
        kind="unresolved",
        reason="sentetik",
        payload_json={"sources": [{"file_id": source.id, "pages": pages}]},
        resolved_at=NOW if resolved else None,
        resolved_by=ACTOR if resolved else None,
    )
    session.add(item)
    session.flush()
    return item


def _delete(session: Session, layout: DataLayout, document: Document) -> DeletedDocument:
    deleted = delete_document(session, layout, document.id, actor=ACTOR, now=NOW)
    session.commit()
    assert remove_document_files(session, deleted) == 0
    session.commit()
    return deleted


def _received_files(layout: DataLayout, folder: str = OWNER_FOLDER) -> list[str]:
    return sorted(path.name for path in layout.received_dir(folder).iterdir())


def _roles(files: Any) -> list[str]:
    return sorted(planned.role.value for planned in files)


def _page(session: Session, source: UploadFile, index: int) -> Page:
    return session.scalars(
        select(Page)
        .where(Page.file_id == source.id, Page.index == index)
        .execution_options(populate_existing=True)
    ).one()


# --- tek kaynaklı belge -------------------------------------------------------------------------


def test_a_single_source_document_takes_its_file_copy_original_and_pages_with_it(
    session: Session, layout: DataLayout
) -> None:
    source = _upload(session, layout, "u_tek", b"%PDF tek kaynak", pages=1)
    document = _document(session, layout, source, [], name="Test_Kisi-Passport.pdf")
    output = layout.resolve(document.path)
    inbox = layout.resolve(source.stored_path)
    image = layout.resolve(_page(session, source, 0).image_path)
    session.commit()

    plan = plan_document_deletion(session, layout, document)
    assert _roles(plan.remove) == ["document", "inbox", "received"]
    assert plan.counts == (3, 0)
    assert [page.image for page in plan.pages] == [image]

    _delete(session, layout, document)

    for path in (output, inbox, image):
        assert not path.exists()
    assert _received_files(layout) == []
    page = _page(session, source, 0)
    assert (page.image_path, page.analysis_json, page.text_layer) == (None, None, None)


def test_the_row_stays_as_a_skeleton_with_who_and_when(
    session: Session, layout: DataLayout
) -> None:
    source = _upload(session, layout, "u_iskelet", b"%PDF iskelet", pages=1)
    document = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    created_at, sequence_no = document.created_at, document.sequence_no
    session.commit()

    _delete(session, layout, document)

    row = session.get_one(Document, document.id, populate_existing=True)
    assert row.status == DocumentStatus.DELETED.value
    assert row.path is None
    assert (row.deleted_at, row.deleted_by) == (NOW, ACTOR)
    assert (row.employee_id, row.type_slug, row.created_at) == (OWNER, TYPE_SLUG, created_at)
    assert row.sequence_no == sequence_no
    assert row.source_refs_json == [{"file_id": source.id, "pages": [0]}]  # köken kalır (K15)


def test_the_event_carries_only_ids_and_counts_and_the_user_name(
    session: Session, layout: DataLayout
) -> None:
    source = _upload(session, layout, "u_olay", b"%PDF olay", pages=1)
    document = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    record_event(session, EventType.OUTPUT_SAVED, document_id=document.id, employee_id=OWNER)
    session.commit()

    _delete(session, layout, document)

    (event,) = session.scalars(select(Event).where(Event.type == "DOCUMENT_DELETED")).all()
    assert (event.actor, event.document_id, event.employee_id) == (ACTOR, document.id, OWNER)
    assert event.data_json == {
        "document_id": document.id,
        "document_type_slug": TYPE_SLUG,
        "previous_status": "active",
        "files_deleted": 3,
        "files_kept": 0,
        "pages_cleared": 1,
    }
    assert event.message is None
    # K15: önceki olay satırları silinmez.
    types = [row.type for row in session.scalars(select(Event).order_by(Event.id))]
    assert types == ["OUTPUT_SAVED", "DOCUMENT_DELETED"]


# --- ortak kaynak: aynı PDF'ten birden çok belge ------------------------------------------------


def test_two_documents_from_one_pdf_keep_the_original_until_the_last_one_goes(
    session: Session, layout: DataLayout
) -> None:
    # S3/S4: aynı yüklemeden iki belge; ilki silinince orijinal ve Alinan kalır, ikincisiyle gider.
    source = _upload(session, layout, "u_ortak", b"%PDF iki belge")
    first = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    second = _document(session, layout, source, [1], name="Test_Kisi-Passport-2.pdf")
    inbox = layout.resolve(source.stored_path)
    session.commit()

    plan = plan_document_deletion(session, layout, first)
    assert _roles(plan.remove) == ["document"]
    assert _roles(plan.keep) == ["inbox", "received"]
    assert plan.counts == (1, 2)
    _delete(session, layout, first)

    assert inbox.exists() and _received_files(layout) == ["tarama.pdf"]
    assert _page(session, source, 0).analysis_json is None
    assert _page(session, source, 1).analysis_json == {"person": {"surname": PERSON}}

    assert plan_document_deletion(session, layout, second).counts == (3, 0)
    _delete(session, layout, second)

    assert not inbox.exists() and _received_files(layout) == []
    assert _page(session, source, 1).text_layer is None


def test_an_original_shared_with_another_employee_stays(
    session: Session, layout: DataLayout
) -> None:
    # K10: orijinal başka çalışanın belgesine kaynaksa dokunulmaz; o çalışanın Alinan'ı da kalır.
    source = _upload(session, layout, "u_iki_kisi", b"%PDF iki kisi")
    mine = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    _document(
        session,
        layout,
        source,
        [1],
        name="Baska_Kisi-Passport.pdf",
        owner=OTHER,
        folder=OTHER_FOLDER,
    )
    session.commit()

    plan = plan_document_deletion(session, layout, mine)
    assert _roles(plan.remove) == ["document", "received"]
    assert _roles(plan.keep) == ["inbox"]
    _delete(session, layout, mine)

    assert layout.resolve(source.stored_path).exists()
    assert _received_files(layout) == []
    assert _received_files(layout, OTHER_FOLDER) == ["tarama.pdf"]


def test_a_superseded_or_archived_document_on_the_same_source_keeps_it(
    session: Session, layout: DataLayout
) -> None:
    # K18: eski sürüm de aynı kaynağa dayanır; silinmemiş her belge ölçüte girer.
    source = _upload(session, layout, "u_surum", b"%PDF surum", pages=1)
    old = _document(
        session,
        layout,
        source,
        [0],
        name="Test_Kisi-Passport-eski.pdf",
        status=DocumentStatus.SUPERSEDED,
    )
    current = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    session.commit()

    plan = plan_document_deletion(session, layout, current)
    assert _roles(plan.remove) == ["document"]
    assert _roles(plan.keep) == ["inbox", "received"]
    assert plan.pages == ()  # sayfa eski sürümün de kaynağı

    _delete(session, layout, current)
    assert _page(session, source, 0).analysis_json is not None
    assert layout.resolve(old.path).exists()


# --- kuyruk -------------------------------------------------------------------------------------


def test_an_open_queue_item_keeps_the_original_and_its_queue_copy(
    session: Session, layout: DataLayout
) -> None:
    source = _upload(session, layout, "u_kuyruk", b"%PDF kuyruk")
    document = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    _queue_item(session, layout, source, [1])
    session.commit()

    plan = plan_document_deletion(session, layout, document)
    assert _roles(plan.remove) == ["document", "received"]
    assert _roles(plan.keep) == ["inbox", "queue"]
    _delete(session, layout, document)

    assert layout.resolve(source.stored_path).exists()
    queue = layout.queue_dir("unresolved", source.upload_id)
    assert sorted(path.name for path in queue.iterdir()) == ["reason.json", "tarama.pdf"]


def test_a_resolved_queue_item_lets_the_original_and_its_queue_copy_go(
    session: Session, layout: DataLayout
) -> None:
    source = _upload(session, layout, "u_kapali", b"%PDF kapali")
    document = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    _queue_item(session, layout, source, [1], resolved=True)
    session.commit()

    plan = plan_document_deletion(session, layout, document)
    assert _roles(plan.remove) == ["document", "inbox", "queue", "received"]
    _delete(session, layout, document)

    queue = layout.queue_dir("unresolved", source.upload_id)
    assert sorted(path.name for path in queue.iterdir()) == ["reason.json"]
    # Kuyruk öğesinin sayfası silinen belgenin kaynağı değil: analizi yerinde.
    assert _page(session, source, 1).analysis_json is not None


def test_an_unreadable_queue_payload_counts_as_the_whole_batch(
    session: Session, layout: DataLayout
) -> None:
    source = _upload(session, layout, "u_bozuk", b"%PDF bozuk kuyruk")
    document = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    item = _queue_item(session, layout, source, [1])
    item.payload_json = {"sources": "bozuk"}
    session.commit()

    plan = plan_document_deletion(session, layout, document)

    # Kaynağı okunamayan açık öğe partinin bütününe dayanır: emin olunamayan dosya silinmez.
    assert _roles(plan.remove) == ["document", "received"]
    assert _roles(plan.keep) == ["inbox", "queue"]
    assert plan.pages == ()


def test_a_batch_still_being_processed_keeps_its_original_and_pages(
    session: Session, layout: DataLayout
) -> None:
    source = _upload(
        session, layout, "u_isleniyor", b"%PDF isleniyor", pages=1, status=UploadStatus.EXECUTING
    )
    document = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    session.commit()

    plan = plan_document_deletion(session, layout, document)

    assert _roles(plan.remove) == ["document", "received"]
    assert _roles(plan.keep) == ["inbox"]
    assert plan.pages == ()


# --- tekrar yükleme, taşınmış belge, arşiv ------------------------------------------------------


def test_a_duplicate_upload_of_the_same_bytes_goes_with_the_original(
    session: Session, layout: DataLayout
) -> None:
    content = b"%PDF ayni icerik"
    source = _upload(session, layout, "u_ilk", content, pages=1)
    duplicate = _upload(session, layout, "u_tekrar", content, pages=1, duplicate_of=source)
    document = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    session.commit()

    plan = plan_document_deletion(session, layout, document)
    assert _roles(plan.remove) == ["document", "inbox", "inbox", "received"]
    _delete(session, layout, document)

    assert not layout.resolve(duplicate.stored_path).exists()


def test_a_moved_document_also_clears_the_previous_owners_received_copy(
    session: Session, layout: DataLayout
) -> None:
    # 10.8.2: taşımada eski sahibin Alinan kopyası kalır; belge silinince o da gider.
    source = _upload(session, layout, "u_tasindi", b"%PDF tasindi", pages=1)
    document = _document(
        session,
        layout,
        source,
        [0],
        name="Baska_Kisi-Passport.pdf",
        owner=OTHER,
        folder=OTHER_FOLDER,
    )
    copy_to_received(layout, OWNER_FOLDER, layout.resolve(source.stored_path), sha256=source.sha256)
    record_event(
        session,
        EventType.MANUAL_MOVE,
        document_id=document.id,
        employee_id=OTHER,
        actor=ACTOR,
        data={"document_id": document.id, "from_employee_id": OWNER, "to_employee_id": OTHER},
    )
    session.commit()

    plan = plan_document_deletion(session, layout, document)
    assert _roles(plan.remove) == ["document", "inbox", "received", "received"]
    _delete(session, layout, document)

    assert _received_files(layout) == [] and _received_files(layout, OTHER_FOLDER) == []


def test_an_archived_document_is_deleted_from_the_archive(
    session: Session, layout: DataLayout
) -> None:
    source = _upload(session, layout, "u_arsiv", b"%PDF arsiv", pages=1)
    document = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    archive_document(session, layout, document.id, actor=ACTOR)
    archived = layout.resolve(document.path)
    assert archived.is_relative_to(layout.archive)
    session.commit()

    deleted = _delete(session, layout, document)

    assert deleted.previous_status == "archived"
    assert not archived.exists()
    event = deleted.event
    assert event.data_json is not None and event.data_json["previous_status"] == "archived"


def test_a_document_whose_file_is_already_gone_is_still_deleted(
    session: Session, layout: DataLayout
) -> None:
    source = _upload(session, layout, "u_dosyasiz", b"%PDF dosyasiz", pages=1)
    document = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    layout.resolve(document.path).unlink()
    session.commit()

    plan = plan_document_deletion(session, layout, document)
    assert _roles(plan.remove) == ["inbox", "received"]  # yok olan dosya sayılmaz
    _delete(session, layout, document)

    assert session.get_one(Document, document.id).status == "deleted"


# --- paket, profil, retler ----------------------------------------------------------------------


def test_the_package_tick_drops_and_the_profile_no_longer_lists_the_document(
    session: Session, layout: DataLayout
) -> None:
    source = _upload(session, layout, "u_paket", b"%PDF paket", pages=1)
    document = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    group = create_group(session, name="Vize", description=None, actor=ACTOR)
    add_item(session, group.id, match_kind="type", type_slug=TYPE_SLUG, actor=ACTOR)
    package = assign_package(session, OWNER, group.id, actor=ACTOR).package
    assert package is not None and package.status == PackageStatus.COMPLETED.value
    session.commit()

    _delete(session, layout, document)

    package = session.get_one(EmployeePackage, package.id, populate_existing=True)
    assert package.status == PackageStatus.OPEN.value
    profile = layout.profile_path(OWNER_FOLDER).read_text(encoding="utf-8")
    assert "Test_Kisi-Passport.pdf" not in profile
    reopened = session.scalars(select(Event).where(Event.type == "PACKAGE_REOPENED")).one()
    assert reopened.actor == ACTOR
    assert session.get_one(DocumentGroup, group.id) is not None


def test_refusals_change_nothing(session: Session, layout: DataLayout) -> None:
    source = _upload(session, layout, "u_ret", b"%PDF ret", pages=1)
    document = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    output = layout.resolve(document.path)
    session.commit()

    with pytest.raises(ValueError, match="actor"):
        delete_document(session, layout, document.id, actor=" ")
    with pytest.raises(DocumentNotFoundError):
        delete_document(session, layout, 9999, actor=ACTOR)
    with pytest.raises(DeletionChangedError) as changed:
        delete_document(session, layout, document.id, actor=ACTOR, expected_counts=(1, 0))
    assert (changed.value.expected, changed.value.actual) == ((1, 0), (3, 0))
    session.rollback()

    assert session.get_one(Document, document.id).status == "active" and output.exists()
    assert session.scalars(select(Event)).all() == []

    _delete(session, layout, document)
    with pytest.raises(DocumentNotDeletableError):
        delete_document(session, layout, document.id, actor=ACTOR)


def test_a_file_that_cannot_be_removed_is_counted_logged_and_not_rolled_back(
    session: Session,
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Windows'ta açık dosya silinemeyebilir: hata sayıya ve loga girer, silme geri sarılmaz.
    source = _upload(session, layout, "u_kilit", b"%PDF kilitli", pages=1)
    document = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    inbox = layout.resolve(source.stored_path)
    session.commit()
    original_unlink = Path.unlink

    def locked(path: Path, missing_ok: bool = False) -> None:
        if path == inbox:
            raise PermissionError("dosya açık")
        original_unlink(path, missing_ok=missing_ok)

    deleted = delete_document(session, layout, document.id, actor=ACTOR)
    session.commit()
    monkeypatch.setattr(Path, "unlink", locked)
    with caplog.at_level(logging.WARNING, logger="app.storage.delete"):
        failed = remove_document_files(session, deleted)
    session.commit()

    assert failed == 1 and inbox.exists()
    assert not layout.received_dir(OWNER_FOLDER).joinpath("tarama.pdf").exists()
    event = session.scalars(select(Event).where(Event.type == "DOCUMENT_DELETED")).one()
    assert event.data_json is not None and event.data_json["files_failed"] == 1
    assert session.get_one(Document, document.id).status == "deleted"
    (record,) = caplog.records
    assert "inbox" in record.getMessage() and "PermissionError" in record.getMessage()
    assert "tarama" not in record.getMessage() and "Test_Kisi" not in record.getMessage()


def test_nothing_personal_survives_in_the_deleted_document_row_or_its_event(
    session: Session, layout: DataLayout
) -> None:
    source = _upload(session, layout, "u_kisisel", b"%PDF kisisel", pages=1)
    document = _document(session, layout, source, [0], name="Test_Kisi-Passport.pdf")
    session.commit()

    deleted = _delete(session, layout, document)

    row = session.get_one(Document, document.id)
    values = [str(getattr(row, column.key)) for column in Document.__table__.columns]
    values += [str(value) for value in (deleted.event.data_json or {}).values()]
    assert not [value for value in values if "Test_Kisi" in value or PERSON in value]
    assert FileRole.DOCUMENT.value == "document"
