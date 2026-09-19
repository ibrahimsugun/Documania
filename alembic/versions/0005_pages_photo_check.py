"""Fotoğraf türündeki sayfanın kural değerlendirmesi: `pages.photo_check_json` (11.7.1)

Profil fotoğrafı analizde kurallara göre değerlendirilir (her kural pass/fail/unsure); plan bu
kaydı okuyup `fail`'i Unresolved'a gönderir (K9: plan yapay zekâya yeniden sormaz). Değerlendirme
§8.4 sayfa analizinin parçası değildir, `analysis_json`'a konmaz; PRD §8.1 `pages` satırı bu alanı
saymaz (PLAN.md §C64). Var olan sayfalarda boş kalır.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-19 18:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("pages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("photo_check_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("pages", schema=None) as batch_op:
        batch_op.drop_column("photo_check_json")
