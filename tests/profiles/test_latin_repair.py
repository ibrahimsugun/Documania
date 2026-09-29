"""05.2.2 — Latin ad onarımı (`app.profiles.latin_names`, `python -m app.profiles`).

Latin alanında Latin olmayan harf taşıyan eski kayıt tekrar çalıştırılabilir onarımla düzelir:
yazım orijinal yazıma taşınır (boşsa), Latin yazım çalışanın Latin isim yazımından ya da Kiril
çevirisinden bulunur, bulunamazsa alan değişmez; değişen her alan için olay yazılır. Kayıtlar
sentetiktir; gerçek kişi yok.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    Document,
    Employee,
    EmployeeAlias,
    Event,
    KnownDocumentType,
    Page,
    Upload,
    UploadFile,
)
from app.events import EventType
from app.matching.names import normalize_name
from app.profiles.cli import main
from app.profiles.latin_names import (
    LatinRepair,
    RepairSource,
    needs_latin_repair,
    repair_latin_names,
)
from app.storage import DataLayout

ACTOR = "ik.admin"
FOLDER = "Test_Ornekova_E0001"
# Kişisel değerler: olay verisinde ve komut çıktısında geçmez.
PERSONAL_VALUES = ("ТЕСТ", "ОРНЕКОВА", "TEST", "ORNEKOVA", "Ornekova", "МАРКО", "علي")


def _employee(
    session: Session,
    employee_id: str = "E0001",
    *,
    given_names: str = "ТЕСТ",
    surname: str = "ОРНЕКОВА",
    other_names: str | None = None,
    original_script_name: str | None = None,
    folder_name: str = FOLDER,
    aliases: tuple[str, ...] = (),
) -> Employee:
    employee = Employee(
        id=employee_id,
        folder_name=folder_name,
        given_names=given_names,
        surname=surname,
        other_names=other_names,
        original_script_name=original_script_name,
    )
    session.add(employee)
    for raw in aliases:
        session.add(
            EmployeeAlias(employee=employee, raw_name=raw, normalized_name=normalize_name(raw))
        )
    session.flush()
    return employee


def _document(session: Session, employee_id: str, *pages: tuple[str | None, str]) -> None:
    """Çalışanın belgesi; kaynak sayfaların analizi (dil, alfabe) verilen gibidir."""
    if session.get(KnownDocumentType, "russian_passport") is None:
        session.add(
            KnownDocumentType(
                slug="russian_passport",
                name="Russian Passport",
                file_label="Passport",
                sides="single",
                direct=True,
                analyze=True,
                output_format="keep",
            )
        )
    upload_id = f"u_20260915_{len(session.scalars(select(Upload)).all()) + 1:04d}"
    upload = Upload(id=upload_id, channel="web")
    upload_file = UploadFile(
        upload=upload,
        original_name="pasaport.pdf",
        stored_path=f"Inbox/{upload_id}/pasaport.pdf",
        sha256="0" * 64,
        mime="application/pdf",
    )
    session.add(upload_file)
    for index, (language, script) in enumerate(pages):
        session.add(
            Page(
                file=upload_file,
                index=index,
                analysis_json={"language": language, "script": script},
                analysis_status="done",
            )
        )
    session.flush()
    session.add(
        Document(
            employee_id=employee_id,
            type_slug="russian_passport",
            path=f"Employees/{FOLDER}/Hazir/Test_Ornekova-Passport.pdf",
            format="pdf",
            source_refs_json=[{"file_id": upload_file.id, "pages": list(range(len(pages)))}],
        )
    )
    session.flush()


def _names(employee: Employee) -> tuple[str | None, ...]:
    return (
        employee.given_names,
        employee.other_names,
        employee.surname,
        employee.original_script_name,
    )


def _events(session: Session) -> list[Event]:
    return list(session.scalars(select(Event).order_by(Event.id)))


def _event_data(session: Session) -> list[tuple[str | None, str, dict[str, Any] | None]]:
    return [(event.employee_id, event.actor, event.data_json) for event in _events(session)]


def _filled(field: str, source: RepairSource) -> dict[str, str]:
    return {"field": field, "source": source.value, "rule": "05.2.2"}


def _assert_no_personal_values(text: str) -> None:
    for value in PERSONAL_VALUES:
        assert value not in text


# --- onarım ---------------------------------------------------------------------------------------


def test_cyrillic_latin_fields_are_transliterated_and_moved_to_the_original(
    session: Session,
) -> None:
    # E0001 bulgusu: Kiril yazım `surname`/`given_names`'te, orijinal yazım boş; belge Rusça.
    employee = _employee(session)
    _document(session, "E0001", ("ru", "cyrillic"))

    repairs = repair_latin_names(session, actor=ACTOR)

    assert repairs == [
        LatinRepair(
            "E0001",
            filled=(
                ("original_script_name", RepairSource.LATIN_FIELDS),
                ("given_names", RepairSource.TRANSLITERATION),
                ("surname", RepairSource.TRANSLITERATION),
            ),
            latin_missing=(),
        )
    ]
    assert _names(employee) == ("TEST", None, "ORNEKOVA", "ТЕСТ ОРНЕКОВА")
    assert employee.folder_name == FOLDER  # K8: klasör adı değişmez
    assert not needs_latin_repair(employee)
    assert _event_data(session) == [
        ("E0001", ACTOR, _filled("original_script_name", RepairSource.LATIN_FIELDS)),
        ("E0001", ACTOR, _filled("given_names", RepairSource.TRANSLITERATION)),
        ("E0001", ACTOR, _filled("surname", RepairSource.TRANSLITERATION)),
    ]
    assert {event.type for event in _events(session)} == {EventType.EMPLOYEE_FIELD_FILLED.value}
    for event in _events(session):
        _assert_no_personal_values(f"{event.message} {event.data_json}")


def test_second_run_changes_nothing(session: Session) -> None:
    employee = _employee(session)
    repair_latin_names(session)
    before, events = _names(employee), len(_events(session))

    assert repair_latin_names(session) == []
    assert _names(employee) == before
    assert len(_events(session)) == events


def test_latin_alias_of_the_employee_is_used_before_transliteration(session: Session) -> None:
    # Belge ya da MRZ kaynaklı Latin isim yazımı (05.7.2) aksanlarıyla kullanılır.
    employee = _employee(
        session,
        given_names="МАРКО",
        surname="ЖИВКОВИЋ",
        other_names="ПЕТАР",
        original_script_name="Марко Живковић",
        aliases=("МАРКО ЖИВКОВИЋ", "Marko Živković"),
    )
    _document(session, "E0001", ("sr", "cyrillic"))

    (repair,) = repair_latin_names(session)

    assert repair.filled == (
        ("given_names", RepairSource.ALIAS),
        ("other_names", RepairSource.TRANSLITERATION),
        ("surname", RepairSource.ALIAS),
    )
    # Orijinal yazım doluydu: üzerine yazılmaz.
    assert _names(employee) == ("Marko", "PETAR", "Živković", "Марко Живковић")


def test_a_latin_alias_removed_from_the_profile_is_not_a_source(session: Session) -> None:
    # 10.5.8: İK'nın kaldırdığı yazım Latin kaynak olmaz; çeviri kullanılır.
    employee = _employee(
        session,
        given_names="МАРКО",
        surname="ЖИВКОВИЋ",
        original_script_name="Марко Живковић",
        aliases=("МАРКО ЖИВКОВИЋ", "Marko Živković"),
    )
    _document(session, "E0001", ("sr", "cyrillic"))
    latin = session.scalars(
        select(EmployeeAlias).where(EmployeeAlias.raw_name == "Marko Živković")
    ).one()
    latin.removed_at, latin.removed_by = datetime.now(UTC), ACTOR
    session.flush()

    (repair,) = repair_latin_names(session)

    assert repair.filled == (
        ("given_names", RepairSource.TRANSLITERATION),
        ("surname", RepairSource.TRANSLITERATION),
    )
    assert _names(employee)[0::2] == ("MARKO", "ŽIVKOVIĆ")


@pytest.mark.parametrize(
    ("pages", "expected"),
    [
        ((("sr", "cyrillic"),), "ŽIVKOVIĆ"),
        ((("sr", "cyrillic"), ("en", "latin")), "ŽIVKOVIĆ"),
        ((("sr", "cyrillic"), ("uk", "cyrillic")), "ZHIVKOVIC"),
        ((), "ZHIVKOVIC"),
    ],
    ids=["serbian-page", "latin-page-ignored", "two-languages", "no-document"],
)
def test_transliteration_uses_the_language_of_the_employee_s_cyrillic_pages(
    session: Session, pages: tuple[tuple[str, str], ...], expected: str
) -> None:
    employee = _employee(session, given_names="МАРКО", surname="ЖИВКОВИЋ")
    if pages:
        _document(session, "E0001", *pages)

    repair_latin_names(session)

    assert (employee.given_names, employee.surname) == ("MARKO", expected)


def test_name_without_latin_spelling_keeps_its_fields_and_is_flagged(session: Session) -> None:
    # Arap yazımı tahminle çevrilmez: yazım orijinal yazıma taşınır, alanlar değişmez.
    employee = _employee(session, given_names="محمد", surname="علي", folder_name="Mhmd_Ely_E0001")

    (repair,) = repair_latin_names(session)

    assert repair == LatinRepair(
        "E0001",
        filled=(("original_script_name", RepairSource.LATIN_FIELDS),),
        latin_missing=("given_names", "surname"),
    )
    assert _names(employee) == ("محمد", None, "علي", "محمد علي")
    assert needs_latin_repair(employee)
    events = len(_events(session))

    # İkinci çalıştırma: yine Latin yazım yok, hiçbir şey yazılmaz.
    assert repair_latin_names(session) == [
        LatinRepair("E0001", filled=(), latin_missing=("given_names", "surname"))
    ]
    assert len(_events(session)) == events


def test_latin_employees_are_not_touched_and_dry_run_writes_nothing(session: Session) -> None:
    latin = _employee(
        session, "E0002", given_names="Ana", surname="Test", folder_name="Ana_Test_E0002"
    )
    cyrillic = _employee(session)

    (repair,) = repair_latin_names(session, dry_run=True)

    assert repair.employee_id == "E0001"
    assert _names(cyrillic) == ("ТЕСТ", None, "ОРНЕКОВА", None)
    assert _names(latin) == ("Ana", None, "Test", None)
    assert _events(session) == []


def test_a_corrupt_source_reference_is_skipped(session: Session) -> None:
    # Bozuk `source_refs_json` dil vermez: ICAO varsayılan sütunu kullanılır.
    employee = _employee(session, given_names="МАРКО", surname="ЖИВКОВИЋ")
    _document(session, "E0001", ("sr", "cyrillic"))
    document = session.scalars(select(Document)).one()
    document.source_refs_json = {"file_id": 1}  # type: ignore[assignment]
    session.flush()

    repair_latin_names(session)

    assert employee.surname == "ZHIVKOVIC"


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


def test_command_repairs_commits_and_rewrites_the_profile(
    environment: DataLayout,
    session: Session,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _employee(session)
    session.commit()
    environment.ensure_employee_tree(FOLDER)

    assert main(["repair-latin-names", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "E0001: yazılan original_script_name (latin_fields), given_names" in out
    assert "Latin ad onarımı: 1 çalışan onarılacak." in out
    session.expire_all()
    assert session.get_one(Employee, "E0001").surname == "ОРНЕКОВА"
    session.rollback()  # okuma işlemi yazma kilidini tutmasın (BEGIN IMMEDIATE)

    assert main(["repair-latin-names", "--actor", ACTOR]) == 0
    out = capsys.readouterr().out
    assert "Latin ad onarımı: 1 çalışan onarıldı." in out
    _assert_no_personal_values(out)
    session.expire_all()
    assert _names(session.get_one(Employee, "E0001")) == (
        "TEST",
        None,
        "ORNEKOVA",
        "ТЕСТ ОРНЕКОВА",
    )
    assert {actor for _, actor, _ in _event_data(session)} == {ACTOR}
    session.rollback()
    profile = environment.profile_path(FOLDER).read_text(encoding="utf-8")
    assert "# TEST ORNEKOVA" in profile
    assert "| Orijinal yazım | ТЕСТ ОРНЕКОВА |" in profile

    assert main(["repair-latin-names"]) == 0
    assert "Latin ad onarımı: 0 çalışan onarıldı." in capsys.readouterr().out


def test_command_names_the_fields_left_without_latin_spelling(
    environment: DataLayout,
    session: Session,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _employee(session, given_names="محمد", surname="علي", folder_name="Mhmd_Ely_E0001")
    session.commit()

    assert main(["repair-latin-names"]) == 0

    out = capsys.readouterr().out
    assert (
        "E0001: yazılan original_script_name (latin_fields); "
        "Latin yazım eksik: given_names, surname"
    ) in out
    _assert_no_personal_values(out)
