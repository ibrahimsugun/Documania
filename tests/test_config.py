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


AI_VARIABLES = (
    "AI_PROVIDER",
    "AI_MAX_OUTPUT_TOKENS",
    "AI_REQUEST_TIMEOUT_SECONDS",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
)


def test_ai_settings_have_defaults_and_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    for name in AI_VARIABLES:
        monkeypatch.delenv(name, raising=False)

    defaults = load_settings(_env_file=None)
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_MAX_OUTPUT_TOKENS", "1024")
    monkeypatch.setenv("AI_REQUEST_TIMEOUT_SECONDS", "30.5")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    configured = load_settings(_env_file=None)

    assert (defaults.ai_provider, defaults.ai_max_output_tokens) == ("anthropic", 4096)
    assert defaults.ai_request_timeout_seconds == 120.0
    assert (defaults.anthropic_api_key, defaults.anthropic_model) == (None, "claude-opus-5")
    assert (defaults.openai_api_key, defaults.openai_model) == (None, "gpt-5.5")
    assert (configured.ai_provider, configured.ai_max_output_tokens) == ("openai", 1024)
    assert configured.ai_request_timeout_seconds == 30.5
    assert configured.anthropic_api_key is not None
    assert configured.anthropic_api_key.get_secret_value() == "test-key"
    assert configured.anthropic_model == "claude-test"
    assert configured.openai_api_key is not None
    assert configured.openai_api_key.get_secret_value() == "test-openai-key"
    assert configured.openai_model == "gpt-test"


def test_env_example_documents_ai_settings() -> None:
    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assigned = {line.split("=", 1)[0] for line in example.splitlines() if "=" in line}

    assert set(AI_VARIABLES) <= assigned
    # Gerçek anahtar şablona yazılmaz.
    assert "ANTHROPIC_API_KEY=\n" in example


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AI_PROVIDER", "Anthropic"),
        ("AI_MAX_OUTPUT_TOKENS", "0"),
        ("AI_REQUEST_TIMEOUT_SECONDS", "0"),
        ("ANTHROPIC_MODEL", ""),
        ("OPENAI_MODEL", ""),
    ],
)
def test_invalid_ai_settings_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match=name.lower()):
        load_settings(_env_file=None)


def test_session_lifetime_has_a_default_reads_environment_and_is_documented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 10.1.2: panel oturumunun ömrü.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.delenv("SESSION_MAX_AGE_SECONDS", raising=False)
    assert load_settings(_env_file=None).session_max_age_seconds == 12 * 60 * 60

    monkeypatch.setenv("SESSION_MAX_AGE_SECONDS", "900")
    assert load_settings(_env_file=None).session_max_age_seconds == 900

    monkeypatch.setenv("SESSION_MAX_AGE_SECONDS", "0")
    with pytest.raises(ValidationError, match="session_max_age_seconds"):
        load_settings(_env_file=None)

    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assert "SESSION_MAX_AGE_SECONDS=43200\n" in example
