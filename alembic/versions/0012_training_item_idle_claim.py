"""Eğitim yapay zekâ yolu: `training_items` sahiplenme alanları (11.9.3)

İşçi yükleme kuyruğu boşken `ai_pending` eğitim öğesini boş-zaman işi olarak sahiplenir ve yapay
zekâya sınıflandırtır (PLAN.md §C86 "Yapay zekâ yolu", `app.training.classification`). Boş-zaman
çerçevesinin sahiplenme alanları (`IdleClaimMixin`, tm 111) bu tabloya girer: `idle_claimed_by`,
`idle_claim_expires_at`, `idle_attempts` (varsayılan 0). Göç veri yazmaz: var olan `ai_pending` öğe
sahiplenilmemiş sayılır ve işçi onu sırası gelince sınıflandırır. Geri alışta üç sütun düşer.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-26 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("training_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("idle_claimed_by", sa.String(length=128), nullable=True))
        batch_op.add_column(
            sa.Column("idle_claim_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("idle_attempts", sa.Integer(), server_default="0", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("training_items", schema=None) as batch_op:
        batch_op.drop_column("idle_attempts")
        batch_op.drop_column("idle_claim_expires_at")
        batch_op.drop_column("idle_claimed_by")
