"""Pasif çalışanı kalıcı silme: `deleted_at`, `deleted_by`, durum CHECK'i (10.5.13)

Kalıcı silinen çalışan satır olarak kalır (olaylar, erişim logu, yüklemenin bağlam çalışanı ve
belge iskeletleri ona bağlıdır; K15) ve `deleted` iskeletine döner: kişisel sütunlar boşalır,
`folder_name` `deleted_<E>` olur, silme anı ve kullanıcısı yazılır (PLAN.md §D110 a). `status`
artık CHECK'lidir: `active`, `inactive`, `merged`, `deleted`. Göç veri yazmaz; var olan çalışanların
silme alanları boş kalır. SQLite'ta tablo yeniden kurulur, kısıtlar korunur. Geri alış silinmiş
çalışan varken yapılamaz (`deleted` eski kısıtsız şemaya sığar ama hiçbir kod onu tanımaz); yalnız
geliştirme veritabanı içindir.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-09 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("deleted_by", sa.String(length=255), nullable=True))
        batch_op.create_check_constraint(
            op.f("ck_employees_status"),
            "status IN ('active', 'inactive', 'merged', 'deleted')",
        )


def downgrade() -> None:
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_employees_status"), type_="check")
        batch_op.drop_column("deleted_by")
        batch_op.drop_column("deleted_at")
