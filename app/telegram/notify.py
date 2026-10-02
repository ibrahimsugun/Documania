"""Kuyruk bildirimi (PRD 12.4.1, 12.1.9; K13; PLAN.md §D98 e).

Kuyruğa yeni öğe düşünce beyaz listedeki her kullanıcıya özel sohbetten tek, sade bir mesaj gider:
"Kontrol etmeniz gereken N yeni belge var. Panelde bakabilirsiniz." Bot paneli çalıştıran süreçten
ayrı bir süreçtir; iki süreç arasındaki köprü `events` tablosudur (K15): kuyruğa alma
`QUEUED_UNKNOWN`/`QUEUED_UNREADABLE`/`QUEUED_UNRESOLVED` (`app.pipeline.route.route_queue_item`)
olayını yazar — ister web yüklemesi ister bot işlemiş olsun. Bildirici bu olayları
`POLL_INTERVAL_SECONDS`'te bir okur; boru hattı bota hiçbir şey bilmez.

**Sade dil (12.1.9, §D98).** Tarama başına tek mesaj: kaç partiden gelirse gelsin yeni öğelerin
sayısı; parti numarası, kuyruk türü ve gerekçe yazılmaz. Parti hatası (`PIPELINE_FAILED`) Telegram'a
**gitmez**: gönderen kişi kendi sade yanıtını alır, panel partiyi gösterir. İzleme uyarıları
(13.6.1) da gitmez: ölçüm worker'da ve panelde yapılır, uyarı logda "Uyarı — …" olarak kalır
(`app.worker.monitor`). Mesaj alıcının arayüz dilindedir (12.1.6; tercih boşsa `default_language`).

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
durumu panelde durur.

**Gizlilik (CONVENTIONS §6).** Mesaj yalnız bir sayı taşır. Loga kimlik ve içerik yazılmaz.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from telegram import Bot
from telegram.error import TelegramError
from telegram.ext import Application

from app.db.models import Event, TelegramUser, User, utcnow
from app.events import EventType
from app.i18n import DEFAULT_LANGUAGE, is_supported, ngettext, use_language
from app.telegram.whitelist import permitted_ids

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 15.0
# Olay yazıldığı andan commit'lendiği ana kadar bu süre içinde görünür olmak zorundadır.
LOOKBACK = timedelta(minutes=10)
# Dil verilmezse tercihi olmayan alıcının dili; `bot.main` ayardaki `PANEL_DEFAULT_LANGUAGE`'ı
# verir, bot testleri bunu `tr` yapar (`tests/telegram/conftest.py`).
FALLBACK_LANGUAGE = DEFAULT_LANGUAGE

QUEUE_EVENT_TYPES = frozenset(
    {
        EventType.QUEUED_UNKNOWN.value,
        EventType.QUEUED_UNREADABLE.value,
        EventType.QUEUED_UNRESOLVED.value,
    }
)


@dataclass(frozen=True, slots=True)
class PendingEvent:
    """Bildirilecek bir kuyruk olayı (oturum kapanınca da kullanılır)."""

    id: int
    ts: datetime


@dataclass(frozen=True, slots=True)
class Recipient:
    """Bildirim alıcısı: izinli Telegram kimliği ve bağlı kullanıcının dili."""

    telegram_id: int
    language: str | None


def queue_message(count: int) -> str:
    """Bir taramada kuyruğa düşen `count` öğenin sade bildirimi (bu bağlamın dilinde)."""
    return ngettext(
        "Kontrol etmeniz gereken {count} yeni belge var. Panelde bakabilirsiniz.",
        "Kontrol etmeniz gereken {count} yeni belge var. Panelde bakabilirsiniz.",
        count,
    ).format(count=count)


class Notifier:
    """`events`'i tarar ve yeni kuyruk olaylarını tarama başına tek mesajla beyaz listedeki
    kullanıcılara, her birinin dilinde yollar.

    Kurulduğu andaki son olay numarası başlangıçtır (modül açıklaması): `Notifier` bot süreci
    başlarken kurulur ve veritabanı o an okunabilir olmalıdır. `register` botun başlama/durma
    kancalarına bağlar; testler `notify_once`'ı doğrudan çağırır."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        interval: float = POLL_INTERVAL_SECONDS,
        lookback: timedelta = LOOKBACK,
        default_language: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._interval = interval
        self._lookback = lookback
        self._default_language = default_language
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
        """Bir tarama: yeni kuyruk olaylarını sayar, her alıcıya kendi dilinde tek mesaj yollar.
        Gönderilmeye çalışılan mesaj sayısını (alıcı başına değil: 0 ya da 1) döner."""
        events, recipients = await asyncio.to_thread(self._collect)
        if not events or not recipients:
            return 0
        default = self._default_language or FALLBACK_LANGUAGE
        for recipient in recipients:
            language = recipient.language if is_supported(recipient.language) else default
            with use_language(language):
                text = queue_message(len(events))
            await self._send(bot, recipient.telegram_id, text)
        return 1

    def _collect(self) -> tuple[list[PendingEvent], list[Recipient]]:
        """Yeni kuyruk olaylarını ve alıcıları okur; olayları gönderilmiş sayar (en çok bir kez).

        Alıcı yoksa olaylar yine tüketilir: bildirim, olay olduğu andaki listedekileredir."""
        cutoff = utcnow() - self._lookback
        self._notified = {id_: ts for id_, ts in self._notified.items() if ts >= cutoff}
        with self._session_factory() as session:
            rows = session.execute(
                select(Event.id, Event.ts)
                .where(
                    Event.id > self._baseline,
                    Event.ts >= cutoff,
                    Event.type.in_(QUEUE_EVENT_TYPES),
                )
                .order_by(Event.id)
            ).all()
            events = [
                PendingEvent(id=row.id, ts=row.ts) for row in rows if row.id not in self._notified
            ]
            if not events:
                return [], []
            self._notified.update({event.id: event.ts for event in events})
            recipients = [
                Recipient(row.telegram_id, row.language)
                for row in session.execute(
                    permitted_ids().add_columns(User.language).order_by(TelegramUser.telegram_id)
                )
            ]
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
