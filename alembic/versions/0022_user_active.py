"""Panel kullanıcısını pasife alma: `users.active` (10.1.4)

Kullanıcı silinmez (R11); yönetici "Kullanıcılar" sayfasında kullanıcıyı pasife alır ve yeniden
etkinleştirir (PLAN.md §C92-d). Sütun boş olamaz, varsayılanı `true`'dur: var olan kullanıcılar
etkin kalır. Göç veri yazmaz. Geri alış sütunu düşürür; yalnız geliştirme veritabanı içindir.

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-29 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("active")
