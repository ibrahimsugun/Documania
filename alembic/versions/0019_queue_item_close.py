"""Kuyruk öğesini kapatma: `closed` çözümü, `resolution_reason`, `resolution_note` (10.7.4)

İK bekleyen bir kuyruk öğesini iki aşamalı onayla, gerekçeyle kapatır (K16, PLAN.md §C91, §D61):
öğe çözülmüş sayılır (`resolved_at`/`resolved_by`), çözüm nedeni `resolution = 'closed'` olur
(CHECK `closed`'u da kabul eder), gerekçe kodu `resolution_reason`'a (`not_a_document`,
`already_exists`, `other`; CHECK'li) ve isteğe bağlı not `resolution_note`'a (≤ 200) yazılır. Göç
veri yazmaz: var olan öğeler kapatılmamış kalır. SQLite'ta tablo yeniden kurulur, kısıtlar korunur.
Geri alış kapatılmış öğelerin nedenini boşaltır (eski CHECK'e sığmaz; öğe çözülmüş kalır) ve iki
sütunu düşürür; yalnız geliştirme veritabanı içindir.

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-29 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RESOLUTION_CHECK = "ck_queue_items_resolution"
_REASON_CHECK = "ck_queue_items_resolution_reason"


def upgrade() -> None:
    with op.batch_alter_table("queue_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("resolution_reason", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("resolution_note", sa.String(length=200), nullable=True))
        batch_op.drop_constraint(batch_op.f(_RESOLUTION_CHECK), type_="check")
        batch_op.create_check_constraint(
            batch_op.f(_RESOLUTION_CHECK), "resolution IN ('dismissed', 'closed')"
        )
        batch_op.create_check_constraint(
            batch_op.f(_REASON_CHECK),
            "resolution_reason IN ('not_a_document', 'already_exists', 'other')",
        )


def downgrade() -> None:
    op.execute(sa.text("UPDATE queue_items SET resolution = NULL WHERE resolution = 'closed'"))
    with op.batch_alter_table("queue_items", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f(_REASON_CHECK), type_="check")
        batch_op.drop_constraint(batch_op.f(_RESOLUTION_CHECK), type_="check")
        batch_op.create_check_constraint(
            batch_op.f(_RESOLUTION_CHECK), "resolution IN ('dismissed')"
        )
        batch_op.drop_column("resolution_note")
        batch_op.drop_column("resolution_reason")
