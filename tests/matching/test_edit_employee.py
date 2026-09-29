"""10.5.6 — çalışan profilini düzenleme: değişen alanlar yazılır, ad ya da soyad değişince klasör ve
`Hazir/`'daki etkin belge dosyaları K8 adına yeniden adlandırılır; köken bilgisi, içerik ve E
numarası değişmez; yeniden adlandırma yarıda kalırsa hiçbir şey değişmiş görünmez (PLAN.md §C90-a;
K8, K11, K16, K17, K18).

Birim testleri `update_employee_fields`'ı geçici SQLite ve geçici veri dizinindeki sentetik
çalışanla sınar: belgeler `tests/fixtures/gen.py`'nin sentetik PDF'leridir, gerçek kişi ya da
belge yoktur, ağ çağrısı yoktur. İki aşamalı onay ve sayfa
`tests/web/test_employee_fields.py`'dedir.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePath
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.storage.rename as rename_module
from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeAlias,
    EmployeeFieldObservation,
    Event,
    FieldOutcome,
    FieldSource,
    KnownDocumentType,
)
from app.events import EventType
from app.matching.edit import (
    EmployeeNotEditableError,
    NoFieldChangesError,
    changed_fields,
    current_profile_fields,
    preview_employee_edit,
    update_employee_fields,
)
from app.matching.fields import complete_profile_fields
from app.matching.match import (
    LATIN_ONLY_PROBLEM,
    ProfileFields,
    ProfileFieldsError,
)
from app.matching.names import normalize_name
from app.storage import DataLayout, EmployeeRenameError, sha256_file
from app.storage.rename import _rename
from tests.fixtures.gen import make_pdf_bytes
from tests.matching.test_profile_fields import _key, _source

ACTOR = "ik-yonetici"
EMPLOYEE_ID = "E0001"
OLD_FOLDER = "Ivan_Petrov_E0001"
NEW_FOLDER = "Ivan_Petrova_E0001"
BORN = date(1990, 1, 1)
SOURCE_REFS = [{"file_id": 7, "pages": [0, 1]}]
TYPES = (
    ("ru_passport", "Rus Pasaportu", "Passport"),
    ("residence_card", "İkamet Kartı", "Residence Card"),
    ("visa", "Vize", "Visa"),
)


@dataclass(frozen=True)
class Folder:
    """Sentetik çalışanın klasörü: etkin belgeler (iki pasaport, bir ikamet kartı), eski sürüm bir
    vize, arşivde bir belge, `Alinan/` kopyası ve `profil.md`."""

    passport: int
    passport_2: int
    residence: int
    superseded: int
    archived: int
    hashes: dict[str, str]


def _employee(session: Session, employee_id: str = EMPLOYEE_ID, **fields: Any) -> Employee:
    values: dict[str, Any] = {
        "given_names": "Ivan",
        "surname": "Petrov",
        "date_of_birth": BORN,
        "nationality": "RUS",
    } | fields
    folder = f"{values['given_names']}_{values['surname']}_{employee_id}"
    employee = Employee(id=employee_id, folder_name=folder, **values)
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


def _document(
    session: Session,
    layout: DataLayout,
    path: Path,
    *,
    slug: str,
    sequence_no: int = 1,
    status: DocumentStatus = DocumentStatus.ACTIVE,
    pages: int = 1,
) -> Document:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(make_pdf_bytes(pages))
    document = Document(
        employee_id=EMPLOYEE_ID,
        type_slug=slug,
        path=layout.relative(path),
        format="pdf",
        sequence_no=sequence_no,
        source_refs_json=SOURCE_REFS,
        status=status.value,
    )
    session.add(document)
    session.flush()
    return document


@pytest.fixture
def folder(session: Session, layout: DataLayout) -> Folder:
    _catalog(session)
    _employee(session)
    layout.ensure_employee_tree(OLD_FOLDER)
    ready = layout.ready_dir(OLD_FOLDER)
    passport = _document(session, layout, ready / "Ivan_Petrov-Passport.pdf", slug="ru_passport")
    passport_2 = _document(
        session,
        layout,
        ready / "Ivan_Petrov-Passport-2.pdf",
        slug="ru_passport",
        sequence_no=2,
        pages=2,
    )
    residence = _document(
        session, layout, ready / "Ivan_Petrov-Residence-Card.pdf", slug="residence_card", pages=3
    )
    superseded = _document(
        session,
        layout,
        ready / "Ivan_Petrov-Visa.pdf",
        slug="visa",
        status=DocumentStatus.SUPERSEDED,
        pages=4,
    )
    archived = _document(
        session,
        layout,
        layout.archive_dir(date(2026, 9, 1)) / "Ivan_Petrov-Visa-2.pdf",
        slug="visa",
        sequence_no=2,
        status=DocumentStatus.ARCHIVED,
        pages=5,
    )
    (layout.received_dir(OLD_FOLDER) / "tarama.pdf").write_bytes(make_pdf_bytes(6))
    layout.profile_path(OLD_FOLDER).write_text("# Ivan Petrov\n", encoding="utf-8")
    session.commit()
    hashes = {
        document.path: sha256_file(layout.resolve(document.path))
        for document in session.scalars(select(Document))
    }
    return Folder(
        passport.id, passport_2.id, residence.id, superseded.id, archived.id, hashes=hashes
    )


def _fields(employee: Employee, **changes: Any) -> ProfileFields:
    values = current_profile_fields(employee)
    return ProfileFields(
        **{
            "given_names": values.given_names,
            "surname": values.surname,
            "other_names": values.other_names,
            "original_script_name": values.original_script_name,
            "date_of_birth": values.date_of_birth,
            "nationality": values.nationality,
        }
        | changes
    )


def _edit(session: Session, layout: DataLayout, **changes: Any) -> Any:
    employee = session.get_one(Employee, EMPLOYEE_ID)
    return update_employee_fields(
        session, layout, employee, _fields(employee, **changes), actor=ACTOR
    )


def _tree(root: Path) -> dict[str, str]:
    """Veri dizinindeki her dosya → SHA-256 (göreli, `/` ayırıcılı)."""
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _state(session: Session) -> list[tuple[Any, ...]]:
    session.expire_all()
    employee = session.get_one(Employee, EMPLOYEE_ID)
    documents = session.scalars(select(Document).order_by(Document.id)).all()
    return [
        (employee.folder_name, employee.surname),
        *((doc.path, doc.sequence_no, doc.source_refs_json) for doc in documents),
        session.scalar(select(func.count()).select_from(Event)),
        session.scalar(select(func.count()).select_from(EmployeeFieldObservation)),
        session.scalar(select(func.count()).select_from(EmployeeAlias)),
    ]


def _edited_events(session: Session) -> list[Event]:
    return list(session.scalars(select(Event).where(Event.type == EventType.EMPLOYEE_EDITED.value)))


# --- yalnız alan: dosya taşınmaz --------------------------------------------------------------


def test_a_date_of_birth_change_writes_the_field_and_moves_no_file(
    session: Session, layout: DataLayout, folder: Folder
) -> None:
    before = _tree(layout.root)

    edited = _edit(session, layout, date_of_birth=date(1991, 2, 3))
    session.commit()

    assert (edited.changed, edited.renamed, edited.documents) == (("date_of_birth",), False, ())
    employee = session.get_one(Employee, EMPLOYEE_ID)
    assert employee.date_of_birth == date(1991, 2, 3)
    assert (employee.id, employee.folder_name) == (EMPLOYEE_ID, OLD_FOLDER)
    assert _tree(layout.root) == before
    (event,) = _edited_events(session)
    assert (event.actor, event.employee_id) == (ACTOR, EMPLOYEE_ID)
    assert event.data_json == {"fields": ["date_of_birth"], "renamed": False, "documents": []}
    (observation,) = session.scalars(select(EmployeeFieldObservation)).all()
    assert (
        observation.field,
        observation.outcome,
        observation.source,
        observation.actor,
        observation.file_id,
        observation.page_index,
    ) == ("date_of_birth", FieldOutcome.FILLED.value, FieldSource.MANUAL.value, ACTOR, None, None)


def test_every_changed_field_gets_its_own_manual_observation(
    session: Session, layout: DataLayout, folder: Folder
) -> None:
    edited = _edit(
        session,
        layout,
        other_names="Sergeevich",
        original_script_name="Иван Петров",
        nationality="KAZ",
    )
    session.commit()

    assert edited.changed == ("other_names", "original_script_name", "nationality")
    rows = session.scalars(select(EmployeeFieldObservation).order_by(EmployeeFieldObservation.id))
    assert [(row.field, row.source, row.actor) for row in rows] == [
        (name, "manual", ACTOR) for name in edited.changed
    ]
    employee = session.get_one(Employee, EMPLOYEE_ID)
    assert (employee.other_names, employee.original_script_name, employee.nationality) == (
        "Sergeevich",
        "Иван Петров",
        "KAZ",
    )


# --- ad değişince: K8 yeniden adlandırma --------------------------------------------------------


def test_a_surname_change_renames_the_folder_and_the_active_files_keeping_bytes_and_origin(
    session: Session, layout: DataLayout, folder: Folder
) -> None:
    edited = _edit(session, layout, surname="Petrova")
    session.commit()

    assert edited.changed == ("surname",)
    assert edited.renamed is True
    assert sorted(edited.documents) == sorted(
        [folder.passport, folder.passport_2, folder.residence]
    )
    employee = session.get_one(Employee, EMPLOYEE_ID)
    assert (employee.id, employee.folder_name) == (EMPLOYEE_ID, NEW_FOLDER)
    assert not layout.employee_dir(OLD_FOLDER).exists()

    expected = {
        folder.passport: (f"Employees/{NEW_FOLDER}/Hazir/Ivan_Petrova-Passport.pdf", 1),
        folder.passport_2: (f"Employees/{NEW_FOLDER}/Hazir/Ivan_Petrova-Passport-2.pdf", 2),
        folder.residence: (f"Employees/{NEW_FOLDER}/Hazir/Ivan_Petrova-Residence-Card.pdf", 1),
        # K18: eski sürüm yeniden adlandırılmaz, yalnız klasörüyle taşınır.
        folder.superseded: (f"Employees/{NEW_FOLDER}/Hazir/Ivan_Petrov-Visa.pdf", 1),
        # Arşivdeki belge çalışan klasöründe değil; adı tarihseldir.
        folder.archived: ("Archive/2026-09/Ivan_Petrov-Visa-2.pdf", 2),
    }
    old_paths = {
        folder.passport: f"Employees/{OLD_FOLDER}/Hazir/Ivan_Petrov-Passport.pdf",
        folder.passport_2: f"Employees/{OLD_FOLDER}/Hazir/Ivan_Petrov-Passport-2.pdf",
        folder.residence: f"Employees/{OLD_FOLDER}/Hazir/Ivan_Petrov-Residence-Card.pdf",
        folder.superseded: f"Employees/{OLD_FOLDER}/Hazir/Ivan_Petrov-Visa.pdf",
        folder.archived: "Archive/2026-09/Ivan_Petrov-Visa-2.pdf",
    }
    for document_id, (path, sequence_no) in expected.items():
        document = session.get_one(Document, document_id)
        assert (document.path, document.sequence_no) == (path, sequence_no)
        assert document.source_refs_json == SOURCE_REFS  # köken değişmez
        assert document.employee_id == EMPLOYEE_ID
        # K11: içerik bayt bayt aynı.
        assert sha256_file(layout.resolve(path)) == folder.hashes[old_paths[document_id]]
    # Alinan kopyası yüklemedeki adını korur (K10), klasörle gelir; profil.md de.
    assert (layout.received_dir(NEW_FOLDER) / "tarama.pdf").is_file()
    assert layout.profile_path(NEW_FOLDER).is_file()
    assert sorted(path.name for path in layout.ready_dir(NEW_FOLDER).iterdir()) == [
        "Ivan_Petrov-Visa.pdf",
        "Ivan_Petrova-Passport-2.pdf",
        "Ivan_Petrova-Passport.pdf",
        "Ivan_Petrova-Residence-Card.pdf",
    ]
    (event,) = _edited_events(session)
    assert event.data_json["fields"] == ["surname"]
    assert event.data_json["renamed"] is True
    assert sorted(event.data_json["documents"]) == sorted(edited.documents)


def test_the_preview_counts_the_files_that_will_be_renamed_and_writes_nothing(
    session: Session, layout: DataLayout, folder: Folder
) -> None:
    employee = session.get_one(Employee, EMPLOYEE_ID)
    before, state = _tree(layout.root), _state(session)

    renaming = preview_employee_edit(
        session, layout, employee, _fields(employee, surname="Petrova")
    )
    staying = preview_employee_edit(session, layout, employee, _fields(employee, nationality="KAZ"))

    assert (renaming.changed, renaming.renamed, renaming.documents) == (("surname",), True, 3)
    assert (staying.changed, staying.renamed, staying.documents) == (("nationality",), False, 0)
    assert _tree(layout.root) == before
    assert _state(session) == state


def test_a_name_that_gives_the_same_folder_renames_nothing(
    session: Session, layout: DataLayout, folder: Folder
) -> None:
    # Aksan ve harf büyüklüğü klasör adını değiştirmez (00.4.2): dosyalar yerinde kalır.
    before = _tree(layout.root)

    edited = _edit(session, layout, given_names="Iván")
    session.commit()

    assert (edited.changed, edited.renamed) == (("given_names",), False)
    assert session.get_one(Employee, EMPLOYEE_ID).folder_name == OLD_FOLDER
    assert _tree(layout.root) == before


def test_a_file_name_taken_by_another_file_gets_the_first_free_sequence(
    session: Session, layout: DataLayout, folder: Folder
) -> None:
    # Hazir'da yeni gövdeyle bir dosya zaten var (ör. önceki bir ad değişikliğinin eski sürümü):
    # üzerine yazılmaz, `write_sequenced`'ın kuralıyla ilk boş ek seçilir.
    stray = layout.ready_dir(OLD_FOLDER) / "Ivan_Petrova-Passport.pdf"
    stray.write_bytes(b"baska dosya")

    _edit(session, layout, surname="Petrova")
    session.commit()

    ready = layout.ready_dir(NEW_FOLDER)
    assert (ready / "Ivan_Petrova-Passport.pdf").read_bytes() == b"baska dosya"
    first = session.get_one(Document, folder.passport)
    second = session.get_one(Document, folder.passport_2)
    assert (PurePath(first.path).name, first.sequence_no) == ("Ivan_Petrova-Passport-2.pdf", 2)
    assert (PurePath(second.path).name, second.sequence_no) == ("Ivan_Petrova-Passport-3.pdf", 3)
    assert (
        sha256_file(layout.resolve(second.path))
        == folder.hashes[f"Employees/{OLD_FOLDER}/Hazir/Ivan_Petrov-Passport-2.pdf"]
    )


def test_a_document_whose_file_is_missing_only_follows_the_folder(
    session: Session, layout: DataLayout, folder: Folder
) -> None:
    # Dosyası yerinde olmayan belge yeniden adlandırılamaz: yolu yeni klasörü gösterir, adı kalır.
    missing = session.get_one(Document, folder.residence)
    layout.resolve(missing.path).unlink()

    edited = _edit(session, layout, surname="Petrova")
    session.commit()

    assert folder.residence not in edited.documents
    assert sorted(edited.documents) == sorted([folder.passport, folder.passport_2])
    assert session.get_one(Document, folder.residence).path == (
        f"Employees/{NEW_FOLDER}/Hazir/Ivan_Petrov-Residence-Card.pdf"
    )


def test_two_employees_given_the_same_new_name_keep_their_own_folders(
    session: Session, layout: DataLayout, folder: Folder
) -> None:
    other = _employee(session, "E0002", given_names="Anna", surname="Smirnova")
    layout.ensure_employee_tree(other.folder_name)
    session.commit()

    _edit(session, layout, given_names="Anna", surname="Smirnova")
    session.commit()

    folders = dict(session.execute(select(Employee.id, Employee.folder_name)).all())
    assert folders == {"E0001": "Anna_Smirnova_E0001", "E0002": "Anna_Smirnova_E0002"}
    assert layout.employee_dir("Anna_Smirnova_E0001").is_dir()
    assert layout.employee_dir("Anna_Smirnova_E0002").is_dir()


def test_an_interrupted_rename_restores_every_file_and_leaves_no_row_changed(
    session: Session, layout: DataLayout, folder: Folder, monkeypatch: pytest.MonkeyPatch
) -> None:
    before, state = _tree(layout.root), _state(session)
    calls: list[tuple[Path, Path]] = []

    def failing_rename(source: Path, target: Path) -> None:
        calls.append((source, target))
        if len(calls) == 3:  # klasör ve bir dosya taşındı, ikinci dosyada disk hatası
            raise PermissionError("dosya başka bir süreçte açık")
        _rename(source, target)

    monkeypatch.setattr(rename_module, "_rename", failing_rename)

    with pytest.raises(EmployeeRenameError, match="geri alındı"):
        _edit(session, layout, surname="Petrova")
    session.rollback()

    assert len(calls) > 3  # geri alma adımları da çalıştı
    assert _tree(layout.root) == before
    assert not layout.employee_dir(NEW_FOLDER).exists()
    assert _state(session) == state
    assert _edited_events(session) == []


def test_an_existing_target_folder_stops_the_rename_before_anything_moves(
    session: Session, layout: DataLayout, folder: Folder
) -> None:
    layout.employee_dir(NEW_FOLDER).mkdir()
    before, state = _tree(layout.root), _state(session)

    with pytest.raises(EmployeeRenameError, match="zaten var"):
        _edit(session, layout, surname="Petrova")
    session.rollback()

    assert _tree(layout.root) == before
    assert _state(session) == state


def test_a_case_only_rename_goes_through_a_temporary_name(tmp_path: Path) -> None:
    # Windows'ta yalnız harf büyüklüğü değişen ad aynı giriştir: iki adımda değiştirilir.
    source = tmp_path / "ivan_petrov-passport.pdf"
    source.write_bytes(b"icerik")

    _rename(source, tmp_path / "Ivan_Petrov-Passport.pdf")

    assert [path.name for path in tmp_path.iterdir()] == ["Ivan_Petrov-Passport.pdf"]
    assert (tmp_path / "Ivan_Petrov-Passport.pdf").read_bytes() == b"icerik"


def test_a_rename_never_overwrites_another_file(tmp_path: Path) -> None:
    source, target = tmp_path / "a.pdf", tmp_path / "b.pdf"
    source.write_bytes(b"a")
    target.write_bytes(b"b")

    with pytest.raises(FileExistsError):
        _rename(source, target)

    assert (source.read_bytes(), target.read_bytes()) == (b"a", b"b")


# --- denetim: hiçbir şey yazılmaz ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "field", "problem"),
    [
        ({"given_names": "Иван"}, "given_names", LATIN_ONLY_PROBLEM),
        ({"surname": " "}, "surname", "boş olamaz"),
        ({"other_names": "Сергеевич"}, "other_names", LATIN_ONLY_PROBLEM),
        ({"date_of_birth": date(2999, 1, 1)}, "date_of_birth", "gelecekte olamaz"),
        ({"nationality": "rus1"}, "nationality", "ICAO"),
        ({"given_names": "!!!", "surname": "???"}, "given_names", "harf ya da rakam"),
    ],
)
def test_invalid_fields_are_refused_and_nothing_changes(
    session: Session,
    layout: DataLayout,
    folder: Folder,
    changes: dict[str, Any],
    field: str,
    problem: str,
) -> None:
    before, state = _tree(layout.root), _state(session)

    with pytest.raises(ProfileFieldsError) as refused:
        _edit(session, layout, **changes)
    session.rollback()

    assert problem in refused.value.errors[field]
    assert _tree(layout.root) == before
    assert _state(session) == state


def test_an_unchanged_form_is_refused(session: Session, layout: DataLayout, folder: Folder) -> None:
    employee = session.get_one(Employee, EMPLOYEE_ID)
    assert changed_fields(employee, _fields(employee)) == ()

    with pytest.raises(NoFieldChangesError):
        _edit(session, layout)


def test_a_merged_employee_is_not_edited(
    session: Session, layout: DataLayout, folder: Folder
) -> None:
    session.get_one(Employee, EMPLOYEE_ID).status = "merged"
    session.flush()

    with pytest.raises(EmployeeNotEditableError):
        _edit(session, layout, surname="Petrova")


def test_an_empty_actor_is_refused(session: Session, layout: DataLayout, folder: Folder) -> None:
    employee = session.get_one(Employee, EMPLOYEE_ID)

    with pytest.raises(ValueError, match="actor"):
        update_employee_fields(
            session, layout, employee, _fields(employee, surname="Petrova"), actor=" "
        )


# --- eşleştirme ve 05.7.3 -----------------------------------------------------------------------


def test_the_new_spelling_is_added_as_an_alias_and_old_ones_stay(
    session: Session, layout: DataLayout, folder: Folder
) -> None:
    session.add(
        EmployeeAlias(
            employee_id=EMPLOYEE_ID,
            raw_name="Ivan Petrov",
            normalized_name=normalize_name("Ivan", "Petrov"),
            script="latin",
        )
    )
    session.flush()

    _edit(session, layout, surname="Petrova", original_script_name="Иван Петрова")
    session.commit()

    aliases = {
        row.raw_name: (row.normalized_name, row.script)
        for row in session.scalars(select(EmployeeAlias))
    }
    assert aliases == {
        "Ivan Petrov": (normalize_name("Ivan", "Petrov"), "latin"),
        "Ivan Petrova": (normalize_name("Ivan", "Petrova"), "latin"),
        "Иван Петрова": (normalize_name("Иван Петрова"), "cyrillic"),
    }


def test_a_later_document_does_not_overwrite_a_manual_field_and_is_a_conflict(
    session: Session, layout: DataLayout, folder: Folder
) -> None:
    # 05.7.3: elle girilen değer doludur; farklı okuyan belge alanı değiştirmez, çakışma olur.
    _edit(session, layout, given_names="Test", surname="Ornekova", nationality="KAZ")
    session.commit()

    completion = complete_profile_fields(
        session,
        _key(),  # TEST ORNEKOVA, RUS, 1990-01-01
        employee_id=EMPLOYEE_ID,
        file_id=_source(session),
        page_index=0,
    )
    session.commit()

    employee = session.get_one(Employee, EMPLOYEE_ID)
    assert (employee.given_names, employee.surname, employee.nationality) == (
        "Test",
        "Ornekova",
        "KAZ",
    )
    assert "nationality" in completion.conflicts
    assert {"given_names", "surname"} <= set(completion.same)
    rows = session.scalars(
        select(EmployeeFieldObservation).where(EmployeeFieldObservation.field == "nationality")
    ).all()
    assert [(row.source, row.outcome) for row in rows] == [
        ("manual", "filled"),
        ("document", "conflict"),
    ]


def test_neither_the_event_nor_the_observations_carry_values(
    session: Session, layout: DataLayout, folder: Folder
) -> None:
    _edit(
        session,
        layout,
        surname="Petrova",
        date_of_birth=date(1991, 2, 3),
        original_script_name="Иван Петрова",
    )
    session.commit()

    logged = json.dumps(
        [[event.message, event.data_json] for event in session.scalars(select(Event))],
        ensure_ascii=False,
    )
    for value in ("Petrova", "Petrov", "Иван", "1991", "Ivan"):
        assert value not in logged
    assert set(EmployeeFieldObservation.__table__.columns.keys()) >= {"source", "actor"}
    assert "value" not in EmployeeFieldObservation.__table__.columns.keys()
