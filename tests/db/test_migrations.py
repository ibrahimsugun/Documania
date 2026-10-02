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
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0024"
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

        # 0016 kaynak ve kullanıcı sütunlarını ekler (aşağıdaki test); bu test 0008'in şemasıdır.
        command.upgrade(config, "0008")
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


def test_candidate_proposal_migration_adds_columns_and_is_reversible(sqlite_url: str) -> None:
    # 0010 (11.5.5): var olan aday incelenmemiş (`proposal_status` boş) ve sahiplenilmemiş
    # (deneme 0) kalır; inceleme sonucu kapalı kümedir. Geri alış altı sütunu düşürür, aday kalır.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0009")
    engine = create_engine(sqlite_url)
    columns = {
        "proposal_json",
        "proposal_status",
        "proposal_generated_at",
        "idle_claimed_by",
        "idle_claim_expires_at",
        "idle_attempts",
    }
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO uploads (id, channel, status, created_at) "
                    "VALUES ('u_1', 'web', 'done', '2026-09-26 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO candidate_document_types (id, proposed_name, normalized_name, "
                    "first_seen_upload_id, sample_page_ids, seen_count, status) VALUES "
                    "(1, 'Test Card', 'test card', 'u_1', '[]', 1, 'pending')"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT proposal_json, proposal_status, proposal_generated_at, "
                    "idle_claimed_by, idle_claim_expires_at, idle_attempts "
                    "FROM candidate_document_types"
                )
            ).one()
            assert tuple(row) == (None, None, None, None, None, 0)
        with engine.begin() as connection:
            for value in ("ready", "failed", "no_samples"):
                connection.execute(
                    text("UPDATE candidate_document_types SET proposal_status = :value"),
                    {"value": value},
                )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("UPDATE candidate_document_types SET proposal_status = 'ok'"))

        command.downgrade(config, "0009")
        with engine.connect() as connection:
            names = {
                column["name"]
                for column in inspect(connection).get_columns("candidate_document_types")
            }
            assert columns.isdisjoint(names)
            assert connection.scalar(text("SELECT status FROM candidate_document_types")) == (
                "pending"
            )
    finally:
        engine.dispose()


def test_training_migration_creates_the_tables_and_is_reversible(sqlite_url: str) -> None:
    # 0011 (11.9): eğitim tabloları boş açılır, klasördeki örnekler kayıtsız kalır; durum, yöntem
    # ve etiket kümeleri kapalıdır; örnek adı tür içinde tekildir. Geri alış üç tabloyu düşürür,
    # var olan aday türe dokunmaz.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0010")
    engine = create_engine(sqlite_url)
    tables = {"training_runs", "training_items", "example_files"}
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO uploads (id, channel, status, created_at) "
                    "VALUES ('u_1', 'web', 'done', '2026-09-26 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO candidate_document_types (id, proposed_name, normalized_name, "
                    "first_seen_upload_id, sample_page_ids, seen_count, status) VALUES "
                    "(1, 'Test Card', 'test card', 'u_1', '[]', 1, 'pending')"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert tables <= set(inspect(connection).get_table_names())
            for table in sorted(tables):
                assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO training_runs (id, kind, created_by, created_at, status, "
                    "counts_json) VALUES (1, 'upload', 'ik', '2026-09-26 00:00:00', 'running', "
                    "'{}')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO training_items (id, run_id, original_name, status, method) "
                    "VALUES (1, 1, 'a.pdf', 'placed', 'mechanical')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO example_files (type_slug, name, sha256, method, label, "
                    "training_item_id, created_at) VALUES ('albanian_passport', 'a.pdf', :sha, "
                    "'ai', 'ai_decision', 1, '2026-09-26 00:00:00')"
                ),
                {"sha": "a" * 64},
            )
        for statement in (
            "UPDATE training_runs SET kind = 'batch'",
            "UPDATE training_runs SET status = 'failed'",
            "UPDATE training_items SET status = 'done'",
            "UPDATE training_items SET method = 'legacy'",
            "UPDATE example_files SET method = 'guess'",
            "UPDATE example_files SET label = 'checked'",
            "INSERT INTO example_files (type_slug, name, sha256, method, created_at) VALUES "
            "('albanian_passport', 'a.pdf', 'b', 'manual', '2026-09-26 00:00:00')",
        ):
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(text(statement))

        command.downgrade(config, "0010")
        with engine.connect() as connection:
            assert tables.isdisjoint(inspect(connection).get_table_names())
            assert connection.scalar(text("SELECT status FROM candidate_document_types")) == (
                "pending"
            )
    finally:
        engine.dispose()


def test_training_item_idle_claim_migration_adds_columns_and_is_reversible(
    sqlite_url: str,
) -> None:
    # 0012 (11.9.3): var olan eğitim öğesi sahiplenilmemiş (deneme 0) kalır; `ai_pending` öğe
    # işçinin sırasını bekler. Geri alış üç sütunu düşürür, öğe ve durumu kalır.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0011")
    engine = create_engine(sqlite_url)
    columns = {"idle_claimed_by", "idle_claim_expires_at", "idle_attempts"}
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO training_runs (id, kind, created_by, created_at, status, "
                    "counts_json) VALUES (1, 'upload', 'ik', '2026-09-26 00:00:00', 'running', "
                    "'{}')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO training_items (id, run_id, original_name, status) "
                    "VALUES (1, 1, 'a.jpg', 'ai_pending')"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT status, idle_claimed_by, idle_claim_expires_at, idle_attempts "
                    "FROM training_items"
                )
            ).one()
            assert tuple(row) == ("ai_pending", None, None, 0)
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("UPDATE training_items SET idle_attempts = NULL"))

        command.downgrade(config, "0011")
        with engine.connect() as connection:
            names = {column["name"] for column in inspect(connection).get_columns("training_items")}
            assert columns.isdisjoint(names)
            assert connection.scalar(text("SELECT status FROM training_items")) == "ai_pending"
    finally:
        engine.dispose()


def test_example_file_removal_migration_narrows_the_unique_name_and_is_reversible(
    sqlite_url: str,
) -> None:
    # 0013 (11.9.4): var olan örnek kaydı etkin kalır (çıkarılma alanları boş); `(type_slug, name)`
    # yalnız etkin kayıtlarda tekildir — çıkarılmış kaydın adı yeniden kullanılabilir. Geri alış
    # üç sütunu düşürür ve tam tekilliği geri getirir; kayıt kalır.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0012")
    engine = create_engine(sqlite_url)
    insert = text(
        "INSERT INTO example_files (id, type_slug, name, sha256, method, created_at) "
        "VALUES (:id, 'albanian_passport', 'ornek.png', :sha, 'ai', '2026-09-26 00:00:00')"
    )
    try:
        with engine.begin() as connection:
            connection.execute(insert, {"id": 1, "sha": "a" * 64})

        command.upgrade(config, "head")
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT name, removed_at, removed_by, removed_path FROM example_files")
            ).one()
            assert tuple(row) == ("ornek.png", None, None, None)
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(insert, {"id": 2, "sha": "b" * 64})
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE example_files SET removed_at = '2026-09-26 01:00:00', "
                    "removed_by = 'ik', removed_path = 'KnownDocuments/_egitim/cikarilan/x/o.png'"
                )
            )
            connection.execute(insert, {"id": 2, "sha": "b" * 64})

        with engine.begin() as connection:
            connection.execute(text("DELETE FROM example_files WHERE id = 2"))
        command.downgrade(config, "0012")
        with engine.connect() as connection:
            names = {column["name"] for column in inspect(connection).get_columns("example_files")}
            assert {"removed_at", "removed_by", "removed_path"}.isdisjoint(names)
            assert connection.scalar(text("SELECT name FROM example_files")) == "ornek.png"
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(insert, {"id": 3, "sha": "c" * 64})
    finally:
        engine.dispose()


def test_document_groups_migration_creates_the_tables_and_is_reversible(sqlite_url: str) -> None:
    # 0014 (14.1): iki tablo boş açılır; grup adı sadeleşmiş hâliyle tekildir, kalemin eşleşme
    # anahtarı kapalı kümedir ve anahtara göre etiket ya da tür slug'ından tam biri doludur; tür
    # kalemi katalog türüne bağlıdır. Geri alış iki tabloyu düşürür, katalog türü kalır.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0013")
    engine = create_engine(sqlite_url)
    tables = {"document_groups", "document_group_items"}
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO known_document_types (slug, name, file_label, sides, direct, "
                    "analyze, output_format, expected_file_types, front_back_layouts, "
                    "required_fields, allowed_conversions, acceptance_criteria, active) VALUES "
                    "('russian_passport', 'Russian Passport', 'Passport', 'single', 1, 1, 'keep', "
                    "'[]', '[]', '[]', '[]', '[]', 1)"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert tables <= set(inspect(connection).get_table_names())
            for table in sorted(tables):
                assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO document_groups (id, name, normalized_name, created_by, "
                    "created_at) VALUES (1, 'Sırbistan', 'sirbistan', 'ik', "
                    "'2026-09-28 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO document_group_items (id, group_id, position, match_kind, "
                    "file_label, type_slug, required) VALUES "
                    "(1, 1, 1, 'label', 'Passport', NULL, 1), "
                    "(2, 1, 2, 'type', NULL, 'russian_passport', 0)"
                )
            )
        item = (
            "INSERT INTO document_group_items (group_id, position, match_kind, file_label, "
            "type_slug, required) VALUES "
        )
        for statement in (
            "INSERT INTO document_groups (name, normalized_name, created_by, created_at) VALUES "
            "('SIRBISTAN', 'sirbistan', 'ik', '2026-09-28 00:00:00')",
            item + "(1, 3, 'country', 'Passport', NULL, 1)",
            item + "(1, 3, 'label', NULL, NULL, 1)",
            item + "(1, 3, 'label', 'Passport', 'russian_passport', 1)",
            item + "(1, 3, 'type', NULL, NULL, 1)",
            item + "(1, 3, 'type', NULL, 'yok_boyle_tur', 1)",
            item + "(9, 3, 'label', 'Passport', NULL, 1)",
        ):
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.execute(text(statement))

        command.downgrade(config, "0013")
        with engine.connect() as connection:
            assert tables.isdisjoint(inspect(connection).get_table_names())
            assert connection.scalar(text("SELECT slug FROM known_document_types")) == (
                "russian_passport"
            )
    finally:
        engine.dispose()


def test_employee_packages_migration_creates_the_table_and_is_reversible(sqlite_url: str) -> None:
    # 0015 (14.2): tablo boş açılır; durum kapalı kümedir, çalışan ve grup kayıtlı olmalıdır. Geri
    # alış tabloyu düşürür, grup ve çalışan kalır.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0014")
    engine = create_engine(sqlite_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO employees (id, folder_name, given_names, surname, status, "
                    "created_at) VALUES ('E0001', 'Test_Kisi_E0001', 'Test', 'Kisi', 'active', "
                    "'2026-09-29 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO document_groups (id, name, normalized_name, created_by, "
                    "created_at) VALUES (1, 'Sırbistan', 'sirbistan', 'ik', "
                    "'2026-09-29 00:00:00')"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert "employee_packages" in inspect(connection).get_table_names()
            assert connection.scalar(text("SELECT count(*) FROM employee_packages")) == 0
        package = (
            "INSERT INTO employee_packages (employee_id, group_id, status, requested_by, "
            "requested_at) VALUES "
        )
        with engine.begin() as connection:
            connection.execute(text(package + "('E0001', 1, 'open', 'ik', '2026-09-29 00:00:00')"))
        for statement in (
            package + "('E0001', 1, 'done', 'ik', '2026-09-29 00:00:00')",
            package + "('E9999', 1, 'open', 'ik', '2026-09-29 00:00:00')",
            package + "('E0001', 9, 'open', 'ik', '2026-09-29 00:00:00')",
        ):
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.execute(text(statement))

        command.downgrade(config, "0014")
        with engine.connect() as connection:
            assert "employee_packages" not in inspect(connection).get_table_names()
            assert connection.scalar(text("SELECT count(*) FROM document_groups")) == 1
            assert connection.scalar(text("SELECT count(*) FROM employees")) == 1
    finally:
        engine.dispose()


def test_manual_field_observations_migration_keeps_rows_and_is_reversible(
    sqlite_url: str,
) -> None:
    # 0016 (10.5.6): var olan gözlem `document` kaynaklı kalır; elle düzenleme gözlemi kaynak
    # sayfası olmadan, kullanıcıyla yazılır. Alan, sonuç ve kaynak kapalı kümedir; belge gözlemi
    # sayfasız, elle gözlem kullanıcısız olamaz. Geri alış elle gözlemleri kaldırır, belge
    # gözlemleri kalır.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0015")
    engine = create_engine(sqlite_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO employees (id, folder_name, given_names, surname, status, "
                    "created_at) VALUES ('E0001', 'Test_Kisi_E0001', 'Test', 'Kisi', 'active', "
                    "'2026-09-29 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO uploads (id, channel, status, created_at) "
                    "VALUES ('u_1', 'web', 'done', '2026-09-29 00:00:00')"
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
                    "INSERT INTO employee_field_observations (employee_id, field, outcome, "
                    "file_id, page_index, observed_at) VALUES ('E0001', 'surname', 'filled', 1, "
                    "0, '2026-09-29 00:00:00')"
                )
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
                "source",
                "actor",
            }
            assert connection.execute(
                text("SELECT source, actor FROM employee_field_observations")
            ).all() == [("document", None)]
        insert = text(
            "INSERT INTO employee_field_observations (employee_id, field, outcome, file_id, "
            "page_index, observed_at, source, actor) VALUES ('E0001', :field, :outcome, :file_id, "
            ":page_index, '2026-09-29 00:00:00', :source, :actor)"
        )
        manual = {
            "field": "surname",
            "outcome": "filled",
            "file_id": None,
            "page_index": None,
            "source": "manual",
            "actor": "ik",
        }
        with engine.begin() as connection:
            connection.execute(insert, manual)
            connection.execute(insert, manual)  # elle düzenleme her kez yeni satırdır
        for changes in (
            {"source": "belge"},
            {"actor": None},
            {"source": "document", "actor": None},
            {"field": "expiry_date"},
            {"outcome": "changed"},
        ):
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(insert, {**manual, **changes})

        command.downgrade(config, "0015")
        with engine.connect() as connection:
            columns = {
                column["name"]
                for column in inspect(connection).get_columns("employee_field_observations")
            }
            assert "source" not in columns and "actor" not in columns
            assert connection.scalar(text("SELECT count(*) FROM employee_field_observations")) == 1
    finally:
        engine.dispose()


def test_profile_record_removal_migration_keeps_rows_active_and_is_reversible(
    sqlite_url: str,
) -> None:
    # 0017 (10.5.8): alias, numara ve iletişim satırları `removed_at`, `removed_by` ve
    # `seen_after_removal_at`, iletişim ayrıca `added_by` alır; hepsi boş olabilir, var olan
    # satırlar etkin kalır. Tekillik kısıtları değişmez. Geri alış sütunları kaldırır, satırlar
    # kalır.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0016")
    engine = create_engine(sqlite_url)
    removal = {"removed_at", "removed_by", "seen_after_removal_at"}
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO employees (id, folder_name, given_names, surname, status, "
                    "created_at) VALUES ('E0001', 'Test_Kisi_E0001', 'Test', 'Kisi', 'active', "
                    "'2026-09-29 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO employee_aliases (employee_id, raw_name, normalized_name) "
                    "VALUES ('E0001', 'TEST KISI', 'kisi test')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO employee_identifiers (employee_id, kind, value) "
                    "VALUES ('E0001', 'passport', '000000001')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO employee_contacts (employee_id, kind, value, first_seen_at, "
                    "last_seen_at, is_current) VALUES ('E0001', 'phone', '+90 000', "
                    "'2026-09-29 00:00:00', '2026-09-29 00:00:00', 1)"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            inspector = inspect(connection)
            for table, extra in (
                ("employee_aliases", set()),
                ("employee_identifiers", set()),
                ("employee_contacts", {"added_by"}),
            ):
                columns = {column["name"]: column for column in inspector.get_columns(table)}
                assert removal | extra <= set(columns), table
                assert all(columns[name]["nullable"] for name in removal | extra), table
                values = connection.execute(
                    text(f"SELECT removed_at, removed_by, seen_after_removal_at FROM {table}")
                ).all()
                assert values == [(None, None, None)], table
            assert connection.scalar(text("SELECT added_by FROM employee_contacts")) is None
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO employee_identifiers (employee_id, kind, value, removed_at) "
                    "VALUES ('E0001', 'passport', '000000001', '2026-09-29 00:00:00')"
                )
            )

        command.downgrade(config, "0016")
        with engine.connect() as connection:
            inspector = inspect(connection)
            for table in ("employee_aliases", "employee_identifiers", "employee_contacts"):
                columns = {column["name"] for column in inspector.get_columns(table)}
                assert not (removal | {"added_by"}) & columns, table
                assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 1
    finally:
        engine.dispose()


def test_employee_merge_migration_adds_merged_into_and_the_merge_source_and_is_reversible(
    sqlite_url: str,
) -> None:
    # 0018 (10.5.9): `employees.merged_into_id` (FK, boş olabilir) eklenir, var olan çalışanlar
    # birleştirilmemiş kalır; gözlem kaynağı CHECK'i `merge`'ü kabul eder (kullanıcıyla, belge
    # kaynağı olmadan). Geri alış sütunu kaldırır ve birleştirme gözlemlerini siler (eski CHECK'e
    # sığmazlar); öteki satırlar kalır.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0017")
    engine = create_engine(sqlite_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO employees (id, folder_name, given_names, surname, status, "
                    "created_at) VALUES ('E0001', 'Test_Kisi_E0001', 'Test', 'Kisi', 'active', "
                    "'2026-09-29 00:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO employee_field_observations (employee_id, field, outcome, "
                    "observed_at, source, actor) VALUES ('E0001', 'nationality', 'filled', "
                    "'2026-09-29 00:00:00', 'manual', 'ik')"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            columns = {c["name"]: c for c in inspect(connection).get_columns("employees")}
            assert columns["merged_into_id"]["nullable"]
            foreign_keys = inspect(connection).get_foreign_keys("employees")
            assert [(fk["constrained_columns"], fk["referred_table"]) for fk in foreign_keys] == [
                (["merged_into_id"], "employees")
            ]
            assert connection.scalar(text("SELECT merged_into_id FROM employees")) is None
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO employee_field_observations (employee_id, field, outcome, "
                    "observed_at, source, actor) VALUES ('E0001', 'date_of_birth', 'filled', "
                    "'2026-09-29 00:00:00', 'merge', 'ik')"
                )
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO employee_field_observations (employee_id, field, outcome, "
                    "observed_at, source, actor) VALUES ('E0001', 'surname', 'filled', "
                    "'2026-09-29 00:00:00', 'guess', 'ik')"
                )
            )

        command.downgrade(config, "0017")
        with engine.connect() as connection:
            columns = {c["name"] for c in inspect(connection).get_columns("employees")}
            assert "merged_into_id" not in columns
            sources = connection.execute(
                text("SELECT source FROM employee_field_observations ORDER BY id")
            ).scalars()
            assert list(sources) == ["manual"]
    finally:
        engine.dispose()


def test_queue_item_close_migration_adds_the_reason_and_note_and_is_reversible(
    sqlite_url: str,
) -> None:
    # 0019 (10.7.4): `queue_items.resolution` CHECK'i `closed`'u kabul eder; gerekçe kodu
    # (`resolution_reason`, CHECK'li) ve not (`resolution_note`) boş olabilir, var olan öğeler
    # kapatılmamış kalır. Geri alış iki sütunu düşürür ve kapatılmış öğenin nedenini boşaltır (eski
    # CHECK'e sığmaz); öğe çözülmüş kalır, yoksayılmış öğe değişmez.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0018")
    engine = create_engine(sqlite_url)
    insert_item = text(
        "INSERT INTO queue_items (upload_id, kind, reason, resolved_at, resolved_by, resolution"
        "{extra}) VALUES ('u_1', 'unknown', 'r', '2026-09-29 00:00:00', 'ik', :resolution{values})"
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO uploads (id, channel, status, created_at) "
                    "VALUES ('u_1', 'web', 'done', '2026-09-29 00:00:00')"
                )
            )
            connection.execute(
                text(insert_item.text.format(extra="", values="")), {"resolution": "dismissed"}
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            columns = {c["name"]: c for c in inspect(connection).get_columns("queue_items")}
            assert columns["resolution_reason"]["nullable"]
            assert columns["resolution_note"]["nullable"]
            assert connection.execute(
                text("SELECT resolution, resolution_reason, resolution_note FROM queue_items")
            ).all() == [("dismissed", None, None)]
        closed = text(
            insert_item.text.format(
                extra=", resolution_reason, resolution_note", values=", :reason, :note"
            )
        )
        with engine.begin() as connection:
            connection.execute(closed, {"resolution": "closed", "reason": "other", "note": "not"})
        for resolution, reason in (("silindi", "other"), ("closed", "cop")):
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(
                    closed, {"resolution": resolution, "reason": reason, "note": None}
                )

        command.downgrade(config, "0018")
        with engine.connect() as connection:
            columns = {c["name"] for c in inspect(connection).get_columns("queue_items")}
            assert not {"resolution_reason", "resolution_note"} & columns
            rows = connection.execute(
                text("SELECT resolution, resolved_by FROM queue_items ORDER BY id")
            ).all()
            assert rows == [("dismissed", "ik"), (None, "ik")]
    finally:
        engine.dispose()


def test_document_type_archive_migration_adds_nullable_columns_and_is_reversible(
    sqlite_url: str,
) -> None:
    # 0020 (11.1.6): `known_document_types.archived_at`/`archived_by` boş olabilir, var olan türler
    # arşivsiz kalır; geri alış iki sütunu düşürür, tür satırı yerinde kalır.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0019")
    engine = create_engine(sqlite_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO known_document_types (slug, name, file_label, sides, direct, "
                    "analyze, output_format, expected_file_types, front_back_layouts, "
                    "required_fields, allowed_conversions, acceptance_criteria, active) VALUES "
                    "('passport', 'Passport', 'Passport', 'single', 1, 1, 'keep', "
                    "'[]', '[]', '[]', '[]', '[]', 1)"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            columns = {
                c["name"]: c for c in inspect(connection).get_columns("known_document_types")
            }
            assert columns["archived_at"]["nullable"]
            assert columns["archived_by"]["nullable"]
            assert connection.execute(
                text("SELECT slug, archived_at, archived_by FROM known_document_types")
            ).all() == [("passport", None, None)]
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE known_document_types SET archived_at = '2026-09-29 00:00:00', "
                    "archived_by = 'ik'"
                )
            )

        command.downgrade(config, "0019")
        with engine.connect() as connection:
            columns = {c["name"] for c in inspect(connection).get_columns("known_document_types")}
            assert not {"archived_at", "archived_by"} & columns
            assert connection.execute(text("SELECT slug FROM known_document_types")).all() == [
                ("passport",)
            ]
    finally:
        engine.dispose()


def test_training_cleanup_migration_accepts_dismissed_and_archives_runs_reversibly(
    sqlite_url: str,
) -> None:
    # 0021 (11.9.6): `training_items.status` CHECK'i `dismissed`'i kabul eder, var olan öğeler
    # değişmez; `training_runs.archived_at` boş olabilir, var olan çalıştırmalar arşivsiz kalır.
    # Geri alış yoksayılmış öğeyi `unplaced`'e döndürür (eski CHECK'e sığmaz) ve sütunu düşürür.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0020")
    engine = create_engine(sqlite_url)
    insert_item = text(
        "INSERT INTO training_items (run_id, original_name, status) VALUES (1, :name, :status)"
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO training_runs (id, kind, created_by, created_at, status, "
                    "counts_json) VALUES (1, 'upload', 'ik', '2026-09-29 00:00:00', 'done', '{}')"
                )
            )
            connection.execute(insert_item, {"name": "a.pdf", "status": "unplaced"})
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(insert_item, {"name": "b.pdf", "status": "dismissed"})

        command.upgrade(config, "head")
        with engine.connect() as connection:
            columns = {c["name"]: c for c in inspect(connection).get_columns("training_runs")}
            assert columns["archived_at"]["nullable"]
            assert connection.execute(text("SELECT id, archived_at FROM training_runs")).all() == [
                (1, None)
            ]
            assert connection.execute(
                text("SELECT original_name, status FROM training_items")
            ).all() == [("a.pdf", "unplaced")]
        with engine.begin() as connection:
            connection.execute(insert_item, {"name": "b.pdf", "status": "dismissed"})
            connection.execute(text("UPDATE training_runs SET archived_at = '2026-09-29 00:00:00'"))
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(insert_item, {"name": "c.pdf", "status": "silindi"})

        command.downgrade(config, "0020")
        with engine.connect() as connection:
            columns = {c["name"] for c in inspect(connection).get_columns("training_runs")}
            assert "archived_at" not in columns
            assert connection.execute(
                text("SELECT original_name, status FROM training_items ORDER BY id")
            ).all() == [("a.pdf", "unplaced"), ("b.pdf", "unplaced")]
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(insert_item, {"name": "d.pdf", "status": "dismissed"})
    finally:
        engine.dispose()


def test_user_active_migration_keeps_existing_users_active_and_is_reversible(
    sqlite_url: str,
) -> None:
    # 0022 (10.1.4): var olan kullanıcılar etkin kalır (sunucu varsayılanı), sütun boş olamaz;
    # geri alış sütunu düşürür, kullanıcı satırı kalır.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0021")
    engine = create_engine(sqlite_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, username, password_hash, role) "
                    "VALUES (1, 'yonetici', 'ozet', 'admin')"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            columns = {c["name"]: c for c in inspect(connection).get_columns("users")}
            assert not columns["active"]["nullable"]
            assert connection.execute(text("SELECT username, active FROM users")).all() == [
                ("yonetici", 1)
            ]
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (username, password_hash, role, active) "
                    "VALUES ('baska', 'ozet', 'admin', NULL)"
                )
            )

        command.downgrade(config, "0021")
        with engine.connect() as connection:
            columns = {c["name"] for c in inspect(connection).get_columns("users")}
            assert "active" not in columns
            assert connection.scalar(text("SELECT username FROM users")) == "yonetici"
    finally:
        engine.dispose()


def test_telegram_link_codes_migration_adds_the_table_and_is_reversible(sqlite_url: str) -> None:
    # 0023 (12.1.4): bağlantı kodunun özeti tekildir, kod bir kullanıcıya bağlıdır; geri alış
    # tabloyu düşürür, kullanıcılar kalır.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0022")
    engine = create_engine(sqlite_url)
    insert_code = text(
        "INSERT INTO telegram_link_codes (code_hash, user_id, created_by, created_at, expires_at) "
        "VALUES (:hash, 1, 'yonetici', '2026-10-01 10:00:00', '2026-10-01 10:10:00')"
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, username, password_hash, role) "
                    "VALUES (1, 'yonetici', 'ozet', 'admin')"
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            columns = {c["name"]: c for c in inspect(connection).get_columns("telegram_link_codes")}
            assert set(columns) == {
                "id",
                "code_hash",
                "user_id",
                "created_by",
                "created_at",
                "expires_at",
                "used_at",
                "used_telegram_id",
                "revoked_at",
            }
            assert not columns["code_hash"]["nullable"] and columns["used_at"]["nullable"]
        with engine.begin() as connection:
            connection.execute(insert_code, {"hash": "a" * 64})
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(insert_code, {"hash": "a" * 64})

        command.downgrade(config, "0022")
        with engine.connect() as connection:
            assert "telegram_link_codes" not in inspect(connection).get_table_names()
            assert connection.scalar(text("SELECT username FROM users")) == "yonetici"
    finally:
        engine.dispose()


def test_user_language_migration_adds_a_checked_nullable_column_and_is_reversible(
    sqlite_url: str,
) -> None:
    # 0024 (10.10.2): var olan kullanıcının tercihi boş kalır; yalnız `en`, `tr`, `sr` yazılabilir;
    # geri alış sütunu düşürür, kullanıcı kalır.
    config = _alembic_config(sqlite_url)
    command.upgrade(config, "0023")
    engine = create_engine(sqlite_url)
    set_language = text("UPDATE users SET language = :language WHERE username = 'yonetici'")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (username, password_hash, role) "
                    "VALUES ('yonetici', 'ozet', 'admin')"
                )
            )

        command.upgrade(config, "0024")
        with engine.connect() as connection:
            columns = {c["name"]: c for c in inspect(connection).get_columns("users")}
            assert columns["language"]["nullable"]
            assert connection.scalar(text("SELECT language FROM users")) is None
        for language in ("en", "tr", "sr", None):
            with engine.begin() as connection:
                connection.execute(set_language, {"language": language})
        for invalid in ("de", "EN", "sr-Latn", ""):
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(set_language, {"language": invalid})

        command.downgrade(config, "0023")
        with engine.connect() as connection:
            columns = {c["name"] for c in inspect(connection).get_columns("users")}
            assert "language" not in columns
            assert connection.scalar(text("SELECT username FROM users")) == "yonetici"
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
