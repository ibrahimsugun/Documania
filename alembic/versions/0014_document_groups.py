"""Belge grupları: `document_groups`, `document_group_items` (14.1.1, 14.1.2)

İK bir süreç için gereken belgeleri (örn. Sırbistan iş başvurusu) grup olarak tanımlar (PLAN.md
§C89). `document_groups` grubu (ad, 00.4.2 sadeleştirmesiyle tekil `normalized_name`, açıklama,
oluşturan, arşiv alanları), `document_group_items` kalemini (sıra, eşleşme anahtarı `label` ya da
`type`, dosya etiketi ya da tür slug'ı, zorunlu/isteğe bağlı, not, kaldırılma alanları — §D64)
tutar. CHECK `match_target` eşleşme anahtarına göre `file_label` ile `type_slug`'dan tam birinin
dolu olmasını ister; `type_slug` katalog türüne bağlıdır. Göç veri yazmaz. Geri alışta iki tablo
düşer.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-28 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_groups")),
        sa.UniqueConstraint("normalized_name", name=op.f("uq_document_groups_normalized_name")),
    )
    op.create_table(
        "document_group_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("match_kind", sa.String(length=16), nullable=False),
        sa.Column("file_label", sa.String(length=255), nullable=True),
        sa.Column("type_slug", sa.String(length=64), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(length=120), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_by", sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            "match_kind IN ('label', 'type')", name=op.f("ck_document_group_items_match_kind")
        ),
        sa.CheckConstraint(
            "(match_kind = 'label' AND file_label IS NOT NULL AND type_slug IS NULL) OR "
            "(match_kind = 'type' AND type_slug IS NOT NULL AND file_label IS NULL)",
            name=op.f("ck_document_group_items_match_target"),
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["document_groups.id"],
            name=op.f("fk_document_group_items_group_id_document_groups"),
        ),
        sa.ForeignKeyConstraint(
            ["type_slug"],
            ["known_document_types.slug"],
            name=op.f("fk_document_group_items_type_slug_known_document_types"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_group_items")),
    )
    with op.batch_alter_table("document_group_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_document_group_items_group_id"), ["group_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("document_group_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_document_group_items_group_id"))
    op.drop_table("document_group_items")
    op.drop_table("document_groups")
