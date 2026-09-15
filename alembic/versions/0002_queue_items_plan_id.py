"""Kuyruk kaydı plan sürümüne bağlanır: `queue_items.plan_id` (06.6.2, K18)

Plan öğesi kimlikleri (`i1`, `i2`…) partinin plan sürümleri arasında tekrar eder; yeniden analiz
(06.6.2) aynı partide yeni sürüm açtığı için öğeyi `upload_id` + `plan_item_id` artık tek başına
göstermez (PLAN.md §C5, §C35).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-15 16:21:42.020485
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("queue_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("plan_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_queue_items_plan_id"), ["plan_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_queue_items_plan_id_plans"), "plans", ["plan_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("queue_items", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_queue_items_plan_id_plans"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_queue_items_plan_id"))
        batch_op.drop_column("plan_id")
