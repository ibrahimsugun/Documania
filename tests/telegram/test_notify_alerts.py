"""13.6.1, 12.1.9 — izleme uyarıları Telegram'a gitmez (PLAN.md §D98 e; tm 161).

Uyarı eşiği aşılsa da bot mesaj göndermez: bildiriciye ölçüm verilmez, uyarı worker'ın ve panelin
logunda "Uyarı — …" olarak kalır (ölçümün kendisi `tests/worker/test_monitor.py`'dedir; 13.6.1'in
"uyarı üretilir" ölçütü orada sınanır). Bot gerçek `Application` ile kurulur, yalnız Telegram
aktarıcısı sahtedir (`tests.telegram.test_notify`in düzeni). Disk eşiği %101 verilir: gerçek disk
hiçbir testte uyarı çıkarmaz.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session, sessionmaker
from telegram.ext import ApplicationBuilder

from app.config import get_settings
from app.db.models import Upload, UploadStatus
from app.telegram import bot as bot_module
from app.telegram.bot import build_application
from app.telegram.notify import Notifier
from app.worker.monitor import AlertThresholds, AlertWatch
from app.worker.queue import enqueue_upload
from tests.telegram.conftest import LISTED_ID, TOKEN, FakeTelegram, polling_config
from tests.telegram.test_notify import (
    SECOND_UPLOAD_ID,
    UPLOAD_ID,
    add_uploads,
    failure_event,
    scan,
)

THRESHOLDS = AlertThresholds(
    error_count=2, job_queue_length=3, disk_used_percent=101.0, interval=timedelta(0)
)


@pytest.fixture
def listed(whitelist: Callable[..., None]) -> None:
    whitelist(LISTED_ID)


def waiting_jobs(session_factory: sessionmaker[Session], count: int) -> None:
    with session_factory() as session:
        for number in range(count):
            upload_id = f"w_{number}"
            session.add(Upload(id=upload_id, channel="web", status=UploadStatus.RECEIVED.value))
            session.flush()
            enqueue_upload(session, upload_id)
        session.commit()


def test_the_notifier_takes_no_alert_watch() -> None:
    assert "watch" not in inspect.signature(Notifier).parameters
    with pytest.raises(TypeError):
        Notifier(MagicMock(), watch=MagicMock())  # type: ignore[call-arg]


def test_alert_conditions_send_nothing_to_telegram_but_are_still_logged(
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    waiting_jobs(session_factory, 3)
    add_uploads(session_factory, UPLOAD_ID, SECOND_UPLOAD_ID)
    telegram = FakeTelegram()
    notifier = Notifier(session_factory)
    application = build_application(
        polling_config(),
        session_factory,
        builder=ApplicationBuilder().request(telegram).get_updates_request(telegram),
        notifier=notifier,
    )
    failure_event(session_factory, UPLOAD_ID)
    failure_event(session_factory, SECOND_UPLOAD_ID)

    assert scan(application, notifier) == 0
    assert telegram.sent("sendMessage") == []

    # Ölçüm worker'da (ve panelde) sürer: uyarı logda "Uyarı — …" olarak yazılır.
    with caplog.at_level(logging.WARNING, logger="app.worker.monitor"):
        notices = AlertWatch(session_factory, tmp_path, THRESHOLDS).check()
    assert notices
    assert "Uyarı — iş kuyruğu: 3 parti işlenmeyi bekliyor (eşik 3)." in caplog.text
    assert "Uyarı — hata: son 60 dakikada 2 parti işlenemedi (eşik 2)." in caplog.text


def test_the_bot_process_builds_its_notifier_without_alerts_and_with_the_default_language(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("PANEL_DEFAULT_LANGUAGE", "sr")
    monkeypatch.setenv("STARTUP_SCHEMA_CHECK", "false")  # bellek içi veritabanında göç yok
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "veri"))
    get_settings.cache_clear()
    built: list[dict[str, Any]] = []

    class SpyNotifier(Notifier):
        def __init__(self, session_factory: Any, **options: Any) -> None:
            built.append(options)
            super().__init__(session_factory, **options)

    monkeypatch.setattr(bot_module, "get_session_factory", lambda: MagicMock())
    monkeypatch.setattr(bot_module, "Notifier", SpyNotifier)
    monkeypatch.setattr(bot_module, "run", lambda *_args: None)
    try:
        assert bot_module.main() == 0
    finally:
        get_settings.cache_clear()

    assert built == [{"default_language": "sr"}]
