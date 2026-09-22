"""00.3.2 — `alembic upgrade head` SQLite ve PostgreSQL üzerinde temiz çalışır."""

import json
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
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0009"
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


def test_queue_item_plan_id_migration_keeps_existing_rows_both_ways(sqlite_url: str) -> None:
    # 0002 SQLite'ta tabloyu batch kipinde yeniden kurar; var olan kuyruk kaydı kaybolmamalı.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0001")
    engine = create_engine(sqlite_url)
    row = "SELECT upload_id, plan_item_id, kind, reason FROM queue_items"
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO uploads (id, channel, status, created_at) "
                    "VALUES ('u_1', 'web', 'received', '2026-09-05 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO queue_items (upload_id, plan_item_id, kind, reason) "
                    "VALUES ('u_1', 'i2', 'unresolved', 'R6')"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.execute(text(row)).all() == [("u_1", "i2", "unresolved", "R6")]
            assert connection.scalar(text("SELECT plan_id FROM queue_items")) is None

        command.downgrade(config, "0001")
        with engine.connect() as connection:
            assert connection.execute(text(row)).all() == [("u_1", "i2", "unresolved", "R6")]
            columns = {column["name"] for column in inspect(connection).get_columns("queue_items")}
            assert "plan_id" not in columns
    finally:
        engine.dispose()


def test_user_sessions_migration_is_reversible_and_keeps_users(sqlite_url: str) -> None:
    # 0003 yalnız oturum tablosunu ekler (10.1.2); var olan panel kullanıcısına dokunmaz.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0002")
    engine = create_engine(sqlite_url)
    user = "SELECT username, role FROM users"
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (username, password_hash, role) "
                    "VALUES ('yonetici', 'hash', 'admin')"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert "user_sessions" in inspect(connection).get_table_names()
            assert connection.execute(text(user)).all() == [("yonetici", "admin")]

        command.downgrade(config, "0002")
        with engine.connect() as connection:
            assert "user_sessions" not in inspect(connection).get_table_names()
            assert connection.execute(text(user)).all() == [("yonetici", "admin")]
    finally:
        engine.dispose()


def test_confirmation_tokens_migration_is_reversible_and_keeps_sessions(sqlite_url: str) -> None:
    # 0004 yalnız onay belirteci tablosunu ekler (10.8.1); var olan oturuma dokunmaz.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0003")
    engine = create_engine(sqlite_url)
    session_row = "SELECT user_id, token_hash FROM user_sessions"
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, username, password_hash, role) "
                    "VALUES (1, 'yonetici', 'hash', 'admin')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO user_sessions (user_id, token_hash, created_at, expires_at) "
                    "VALUES (1, 'ozet', '2026-09-19 00:00:00', '2026-09-20 00:00:00')"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert "confirmation_tokens" in inspect(connection).get_table_names()
            assert connection.execute(text(session_row)).all() == [(1, "ozet")]

        command.downgrade(config, "0003")
        with engine.connect() as connection:
            assert "confirmation_tokens" not in inspect(connection).get_table_names()
            assert connection.execute(text(session_row)).all() == [(1, "ozet")]
    finally:
        engine.dispose()


def test_photo_check_migration_is_reversible_and_keeps_page_analyses(sqlite_url: str) -> None:
    # 0005 `pages`'e boş `photo_check_json` ekler (11.7.1); var olan sayfanın analizi kalır.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0004")
    engine = create_engine(sqlite_url)
    page_row = 'SELECT file_id, "index", analysis_json, analysis_status FROM pages'
    expected = [(1, 0, '{"page_index": 0}', "done")]
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO uploads (id, channel, status, created_at) "
                    "VALUES ('u_1', 'web', 'done', '2026-09-05 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO upload_files (id, upload_id, original_name, stored_path, sha256, "
                    "mime) VALUES (1, 'u_1', 'a.pdf', 'Inbox/u_1/a.pdf', :sha, 'application/pdf')"
                ),
                {"sha": "0" * 64},
            )
            connection.execute(
                text(
                    'INSERT INTO pages (file_id, "index", is_blank, has_single_embedded_image, '
                    "analysis_json, analysis_status) "
                    "VALUES (1, 0, 0, 0, '{\"page_index\": 0}', 'done')"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.execute(text(page_row)).all() == expected
            assert connection.scalar(text("SELECT photo_check_json FROM pages")) is None

        command.downgrade(config, "0004")
        with engine.connect() as connection:
            assert connection.execute(text(page_row)).all() == expected
            columns = {column["name"] for column in inspect(connection).get_columns("pages")}
            assert "photo_check_json" not in columns
    finally:
        engine.dispose()


def test_upload_jobs_migration_queues_every_unfinished_batch_and_is_reversible(
    sqlite_url: str,
) -> None:
    # 0006 kalıcı işçi kuyruğunu açar (13.3.1): göçten önce yarıda kalmış ya da hiç işlenmemiş
    # parti kuyruğa girer, bitmiş partiye iş açılmaz.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0005")
    engine = create_engine(sqlite_url)
    statuses = {
        "u_1": ("received", "2026-09-05 08:00:00"),
        "u_2": ("analyzing", "2026-09-05 07:00:00"),
        "u_3": ("executing", "2026-09-05 09:00:00"),
        "u_4": ("done", "2026-09-05 06:00:00"),
        "u_5": ("partial", "2026-09-05 06:00:00"),
        "u_6": ("failed", "2026-09-05 06:00:00"),
    }
    upload_row = "SELECT id, status FROM uploads ORDER BY id"
    try:
        with engine.begin() as connection:
            for upload_id, (status, created_at) in statuses.items():
                connection.execute(
                    text(
                        "INSERT INTO uploads (id, channel, status, created_at) "
                        "VALUES (:i, 'web', :s, :t)"
                    ),
                    {"i": upload_id, "s": status, "t": created_at},
                )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            jobs = connection.execute(
                text(
                    "SELECT upload_id, status, attempts, claimed_by, lease_expires_at, "
                    "enqueued_at FROM upload_jobs ORDER BY id"
                )
            ).all()
            assert [tuple(job) for job in jobs] == [
                ("u_2", "queued", 0, None, None, "2026-09-05 07:00:00"),
                ("u_1", "queued", 0, None, None, "2026-09-05 08:00:00"),
                ("u_3", "queued", 0, None, None, "2026-09-05 09:00:00"),
            ]
            before = connection.execute(text(upload_row)).all()
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO upload_jobs (upload_id, status, attempts, enqueued_at) "
                    "VALUES ('u_4', 'bekliyor', 0, '2026-09-05 00:00:00')"
                )
            )

        command.downgrade(config, "0005")
        with engine.connect() as connection:
            assert "upload_jobs" not in inspect(connection).get_table_names()
            assert connection.execute(text(upload_row)).all() == before
    finally:
        engine.dispose()


def test_front_back_layouts_migration_gives_every_card_both_layouts_and_is_reversible(
    sqlite_url: str,
) -> None:
    # 0007 (04.1.2): var olan `front_back` tür iki düzeni de kabul eder ve aralığı düzenlerden
    # türer (1–2); tek yüzlü türün düzen listesi boştur, aralığı değişmez.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0006")
    engine = create_engine(sqlite_url)
    types = {
        "card_two_pages": ("front_back", 2, 2),
        "card_no_range": ("front_back", None, None),
        "passport": ("single", 1, 1),
        "letter": ("single", None, None),
    }
    rows = (
        "SELECT slug, sides, expected_pages_min, expected_pages_max FROM known_document_types "
        "ORDER BY slug"
    )
    try:
        with engine.begin() as connection:
            for slug, (sides, low, high) in types.items():
                connection.execute(
                    text(
                        "INSERT INTO known_document_types (slug, name, file_label, "
                        "expected_file_types, expected_pages_min, expected_pages_max, sides, "
                        "direct, analyze, required_fields, allowed_conversions, output_format, "
                        "acceptance_criteria, active) VALUES (:slug, 'Ad', 'Etiket', '[\"pdf\"]', "
                        ":low, :high, :sides, 0, 1, '[]', '[]', 'keep', '[]', 1)"
                    ),
                    {"slug": slug, "sides": sides, "low": low, "high": high},
                )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            migrated = connection.execute(
                text(
                    "SELECT slug, front_back_layouts, expected_pages_min, expected_pages_max "
                    "FROM known_document_types ORDER BY slug"
                )
            ).all()
            assert [
                (slug, json.loads(layouts), low, high) for slug, layouts, low, high in migrated
            ] == [
                ("card_no_range", ["separate", "combined"], 1, 2),
                ("card_two_pages", ["separate", "combined"], 1, 2),
                ("letter", [], None, None),
                ("passport", [], 1, 1),
            ]
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("UPDATE known_document_types SET front_back_layouts = NULL"))

        command.downgrade(config, "0006")
        with engine.connect() as connection:
            columns = {
                column["name"] for column in inspect(connection).get_columns("known_document_types")
            }
            assert "front_back_layouts" not in columns
            assert connection.execute(text(rows)).all() == [
                ("card_no_range", "front_back", 1, 2),
                ("card_two_pages", "front_back", 1, 2),
                ("letter", "single", None, None),
                ("passport", "single", 1, 1),
            ]
    finally:
        engine.dispose()


def test_field_observations_migration_adds_the_table_and_is_reversible(sqlite_url: str) -> None:
    # 0008 (05.7.3): gözlem tablosu değer sütunu taşımaz; alan ve sonuç kapalı kümedir, bir alan
    # aynı kaynaktan bir kez gözlenir. Geri alış tabloyu düşürür, çalışanlar kalır.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0007")
    engine = create_engine(sqlite_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO employees (id, folder_name, given_names, surname, status, "
                    "created_at) VALUES ('E0001', 'Test_Kisi_E0001', 'Test', 'Kisi', 'active', "
                    "'2026-09-22 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO uploads (id, channel, status, created_at) "
                    "VALUES ('u_1', 'web', 'done', '2026-09-22 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO upload_files (id, upload_id, original_name, stored_path, sha256, "
                    "mime) VALUES (1, 'u_1', 'a.pdf', 'Inbox/u_1/a.pdf', :sha, 'application/pdf')"
                ),
                {"sha": "0" * 64},
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            columns = {
                column["name"]
                for column in inspect(connection).get_columns("employee_field_observations")
            }
        assert columns == {
            "id",
            "employee_id",
            "field",
            "outcome",
            "file_id",
            "page_index",
            "observed_at",
        }
        insert = text(
            "INSERT INTO employee_field_observations (employee_id, field, outcome, file_id, "
            "page_index, observed_at) VALUES ('E0001', :field, :outcome, 1, 0, "
            "'2026-09-22 00:00:00')"
        )
        with engine.begin() as connection:
            connection.execute(insert, {"field": "date_of_birth", "outcome": "filled"})
        for values in (
            {"field": "expiry_date", "outcome": "filled"},
            {"field": "nationality", "outcome": "changed"},
            {"field": "date_of_birth", "outcome": "same"},
        ):
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(insert, values)

        command.downgrade(config, "0007")
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
            assert "employee_field_observations" not in tables
            assert connection.scalar(text("SELECT count(*) FROM employees")) == 1
    finally:
        engine.dispose()


def test_upload_dismissal_migration_adds_nullable_columns_and_is_reversible(
    sqlite_url: str,
) -> None:
    # 0009 (10.3.4): var olan parti yoksayılmamış, var olan çözülmüş öğe nedensiz kalır; çözüm
    # nedeni kapalı kümedir. Geri alış üç sütunu düşürür, parti ve öğeler kalır.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0008")
    engine = create_engine(sqlite_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO uploads (id, channel, status, created_at) "
                    "VALUES ('u_1', 'web', 'done', '2026-09-22 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO queue_items (id, upload_id, kind, reason, resolved_at, "
                    "resolved_by) VALUES (1, 'u_1', 'unknown', 'tür yok', "
                    "'2026-09-22 01:00:00', 'ik')"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            upload = connection.execute(
                text("SELECT dismissed_at, dismissed_by FROM uploads WHERE id = 'u_1'")
            ).one()
            assert tuple(upload) == (None, None)
            assert connection.scalar(text("SELECT resolution FROM queue_items")) is None
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE uploads SET dismissed_at = '2026-09-22 02:00:00', dismissed_by = 'ik'")
            )
            connection.execute(text("UPDATE queue_items SET resolution = 'dismissed'"))
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("UPDATE queue_items SET resolution = 'deleted'"))
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("UPDATE queue_items SET kind = 'lost'"))

        command.downgrade(config, "0008")
        with engine.connect() as connection:
            inspector = inspect(connection)
            assert {"dismissed_at", "dismissed_by"}.isdisjoint(
                column["name"] for column in inspector.get_columns("uploads")
            )
            assert "resolution" not in {
                column["name"] for column in inspector.get_columns("queue_items")
            }
            assert connection.scalar(text("SELECT count(*) FROM uploads")) == 1
            assert connection.scalar(text("SELECT resolved_by FROM queue_items")) == "ik"
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("UPDATE queue_items SET kind = 'lost'"))
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
