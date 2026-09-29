"""Eğitim temizliği: `dismissed` öğe durumu, `training_runs.archived_at` (11.9.6)

İK yerleşemeyen eğitim öğesini (`unplaced`, `conflict`, `review`) tek adımda yoksayar ve geri alır;
çalıştırmayı arşivler ve geri alır (PLAN.md §C92-c, §D61-b): `training_items.status` CHECK'i
`dismissed`'i de kabul eder, `training_runs.archived_at` (UTC) boş olabilir. Hiçbir satır silinmez
(R11); göç veri yazmaz: var olan öğeler ve çalıştırmalar olduğu gibi kalır. SQLite'ta tablolar
yeniden kurulur, kısıtlar ve dizinler korunur. Geri alış yoksayılmış öğeleri `unplaced`'e döndürür
(eski CHECK'e sığmaz; yoksaymanın geri alınmasıyla aynı son) ve sütunu düşürür; yalnız geliştirme
veritabanı içindir.

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-29 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_CHECK = "ck_training_items_status"
_STATUSES = (
    "'queued', 'placed', 'ai_pending', 'skipped', 'failed', 'unplaced', 'conflict', 'review'"
)


def upgrade() -> None:
    with op.batch_alter_table("training_items", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f(_STATUS_CHECK), type_="check")
        batch_op.create_check_constraint(
            batch_op.f(_STATUS_CHECK), f"status IN ({_STATUSES}, 'dismissed')"
        )
    with op.batch_alter_table("training_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.execute(sa.text("UPDATE training_items SET status = 'unplaced' WHERE status = 'dismissed'"))
    with op.batch_alter_table("training_runs", schema=None) as batch_op:
        batch_op.drop_column("archived_at")
    with op.batch_alter_table("training_items", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f(_STATUS_CHECK), type_="check")
        batch_op.create_check_constraint(batch_op.f(_STATUS_CHECK), f"status IN ({_STATUSES})")
