from pathlib import Path

import pytest
from pydantic import ValidationError

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


PAGE_RENDER_VARIABLES = (
    "PAGE_RENDER_DPI",
    "PAGE_RENDER_MAX_LONG_EDGE_PX",
    "PAGE_RENDER_JPEG_QUALITY",
)


def test_page_render_settings_have_defaults_and_read_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    for name in PAGE_RENDER_VARIABLES:
        monkeypatch.delenv(name, raising=False)

    defaults = load_settings(_env_file=None)
    monkeypatch.setenv("PAGE_RENDER_DPI", "300")
    monkeypatch.setenv("PAGE_RENDER_MAX_LONG_EDGE_PX", "2000")
    monkeypatch.setenv("PAGE_RENDER_JPEG_QUALITY", "75")
    configured = load_settings(_env_file=None)

    assert (
        defaults.page_render_dpi,
        defaults.page_render_max_long_edge_px,
        defaults.page_render_jpeg_quality,
    ) == (200, 1568, 90)
    assert (
        configured.page_render_dpi,
        configured.page_render_max_long_edge_px,
        configured.page_render_jpeg_quality,
    ) == (300, 2000, 75)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PAGE_RENDER_DPI", "0"),
        ("PAGE_RENDER_MAX_LONG_EDGE_PX", "-1"),
        ("PAGE_RENDER_JPEG_QUALITY", "0"),
        ("PAGE_RENDER_JPEG_QUALITY", "101"),
    ],
)
def test_invalid_page_render_settings_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match=name.lower()):
        load_settings(_env_file=None)
