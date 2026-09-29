"""Belge türünü arşivleme: `known_document_types.archived_at`, `archived_by` (11.1.6)

İK bir türü iki aşamalı onayla arşivler (PLAN.md §C92-a, §D61-d): satır silinmez (R11),
`archived_at` (UTC) ve `archived_by` (kullanıcı adı) dolar; arşivli tür listeden, analiz
talimatından, tür seçicilerden ve eğitim modunun bilinen türlerinden kalkar, o türe bağlı belgeler
yerinde kalır. Geri alma iki sütunu boşaltır. İki sütun da boş olabilir; göç veri yazmaz, var olan
türler arşivsiz kalır.

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-29 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("known_document_types", schema=None) as batch_op:
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("archived_by", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("known_document_types", schema=None) as batch_op:
        batch_op.drop_column("archived_by")
        batch_op.drop_column("archived_at")
