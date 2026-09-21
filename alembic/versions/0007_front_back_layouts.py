"""`front_back` türün kabul ettiği düzenler: `known_document_types.front_back_layouts` (04.1.2)

Ön ve arka yüzlü belge iki ayrı sayfada (`separate`) da, iki yüzü tek sayfaya konmuş (`combined`)
da gelebilir; tür hangi düzenleri kabul ettiğini bu sütunda taşır (PRD §8.6, PLAN.md §C78). Tek
yüzlü türde liste boştur. `front_back` türün sayfa aralığı düzenlerden türetilir (yalnız `separate`
2–2, yalnız `combined` 1–1, ikisi 1–2): göç anında var olan her `front_back` tür iki düzeni de
kabul eder ve aralığı 1–2 olur. Geri alışta sütun düşer; türetilmiş aralık geri yazılmaz (eski
aralık bilinmez, eski sürüm aralığı denetlemez).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-21 21:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPES = sa.table(
    "known_document_types",
    sa.column("sides", sa.String()),
    sa.column("front_back_layouts", sa.JSON()),
    sa.column("expected_pages_min", sa.Integer()),
    sa.column("expected_pages_max", sa.Integer()),
)


def upgrade() -> None:
    with op.batch_alter_table("known_document_types", schema=None) as batch_op:
        batch_op.add_column(sa.Column("front_back_layouts", sa.JSON(), nullable=True))

    op.execute(
        _TYPES.update()
        .where(_TYPES.c.sides == "front_back")
        .values(
            front_back_layouts=["separate", "combined"],
            expected_pages_min=1,
            expected_pages_max=2,
        )
    )
    op.execute(_TYPES.update().where(_TYPES.c.sides != "front_back").values(front_back_layouts=[]))

    with op.batch_alter_table("known_document_types", schema=None) as batch_op:
        batch_op.alter_column("front_back_layouts", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("known_document_types", schema=None) as batch_op:
        batch_op.drop_column("front_back_layouts")
