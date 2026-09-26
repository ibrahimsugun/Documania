"""Eğitim modu: `training_runs`, `training_items`, `example_files` (11.9)

Eğitim modu yalnız bilinen belgelerin örneklerini besler (PLAN.md §C86): yüklenen dosya
`KnownDocuments/_egitim/gelen/<run>/<item>.<ext>`'e yazılır, bilinen bir türe yerleşirse
`examples/<slug>/`'a kopyalanır. `training_runs` çalıştırmayı (tür `upload`/`map`, durum
`running`/`done`, durumlara göre sayaçlar), `training_items` işlenen dosyayı (yol, SHA-256, ipucu ve
sonuç türü, yöntem, durum, not, kontroller, karar), `example_files` örnek dosyasının kaydını
(`(type_slug, name)` tekil, türler arası tekrar tespiti için `sha256` dizinli, yöntem ve etiket)
tutar. `example_files.type_slug` katalog dışı önerilen tür olabildiği için katalog tablosuna
bağlanmaz. Göç veri yazmaz: klasörde duran örnekler kayıtsız ve etiketsiz kalır. Geri alışta üç
tablo düşer.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-26 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "training_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("map_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("counts_json", sa.JSON(), nullable=False),
        sa.CheckConstraint("kind IN ('upload', 'map')", name=op.f("ck_training_runs_kind")),
        sa.CheckConstraint("status IN ('running', 'done')", name=op.f("ck_training_runs_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_training_runs")),
    )
    op.create_table(
        "training_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("source_ref", sa.String(length=1024), nullable=True),
        sa.Column("staged_path", sa.String(length=1024), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("file_kind", sa.String(length=16), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("hint_slug", sa.String(length=64), nullable=True),
        sa.Column("result_slug", sa.String(length=64), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("checks_json", sa.JSON(), nullable=True),
        sa.Column("decided_by", sa.String(length=255), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "method IN ('mechanical', 'ai', 'manual')", name=op.f("ck_training_items_method")
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'placed', 'ai_pending', 'skipped', 'failed', 'unplaced', "
            "'conflict', 'review')",
            name=op.f("ck_training_items_status"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["training_runs.id"], name=op.f("fk_training_items_run_id_training_runs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_training_items")),
    )
    with op.batch_alter_table("training_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_training_items_run_id"), ["run_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_training_items_sha256"), ["sha256"], unique=False)
        batch_op.create_index(batch_op.f("ix_training_items_status"), ["status"], unique=False)

    op.create_table(
        "example_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type_slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=16), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("training_item_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "label IN ('ai_decision', 'verified')", name=op.f("ck_example_files_label")
        ),
        sa.CheckConstraint(
            "method IN ('mechanical', 'ai', 'manual', 'legacy')",
            name=op.f("ck_example_files_method"),
        ),
        sa.ForeignKeyConstraint(
            ["training_item_id"],
            ["training_items.id"],
            name=op.f("fk_example_files_training_item_id_training_items"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_example_files")),
        sa.UniqueConstraint("type_slug", "name", name=op.f("uq_example_files_type_slug_name")),
    )
    with op.batch_alter_table("example_files", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_example_files_sha256"), ["sha256"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("example_files", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_example_files_sha256"))

    op.drop_table("example_files")
    with op.batch_alter_table("training_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_training_items_status"))
        batch_op.drop_index(batch_op.f("ix_training_items_sha256"))
        batch_op.drop_index(batch_op.f("ix_training_items_run_id"))

    op.drop_table("training_items")
    op.drop_table("training_runs")
