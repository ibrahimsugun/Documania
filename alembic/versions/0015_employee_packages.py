"""Çalışanın belge paketleri: `employee_packages` (14.2.1–14.2.3, 14.3.1)

İK bir belge grubunu (0014) çalışana paket olarak tanımlar (PLAN.md §C89). Satır çalışanı, grubu,
durumu (`open`, `completed`, `cancelled` — CHECK `status`), tanımlayan kullanıcı ve zamanı,
tamamlanma ve iptal zamanlarını, tanımlama notunu ve iptal nedenini (`cancel_note`, PLAN.md §D65)
tutar. Kalem tikleri yazılmaz, belgelerden hesaplanır. Göç veri yazmaz. Geri alışta tablo düşer.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-29 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "employee_packages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.String(length=16), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.String(length=255), nullable=True),
        sa.Column("note", sa.String(length=120), nullable=True),
        sa.Column("cancel_note", sa.String(length=120), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'completed', 'cancelled')",
            name=op.f("ck_employee_packages_status"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name=op.f("fk_employee_packages_employee_id_employees"),
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["document_groups.id"],
            name=op.f("fk_employee_packages_group_id_document_groups"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employee_packages")),
    )
    with op.batch_alter_table("employee_packages", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_employee_packages_employee_id"), ["employee_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_employee_packages_group_id"), ["group_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("employee_packages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_employee_packages_group_id"))
        batch_op.drop_index(batch_op.f("ix_employee_packages_employee_id"))
    op.drop_table("employee_packages")
