"""Giriş kaydı: `login_log` tablosu (10.1.11)

Panel girişleri ve çıkışları (PRD §8.1; PLAN.md §D125): zaman, denenen ad (en çok 64 karakter),
bulunduysa kullanıcı, sonuç (`success`, `failed`, `logout`), başarısızlığın nedeni, IP ve tarayıcı
(en çok 255 karakter). Parola ve belirteç sütunu yoktur. `ts` ve `user_id` dizinlidir. Göç veri
yazmaz; geri alışta tablo düşer.

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-26 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | Sequence[str] | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            "outcome IN ('success', 'failed', 'logout')", name=op.f("ck_login_log_outcome")
        ),
        sa.CheckConstraint(
            "(outcome = 'failed' AND reason IS NOT NULL "
            "AND reason IN ('unknown_user', 'wrong_password', 'inactive')) "
            "OR (outcome != 'failed' AND reason IS NULL)",
            name=op.f("ck_login_log_reason"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_login_log_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_log")),
    )
    with op.batch_alter_table("login_log", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_login_log_ts"), ["ts"], unique=False)
        batch_op.create_index(batch_op.f("ix_login_log_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("login_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_login_log_user_id"))
        batch_op.drop_index(batch_op.f("ix_login_log_ts"))
    op.drop_table("login_log")
