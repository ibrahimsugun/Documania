"""Ek profil alanları: anne adı, baba adı, doğum yeri, kişisel numara ve ülkesi (15.3.1)

`employees`'a beş boş olabilen sütun eklenir: `mother_name`, `father_name`, `place_of_birth`
(`String(255)`), `personal_number` (`String(64)`, olduğu gibi; 15.3.3) ve `personal_number_country`
(`String(8)`, ICAO/alfa-3 kodu). Pasaport numarası sütun değildir (`employee_identifiers`, PLAN.md
§D123 e). Alan gözlemlerinin CHECK'i (`employee_field_observations.field`) dört yeni alanı da
kabul eder; ülke numarayla birlikte `personal_number` adıyla gözlenir. Göç veri yazmaz: var olan
çalışanların yeni alanları boş kalır. SQLite'ta tablolar yeniden kurulur, kısıtlar korunur. Geri
alış yeni alanların gözlemlerini kaldırır (eski CHECK'e sığmazlar) ve sütunları düşürür; yalnız
geliştirme veritabanı içindir.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-23 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | Sequence[str] | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OBSERVATIONS = "employee_field_observations"
_FIELD_CHECK = "ck_employee_field_observations_field"
_OLD_FIELDS = (
    "given_names",
    "surname",
    "other_names",
    "original_script_name",
    "date_of_birth",
    "nationality",
)
_NEW_FIELDS = ("mother_name", "father_name", "place_of_birth", "personal_number")


def _field_check(fields: Sequence[str]) -> str:
    return "field IN ({})".format(", ".join(f"'{name}'" for name in fields))


def upgrade() -> None:
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.add_column(sa.Column("mother_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("father_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("place_of_birth", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("personal_number", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("personal_number_country", sa.String(length=8), nullable=True)
        )
    with op.batch_alter_table(_OBSERVATIONS, schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f(_FIELD_CHECK), type_="check")
        batch_op.create_check_constraint(
            batch_op.f(_FIELD_CHECK), _field_check(_OLD_FIELDS + _NEW_FIELDS)
        )


def downgrade() -> None:
    new_fields = ", ".join(f"'{name}'" for name in _NEW_FIELDS)
    op.execute(sa.text(f"DELETE FROM {_OBSERVATIONS} WHERE field IN ({new_fields})"))
    with op.batch_alter_table(_OBSERVATIONS, schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f(_FIELD_CHECK), type_="check")
        batch_op.create_check_constraint(batch_op.f(_FIELD_CHECK), _field_check(_OLD_FIELDS))
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.drop_column("personal_number_country")
        batch_op.drop_column("personal_number")
        batch_op.drop_column("place_of_birth")
        batch_op.drop_column("father_name")
        batch_op.drop_column("mother_name")
