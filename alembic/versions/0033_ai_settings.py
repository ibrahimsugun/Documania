"""Yapay zekâ çalışma zamanı ayarı: `ai_settings` tek satırlık tablo (03.8.1, 03.8.2)

Etkin sağlayıcı (`anthropic` ya da `openai`), her sağlayıcının modeli ve eforu (boş = sağlayıcı
varsayılanı), son değiştiren ve zamanı (PRD §8.1; PLAN.md §D124). `id = 1` denetimi tabloyu tek
satırda tutar. Anahtar sütunu yoktur. Göç veri yazmaz: satır yokken `.env` geçerlidir ve bugünkü
kurulum değişmeden çalışır; ilk kayıt satırı açar. Geri alışta tablo düşer (ayar `.env`'e döner).

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-23 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | Sequence[str] | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("anthropic_model", sa.String(length=100), nullable=False),
        sa.Column("anthropic_effort", sa.String(length=16), nullable=True),
        sa.Column("openai_model", sa.String(length=100), nullable=False),
        sa.Column("openai_effort", sa.String(length=16), nullable=True),
        sa.Column("updated_by", sa.String(length=150), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_ai_settings_single_row")),
        sa.CheckConstraint(
            "provider IN ('anthropic', 'openai')", name=op.f("ck_ai_settings_provider")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_settings")),
    )


def downgrade() -> None:
    op.drop_table("ai_settings")
