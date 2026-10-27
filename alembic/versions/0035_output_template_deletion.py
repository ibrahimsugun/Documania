"""Arşivdeki şablonu kalıcı silme: `output_templates.status` = `deleted`, silme alanları (15.1.5)

PLAN.md §D134 c: arşivdeki ve üretilmiş belgesi olmayan şablonun dosyaları ve alan haritası silinir,
satırı iskelet olarak kalır (erişim logu `access_log.template_id` ona bağlıdır ve silinmez, 10.9.2):
`status` CHECK'i `deleted`'ı da kabul eder, `deleted_at` (UTC) ve `deleted_by` boş olabilir. Göç
veri yazmaz. SQLite'ta tablo yeniden kurulur, kısıtlar ve dizinler korunur. Geri alış silinmiş
iskeletleri `archived`'a döndürür (eski CHECK'e sığmaz; dosyaları yoktur) ve sütunları düşürür;
yalnız geliştirme veritabanı içindir.

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-27 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | Sequence[str] | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_CHECK = "ck_output_templates_status"
_STATUSES = "'draft', 'ready', 'archived'"


def upgrade() -> None:
    with op.batch_alter_table("output_templates", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f(_STATUS_CHECK), type_="check")
        batch_op.create_check_constraint(
            batch_op.f(_STATUS_CHECK), f"status IN ({_STATUSES}, 'deleted')"
        )
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("deleted_by", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.execute(sa.text("UPDATE output_templates SET status = 'archived' WHERE status = 'deleted'"))
    with op.batch_alter_table("output_templates", schema=None) as batch_op:
        batch_op.drop_column("deleted_by")
        batch_op.drop_column("deleted_at")
        batch_op.drop_constraint(batch_op.f(_STATUS_CHECK), type_="check")
        batch_op.create_check_constraint(batch_op.f(_STATUS_CHECK), f"status IN ({_STATUSES})")
