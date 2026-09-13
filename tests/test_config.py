from pathlib import Path

import pytest

from app.config import load_settings


def test_settings_read_from_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATA_DIR", "/srv/veri")

    settings = load_settings(_env_file=None)

    assert settings.database_url == "sqlite:///./data/test.db"
    assert settings.app_env == "production"
    assert settings.data_dir == Path("/srv/veri")


def test_settings_read_from_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql+psycopg://user:pw@host:5432/belgeee\n")

    settings = load_settings(_env_file=env_file)

    assert settings.database_url == "postgresql+psycopg://user:pw@host:5432/belgeee"


def test_optional_settings_have_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)

    settings = load_settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.data_dir == Path("data")


def test_missing_required_setting_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        load_settings(_env_file=None)
