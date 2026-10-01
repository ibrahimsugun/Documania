"""13.5.3 — şema ve kod sürümü uyuşmazlığı koruması (tm 141, PLAN.md §D77, §D79).

Panel, işçi ve bot açılışta veritabanının göç sürümünü koddaki son göçle karşılaştırır: göç hiç
koşulmamışsa, şema eskiyse ya da veritabanı kodun bilmediği ileri bir sürümdeyse açılmaz ve iki
sürümü ve çare komutunu söyler. `/health` oturumsuz `{status, schema, code}` döner.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import Settings, get_settings, load_settings
from app.db import schema_check
from app.db.models import Base
from app.db.schema_check import (
    SchemaVersionError,
    current_revision,
    ensure_schema_current,
    expected_revision,
    schema_mismatch,
)
from app.main import create_app
from app.telegram import bot as bot_module
from app.web.code_watch import CodeWatch, fingerprint
from app.worker import __main__ as worker_entrypoint
from tests.telegram.conftest import TOKEN

REPO_ROOT = Path(__file__).resolve().parents[1]
HEAD = expected_revision()


def _migrate(database_url: str, revision: str) -> None:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False
    command.upgrade(config, revision)


def _url(tmp_path: Path, name: str = "belgeee.db") -> str:
    return f"sqlite:///{(tmp_path / name).as_posix()}"


@pytest.fixture
def blank_db(tmp_path: Path) -> str:
    """Göç koşulmamış temiz veritabanı."""
    return _url(tmp_path)


@pytest.fixture
def old_db(tmp_path: Path) -> str:
    """Kullanıcının veritabanı gibi `0013`'te kalmış şema (§D77)."""
    database_url = _url(tmp_path)
    _migrate(database_url, "0013")
    return database_url


@pytest.fixture
def head_db(tmp_path: Path) -> str:
    database_url = _url(tmp_path)
    _migrate(database_url, "head")
    return database_url


@pytest.fixture
def forward_db(tmp_path: Path) -> str:
    """Bu kodun bilmediği ileri bir göçte (yeni kodla yükseltilmiş, eski kodla açılan) şema."""
    database_url = _url(tmp_path)
    _migrate(database_url, "head")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = '9999'"))
    engine.dispose()
    return database_url


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[pytest.MonkeyPatch]:
    """Ayarlar ortam değişkenlerinden; depo kökündeki `.env` okunmaz."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "veri"))
    monkeypatch.delenv("STARTUP_SCHEMA_CHECK", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def _settings(database_url: str, tmp_path: Path, **overrides: object) -> Settings:
    return load_settings(
        _env_file=None, database_url=database_url, data_dir=tmp_path / "veri", **overrides
    )


def _assert_message(message: str, current: str) -> None:
    assert f"Mevcut sürüm: {current}" in message
    assert f"beklenen sürüm: {HEAD}" in message
    assert "python -m alembic upgrade head" in message
    assert "baslat.bat" in message


# --- sürüm karşılaştırması ---------------------------------------------------------------


def test_the_expected_revision_is_the_last_migration_in_the_repo() -> None:
    versions = sorted(path.name[:4] for path in (REPO_ROOT / "alembic" / "versions").glob("0*.py"))
    assert HEAD == versions[-1]


def test_current_revision_reads_alembic_version_and_none_without_it(
    old_db: str, tmp_path: Path
) -> None:
    old = create_engine(old_db)
    blank = create_engine(_url(tmp_path, "bos.db"))
    try:
        assert current_revision(old) == "0013"
        assert current_revision(blank) is None
    finally:
        old.dispose()
        blank.dispose()


def test_matching_revision_is_no_mismatch() -> None:
    assert schema_mismatch(HEAD, HEAD) is None


@pytest.mark.parametrize(
    ("current", "reason"),
    [
        (None, "göç sürümü yok"),
        ("0013", "şeması eski"),
        ("0001", "şeması eski"),
    ],
)
def test_missing_or_old_revision_names_both_versions_and_the_command(
    current: str | None, reason: str
) -> None:
    message = schema_mismatch(current, HEAD)

    assert message is not None and reason in message
    _assert_message(message, current or "yok")


def test_a_revision_unknown_to_the_code_is_a_forward_schema_and_says_update_the_code() -> None:
    message = schema_mismatch("9999", HEAD)

    assert message is not None
    assert "ileri bir sürümde" in message
    assert f"Mevcut sürüm: 9999, beklenen sürüm: {HEAD}" in message
    assert "Kodu veritabanını yükselten sürüme güncelleyin" in message
    assert "baslat.bat" in message


def test_several_recorded_revisions_are_a_mismatch() -> None:
    message = schema_mismatch(f"0021, {HEAD}", HEAD)

    assert message is not None and "birden fazla göç sürümü" in message


# --- ensure_schema_current ---------------------------------------------------------------


def test_head_schema_passes_and_returns_the_revision(head_db: str, tmp_path: Path) -> None:
    assert ensure_schema_current(_settings(head_db, tmp_path)) == HEAD


@pytest.mark.parametrize(("fixture", "current"), [("blank_db", "yok"), ("old_db", "0013")])
def test_blank_or_old_schema_is_refused(
    fixture: str, current: str, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    database_url = request.getfixturevalue(fixture)

    with pytest.raises(SchemaVersionError) as excinfo:
        ensure_schema_current(_settings(database_url, tmp_path))

    _assert_message(str(excinfo.value), current)


def test_tables_without_migration_record_are_refused(tmp_path: Path) -> None:
    # Şemayı `create_all` ile kurmak göç kaydı bırakmaz: açılış bunu da göçsüz sayar.
    database_url = _url(tmp_path)
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    engine.dispose()

    with pytest.raises(SchemaVersionError) as excinfo:
        ensure_schema_current(_settings(database_url, tmp_path))

    _assert_message(str(excinfo.value), "yok")


def test_forward_schema_is_refused(forward_db: str, tmp_path: Path) -> None:
    with pytest.raises(SchemaVersionError, match="ileri bir sürümde"):
        ensure_schema_current(_settings(forward_db, tmp_path))


def test_the_check_only_reads(old_db: str, tmp_path: Path) -> None:
    with pytest.raises(SchemaVersionError):
        ensure_schema_current(_settings(old_db, tmp_path))

    engine = create_engine(old_db)
    assert current_revision(engine) == "0013"
    engine.dispose()


def test_the_check_can_be_switched_off_for_create_all_tests(blank_db: str, tmp_path: Path) -> None:
    settings = _settings(blank_db, tmp_path, startup_schema_check=False)

    assert ensure_schema_current(settings) is None


def test_the_check_is_on_by_default() -> None:
    assert load_settings(_env_file=None, database_url="sqlite://").startup_schema_check is True


def test_a_branched_migration_chain_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    branched = MagicMock()
    branched.get_heads.return_value = ["0022", "0023a"]
    monkeypatch.setattr(schema_check, "_script_directory", lambda: branched)

    with pytest.raises(SchemaVersionError, match="tek son sürüm yok: 0022, 0023a"):
        expected_revision()


def test_missing_migration_scripts_stop_startup_but_not_the_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Paket site-packages'tan yüklenmiş ve çalışma dizininde `alembic/` yok.
    monkeypatch.setattr(schema_check, "__file__", str(tmp_path / "site" / "app" / "db" / "x.py"))
    monkeypatch.chdir(tmp_path)
    schema_check._script_directory.cache_clear()
    try:
        application = create_app(_settings(_url(tmp_path), tmp_path))
        assert application.state.schema_revision is None

        with pytest.raises(SchemaVersionError, match="Göç betikleri bulunamadı"):
            with TestClient(application):
                pytest.fail("panel açılmamalıydı")
    finally:
        schema_check._script_directory.cache_clear()


def test_scripts_are_found_from_the_working_directory_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(schema_check, "__file__", str(tmp_path / "site" / "app" / "db" / "x.py"))
    monkeypatch.chdir(REPO_ROOT)
    schema_check._script_directory.cache_clear()
    try:
        assert expected_revision() == HEAD
    finally:
        schema_check._script_directory.cache_clear()


# --- panel ---------------------------------------------------------------------------------


@pytest.mark.parametrize(("fixture", "current"), [("blank_db", "yok"), ("old_db", "0013")])
def test_panel_does_not_start_on_a_blank_or_old_schema(
    fixture: str, current: str, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    database_url = request.getfixturevalue(fixture)

    with pytest.raises(SchemaVersionError) as excinfo:
        with TestClient(create_app(_settings(database_url, tmp_path))):
            pytest.fail("panel açılmamalıydı")

    _assert_message(str(excinfo.value), current)
    # Denetim veri dizininden ve katalog tohumundan önce: hiçbir şey kurulmadı.
    assert not (tmp_path / "veri").exists()


def test_panel_does_not_start_on_a_forward_schema(forward_db: str, tmp_path: Path) -> None:
    with pytest.raises(SchemaVersionError, match="ileri bir sürümde"):
        with TestClient(create_app(_settings(forward_db, tmp_path))):
            pytest.fail("panel açılmamalıydı")


def test_panel_starts_on_the_head_schema_and_health_reports_versions(
    head_db: str, tmp_path: Path
) -> None:
    application = create_app(_settings(head_db, tmp_path))

    with TestClient(application) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "schema": HEAD,
        "code": application.state.code_watch.short,
    }


def test_health_needs_no_session_and_reveals_only_short_versions(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["schema"] == HEAD
    assert len(body["code"]) == 12 and int(body["code"], 16) >= 0
    assert "set-cookie" not in response.headers


def test_health_code_is_the_startup_fingerprint_of_the_app_package() -> None:
    application = create_app()

    assert application.state.code_watch.startup == fingerprint(REPO_ROOT / "app")


# --- işçi ----------------------------------------------------------------------------------


@pytest.mark.parametrize(("fixture", "current"), [("blank_db", "yok"), ("old_db", "0013")])
def test_worker_does_not_start_on_a_blank_or_old_schema(
    fixture: str,
    current: str,
    request: pytest.FixtureRequest,
    env: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env.setenv("DATABASE_URL", request.getfixturevalue(fixture))
    env.setattr(worker_entrypoint, "create_worker", MagicMock(side_effect=AssertionError))

    assert worker_entrypoint.main() == 1

    _assert_message(capsys.readouterr().err, current)
    assert not (tmp_path / "veri").exists()


def test_worker_starts_on_the_head_schema(head_db: str, env: pytest.MonkeyPatch) -> None:
    env.setenv("DATABASE_URL", head_db)
    built: list[object] = []

    class StoppedWorker:
        def start(self, *, paused: bool = False) -> None:
            pass

        def resume(self) -> None:
            pass

        def request_stop(self) -> None:
            pass

        def wait(self) -> bool:
            return True

        def stop(self, timeout: float = 5.0) -> None:
            pass

    env.setattr(
        worker_entrypoint,
        "create_worker",
        lambda settings, layout: built.append(settings) or StoppedWorker(),
    )
    env.setattr(worker_entrypoint.signal, "signal", lambda signum, handler: None)

    assert worker_entrypoint.main() == 0
    assert len(built) == 1


# --- bot -----------------------------------------------------------------------------------


@pytest.mark.parametrize(("fixture", "current"), [("blank_db", "yok"), ("old_db", "0013")])
def test_bot_does_not_start_on_a_blank_or_old_schema(
    fixture: str,
    current: str,
    request: pytest.FixtureRequest,
    env: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env.setenv("DATABASE_URL", request.getfixturevalue(fixture))
    env.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    env.setattr(bot_module, "run", MagicMock(side_effect=AssertionError))

    assert bot_module.main() == 1

    _assert_message(capsys.readouterr().err, current)
    assert not (tmp_path / "veri").exists()


def test_bot_starts_on_the_head_schema(head_db: str, env: pytest.MonkeyPatch) -> None:
    env.setenv("DATABASE_URL", head_db)
    env.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    env.setattr(bot_module, "get_session_factory", lambda: MagicMock())
    started: list[object] = []
    env.setattr(bot_module, "run", lambda application, config: started.append(config))

    assert bot_module.main() == 0
    assert len(started) == 1


# --- kod parmak izi ------------------------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def code_tree(tmp_path: Path) -> Path:
    root = tmp_path / "app"
    (root / "web" / "templates").mkdir(parents=True)
    (root / "web" / "static").mkdir()
    (root / "__pycache__").mkdir()
    (root / "main.py").write_text("x = 1\n", encoding="utf-8")
    (root / "web" / "templates" / "base.html").write_text("<p>a</p>\n", encoding="utf-8")
    (root / "web" / "static" / "panel.css").write_text("p {}\n", encoding="utf-8")
    (root / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"\0")
    return root


def _touch(path: Path, delta_ns: int = 5_000_000_000) -> None:
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + delta_ns))


def test_unchanged_code_is_not_stale(code_tree: Path) -> None:
    clock = FakeClock()
    watch = CodeWatch(code_tree, clock=clock)
    clock.now += 31

    assert watch.is_stale() is False


@pytest.mark.parametrize("changed", ["main.py", "web/templates/base.html"])
def test_a_changed_module_or_template_makes_the_process_stale(
    code_tree: Path, changed: str
) -> None:
    clock = FakeClock()
    watch = CodeWatch(code_tree, clock=clock)
    _touch(code_tree / changed)
    clock.now += 31

    assert watch.is_stale() is True


def test_a_new_module_makes_the_process_stale(code_tree: Path) -> None:
    clock = FakeClock()
    watch = CodeWatch(code_tree, clock=clock)
    (code_tree / "yeni.py").write_text("", encoding="utf-8")
    clock.now += 31

    assert watch.is_stale() is True


@pytest.mark.parametrize("unwatched", ["web/static/panel.css", "__pycache__/main.cpython-312.pyc"])
def test_static_files_and_bytecode_are_not_watched(code_tree: Path, unwatched: str) -> None:
    clock = FakeClock()
    watch = CodeWatch(code_tree, clock=clock)
    _touch(code_tree / unwatched)
    clock.now += 31

    assert watch.is_stale() is False


def test_the_fingerprint_is_recomputed_at_most_every_30_seconds(code_tree: Path) -> None:
    clock = FakeClock()
    watch = CodeWatch(code_tree, clock=clock)
    _touch(code_tree / "main.py")

    clock.now += 29
    assert watch.is_stale() is False
    clock.now += 2
    assert watch.is_stale() is True


def test_a_stale_process_stays_stale_until_restarted(code_tree: Path) -> None:
    clock = FakeClock()
    watch = CodeWatch(code_tree, clock=clock)
    _touch(code_tree / "main.py")
    clock.now += 31
    assert watch.is_stale() is True

    _touch(code_tree / "main.py", -5_000_000_000)
    clock.now += 31
    assert watch.is_stale() is True


def test_an_unreadable_tree_is_not_reported_as_stale(
    code_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeClock()
    watch = CodeWatch(code_tree, clock=clock)

    def broken(_root: Path) -> str:
        raise PermissionError("erişim yok")

    monkeypatch.setattr("app.web.code_watch.fingerprint", broken)
    clock.now += 31

    assert watch.is_stale() is False


def test_the_short_code_is_the_start_of_the_startup_fingerprint(code_tree: Path) -> None:
    watch = CodeWatch(code_tree)

    assert watch.short == fingerprint(code_tree)[:12]
    _touch(code_tree / "main.py")
    assert watch.short != fingerprint(code_tree)[:12]
