"""Aday tür incelemesi: `candidate_document_types` taslak ve sahiplenme alanları (11.5.5)

İşçi boş zamanında bekleyen adayın örnek sayfalarını inceler ve tür taslağını adayda saklar
(PLAN.md §C85, `app.catalog.propose`): `proposal_json` (taslak ya da gerekçe, gözlenen kanıt,
model, kullanılan sayfa sayısı), `proposal_status` (`NULL` incelenmedi, `ready`, `failed`,
`no_samples`), `proposal_generated_at`. Boş-zaman çerçevesinin sahiplenme alanları
(`IdleClaimMixin`, tm 111) bu tabloya ilk kez girer: `idle_claimed_by`, `idle_claim_expires_at`,
`idle_attempts` (varsayılan 0). Göç veri yazmaz: var olan aday incelenmemiş sayılır ve işçi onu
sırası gelince inceler. Geri alışta altı sütun ve kısıt düşer.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-26 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("candidate_document_types", schema=None) as batch_op:
        batch_op.add_column(sa.Column("proposal_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("proposal_status", sa.String(length=16), nullable=True))
        batch_op.add_column(
            sa.Column("proposal_generated_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("idle_claimed_by", sa.String(length=128), nullable=True))
        batch_op.add_column(
            sa.Column("idle_claim_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("idle_attempts", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.create_check_constraint(
            op.f("ck_candidate_document_types_proposal_status"),
            "proposal_status IN ('ready', 'failed', 'no_samples')",
        )


def downgrade() -> None:
    with op.batch_alter_table("candidate_document_types", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_candidate_document_types_proposal_status"), type_="check")
        batch_op.drop_column("idle_attempts")
        batch_op.drop_column("idle_claim_expires_at")
        batch_op.drop_column("idle_claimed_by")
        batch_op.drop_column("proposal_generated_at")
        batch_op.drop_column("proposal_status")
        batch_op.drop_column("proposal_json")
