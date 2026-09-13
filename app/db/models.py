"""Veri modeli — PRD §8.1 tabloları (00.3.1) ve çalışan numarası üretici (00.3.3).

Silme yoktur, arşiv vardır (K16): ilişkilerde silme kaskadı tanımlanmaz.
Dosya yolu burada üretilmez (yol kuralı: `app/storage/`); yol sütunları yalnız saklar.
Şema değişikliği yalnız Alembic göçüyle yapılır (`alembic/versions/`).
"""

from __future__ import annotations

import enum
import zlib
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Dialect,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    cast,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

# Kısıt adları iki motorda da aynı ve öngörülebilir olsun (Alembic batch göçleri ada dayanır).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    return datetime.now(UTC)


class UtcDateTime(TypeDecorator[datetime]):
    """Zaman damgası: yalnız saat dilimli değer kabul eder, UTC saklar ve UTC döndürür.

    SQLite saat dilimi saklamaz; bu tip iki motorda da aynı (UTC, saat dilimli) değeri
    döndürerek NFR-05'i korur.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Saat dilimsiz zaman damgası saklanmaz; UTC değeri verin.")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def _one_of(column: str, values: type[enum.StrEnum]) -> str:
    allowed = ", ".join(f"'{member.value}'" for member in values)
    return f"{column} IN ({allowed})"


class UploadStatus(enum.StrEnum):
    """Parti durum makinesi (PRD 09.2.1)."""

    RECEIVED = "received"
    RENDERING = "rendering"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    EXECUTING = "executing"
    DONE = "done"
    PARTIAL = "partial"
    FAILED = "failed"


class ContactKind(enum.StrEnum):
    """İletişim bilgisi türü (PRD §8.1 `employee_contacts.kind`)."""

    PHONE = "phone"
    EMAIL = "email"
    ADDRESS = "address"


class QueueKind(enum.StrEnum):
    """Kuyruk türü: Plan JSON `route` değerlerinden kuyruğa düşenler (PRD §8.5)."""

    UNKNOWN = "unknown"
    UNREADABLE = "unreadable"
    UNRESOLVED = "unresolved"


# --- çalışan -----------------------------------------------------------------------------


class Employee(Base):
    __tablename__ = "employees"

    # K8: E numarası sistem tarafından verilir ve asla değişmez (bkz. allocate_employee_number).
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    folder_name: Mapped[str] = mapped_column(String(255), unique=True)
    given_names: Mapped[str] = mapped_column(String(255))
    surname: Mapped[str] = mapped_column(String(255))
    # §8.4 `person.other_names` — 03.1.3 gereği çalışan kaydına taşınır.
    other_names: Mapped[str | None] = mapped_column(String(255))
    original_script_name: Mapped[str | None] = mapped_column(String(255))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    identifiers: Mapped[list[EmployeeIdentifier]] = relationship(back_populates="employee")
    aliases: Mapped[list[EmployeeAlias]] = relationship(back_populates="employee")
    contacts: Mapped[list[EmployeeContact]] = relationship(back_populates="employee")
    documents: Mapped[list[Document]] = relationship(back_populates="employee")


class EmployeeIdentifier(Base):
    __tablename__ = "employee_identifiers"
    __table_args__ = (UniqueConstraint("employee_id", "kind", "value"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(String(128), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))

    employee: Mapped[Employee] = relationship(back_populates="identifiers")
    source_document: Mapped[Document | None] = relationship()


class EmployeeAlias(Base):
    __tablename__ = "employee_aliases"
    __table_args__ = (UniqueConstraint("employee_id", "raw_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    raw_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    script: Mapped[str | None] = mapped_column(String(16))

    employee: Mapped[Employee] = relationship(back_populates="aliases")


class EmployeeContact(Base):
    __tablename__ = "employee_contacts"
    __table_args__ = (CheckConstraint(_one_of("kind", ContactKind), name="kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    value: Mapped[str] = mapped_column(Text)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    first_seen_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    employee: Mapped[Employee] = relationship(back_populates="contacts")
    source_document: Mapped[Document | None] = relationship()


# --- yükleme, dosya, sayfa, plan -----------------------------------------------------------


class Upload(Base):
    __tablename__ = "uploads"
    __table_args__ = (CheckConstraint(_one_of("status", UploadStatus), name="status"),)

    # Metin kimlik: Inbox/<upload_id>/ ve Plan JSON `upload_id` (§8.2, §8.5).
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    uploaded_by: Mapped[str | None] = mapped_column(String(255))
    context_employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"))
    status: Mapped[str] = mapped_column(String(16), default=UploadStatus.RECEIVED.value)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    context_employee: Mapped[Employee | None] = relationship()
    files: Mapped[list[UploadFile]] = relationship(
        back_populates="upload", order_by="UploadFile.id"
    )
    plans: Mapped[list[Plan]] = relationship(back_populates="upload", order_by="Plan.version")
    queue_items: Mapped[list[QueueItem]] = relationship(
        back_populates="upload", order_by="QueueItem.id"
    )


class UploadFile(Base):
    __tablename__ = "upload_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.id"), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(1024))
    # K10: tekrar yükleme SHA-256 ile tespit edilir; tekrarlar da satır olarak kalır.
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    mime: Mapped[str] = mapped_column(String(127))
    page_count: Mapped[int | None] = mapped_column(Integer)
    is_duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("upload_files.id"))

    upload: Mapped[Upload] = relationship(back_populates="files")
    duplicate_of: Mapped[UploadFile | None] = relationship(remote_side=[id])
    pages: Mapped[list[Page]] = relationship(back_populates="file", order_by="Page.index")


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("file_id", "index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("upload_files.id"))
    index: Mapped[int] = mapped_column(Integer)
    image_path: Mapped[str | None] = mapped_column(String(1024))
    text_layer: Mapped[str | None] = mapped_column(Text)
    is_blank: Mapped[bool] = mapped_column(Boolean, default=False)
    has_single_embedded_image: Mapped[bool] = mapped_column(Boolean, default=False)
    analysis_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    analysis_status: Mapped[str] = mapped_column(String(16), default="pending")

    file: Mapped[UploadFile] = relationship(back_populates="pages")


class Plan(Base):
    __tablename__ = "plans"
    # K18: yeniden analiz aynı partide yeni sürüm açar.
    __table_args__ = (UniqueConstraint("upload_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.id"))
    version: Mapped[int] = mapped_column(Integer)
    json: Mapped[dict[str, Any]] = mapped_column(JSON)
    model: Mapped[str | None] = mapped_column(String(128))
    plan_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    executed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    upload: Mapped[Upload] = relationship(back_populates="plans")
    documents: Mapped[list[Document]] = relationship(back_populates="plan")


# --- çıktı, kuyruk, katalog ----------------------------------------------------------------


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    type_slug: Mapped[str] = mapped_column(ForeignKey("known_document_types.slug"))
    path: Mapped[str] = mapped_column(String(1024))
    format: Mapped[str] = mapped_column(String(16))
    # K8: aynı türden ikinci belge `-2`, üçüncü `-3` eki alır; ilk belge 1.
    sequence_no: Mapped[int] = mapped_column(Integer, default=1)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"))
    # K15: her çıktı kaynak dosya ve sayfa aralığına bağlanır.
    source_refs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    employee: Mapped[Employee] = relationship(back_populates="documents")
    plan: Mapped[Plan | None] = relationship(back_populates="documents")
    document_type: Mapped[KnownDocumentType] = relationship()


class QueueItem(Base):
    __tablename__ = "queue_items"
    __table_args__ = (CheckConstraint(_one_of("kind", QueueKind), name="kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.id"), index=True)
    plan_item_id: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    resolved_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    resolved_by: Mapped[str | None] = mapped_column(String(255))

    upload: Mapped[Upload] = relationship(back_populates="queue_items")


class KnownDocumentType(Base):
    """Katalog kaydı (§8.1 + §8.6). Şema doğrulaması `app/catalog/` işidir (00.6.1)."""

    __tablename__ = "known_document_types"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    file_label: Mapped[str] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(8))
    description: Mapped[str | None] = mapped_column(Text)
    expected_file_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    expected_pages_min: Mapped[int | None] = mapped_column(Integer)
    expected_pages_max: Mapped[int | None] = mapped_column(Integer)
    sides: Mapped[str] = mapped_column(String(16))
    direct: Mapped[bool] = mapped_column(Boolean)
    analyze: Mapped[bool] = mapped_column(Boolean)
    required_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_conversions: Mapped[list[str]] = mapped_column(JSON, default=list)
    output_format: Mapped[str] = mapped_column(String(16))
    # §8.6 `acceptance_criteria` — 00.6.1 ve 04.4.2 bu alanı katalogda arar.
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, default=list)
    prompt_description: Mapped[str | None] = mapped_column(Text)
    photo_rules: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CandidateDocumentType(Base):
    __tablename__ = "candidate_document_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposed_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    first_seen_upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.id"))
    sample_page_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    seen_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="pending")

    first_seen_upload: Mapped[Upload] = relationship()


# --- log ve kullanıcılar -------------------------------------------------------------------


class Event(Base):
    """Olay logu satırı (K15). Olay türleri listesi `app/events.py` işidir (00.5.1)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, index=True)
    upload_id: Mapped[str | None] = mapped_column(ForeignKey("uploads.id"), index=True)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("upload_files.id"))
    page_index: Mapped[int | None] = mapped_column(Integer)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), index=True)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"), index=True)
    actor: Mapped[str] = mapped_column(String(255), default="system")
    type: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str | None] = mapped_column(Text)
    data_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    upload: Mapped[Upload | None] = relationship()
    file: Mapped[UploadFile | None] = relationship()
    document: Mapped[Document | None] = relationship()
    employee: Mapped[Employee | None] = relationship()


class AccessLog(Base):
    __tablename__ = "access_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16))

    user: Mapped[User] = relationship()
    document: Mapped[Document] = relationship()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))

    telegram_accounts: Mapped[list[TelegramUser]] = relationship(back_populates="user")


class TelegramUser(Base):
    """K13: Telegram kullanıcı ID beyaz listesi."""

    __tablename__ = "telegram_users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    allowed: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="telegram_accounts")


# --- çalışan numarası üretici (00.3.3) -----------------------------------------------------

EMPLOYEE_NUMBER_PREFIX = "E"
_EMPLOYEE_NUMBER_LOCK_KEY = zlib.crc32(b"belgeee.employees.id")


def format_employee_number(sequence: int) -> str:
    """`1 → E0001`; 9999'dan sonra hane sayısı büyür (`E10000`)."""
    if sequence < 1:
        raise ValueError(f"Çalışan sıra numarası 1 veya büyük olmalı: {sequence}")
    return f"{EMPLOYEE_NUMBER_PREFIX}{sequence:04d}"


def allocate_employee_number(session: Session) -> str:
    """Bu işlemde eklenecek çalışanın E numarasını verir (artan, tekil; K8).

    Sözleşme: dönen numarayla `Employee` **aynı işlemde** eklenir ve işlem commit edilir.
    Tahsis işlem sonuna kadar kilitlidir, eşzamanlı çağrılar sıraya girer:

    - PostgreSQL: işlem ömürlü advisory kilit (`pg_advisory_xact_lock`).
    - SQLite: `app.db.session` motoru her işlemi `BEGIN IMMEDIATE` ile açar; yazma kilidi
      işlemin başından beri bu işlemdedir.

    Numara bir kez verilip işlem geri alınırsa aynı numara sonraki çağrıya tekrar verilir;
    commit edilmiş numara silme olmadığı için (K16) bir daha asla verilmez.
    """
    if session.get_bind().dialect.name == "postgresql":
        session.execute(select(func.pg_advisory_xact_lock(_EMPLOYEE_NUMBER_LOCK_KEY)))
    session.flush()
    sequence = cast(func.substr(Employee.id, len(EMPLOYEE_NUMBER_PREFIX) + 1), Integer)
    current = session.scalar(select(func.max(sequence)))
    return format_employee_number((current or 0) + 1)
