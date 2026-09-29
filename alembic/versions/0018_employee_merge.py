"""İki çalışanı birleştirme: `employees.merged_into_id`, gözlem kaynağı `merge` (10.5.9)

Birleştirilen çalışan (`status = merged`, PLAN.md §C90-d) kalan kaydın numarasını
`merged_into_id`'de taşır (FK `employees.id`, boş olabilir; öteki durumlarda boş). Kalan kaydın
boş profil alanı birleşenin dolu alanıyla dolunca `employee_field_observations`'a `source=merge`
satırı yazılır (kullanıcı `actor`, belge kaynağı yok): CHECK `source` `merge`'ü de kabul eder.
Göç veri yazmaz; var olan çalışanlar birleştirilmemiş kalır. SQLite'ta tablolar yeniden kurulur,
kısıtlar korunur. Geri alış birleştirme gözlemlerini kaldırır (eski CHECK'e sığmazlar); yalnız
geliştirme veritabanı içindir.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-29 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OBSERVATIONS = "employee_field_observations"
_SOURCE_CHECK = "ck_employee_field_observations_source"


def upgrade() -> None:
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.add_column(sa.Column("merged_into_id", sa.String(length=16), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_employees_merged_into_id_employees"),
            "employees",
            ["merged_into_id"],
            ["id"],
        )
    with op.batch_alter_table(_OBSERVATIONS, schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f(_SOURCE_CHECK), type_="check")
        batch_op.create_check_constraint(
            batch_op.f(_SOURCE_CHECK), "source IN ('document', 'manual', 'merge')"
        )


def downgrade() -> None:
    op.execute(sa.text(f"DELETE FROM {_OBSERVATIONS} WHERE source = 'merge'"))
    with op.batch_alter_table(_OBSERVATIONS, schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f(_SOURCE_CHECK), type_="check")
        batch_op.create_check_constraint(
            batch_op.f(_SOURCE_CHECK), "source IN ('document', 'manual')"
        )
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_employees_merged_into_id_employees"), type_="foreignkey"
        )
        batch_op.drop_column("merged_into_id")
