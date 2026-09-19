"""Kalıcı işçi kuyruğu: `upload_jobs` (13.3.1)

Partiyi işleme işi veritabanında durur: uygulama yeniden başlayınca yarım kalan parti kaldığı
aşamadan sürdürülür (`app.worker`). PRD §8.1 tablo listesinde yok; bu tablo o gereksinimin deposudur
(PLAN.md §C72, §D43). Göç anında son durumda (`done`, `partial`, `failed`) olmayan her parti için
kuyrukta bekleyen bir iş açılır — göçten önce yarıda kalmış ya da hiç işlenmemiş parti de kuyruğa
girer.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-19 20:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "upload_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("upload_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("claimed_by", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'finished', 'abandoned')",
            name=op.f("ck_upload_jobs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"], ["uploads.id"], name=op.f("fk_upload_jobs_upload_id_uploads")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_upload_jobs")),
        sa.UniqueConstraint("upload_id", name=op.f("uq_upload_jobs_upload_id")),
    )
    with op.batch_alter_table("upload_jobs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_upload_jobs_status"), ["status"], unique=False)

    op.execute(
        "INSERT INTO upload_jobs (upload_id, status, attempts, enqueued_at) "
        "SELECT id, 'queued', 0, created_at FROM uploads "
        "WHERE status NOT IN ('done', 'partial', 'failed') ORDER BY created_at, id"
    )


def downgrade() -> None:
    with op.batch_alter_table("upload_jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_upload_jobs_status"))

    op.drop_table("upload_jobs")
