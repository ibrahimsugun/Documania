"""Kalıcı örnek dizini: `example_index` tablosu (11.9.10)

PLAN.md §D135 a: her örnek dosyası için tür, ad, boyut, SHA-256, dosya türü, sayfa sayısı, önizleme
anahtarı ve ham dosyanın durumu (`present`/`removed`, `removed_at`); örneklerden çıkarılan satır
`archived_at` taşır ve `(type_slug, name)` tekilliği yalnız çıkarılmamış satırlardadır. Ham dosya
silinince örnek bu satır ve kalıcı önizlemesiyle yaşar. Göç veri yazmaz: dizin uygulama
(`app.storage.examples.sync_example_index`) ve örnek yazımı tarafından doldurulur. Geri alışta
tablo düşer.

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | Sequence[str] | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE = "archived_at IS NULL"


def upgrade() -> None:
    op.create_table(
        "example_index",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type_slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("file_kind", sa.String(length=16), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("preview_key", sa.String(length=32), nullable=False),
        sa.Column("original_state", sa.String(length=16), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "original_state IN ('present', 'removed')",
            name=op.f("ck_example_index_original_state"),
        ),
        sa.CheckConstraint(
            "(original_state = 'removed') = (removed_at IS NOT NULL)",
            name=op.f("ck_example_index_removed_at"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_example_index")),
    )
    with op.batch_alter_table("example_index", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_example_index_sha256"), ["sha256"], unique=False)
        batch_op.create_index(
            "uq_example_index_active_name",
            ["type_slug", "name"],
            unique=True,
            sqlite_where=sa.text(_ACTIVE),
            postgresql_where=sa.text(_ACTIVE),
        )


def downgrade() -> None:
    with op.batch_alter_table("example_index", schema=None) as batch_op:
        batch_op.drop_index("uq_example_index_active_name")
        batch_op.drop_index(batch_op.f("ix_example_index_sha256"))
    op.drop_table("example_index")
