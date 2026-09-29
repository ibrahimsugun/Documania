"""Profil alanı gözleminin kaynağı: `employee_field_observations.source`, `actor` (10.5.6)

İK'nın profil düzenlemesi (PLAN.md §C90-a) her değişen alan için `source=manual` gözlemi yazar:
belge kaynağı yoktur, `actor` düzenleyen kullanıcıdır. Bu yüzden `file_id` ve `page_index` boş
olabilir; `source` (`document`, `manual` — CHECK `source`) eklenir, var olan satırlar `document`
olur. CHECK `source_reference`: belge gözlemi kaynak sayfayı, öteki kaynaklar kullanıcıyı taşır.
Değer sütunu yine yoktur (CONVENTIONS §6). SQLite'ta tablo yeniden kurulur; CHECK ve tekillik
kısıtları korunur. Geri alış elle girilen gözlemleri kaldırır (kaynak sayfası olmadığı için eski
şemaya sığmazlar); yalnız geliştirme veritabanı içindir.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-29 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "employee_field_observations"
_SOURCE_REFERENCE = (
    "(source = 'document' AND file_id IS NOT NULL AND page_index IS NOT NULL) "
    "OR (source != 'document' AND actor IS NOT NULL)"
)


def upgrade() -> None:
    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("source", sa.String(length=16), server_default="document", nullable=False)
        )
        batch_op.add_column(sa.Column("actor", sa.String(length=255), nullable=True))
        batch_op.alter_column("file_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("page_index", existing_type=sa.Integer(), nullable=True)
        batch_op.create_check_constraint(
            batch_op.f("ck_employee_field_observations_source"),
            "source IN ('document', 'manual')",
        )
        batch_op.create_check_constraint(
            batch_op.f("ck_employee_field_observations_source_reference"), _SOURCE_REFERENCE
        )


def downgrade() -> None:
    op.execute(sa.text(f"DELETE FROM {_TABLE} WHERE source != 'document'"))
    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("ck_employee_field_observations_source_reference"), type_="check"
        )
        batch_op.drop_constraint(batch_op.f("ck_employee_field_observations_source"), type_="check")
        batch_op.alter_column("page_index", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("file_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("actor")
        batch_op.drop_column("source")
