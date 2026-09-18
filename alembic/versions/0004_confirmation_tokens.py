"""İki aşamalı onayın tek kullanımlık belirteci: `confirmation_tokens` (10.8.1)

PRD §20.6.1 onay belirtecinin tek kullanımlık olmasını (adım 4: "sunucu belirteci doğrular ve
tüketir") ister; bunun için belirteç sunucuda durmalıdır. PRD §8.1 tablo listesinde yok; bu tablo o
kuralın deposudur (PLAN.md §C54, §D26). Belirtecin kendisi değil SHA-256 özeti saklanır.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-19 10:12:40.518302
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "confirmation_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("session_hash", sa.String(length=64), nullable=False),
        sa.Column("username", sa.String(length=150), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_confirmation_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_confirmation_tokens_token_hash")),
    )


def downgrade() -> None:
    op.drop_table("confirmation_tokens")
