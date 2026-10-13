"""Kayda İngilizce yazılan sistem metninin yapısı: `recorded_texts` (10.10.6)

Plan, kuyruk ve olay gerekçeleri kayıtta İngilizce düz metindir; panel onları kullanıcının dilinde
gösterir (PLAN.md §D121). Bu tablo metnin kaynağını (Türkçe msgid şablonu ve değerleri) metnin
SHA-256 özetiyle saklar. PRD §8.1 tablo listesinde yok; §D121'deki kararın deposudur. Göç veri
yazmaz: eski Türkçe kayıtlar geriye dönük çevrilmez, panelde olduğu gibi görünür. Geri alış tabloyu
düşürür, yalnız geliştirme veritabanı içindir.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-13 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | Sequence[str] | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recorded_texts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recorded_texts")),
        sa.UniqueConstraint("text_hash", name=op.f("uq_recorded_texts_text_hash")),
    )


def downgrade() -> None:
    op.drop_table("recorded_texts")
