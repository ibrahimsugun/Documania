"""Hazır şablonlar: `output_templates`, `output_template_maps`, `generated_documents`; erişim
logunun hedefi (15.1.1, 15.1.4, 15.2; PLAN.md §D123)

`output_templates` İK'nın hazır şablonunu (ad, tekil `normalized_name`, K8 `file_label`, açıklama,
veri köküne göreli dosya yolu, tekil SHA-256, sayfa sayısı, durum `draft`/`ready`/`archived`,
inceleme hatası, yükleyen, arşiv alanları), `output_template_maps` alan haritası sürümlerini (§8.7
JSON, model, `map_hash`, onay alanları; şablon başına sürüm tekil), `generated_documents`
üretilen belgeleri (çalışan, şablon, harita sürümü, yol, sıra, durum, alan adları, üreten, arşiv
alanları) tutar. `access_log.document_id` boş olabilir hâle gelir; `template_id` ve
`generated_document_id` eklenir, CHECK `target` üçünden tam birinin dolu olmasını ister (§D123
f). Göç veri yazmaz: var olan erişim satırlarının hepsi `document_id` taşır. Geri alışta üç tablo
ve iki sütun düşer; şablon ya da üretilen belge erişim satırları önce silinir (`document_id`
yeniden zorunlu olur) — yalnız geliştirme veritabanı içindir.

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-23 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | Sequence[str] | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACCESS_TARGET = (
    "(document_id IS NOT NULL AND template_id IS NULL AND generated_document_id IS NULL) OR "
    "(document_id IS NULL AND template_id IS NOT NULL AND generated_document_id IS NULL) OR "
    "(document_id IS NULL AND template_id IS NULL AND generated_document_id IS NOT NULL)"
)


def upgrade() -> None:
    op.create_table(
        "output_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("file_label", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("examine_error", sa.Text(), nullable=True),
        sa.Column("uploaded_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by", sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'ready', 'archived')", name=op.f("ck_output_templates_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_output_templates")),
        sa.UniqueConstraint("normalized_name", name=op.f("uq_output_templates_normalized_name")),
        sa.UniqueConstraint("sha256", name=op.f("uq_output_templates_sha256")),
    )
    op.create_table(
        "output_template_maps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("json", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("map_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["output_templates.id"],
            name=op.f("fk_output_template_maps_template_id_output_templates"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_output_template_maps")),
        sa.UniqueConstraint(
            "template_id", "version", name=op.f("uq_output_template_maps_template_id_version")
        ),
    )
    with op.batch_alter_table("output_template_maps", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_output_template_maps_template_id"), ["template_id"], unique=False
        )
    op.create_table(
        "generated_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.String(length=16), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("map_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=True),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("filled_fields_json", sa.JSON(), nullable=False),
        sa.Column("missing_fields_json", sa.JSON(), nullable=False),
        sa.Column("generated_by", sa.String(length=255), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by", sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'superseded', 'archived', 'deleted')",
            name=op.f("ck_generated_documents_status"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name=op.f("fk_generated_documents_employee_id_employees"),
        ),
        sa.ForeignKeyConstraint(
            ["map_id"],
            ["output_template_maps.id"],
            name=op.f("fk_generated_documents_map_id_output_template_maps"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["output_templates.id"],
            name=op.f("fk_generated_documents_template_id_output_templates"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generated_documents")),
    )
    with op.batch_alter_table("generated_documents", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_generated_documents_employee_id"), ["employee_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_generated_documents_template_id"), ["template_id"], unique=False
        )
    with op.batch_alter_table("access_log", schema=None) as batch_op:
        batch_op.alter_column("document_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column("template_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("generated_document_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_access_log_template_id_output_templates"),
            "output_templates",
            ["template_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_access_log_generated_document_id_generated_documents"),
            "generated_documents",
            ["generated_document_id"],
            ["id"],
        )
        batch_op.create_index(batch_op.f("ix_access_log_template_id"), ["template_id"])
        batch_op.create_index(
            batch_op.f("ix_access_log_generated_document_id"), ["generated_document_id"]
        )
        batch_op.create_check_constraint(batch_op.f("ck_access_log_target"), _ACCESS_TARGET)


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM access_log WHERE document_id IS NULL"))
    with op.batch_alter_table("access_log", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_access_log_target"), type_="check")
        batch_op.drop_index(batch_op.f("ix_access_log_generated_document_id"))
        batch_op.drop_index(batch_op.f("ix_access_log_template_id"))
        batch_op.drop_constraint(
            batch_op.f("fk_access_log_generated_document_id_generated_documents"),
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            batch_op.f("fk_access_log_template_id_output_templates"), type_="foreignkey"
        )
        batch_op.drop_column("generated_document_id")
        batch_op.drop_column("template_id")
        batch_op.alter_column("document_id", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("generated_documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_generated_documents_template_id"))
        batch_op.drop_index(batch_op.f("ix_generated_documents_employee_id"))
    op.drop_table("generated_documents")
    with op.batch_alter_table("output_template_maps", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_output_template_maps_template_id"))
    op.drop_table("output_template_maps")
    op.drop_table("output_templates")
