"""10.5.13 — pasif çalışanı kalıcı silme çekirdeği: yalnız pasif çalışan; belgeler, alt kayıtlar,
klasör, ona ait yüklemenin orijinali ve sayfaları gider; ortak yüklemenin orijinali ve öbür
çalışanın sayfaları kalır; çalışan satırı iskelet; planlarda ve olaylarda kişisel değer kalmaz; E
numarası yeniden verilmez; eşleştirme ve bot silineni bulmaz (K8, K9, K10, K15, K16, R11; PLAN.md
§D110, §D116).

Veriler sentetiktir: kişi adları, numaralar ve dosyalar uydurmadır, gerçek kimlik belgesi
kullanılmaz.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Base,
    Document,
    DocumentGroup,
    DocumentStatus,
    Employee,
    EmployeeAlias,
    EmployeeContact,
    EmployeeFieldObservation,
    EmployeeIdentifier,
    EmployeePackage,
    EmployeeStatus,
    Event,
    KnownDocumentType,
    Page,
    Plan,
    QueueItem,
    Upload,
    UploadFile,
    UploadStatus,
    allocate_employee_number,
)
from app.db.session import create_db_engine, create_session_factory
from app.events import EventType, record_event
from app.matching.match import DocumentNumberKey, MatchRule, PersonKey, match_employee
from app.matching.names import normalize_name
from app.pipeline.plan import PlanDocument, read_plan
from app.profiles import write_profile
from app.storage import (
    DataLayout,
    EmployeeDeletionChangedError,
    EmployeeNotDeletableError,
    copy_to_received,
    delete_employee,
    plan_employee_deletion,
    prepare_data_dir,
    remove_employee_files,
)
from app.storage.delete_employee import DELETED_EMPLOYEE_MESSAGE, EmployeeNotFoundError
from app.telegram.intent import find_employees, parse_person

ACTOR = "ik.ayse"
TYPE_SLUG = "test_passport"
GONE, GONE_FOLDER = "E0001", "Zorana_Testovic_E0001"
OTHER, OTHER_FOLDER = "E0002", "Milan_Probic_E0002"
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
BORN = date(1991, 4, 12)
NUMBER = "ZT1234567"
PHONE = "+381 60 1234567"
# Silmeden sonra veritabanının hiçbir olayında, planında ve iskeletinde geçmemesi gereken değerler.
PERSONAL = ("Zorana", "Testovic", "Зорана", NUMBER, PHONE, "1991-04-12", "12.04.1991")


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine: Engine = create_db_engine(f"sqlite:///{(tmp_path / 'delete-emp.db').as_posix()}")
    Base.metadata.create_all(engine)
    try:
        with create_session_factory(engine)() as db_session:
            yield db_session
    finally:
        engine.dispose()


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


def _employee(
    session: Session,
    layout: DataLayout,
    employee_id: str,
    folder: str,
    given: str,
    surname: str,
    *,
    status: EmployeeStatus = EmployeeStatus.INACTIVE,
    merged_into: str | None = None,
) -> Employee:
    employee = Employee(
        id=employee_id,
        folder_name=folder,
        given_names=given,
        surname=surname,
        other_names=None,
        original_script_name="Зорана Тестовић" if given == "Zorana" else None,
        date_of_birth=BORN if given == "Zorana" else date(1985, 1, 1),
        nationality="SRB",
        status=status.value,
        merged_into_id=merged_into,
    )
    session.add(employee)
    session.flush()
    layout.ensure_employee_tree(folder)
    return employee


def _upload(
    session: Session, layout: DataLayout, upload_id: str, content: bytes, *, pages: int
) -> UploadFile:
    session.add(Upload(id=upload_id, channel="web", status=UploadStatus.DONE.value))
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
    )
    session.add(upload_file)
    session.flush()
    for index in range(pages):
        image = layout.page_image_path(upload_file.id, index)
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"jpeg " + content + bytes([index]))
        session.add(
            Page(
                file_id=upload_file.id,
                index=index,
                image_path=layout.relative(image),
                text_layer=f"sayfa {index}",
                analysis_json={"person": {"surname": "okunan"}},
                analysis_status="done",
            )
        )
    session.flush()
    return upload_file


def _plan(
    session: Session, upload_file: UploadFile, items: list[tuple[str, str, list[int], str]]
) -> Plan:
    """Sözleşmeye uyan plan: `(öğe, çalışan, sayfalar, hedef adı)` başına bir `hazir` öğesi."""
    document = PlanDocument.model_validate(
        {
            "upload_id": upload_file.upload_id,
            "version": 1,
            "model": None,
            "items": [
                {
                    "item_id": item_id,
                    "document_type_slug": TYPE_SLUG,
                    "sources": [{"file_id": upload_file.id, "pages": pages}],
                    "operation": "extract",
                    "target_format": "pdf",
                    "target_name": target,
                    "employee": {
                        "action": "match",
                        "employee_id": employee_id,
                        "matched_by": "document_number",
                    },
                    "route": "hazir",
                    "route_reason": None,
                    "validations": [{"name": "page_count", "ok": True}],
                }
                for item_id, employee_id, pages, target in items
            ],
        }
    )
    plan = Plan(
        upload_id=upload_file.upload_id,
        version=1,
        json=document.model_dump(mode="json"),
        plan_hash=document.plan_hash,
    )
    session.add(plan)
    session.flush()
    return plan


def _document(
    session: Session,
    layout: DataLayout,
    plan: Plan,
    source: UploadFile,
    pages: list[int],
    *,
    owner: str,
    folder: str,
    name: str,
    status: DocumentStatus = DocumentStatus.ACTIVE,
) -> Document:
    path = layout.ready_dir(folder) / name
    path.write_bytes(b"%PDF cikti " + name.encode())
    document = Document(
        employee_id=owner,
        type_slug=TYPE_SLUG,
        path=layout.relative(path),
        format="pdf",
        plan_id=plan.id,
        source_refs_json=[{"file_id": source.id, "pages": pages}],
        status=status.value,
    )
    session.add(document)
    session.flush()
    copy_to_received(layout, folder, layout.resolve(source.stored_path), sha256=source.sha256)
    return document


@pytest.fixture
def world(session: Session, layout: DataLayout) -> dict[str, Any]:
    """E0001 (pasif): yalnız ona ait partide etkin ve arşivdeki iki belge (üçüncü sayfa belgesiz),
    ortak partide eski sürüm; alt kayıtlar, paket, kişisel değer taşıyan olaylar. E0002 (etkin):
    ortak partinin ikinci sayfası."""
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
    gone = _employee(session, layout, GONE, GONE_FOLDER, "Zorana", "Testovic")
    _employee(session, layout, OTHER, OTHER_FOLDER, "Milan", "Probic", status=EmployeeStatus.ACTIVE)
    own = _upload(session, layout, "u_own", b"%PDF yalniz ona ait", pages=3)
    shared = _upload(session, layout, "u_shared", b"%PDF iki kisi bir arada", pages=2)
    own_plan = _plan(
        session,
        own,
        [
            ("i1", GONE, [0], "Zorana_Testovic-Passport.pdf"),
            ("i2", GONE, [1], "Zorana_Testovic-Passport-2.pdf"),
        ],
    )
    shared_plan = _plan(
        session,
        shared,
        [
            ("i1", GONE, [0], "Zorana_Testovic-Passport.pdf"),
            ("i2", OTHER, [1], "Milan_Probic-Passport.pdf"),
        ],
    )
    active = _document(
        session,
        layout,
        own_plan,
        own,
        [0],
        owner=GONE,
        folder=GONE_FOLDER,
        name="Zorana_Testovic-Passport.pdf",
    )
    archived = _document(
        session,
        layout,
        own_plan,
        own,
        [1],
        owner=GONE,
        folder=GONE_FOLDER,
        name="Zorana_Testovic-Passport-2.pdf",
        status=DocumentStatus.ARCHIVED,
    )
    superseded = _document(
        session,
        layout,
        shared_plan,
        shared,
        [0],
        owner=GONE,
        folder=GONE_FOLDER,
        name="Zorana_Testovic-Passport-3.pdf",
        status=DocumentStatus.SUPERSEDED,
    )
    others = _document(
        session,
        layout,
        shared_plan,
        shared,
        [1],
        owner=OTHER,
        folder=OTHER_FOLDER,
        name="Milan_Probic-Passport.pdf",
    )
    session.add_all(
        [
            EmployeeAlias(
                employee_id=GONE,
                raw_name="Zorana Testovic",
                normalized_name=normalize_name("Zorana Testovic"),
                script="latin",
            ),
            EmployeeAlias(
                employee_id=GONE,
                raw_name="Зорана Тестовић",
                normalized_name=normalize_name("Зорана Тестовић"),
                script="cyrillic",
            ),
            EmployeeIdentifier(
                employee_id=GONE, kind=TYPE_SLUG, value=NUMBER, source_document_id=active.id
            ),
            EmployeeContact(
                employee_id=GONE, kind="phone", value=PHONE, source_document_id=active.id
            ),
            EmployeeFieldObservation(
                employee_id=GONE,
                field="surname",
                outcome="filled",
                file_id=own.id,
                page_index=0,
            ),
            EmployeeAlias(
                employee_id=OTHER,
                raw_name="Milan Probic",
                normalized_name=normalize_name("Milan Probic"),
                script="latin",
            ),
        ]
    )
    group = DocumentGroup(name="Vize dosyasi", normalized_name="vize dosyasi", created_by=ACTOR)
    session.add(group)
    session.flush()
    session.add(EmployeePackage(employee_id=GONE, group_id=group.id, requested_by=ACTOR))
    # Her olay türü: mesajında ad, verisinde kişisel anahtarlar ve kişinin değerini taşıyan
    # sıradan anahtarlar (bu çalışanın olayları).
    for event_type in EventType:
        record_event(
            session,
            event_type,
            upload_id="u_own",
            employee_id=GONE,
            document_id=active.id,
            message=f"{event_type.value}: Zorana Testovic ({NUMBER})",
            data={
                "employee_id": GONE,
                "path": f"Employees/{GONE_FOLDER}/Hazir/Zorana_Testovic-Passport.pdf",
                "given_names": "Zorana",
                "date_of_birth": "1991-04-12",
                "note": "Testovic belgesi",
                "readings": [{"value": NUMBER}],
                "nested": {"label": "Зорана Тестовић", "count": 2, "rule": "name_dob"},
                "phones": [PHONE, "baska"],
                "count": 3,
            },
        )
    # Kişiye bağlı olmayan ama onun dosyasının olayı: dosya adında kişinin adı.
    record_event(
        session,
        EventType.FILE_UPLOADED,
        upload_id="u_shared",
        file_id=shared.id,
        message="Zorana_Testovic_pasaport.pdf",
        data={"name": "Zorana_Testovic_pasaport.pdf", "size": 10},
    )
    # Öbür çalışanın olayı: dokunulmaz.
    other_event = record_event(
        session,
        EventType.PERSON_MATCHED,
        employee_id=OTHER,
        message="Milan Probic eşleşti",
        data={"name": "Milan Probic"},
    )
    session.commit()
    return {
        "own": own.id,
        "shared": shared.id,
        "active": active.id,
        "archived": archived.id,
        "superseded": superseded.id,
        "others": others.id,
        "own_plan": own_plan.id,
        "shared_plan": shared_plan.id,
        "other_event": other_event.id,
        "gone": gone,
    }


def _delete(session: Session, layout: DataLayout, **kwargs: Any) -> Any:
    deleted = delete_employee(session, layout, GONE, actor=ACTOR, now=NOW, **kwargs)
    session.commit()
    failed = remove_employee_files(session, deleted)
    session.commit()
    return deleted, failed


def _dump(session: Session) -> str:
    """Olayların, planların ve çalışan satırlarının bütün metni (kişisel değer taraması)."""
    rows: list[object] = []
    for event in session.scalars(select(Event)):
        rows.append([event.message, event.data_json])
    rows.extend(plan.json for plan in session.scalars(select(Plan)))
    for employee in session.scalars(select(Employee).where(Employee.id == GONE)):
        rows.append(
            [
                employee.given_names,
                employee.surname,
                employee.other_names,
                employee.original_script_name,
                employee.folder_name,
                str(employee.date_of_birth),
                employee.nationality,
            ]
        )
    return json.dumps(rows, ensure_ascii=False, default=str)


def _count(session: Session, model: Any, **where: Any) -> int:
    query = select(func.count()).select_from(model)
    for column, value in where.items():
        query = query.where(getattr(model, column) == value)
    return session.scalar(query) or 0


# --- çekirdek -----------------------------------------------------------------------------------


def test_an_inactive_employee_is_deleted_with_documents_records_and_folder(
    session: Session, layout: DataLayout, world: dict[str, Any]
) -> None:
    folder = layout.employee_dir(GONE_FOLDER)
    assert folder.is_dir()

    deleted, failed = _delete(session, layout, expected_documents=3)

    assert failed == 0
    assert not folder.exists()
    employee = session.get_one(Employee, GONE)
    assert employee.status == EmployeeStatus.DELETED.value
    assert (employee.given_names, employee.surname) == ("", "")
    assert employee.other_names is None and employee.original_script_name is None
    assert employee.date_of_birth is None and employee.nationality is None
    assert employee.folder_name == f"deleted_{GONE}"
    assert (employee.deleted_at, employee.deleted_by) == (NOW, ACTOR)
    for key in ("active", "archived", "superseded"):
        document = session.get_one(Document, world[key])
        assert document.status == DocumentStatus.DELETED.value
        assert document.path is None and document.deleted_by == ACTOR
        # İskelet: kimlik, tür, çalışan, köken kalır.
        assert document.employee_id == GONE and document.source_refs_json
    for model in (
        EmployeeAlias,
        EmployeeIdentifier,
        EmployeeContact,
        EmployeeFieldObservation,
        EmployeePackage,
    ):
        assert _count(session, model, employee_id=GONE) == 0
    # Öbür çalışan ve belgesi yerinde.
    assert _count(session, EmployeeAlias, employee_id=OTHER) == 1
    other = session.get_one(Document, world["others"])
    assert other.status == DocumentStatus.ACTIVE.value
    assert layout.resolve(other.path or "").is_file()
    assert layout.employee_dir(OTHER_FOLDER).is_dir()

    event = deleted.event
    assert (event.type, event.actor, event.employee_id) == ("EMPLOYEE_DELETED", ACTOR, GONE)
    assert event.data_json["documents"] == 3
    assert event.data_json["records"] == 5 and event.data_json["packages"] == 1
    assert all(isinstance(value, int) for value in event.data_json.values())
    assert event.message is None


def test_only_an_inactive_employee_is_deleted(
    session: Session, layout: DataLayout, world: dict[str, Any]
) -> None:
    gone = session.get_one(Employee, GONE)
    for status in (EmployeeStatus.ACTIVE, EmployeeStatus.MERGED, EmployeeStatus.DELETED):
        gone.status = status.value
        session.commit()
        with pytest.raises(EmployeeNotDeletableError):
            delete_employee(session, layout, GONE, actor=ACTOR)
        session.rollback()
    with pytest.raises(EmployeeNotFoundError):
        delete_employee(session, layout, "E0404", actor=ACTOR)
    gone.status = EmployeeStatus.INACTIVE.value
    session.commit()
    with pytest.raises(ValueError, match="actor"):
        delete_employee(session, layout, GONE, actor=" ")

    assert session.get_one(Employee, GONE).given_names == "Zorana"
    assert _count(session, Document, status=DocumentStatus.DELETED.value) == 0
    assert _count(session, Event, type="EMPLOYEE_DELETED", actor=ACTOR) == 0
    assert layout.employee_dir(GONE_FOLDER).is_dir()


def test_a_changed_document_count_deletes_nothing(
    session: Session, layout: DataLayout, world: dict[str, Any]
) -> None:
    with pytest.raises(EmployeeDeletionChangedError) as raised:
        delete_employee(session, layout, GONE, actor=ACTOR, expected_documents=2)
    session.rollback()

    assert (raised.value.expected, raised.value.actual) == (2, 3)
    assert session.get_one(Employee, GONE).status == EmployeeStatus.INACTIVE.value
    assert _count(session, EmployeeAlias, employee_id=GONE) == 2


def test_the_own_upload_goes_and_the_shared_upload_stays(
    session: Session, layout: DataLayout, world: dict[str, Any]
) -> None:
    # S25: yalnız ona ait partinin orijinali ve bütün sayfa görüntüleri (belgesiz sayfa dahil)
    # gider; ortak partinin orijinali ve öbür çalışanın sayfası kalır.
    own = session.get_one(UploadFile, world["own"])
    shared = session.get_one(UploadFile, world["shared"])
    own_inbox, shared_inbox = layout.resolve(own.stored_path), layout.resolve(shared.stored_path)
    plan = plan_employee_deletion(session, layout, session.get_one(Employee, GONE))
    assert plan.document_count == 3
    assert {page.page_id for page in plan.pages} == {
        page.id
        for page in session.scalars(select(Page))
        if page.file_id == own.id or (page.file_id == shared.id and page.index == 0)
    }

    _delete(session, layout)

    assert not own_inbox.exists()
    assert shared_inbox.is_file()
    for page in session.scalars(select(Page).where(Page.file_id == own.id)):
        assert page.image_path is None and page.analysis_json is None and page.text_layer is None
    shared_pages = {
        page.index: page for page in session.scalars(select(Page).where(Page.file_id == shared.id))
    }
    assert shared_pages[0].image_path is None and shared_pages[0].analysis_json is None
    kept = shared_pages[1]
    assert kept.image_path is not None and layout.resolve(kept.image_path).is_file()
    assert kept.analysis_json is not None
    # Öbür çalışanın Alinan kopyası (ortak orijinal) yerinde.
    assert any(layout.received_dir(OTHER_FOLDER).iterdir())


def test_an_open_queue_item_keeps_the_original(
    session: Session, layout: DataLayout, world: dict[str, Any]
) -> None:
    own = session.get_one(UploadFile, world["own"])
    session.add(
        QueueItem(
            upload_id=own.upload_id,
            kind="unresolved",
            reason="Pasif çalışan (E0001) ile eşleşti (inactive_employee)",
            payload_json={"sources": [{"file_id": own.id, "pages": [2]}]},
        )
    )
    session.commit()

    _delete(session, layout)

    assert layout.resolve(own.stored_path).is_file()
    page = session.scalars(select(Page).where(Page.file_id == own.id, Page.index == 2)).one()
    assert page.image_path is not None and page.analysis_json is not None


def test_events_keep_their_rows_but_lose_every_personal_value(
    session: Session, layout: DataLayout, world: dict[str, Any]
) -> None:
    events_before = _count(session, Event)
    before = _dump(session)
    assert all(value in before for value in PERSONAL if value != "12.04.1991")

    _delete(session, layout)

    assert _count(session, Event) == events_before + 1  # yalnız EMPLOYEE_DELETED eklendi
    dump = _dump(session).casefold()
    for value in PERSONAL:
        assert value.casefold() not in dump, value
    own = session.scalars(
        select(Event).where(Event.employee_id == GONE, Event.type == "PAGE_ANALYZED")
    ).one()
    assert own.message == DELETED_EMPLOYEE_MESSAGE.format(type="PAGE_ANALYZED")
    # Kişisel olmayan veri kalır.
    assert own.data_json == {
        "employee_id": GONE,
        "nested": {"count": 2, "rule": "name_dob"},
        "phones": ["baska"],
        "count": 3,
    }
    related = session.scalars(select(Event).where(Event.file_id == world["shared"])).one()
    assert related.message == DELETED_EMPLOYEE_MESSAGE.format(type="FILE_UPLOADED")
    assert related.data_json == {"size": 10}
    other = session.get_one(Event, world["other_event"])
    assert (other.message, other.data_json) == ("Milan Probic eşleşti", {"name": "Milan Probic"})


def test_plans_lose_the_target_names_and_stay_readable(
    session: Session, layout: DataLayout, world: dict[str, Any]
) -> None:
    _delete(session, layout)

    shared = session.get_one(Plan, world["shared_plan"])
    names = {item.item_id: item.target_name for item in read_plan(shared).items}
    assert names == {"i1": "deleted-i1.pdf", "i2": "Milan_Probic-Passport.pdf"}
    own = read_plan(session.get_one(Plan, world["own_plan"]))
    assert [item.target_name for item in own.items] == ["deleted-i1.pdf", "deleted-i2.pdf"]


def test_the_employee_number_is_never_given_again(
    session: Session, layout: DataLayout, world: dict[str, Any]
) -> None:
    # K8: en büyük numaralı kayıt silinse de numarası yeniden verilmez.
    late = _employee(session, layout, "E0003", "Zorana_Testovic_E0003", "Zorana", "Testovic")
    session.commit()
    deleted = delete_employee(session, layout, late.id, actor=ACTOR)
    session.commit()
    remove_employee_files(session, deleted)

    assert allocate_employee_number(session) == "E0004"


def test_matching_and_the_bot_do_not_find_the_deleted_employee(
    session: Session, layout: DataLayout, world: dict[str, Any]
) -> None:
    key = PersonKey(
        document_numbers=(DocumentNumberKey(NUMBER, legible=True),),
        normalized_name=normalize_name("Zorana Testovic"),
        date_of_birth=BORN,
        original_script_name=None,
        normalized_original_name=None,
        mrz_allows_clean_document_number=True,
        conflicts=(),
    )
    assert match_employee(session, key).rule is MatchRule.DOCUMENT_NUMBER
    assert [e.id for e in find_employees(session, parse_person("Zorana Testovic"))] == [GONE]
    session.rollback()

    _delete(session, layout)

    assert match_employee(session, key).rule is MatchRule.NO_MATCH
    assert find_employees(session, parse_person("Zorana Testovic")) == []
    assert find_employees(session, parse_person(GONE)) == []


def test_a_deleted_employee_gets_no_profile_file(
    session: Session, layout: DataLayout, world: dict[str, Any]
) -> None:
    _delete(session, layout)

    assert write_profile(session, layout, session.get_one(Employee, GONE)) is None
    assert not layout.employee_dir(f"deleted_{GONE}").exists()


def test_a_record_merged_into_the_employee_is_deleted_with_it(
    session: Session, layout: DataLayout, world: dict[str, Any]
) -> None:
    # 10.5.9: birleştirilen kayıt aynı kişidir; klasörü ve profil.md'si de adını taşır.
    merged = _employee(
        session,
        layout,
        "E0005",
        "Zorana_Testovic_E0005",
        "Zorana",
        "Testovic",
        status=EmployeeStatus.MERGED,
        merged_into=GONE,
    )
    layout.profile_path(merged.folder_name).write_text("Zorana Testovic", encoding="utf-8")
    record_event(
        session, EventType.EMPLOYEE_MERGED, employee_id=merged.id, message="Zorana Testovic"
    )
    session.commit()

    deleted, _ = _delete(session, layout)

    assert deleted.plan.people == (GONE, "E0005")
    assert deleted.event.data_json["merged_records"] == 1
    row = session.get_one(Employee, "E0005")
    assert row.status == EmployeeStatus.DELETED.value and row.given_names == ""
    assert row.merged_into_id == GONE
    assert not layout.employee_dir("Zorana_Testovic_E0005").exists()
    assert "Testovic" not in _dump(session)


def test_a_file_that_cannot_be_removed_is_counted_on_the_event(
    session: Session,
    layout: DataLayout,
    world: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    own = session.get_one(UploadFile, world["own"])
    inbox = layout.resolve(own.stored_path)
    original_unlink = Path.unlink

    def locked(path: Path, missing_ok: bool = False) -> None:
        if path == inbox:
            raise PermissionError("kilitli")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", locked)

    deleted, failed = _delete(session, layout)

    assert failed == 1
    assert deleted.event.data_json["files_failed"] == 1
    assert session.get_one(Employee, GONE).status == EmployeeStatus.DELETED.value
