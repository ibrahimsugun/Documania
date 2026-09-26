"""Kalıcı işçi kuyruğu (PRD 13.3.1), ayrı `python -m app.worker` sürecinde çalışır.

HTTP uygulaması worker döngüsü başlatmaz. Partiler veritabanında kalır; süreç yeniden
başlayınca süresi dolan kira ile yarım kalan iş kaldığı aşamadan sürdürülür. İzleme
(PRD 13.6.1) `monitor` modülünde, kuyruk boşken koşan arka plan işlerinin çerçevesi (PLAN.md §C85)
`idle` modülündedir.
"""

from app.worker.idle import (
    IdleClaim,
    IdleClaimMixin,
    IdleContext,
    IdleJob,
    IdleTable,
    default_idle_jobs,
    run_idle_unit,
)
from app.worker.monitor import (
    AlertKind,
    AlertThresholds,
    AlertTracker,
    AlertWatch,
    Notice,
    NoticeState,
    Reading,
    measure,
)
from app.worker.queue import (
    Claim,
    JobAbandonedError,
    LeaseLostError,
    abandon_exhausted,
    claim_next,
    claim_upload,
    enqueue_upload,
    finish_claim,
    new_claim_token,
    release_claim,
    renew_claim,
)
from app.worker.runner import (
    Worker,
    claim_and_run,
    create_worker,
    lease_checkpoint,
    run_claimed_upload,
    start_worker,
)

__all__ = [
    "AlertKind",
    "AlertThresholds",
    "AlertTracker",
    "AlertWatch",
    "Claim",
    "IdleClaim",
    "IdleClaimMixin",
    "IdleContext",
    "IdleJob",
    "IdleTable",
    "JobAbandonedError",
    "LeaseLostError",
    "Notice",
    "NoticeState",
    "Reading",
    "Worker",
    "abandon_exhausted",
    "claim_and_run",
    "claim_next",
    "claim_upload",
    "create_worker",
    "default_idle_jobs",
    "enqueue_upload",
    "finish_claim",
    "lease_checkpoint",
    "measure",
    "new_claim_token",
    "release_claim",
    "renew_claim",
    "run_claimed_upload",
    "run_idle_unit",
    "start_worker",
]
