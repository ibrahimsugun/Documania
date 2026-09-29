"""10.5.9 — birleştirmenin dosya işleri (`app.storage.merge`): planın uç durumları ve taşımanın geri
alınması. Etkin belge K8 adını alır, eski sürüm adını korur ve gövdesi doluysa ek alır; dosyası
yerinde olmayan ya da yolu veri dizininden kaçan belgenin dosya işi yoktur; taşıma yarıda kalırsa
yapılanlar geri alınır, geri alma da düşerse hata bunu söyler (K8, K11, K18, R11; PLAN.md §D69).

Belgeler `tests/fixtures/gen.py`'nin sentetik PDF'leridir; gerçek kişi ya da belge yoktur.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import app.storage.merge as merge_module
from app.db.models import Base, Document, DocumentStatus, Employee, KnownDocumentType
from app.db.session import create_db_engine, create_session_factory
from app.storage import (
    DataLayout,
    EmployeeMergeError,
    FileMove,
    plan_employee_merge,
    prepare_data_dir,
    relocate_merged_files,
)
from tests.fixtures.gen import make_pdf_bytes

KEEP_FOLDER, MERGE_FOLDER = "Ivan_Petrov_E0001", "Ivan_Petrow_E0005"


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    db_engine = create_db_engine(f"sqlite:///{(tmp_path / 'merge-files.db').as_posix()}")
    Base.metadata.create_all(db_engine)
    yield db_engine
    db_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with create_session_factory(engine)() as db_session:
        yield db_session


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


@pytest.fixture
def pair(session: Session, layout: DataLayout) -> tuple[Employee, Employee]:
    session.add(
        KnownDocumentType(
            slug="visa",
            name="Vize",
            file_label="Visa",
            sides="single",
            direct=True,
            analyze=True,
            output_format="pdf",
        )
    )
    keep = Employee(id="E0001", folder_name=KEEP_FOLDER, given_names="Ivan", surname="Petrov")
    merge = Employee(id="E0005", folder_name=MERGE_FOLDER, given_names="Ivan", surname="Petrow")
    session.add_all([keep, merge])
    session.flush()
    for folder in (KEEP_FOLDER, MERGE_FOLDER):
        layout.ensure_employee_tree(folder)
    return keep, merge


def _document(
    session: Session, employee_id: str, path: str, *, status: DocumentStatus, sequence_no: int = 1
) -> Document:
    document = Document(
        employee_id=employee_id,
        type_slug="visa",
        path=path,
        format="pdf",
        sequence_no=sequence_no,
        source_refs_json=[{"file_id": 1, "pages": [0]}],
        status=status.value,
    )
    session.add(document)
    session.flush()
    return document


def test_an_old_version_keeps_its_name_and_takes_a_suffix_only_when_the_stem_is_taken(
    session: Session, layout: DataLayout, pair: tuple[Employee, Employee]
) -> None:
    keep, merge = pair
    # Kalanda aynı gövde (uzantısı farklı da olsa) dolu: `-2`, o da doluysa `-3`.
    (layout.ready_dir(KEEP_FOLDER) / "Ivan_Petrow-Visa.jpg").write_bytes(b"kalan")
    (layout.ready_dir(KEEP_FOLDER) / "Ivan_Petrow-Visa-2.pdf").write_bytes(b"kalan")
    old = layout.ready_dir(MERGE_FOLDER) / "Ivan_Petrow-Visa.pdf"
    old.write_bytes(make_pdf_bytes(2))
    no_suffix = layout.ready_dir(MERGE_FOLDER) / "Ivan_Petrow-Visa-Tarama"
    no_suffix.write_bytes(make_pdf_bytes(3))
    superseded = _document(
        session, merge.id, layout.relative(old), status=DocumentStatus.SUPERSEDED, sequence_no=4
    )
    # Uzantısı okunamayan etkin belge de K8 adına çevrilemez: adını korur.
    odd = _document(session, merge.id, layout.relative(no_suffix), status=DocumentStatus.ACTIVE)

    plan = plan_employee_merge(session, layout, keep, merge)

    paths = {document.document_id: document.path for document in plan.documents}
    ready = f"Employees/{KEEP_FOLDER}/Hazir"
    assert paths == {
        odd.id: f"{ready}/Ivan_Petrow-Visa-Tarama",
        superseded.id: f"{ready}/Ivan_Petrow-Visa-3.pdf",
    }
    # Eski sürümün sıra numarası değişmez (K18).
    assert {document.document_id: document.sequence_no for document in plan.documents} == {
        odd.id: 1,
        superseded.id: 4,
    }
    relocate_merged_files(layout, plan)
    assert (layout.ready_dir(KEEP_FOLDER) / "Ivan_Petrow-Visa-3.pdf").read_bytes() == (
        make_pdf_bytes(2)
    )
    assert not old.exists() and not no_suffix.exists()


def test_a_document_without_its_file_or_outside_the_data_dir_has_no_file_work(
    session: Session, layout: DataLayout, pair: tuple[Employee, Employee]
) -> None:
    keep, merge = pair
    _document(
        session,
        merge.id,
        f"Employees/{MERGE_FOLDER}/Hazir/Ivan_Petrow-Visa.pdf",
        status=DocumentStatus.ACTIVE,
    )
    _document(session, merge.id, "../disari/Ivan_Petrow-Visa.pdf", status=DocumentStatus.ACTIVE)
    # Birleşenin `Alinan/` klasörü hiç yok: taşınacak kopya da yok.
    layout.received_dir(MERGE_FOLDER).rmdir()

    plan = plan_employee_merge(session, layout, keep, merge)

    assert plan.documents == () and plan.received == ()
    relocate_merged_files(layout, plan)
    assert layout.received_dir(MERGE_FOLDER).is_dir()


def test_a_missing_target_directory_yields_an_empty_stem_set(
    session: Session, layout: DataLayout, pair: tuple[Employee, Employee]
) -> None:
    keep, merge = pair
    for directory in (layout.ready_dir(KEEP_FOLDER), layout.received_dir(KEEP_FOLDER)):
        directory.rmdir()
    source = layout.ready_dir(MERGE_FOLDER) / "Ivan_Petrow-Visa.pdf"
    source.write_bytes(make_pdf_bytes())
    document = _document(session, merge.id, layout.relative(source), status=DocumentStatus.ACTIVE)

    plan = plan_employee_merge(session, layout, keep, merge)
    relocate_merged_files(layout, plan)

    assert [each.path for each in plan.documents] == [
        f"Employees/{KEEP_FOLDER}/Hazir/Ivan_Petrov-Visa.pdf"
    ]
    assert plan.documents[0].document_id == document.id
    assert (layout.ready_dir(KEEP_FOLDER) / "Ivan_Petrov-Visa.pdf").is_file()


def test_a_move_that_cannot_drop_the_old_name_removes_the_new_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = tmp_path / "a.pdf", tmp_path / "b.pdf"
    source.write_bytes(b"icerik")
    real_unlink = Path.unlink

    def refuse_source(path: Path, missing_ok: bool = False) -> None:
        if path == source:
            raise PermissionError("açık")
        real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", refuse_source)

    with pytest.raises(PermissionError):
        merge_module._move(source, target)
    assert source.read_bytes() == b"icerik" and not target.exists()


def test_an_undo_that_also_fails_says_so(
    tmp_path: Path, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    moves = tuple(
        FileMove(tmp_path / f"{name}.pdf", tmp_path / f"{name}-kalan.pdf") for name in "ab"
    )
    for move in moves:
        move.source.write_bytes(b"icerik")
    plan = merge_module.EmployeeMergePlan(KEEP_FOLDER, MERGE_FOLDER, (), moves)
    calls = {"count": 0}
    real_move = merge_module._move

    def fail_after_first(source: Path, target: Path) -> None:
        calls["count"] += 1
        if calls["count"] > 1:
            raise OSError("disk")
        real_move(source, target)

    monkeypatch.setattr(merge_module, "_move", fail_after_first)

    with pytest.raises(EmployeeMergeError, match="geri alma tamamlanamadı"):
        relocate_merged_files(layout, plan)
