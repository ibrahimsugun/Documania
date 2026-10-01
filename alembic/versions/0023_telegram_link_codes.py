"""Telegram hesabını bağlantıyla bağlamanın tek kullanımlık kodu: `telegram_link_codes` (12.1.4)

Yönetici Kullanıcılar sayfasında bir kullanıcı için bot bağlantısı (`?start=<kod>`) üretir; kişi
bağlantıyı açınca bot Telegram kimliğini o kullanıcıya bağlar (PLAN.md §D87). Kodun kendisi değil
SHA-256 özeti saklanır; kod 10 dakika ve bir kez geçerlidir, yeni kod öncekini iptal eder. PRD §8.1
tablo listesinde yok; bu tablo §D87'deki kuralın deposudur. Satır silinmez (R11). Göç veri yazmaz;
geri alış tabloyu düşürür, yalnız geliştirme veritabanı içindir.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-01 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_link_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=150), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_telegram_link_codes_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telegram_link_codes")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_telegram_link_codes_code_hash")),
    )
    with op.batch_alter_table("telegram_link_codes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_telegram_link_codes_user_id"), ["user_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("telegram_link_codes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_telegram_link_codes_user_id"))

    op.drop_table("telegram_link_codes")
