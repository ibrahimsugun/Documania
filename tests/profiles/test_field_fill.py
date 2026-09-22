"""05.7.3 — geçmiş veri: mevcut çalışanların etkin belgeleri en eski önce, boru hattının kuralıyla
işlenir (`app.profiles.field_fill`, `python -m app.profiles fill-fields`).

Boş alan onu ilk okuyan belgeden dolar, dolu alan değişmez; komut tekrar çalıştırılabilir. Belgeler
ve sayfa analizleri sentetiktir; gerçek kişi yok.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeFieldObservation,
    Event,
    KnownDocumentType,
    Page,
    Upload,
    UploadFile,
)
from app.events import EventType
from app.profiles.__main__ import main
from app.profiles.field_fill import ProfileFieldFill, fill_profile_fields
from app.storage import DataLayout
from tests.ai.payloads import analysis_payload

ACTOR = "ik.admin"
FOLDER = "Test_Ornekova_E0001"
PASSPORT = "russian_passport"
BORN = date(1990, 1, 1)
# Kişisel değerler: komut çıktısında ve olay verisinde geçmez.
PERSONAL_VALUES = ("ORNEKOVA", "Ornekova", "TEST", "Орнекова", "1990-01-01", "1991-02-02", "RUS")


def _employee(session: Session, employee_id: str = "E0001", **fields: Any) -> Employee:
    values: dict[str, Any] = {"given_names": "Test", "surname": "Ornekova"} | fields
    folder = FOLDER if employee_id == "E0001" else f"Test_Ornekova_{employee_id}"
    employee = Employee(id=employee_id, folder_name=folder, **values)
    session.add(employee)
    session.flush()
    return employee


def _payload(index: int = 0, **person: Any) -> dict[str, Any]:
    payload = analysis_payload(page_index=index)
    payload["person"].update(person)
    return payload


def _document(
    session: Session,
    employee_id: str,
    *pages: dict[str, Any] | None,
    created_at: datetime,
    status: DocumentStatus = DocumentStatus.ACTIVE,
    analysis_status: str = "done",
    source_refs: Any = None,
) -> tuple[Document, int]:
    """Çalışanın belgesi; kaynak dosyanın sayfaları verilen analizleri taşır (`None`: analizsiz)."""
    if session.get(KnownDocumentType, PASSPORT) is None:
        session.add(
            KnownDocumentType(
                slug=PASSPORT,
                name="Russian Passport",
                file_label="Passport",
                sides="single",
                direct=True,
                analyze=True,
                output_format="keep",
            )
        )
    upload_id = f"u_20260915_{len(session.scalars(select(Upload)).all()) + 1:04d}"
    upload_file = UploadFile(
        upload=Upload(id=upload_id, channel="web", created_at=created_at),
        original_name="pasaport.pdf",
        stored_path=f"Inbox/{upload_id}/pasaport.pdf",
        sha256="0" * 64,
        mime="application/pdf",
    )
    session.add(upload_file)
    for index, analysis in enumerate(pages):
        session.add(
            Page(
                file=upload_file,
                index=index,
                analysis_json=analysis,
                analysis_status=analysis_status if analysis is not None else "pending",
            )
        )
    session.flush()
    document = Document(
        employee_id=employee_id,
        type_slug=PASSPORT,
        path=f"Employees/{FOLDER}/Hazir/Test_Ornekova-Passport-{upload_id}.pdf",
        format="pdf",
        source_refs_json=(
            [{"file_id": upload_file.id, "pages": list(range(len(pages)))}]
            if source_refs is None
            else source_refs
        ),
        status=status.value,
        created_at=created_at,
    )
    session.add(document)
    session.flush()
    return document, upload_file.id


def _at(day: int) -> datetime:
    return datetime(2026, 9, day, 12, 0, tzinfo=UTC)


def _observations(session: Session) -> list[tuple[str, str, str, int, int]]:
    rows = session.scalars(select(EmployeeFieldObservation).order_by(EmployeeFieldObservation.id))
    return [(row.employee_id, row.field, row.outcome, row.file_id, row.page_index) for row in rows]


def _filled_events(session: Session) -> list[Event]:
    return list(
        session.scalars(
            select(Event)
            .where(Event.type == EventType.EMPLOYEE_FIELD_FILLED.value)
            .order_by(Event.id)
        )
    )


def _filled(field: str) -> dict[str, str]:
    return {"field": field, "source": "document", "rule": "05.7.3"}


def _assert_no_personal_values(text: str) -> None:
    for value in PERSONAL_VALUES:
        assert value not in text


# --- sıra ve kural ----------------------------------------------------------------------------


def test_the_oldest_document_fills_first_and_a_later_different_value_is_a_conflict(
    session: Session,
) -> None:
    employee = _employee(session)
    # Yeni belge önce eklendi: sıra kimlikle değil oluşturulma zamanıyla verilir.
    newer, newer_file = _document(
        session, "E0001", _payload(date_of_birth="1991-02-02"), created_at=_at(20)
    )
    older, older_file = _document(session, "E0001", _payload(), created_at=_at(10))

    fills = fill_profile_fields(session, actor=ACTOR)

    assert fills == [
        ProfileFieldFill(
            employee_id="E0001",
            documents=2,
            filled=("original_script_name", "date_of_birth", "nationality"),
            conflicts=("date_of_birth",),
        )
    ]
    assert (employee.date_of_birth, employee.nationality) == (BORN, "RUS")
    assert employee.original_script_name == "Орнекова Тест"
    assert (employee.given_names, employee.surname) == ("Test", "Ornekova")
    assert _observations(session) == [
        ("E0001", "given_names", "same", older_file, 0),
        ("E0001", "surname", "same", older_file, 0),
        ("E0001", "original_script_name", "filled", older_file, 0),
        ("E0001", "date_of_birth", "filled", older_file, 0),
        ("E0001", "nationality", "filled", older_file, 0),
        ("E0001", "given_names", "same", newer_file, 0),
        ("E0001", "surname", "same", newer_file, 0),
        ("E0001", "original_script_name", "same", newer_file, 0),
        ("E0001", "date_of_birth", "conflict", newer_file, 0),
        ("E0001", "nationality", "same", newer_file, 0),
    ]
    events = _filled_events(session)
    assert [
        (e.document_id, e.file_id, e.page_index, e.employee_id, e.actor, e.data_json)
        for e in events
    ] == [
        (older.id, older_file, 0, "E0001", ACTOR, _filled(name))
        for name in ("original_script_name", "date_of_birth", "nationality")
    ]
    assert newer.id != older.id
    _assert_no_personal_values(json.dumps([e.data_json for e in events], ensure_ascii=False))


def test_second_run_writes_nothing(session: Session) -> None:
    employee = _employee(session)
    _document(session, "E0001", _payload(), created_at=_at(10))
    fill_profile_fields(session)
    rows, events = _observations(session), len(_filled_events(session))

    fills = fill_profile_fields(session)

    assert fills == [ProfileFieldFill("E0001", documents=1, filled=(), conflicts=())]
    assert _observations(session) == rows
    assert len(_filled_events(session)) == events
    assert employee.date_of_birth == BORN


def test_a_source_the_pipeline_already_observed_is_not_observed_again(session: Session) -> None:
    # Boru hattı belgeyi planlarken doğum tarihini bu kaynaktan gözlemişti (05.7.3).
    employee = _employee(session)
    _, file_id = _document(session, "E0001", _payload(), created_at=_at(10))
    session.add(
        EmployeeFieldObservation(
            employee_id="E0001",
            field="date_of_birth",
            outcome="conflict",
            file_id=file_id,
            page_index=0,
        )
    )
    session.flush()

    (fill,) = fill_profile_fields(session)

    assert "date_of_birth" not in (*fill.filled, *fill.conflicts)
    assert employee.date_of_birth is None
    assert [field for _, field, *_ in _observations(session)].count("date_of_birth") == 1


def test_the_key_reads_every_source_page_of_the_document(session: Session) -> None:
    # Kartın ön yüzü uyruğu, arka yüzü doğum tarihini okur: kaynak ilk sayfadır.
    employee = _employee(session)
    front = _payload(0, date_of_birth=None)
    back = _payload(1, nationality=None, original_script_name=None)
    _, file_id = _document(session, "E0001", front, back, created_at=_at(10))

    (fill,) = fill_profile_fields(session)

    assert fill.filled == ("original_script_name", "date_of_birth", "nationality")
    assert (employee.date_of_birth, employee.nationality) == (BORN, "RUS")
    assert {(source, page) for *_, source, page in _observations(session)} == {(file_id, 0)}


@pytest.mark.parametrize(
    "build",
    [
        lambda s: _document(
            s, "E0001", _payload(), created_at=_at(10), status=DocumentStatus.SUPERSEDED
        ),
        lambda s: _document(
            s, "E0001", _payload(), created_at=_at(10), status=DocumentStatus.ARCHIVED
        ),
        lambda s: _document(s, "E0001", _payload(), created_at=_at(10), analysis_status="failed"),
        lambda s: _document(s, "E0001", _payload(), None, created_at=_at(10)),
        lambda s: _document(s, "E0001", {"page_index": 0}, created_at=_at(10)),
        lambda s: _document(s, "E0001", _payload(), created_at=_at(10), source_refs=[]),
        lambda s: _document(
            s, "E0001", _payload(), created_at=_at(10), source_refs=[{"file_id": "x"}]
        ),
        lambda s: _document(
            s, "E0001", _payload(), created_at=_at(10), source_refs=[{"file_id": 1, "pages": []}]
        ),
        lambda s: _document(s, "E0001", created_at=_at(10)),
        lambda s: _document(
            s, "E0001", _payload(), created_at=_at(10), source_refs={"file_id": 1, "pages": [0]}
        ),
        lambda s: _document(
            s, "E0001", _payload(), created_at=_at(10), source_refs=[{"file_id": 1, "pages": ["0"]}]
        ),
    ],
    ids=[
        "superseded",
        "archived",
        "analysis-failed",
        "page-without-analysis",
        "analysis-off-schema",
        "no-source",
        "corrupt-source",
        "source-without-pages",
        "attachment-without-pages",
        "source-not-a-list",
        "page-not-a-number",
    ],
)
def test_documents_without_a_trustworthy_reading_are_skipped(session: Session, build) -> None:
    employee = _employee(session)
    build(session)

    assert fill_profile_fields(session) == []
    assert employee.date_of_birth is None
    assert _observations(session) == []


def test_employees_are_processed_in_employee_number_order(session: Session) -> None:
    for employee_id in ("E10000", "E9999"):
        _employee(session, employee_id)
        _document(session, employee_id, _payload(), created_at=_at(10))

    fills = fill_profile_fields(session)

    assert [fill.employee_id for fill in fills] == ["E9999", "E10000"]


# --- komut ----------------------------------------------------------------------------------------


@pytest.fixture
def environment(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[DataLayout]:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("DATABASE_URL", str(engine.url))
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    get_settings.cache_clear()
    yield DataLayout(data_dir)
    get_settings.cache_clear()


def test_command_fills_commits_rewrites_the_profile_and_is_repeatable(
    environment: DataLayout,
    session: Session,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _employee(session)
    _document(session, "E0001", _payload(), created_at=_at(10))
    _document(session, "E0001", _payload(nationality="SRB"), created_at=_at(20))
    session.commit()
    environment.ensure_employee_tree(FOLDER)

    assert main(["fill-fields", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert (
        "E0001: 2 belge; doldurulan original_script_name, date_of_birth, nationality; "
        "belgede farklı değer: nationality"
    ) in out
    assert (
        "Profil alanı tamamlama: 1 çalışanın belgeleri işlendi, 1 çalışanda alan doldurulacak."
    ) in out
    session.expire_all()
    assert session.get_one(Employee, "E0001").date_of_birth is None
    assert _observations(session) == []
    session.rollback()  # okuma işlemi yazma kilidini tutmasın (BEGIN IMMEDIATE)

    assert main(["fill-fields", "--actor", ACTOR]) == 0
    out = capsys.readouterr().out
    assert "1 çalışanda alan dolduruldu." in out
    _assert_no_personal_values(out)
    session.expire_all()
    employee = session.get_one(Employee, "E0001")
    assert (employee.date_of_birth, employee.nationality) == (BORN, "RUS")
    assert {event.actor for event in _filled_events(session)} == {ACTOR}
    session.rollback()
    profile = environment.profile_path(FOLDER).read_text(encoding="utf-8")
    assert "| Doğum tarihi | 1990-01-01 |" in profile
    assert "| Vatandaşlık | RUS |" in profile

    assert main(["fill-fields"]) == 0
    out = capsys.readouterr().out
    assert "E0001: 2 belge; doldurulan yok" in out
    assert "0 çalışanda alan dolduruldu." in out
