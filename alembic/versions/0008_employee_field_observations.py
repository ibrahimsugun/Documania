"""Profil alanlarının belge gözlemleri: `employee_field_observations` (05.7.3)

Eşleşen ya da yeni açılan çalışanın boş profil alanı belgede okunan değerle dolar; dolu alan
değişmez, farklı değer profilde uyarı olur. Her alanın hangi belgede görüldüğü ve sonucu
(`filled`/`same`/`conflict`) bu tabloda durur — değer tutulmaz (PLAN.md §C82). PRD §8.1 tablo
listesinde yok; bu tablo o gereksinimin deposudur. Göç veri yazmaz: geçmiş belgeler yönetici
komutuyla işlenir (`python -m app.profiles fill-fields`).

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-22 02:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "employee_field_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.String(length=16), nullable=False),
        sa.Column("field", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("page_index", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "field IN ('given_names', 'surname', 'other_names', 'original_script_name', "
            "'date_of_birth', 'nationality')",
            name=op.f("ck_employee_field_observations_field"),
        ),
        sa.CheckConstraint(
            "outcome IN ('filled', 'same', 'conflict')",
            name=op.f("ck_employee_field_observations_outcome"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name=op.f("fk_employee_field_observations_employee_id_employees"),
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["upload_files.id"],
            name=op.f("fk_employee_field_observations_file_id_upload_files"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employee_field_observations")),
        sa.UniqueConstraint(
            "employee_id",
            "field",
            "file_id",
            "page_index",
            name="uq_employee_field_observations_source",
        ),
    )
    with op.batch_alter_table("employee_field_observations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_employee_field_observations_employee_id"), ["employee_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("employee_field_observations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_employee_field_observations_employee_id"))

    op.drop_table("employee_field_observations")
