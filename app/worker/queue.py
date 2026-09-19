"""Kalıcı işçi kuyruğu: iş kaydı, alma, kira ve vazgeçme (PRD 13.3.1; PLAN.md §C72).

Partiyi işleme işi `upload_jobs` tablosunda durur; iş, parti açıldığı işlemde kuyruğa girer
(`enqueue_upload`, `app.web.routers.uploads.store_upload`). Parti ile işi aynı commit'te doğduğu
için hiçbir parti işsiz kalmaz ve süreç ne zaman durursa dursun iş veritabanında bekler.

**Alma.** Bir işleyici işi tek kullanımlık bir kimlikle (`new_claim_token`) alır: iş `running`
olur, `attempts` bir artar ve kira (`lease_expires_at`) başlar. Alınabilecek iş kuyrukta bekleyen
(`queued`) ya da kirası dolmuş `running` iştir; kirası dolan iş, onu alan işleyicinin durduğu
anlamına gelir (yeniden başlatma, çökme). Alma koşullu bir güncellemedir: aynı işi iki işleyici
alamaz (PostgreSQL'de satır kilidi ve `SKIP LOCKED`, SQLite'ta her işlemin tuttuğu yazma kilidi).

**Kira.** İşleyici kirasını partinin her geçişinde, geçişle aynı işlemde yeniler; parti son duruma
vardığı işlemde iş `finished` olur (`app.worker.runner`). Her yenileme işin hâlâ aynı kimlikte
olduğunu denetler: iş başka bir işleyiciye geçmişse `LeaseLostError` (orkestrasyonun
`ProcessingWithdrawn`'ı) yükselir ve eski işleyici partiye bir daha yazmaz. İşin kime ait olduğu
kiranın süresine değil kimliğe bakar: kirası dolmuş ama henüz kimse almamış iş hâlâ eski
sahibinindir.

**Vazgeçme.** Kirası `max_attempts` kez dolmuş iş (işleyicisi o kadar kez yarıda kalmış — ör. her
seferinde süreci düşüren bir parti) bir daha alınmaz: iş `abandoned` olur, parti durduğu aşamadan
`failed`'a geçer ve `PIPELINE_FAILED` yazılır (`JobAbandonedError`). Son durumdaki partinin işi ise
yalnız `finished` işaretlenir.

İşlevler oturumu commit etmez — işlem sınırı çağıranındır. Zaman `now` ile verilebilir (UTC).
"""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, and_, or_, select, update
from sqlalchemy.orm import Session

from app.db.models import JobStatus, Upload, UploadJob, UploadStatus, utcnow
from app.pipeline.orchestrate import UPLOAD_TRANSITIONS, ProcessingWithdrawn, fail_upload

_TOKEN_HOST_LENGTH = 64  # `upload_jobs.claimed_by` 128 karakterdir


class LeaseLostError(ProcessingWithdrawn):
    """13.3.1: iş artık bu işleyicinin değil — başka bir işleyiciye geçti, bitti ya da bırakıldı."""


class JobAbandonedError(RuntimeError):
    """13.3.1: işleyicisi en çok deneme sayısı kadar yarıda kalan partiden vazgeçildi
    (`PIPELINE_FAILED.error`)."""


@dataclass(frozen=True, slots=True)
class Claim:
    """Bir işleyicinin aldığı iş: partisi ve alışın tek kullanımlık kimliği."""

    upload_id: str
    token: str


def new_claim_token() -> str:
    """İşi alan işleyicinin tek kullanımlık kimliği: `<makine>:<süreç>:<rastgele>`.

    Makine ve süreç, işi kimin tuttuğunu okuyana söyler; rastgele kısım aynı süreçteki iki alışı
    bile birbirinden ayırır."""
    host = socket.gethostname()[:_TOKEN_HOST_LENGTH]
    return f"{host}:{os.getpid()}:{uuid.uuid4().hex}"


def enqueue_upload(session: Session, upload_id: str, *, now: datetime | None = None) -> UploadJob:
    """Partinin işini kuyruğa ekler (`queued`). Parti açılan işlemde çağrılır."""
    job = UploadJob(
        upload_id=upload_id,
        status=JobStatus.QUEUED.value,
        attempts=0,
        enqueued_at=now or utcnow(),
    )
    session.add(job)
    session.flush()
    return job


def claim_upload(
    session: Session,
    upload_id: str,
    *,
    token: str,
    lease_seconds: int,
    now: datetime | None = None,
) -> Claim | None:
    """Partinin kuyrukta bekleyen işini `token` ile alır; iş yoksa ya da beklemiyorsa `None`."""
    waiting = and_(UploadJob.upload_id == upload_id, UploadJob.status == JobStatus.QUEUED)
    if not _take(session, waiting, token=token, lease_seconds=lease_seconds, now=now or utcnow()):
        return None
    return Claim(upload_id, token)


def claim_next(
    session: Session,
    *,
    token: str,
    lease_seconds: int,
    max_attempts: int,
    now: datetime | None = None,
) -> Claim | None:
    """Sıradaki işi `token` ile alır: en eski bekleyen ya da kirası dolmuş (ve `max_attempts`'a
    varmamış) iş. Alınacak iş yoksa `None`."""
    now = now or utcnow()
    claimable = or_(
        UploadJob.status == JobStatus.QUEUED,
        and_(
            UploadJob.status == JobStatus.RUNNING,
            UploadJob.lease_expires_at < now,
            UploadJob.attempts < max_attempts,
        ),
    )
    candidate = session.execute(
        select(UploadJob.id, UploadJob.upload_id)
        .where(claimable)
        .order_by(UploadJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if candidate is None:
        return None
    job_id, upload_id = candidate
    if not _take(
        session,
        and_(UploadJob.id == job_id, claimable),
        token=token,
        lease_seconds=lease_seconds,
        now=now,
    ):
        return None
    return Claim(upload_id, token)


def renew_claim(
    session: Session, claim: Claim, *, lease_seconds: int, now: datetime | None = None
) -> None:
    """İş hâlâ `claim`'inse kirasını `lease_seconds` uzatır; değilse `LeaseLostError`."""
    job = _owned(session, claim)
    job.lease_expires_at = (now or utcnow()) + timedelta(seconds=lease_seconds)
    session.flush()


def finish_claim(session: Session, claim: Claim, *, now: datetime | None = None) -> None:
    """Partisi son duruma varan işi `finished` yapar; iş `claim`'in değilse `LeaseLostError`."""
    job = _owned(session, claim)
    job.status = JobStatus.FINISHED.value
    job.finished_at = now or utcnow()
    job.lease_expires_at = None
    session.flush()


def release_claim(session: Session, claim: Claim) -> None:
    """Alınıp işlenmeye başlanmamış işi kuyruğa geri koyar (ör. yapay zekâ sağlayıcısı
    kurulamadı); iş `claim`'in değilse `LeaseLostError`. Alış sayısı geri alınmaz."""
    job = _owned(session, claim)
    job.status = JobStatus.QUEUED.value
    job.claimed_by = None
    job.lease_expires_at = None
    session.flush()


def abandon_exhausted(
    session: Session, *, max_attempts: int, now: datetime | None = None
) -> list[str]:
    """Kirası `max_attempts` kez dolmuş işlerden vazgeçer; partileri döner (modül açıklaması).

    Bitmemiş parti `failed` olur ve `PIPELINE_FAILED` yazılır (`JobAbandonedError`, durduğu
    aşama `stage`'de); iş `abandoned` olur. Parti zaten son durumdaysa iş yalnız `finished` olur."""
    now = now or utcnow()
    exhausted = and_(
        UploadJob.status == JobStatus.RUNNING,
        UploadJob.lease_expires_at < now,
        UploadJob.attempts >= max_attempts,
    )
    jobs = session.scalars(
        select(UploadJob)
        .where(exhausted)
        .order_by(UploadJob.id)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    ).all()
    abandoned: list[str] = []
    for job in jobs:
        upload = session.get_one(
            Upload, job.upload_id, with_for_update=True, populate_existing=True
        )
        job.finished_at = now
        job.lease_expires_at = None
        if not UPLOAD_TRANSITIONS[UploadStatus(upload.status)]:
            job.status = JobStatus.FINISHED.value
            continue
        job.status = JobStatus.ABANDONED.value
        fail_upload(
            session,
            upload,
            JobAbandonedError(
                f"Partiyi işleyen süreç {job.attempts} kez yarıda kaldı; parti bırakıldı (13.3.1)."
            ),
        )
        abandoned.append(job.upload_id)
    session.flush()
    return abandoned


def _take(
    session: Session,
    condition: ColumnElement[bool],
    *,
    token: str,
    lease_seconds: int,
    now: datetime,
) -> bool:
    # Koşullu güncelleme: iş bu arada başka bir işleyiciye geçtiyse hiçbir satır değişmez.
    result = session.execute(
        update(UploadJob)
        .where(condition)
        .values(
            status=JobStatus.RUNNING.value,
            claimed_by=token,
            claimed_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            attempts=UploadJob.attempts + 1,
        )
        .execution_options(synchronize_session="fetch")
    )
    return bool(result.rowcount)


def _owned(session: Session, claim: Claim) -> UploadJob:
    # Oturumdaki kopya bayat olabilir (commit nesneleri eskitmez); satır kilitlenip yeniden okunur.
    job = session.scalars(
        select(UploadJob)
        .where(UploadJob.upload_id == claim.upload_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if job is None or job.status != JobStatus.RUNNING or job.claimed_by != claim.token:
        raise LeaseLostError(f"Partinin işi bu işleyicide değil (parti {claim.upload_id}).")
    return job
