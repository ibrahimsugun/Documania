"""Profil alt kayıtlarını kaldırma ve iletişim bilgisi ekleme (10.5.8)

İK çalışanın görülen isim yazımlarını (`employee_aliases`), belge numaralarını
(`employee_identifiers`) ve iletişim bilgilerini (`employee_contacts`) iki aşamalı onayla kaldırır
(PLAN.md §C90-c, §D61): satır silinmez (R11), `removed_at` (UTC) ve `removed_by` (kullanıcı adı)
dolar; kaldırılmış satır eşleştirmeye ve aramaya girmez, tek adımda geri alınır. Aynı değer
belgeden yeniden gelirse satır geri açılmaz; `seen_after_removal_at` dolar ve profil uyarır
(PLAN.md §D68). `employee_contacts.added_by` elle eklenen iletişim bilgisinin ekleyenidir.
Sütunların hepsi boş olabilir; göç veri yazmaz, var olan kayıtlar etkin kalır. Tekillik kısıtları
değişmez: kaldırılmış satır aynı değerin yeniden açılmasını zaten engeller.

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-29 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("employee_aliases", "employee_identifiers", "employee_contacts")
_REMOVAL_COLUMNS = ("removed_at", "removed_by", "seen_after_removal_at")


def upgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            if table == "employee_contacts":
                batch_op.add_column(sa.Column("added_by", sa.String(length=255), nullable=True))
            batch_op.add_column(sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.add_column(sa.Column("removed_by", sa.String(length=255), nullable=True))
            batch_op.add_column(
                sa.Column("seen_after_removal_at", sa.DateTime(timezone=True), nullable=True)
            )


def downgrade() -> None:
    for table in reversed(_TABLES):
        with op.batch_alter_table(table, schema=None) as batch_op:
            for column in reversed(_REMOVAL_COLUMNS):
                batch_op.drop_column(column)
            if table == "employee_contacts":
                batch_op.drop_column("added_by")
