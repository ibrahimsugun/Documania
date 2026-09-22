"""Taramayı yoksay: `uploads.dismissed_at`/`dismissed_by`, `queue_items.resolution` (10.3.4)

İK son durumdaki bir partiyi iki aşamalı onayla yoksayar (K16'nın altıncı manuel işlemi, PLAN.md
§C80, §D50): parti yükleme listesinden ve kuyruklardan kalkar, dosyası, olayı ve çıktısı yerinde
durur. Yoksayma anı ve kullanıcısı partide durur; partinin çözülmemiş kuyruk öğeleri çözülür ve
çözüm nedeni `resolution = 'dismissed'` olur (`QueueResolution`). Göç veri yazmaz: var olan parti
yoksayılmamış, var olan çözülmüş öğe nedensiz sayılır. Geri alışta üç sütun düşer.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-22 16:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("uploads", schema=None) as batch_op:
        batch_op.add_column(sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("dismissed_by", sa.String(length=255), nullable=True))

    with op.batch_alter_table("queue_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("resolution", sa.String(length=16), nullable=True))
        batch_op.create_check_constraint(
            op.f("ck_queue_items_resolution"), "resolution IN ('dismissed')"
        )


def downgrade() -> None:
    with op.batch_alter_table("queue_items", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_queue_items_resolution"), type_="check")
        batch_op.drop_column("resolution")

    with op.batch_alter_table("uploads", schema=None) as batch_op:
        batch_op.drop_column("dismissed_by")
        batch_op.drop_column("dismissed_at")
