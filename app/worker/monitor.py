"""İzleme ve uyarı: hata, disk doluluğu ve kuyruk uzunluğu (PRD 13.6.1; PLAN.md §C76).

**Ne ölçülür.** Dört değer, her biri kendi eşiğiyle (`AlertThresholds`, `ALERT_*` ayarları):

- `errors` — son `error_window` içinde işlenemeyip `failed` olan parti sayısı (`PIPELINE_FAILED`
  olayı; işleyicisi defalarca yarıda kalıp bırakılan parti de bu olayı yazar, 13.3.1). Tek başarısız
  parti 12.4.1'in kendi bildirimidir; bu uyarı hatanın *sürekli* olduğunu (ör. sağlayıcı kesintisi)
  söyler.
- `disk` — veri dizininin bulunduğu diskin doluluk yüzdesi (`df`'in `Use%` sütunuyla aynı tanım).
  PostgreSQL'in kendi hacmi uygulama sürecinden görünmez, ölçülmez.
- `job_queue` — işlenmeyi bekleyen parti sayısı: kuyruktaki (`queued`) iş ile kirası dolmuş,
  yani işleyicisi durmuş (`running`) iş (13.3.1). Bekleyen iş çoğalıyorsa işleyici yetişmiyor ya da
  çalışmıyordur.
- `review_queue` — İK kararı bekleyen kuyruk öğesi sayısı (12.4). "Açık" tanımı panelin kuyruk
  sayfasıyla aynıdır (`app.web.routers.queue._state_filter`): çözülmemiş ve partisinin güncel
  planına ait (K18). `app.web` içe aktarılmaz (panel bu paketi kullanır); eşlik testte sınanır.

**Ne zaman uyarı.** `AlertTracker` her ölçümü önceki duruma göre değerlendirir: değer eşiğe varınca
uyarı *çıkar* (`RAISED`), sürdükçe `repeat`'te bir *hatırlatılır* (`REMINDER`) ve eşiğin
`CLEAR_RATIO`'sunun altına inince *giderilir* (`CLEARED`). Eşiğin hemen altındaki dalgalanma
arka arkaya çıkma/gitme mesajı yağdırmasın diye giderme eşiği çıkma eşiğinden düşüktür.

**Kim çalıştırır.** `AlertWatch` ölçümü `AlertThresholds.interval`'de bir yapar ve her uyarıyı loga
yazar (uyarı WARNING, giderilme INFO). Panel sürecinin işleyicisi (`app.worker.runner.Worker`) ve
botun bildiricisi (`app.telegram.notify.Notifier`, uyarıyı beyaz listedeki kullanıcılara da yollar)
birer `AlertWatch` kullanır; ikisi ayrı süreçtir ve her biri kendi durumunu tutar. Uyarı olay
değildir — §8.3'teki olay türü listesi kapalıdır (PRD 00.5.1) —, ölçümden her seferinde yeniden
hesaplanır; süreç yeniden başlayınca süren uyarı yeniden çıkar.

**Gizlilik (CONVENTIONS §6).** Mesaj ve log yalnız sayı ve yüzde taşır; belge, çalışan ya da hata
metni yoktur.
"""

from __future__ import annotations

import enum
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session, aliased, sessionmaker

from app.config import Settings
from app.db.models import Event, JobStatus, Plan, QueueItem, UploadJob, utcnow
from app.events import EventType

logger = logging.getLogger(__name__)

# Süren uyarı, değer eşiğin bu oranının altına inince giderilir (modül açıklaması).
CLEAR_RATIO = 0.9

_GIB = 1024**3


class AlertKind(enum.StrEnum):
    ERRORS = "errors"
    DISK = "disk"
    JOB_QUEUE = "job_queue"
    REVIEW_QUEUE = "review_queue"


LABELS: dict[AlertKind, str] = {
    AlertKind.ERRORS: "hata",
    AlertKind.DISK: "disk",
    AlertKind.JOB_QUEUE: "iş kuyruğu",
    AlertKind.REVIEW_QUEUE: "kuyruk",
}
ADVICE: dict[AlertKind, str] = {
    AlertKind.ERRORS: "Panelde başarısız partilere bakın.",
    AlertKind.DISK: "Yer açın ya da diski büyütün.",
    AlertKind.JOB_QUEUE: "İşleyicinin ve yapay zekâ sağlayıcısının çalıştığını kontrol edin.",
    AlertKind.REVIEW_QUEUE: "Panelde kuyruğa bakın.",
}


@dataclass(frozen=True, slots=True)
class AlertThresholds:
    """Uyarı eşikleri ve zamanlaması; varsayılanlar `Settings`'inkilerle aynıdır."""

    error_count: int = 3
    error_window: timedelta = timedelta(minutes=60)
    disk_used_percent: float = 85.0
    job_queue_length: int = 20
    review_queue_length: int = 50
    interval: timedelta = timedelta(seconds=60)
    repeat: timedelta = timedelta(minutes=360)

    @classmethod
    def from_settings(cls, settings: Settings) -> AlertThresholds:
        return cls(
            error_count=settings.alert_error_count,
            error_window=timedelta(minutes=settings.alert_error_window_minutes),
            disk_used_percent=settings.alert_disk_used_percent,
            job_queue_length=settings.alert_job_queue_length,
            review_queue_length=settings.alert_review_queue_length,
            interval=timedelta(seconds=settings.alert_check_seconds),
            repeat=timedelta(minutes=settings.alert_repeat_minutes),
        )


@dataclass(frozen=True, slots=True)
class Reading:
    """Bir değerin ölçümü: değer, eşiği ve kişisel değer taşımayan açıklaması (`text`)."""

    kind: AlertKind
    value: float
    limit: float
    text: str

    @property
    def tripped(self) -> bool:
        return self.value >= self.limit

    @property
    def recovered(self) -> bool:
        return self.value < self.limit * CLEAR_RATIO


class NoticeState(enum.StrEnum):
    RAISED = "raised"
    REMINDER = "reminder"
    CLEARED = "cleared"


_NOTICE_TITLES: dict[NoticeState, str] = {
    NoticeState.RAISED: "Uyarı",
    NoticeState.REMINDER: "Uyarı sürüyor",
    NoticeState.CLEARED: "Uyarı giderildi",
}


@dataclass(frozen=True, slots=True)
class Notice:
    """Bir uyarı olayı: çıktı, hatırlatıldı ya da giderildi."""

    state: NoticeState
    reading: Reading

    @property
    def message(self) -> str:
        """Beyaz listedeki kullanıcıya giden ve loga yazılan metin."""
        kind = self.reading.kind
        text = f"{_NOTICE_TITLES[self.state]} — {LABELS[kind]}: {self.reading.text}."
        if self.state is NoticeState.CLEARED:
            return text
        return f"{text} {ADVICE[kind]}"


def measure(
    session: Session, data_dir: Path, thresholds: AlertThresholds, *, now: datetime | None = None
) -> list[Reading]:
    """Dört değeri ölçer (modül açıklaması). Diskin ölçümü başarısızsa o okuma yoktur."""
    now = now or utcnow()
    readings = [
        _errors(session, thresholds, now),
        _disk(data_dir, thresholds),
        _job_queue(session, thresholds, now),
        _review_queue(session, thresholds),
    ]
    return [reading for reading in readings if reading is not None]


def _errors(session: Session, thresholds: AlertThresholds, now: datetime) -> Reading:
    failed = session.scalar(
        select(func.count())
        .select_from(Event)
        .where(
            Event.type == EventType.PIPELINE_FAILED.value,
            Event.ts >= now - thresholds.error_window,
        )
    )
    minutes = round(thresholds.error_window.total_seconds() / 60)
    return Reading(
        AlertKind.ERRORS,
        failed or 0,
        thresholds.error_count,
        f"son {minutes} dakikada {failed or 0} parti işlenemedi (eşik {thresholds.error_count})",
    )


def _disk(data_dir: Path, thresholds: AlertThresholds) -> Reading | None:
    try:
        usage = shutil.disk_usage(_existing_ancestor(data_dir))
    except OSError as exc:
        logger.warning("Disk doluluğu ölçülemedi (%s)", type(exc).__name__)
        return None
    # `df`'in `Use%`'sı: ayrılmış (yalnız yöneticiye açık) bloklar doluluğu düşürmesin.
    capacity = usage.used + usage.free
    if capacity <= 0:
        return None
    percent = usage.used / capacity * 100
    free = f"{usage.free / _GIB:.1f}".replace(".", ",")
    return Reading(
        AlertKind.DISK,
        percent,
        thresholds.disk_used_percent,
        f"veri diski %{percent:.0f} dolu, {free} GB boş (eşik %{thresholds.disk_used_percent:g})",
    )


def _existing_ancestor(path: Path) -> Path:
    # Veri dizini henüz açılmamış olabilir; doluluğu bulunduğu diskin en yakın var olan atası verir.
    path = path.absolute()
    while not path.exists() and path.parent != path:
        path = path.parent
    return path


def _job_queue(session: Session, thresholds: AlertThresholds, now: datetime) -> Reading:
    waiting = session.scalar(
        select(func.count())
        .select_from(UploadJob)
        .where(
            or_(
                UploadJob.status == JobStatus.QUEUED,
                and_(UploadJob.status == JobStatus.RUNNING, UploadJob.lease_expires_at < now),
            )
        )
    )
    return Reading(
        AlertKind.JOB_QUEUE,
        waiting or 0,
        thresholds.job_queue_length,
        f"{waiting or 0} parti işlenmeyi bekliyor (eşik {thresholds.job_queue_length})",
    )


def _review_queue(session: Session, thresholds: AlertThresholds) -> Reading:
    newer = aliased(Plan)
    current = select(Plan.id).where(
        ~exists().where(newer.upload_id == Plan.upload_id, newer.version > Plan.version)
    )
    open_items = session.scalar(
        select(func.count())
        .select_from(QueueItem)
        .where(QueueItem.resolved_at.is_(None), QueueItem.plan_id.in_(current))
    )
    return Reading(
        AlertKind.REVIEW_QUEUE,
        open_items or 0,
        thresholds.review_queue_length,
        f"{open_items or 0} öğe karar bekliyor (eşik {thresholds.review_queue_length})",
    )


class AlertTracker:
    """Ölçümleri önceki duruma göre uyarıya çevirir (modül açıklaması); süren uyarıları tutar."""

    def __init__(self, repeat: timedelta) -> None:
        self._repeat = repeat
        # Süren uyarı → en son bildirildiği an.
        self._active: dict[AlertKind, datetime] = {}

    def observe(self, readings: list[Reading], now: datetime) -> list[Notice]:
        notices: list[Notice] = []
        for reading in readings:
            notified = self._active.get(reading.kind)
            if notified is None:
                if reading.tripped:
                    self._active[reading.kind] = now
                    notices.append(Notice(NoticeState.RAISED, reading))
            elif reading.recovered:
                del self._active[reading.kind]
                notices.append(Notice(NoticeState.CLEARED, reading))
            elif now - notified >= self._repeat:
                self._active[reading.kind] = now
                notices.append(Notice(NoticeState.REMINDER, reading))
        return notices

    @property
    def active(self) -> frozenset[AlertKind]:
        return frozenset(self._active)


class AlertWatch:
    """Ölçümü `interval`'de bir yapar, uyarıları loga yazar ve çağırana döner (modül açıklaması).

    Bir örnek tek iş parçacığından kullanılır. Ölçüm hata verirse istisna çağırana yükselir."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        data_dir: Path,
        thresholds: AlertThresholds | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._data_dir = data_dir
        self._thresholds = thresholds or AlertThresholds()
        self._tracker = AlertTracker(self._thresholds.repeat)
        self._last_check: datetime | None = None

    @classmethod
    def from_settings(
        cls,
        session_factory: sessionmaker[Session],
        settings: Settings,
        data_dir: Path | None = None,
    ) -> AlertWatch:
        """`settings`'in eşikleriyle kurar; disk, `data_dir`'in (varsayılan `DATA_DIR`) diskidir."""
        return cls(
            session_factory,
            data_dir if data_dir is not None else settings.data_dir,
            AlertThresholds.from_settings(settings),
        )

    @property
    def active(self) -> frozenset[AlertKind]:
        """Şu an süren uyarılar."""
        return self._tracker.active

    def check(self, now: datetime | None = None) -> list[Notice]:
        """Son ölçümden `interval` geçtiyse ölçer ve yeni uyarıları döner; geçmediyse boş."""
        now = now or utcnow()
        if self._last_check is not None and now - self._last_check < self._thresholds.interval:
            return []
        self._last_check = now
        with self._session_factory() as session:
            readings = measure(session, self._data_dir, self._thresholds, now=now)
        notices = self._tracker.observe(readings, now)
        for notice in notices:
            level = logging.INFO if notice.state is NoticeState.CLEARED else logging.WARNING
            logger.log(level, notice.message)
        return notices
