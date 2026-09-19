"""12.1.1 — bot ayrı süreç olarak çalışır: geliştirmede polling, üretimde webhook."""

import logging
import os
import runpy
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, create_autospec

import pytest
from telegram.ext import Application, ApplicationBuilder

from app.config import get_settings
from app.telegram import bot as bot_module
from app.telegram.bot import (
    HANDLED_UPDATES,
    BotConfig,
    BotConfigError,
    BotMode,
    build_application,
    load_bot_config,
    run,
)
from tests.telegram.conftest import TOKEN, FakeTelegram, bot_settings, polling_config

WEBHOOK_URL = "https://belge.example.com/telegram/webhook"
SECRET = "gizli-deger_123"


def production(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "app_env": "production",
        "telegram_webhook_url": WEBHOOK_URL,
        "telegram_webhook_secret": SECRET,
    }
    values.update(overrides)
    return values


def test_development_selects_polling_and_needs_only_the_token() -> None:
    config = load_bot_config(bot_settings())

    assert config.mode is BotMode.POLLING
    assert config.token == TOKEN
    assert config.webhook_url is None
    assert config.secret_token is None


def test_development_ignores_webhook_settings() -> None:
    config = load_bot_config(
        bot_settings(telegram_webhook_url="http://yanlis", telegram_webhook_secret="boşluklu değer")
    )

    assert config.mode is BotMode.POLLING


def test_production_selects_webhook() -> None:
    config = load_bot_config(
        bot_settings(**production(telegram_webhook_listen="0.0.0.0", telegram_webhook_port=8080))
    )

    assert config.mode is BotMode.WEBHOOK
    assert config.webhook_url == WEBHOOK_URL
    assert config.url_path == "telegram/webhook"
    assert config.secret_token == SECRET
    assert (config.listen, config.port) == ("0.0.0.0", 8080)


def test_polling_config_has_no_webhook_path() -> None:
    assert load_bot_config(bot_settings()).url_path == ""


def test_webhook_defaults_listen_on_loopback() -> None:
    config = load_bot_config(bot_settings(**production()))

    assert (config.listen, config.port) == ("127.0.0.1", 8443)


def test_webhook_url_without_a_path_listens_on_root() -> None:
    config = load_bot_config(bot_settings(**production(telegram_webhook_url="https://b.example")))

    assert config.url_path == ""


def test_missing_token_is_a_clear_error() -> None:
    with pytest.raises(BotConfigError, match="TELEGRAM_BOT_TOKEN"):
        load_bot_config(bot_settings(telegram_bot_token=None))
    with pytest.raises(BotConfigError, match="TELEGRAM_BOT_TOKEN"):
        load_bot_config(bot_settings(telegram_bot_token="   "))


def test_token_is_stripped() -> None:
    assert load_bot_config(bot_settings(telegram_bot_token=f"  {TOKEN}\n")).token == TOKEN


@pytest.mark.parametrize(
    ("overrides", "variable"),
    [
        ({"telegram_webhook_url": None}, "TELEGRAM_WEBHOOK_URL"),
        ({"telegram_webhook_url": ""}, "TELEGRAM_WEBHOOK_URL"),
        ({"telegram_webhook_url": "http://belge.example.com/hook"}, "TELEGRAM_WEBHOOK_URL"),
        ({"telegram_webhook_url": "https:///hook"}, "TELEGRAM_WEBHOOK_URL"),
        ({"telegram_webhook_url": "belge.example.com/hook"}, "TELEGRAM_WEBHOOK_URL"),
        ({"telegram_webhook_secret": None}, "TELEGRAM_WEBHOOK_SECRET"),
        ({"telegram_webhook_secret": "  "}, "TELEGRAM_WEBHOOK_SECRET"),
        ({"telegram_webhook_secret": "boşluk var"}, "TELEGRAM_WEBHOOK_SECRET"),
        ({"telegram_webhook_secret": "a" * 257}, "TELEGRAM_WEBHOOK_SECRET"),
    ],
)
def test_production_rejects_incomplete_webhook_settings(
    overrides: dict[str, object], variable: str
) -> None:
    with pytest.raises(BotConfigError, match=variable):
        load_bot_config(bot_settings(**production(**overrides)))


@pytest.mark.parametrize("missing", [None, "", "  "])
def test_production_requires_the_webhook_secret(missing: str | None) -> None:
    """Gizli değer yoksa webhook'a herkes sahte güncelleme yollayıp beyaz listeyi atlayabilir."""
    with pytest.raises(BotConfigError, match="TELEGRAM_WEBHOOK_SECRET zorunlu"):
        load_bot_config(bot_settings(**production(telegram_webhook_secret=missing)))


def test_config_errors_never_echo_secret_values() -> None:
    with pytest.raises(BotConfigError) as excinfo:
        load_bot_config(bot_settings(**production(telegram_webhook_secret="boşluk var")))

    assert "boşluk var" not in str(excinfo.value)
    assert TOKEN not in str(excinfo.value)


def test_config_repr_hides_token_and_secret() -> None:
    config = load_bot_config(bot_settings(**production()))

    assert TOKEN not in repr(config)
    assert SECRET not in repr(config)


def test_build_application_makes_no_network_call() -> None:
    """Kurulum yalnız nesne kurar; `getMe` gibi çağrılar başlatmada (`run_*`) yapılır."""
    telegram = FakeTelegram()

    build_application(polling_config(), MagicMock(), builder=ApplicationBuilder().request(telegram))

    assert telegram.calls == []


def test_run_polls_in_development() -> None:
    application = create_autospec(Application, instance=True)

    run(application, load_bot_config(bot_settings()))

    application.run_polling.assert_called_once_with(allowed_updates=list(HANDLED_UPDATES))
    application.run_webhook.assert_not_called()


def test_run_serves_the_webhook_in_production() -> None:
    application = create_autospec(Application, instance=True)
    config = load_bot_config(bot_settings(**production(telegram_webhook_port=8080)))

    run(application, config)

    application.run_webhook.assert_called_once_with(
        listen="127.0.0.1",
        port=8080,
        url_path="telegram/webhook",
        webhook_url=WEBHOOK_URL,
        secret_token=SECRET,
        allowed_updates=list(HANDLED_UPDATES),
    )
    application.run_polling.assert_not_called()


def test_only_messages_and_callbacks_are_requested() -> None:
    assert [str(kind) for kind in HANDLED_UPDATES] == ["message", "callback_query"]


@pytest.fixture
def clean_process(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """`main()` ortam ve kayıtçı düzeyini değiştirir: `.env`'siz dizin, temiz ayar önbelleği."""
    monkeypatch.chdir(tmp_path)
    for name in (
        "APP_ENV",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_WEBHOOK_URL",
        "TELEGRAM_WEBHOOK_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    saved = {name: logging.getLogger(name).level for name in ("httpx", "httpcore")}
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    for name, level in saved.items():
        logging.getLogger(name).setLevel(level)


def test_main_reports_a_missing_token_and_exits_nonzero(
    clean_process: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert bot_module.main() == 1

    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err


def test_main_starts_the_bot_and_keeps_the_token_out_of_transport_logs(
    clean_process: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    started: list[tuple[object, BotConfig]] = []
    monkeypatch.setattr(bot_module, "get_session_factory", lambda: MagicMock())
    monkeypatch.setattr(
        bot_module, "run", lambda application, config: started.append((application, config))
    )
    logging.getLogger("httpx").setLevel(logging.INFO)

    assert bot_module.main() == 0

    [(application, config)] = started
    assert config.mode is BotMode.POLLING
    assert application.bot.token == TOKEN
    # httpx her isteği `.../bot<TOKEN>/...` adresiyle INFO'ya yazar; ana işlev bunu susturur.
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


def test_module_runs_as_a_script_and_exits_with_the_error_code(clean_process: None) -> None:
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(bot_module.__file__, run_name="__main__")

    assert excinfo.value.code == 1


def test_bot_runs_as_its_own_process() -> None:
    """`python -m app.telegram.bot` (Compose `bot` servisinin komutu) ayrı süreç olarak açılır ve
    token yoksa anlaşılır bir iletiyle sıfır olmayan kodla çıkar."""
    environment = {
        **os.environ,
        "DATABASE_URL": "sqlite://",
        "APP_ENV": "development",
        "TELEGRAM_BOT_TOKEN": "",
        "PYTHONIOENCODING": "utf-8",  # Windows konsol kod sayfası iletiyi başka kodlar
    }
    result = subprocess.run(
        [sys.executable, "-m", "app.telegram.bot"],
        cwd=Path(bot_module.__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )

    assert result.returncode == 1
    assert "TELEGRAM_BOT_TOKEN" in result.stderr
