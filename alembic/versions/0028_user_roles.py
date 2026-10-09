"""Yetki seviyeleri: `users.role` = `root` | `hr` | `user`, en çok bir root (10.1.8, 10.1.9)

Tek rol `admin` kalkar (PLAN.md §D115 a): `Zvz` adlı kullanıcı `root` olur, öteki her `admin` `hr`
(İK) olur. Göç adla rol tahmin etmez: Kullanıcı (`user`) rolüne alma İK'nın panelden yapacağı iştir.
`Zvz` yoksa root açılmaz (temiz kurulumda `python -m app.web create-root`). `users.role` CHECK'i
üç değeri kabul eder; kısmi benzersiz indeks `uq_users_single_root` ikinci root'u reddeder.
SQLite'ta tablo yeniden kurulur, kısıtlar korunur. Geri alış her rolü `admin`'e çevirir; yalnız
geliştirme veritabanı içindir.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-09 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | Sequence[str] | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROOT_USERNAME = "Zvz"  # insan kararı 2026-10-09: tek root
_ROLE_CHECK = "ck_users_role"
_SINGLE_ROOT = "uq_users_single_root"
_IS_ROOT = "role = 'root'"


def upgrade() -> None:
    users = sa.table("users", sa.column("username", sa.String), sa.column("role", sa.String))
    op.execute(
        users.update()
        .where(users.c.username == ROOT_USERNAME, users.c.role == "admin")
        .values(role="root")
    )
    op.execute(users.update().where(users.c.role != "root").values(role="hr"))
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_check_constraint(batch_op.f(_ROLE_CHECK), "role IN ('root', 'hr', 'user')")
        batch_op.create_index(
            _SINGLE_ROOT,
            ["role"],
            unique=True,
            sqlite_where=sa.text(_IS_ROOT),
            postgresql_where=sa.text(_IS_ROOT),
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(_SINGLE_ROOT)
        batch_op.drop_constraint(batch_op.f(_ROLE_CHECK), type_="check")
    users = sa.table("users", sa.column("role", sa.String))
    op.execute(users.update().values(role="admin"))
