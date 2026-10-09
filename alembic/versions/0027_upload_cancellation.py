"""Süren partiyi iptal etme: `cancelled` parti ve iş durumu (10.3.6, 10.3.7)

Süren parti elle (iki aşamalı onayla) ya da alındıktan 10 dakika sonra kendiliğinden iptal edilir
(PLAN.md §D114): parti `cancelled` olur, işi kuyruktan düşer (`upload_jobs.status = 'cancelled'`).
`uploads.status` ve `upload_jobs.status` CHECK'leri yeni değeri kabul eder. Göç veri yazmaz: var
olan parti ve işler olduğu gibi kalır. SQLite'ta tablolar yeniden kurulur, kısıtlar korunur. Geri
alış iptal edilmiş parti ya da iş varken yapılamaz (eski CHECK'e sığmaz); yalnız geliştirme
veritabanı içindir.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-09 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPLOAD_CHECK = "ck_uploads_status"
_JOB_CHECK = "ck_upload_jobs_status"
_UPLOAD_STATUSES = (
    "'received', 'rendering', 'analyzing', 'planning', 'executing', 'done', 'partial', 'failed'"
)
_JOB_STATUSES = "'queued', 'running', 'finished', 'abandoned'"


def upgrade() -> None:
    with op.batch_alter_table("uploads", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f(_UPLOAD_CHECK), type_="check")
        batch_op.create_check_constraint(
            batch_op.f(_UPLOAD_CHECK), f"status IN ({_UPLOAD_STATUSES}, 'cancelled')"
        )
    with op.batch_alter_table("upload_jobs", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f(_JOB_CHECK), type_="check")
        batch_op.create_check_constraint(
            batch_op.f(_JOB_CHECK), f"status IN ({_JOB_STATUSES}, 'cancelled')"
        )


def downgrade() -> None:
    with op.batch_alter_table("upload_jobs", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f(_JOB_CHECK), type_="check")
        batch_op.create_check_constraint(batch_op.f(_JOB_CHECK), f"status IN ({_JOB_STATUSES})")
    with op.batch_alter_table("uploads", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f(_UPLOAD_CHECK), type_="check")
        batch_op.create_check_constraint(
            batch_op.f(_UPLOAD_CHECK), f"status IN ({_UPLOAD_STATUSES})"
        )
