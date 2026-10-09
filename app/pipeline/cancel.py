"""Süren partiyi iptal etme ve takılan partinin otomatik iptali — PRD 10.3.6, 10.3.7 (K10, K15, K16;
PLAN.md §D114).

Partiyi yalnız ayrı işleyici süreci (`python -m app.worker`) işler; işleyici kapalıysa ya da önünde
uzun bir iş varsa parti `received`'da, işi `queued`'da bekler. İK süren partiyi iki aşamalı onayla
iptal eder (`cancel_upload`, `reason = manual`); alındığı andan (`uploads.created_at`) beri
`Settings.upload_timeout_seconds` (600) geçmiş ve hâlâ bitmemiş parti kendiliğinden iptal edilir
(`cancel_stale_uploads`, `reason = timeout`, `actor = system`).

**Sonuç.** Parti `cancelled` olur (son durum; `failed` değil — hata izleme ve botun "işlenemedi"
bildirimi onu saymaz). İşi `cancelled` olur, kirası boşalır, `finished_at` yazılır: kimse onu almaz.
İşi tutan işleyici bir sonraki geçişinde işin kendisinde olmadığını görür (`LeaseLostError`,
orkestrasyonun `ProcessingWithdrawn`'ı): o adımın işlemi geri alınır, parti `failed` yapılmaz,
`cancelled` kalır. Tek işlemli uzun adım (analiz) iptale rağmen sonuna kadar sürer ve sonra geri
alınır; iptal anlık durdurma vaat etmez.

**Silme değildir (K10, K15).** Inbox dosyaları, o ana kadar commit edilmiş sayfalar, analizler,
plan, kuyruk öğeleri ve belgeler yerinde kalır; dosya sistemine hiçbir şey yazılmaz. İptal edilen
partinin dosyaları SHA-256 tekrar tespitinde özgün sayılmaz (`app.storage.hashing`): aynı dosya
yeniden yüklenince yeniden işlenir.

**Yarış.** Parti satırı kilitlenip yeniden okunur: bu arada son duruma varmış (ya da başka bir
istekle iptal edilmiş) parti iptal edilmez (`UploadNotCancellableError`) ve olay yazılmaz — elle ve
otomatik iptal aynı anda gelse de tek `UPLOAD_CANCELLED` düşer.

**Olay.** `UPLOAD_CANCELLED`: veri `stage` (iptal anındaki durum), `reason` (`manual` / `timeout`),
`waited_seconds` (alındığından beri), `job_status` (işin iptal anındaki durumu; iş yoksa `None`).
Kişisel değer yok. `actor` elle iptalde kullanıcı adı, otomatikte `system`. İki aşamalı onay ve
`USER_CONFIRMED` çağıranın işidir (`app.web.routers.upload_page`).

Hiçbir fonksiyon commit etmez; işlem sınırı çağıranındır. Zaman `now` ile verilebilir (UTC).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Event, JobStatus, Upload, UploadJob, UploadStatus, utcnow
from app.events import EventType, record_event
from app.pipeline.orchestrate import UPLOAD_TRANSITIONS

SYSTEM_ACTOR = "system"

# İptal edilebilen (bitmemiş) durumlar: `received`, `rendering`, `analyzing`, `planning`,
# `executing`.
CANCELLABLE_STATUSES = frozenset(
    status for status, targets in UPLOAD_TRANSITIONS.items() if UploadStatus.CANCELLED in targets
)


class CancelReason(enum.StrEnum):
    """`UPLOAD_CANCELLED.data.reason`."""

    MANUAL = "manual"  # 10.3.6: İK iki aşamalı onayla
    TIMEOUT = "timeout"  # 10.3.7: süre aşımı, sistem


class UploadNotCancellableError(ValueError):
    """Parti iptal edilemez: son durumda (bitti, işlenemedi ya da zaten iptal edildi)."""


@dataclass(frozen=True, slots=True)
class Cancellation:
    upload_id: str
    stage: UploadStatus
    reason: CancelReason
    actor: str
    cancelled_at: datetime
    waited_seconds: int
    job_status: str | None


def is_cancellable(upload: Upload) -> bool:
    return UploadStatus(upload.status) in CANCELLABLE_STATUSES


def cancel_upload(
    session: Session,
    upload: Upload,
    *,
    actor: str,
    reason: CancelReason,
    now: datetime | None = None,
) -> Cancellation:
    """Süren partiyi iptal eder (modül açıklaması); commit etmez.

    Parti son durumdaysa `UploadNotCancellableError` ve hiçbir şey yazılmaz. Elle iptalde `actor`
    kullanıcı adıdır (K16) ve boş olamaz.
    """
    if not actor.strip():
        raise ValueError("İptal kullanıcı adıyla loglanır (K16): actor boş olamaz")
    # Satır kilidi (PostgreSQL `FOR UPDATE`; SQLite `BEGIN IMMEDIATE`): aynı anda gelen öteki iptal
    # ya da partiyi bitiren işleyici bekler; sonra parti yeniden okunur.
    session.refresh(upload, with_for_update=True)
    stage = UploadStatus(upload.status)
    if stage not in CANCELLABLE_STATUSES:
        raise UploadNotCancellableError(
            f"Parti {upload.id} '{stage.value}' durumunda; iptal edilmez"
        )
    now = now or utcnow()
    upload.status = UploadStatus.CANCELLED.value
    job = session.scalars(
        select(UploadJob)
        .where(UploadJob.upload_id == upload.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    job_status = job.status if job is not None else None
    if job is not None:
        job.status = JobStatus.CANCELLED.value
        job.lease_expires_at = None
        job.finished_at = now
    waited = max(0, int((now - upload.created_at).total_seconds()))
    record_event(
        session,
        EventType.UPLOAD_CANCELLED,
        upload_id=upload.id,
        actor=actor,
        data={
            "stage": stage.value,
            "reason": reason.value,
            "waited_seconds": waited,
            "job_status": job_status,
        },
    )
    return Cancellation(
        upload_id=upload.id,
        stage=stage,
        reason=reason,
        actor=actor,
        cancelled_at=now,
        waited_seconds=waited,
        job_status=job_status,
    )


def cancel_stale_uploads(
    session: Session, *, timeout_seconds: int, now: datetime | None = None
) -> list[str]:
    """Alındığından beri `timeout_seconds`'tan uzun süredir bitmemiş, yoksayılmamış partileri
    `system` adına iptal eder (10.3.7); iptal edilenlerin kimliklerini alınma sırasıyla döner.
    Commit etmez.

    Başka bir işlemin kilitlediği parti atlanır (PostgreSQL `SKIP LOCKED`); bir sonraki denetim onu
    yakalar. Bu arada son duruma varan parti iptal edilmez.
    """
    now = now or utcnow()
    cutoff = now - timedelta(seconds=timeout_seconds)
    stale = session.scalars(
        select(Upload)
        .where(
            Upload.status.in_([status.value for status in CANCELLABLE_STATUSES]),
            Upload.dismissed_at.is_(None),
            Upload.created_at < cutoff,
        )
        .order_by(Upload.created_at, Upload.id)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    ).all()
    cancelled: list[str] = []
    for upload in stale:
        try:
            cancel_upload(session, upload, actor=SYSTEM_ACTOR, reason=CancelReason.TIMEOUT, now=now)
        except UploadNotCancellableError:
            continue
        cancelled.append(upload.id)
    session.flush()
    return cancelled


def last_cancellation(session: Session, upload_id: str) -> tuple[datetime, str, str] | None:
    """İptal edilen partinin `UPLOAD_CANCELLED` olayı: (an, kullanıcı, `reason`); yoksa `None`."""
    event = session.scalars(
        select(Event)
        .where(Event.upload_id == upload_id, Event.type == EventType.UPLOAD_CANCELLED.value)
        .order_by(Event.id.desc())
        .limit(1)
    ).first()
    if event is None:
        return None
    reason = (event.data_json or {}).get("reason", CancelReason.MANUAL.value)
    return event.ts, event.actor, str(reason)
