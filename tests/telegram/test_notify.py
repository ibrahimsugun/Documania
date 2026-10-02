"""12.4.1, 12.1.9 — kuyruğa yeni öğe düşünce tarama başına tek, sade bildirim gider; parti hatası
Telegram'a gitmez (PLAN.md §D98 e).

Bildirici `events`'i tarar (`QUEUED_*`); bu yüzden uçtan uca senaryolar gerçek
boru hattını (Telegram'dan belge → `process_upload`) çalıştırır, birim senaryoları olayı
doğrudan yazar (web sürecinin yazdığı olaydan farkı yoktur). Bot gerçek `Application` ile kurulur,
yalnız Telegram aktarıcısı (`FakeTelegram`) ve yapay zekâ sağlayıcısı (kayıtlı yanıtlar) sahtedir.
Belgeler `tests/fixtures/gen.py`'nin sentetik sayfalarıdır (CONVENTIONS §6).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from telegram import Update
from telegram.ext import Application, ApplicationBuilder
from telegram.request import RequestData

from app.catalog import import_catalog, load_seed_catalog
from app.db.models import Event, QueueItem, TelegramUser, Upload, UploadStatus, utcnow
from app.events import EventType, record_event
from app.i18n import use_language
from app.storage import prepare_data_dir
from app.telegram import notify
from app.telegram.bot import build_application, run
from app.telegram.handlers import DocumentIntake
from app.telegram.notify import LOOKBACK, Notifier, queue_message
from app.telegram.plain import problems
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    make_document_pdf_bytes,
    make_docx_bytes,
    passport_page,
    recorded_provider,
)
from tests.telegram.conftest import (
    LISTED_ID,
    OTHER_ID,
    FakeTelegram,
    bot_settings,
    document_update,
    polling_config,
)

UPLOAD_ID = "u_20260101_001"
SECOND_UPLOAD_ID = "u_20260101_002"
REASON = "Sayfa 1 okunamadı: kural R3 ihlal edildi."


def announcement(count: int) -> str:
    """`count` yeni öğenin Türkçe bildirimi (testler Türkçe varsayılanla koşar)."""
    return f"Kontrol etmeniz gereken {count} yeni belge var. Panelde bakabilirsiniz."


@dataclass
class NotifyBot:
    """Belge alma ve bildirici bağlı bot; ağ yok, veri dizini geçici."""

    application: Application
    telegram: FakeTelegram
    intake: DocumentIntake
    notifier: Notifier

    def feed(self, *updates: dict[str, Any]) -> None:
        async def _run() -> None:
            await self.application.initialize()
            try:
                for body in updates:
                    update = Update.de_json(body, self.application.bot)
                    await self.application.process_update(update)
                await self.intake.join()
            finally:
                await self.application.shutdown()

        asyncio.run(_run())


def scan(application: Application, notifier: Notifier) -> int:
    """Bir bildirim taraması (döngüsüz): kaç mesaj gönderilmeye çalışıldığını döner."""

    async def _scan() -> int:
        await application.initialize()
        try:
            return await notifier.notify_once(application.bot)
        finally:
            await application.shutdown()

    return asyncio.run(_scan())


@pytest.fixture
def make_notify_bot(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> Callable[..., NotifyBot]:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()

    def _make(provider: Any = None, telegram: FakeTelegram | None = None) -> NotifyBot:
        layout = prepare_data_dir(tmp_path / "data")
        settings = bot_settings(data_dir=layout.root)
        telegram = telegram or FakeTelegram()
        intake = DocumentIntake(
            session_factory, layout, settings, provider_factory=lambda _s: provider, group_wait=0.05
        )
        notifier = Notifier(session_factory, interval=0.02)
        application = build_application(
            polling_config(),
            session_factory,
            builder=ApplicationBuilder().request(telegram).get_updates_request(telegram),
            intake=intake,
            notifier=notifier,
        )
        return NotifyBot(application, telegram, intake, notifier)

    return _make


@pytest.fixture
def make_bare_bot(session_factory: sessionmaker[Session]) -> Callable[..., NotifyBot]:
    """Yalnız bildirici bağlı bot: olaylar testte doğrudan yazılır."""

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


def add_uploads(session_factory: sessionmaker[Session], *ids: str) -> None:
    with session_factory() as session:
        for upload_id in ids:
            session.add(Upload(id=upload_id, channel="web", status=UploadStatus.DONE.value))
        session.commit()


def queue_event(
    session_factory: sessionmaker[Session],
    upload_id: str = UPLOAD_ID,
    kind: EventType = EventType.QUEUED_UNRESOLVED,
    reason: str = REASON,
) -> None:
    with session_factory() as session:
        record_event(session, kind, upload_id=upload_id, message=reason)
        session.commit()


def failure_event(
    session_factory: sessionmaker[Session],
    upload_id: str = UPLOAD_ID,
    stage: str | None = "analyzing",
    message: str | None = None,
) -> None:
    with session_factory() as session:
        data = None if stage is None else {"stage": stage, "error": "builtins.RuntimeError"}
        record_event(
            session, EventType.PIPELINE_FAILED, upload_id=upload_id, message=message, data=data
        )
        session.commit()


@pytest.fixture
def uploads(session_factory: sessionmaker[Session]) -> None:
    add_uploads(session_factory, UPLOAD_ID, SECOND_UPLOAD_ID)


@pytest.fixture
def listed(whitelist: Callable[..., None]) -> None:
    whitelist(LISTED_ID)


def notifications(telegram: FakeTelegram, chat_id: int = LISTED_ID) -> list[str]:
    return [
        parameters["text"]
        for parameters in telegram.sent("sendMessage")
        if parameters["chat_id"] == chat_id
    ]


def passport() -> object:
    return passport_page(
        PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1)
    )


# --- 12.4.1 uçtan uca: gerçek boru hattı ---------------------------------------------------------


def test_a_new_queue_item_is_announced_to_every_listed_user(
    make_notify_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    whitelist: Callable[..., None],
    tmp_path: Path,
) -> None:
    whitelist(LISTED_ID)
    whitelist(OTHER_ID)
    bot = make_notify_bot(recorded_provider(tmp_path / "kayit", [passport()]))  # type: ignore[list-item]
    bot.telegram.files["w1"] = make_docx_bytes()  # Word eki analiz edilmez, kuyruğa düşer
    bot.feed(document_update(1, LISTED_ID, "w1", "ozgecmis.docx"))
    with session_factory() as session:
        (queued,) = session.scalars(select(QueueItem)).all()
        (upload_id, reason) = (queued.upload_id, " ".join(queued.reason.split()))

    sent = scan(bot.application, bot.notifier)

    assert sent == 1
    for chat_id in (LISTED_ID, OTHER_ID):
        text = notifications(bot.telegram, chat_id)[-1]
        assert text == announcement(1)
        # §D98 e: parti numarası, kuyruk türü ve gerekçe yazılmaz.
        assert upload_id not in text and reason[:20] not in text and "Sahibi" not in text
    # Bildirim yalnız özel sohbetlere, listedekilere gitti.
    chats = {parameters["chat_id"] for parameters in bot.telegram.sent("sendMessage")}
    assert chats == {LISTED_ID, OTHER_ID}


def test_a_failed_batch_is_not_announced(
    make_notify_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    whitelist: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Sağlayıcı yanıtları bitince analiz durur (09.2.3): parti `failed`, `PIPELINE_FAILED` var. Bu
    olay Telegram'a gitmez (§D98 e): gönderen kendi sade yanıtını aldı, panel partiyi gösterir."""
    whitelist(LISTED_ID)
    whitelist(OTHER_ID)
    bot = make_notify_bot(recorded_provider(tmp_path / "kayit", [passport()]))  # type: ignore[list-item]
    bot.telegram.files["f1"] = make_document_pdf_bytes([passport(), passport()])  # type: ignore[list-item]
    bot.feed(document_update(1, LISTED_ID, "f1", "pasaport.pdf"))
    with session_factory() as session:
        (upload,) = session.scalars(select(Upload)).all()
        assert upload.status == UploadStatus.FAILED.value
        assert session.scalars(
            select(Event).where(Event.type == EventType.PIPELINE_FAILED.value)
        ).one()

    assert scan(bot.application, bot.notifier) == 0
    assert notifications(bot.telegram, OTHER_ID) == []


def test_a_web_batch_that_reaches_the_queue_is_announced_too(
    make_bare_bot: Callable[..., NotifyBot], session_factory: sessionmaker[Session], listed: None
) -> None:
    """Olay hangi süreçte yazıldıysa yazıldı: web yüklemesinin kuyruk öğesi de bildirilir."""
    bot = make_bare_bot()
    add_uploads(session_factory, UPLOAD_ID)  # kanal `web`
    queue_event(session_factory)

    scan(bot.application, bot.notifier)

    assert notifications(bot.telegram) == [announcement(1)]


def test_a_queue_item_from_a_reanalysis_is_announced(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    uploads: None,
    listed: None,
) -> None:
    bot = make_bare_bot()
    for kind in (EventType.QUEUED_UNKNOWN, EventType.QUEUED_UNREADABLE):
        queue_event(session_factory, kind=kind)

    scan(bot.application, bot.notifier)

    assert notifications(bot.telegram) == [announcement(2)]


# --- kimlere, hangi olaylarda ---------------------------------------------------------------


def test_only_users_on_the_whitelist_are_told(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    whitelist: Callable[..., None],
    uploads: None,
) -> None:
    whitelist(LISTED_ID)
    whitelist(OTHER_ID, allowed=False)
    bot = make_bare_bot()
    queue_event(session_factory)

    scan(bot.application, bot.notifier)

    assert notifications(bot.telegram, LISTED_ID) != []
    assert notifications(bot.telegram, OTHER_ID) == []


def test_ids_of_a_deactivated_panel_user_are_not_told(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    whitelist: Callable[..., None],
    uploads: None,
) -> None:
    """12.1.3: izni açık ama bağlı panel kullanıcısı pasif olan kimlik bildirim almaz."""
    whitelist(LISTED_ID)
    whitelist(OTHER_ID)
    with session_factory() as session:
        session.get_one(TelegramUser, OTHER_ID).user.active = False
        session.commit()
    bot = make_bare_bot()
    queue_event(session_factory)

    scan(bot.application, bot.notifier)

    assert notifications(bot.telegram, LISTED_ID) != []
    assert notifications(bot.telegram, OTHER_ID) == []


def test_events_that_are_not_queue_events_are_ignored(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    uploads: None,
    listed: None,
) -> None:
    bot = make_bare_bot()
    with session_factory() as session:
        for kind in (
            EventType.PLAN_CREATED,
            EventType.OUTPUT_SAVED,
            EventType.MANUAL_ASSIGN,
            EventType.PAGE_ANALYSIS_FAILED,
            EventType.VALIDATION_FAILED,
            EventType.PIPELINE_FAILED,
        ):
            record_event(session, kind, upload_id=UPLOAD_ID)
        session.commit()

    assert scan(bot.application, bot.notifier) == 0
    assert bot.telegram.sent("sendMessage") == []


def test_events_that_predate_the_notifier_are_not_announced(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    uploads: None,
    listed: None,
) -> None:
    """Bot her açılışta geçmiş kuyruğu yağdırmaz."""
    queue_event(session_factory)
    failure_event(session_factory)
    bot = make_bare_bot()  # bildirici olaylardan sonra kuruldu
    queue_event(session_factory, SECOND_UPLOAD_ID)

    scan(bot.application, bot.notifier)

    assert notifications(bot.telegram) == [announcement(1)]  # yalnız sonraki olay sayıldı


def test_without_listed_users_nothing_is_sent_and_the_event_is_spent(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    whitelist: Callable[..., None],
    uploads: None,
) -> None:
    bot = make_bare_bot()
    queue_event(session_factory)
    assert scan(bot.application, bot.notifier) == 0
    whitelist(LISTED_ID)  # sonradan listeye giren, olduğu anda listede olmadığı olayı almaz

    scan(bot.application, bot.notifier)

    assert bot.telegram.sent("sendMessage") == []


def test_an_event_is_announced_only_once(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    uploads: None,
    listed: None,
) -> None:
    bot = make_bare_bot()
    queue_event(session_factory)
    failure_event(session_factory, SECOND_UPLOAD_ID)  # parti hatası gönderilmez

    assert scan(bot.application, bot.notifier) == 1
    assert scan(bot.application, bot.notifier) == 0

    assert notifications(bot.telegram) == [announcement(1)]
    queue_event(session_factory)  # sonradan gelen yenisi yine gider
    scan(bot.application, bot.notifier)
    assert notifications(bot.telegram) == [announcement(1)] * 2


def test_an_event_committed_late_with_a_smaller_number_is_not_skipped(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    uploads: None,
    listed: None,
) -> None:
    """Eşzamanlı iki partide küçük numaralı olay büyüğünden sonra commit edilebilir."""
    bot = make_bare_bot()
    with session_factory() as session:
        base = (session.scalar(select(Event.id).order_by(Event.id.desc())) or 0) + 10
        session.add(Event(id=base + 1, type=EventType.QUEUED_UNRESOLVED.value, upload_id=UPLOAD_ID))
        session.commit()
    scan(bot.application, bot.notifier)
    with session_factory() as session:
        session.add(
            Event(id=base, type=EventType.QUEUED_UNRESOLVED.value, upload_id=SECOND_UPLOAD_ID)
        )
        session.commit()

    scan(bot.application, bot.notifier)

    assert notifications(bot.telegram) == [announcement(1), announcement(1)]


def test_an_event_older_than_the_lookback_is_not_announced(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    uploads: None,
    listed: None,
) -> None:
    bot = make_bare_bot()
    with session_factory() as session:
        session.add(
            Event(
                type=EventType.QUEUED_UNRESOLVED.value,
                upload_id=UPLOAD_ID,
                ts=utcnow() - LOOKBACK - timedelta(minutes=1),
            )
        )
        session.commit()

    assert scan(bot.application, bot.notifier) == 0


def test_the_memory_of_announced_events_does_not_grow_without_bound(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    uploads: None,
    listed: None,
) -> None:
    """Bot aylarca çalışır: bildirilmiş olay numaraları tarama penceresini geçince unutulur."""
    bot = make_bare_bot(lookback=timedelta(seconds=0.2))
    queue_event(session_factory)
    scan(bot.application, bot.notifier)
    assert len(bot.notifier._notified) == 1

    time.sleep(0.3)
    scan(bot.application, bot.notifier)

    assert bot.notifier._notified == {}
    assert len(notifications(bot.telegram)) == 1  # unutulan olay pencerenin dışında: yeniden gitmez


# --- mesaj biçimi ---------------------------------------------------------------------------------


def test_queue_events_of_several_batches_form_one_message_with_their_count(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    uploads: None,
    listed: None,
) -> None:
    bot = make_bare_bot()
    queue_event(session_factory, UPLOAD_ID, EventType.QUEUED_UNKNOWN, "Birinci gerekçe.")
    queue_event(session_factory, SECOND_UPLOAD_ID, reason="İkinci partinin gerekçesi.")
    queue_event(session_factory, UPLOAD_ID, EventType.QUEUED_UNREADABLE, "İkinci gerekçe.")

    assert scan(bot.application, bot.notifier) == 1

    assert notifications(bot.telegram) == [announcement(3)]


def test_a_long_queue_is_still_one_short_message(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    uploads: None,
    listed: None,
) -> None:
    bot = make_bare_bot()
    for _ in range(12):
        queue_event(session_factory, reason="Çok uzun bir gerekçe. " * 30)

    scan(bot.application, bot.notifier)

    assert notifications(bot.telegram) == [announcement(12)]


def test_a_failure_with_an_error_text_never_reaches_telegram(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    uploads: None,
    listed: None,
) -> None:
    bot = make_bare_bot()
    failure_event(session_factory, message="Ornekova 00 0000001 okunamadı")

    assert scan(bot.application, bot.notifier) == 0
    assert bot.telegram.sent("sendMessage") == []


@pytest.mark.parametrize("language", ["tr", "en", "sr"])
@pytest.mark.parametrize("count", [1, 2, 5, 21])
def test_the_announcement_is_plain_in_every_language(language: str, count: int) -> None:
    with use_language(language):
        text = queue_message(count)

    assert str(count) in text
    assert problems(text, language) == []


def test_each_recipient_is_told_in_their_own_language(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    whitelist: Callable[..., None],
    uploads: None,
) -> None:
    whitelist(LISTED_ID)
    whitelist(OTHER_ID)
    with session_factory() as session:
        session.get_one(TelegramUser, OTHER_ID).user.language = "sr"
        session.commit()
    bot = make_bare_bot(default_language="en")
    queue_event(session_factory)
    queue_event(session_factory, SECOND_UPLOAD_ID)

    scan(bot.application, bot.notifier)

    assert notifications(bot.telegram, LISTED_ID) == [
        "There are 2 new documents for you to check. You can look at them in the panel."
    ]
    assert notifications(bot.telegram, OTHER_ID) == [
        "Imate 2 nova dokumenta za proveru. Možete ih pogledati na panelu."
    ]


# --- gönderim hataları ---------------------------------------------------------------------------


_FORBIDDEN = json.dumps(
    {"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"}
).encode()


class RefusingTelegram(FakeTelegram):
    """`refused` sohbetlerine mesaj göndermeyi reddeder (bota hiç yazmamış kullanıcı gibi)."""

    def __init__(self, *refused: int) -> None:
        super().__init__()
        self.refused = set(refused)

    async def do_request(
        self, url: str, method: str, request_data: RequestData | None = None, **_timeouts: Any
    ) -> tuple[int, bytes]:
        parameters = dict(request_data.parameters) if request_data else {}
        if url.endswith("/sendMessage") and parameters.get("chat_id") in self.refused:
            self.calls.append(("sendMessage", parameters))
            return (
                403,
                b'{"ok": false, "error_code": 403, "description": "Forbidden: bot was blocked"}',
            )
        return await super().do_request(url, method, request_data)


def test_a_user_who_cannot_be_reached_does_not_stop_the_others_and_is_not_retried(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    whitelist: Callable[..., None],
    uploads: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    whitelist(LISTED_ID)
    whitelist(OTHER_ID)
    bot = make_bare_bot(RefusingTelegram(LISTED_ID))
    queue_event(session_factory)

    with caplog.at_level(logging.ERROR, logger=notify.__name__):
        scan(bot.application, bot.notifier)
        scan(bot.application, bot.notifier)

    assert len(notifications(bot.telegram, OTHER_ID)) == 1  # öteki alıcıya gitti
    assert len(notifications(bot.telegram, LISTED_ID)) == 1  # tek deneme, yeniden yok
    messages = [record.getMessage() for record in caplog.records]
    assert messages == ["Telegram bildirimi gönderilemedi (Forbidden)"]
    assert str(LISTED_ID) not in caplog.text  # alıcı kimliği loga yazılmaz


# --- döngü ve bota bağlanma -----------------------------------------------------------------------


def wait_until(condition: Callable[[], bool], *, seconds: float = 5.0) -> Awaitable[None]:
    async def _wait() -> None:
        deadline = asyncio.get_running_loop().time() + seconds
        while not condition():
            assert asyncio.get_running_loop().time() < deadline, "koşul zamanında sağlanmadı"
            await asyncio.sleep(0.01)

    return _wait()


def test_the_loop_starts_with_the_bot_announces_new_events_and_stops_with_it(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    uploads: None,
    listed: None,
) -> None:
    bot = make_bare_bot(interval=0.02)
    application = bot.application

    async def _run() -> None:
        await application.initialize()
        try:
            await application.post_init(application)  # type: ignore[misc]
            await application.post_init(application)  # ikinci başlatma ikinci döngü açmaz
            queue_event(session_factory)
            await wait_until(lambda: len(notifications(bot.telegram)) == 1)
            failure_event(session_factory)  # gönderilmez
            queue_event(session_factory)
            await wait_until(lambda: len(notifications(bot.telegram)) == 2)
            await application.post_shutdown(application)  # type: ignore[misc]
            queue_event(session_factory, SECOND_UPLOAD_ID)
            await asyncio.sleep(0.1)  # durduktan sonra tarama yok
        finally:
            await application.shutdown()

    asyncio.run(_run())

    assert notifications(bot.telegram) == [announcement(1), announcement(1)]


def test_a_failing_scan_is_logged_and_the_loop_carries_on(
    make_bare_bot: Callable[..., NotifyBot],
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    uploads: None,
    listed: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    bot = make_bare_bot(interval=0.02)
    original = bot.notifier._collect
    calls: list[int] = []

    def flaky() -> Any:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("veritabanı ORNEK-KIMLIK okunamadı")
        return original()

    monkeypatch.setattr(bot.notifier, "_collect", flaky)
    queue_event(session_factory)
    application = bot.application

    async def _run() -> None:
        await application.initialize()
        try:
            await application.post_init(application)  # type: ignore[misc]
            await wait_until(lambda: len(notifications(bot.telegram)) == 1)
            await application.post_shutdown(application)  # type: ignore[misc]
        finally:
            await application.shutdown()

    with caplog.at_level(logging.ERROR, logger=notify.__name__):
        asyncio.run(_run())

    assert "Bildirim taraması başarısız (RuntimeError)" in caplog.text
    assert "ORNEK-KIMLIK" not in caplog.text  # hata metni loga yazılmaz


def test_registering_keeps_the_hooks_the_builder_already_had(
    session_factory: sessionmaker[Session],
) -> None:
    order: list[str] = []

    async def before_start(_application: Application) -> None:
        order.append("init")

    async def after_stop(_application: Application) -> None:
        order.append("shutdown")

    telegram = FakeTelegram()
    notifier = Notifier(session_factory, interval=0.02)
    application = build_application(
        polling_config(),
        session_factory,
        builder=ApplicationBuilder()
        .request(telegram)
        .get_updates_request(telegram)
        .post_init(before_start)
        .post_shutdown(after_stop),
        notifier=notifier,
    )

    async def _run() -> None:
        await application.initialize()
        try:
            await application.post_init(application)  # type: ignore[misc]
            await application.post_shutdown(application)  # type: ignore[misc]
        finally:
            await application.shutdown()

    asyncio.run(_run())

    assert order == ["init", "shutdown"]


def test_without_a_notifier_the_bot_has_no_start_or_stop_hooks(
    session_factory: sessionmaker[Session],
) -> None:
    telegram = FakeTelegram()
    application = build_application(
        polling_config(),
        session_factory,
        builder=ApplicationBuilder().request(telegram).get_updates_request(telegram),
    )

    assert application.post_init is None and application.post_shutdown is None


class NotifyingTelegram(FakeTelegram):
    """`getUpdates` boş döner; bildirim gidince çalışan botu durdurur."""

    application: Application | None = None

    async def do_request(
        self, url: str, method: str, request_data: RequestData | None = None, **_timeouts: Any
    ) -> tuple[int, bytes]:
        name = url.rsplit("/", 1)[-1]
        if name == "getUpdates":
            await asyncio.sleep(0.05)
            return 200, b'{"ok": true, "result": []}'
        outcome = await super().do_request(url, method, request_data)
        if name == "sendMessage" and self.application is not None:
            self.application.stop_running()
        return outcome


# python-telegram-bot `run_polling` olay döngüsünü kendisi kurar; bu uyarı kütüphanenindir.
@pytest.mark.filterwarnings("ignore:There is no current event loop:DeprecationWarning")
def test_run_polling_starts_the_notifier_and_stops_it_on_shutdown(
    session_factory: sessionmaker[Session], uploads: None, listed: None
) -> None:
    telegram = NotifyingTelegram()
    notifier = Notifier(session_factory, interval=0.02)
    application = build_application(
        polling_config(),
        session_factory,
        builder=ApplicationBuilder().request(telegram).get_updates_request(telegram),
        notifier=notifier,
    )
    telegram.application = application
    queue_event(session_factory)

    try:
        run(application, polling_config())
    finally:
        # `run_polling` işi bitince döngüyü kapatır ama geçerli döngü olarak bırakır; sonraki
        # `run_polling` (test_polling_serving) kapalı döngüyü bulmasın diye temizlenir.
        asyncio.set_event_loop(None)

    (text,) = notifications(telegram)
    assert text == announcement(1)
    assert notifier._task is None  # kapanışta döngü durduruldu
