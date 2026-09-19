"""Kuyruk ve hata bildirimleri (PRD 12.4.1; K13).

Kuyruğa yeni öğe düşünce ve parti işlenemeyip `failed` olunca beyaz listedeki her kullanıcıya
özel sohbetten kısa bir mesaj gider. Bot paneli çalıştıran süreçten ayrı bir süreçtir; iki süreç
arasındaki köprü `events` tablosudur (K15): kuyruğa alma `QUEUED_UNKNOWN`/`QUEUED_UNREADABLE`/
`QUEUED_UNRESOLVED` (`app.pipeline.route.route_queue_item`), parti hatası `PIPELINE_FAILED`
(`app.pipeline.orchestrate`) olayını yazar — ister web yüklemesi ister bot işlemiş olsun. Bildirici
bu olayları `POLL_INTERVAL_SECONDS`'te bir okur; boru hattı bota hiçbir şey bilmez.

**Ne zamandan itibaren.** Bildirici kurulduğu andaki son olaydan sonrakileri bildirir; geçmiş
olaylar (bot açılmadan önce düşen kuyruk öğeleri) gönderilmez, yoksa her başlangıçta kuyruğun
tamamı yağardı. Bot kapalıyken düşen öğe için bildirim yoktur; panel kuyruğun kaynağıdır.

**Geç görünen olay.** Bir partinin olayları planın uygulama adımı bitince toplu commit edilir;
eşzamanlı iki partide küçük numaralı olay büyüğünden sonra görünür olabilir. Bu yüzden "son görülen
numaradan sonrası" yerine son `LOOKBACK`'teki bütün olaylar taranır ve gönderilenler numarasıyla
hatırlanır — geç commit edilen olay da atlanmaz, hiçbiri iki kez gitmez.

**En çok bir kez.** Olay, gönderim denenirken gönderilmiş sayılır: gönderilemeyen (bota hiç
`/start` demeyen, botu engelleyen kullanıcı ya da Telegram kesintisi) mesaj yeniden denenmez; hata
yalnız türüyle loga yazılır ve öteki alıcılara gönderim sürer. Bildirim bir kolaylıktır, kuyruğun
ve partinin durumu panelde durur.

**Gizlilik (CONVENTIONS §6).** Mesaj 12.2.3 özetiyle aynı bilgiyi taşır: parti numarası, kuyruk
türü ve gerekçe (kişisel değer taşımaz) ya da hatanın aşaması. Ad-soyad, belge numarası, hata
metni ve iz gitmez; loga kimlik ve içerik yazılmaz.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from telegram import Bot
from telegram.error import TelegramError
from telegram.ext import Application

from app.db.models import Event, QueueKind, TelegramUser, UploadStatus, utcnow
from app.events import EventType
from app.telegram.handlers import QUEUE_LABELS

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 15.0
# Olay yazıldığı andan commit'lendiği ana kadar bu süre içinde görünür olmak zorundadır.
LOOKBACK = timedelta(minutes=10)

_MAX_LISTED = 10  # bir mesajda tek tek sayılan kuyruk öğesi
_MAX_REASON_LENGTH = 160  # 10 öğe × 160 karakter, Telegram'ın 4096 karakterlik sınırının çok altı

QUEUE_EVENT_KINDS: dict[str, QueueKind] = {
    EventType.QUEUED_UNKNOWN.value: QueueKind.UNKNOWN,
    EventType.QUEUED_UNREADABLE.value: QueueKind.UNREADABLE,
    EventType.QUEUED_UNRESOLVED.value: QueueKind.UNRESOLVED,
}
# `PIPELINE_FAILED.data.stage`: hatanın çıktığı durum (`UploadStatus`).
STAGE_LABELS: dict[str, str] = {
    UploadStatus.RECEIVED.value: "başlangıç",
    UploadStatus.RENDERING.value: "sayfaların hazırlanması",
    UploadStatus.ANALYZING.value: "analiz",
    UploadStatus.PLANNING.value: "plan hazırlama",
    UploadStatus.EXECUTING.value: "plan uygulama",
}

QUEUE_TEXT = "Kuyruğa yeni öğe düştü — parti {upload_id}: {count} öğe."
QUEUE_FOOTER = "Panelde kuyruğa bakın."
FAILED_TEXT = (
    "Parti {upload_id} işlenemedi (aşama: {stage}). Dosyalar saklandı; ayrıntı için panelde "
    "partiye bakın."
)
UNKNOWN_STAGE = "bilinmiyor"

_NOTIFIED_TYPES = (*QUEUE_EVENT_KINDS, EventType.PIPELINE_FAILED.value)


@dataclass(frozen=True, slots=True)
class PendingEvent:
    """Bildirilecek bir olay: mesajı kurmaya yeten alanlar (oturum kapanınca da kullanılır)."""

    id: int
    ts: datetime
    type: str
    upload_id: str | None
    message: str | None
    stage: str | None


@dataclass(slots=True)
class QueueBatch:
    """Aynı partinin, aynı taramada görülen kuyruk olayları: tek mesaj olur."""

    upload_id: str | None
    items: list[tuple[QueueKind, str]] = field(default_factory=list)


def _shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _upload_label(upload_id: str | None) -> str:
    return upload_id or "?"


def build_queue_message(batch: QueueBatch) -> str:
    """Bir partinin yeni kuyruk öğelerini tek mesajda toplar: kuyruk türü ve gerekçe."""
    lines = [QUEUE_TEXT.format(upload_id=_upload_label(batch.upload_id), count=len(batch.items))]
    lines.extend(
        f"• {QUEUE_LABELS[kind]}: {_shorten(reason, _MAX_REASON_LENGTH)}"
        for kind, reason in batch.items[:_MAX_LISTED]
    )
    if len(batch.items) > _MAX_LISTED:
        lines.append(f"… ve {len(batch.items) - _MAX_LISTED} öğe daha.")
    lines.append(QUEUE_FOOTER)
    return "\n".join(lines)


def build_failure_message(event: PendingEvent) -> str:
    stage = STAGE_LABELS.get(event.stage or "", UNKNOWN_STAGE)
    return FAILED_TEXT.format(upload_id=_upload_label(event.upload_id), stage=stage)


def build_messages(events: list[PendingEvent]) -> list[str]:
    """Olayları (numara sırasıyla) mesajlara çevirir: partinin kuyruk olayları tek mesaj, her
    parti hatası ayrı mesajdır. Mesajlar, içerdikleri ilk olayın sırasını korur."""
    slots: list[str | QueueBatch] = []
    batches: dict[str | None, QueueBatch] = {}
    for event in events:
        if event.type == EventType.PIPELINE_FAILED.value:
            slots.append(build_failure_message(event))
            continue
        batch = batches.get(event.upload_id)
        if batch is None:
            batch = batches[event.upload_id] = QueueBatch(event.upload_id)
            slots.append(batch)
        batch.items.append((QUEUE_EVENT_KINDS[event.type], event.message or ""))
    return [slot if isinstance(slot, str) else build_queue_message(slot) for slot in slots]


class Notifier:
    """`events`'i tarar ve yeni kuyruk/parti hatası olaylarını beyaz listedeki kullanıcılara yollar.

    Kurulduğu andaki son olay numarası başlangıçtır (modül açıklaması): `Notifier` bot süreci
    başlarken kurulur ve veritabanı o an okunabilir olmalıdır. `register` botun başlama/durma
    kancalarına bağlar; testler `notify_once`'ı doğrudan çağırır."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        interval: float = POLL_INTERVAL_SECONDS,
        lookback: timedelta = LOOKBACK,
    ) -> None:
        self._session_factory = session_factory
        self._interval = interval
        self._lookback = lookback
        self._baseline = self._latest_event_id()
        # Gönderilmiş sayılan olay numarası → zamanı; `lookback`'i geçen kayıt taranmadığı için
        # unutulur.
        self._notified: dict[int, datetime] = {}
        self._task: asyncio.Task[None] | None = None

    def register(self, application: Application) -> None:
        """Botun başlamasında bildirim döngüsünü açar, durmasında kapatır. Uygulamada zaten bir
        `post_init`/`post_shutdown` varsa (oluşturucudan gelen) ondan sonra çalışırlar."""
        previous_init, previous_shutdown = application.post_init, application.post_shutdown

        async def _start(app: Application) -> None:
            if previous_init is not None:
                await previous_init(app)
            self.start(app.bot)

        async def _stop(app: Application) -> None:
            await self.stop()
            if previous_shutdown is not None:
                await previous_shutdown(app)

        application.post_init = _start
        application.post_shutdown = _stop

    def start(self, bot: Bot) -> None:
        """Döngüyü arka planda başlatır (olay döngüsü içinden); ikinci çağrı yok sayılır."""
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._run(bot))

    async def stop(self) -> None:
        """Döngüyü durdurur ve bitmesini bekler."""
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _run(self, bot: Bot) -> None:
        while True:
            try:
                await self.notify_once(bot)
            except Exception as exc:
                # Hata metni kimlik taşıyabilir (SQL parametresi); yalnız türü yazılır. Döngü
                # sürer: geçici bir veritabanı hatası bildirimleri kalıcı olarak durdurmasın.
                logger.error("Bildirim taraması başarısız (%s)", type(exc).__name__)
            await asyncio.sleep(self._interval)

    async def notify_once(self, bot: Bot) -> int:
        """Bir tarama: yeni olayları bulur, mesajlara çevirir, alıcılara yollar. Gönderilmeye
        çalışılan mesaj sayısını (alıcı başına değil) döner."""
        events, recipients = await asyncio.to_thread(self._collect)
        messages = build_messages(events)
        for chat_id in recipients:
            for text in messages:
                await self._send(bot, chat_id, text)
        return len(messages) if recipients else 0

    def _collect(self) -> tuple[list[PendingEvent], list[int]]:
        """Yeni bildirimlik olayları ve alıcıları okur; olayları gönderilmiş sayar (en çok bir kez).

        Alıcı yoksa olaylar yine tüketilir: bildirim, olay olduğu andaki listedekileredir."""
        cutoff = utcnow() - self._lookback
        self._notified = {id_: ts for id_, ts in self._notified.items() if ts >= cutoff}
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    Event.id, Event.ts, Event.type, Event.upload_id, Event.message, Event.data_json
                )
                .where(
                    Event.id > self._baseline,
                    Event.ts >= cutoff,
                    Event.type.in_(_NOTIFIED_TYPES),
                )
                .order_by(Event.id)
            ).all()
            events = [
                PendingEvent(
                    id=row.id,
                    ts=row.ts,
                    type=row.type,
                    upload_id=row.upload_id,
                    message=row.message,
                    stage=(row.data_json or {}).get("stage"),
                )
                for row in rows
                if row.id not in self._notified
            ]
            if not events:
                return [], []
            self._notified.update({event.id: event.ts for event in events})
            recipients = list(
                session.scalars(
                    select(TelegramUser.telegram_id)
                    .where(TelegramUser.allowed.is_(True))
                    .order_by(TelegramUser.telegram_id)
                )
            )
        return events, recipients

    def _latest_event_id(self) -> int:
        with self._session_factory() as session:
            return session.scalar(select(func.max(Event.id))) or 0

    @staticmethod
    async def _send(bot: Bot, chat_id: int, text: str) -> None:
        try:
            # Özel sohbetin numarası kullanıcı numarasıdır (beyaz liste özel sohbetle sınırlı).
            await bot.send_message(chat_id=chat_id, text=text)
        except TelegramError as exc:
            # Kullanıcı bota hiç yazmamış ya da botu engellemiş olabilir; kimlik loga yazılmaz.
            logger.error("Telegram bildirimi gönderilemedi (%s)", type(exc).__name__)
