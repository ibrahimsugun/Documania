"""13.6.1 — izleme uyarıları bota bağlı bildiriciden beyaz listedeki kullanıcılara gider.

Ölçümün kendisi `tests/worker/test_monitor.py`'dedir; burada bildiricinin uyarıyı alıcılara
taşıması sınanır: kime, ne zaman, kaç kez. Bot gerçek `Application` ile kurulur, yalnız Telegram
aktarıcısı sahtedir (`tests.telegram.test_notify`in düzeni). Disk eşiği %101 verilir: gerçek disk
hiçbir testte uyarı çıkarmaz.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from telegram.ext import ApplicationBuilder

from app.config import get_settings
from app.db.models import JobStatus, Upload, UploadJob, UploadStatus, utcnow
from app.telegram import bot as bot_module
from app.telegram.bot import build_application
from app.telegram.notify import Notifier
from app.worker.monitor import AlertKind, AlertThresholds, AlertWatch
from app.worker.queue import enqueue_upload
from tests.telegram.conftest import LISTED_ID, OTHER_ID, TOKEN, FakeTelegram, polling_config
from tests.telegram.test_notify import (
    SECOND_UPLOAD_ID,
    UPLOAD_ID,
    NotifyBot,
    add_uploads,
    failure_event,
    notifications,
    scan,
)

THRESHOLDS = AlertThresholds(
    error_count=2, job_queue_length=3, disk_used_percent=101.0, interval=timedelta(0)
)
JOB_ALERT = (
    "Uyarı — iş kuyruğu: 3 parti işlenmeyi bekliyor (eşik 3). "
    "İşleyicinin ve yapay zekâ sağlayıcısının çalıştığını kontrol edin."
)


@pytest.fixture
def listed(whitelist: Callable[..., None]) -> None:
    whitelist(LISTED_ID)


@pytest.fixture
def make_alert_bot(session_factory: sessionmaker[Session]) -> Callable[..., NotifyBot]:
    """Yalnız bildirici bağlı bot: olaylar ve işler testte doğrudan yazılır."""

    def _make(telegram: FakeTelegram | None = None, **notifier_options: Any) -> NotifyBot:
        telegram = telegram or FakeTelegram()
        notifier = Notifier(session_factory, **notifier_options)
        application = build_application(
            polling_config(),
            session_factory,
            builder=ApplicationBuilder().request(telegram).get_updates_request(telegram),
            notifier=notifier,
        )
        return NotifyBot(application, telegram, None, notifier)  # type: ignore[arg-type]

    return _make


def alert_watch(
    session_factory: sessionmaker[Session], tmp_path: Path, **overrides: Any
) -> AlertWatch:
    return AlertWatch(session_factory, tmp_path, replace(THRESHOLDS, **overrides))


def waiting_jobs(session_factory: sessionmaker[Session], count: int) -> None:
    with session_factory() as session:
        for number in range(count):
            upload_id = f"w_{number}"
            session.add(Upload(id=upload_id, channel="web", status=UploadStatus.RECEIVED.value))
            session.flush()
            enqueue_upload(session, upload_id)
        session.commit()


def finish_jobs(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        for job in session.scalars(select(UploadJob)):
            job.status = JobStatus.FINISHED.value
        session.commit()


def test_an_alert_reaches_every_listed_user_with_the_measured_values(
    make_alert_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    whitelist: Callable[..., None],
    tmp_path: Path,
) -> None:
    whitelist(LISTED_ID)
    whitelist(OTHER_ID)
    waiting_jobs(session_factory, 3)
    bot = make_alert_bot(watch=alert_watch(session_factory, tmp_path))

    sent = scan(bot.application, bot.notifier)

    assert sent == 1
    for chat_id in (LISTED_ID, OTHER_ID):
        assert notifications(bot.telegram, chat_id) == [JOB_ALERT]


def test_a_failure_streak_alerts_after_the_single_failure_messages(
    make_alert_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    add_uploads(session_factory, UPLOAD_ID, SECOND_UPLOAD_ID)
    bot = make_alert_bot(watch=alert_watch(session_factory, tmp_path))
    failure_event(session_factory, UPLOAD_ID)
    failure_event(session_factory, SECOND_UPLOAD_ID)

    sent = scan(bot.application, bot.notifier)

    first, second, alert = notifications(bot.telegram)
    assert sent == 3
    assert first.startswith(f"Parti {UPLOAD_ID} işlenemedi")
    assert second.startswith(f"Parti {SECOND_UPLOAD_ID} işlenemedi")
    assert alert == (
        "Uyarı — hata: son 60 dakikada 2 parti işlenemedi (eşik 2). "
        "Panelde başarısız partilere bakın."
    )


def test_an_alert_is_sent_once_then_cleared_when_the_value_drops(
    make_alert_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    waiting_jobs(session_factory, 3)
    watch = alert_watch(session_factory, tmp_path)
    bot = make_alert_bot(watch=watch)

    assert scan(bot.application, bot.notifier) == 1
    assert scan(bot.application, bot.notifier) == 0  # süren uyarı yeniden yağmaz
    finish_jobs(session_factory)
    assert scan(bot.application, bot.notifier) == 1

    raised, cleared = notifications(bot.telegram)
    assert raised == JOB_ALERT
    assert cleared == "Uyarı giderildi — iş kuyruğu: 0 parti işlenmeyi bekliyor (eşik 3)."
    assert watch.active == frozenset()


def test_a_lasting_alert_is_reminded_after_the_repeat_interval(
    make_alert_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waiting_jobs(session_factory, 3)
    watch = alert_watch(session_factory, tmp_path, repeat=timedelta(hours=1))
    bot = make_alert_bot(watch=watch)
    clock = [utcnow()]
    real_check = watch.check

    def check_at_clock(now: datetime | None = None) -> Any:
        return real_check(clock[0])

    monkeypatch.setattr(watch, "check", check_at_clock)

    assert scan(bot.application, bot.notifier) == 1
    clock[0] += timedelta(minutes=59)
    assert scan(bot.application, bot.notifier) == 0
    clock[0] += timedelta(minutes=1)
    assert scan(bot.application, bot.notifier) == 1

    raised, reminder = notifications(bot.telegram)
    assert raised == JOB_ALERT
    assert reminder == JOB_ALERT.replace("Uyarı —", "Uyarı sürüyor —")


def test_nothing_is_measured_while_nobody_is_listed_and_the_alert_comes_with_the_first_user(
    make_alert_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    whitelist: Callable[..., None],
    tmp_path: Path,
) -> None:
    waiting_jobs(session_factory, 3)
    watch = alert_watch(session_factory, tmp_path)
    bot = make_alert_bot(watch=watch)

    assert scan(bot.application, bot.notifier) == 0
    assert watch.active == frozenset()  # ölçülmedi: uyarı tüketilmedi
    whitelist(LISTED_ID)
    assert scan(bot.application, bot.notifier) == 1
    assert watch.active == {AlertKind.JOB_QUEUE}
    assert notifications(bot.telegram) == [JOB_ALERT]


def test_a_bot_without_a_watch_sends_no_alerts(
    make_alert_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    listed: None,
) -> None:
    waiting_jobs(session_factory, 50)
    bot = make_alert_bot()

    assert scan(bot.application, bot.notifier) == 0
    assert notifications(bot.telegram) == []


def test_an_alert_that_cannot_be_delivered_is_not_retried(
    make_alert_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    waiting_jobs(session_factory, 3)
    telegram = FakeTelegram()
    bot = make_alert_bot(telegram, watch=alert_watch(session_factory, tmp_path))
    telegram.fail_send = True
    scan(bot.application, bot.notifier)
    telegram.fail_send = False

    scan(bot.application, bot.notifier)

    # Aktarıcı başarısız denemeyi de kaydeder: tek deneme var, uyarı ikinci taramada yinelenmedi.
    assert notifications(telegram) == [JOB_ALERT]
    assert AlertKind.JOB_QUEUE in bot.notifier._watch.active  # type: ignore[union-attr]


def test_the_bot_process_builds_its_notifier_with_the_configured_alert_thresholds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("ALERT_JOB_QUEUE_LENGTH", "7")
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

    (options,) = built
    watch = options["watch"]
    assert isinstance(watch, AlertWatch)
    assert watch._thresholds.job_queue_length == 7
    assert watch._data_dir == tmp_path / "veri"  # disk, uyarının bakacağı veri dizinidir
