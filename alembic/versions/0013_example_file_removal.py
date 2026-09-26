"""Etiket kararı: örneklerden çıkarılan kayıt (11.9.4)

İK eğitim örneğini örneklerden çıkarınca dosya `KnownDocuments/_egitim/cikarilan/<slug>/`'a taşınır,
silinmez (PLAN.md §C86 "Etiket kararı", §D58 d); `example_files` satırı da silinmez, çıkarıldı
olarak işaretlenir: `removed_at`, `removed_by` (kullanıcı adı), `removed_path` (veri köküne göreli
arşiv yolu). Çıkarılan örneğin adı klasörde yeniden kullanılabildiği için `(type_slug, name)`
tekilliği yalnız etkin kayıtlara daraltılır: tekil kısıt `uq_example_files_type_slug_name` düşer,
yerine `removed_at IS NULL` koşullu tekil dizin `uq_example_files_active_name` gelir (SQLite ve
PostgreSQL koşullu dizini destekler). Göç veri yazmaz: var olan kayıtlar etkindir. Geri alışta
çıkarılmış kayıt varsa aynı ad çakışabilir; geri alış yalnız temiz veritabanı içindir.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-26 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE = "removed_at IS NULL"


def upgrade() -> None:
    with op.batch_alter_table("example_files", schema=None) as batch_op:
        batch_op.add_column(sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("removed_by", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("removed_path", sa.String(length=512), nullable=True))
        batch_op.drop_constraint("uq_example_files_type_slug_name", type_="unique")
        batch_op.create_index(
            "uq_example_files_active_name",
            ["type_slug", "name"],
            unique=True,
            sqlite_where=sa.text(_ACTIVE),
            postgresql_where=sa.text(_ACTIVE),
        )


def downgrade() -> None:
    with op.batch_alter_table("example_files", schema=None) as batch_op:
        batch_op.drop_index("uq_example_files_active_name")
        batch_op.create_unique_constraint("uq_example_files_type_slug_name", ["type_slug", "name"])
        batch_op.drop_column("removed_path")
        batch_op.drop_column("removed_by")
        batch_op.drop_column("removed_at")
