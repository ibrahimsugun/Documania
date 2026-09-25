"""05.2.2 — orijinal yazımı kayıttaki adlardan doldurma (`app.profiles.original_spelling`).

Kural değişmeden önce Latin belgeyle açılmış çalışanın `original_script_name` alanı boş kaldı.
Tek seferlik komut bu alanı kayıttaki Latin adlardan doldurur; dolu alana (Kiril/Arap yazım)
dokunmaz ve tekrar çalıştırıldığında hiçbir şey değiştirmez. Kayıtlar sentetiktir; gerçek kişi yok.
"""

from __future__ import annotations

import runpy
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Employee, Event
from app.events import EventType
from app.profiles.cli import main
from app.profiles.original_spelling import (
    FILL_SOURCE,
    OriginalSpellingFill,
    fill_original_spelling,
)
from app.storage import DataLayout

ACTOR = "ik.admin"
CYRILLIC = "ОРНЕКОВА ТЕСТ"
# Kişisel değerler: olay verisinde ve komut çıktısında geçmez (CONVENTIONS §6).
PERSONAL_VALUES = ("MEHMET", "ÖRNEK", "ОРНЕКОВА", "ТЕСТ", "Ali")


def _employee(
    session: Session,
    employee_id: str = "E0001",
    *,
    given_names: str = "MEHMET",
    surname: str = "ÖRNEK",
    other_names: str | None = None,
    original_script_name: str | None = None,
) -> Employee:
    employee = Employee(
        id=employee_id,
        folder_name=f"Ornek_{employee_id}",
        given_names=given_names,
        surname=surname,
        other_names=other_names,
        original_script_name=original_script_name,
    )
    session.add(employee)
    session.flush()
    return employee


def _filled_events(session: Session) -> list[dict[str, str]]:
    return [
        event.data_json
        for event in session.scalars(
            select(Event)
            .where(Event.type == EventType.EMPLOYEE_FIELD_FILLED.value)
            .order_by(Event.id)
        )
    ]


# --- kural ----------------------------------------------------------------------------------------


def test_empty_original_spelling_is_filled_from_the_latin_names(session: Session) -> None:
    _employee(session, other_names="ALİ")

    fills = fill_original_spelling(session, actor=ACTOR)

    assert fills == [OriginalSpellingFill(employee_id="E0001", filled=True)]
    # Ad, diğer isimler, soyad sırasıyla — `PersonKey.original_spelling` ile aynı.
    assert session.get_one(Employee, "E0001").original_script_name == "MEHMET ALİ ÖRNEK"
    assert _filled_events(session) == [
        {"field": "original_script_name", "source": FILL_SOURCE, "rule": "05.2.2"}
    ]


def test_a_filled_original_spelling_is_never_touched(session: Session) -> None:
    _employee(session, original_script_name=CYRILLIC)

    assert fill_original_spelling(session, actor=ACTOR) == []
    assert session.get_one(Employee, "E0001").original_script_name == CYRILLIC
    assert _filled_events(session) == []


def test_running_it_again_changes_nothing(session: Session) -> None:
    _employee(session)

    first = fill_original_spelling(session, actor=ACTOR)
    second = fill_original_spelling(session, actor=ACTOR)

    assert [fill.filled for fill in first] == [True]
    assert second == []
    assert len(_filled_events(session)) == 1


def test_dry_run_writes_nothing(session: Session) -> None:
    _employee(session)

    fills = fill_original_spelling(session, actor=ACTOR, dry_run=True)

    assert fills == [OriginalSpellingFill(employee_id="E0001", filled=True)]
    assert session.get_one(Employee, "E0001").original_script_name is None
    assert _filled_events(session) == []


def test_employees_are_processed_in_employee_number_order(session: Session) -> None:
    for employee_id in ("E10000", "E0002", "E0001"):
        _employee(session, employee_id)

    fills = fill_original_spelling(session, actor=ACTOR)

    assert [fill.employee_id for fill in fills] == ["E0001", "E0002", "E10000"]


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


def test_command_fills_commits_and_says_what_it_did(
    environment: DataLayout,
    session: Session,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _employee(session)
    session.commit()

    assert main(["fill-original-spelling", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "E0001: orijinal yazım" in out
    assert "Orijinal yazım: 1 çalışanın alanı boştu, 1 çalışanda doldurulacak." in out
    session.expire_all()
    assert session.get_one(Employee, "E0001").original_script_name is None
    session.rollback()  # okuma işlemi yazma kilidini tutmasın (BEGIN IMMEDIATE)

    assert main(["fill-original-spelling", "--actor", ACTOR]) == 0
    out = capsys.readouterr().out
    assert "Orijinal yazım: 1 çalışanın alanı boştu, 1 çalışanda dolduruldu." in out
    for value in PERSONAL_VALUES:
        assert value not in out
    session.expire_all()
    assert session.get_one(Employee, "E0001").original_script_name == "MEHMET ÖRNEK"
    session.rollback()

    assert main(["fill-original-spelling"]) == 0
    assert (
        "Orijinal yazım: 0 çalışanın alanı boştu, 0 çalışanda dolduruldu."
        in capsys.readouterr().out
    )


def test_the_module_runs_as_a_script(
    environment: DataLayout,
    session: Session,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    recwarn: pytest.WarningsRecorder,
) -> None:
    """`python -m app.profiles ...` yolu: modül baştan sona çalıştırılır.

    `main`'i içe aktaran testler modülün alt kısmındaki tanımları görür; `python -m` ise
    `if __name__ == "__main__"` bloğuna geldiğinde yalnız o ana kadar tanımlananları bilir.
    Komut işleyicisi bloğun altında kalırsa `NameError` olur — bu test onu yakalar.
    """
    _employee(session)
    session.commit()
    session.rollback()  # okuma işlemi yazma kilidini tutmasın (BEGIN IMMEDIATE)
    monkeypatch.setattr(sys, "argv", ["app.profiles", "fill-original-spelling", "--dry-run"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("app.profiles", run_name="__main__")

    assert exit_info.value.code == 0
    assert "Orijinal yazım: 1 çalışanın alanı boştu" in capsys.readouterr().out
    assert not any(
        issubclass(warning.category, RuntimeWarning)
        and "found in sys.modules after import of package" in str(warning.message)
        for warning in recwarn
    )
