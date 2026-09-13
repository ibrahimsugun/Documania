"""00.3.2 — `alembic upgrade head` SQLite ve PostgreSQL üzerinde temiz çalışır."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.models import Base

REPO_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(database_url: str) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


def _assert_schema_matches_models(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
            assert tables == set(Base.metadata.tables) | {"alembic_version"}
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            assert compare_metadata(context, Base.metadata) == []
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
    finally:
        engine.dispose()


def test_upgrade_head_on_clean_sqlite_matches_models(sqlite_url: str) -> None:
    command.upgrade(_alembic_config(sqlite_url), "head")

    _assert_schema_matches_models(sqlite_url)


def test_upgrade_head_is_idempotent(sqlite_url: str) -> None:
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "head")
    command.upgrade(config, "head")

    _assert_schema_matches_models(sqlite_url)


def test_migrated_schema_keeps_check_constraints(sqlite_url: str) -> None:
    command.upgrade(_alembic_config(sqlite_url), "head")

    engine = create_engine(sqlite_url)
    try:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO uploads (id, channel, status, created_at) VALUES (:i, :c, :s, :t)"
                ),
                {"i": "u_1", "c": "web", "s": "bitti", "t": "2026-09-05 00:00:00"},
            )
    finally:
        engine.dispose()


def test_cli_upgrade_head_reads_database_url(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'cli.db').as_posix()}"
    env = {**os.environ, "DATABASE_URL": database_url}

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    _assert_schema_matches_models(database_url)


def test_upgrade_head_on_clean_postgresql_matches_models(postgres_url: str) -> None:
    command.upgrade(_alembic_config(postgres_url), "head")

    _assert_schema_matches_models(postgres_url)
