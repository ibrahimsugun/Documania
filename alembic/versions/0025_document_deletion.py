"""Belgeyi kalıcı silme: `deleted_at`, `deleted_by`, boş olabilen `path`, durum CHECK'i (10.5.12)

Kalıcı silinen belge satır olarak kalır (olay, erişim logu, kimlik kaydı ona bağlıdır; K15) ve
`deleted` iskeletine döner: dosya yolu boşalır (ad kişi adı taşır, K8), silme anı ve kullanıcısı
yazılır (PLAN.md §D110 a). `status` artık CHECK'lidir: `active`, `superseded`, `archived`,
`deleted`. Göç veri yazmaz; var olan belgelerin yolu dolu, silme alanları boş kalır. SQLite'ta tablo
yeniden kurulur, kısıtlar korunur. Geri alış silinmiş belge varken yapılamaz (yolu boş satır eski
şemaya sığmaz); yalnız geliştirme veritabanı içindir.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-08 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.alter_column("path", existing_type=sa.String(length=1024), nullable=True)
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("deleted_by", sa.String(length=255), nullable=True))
        batch_op.create_check_constraint(
            op.f("ck_documents_status"),
            "status IN ('active', 'superseded', 'archived', 'deleted')",
        )


def downgrade() -> None:
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_documents_status"), type_="check")
        batch_op.drop_column("deleted_by")
        batch_op.drop_column("deleted_at")
        batch_op.alter_column("path", existing_type=sa.String(length=1024), nullable=False)
