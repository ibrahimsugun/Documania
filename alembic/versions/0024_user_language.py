"""Panel kullanıcısının arayüz dili tercihi: `users.language` (10.10.2)

Kullanıcı dil seçicide dil seçince tercih hesabına yazılır, her girişte panel o dilde açılır
(PLAN.md §D92 c, d). Sütun boş olabilir: boş = tercih yok, panel varsayılan dilde (İngilizce)
açılır; var olan kullanıcılar boş kalır. Değer `en`, `tr` ya da `sr` (CHECK). Göç veri yazmaz.
Geri alış sütunu ve kısıtı düşürür; yalnız geliştirme veritabanı içindir.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-02 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("language", sa.String(length=8), nullable=True))
        batch_op.create_check_constraint(
            op.f("ck_users_language"), "language IN ('en', 'tr', 'sr')"
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_users_language"), type_="check")
        batch_op.drop_column("language")
