from decimal import Decimal
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
    assert (defaults.openai_api_key, defaults.openai_model) == (None, "gpt-6-luna")
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


COST_VARIABLES = (
    "ANTHROPIC_PRESCREEN_MODEL",
    "OPENAI_PRESCREEN_MODEL",
    "PAGE_RENDER_TEXT_LAYER_MAX_LONG_EDGE_PX",
)


def test_prescreen_and_text_layer_settings_have_defaults_read_environment_and_are_documented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    for name in COST_VARIABLES:
        monkeypatch.delenv(name, raising=False)

    defaults = load_settings(_env_file=None)
    monkeypatch.setenv("ANTHROPIC_PRESCREEN_MODEL", "claude-ucuz")
    monkeypatch.setenv("OPENAI_PRESCREEN_MODEL", "gpt-ucuz")
    monkeypatch.setenv("PAGE_RENDER_TEXT_LAYER_MAX_LONG_EDGE_PX", "800")
    configured = load_settings(_env_file=None)

    # 13.2.1 ön eleme varsayılan kapalı; 13.2.2 metin katmanı sınırı varsayılan açık.
    assert (
        defaults.anthropic_prescreen_model,
        defaults.openai_prescreen_model,
        defaults.page_render_text_layer_max_long_edge_px,
    ) == (None, None, 1024)
    assert (
        configured.anthropic_prescreen_model,
        configured.openai_prescreen_model,
        configured.page_render_text_layer_max_long_edge_px,
    ) == ("claude-ucuz", "gpt-ucuz", 800)
    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assert "\nPAGE_RENDER_TEXT_LAYER_MAX_LONG_EDGE_PX=1024\n" in example
    assert "\n# ANTHROPIC_PRESCREEN_MODEL=" in example
    assert "\n# OPENAI_PRESCREEN_MODEL=" in example


def test_invalid_text_layer_long_edge_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.setenv("PAGE_RENDER_TEXT_LAYER_MAX_LONG_EDGE_PX", "0")

    with pytest.raises(ValidationError, match="page_render_text_layer_max_long_edge_px"):
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


TELEGRAM_VARIABLES = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_URL",
    "TELEGRAM_WEBHOOK_SECRET",
    "TELEGRAM_WEBHOOK_LISTEN",
    "TELEGRAM_WEBHOOK_PORT",
)


def test_telegram_settings_have_defaults_read_environment_and_are_documented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 12.1.1: bot ayarları; token ve webhook gizli değeri gizli tip olarak tutulur.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    for name in TELEGRAM_VARIABLES:
        monkeypatch.delenv(name, raising=False)

    defaults = load_settings(_env_file=None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "https://belge.example.com/hook")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_LISTEN", "0.0.0.0")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_PORT", "8080")
    configured = load_settings(_env_file=None)

    assert (defaults.telegram_bot_token, defaults.telegram_webhook_url) == (None, None)
    assert defaults.telegram_webhook_secret is None
    assert (defaults.telegram_webhook_listen, defaults.telegram_webhook_port) == ("127.0.0.1", 8443)
    assert configured.telegram_bot_token is not None
    assert configured.telegram_bot_token.get_secret_value() == "test-token"
    assert "test-token" not in repr(configured)
    assert configured.telegram_webhook_url == "https://belge.example.com/hook"
    assert configured.telegram_webhook_secret is not None
    assert configured.telegram_webhook_secret.get_secret_value() == "test-secret"
    assert "test-secret" not in repr(configured)
    assert (configured.telegram_webhook_listen, configured.telegram_webhook_port) == (
        "0.0.0.0",
        8080,
    )

    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assigned = {line.split("=", 1)[0] for line in example.splitlines() if "=" in line}
    assert set(TELEGRAM_VARIABLES) <= assigned
    # Gerçek token ve gizli değer şablona yazılmaz.
    assert "TELEGRAM_BOT_TOKEN=\n" in example
    assert "TELEGRAM_WEBHOOK_SECRET=\n" in example


@pytest.mark.parametrize(
    ("name", "value"), [("TELEGRAM_WEBHOOK_PORT", "0"), ("TELEGRAM_WEBHOOK_PORT", "70000")]
)
def test_invalid_telegram_port_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match=name.lower()):
        load_settings(_env_file=None)


def test_model_prices_default_empty_and_read_json_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 13.1.1: maliyet paneli fiyatları model adına göre bu tablodan okur.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.delenv("AI_MODEL_PRICES", raising=False)
    assert load_settings(_env_file=None).ai_model_prices == {}

    monkeypatch.setenv(
        "AI_MODEL_PRICES",
        '{"claude-test": {"input_per_mtok": 5, "output_per_mtok": 25.5},'
        ' "gpt-test": {"input_per_mtok": "1.25", "output_per_mtok": 10}}',
    )
    prices = load_settings(_env_file=None).ai_model_prices

    assert set(prices) == {"claude-test", "gpt-test"}
    assert (prices["claude-test"].input_per_mtok, prices["claude-test"].output_per_mtok) == (
        Decimal(5),
        Decimal("25.5"),
    )
    assert prices["gpt-test"].input_per_mtok == Decimal("1.25")


@pytest.mark.parametrize(
    "value",
    [
        '{"m": {"input_per_mtok": -1, "output_per_mtok": 1}}',
        '{"m": {"input_per_mtok": 1}}',
        '{"m": {"input_per_mtok": 1, "output_per_mtok": 1, "currency": "TRY"}}',
        '{"m": {"input_per_mtok": "abc", "output_per_mtok": 1}}',
    ],
)
def test_invalid_model_prices_are_rejected(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.setenv("AI_MODEL_PRICES", value)

    with pytest.raises(ValidationError, match="ai_model_prices"):
        load_settings(_env_file=None)


def test_env_example_documents_model_prices_with_a_working_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    (line,) = [line for line in example.splitlines() if line.startswith("# AI_MODEL_PRICES=")]
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=sqlite:///./data/test.db\n" + line.removeprefix("# ") + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("AI_MODEL_PRICES", raising=False)

    prices = load_settings(_env_file=env_file).ai_model_prices

    # Örnek tabloda olmayan bir modeli önbellek fiyatıyla ekler (yerleşik tablo, C77).
    assert set(prices) == {"my-model"}
    assert prices["my-model"].cached_input_per_mtok == Decimal("0.5")


WORKER_VARIABLES = (
    "WORKER_LEASE_SECONDS",
    "WORKER_MAX_ATTEMPTS",
    "WORKER_POLL_SECONDS",
)


def test_worker_settings_have_defaults_read_the_environment_and_are_documented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 13.3.1: kalıcı işçi kuyruğu.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    for name in WORKER_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    defaults = load_settings(_env_file=None)
    assert (
        defaults.worker_lease_seconds,
        defaults.worker_max_attempts,
        defaults.worker_poll_seconds,
    ) == (120, 3, 5.0)

    for name, value in zip(WORKER_VARIABLES, ("300", "5", "0.5"), strict=True):
        monkeypatch.setenv(name, value)
    configured = load_settings(_env_file=None)
    assert (
        configured.worker_lease_seconds,
        configured.worker_max_attempts,
        configured.worker_poll_seconds,
    ) == (300, 5, 0.5)

    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assert "WORKER_ENABLED" not in example
    for line in (
        "WORKER_LEASE_SECONDS=120",
        "WORKER_MAX_ATTEMPTS=3",
        "WORKER_POLL_SECONDS=5",
    ):
        assert f"\n{line}\n" in example


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("WORKER_LEASE_SECONDS", "9"),
        ("WORKER_MAX_ATTEMPTS", "0"),
        ("WORKER_POLL_SECONDS", "0"),
    ],
)
def test_invalid_worker_settings_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match=name.lower()):
        load_settings(_env_file=None)


ALERT_VARIABLES = (
    "ALERT_ERROR_COUNT",
    "ALERT_ERROR_WINDOW_MINUTES",
    "ALERT_DISK_USED_PERCENT",
    "ALERT_JOB_QUEUE_LENGTH",
    "ALERT_REVIEW_QUEUE_LENGTH",
    "ALERT_CHECK_SECONDS",
    "ALERT_REPEAT_MINUTES",
)


def _alert_values(settings: object) -> tuple[object, ...]:
    return tuple(
        getattr(settings, name.lower())
        for name in ALERT_VARIABLES  # `ALERT_ERROR_COUNT` -> `alert_error_count`
    )


def test_alert_settings_have_defaults_read_the_environment_and_are_documented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 13.6.1: izleme ve uyarı eşikleri.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    for name in ALERT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    defaults = load_settings(_env_file=None)
    assert _alert_values(defaults) == (3, 60, 85.0, 20, 50, 60.0, 360)

    for name, value in zip(
        ALERT_VARIABLES, ("5", "30", "90.5", "10", "25", "15", "60"), strict=True
    ):
        monkeypatch.setenv(name, value)
    configured = load_settings(_env_file=None)
    assert _alert_values(configured) == (5, 30, 90.5, 10, 25, 15.0, 60)

    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    for line in (
        "ALERT_ERROR_COUNT=3",
        "ALERT_ERROR_WINDOW_MINUTES=60",
        "ALERT_DISK_USED_PERCENT=85",
        "ALERT_JOB_QUEUE_LENGTH=20",
        "ALERT_REVIEW_QUEUE_LENGTH=50",
        "ALERT_CHECK_SECONDS=60",
        "ALERT_REPEAT_MINUTES=360",
    ):
        assert f"\n{line}\n" in example


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ALERT_ERROR_COUNT", "0"),
        ("ALERT_ERROR_WINDOW_MINUTES", "0"),
        ("ALERT_DISK_USED_PERCENT", "0"),
        ("ALERT_DISK_USED_PERCENT", "101"),
        ("ALERT_JOB_QUEUE_LENGTH", "0"),
        ("ALERT_REVIEW_QUEUE_LENGTH", "0"),
        ("ALERT_CHECK_SECONDS", "0"),
        ("ALERT_REPEAT_MINUTES", "0"),
    ],
)
def test_invalid_alert_settings_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match=name.lower()):
        load_settings(_env_file=None)
