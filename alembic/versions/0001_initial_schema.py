"""İlk şema: PRD §8.1 tabloları (00.3.1, 00.3.2)

Revision ID: 0001
Revises:
Create Date: 2026-09-14 01:27:14.983343
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.String(length=16), nullable=False),
        sa.Column("folder_name", sa.String(length=255), nullable=False),
        sa.Column("given_names", sa.String(length=255), nullable=False),
        sa.Column("surname", sa.String(length=255), nullable=False),
        sa.Column("other_names", sa.String(length=255), nullable=True),
        sa.Column("original_script_name", sa.String(length=255), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("nationality", sa.String(length=8), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employees")),
        sa.UniqueConstraint("folder_name", name=op.f("uq_employees_folder_name")),
    )
    op.create_table(
        "known_document_types",
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("file_label", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=8), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("expected_file_types", sa.JSON(), nullable=False),
        sa.Column("expected_pages_min", sa.Integer(), nullable=True),
        sa.Column("expected_pages_max", sa.Integer(), nullable=True),
        sa.Column("sides", sa.String(length=16), nullable=False),
        sa.Column("direct", sa.Boolean(), nullable=False),
        sa.Column("analyze", sa.Boolean(), nullable=False),
        sa.Column("required_fields", sa.JSON(), nullable=False),
        sa.Column("allowed_conversions", sa.JSON(), nullable=False),
        sa.Column("output_format", sa.String(length=16), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("prompt_description", sa.Text(), nullable=True),
        sa.Column("photo_rules", sa.JSON(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("slug", name=op.f("pk_known_document_types")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=150), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_table(
        "employee_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.String(length=16), nullable=False),
        sa.Column("raw_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("script", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name=op.f("fk_employee_aliases_employee_id_employees"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employee_aliases")),
        sa.UniqueConstraint(
            "employee_id", "raw_name", name=op.f("uq_employee_aliases_employee_id_raw_name")
        ),
    )
    op.create_index(op.f("ix_employee_aliases_employee_id"), "employee_aliases", ["employee_id"])
    op.create_index(
        op.f("ix_employee_aliases_normalized_name"), "employee_aliases", ["normalized_name"]
    )
    op.create_table(
        "telegram_users",
        sa.Column("telegram_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_telegram_users_user_id_users")
        ),
        sa.PrimaryKeyConstraint("telegram_id", name=op.f("pk_telegram_users")),
    )
    op.create_index(op.f("ix_telegram_users_user_id"), "telegram_users", ["user_id"])
    op.create_table(
        "uploads",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("uploaded_by", sa.String(length=255), nullable=True),
        sa.Column("context_employee_id", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('received', 'rendering', 'analyzing', 'planning', 'executing', "
            "'done', 'partial', 'failed')",
            name=op.f("ck_uploads_status"),
        ),
        sa.ForeignKeyConstraint(
            ["context_employee_id"],
            ["employees.id"],
            name=op.f("fk_uploads_context_employee_id_employees"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_uploads")),
    )
    op.create_table(
        "candidate_document_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("proposed_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("first_seen_upload_id", sa.String(length=32), nullable=False),
        sa.Column("sample_page_ids", sa.JSON(), nullable=False),
        sa.Column("seen_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["first_seen_upload_id"],
            ["uploads.id"],
            name=op.f("fk_candidate_document_types_first_seen_upload_id_uploads"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_document_types")),
        sa.UniqueConstraint(
            "normalized_name", name=op.f("uq_candidate_document_types_normalized_name")
        ),
    )
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("upload_id", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("json", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("plan_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["upload_id"], ["uploads.id"], name=op.f("fk_plans_upload_id_uploads")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plans")),
        sa.UniqueConstraint("upload_id", "version", name=op.f("uq_plans_upload_id_version")),
    )
    op.create_table(
        "queue_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("upload_id", sa.String(length=32), nullable=False),
        sa.Column("plan_item_id", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            "kind IN ('unknown', 'unreadable', 'unresolved')", name=op.f("ck_queue_items_kind")
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"], ["uploads.id"], name=op.f("fk_queue_items_upload_id_uploads")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_queue_items")),
    )
    op.create_index(op.f("ix_queue_items_upload_id"), "queue_items", ["upload_id"])
    op.create_table(
        "upload_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("upload_id", sa.String(length=32), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=1024), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mime", sa.String(length=127), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("is_duplicate_of", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["is_duplicate_of"],
            ["upload_files.id"],
            name=op.f("fk_upload_files_is_duplicate_of_upload_files"),
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"], ["uploads.id"], name=op.f("fk_upload_files_upload_id_uploads")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_upload_files")),
    )
    op.create_index(op.f("ix_upload_files_sha256"), "upload_files", ["sha256"])
    op.create_index(op.f("ix_upload_files_upload_id"), "upload_files", ["upload_id"])
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.String(length=16), nullable=False),
        sa.Column("type_slug", sa.String(length=64), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("source_refs_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name=op.f("fk_documents_employee_id_employees")
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], name=op.f("fk_documents_plan_id_plans")),
        sa.ForeignKeyConstraint(
            ["type_slug"],
            ["known_document_types.slug"],
            name=op.f("fk_documents_type_slug_known_document_types"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
    )
    op.create_index(op.f("ix_documents_employee_id"), "documents", ["employee_id"])
    op.create_table(
        "pages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("image_path", sa.String(length=1024), nullable=True),
        sa.Column("text_layer", sa.Text(), nullable=True),
        sa.Column("is_blank", sa.Boolean(), nullable=False),
        sa.Column("has_single_embedded_image", sa.Boolean(), nullable=False),
        sa.Column("analysis_json", sa.JSON(), nullable=True),
        sa.Column("analysis_status", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["file_id"], ["upload_files.id"], name=op.f("fk_pages_file_id_upload_files")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pages")),
        sa.UniqueConstraint("file_id", "index", name=op.f("uq_pages_file_id_index")),
    )
    op.create_table(
        "access_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name=op.f("fk_access_log_document_id_documents")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_access_log_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_log")),
    )
    op.create_index(op.f("ix_access_log_document_id"), "access_log", ["document_id"])
    op.create_index(op.f("ix_access_log_user_id"), "access_log", ["user_id"])
    op.create_table(
        "employee_contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('phone', 'email', 'address')", name=op.f("ck_employee_contacts_kind")
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name=op.f("fk_employee_contacts_employee_id_employees"),
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["documents.id"],
            name=op.f("fk_employee_contacts_source_document_id_documents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employee_contacts")),
    )
    op.create_index(op.f("ix_employee_contacts_employee_id"), "employee_contacts", ["employee_id"])
    op.create_table(
        "employee_identifiers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=128), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name=op.f("fk_employee_identifiers_employee_id_employees"),
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["documents.id"],
            name=op.f("fk_employee_identifiers_source_document_id_documents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employee_identifiers")),
        sa.UniqueConstraint(
            "employee_id",
            "kind",
            "value",
            name=op.f("uq_employee_identifiers_employee_id_kind_value"),
        ),
    )
    op.create_index(
        op.f("ix_employee_identifiers_employee_id"), "employee_identifiers", ["employee_id"]
    )
    op.create_index(op.f("ix_employee_identifiers_value"), "employee_identifiers", ["value"])
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("upload_id", sa.String(length=32), nullable=True),
        sa.Column("file_id", sa.Integer(), nullable=True),
        sa.Column("page_index", sa.Integer(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("employee_id", sa.String(length=16), nullable=True),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("data_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name=op.f("fk_events_document_id_documents")
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name=op.f("fk_events_employee_id_employees")
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["upload_files.id"], name=op.f("fk_events_file_id_upload_files")
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"], ["uploads.id"], name=op.f("fk_events_upload_id_uploads")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index(op.f("ix_events_document_id"), "events", ["document_id"])
    op.create_index(op.f("ix_events_employee_id"), "events", ["employee_id"])
    op.create_index(op.f("ix_events_ts"), "events", ["ts"])
    op.create_index(op.f("ix_events_type"), "events", ["type"])
    op.create_index(op.f("ix_events_upload_id"), "events", ["upload_id"])


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("employee_identifiers")
    op.drop_table("employee_contacts")
    op.drop_table("access_log")
    op.drop_table("pages")
    op.drop_table("documents")
    op.drop_table("upload_files")
    op.drop_table("queue_items")
    op.drop_table("plans")
    op.drop_table("candidate_document_types")
    op.drop_table("uploads")
    op.drop_table("telegram_users")
    op.drop_table("employee_aliases")
    op.drop_table("users")
    op.drop_table("known_document_types")
    op.drop_table("employees")
