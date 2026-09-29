"""10.5.9 — iki çalışanı birleştirme: birleşenin belgeleri kalan kayda K8 adıyla taşınır, `Alinan/`
kopyaları taşınır; numaraları, isim yazımları, iletişim bilgileri, alan kaynakları ve belge
paketleri kalan kayda bağlanır (aynı değer tek kalır); birleşen kayıt `merged` ve kalanın
numarasıyla kalır; dosya taşıması yarıda kalırsa hiçbir şey değişmez (PLAN.md §C90-d, §D69; K8, K11,
K16, K18, R11, R13).

Birim testleri `merge_employees`'ı geçici SQLite ve geçici veri dizinindeki iki sentetik çalışanla
sınar: belgeler `tests/fixtures/gen.py`'nin sentetik PDF'leridir, gerçek kişi ya da belge yoktur,
ağ çağrısı yoktur. İki aşamalı onay ve sayfalar `tests/web/test_employee_merge.py`'dedir.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.storage.merge as merge_module
from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeAlias,
    EmployeeContact,
    EmployeeFieldObservation,
    EmployeeIdentifier,
    EmployeePackage,
    EmployeeStatus,
    Event,
    FieldOutcome,
    FieldSource,
    KnownDocumentType,
    PackageStatus,
    Upload,
    UploadFile,
)
from app.events import EventType
from app.groups import (
    PackageStateError,
    add_item,
    assign_package,
    create_group,
)
from app.matching.match import DocumentNumberKey, MatchRule, PersonKey, match_employee
from app.matching.merge import (
    DUPLICATE_PACKAGE_NOTE,
    EmployeeAlreadyMergedError,
    RecordCounts,
    SameEmployeeError,
    merge_document_count,
    merge_employees,
    merge_field_preview,
)
from app.matching.names import detect_script, normalize_name
from app.profiles import write_profile
from app.storage import (
    DataLayout,
    DocumentNotMovableError,
    EmployeeMergeError,
    move_document,
    sha256_file,
)
from tests.fixtures.gen import make_pdf_bytes

ACTOR = "ik-yonetici"
KEEP, MERGE = "E0001", "E0005"
KEEP_FOLDER, MERGE_FOLDER = "Ivan_Petrov_E0001", "Ivan_Petrow_E0005"
BORN = date(1990, 1, 1)
CYRILLIC = "Иван Петров"
UPLOAD_ID = "u_merge"
TYPES = (
    ("ru_passport", "Rus Pasaportu", "Passport"),
    ("residence_card", "İkamet Kartı", "Residence Card"),
    ("visa", "Vize", "Visa"),
)
# Kayıtların kişisel değerleri: olay verisine girmez.
PERSONAL_VALUES = ("Petrov", "Petrow", "PETROW", CYRILLIC, "000000001", "000000002", "+90 555")


@dataclass(frozen=True)
class Pair:
    """Aynı kişinin iki sentetik kaydı. Kalan (E0001): etkin pasaport, `Alinan/tarama.pdf`, bir
    yazım, bir numara, bir telefon, vize paketi. Birleşen (E0005): etkin pasaport ve ikamet kartı,
    eski sürüm ve arşivde birer vize, iki `Alinan/` kopyası (biri kalanınkiyle aynı adda), iki
    yazım (biri kalanınkiyle aynı anahtarda), iki numara (biri kalanınkiyle aynı), iki telefon (biri
    aynı) ve bir e-posta, alan gözlemleri, pasaport ve vize paketleri."""

    keep_passport: int
    passport: int
    residence: int
    superseded: int
    archived: int
    passport_group: int
    visa_group: int
    keep_visa_package: int
    passport_package: int
    visa_package: int
    hashes: dict[int, str]
    received: dict[str, bytes]


def _at(month: int) -> datetime:
    return datetime(2026, month, 1, tzinfo=UTC)


def _employee(session: Session, employee_id: str, surname: str, **fields: Any) -> Employee:
    employee = Employee(
        id=employee_id,
        folder_name=f"Ivan_{surname}_{employee_id}",
        given_names="Ivan",
        surname=surname,
        date_of_birth=BORN,
        **fields,
    )
    session.add(employee)
    session.flush()
    return employee


def _catalog(session: Session) -> None:
    for slug, name, label in TYPES:
        session.add(
            KnownDocumentType(
                slug=slug,
                name=name,
                file_label=label,
                sides="single",
                direct=True,
                analyze=True,
                output_format="pdf",
            )
        )
    session.flush()


def _source(session: Session, name: str) -> int:
    upload = session.get(Upload, UPLOAD_ID) or Upload(id=UPLOAD_ID, channel="web")
    upload_file = UploadFile(
        upload=upload,
        original_name=name,
        stored_path=f"Inbox/{UPLOAD_ID}/{name}",
        sha256="0" * 64,
        mime="application/pdf",
    )
    session.add(upload_file)
    session.flush()
    return upload_file.id


def _document(
    session: Session,
    layout: DataLayout,
    employee_id: str,
    path: Path,
    *,
    slug: str,
    file_id: int,
    pages: int,
    sequence_no: int = 1,
    status: DocumentStatus = DocumentStatus.ACTIVE,
) -> Document:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(make_pdf_bytes(pages))
    document = Document(
        employee_id=employee_id,
        type_slug=slug,
        path=layout.relative(path),
        format="pdf",
        sequence_no=sequence_no,
        source_refs_json=[{"file_id": file_id, "pages": [0]}],
        status=status.value,
    )
    session.add(document)
    session.flush()
    return document


def _observation(
    session: Session,
    employee_id: str,
    field: str,
    outcome: FieldOutcome,
    *,
    file_id: int | None = None,
    source: FieldSource = FieldSource.DOCUMENT,
) -> None:
    session.add(
        EmployeeFieldObservation(
            employee_id=employee_id,
            field=field,
            outcome=outcome.value,
            file_id=file_id,
            page_index=None if file_id is None else 0,
            source=source.value,
            actor=None if source is FieldSource.DOCUMENT else ACTOR,
        )
    )


def _contact(
    session: Session, employee_id: str, kind: str, value: str, *, month: int, current: bool
) -> None:
    session.add(
        EmployeeContact(
            employee_id=employee_id,
            kind=kind,
            value=value,
            first_seen_at=_at(month),
            last_seen_at=_at(month),
            is_current=current,
        )
    )


def _package(session: Session, employee_id: str, group_id: int) -> int:
    result = assign_package(session, employee_id, group_id, actor=ACTOR)
    assert result.package is not None
    return result.package.id


@pytest.fixture
def pair(session: Session, layout: DataLayout) -> Pair:
    _catalog(session)
    keep_file, merge_file = _source(session, "tarama.pdf"), _source(session, "pasaport.pdf")
    _employee(session, KEEP, "Petrov", nationality="RUS", other_names="Sergeevich")
    _employee(session, MERGE, "Petrow", original_script_name=CYRILLIC, other_names="Sergeyevich")
    for folder in (KEEP_FOLDER, MERGE_FOLDER):
        layout.ensure_employee_tree(folder)
    keep_ready, merge_ready = layout.ready_dir(KEEP_FOLDER), layout.ready_dir(MERGE_FOLDER)

    keep_passport = _document(
        session,
        layout,
        KEEP,
        keep_ready / "Ivan_Petrov-Passport.pdf",
        slug="ru_passport",
        file_id=keep_file,
        pages=1,
    )
    passport = _document(
        session,
        layout,
        MERGE,
        merge_ready / "Ivan_Petrow-Passport.pdf",
        slug="ru_passport",
        file_id=merge_file,
        pages=2,
    )
    residence = _document(
        session,
        layout,
        MERGE,
        merge_ready / "Ivan_Petrow-Residence-Card.pdf",
        slug="residence_card",
        file_id=merge_file,
        pages=3,
    )
    superseded = _document(
        session,
        layout,
        MERGE,
        merge_ready / "Ivan_Petrow-Visa.pdf",
        slug="visa",
        file_id=merge_file,
        pages=4,
        status=DocumentStatus.SUPERSEDED,
    )
    archived = _document(
        session,
        layout,
        MERGE,
        layout.archive_dir(date(2026, 9, 1)) / "Ivan_Petrow-Visa-2.pdf",
        slug="visa",
        file_id=merge_file,
        pages=5,
        sequence_no=2,
        status=DocumentStatus.ARCHIVED,
    )
    received = {
        "keep:tarama.pdf": make_pdf_bytes(6),
        "merge:tarama.pdf": make_pdf_bytes(7),
        "merge:pasaport.pdf": make_pdf_bytes(8),
    }
    for key, content in received.items():
        owner, name = key.split(":")
        folder = KEEP_FOLDER if owner == "keep" else MERGE_FOLDER
        (layout.received_dir(folder) / name).write_bytes(content)
    layout.profile_path(MERGE_FOLDER).write_text("# Ivan Petrow\n", encoding="utf-8")

    for employee_id, raw in ((KEEP, "IVAN PETROV"), (MERGE, "IVAN PETROW"), (MERGE, CYRILLIC)):
        session.add(
            EmployeeAlias(
                employee_id=employee_id,
                raw_name=raw,
                normalized_name=normalize_name(raw),
                script=detect_script(raw),
            )
        )
    for employee_id, value in ((KEEP, "000000001"), (MERGE, "000000001"), (MERGE, "000000002")):
        session.add(EmployeeIdentifier(employee_id=employee_id, kind="ru_passport", value=value))
    _contact(session, KEEP, "phone", "+90 555 000 0001", month=1, current=True)
    _contact(session, MERGE, "phone", "+90 555 000 0002", month=6, current=True)
    _contact(session, MERGE, "phone", "+90 555 000 0001", month=3, current=False)
    _contact(session, MERGE, "email", "ivan@example.test", month=5, current=True)

    _observation(session, KEEP, "date_of_birth", FieldOutcome.SAME, file_id=merge_file)
    _observation(session, MERGE, "original_script_name", FieldOutcome.FILLED, file_id=merge_file)
    _observation(session, MERGE, "other_names", FieldOutcome.FILLED, file_id=merge_file)
    _observation(session, MERGE, "date_of_birth", FieldOutcome.SAME, file_id=merge_file)
    _observation(session, MERGE, "other_names", FieldOutcome.FILLED, source=FieldSource.MANUAL)

    passport_group = create_group(session, name="Pasaport paketi", description=None, actor=ACTOR)
    add_item(session, passport_group.id, match_kind="label", file_label="Passport", actor=ACTOR)
    visa_group = create_group(session, name="Vize paketi", description=None, actor=ACTOR)
    add_item(session, visa_group.id, match_kind="type", type_slug="visa", actor=ACTOR)
    keep_visa_package = _package(session, KEEP, visa_group.id)
    passport_package = _package(session, MERGE, passport_group.id)
    visa_package = _package(session, MERGE, visa_group.id)
    session.commit()

    hashes = {
        document.id: sha256_file(layout.resolve(document.path))
        for document in session.scalars(select(Document))
    }
    return Pair(
        keep_passport=keep_passport.id,
        passport=passport.id,
        residence=residence.id,
        superseded=superseded.id,
        archived=archived.id,
        passport_group=passport_group.id,
        visa_group=visa_group.id,
        keep_visa_package=keep_visa_package,
        passport_package=passport_package,
        visa_package=visa_package,
        hashes=hashes,
        received=received,
    )


def _merge(session: Session, layout: DataLayout) -> Any:
    keep, merge = session.get_one(Employee, KEEP), session.get_one(Employee, MERGE)
    result = merge_employees(session, layout, keep, merge, actor=ACTOR)
    session.commit()
    return result


def _events(session: Session, *types: EventType) -> list[Event]:
    return list(
        session.scalars(
            select(Event).where(Event.type.in_([kind.value for kind in types])).order_by(Event.id)
        )
    )


def _files(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir()) if path.is_file()}


# --- belgeler ve dosyalar ------------------------------------------------------------------------


def test_documents_move_to_the_kept_record_with_k8_names_and_the_same_bytes(
    session: Session, layout: DataLayout, pair: Pair
) -> None:
    result = _merge(session, layout)

    moved = (pair.passport, pair.residence, pair.superseded, pair.archived)
    assert result.documents == moved
    assert set(result.relocated) == {pair.passport, pair.residence, pair.superseded}
    ready = f"Employees/{KEEP_FOLDER}/Hazir"
    expected = {
        # Etkin: kalanın K8 adı, ilk boş sıra eki (kalanın pasaportu `-1`'i tutuyor).
        pair.passport: (f"{ready}/Ivan_Petrov-Passport-2.pdf", 2, DocumentStatus.ACTIVE),
        pair.residence: (f"{ready}/Ivan_Petrov-Residence-Card.pdf", 1, DocumentStatus.ACTIVE),
        # Eski sürüm yeniden adlandırılmaz (K18); arşivdeki belge arşivde kalır.
        pair.superseded: (f"{ready}/Ivan_Petrow-Visa.pdf", 1, DocumentStatus.SUPERSEDED),
        pair.archived: ("Archive/2026-09/Ivan_Petrow-Visa-2.pdf", 2, DocumentStatus.ARCHIVED),
        pair.keep_passport: (f"{ready}/Ivan_Petrov-Passport.pdf", 1, DocumentStatus.ACTIVE),
    }
    for document_id, (path, sequence_no, status) in expected.items():
        document = session.get_one(Document, document_id)
        assert document.employee_id == KEEP
        assert (document.path, document.sequence_no, document.status) == (
            path,
            sequence_no,
            status.value,
        )
        # K11: içerik bayt bayt aynı; R13: köken kaydı değişmez.
        assert sha256_file(layout.resolve(document.path)) == pair.hashes[document_id]
        assert document.source_refs_json[0]["pages"] == [0]
    assert _files(layout.ready_dir(MERGE_FOLDER)) == {}


def test_received_copies_move_and_a_taken_name_gets_a_suffix_nothing_is_deleted(
    session: Session, layout: DataLayout, pair: Pair
) -> None:
    result = _merge(session, layout)

    assert result.received == 2
    assert _files(layout.received_dir(KEEP_FOLDER)) == {
        "pasaport.pdf": pair.received["merge:pasaport.pdf"],
        "tarama-2.pdf": pair.received["merge:tarama.pdf"],
        "tarama.pdf": pair.received["keep:tarama.pdf"],
    }
    # R11: birleşenin klasörü ve dizinleri kalır, içleri boş.
    assert _files(layout.received_dir(MERGE_FOLDER)) == {}
    assert layout.employee_dir(MERGE_FOLDER).is_dir()
    assert layout.ready_dir(MERGE_FOLDER).is_dir()


# --- alt kayıtlar --------------------------------------------------------------------------------


def _rows[R: (EmployeeAlias, EmployeeIdentifier, EmployeeContact)](
    session: Session, model: type[R], employee_id: str
) -> list[R]:
    return list(
        session.scalars(select(model).where(model.employee_id == employee_id).order_by(model.id))
    )


def test_records_are_linked_and_the_same_value_stays_single_without_deleting(
    session: Session, layout: DataLayout, pair: Pair
) -> None:
    result = _merge(session, layout)

    assert result.records == RecordCounts(moved=4, closed=3)
    assert [(row.raw_name, row.removed_at) for row in _rows(session, EmployeeAlias, KEEP)] == [
        ("IVAN PETROV", None),
        ("IVAN PETROW", None),
    ]
    # Aynı normalize anahtar kalanda: Kiril yazım birleşende kalır, kaldırılmış işaretlenir.
    (closed_alias,) = _rows(session, EmployeeAlias, MERGE)
    assert (closed_alias.raw_name, closed_alias.removed_by) == (CYRILLIC, ACTOR)
    assert closed_alias.removed_at is not None

    assert [(row.value, row.removed_at) for row in _rows(session, EmployeeIdentifier, KEEP)] == [
        ("000000001", None),
        ("000000002", None),
    ]
    (closed_number,) = _rows(session, EmployeeIdentifier, MERGE)
    assert (closed_number.value, closed_number.removed_by) == ("000000001", ACTOR)

    contacts = {(row.kind, row.value): row for row in _rows(session, EmployeeContact, KEEP)}
    assert set(contacts) == {
        ("phone", "+90 555 000 0001"),
        ("phone", "+90 555 000 0002"),
        ("email", "ivan@example.test"),
    }
    # 05.8.2: türde tek güncel satır — en son görülen telefon birleşenden gelen.
    assert [key for key, row in contacts.items() if row.is_current] == [
        ("phone", "+90 555 000 0002"),
        ("email", "ivan@example.test"),
    ]
    # Aynı değer tek kalır: görülme zamanı kalandaki satıra katlanır.
    assert contacts[("phone", "+90 555 000 0001")].last_seen_at == _at(3)
    (closed_contact,) = _rows(session, EmployeeContact, MERGE)
    assert closed_contact.removed_by == ACTOR and not closed_contact.is_current


def test_a_value_already_removed_on_either_side_is_not_reopened(
    session: Session, layout: DataLayout, pair: Pair
) -> None:
    kept_number = _rows(session, EmployeeIdentifier, KEEP)[0]
    kept_number.removed_at, kept_number.removed_by = _at(2), "baska-ik"
    for merged_alias in _rows(session, EmployeeAlias, MERGE):
        merged_alias.removed_at, merged_alias.removed_by = _at(2), "baska-ik"
    session.commit()

    result = _merge(session, layout)

    # Kalanın kaldırdığı numara kalanda kaldırılmış kalır; birleşenin aynı numarası da kapanır.
    assert [(row.value, row.removed_by) for row in _rows(session, EmployeeIdentifier, KEEP)] == [
        ("000000001", "baska-ik"),
        ("000000002", None),
    ]
    assert _rows(session, EmployeeIdentifier, MERGE)[0].removed_by == ACTOR
    # Birleşende kaldırılmış yazım kalana kaldırılmış olarak gelir (geçmiş kaydı).
    moved_alias = _rows(session, EmployeeAlias, KEEP)[1]
    assert (moved_alias.raw_name, moved_alias.removed_by) == ("IVAN PETROW", "baska-ik")
    # Çakışan ama zaten kaldırılmış yazım birleşende olduğu gibi kalır (yeniden kapanmaz).
    (kept_on_merge,) = _rows(session, EmployeeAlias, MERGE)
    assert (kept_on_merge.raw_name, kept_on_merge.removed_by) == (CYRILLIC, "baska-ik")
    assert kept_on_merge.removed_at == _at(2)
    assert result.records == RecordCounts(moved=4, closed=2)


# --- alan kaynakları -----------------------------------------------------------------------------


def _observations(session: Session, employee_id: str) -> list[tuple[str, str, str, int | None]]:
    rows = session.scalars(
        select(EmployeeFieldObservation)
        .where(EmployeeFieldObservation.employee_id == employee_id)
        .order_by(EmployeeFieldObservation.id)
    )
    return [(row.field, row.outcome, row.source, row.file_id) for row in rows]


def test_empty_fields_are_filled_from_the_merged_record_and_the_sources_follow(
    session: Session, layout: DataLayout, pair: Pair
) -> None:
    file_id = session.get_one(Document, pair.passport).source_refs_json[0]["file_id"]

    result = _merge(session, layout)

    keep = session.get_one(Employee, KEEP)
    assert result.fields == ("original_script_name",)
    # 05.7.3 kuralı: boş alan dolar, dolu alan (diğer isimler, uyruk, doğum tarihi) değişmez.
    assert (keep.original_script_name, keep.other_names, keep.nationality) == (
        CYRILLIC,
        "Sergeevich",
        "RUS",
    )
    assert _observations(session, KEEP) == [
        ("date_of_birth", "same", "document", file_id),
        ("original_script_name", "filled", "document", file_id),
        # Birleşenin belgesi kalanınkinden farklı değer okudu: profil uyarısı.
        ("other_names", "conflict", "document", file_id),
        ("original_script_name", "filled", "merge", None),
    ]
    # Aynı kaynaktan gözlem kalanda var; elle düzenleme birleşenin kendi değerini anlatır.
    assert _observations(session, MERGE) == [
        ("date_of_birth", "same", "document", file_id),
        ("other_names", "filled", "manual", None),
    ]
    merge_observation = session.scalars(
        select(EmployeeFieldObservation).where(
            EmployeeFieldObservation.source == FieldSource.MERGE.value
        )
    ).one()
    assert merge_observation.actor == ACTOR
    (filled,) = _events(session, EventType.EMPLOYEE_FIELD_FILLED)
    assert (filled.employee_id, filled.actor) == (KEEP, ACTOR)
    assert filled.data_json == {
        "field": "original_script_name",
        "source": "merge",
        "rule": "10.5.9",
        "from_employee_id": MERGE,
    }


def test_a_manual_value_that_fills_the_kept_field_takes_its_source_along(
    session: Session, layout: DataLayout, pair: Pair
) -> None:
    # Birleşende elle girilmiş orijinal yazım: değer kalana geçtiği için gözlemi de geçer.
    _observation(
        session, MERGE, "original_script_name", FieldOutcome.FILLED, source=FieldSource.MANUAL
    )
    session.commit()

    _merge(session, layout)

    manual = [row for row in _observations(session, KEEP) if row[2] == "manual"]
    assert manual == [("original_script_name", "filled", "manual", None)]
    assert _observations(session, MERGE)[-1] == ("other_names", "filled", "manual", None)


def test_a_cancelled_package_moves_as_it_is_and_is_not_counted_as_a_duplicate(
    session: Session, layout: DataLayout, pair: Pair
) -> None:
    package = session.get_one(EmployeePackage, pair.visa_package)
    package.status = PackageStatus.CANCELLED.value
    session.commit()

    result = _merge(session, layout)

    assert result.cancelled_packages == ()
    moved = session.get_one(EmployeePackage, pair.visa_package)
    assert (moved.employee_id, moved.status) == (KEEP, PackageStatus.CANCELLED.value)
    assert _events(session, EventType.PACKAGE_CANCELLED) == []


def test_the_field_preview_tells_what_happens_to_each_field(session: Session, pair: Pair) -> None:
    keep, merge = session.get_one(Employee, KEEP), session.get_one(Employee, MERGE)

    assert merge_field_preview(keep, merge) == {
        "given_names": "same",
        "surname": "different",
        "other_names": "different",
        "original_script_name": "filled",
        "date_of_birth": "same",
        "nationality": "none",
    }
    assert merge_document_count(session, MERGE) == 4
    assert merge_document_count(session, KEEP) == 1


# --- belge paketleri -----------------------------------------------------------------------------


def test_packages_follow_the_kept_record_and_a_duplicate_group_is_cancelled(
    session: Session, layout: DataLayout, pair: Pair
) -> None:
    result = _merge(session, layout)

    assert result.packages == (pair.passport_package, pair.visa_package)
    assert result.cancelled_packages == (pair.visa_package,)
    packages = {
        package.id: package
        for package in session.scalars(select(EmployeePackage).order_by(EmployeePackage.id))
    }
    assert {package.employee_id for package in packages.values()} == {KEEP}
    # 14.2.2: kalanın etkin pasaportu kalemi karşılar; paket tamamlanır.
    assert packages[pair.passport_package].status == PackageStatus.COMPLETED.value
    # Aynı grubun paketi kalanda var: birleşenden gelen iptal edilir (silinmez, yeniden açılır).
    duplicate = packages[pair.visa_package]
    assert (duplicate.status, duplicate.cancelled_by, duplicate.cancel_note) == (
        PackageStatus.CANCELLED.value,
        ACTOR,
        DUPLICATE_PACKAGE_NOTE,
    )
    # Eski sürüm ve arşivdeki vize kalemi karşılamaz.
    assert packages[pair.keep_visa_package].status == PackageStatus.OPEN.value
    cancelled = _events(session, EventType.PACKAGE_CANCELLED)
    completed = _events(session, EventType.PACKAGE_COMPLETED)
    assert [event.data_json["package_id"] for event in cancelled] == [pair.visa_package]
    assert [event.data_json["package_id"] for event in completed] == [pair.passport_package]


# --- birleşen kayıt ve olay ----------------------------------------------------------------------


def test_the_merged_record_is_closed_and_one_event_carries_the_numbers_and_ids(
    session: Session, layout: DataLayout, pair: Pair
) -> None:
    result = _merge(session, layout)

    merge = session.get_one(Employee, MERGE)
    assert (merge.status, merge.merged_into_id) == (EmployeeStatus.MERGED.value, KEEP)
    # R11: birleşenin kendi alanları ve klasörü yerinde.
    assert (merge.given_names, merge.surname, merge.folder_name) == ("Ivan", "Petrow", MERGE_FOLDER)
    assert session.get_one(Employee, KEEP).merged_into_id is None
    (event,) = _events(session, EventType.EMPLOYEE_MERGED)
    assert event.id == result.event.id
    assert (event.employee_id, event.actor) == (KEEP, ACTOR)
    assert event.data_json == {
        "kept": KEEP,
        "merged": MERGE,
        "documents": [pair.passport, pair.residence, pair.superseded, pair.archived],
        "relocated": list(result.relocated),
        "received": 2,
        "records": {"moved": 4, "closed": 3},
        "fields": ["original_script_name"],
        "packages": [pair.passport_package, pair.visa_package],
        "cancelled_packages": [pair.visa_package],
    }
    # Belge başına taşıma olayı yazılmaz; olay verisi kişisel değer taşımaz.
    assert _events(session, EventType.MANUAL_MOVE) == []
    written = json.dumps(
        [row.data_json for row in session.scalars(select(Event))], ensure_ascii=False
    )
    for value in PERSONAL_VALUES:
        assert value not in written


def test_both_profiles_are_rendered_and_the_merged_one_only_points_to_the_kept_record(
    session: Session, layout: DataLayout, pair: Pair
) -> None:
    _merge(session, layout)

    for employee_id in (KEEP, MERGE):
        write_profile(session, layout, session.get_one(Employee, employee_id))
    merged = layout.profile_path(MERGE_FOLDER).read_text(encoding="utf-8")
    kept = layout.profile_path(KEEP_FOLDER).read_text(encoding="utf-8")

    assert f"Bu kayıt {KEEP} ile birleştirildi" in merged
    assert f"merged_into: {KEEP}" in merged and f"merged_into_folder: {KEEP_FOLDER}" in merged
    assert "status: merged" in merged
    assert "## Belgeler" not in merged and "Passport" not in merged
    for name in ("Ivan_Petrov-Passport-2.pdf", "Ivan_Petrov-Residence-Card.pdf"):
        assert name in kept
    assert "000000002" in kept and "Pasaport paketi" in kept


# --- geri alma ve ret ----------------------------------------------------------------------------


def test_a_failure_while_moving_files_undoes_the_moves_and_nothing_changes(
    session: Session, layout: DataLayout, pair: Pair, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_move = merge_module._move
    calls = {"count": 0}

    def failing_move(source: Path, target: Path) -> None:
        calls["count"] += 1
        if calls["count"] == 3:
            raise PermissionError("dosya açık")
        real_move(source, target)

    monkeypatch.setattr(merge_module, "_move", failing_move)
    before = {
        folder: (_files(layout.ready_dir(folder)), _files(layout.received_dir(folder)))
        for folder in (KEEP_FOLDER, MERGE_FOLDER)
    }
    keep, merge = session.get_one(Employee, KEEP), session.get_one(Employee, MERGE)

    with pytest.raises(EmployeeMergeError, match="geri alındı"):
        merge_employees(session, layout, keep, merge, actor=ACTOR)
    session.rollback()

    assert {
        folder: (_files(layout.ready_dir(folder)), _files(layout.received_dir(folder)))
        for folder in (KEEP_FOLDER, MERGE_FOLDER)
    } == before
    merge = session.get_one(Employee, MERGE)
    assert (merge.status, merge.merged_into_id) == (EmployeeStatus.ACTIVE.value, None)
    assert session.scalar(select(func.count()).where(Document.employee_id == MERGE)) == 4
    assert _events(session, EventType.EMPLOYEE_MERGED) == []
    assert session.get_one(Employee, KEEP).original_script_name is None


def test_merging_a_record_with_itself_or_a_merged_one_or_without_a_user_is_refused(
    session: Session, layout: DataLayout, pair: Pair
) -> None:
    keep, merge = session.get_one(Employee, KEEP), session.get_one(Employee, MERGE)

    with pytest.raises(SameEmployeeError):
        merge_employees(session, layout, keep, keep, actor=ACTOR)
    with pytest.raises(ValueError, match="actor"):
        merge_employees(session, layout, keep, merge, actor=" ")
    _merge(session, layout)
    third = _employee(session, "E0009", "Petrof")
    session.commit()
    for kept, merged in ((third, merge), (merge, third)):
        with pytest.raises(EmployeeAlreadyMergedError):
            merge_employees(session, layout, kept, merged, actor=ACTOR)
    assert len(_events(session, EventType.EMPLOYEE_MERGED)) == 1


# --- birleştirilmiş kayıt hiçbir yerde bulunmaz ---------------------------------------------------


def _key(number: str | None, *, surname: str = "PETROW") -> PersonKey:
    return PersonKey(
        document_numbers=() if number is None else (DocumentNumberKey(number, legible=True),),
        normalized_name=normalize_name("IVAN", surname),
        date_of_birth=BORN,
        original_script_name=None,
        normalized_original_name=None,
        mrz_allows_clean_document_number=True,
        conflicts=(),
        surname=surname,
        given_names="IVAN",
        date_of_birth_legible=True,
    )


def test_matching_finds_the_kept_record_and_never_a_merged_one(
    session: Session, layout: DataLayout, pair: Pair
) -> None:
    # Birleştirmeden önce aynı numara iki kayıtta: belirsiz.
    assert match_employee(session, _key("000000001")).rule is MatchRule.DOCUMENT_NUMBER_AMBIGUOUS
    _merge(session, layout)

    assert match_employee(session, _key("000000001")).employee_ids == (KEEP,)
    assert match_employee(session, _key("000000002")).employee_ids == (KEEP,)
    # Birleşenin yazımı kalana taşındı: ad + doğum tarihi kalanı bulur.
    by_name = match_employee(session, _key(None))
    assert (by_name.rule, by_name.employee_ids) == (MatchRule.NAME_DOB, (KEEP,))

    # Güvenlik süzgeci: birleşende kalmış etkin bir kayıt (elle yazılmış eski veri) bile sayılmaz.
    session.add(EmployeeIdentifier(employee_id=MERGE, kind="ru_passport", value="000000009"))
    session.add(
        EmployeeAlias(employee_id=MERGE, raw_name="IVAN PETROF", normalized_name="ivan petrof")
    )
    session.commit()
    assert match_employee(session, _key("000000009", surname="PETROF")).rule is MatchRule.NO_MATCH
    assert match_employee(session, _key(None, surname="PETROF")).rule is MatchRule.NO_MATCH


def test_a_document_is_not_moved_and_no_package_is_defined_on_a_merged_record(
    session: Session, layout: DataLayout, pair: Pair
) -> None:
    _merge(session, layout)
    third = _employee(session, "E0009", "Petrof")
    layout.ensure_employee_tree(third.folder_name)
    session.commit()
    passport = session.get_one(Document, pair.keep_passport)

    with pytest.raises(DocumentNotMovableError, match="birleştirildi"):
        move_document(session, layout, passport.id, MERGE, actor=ACTOR)
    session.rollback()
    with pytest.raises(PackageStateError, match="birleştirildi"):
        assign_package(session, MERGE, pair.passport_group, actor=ACTOR)
    session.rollback()
    assert session.get_one(Document, pair.keep_passport).employee_id == KEEP
