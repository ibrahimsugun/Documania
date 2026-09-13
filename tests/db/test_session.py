"""Motor ve oturum fabrikası: SQLite ayarları ve `DATABASE_URL` bağlantısı."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session as db_session
from app.db.models import Employee
from app.db.session import create_session_factory


def _employee(number: str) -> Employee:
    return Employee(
        id=number, folder_name=f"Test_Kisi_{number}", given_names="Test", surname="Kisi"
    )


def test_sqlite_connections_enforce_foreign_keys(engine: Engine) -> None:
    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1


def test_sqlite_transaction_takes_write_lock_at_begin(engine: Engine, sqlite_url: str) -> None:
    database_path = sqlite_url.removeprefix("sqlite:///")
    with create_session_factory(engine)() as session:
        session.execute(text("SELECT 1"))  # yalnız okuma; kilit yine de alınmış olmalı

        other = sqlite3.connect(database_path, timeout=0, isolation_level=None)
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("BEGIN IMMEDIATE")
        finally:
            other.close()


def test_savepoint_rollback_keeps_outer_transaction(session: Session) -> None:
    session.add(_employee("E0001"))
    with session.begin_nested() as savepoint:
        session.add(_employee("E0002"))
        session.flush()
        savepoint.rollback()
    session.commit()

    assert [e.id for e in session.query(Employee).order_by(Employee.id)] == ["E0001"]


@pytest.fixture
def configured_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    database_url = f"sqlite:///{(tmp_path / 'settings.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    caches = (get_settings, db_session.get_engine, db_session.get_session_factory)
    for cache in caches:
        cache.cache_clear()
    yield database_url
    db_session.get_engine().dispose()
    for cache in caches:
        cache.cache_clear()


def test_get_session_uses_database_url_from_settings(configured_database: str) -> None:
    sessions = db_session.get_session()
    session = next(sessions)

    assert str(session.get_bind().url) == configured_database
    assert db_session.get_engine() is db_session.get_engine()
    with pytest.raises(StopIteration):
        next(sessions)
