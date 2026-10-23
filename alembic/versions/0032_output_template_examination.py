"""Hazır şablon incelemesi: `output_templates` inceleme kuyruğu ve sahiplenme alanları (15.1.2)

Şablon yüklenince (ve "yeniden incele" ile) işçinin boş-zaman işi onu sahiplenip yapay zekâya
inceletir (`app.output_templates.examine`, PLAN.md §D123 c). `examine_requested_at` incelemenin
istendiği zamandır; doluysa şablon kuyrukta bekler, inceleme bitince (harita sürümü ya da
`examine_error`) boşalır. Boş-zaman çerçevesinin sahiplenme alanları (`IdleClaimMixin`, tm 111)
aynı tabloya girer: `idle_claimed_by`, `idle_claim_expires_at`, `idle_attempts` (varsayılan 0).
Göç veri yazmaz: var olan şablonlar incelenmemiş sayılır ve kuyruğa girmez — İK "yeniden incele"
ile ister. Geri alışta dört sütun düşer.

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-23 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | Sequence[str] | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("output_templates", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("examine_requested_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("idle_claimed_by", sa.String(length=128), nullable=True))
        batch_op.add_column(
            sa.Column("idle_claim_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("idle_attempts", sa.Integer(), server_default="0", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("output_templates", schema=None) as batch_op:
        batch_op.drop_column("idle_attempts")
        batch_op.drop_column("idle_claim_expires_at")
        batch_op.drop_column("idle_claimed_by")
        batch_op.drop_column("examine_requested_at")
