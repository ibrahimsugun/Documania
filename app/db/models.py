"""Veri modeli — PRD §8.1 tabloları (00.3.1), çalışan numarası üretici (00.3.3), aday tür
kaydı (04.6.1) ve kararı (11.5), panel oturumu (10.1.2), iki aşamalı onayın belirteci (10.8.1),
kalıcı işçi kuyruğu (13.3.1), profil alanlarının belge gözlemleri (05.7.3), partinin yoksayılması
(10.3.4), aday türün incelemesi (11.5.5) ve eğitim modu (11.9).

Silme yoktur, arşiv vardır (K16): ilişkilerde silme kaskadı tanımlanmaz.
Dosya yolu burada üretilmez (yol kuralı: `app/storage/`); yol sütunları yalnız saklar.
Şema değişikliği yalnız Alembic göçüyle yapılır (`alembic/versions/`).
"""

from __future__ import annotations

import enum
import zlib
from dataclasses import dataclass
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
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    cast,
    func,
    select,
    text,
    update,
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


class IdleClaimMixin:
    """İşçinin boş-zaman işinin tükettiği tablonun sahiplenme alanları (`app.worker.idle`).

    `idle_claimed_by` son sahiplenenin tek kullanımlık belirtecidir (her alışta yenisi),
    `idle_claim_expires_at` sahiplenmenin süresi, `idle_attempts` satırın kaç kez alındığıdır.
    Alanlar tüketen tablonun göçündedir. Tanım burada durur (`app.worker.idle` bu modülü içe
    aktarır; tersi döngü olurdu) ve `app.worker`'dan da dışa aktarılır.
    """

    idle_claimed_by: Mapped[str | None] = mapped_column(String(128))
    idle_claim_expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    idle_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


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


class QueueResolution(enum.StrEnum):
    """Kuyruk öğesinin çözüm nedeni (`queue_items.resolution`). Atama (08.2.1) ve profil onayı
    (08.3.1) nedeni yazmaz — kendi olayları (`MANUAL_ASSIGN`, `MANUAL_APPROVE`) ve çıktıları
    anlatır; yalnız partisi yoksayılınca (10.3.4) kapanan öğe `dismissed` taşır."""

    DISMISSED = "dismissed"


class DocumentStatus(enum.StrEnum):
    """Çıktı belgesi durumu (§8.1 `documents.status`).

    Belge `active` yazılır. Parti yeniden analiz edilince önceki plan sürümlerinin etkin çıktıları
    "eski sürüm" (`superseded`) işaretlenir; satır ve dosya silinmez, yeniden adlandırılmaz (K18,
    06.6.2). Yalnız `active` belge arşivlenir (K16, 08.4.1); arşive taşınan belge `archived`
    işaretlenir, satır ve dosya yine silinmez.
    """

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class ProfileField(enum.StrEnum):
    """Belgeden tamamlanan profil alanı (05.7.3; `employee_field_observations.field`): `employees`
    sütun adları. Belge numarası ve iletişim bilgisi kendi birikim yolundadır (05.7.2, 05.8.1)."""

    GIVEN_NAMES = "given_names"
    SURNAME = "surname"
    OTHER_NAMES = "other_names"
    ORIGINAL_SCRIPT_NAME = "original_script_name"
    DATE_OF_BIRTH = "date_of_birth"
    NATIONALITY = "nationality"


class FieldOutcome(enum.StrEnum):
    """Belgede okunan değerin profil alanıyla karşılaştırması (05.7.3,
    `employee_field_observations.outcome`)."""

    FILLED = "filled"  # alan boştu, belgedeki değerle dolduruldu
    SAME = "same"  # alan doluydu, belge aynı değeri okudu (§20.2.1 normalizasyonuyla)
    CONFLICT = "conflict"  # alan doluydu, belge farklı değer okudu; alan değişmedi


class CandidateTypeStatus(enum.StrEnum):
    """Aday tür durumu (§8.1 `candidate_document_types.status`).

    Kayıt `pending` açılır; onay (11.5.2, `TYPE_APPROVED`) ve ret (11.5.4, `TYPE_REJECTED`)
    insanın kararıdır ve `decide_candidate_type` ile yalnız bekleyen kayda bir kez yazılır. Türün
    yeniden görülmesi durumu değiştirmez.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CandidateProposalStatus(enum.StrEnum):
    """Aday türün incelemesinin sonucu (§8.1 `candidate_document_types.proposal_status`, 11.5.5).

    `NULL` incelenmedi demektir (işçinin boş-zaman işi bekleyen adayı inceler,
    `app.catalog.propose`). `ready`: tür taslağı saklandı; `failed`: taslak üretilemedi ya da
    örnekteki kişiye ait değer taşıdığı için saklanmadı; `no_samples`: görüntüsü kalan örnek sayfa
    yok.
    """

    READY = "ready"
    FAILED = "failed"
    NO_SAMPLES = "no_samples"


class TrainingRunKind(enum.StrEnum):
    """Eğitim modu çalıştırmasının türü (§8.1 `training_runs.kind`, 11.9): panelden dosya
    yükleme (11.9.1) ya da harita ile toplu tarama (11.9.5)."""

    UPLOAD = "upload"
    MAP = "map"


class TrainingRunStatus(enum.StrEnum):
    """Eğitim çalıştırmasının durumu (`training_runs.status`): `running` — kararı sistemde bekleyen
    (`queued` ya da `ai_pending`) öğesi var; `done` — öğelerin hepsi sistemin son kararında
    (`app.training.refresh_run`). İnsan bekleyen öğe (`unplaced`, `conflict`, `review`) çalıştırmayı
    açık tutmaz."""

    RUNNING = "running"
    DONE = "done"


class TrainingItemStatus(enum.StrEnum):
    """Eğitim öğesinin durumu (`training_items.status`, PLAN.md §C86).

    `queued` → `placed` | `ai_pending` | `skipped` | `failed`; `ai_pending` → `placed` |
    `unplaced` | `conflict`; harita satırı ayrıca `review` (§C87). `skipped`: aynı içerik bu türde
    zaten örnek; `conflict`: aynı içerik başka türde örnek ya da ipucuyla çelişen sonuç;
    `unplaced`: hiçbir bilinen türe yerleşmedi ("Yerleştirilemedi").
    """

    QUEUED = "queued"
    PLACED = "placed"
    AI_PENDING = "ai_pending"
    SKIPPED = "skipped"
    FAILED = "failed"
    UNPLACED = "unplaced"
    CONFLICT = "conflict"
    REVIEW = "review"


class TrainingMethod(enum.StrEnum):
    """Eğitim öğesini türe yerleştiren yol (`training_items.method`): mekanik tanıma (11.9.2),
    yapay zekâ incelemesi (11.9.3) ya da İK'nın "Türe yerleştir"i (11.9.1)."""

    MECHANICAL = "mechanical"
    AI = "ai"
    MANUAL = "manual"


class ExampleMethod(enum.StrEnum):
    """Örnek dosyası kaydının yolu (`example_files.method`): eğitim yolları ve `legacy` — eğitimden
    önce klasöre konmuş, kaydı sonradan tutulan dosya."""

    MECHANICAL = "mechanical"
    AI = "ai"
    MANUAL = "manual"
    LEGACY = "legacy"


class ExampleLabel(enum.StrEnum):
    """Örnek dosyasının etiketi (`example_files.label`; `NULL` etiketsiz): yapay zekânın
    yerleştirdiği örnek `ai_decision` ("AI kararı", elle kontrol gerekli, 11.9.3), İK'nın
    doğruladığı ya da yerleştirdiği örnek `verified` (11.9.1, 11.9.4)."""

    AI_DECISION = "ai_decision"
    VERIFIED = "verified"


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


class EmployeeFieldObservation(Base):
    """Bir profil alanının bir belgede görülmesi (05.7.3, PLAN.md §C82): alan belgeden dolduruldu
    mu, belge aynı değeri mi okudu, farklı mı.

    **Değer tutulmaz** — kişisel değer sayfa analizinde durur (CONVENTIONS §6). Kaynak belgenin
    ilk sayfasıdır (`file_id`, `page_index`): planın belge adayının ilk sayfası, çıktının kökeninin
    (`documents.source_refs_json`) ilk sayfası. Bir alan aynı kaynaktan bir kez gözlenir; satır
    silinmez. PRD §8.1 tablo listesinde yok; bu tablo 05.7.3'ün deposudur.
    """

    __tablename__ = "employee_field_observations"
    __table_args__ = (
        CheckConstraint(_one_of("field", ProfileField), name="field"),
        CheckConstraint(_one_of("outcome", FieldOutcome), name="outcome"),
        UniqueConstraint(
            "employee_id",
            "field",
            "file_id",
            "page_index",
            # Kuralın üreteceği ad PostgreSQL'in 63 karakter sınırını aşar.
            name="uq_employee_field_observations_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    field: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(16))
    file_id: Mapped[int] = mapped_column(ForeignKey("upload_files.id"))
    page_index: Mapped[int] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    employee: Mapped[Employee] = relationship()
    file: Mapped[UploadFile] = relationship()


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
    # 10.3.4: taramayı yoksayma anı ve kullanıcısı. Durum makinesinin (09.2.1) parçası değildir:
    # yoksayılan parti listelerden ve kuyruklardan kalkar, dosyası/olayı/çıktısı yerinde durur.
    dismissed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    dismissed_by: Mapped[str | None] = mapped_column(String(255))

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
    # 11.7.1: fotoğraf türündeki sayfanın kural değerlendirmesi (`app.ai.photo_check.PhotoCheck`);
    # fotoğraf kontrolü yapılmayan sayfada boş.
    photo_check_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

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
    status: Mapped[str] = mapped_column(String(16), default=DocumentStatus.ACTIVE.value)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    employee: Mapped[Employee] = relationship(back_populates="documents")
    plan: Mapped[Plan | None] = relationship(back_populates="documents")
    document_type: Mapped[KnownDocumentType] = relationship()


class QueueItem(Base):
    __tablename__ = "queue_items"
    __table_args__ = (
        CheckConstraint(_one_of("kind", QueueKind), name="kind"),
        CheckConstraint(_one_of("resolution", QueueResolution), name="resolution"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.id"), index=True)
    # K18: plan öğesi kimlikleri (`i1`, `i2`…) partinin plan sürümleri arasında tekrar eder;
    # öğeyi yalnız `plan_id` + `plan_item_id` birlikte gösterir. Kaydı yazan (08.1) ikisini de
    # yazar; partinin güncel planına ait olmayan öğe eski sürümdür (06.6.2).
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"), index=True)
    plan_item_id: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    resolved_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    resolved_by: Mapped[str | None] = mapped_column(String(255))
    resolution: Mapped[str | None] = mapped_column(String(16))  # `QueueResolution`

    upload: Mapped[Upload] = relationship(back_populates="queue_items")
    plan: Mapped[Plan | None] = relationship()


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
    # §8.6 `front_back_layouts` (04.1.2): `front_back` türün kabul ettiği düzenler; tek yüzlüde boş.
    front_back_layouts: Mapped[list[str]] = mapped_column(JSON, default=list)
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


class CandidateDocumentType(IdleClaimMixin, Base):
    """Katalogda olmayan, analizcinin önerdiği belge türü (04.6.1).

    Kayıt `record_candidate_type_sighting` ile yazılır. `normalized_name` tekillik anahtarıdır
    (`normalize_candidate_type_name`), `proposed_name` ilk görüldüğü yazımdır. `sample_page_ids`
    türün görüldüğü her belge adayının ilk sayfasını (`pages.id`) görülme sırasıyla taşır;
    `seen_count` bu görülmelerin sayısıdır.

    İnceleme (11.5.5, `app.catalog.propose`): `proposal_status` sonucu (`CandidateProposalStatus`;
    `NULL` incelenmedi), `proposal_json` tür taslağını ya da gerekçeyi, gözlenen kanıtı, modeli ve
    kullanılan sayfa sayısını, `proposal_generated_at` incelemenin anını taşır. Sahiplenme alanları
    (`IdleClaimMixin`) işçinin boş-zaman işinindir.
    """

    __tablename__ = "candidate_document_types"
    __table_args__ = (
        CheckConstraint(
            _one_of("proposal_status", CandidateProposalStatus), name="proposal_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposed_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    first_seen_upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.id"))
    sample_page_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    seen_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default=CandidateTypeStatus.PENDING.value)
    proposal_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    proposal_status: Mapped[str | None] = mapped_column(String(16))
    proposal_generated_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    first_seen_upload: Mapped[Upload] = relationship()


# --- eğitim modu (11.9) --------------------------------------------------------------------


class TrainingRun(Base):
    """Eğitim modu çalıştırması (§8.1, 11.9; PLAN.md §C86): bir yükleme ya da bir harita taraması.

    Eğitim yolu çalışan verisine dokunmaz: parti (`uploads`), dosya (`upload_files`), çalışan,
    kuyruk öğesi ya da çıktı belgesi açmaz. `counts_json` öğelerin durumlarına göre sayısıdır
    (`{"<durum>": n}`) ve `app.training.refresh_run` ile öğelerden yeniden sayılır.
    """

    __tablename__ = "training_runs"
    __table_args__ = (
        CheckConstraint(_one_of("kind", TrainingRunKind), name="kind"),
        CheckConstraint(_one_of("status", TrainingRunStatus), name="status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    map_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default=TrainingRunStatus.RUNNING.value)
    counts_json: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)

    items: Mapped[list[TrainingItem]] = relationship(
        back_populates="run", order_by="TrainingItem.id"
    )


class TrainingItem(IdleClaimMixin, Base):
    """Eğitim modunda işlenen bir dosya (§8.1, 11.9).

    `staged_path` yüklenen içeriğin `KnownDocuments/_egitim/gelen/<run>/<item>.<ext>` kopyasının
    veri köküne göreli yoludur (örnek olarak kabul edilmeyen dosya yazılmaz); harita satırında
    `row_number` ve `source_ref` (haritadaki yol) dolar. `hint_slug` beklenen ya da haritadaki tür,
    `result_slug` sonucun türüdür. `checks_json` mekanik kontrollerin ve yapay zekâ
    sınıflandırmasının (`ai` anahtarı, 11.9.3) kişisel değer taşımayan dökümüdür. Sahiplenme
    alanları (`IdleClaimMixin`) işçinin `ai_pending` öğeyi sınıflandıran boş-zaman işinindir
    (`app.training.classification`).
    """

    __tablename__ = "training_items"
    __table_args__ = (
        CheckConstraint(_one_of("status", TrainingItemStatus), name="status"),
        CheckConstraint(_one_of("method", TrainingMethod), name="method"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("training_runs.id"), index=True)
    row_number: Mapped[int | None] = mapped_column(Integer)
    original_name: Mapped[str] = mapped_column(String(255))
    source_ref: Mapped[str | None] = mapped_column(String(1024))
    staged_path: Mapped[str | None] = mapped_column(String(1024))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    file_kind: Mapped[str | None] = mapped_column(String(16))
    page_count: Mapped[int | None] = mapped_column(Integer)
    hint_slug: Mapped[str | None] = mapped_column(String(64))
    result_slug: Mapped[str | None] = mapped_column(String(64))
    method: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(
        String(16), default=TrainingItemStatus.QUEUED.value, index=True
    )
    note: Mapped[str | None] = mapped_column(Text)
    checks_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    decided_by: Mapped[str | None] = mapped_column(String(255))
    decided_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    run: Mapped[TrainingRun] = relationship(back_populates="items")


class ExampleFileRecord(Base):
    """Örnek dosyasının kaydı ve etiketi (§8.1 `example_files`, 11.9).

    Dosya `KnownDocuments/examples/<type_slug>/<name>`'dedir; `type_slug` katalog ya da hazır
    önerilen türdür (katalog dışı olabildiği için `known_document_types`'a bağlanmaz). `sha256`
    türler arası tekrar tespitinin dizinidir (`app.storage.examples.store_example` yalnız aynı
    klasöre bakar). Kaydı olmayan örnek (eğitimden önce konmuş ya da tür sayfasından el ile
    yüklenmiş, 11.2.1) etiketsizdir. Satır silinmez.

    **Örneklerden çıkarılan (11.9.4):** dosya `KnownDocuments/_egitim/cikarilan/<type_slug>/`'a
    taşınır (silinmez); kayıt kalır ve `removed_at`, `removed_by`, `removed_path` (veri köküne
    göreli arşiv yolu) dolar. Çıkarılan kayıt örnek sayılmaz: tekrar tespiti, sayımlar ve açıklama
    üretimi onu görmez. `(type_slug, name)` yalnız etkin (çıkarılmamış) kayıtlarda tekildir —
    çıkarılan örneğin adı klasörde yeniden kullanılabilir.
    """

    __tablename__ = "example_files"
    __table_args__ = (
        Index(
            "uq_example_files_active_name",
            "type_slug",
            "name",
            unique=True,
            sqlite_where=text("removed_at IS NULL"),
            postgresql_where=text("removed_at IS NULL"),
        ),
        CheckConstraint(_one_of("method", ExampleMethod), name="method"),
        CheckConstraint(_one_of("label", ExampleLabel), name="label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type_slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    method: Mapped[str] = mapped_column(String(16))
    label: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    training_item_id: Mapped[int | None] = mapped_column(ForeignKey("training_items.id"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    removed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    removed_by: Mapped[str | None] = mapped_column(String(255))
    removed_path: Mapped[str | None] = mapped_column(String(512))

    training_item: Mapped[TrainingItem | None] = relationship()


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


class AccessAction(enum.StrEnum):
    """Belgeye erişimin türü (`access_log.action`, 10.9.2): belge açıldı ya da indirildi."""

    VIEW = "view"
    DOWNLOAD = "download"


class AccessChannel(enum.StrEnum):
    """Belgeye erişilen kanal (`access_log.channel`): panel ya da bot (12.3.3)."""

    WEB = "web"
    TELEGRAM = "telegram"


class AccessLog(Base):
    """Belge erişim logu (10.9.2): kim, hangi belgeyi, ne zaman, hangi kanaldan açtı ya da indirdi.

    Satırı `app.web.access.record_access` yazar; silinmez ve değiştirilmez. `action` ve `channel`
    değerleri `AccessAction` / `AccessChannel`'dan gelir.
    """

    __tablename__ = "access_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16))

    user: Mapped[User] = relationship()
    document: Mapped[Document] = relationship()


class UserRole(enum.StrEnum):
    """Panel kullanıcısının rolü (`users.role`). Komut satırı ilk yöneticiyi açar (10.1.3)."""

    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))

    telegram_accounts: Mapped[list[TelegramUser]] = relationship(back_populates="user")


class UserSession(Base):
    """Panel oturumu (10.1.2): MASTER-PROMPT §4 "sunucu tarafı oturum çerezi" (PLAN.md §C45).

    Çerez yalnız rastgele belirteci taşır; burada belirtecin SHA-256 özeti durur, belirtecin
    kendisi saklanmaz. Oturum süresi dolunca ya da çıkışta (`revoked_at`) geçersizdir; satır
    silinmez.
    """

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    user: Mapped[User] = relationship()


class ConfirmationToken(Base):
    """İki aşamalı onayın tek kullanımlık belirteci (10.8.1, PRD §20.6.1; PLAN.md §C54).

    Birinci onaydan sonra üretilir (`created_at` birinci onayın anıdır); oturuma (çerezin SHA-256
    özeti), kullanıcıya, işleme (`operation`) ve hedef kayda (`target`) bağlıdır ve `expires_at`'e
    kadar geçerlidir. İkinci onayla gelen istek belirteci tüketir (`consumed_at`): tüketilmiş,
    süresi geçmiş ya da başka oturuma veya işleme ait belirteç reddedilir. Belirtecin kendisi
    değil SHA-256 özeti saklanır; satır silinmez.
    """

    __tablename__ = "confirmation_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    session_hash: Mapped[str] = mapped_column(String(64))
    username: Mapped[str] = mapped_column(String(150))
    operation: Mapped[str] = mapped_column(String(32))
    target: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    consumed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class JobStatus(enum.StrEnum):
    """Kalıcı işçi kuyruğundaki işin durumu (`upload_jobs.status`, PRD 13.3.1; `app.worker`).

    İş, parti açıldığı işlemde `queued` yazılır. Bir işleyici işi alınca `running` olur ve kirasını
    (`lease_expires_at`) tutar; parti son duruma (`done`, `partial`, `failed`) vardığı işlemde iş
    `finished` olur. Kirası dolmuş `running` iş sahipsiz sayılır ve yeniden alınır; alınıp
    bitirilemeden kirası en çok izin verilen deneme kadar dolan işten vazgeçilir (`abandoned`) ve
    parti `failed` olur.
    """

    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    ABANDONED = "abandoned"


class UploadJob(Base):
    """Partiyi işleme işi (13.3.1): uygulama yeniden başlasa da yarım kalan parti kaybolmasın diye
    işin kendisi veritabanında durur (PLAN.md §C72).

    Parti başına tek iş vardır. `claimed_by` işi son alan işleyicinin tek kullanımlık kimliğidir
    (her alışta yenisi): işleyici partinin her geçişini ancak iş hâlâ bu kimlikteyken commit eder.
    `attempts` işin kaç kez alındığıdır. Satır silinmez.
    """

    __tablename__ = "upload_jobs"
    __table_args__ = (CheckConstraint(_one_of("status", JobStatus), name="status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.id"), unique=True)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED.value, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    claimed_by: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    enqueued_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    claimed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    upload: Mapped[Upload] = relationship()


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


# --- yükleme parti kimliği üretici (01.1.1) ------------------------------------------------

UPLOAD_ID_PREFIX = "u"
_UPLOAD_ID_LOCK_KEY = zlib.crc32(b"belgeee.uploads.id")


def format_upload_id(day: date, sequence: int) -> str:
    """`(2026-09-05, 1) → u_20260905_0001` (PRD §8.5 örneği)."""
    if sequence < 1:
        raise ValueError(f"Yükleme sıra numarası 1 veya büyük olmalı: {sequence}")
    return f"{UPLOAD_ID_PREFIX}_{day:%Y%m%d}_{sequence:04d}"


def allocate_upload_id(session: Session, *, today: date | None = None) -> str:
    """Bu partinin `upload_id`'sini verir; sıra numarası her gün 1'den başlar.

    Sözleşme ve eşzamanlılık garantisi `allocate_employee_number` ile aynıdır: dönen
    kimlikle `Upload` **aynı işlemde** eklenip commit edilir; tahsis işlem sonuna kadar
    kilitlidir (SQLite `BEGIN IMMEDIATE`, PostgreSQL işlem ömürlü advisory kilit).
    """
    if session.get_bind().dialect.name == "postgresql":
        session.execute(select(func.pg_advisory_xact_lock(_UPLOAD_ID_LOCK_KEY)))
    session.flush()
    day = today or utcnow().date()
    prefix = f"{UPLOAD_ID_PREFIX}_{day:%Y%m%d}_"
    sequence = cast(func.substr(Upload.id, len(prefix) + 1), Integer)
    current = session.scalar(select(func.max(sequence)).where(Upload.id.like(f"{prefix}%")))
    return format_upload_id(day, (current or 0) + 1)


# --- aday tür kaydı (04.6.1) -----------------------------------------------------------------

_CANDIDATE_TYPE_LOCK_KEY = zlib.crc32(b"belgeee.candidate_document_types.normalized_name")


def normalize_candidate_type_name(name: str) -> str:
    """Aday tür adının tekillik anahtarı: harf büyüklüğü ve boşluk farkı yok sayılır.

    Dosya içi gruplamanın (04.1.1) aynı tür saydığı iki ad aynı anahtara iner.
    """
    normalized = " ".join(name.casefold().split())
    if not normalized:
        raise ValueError("Aday tür adı boş olamaz")
    return normalized


@dataclass(frozen=True, slots=True)
class CandidateTypeSighting:
    """`record_candidate_type_sighting` sonucu.

    `created`: kayıt bu çağrıda açıldı. `counted`: görülme bu çağrıda sayıldı — aynı ilk sayfa
    daha önce sayılmışsa (ör. aynı parti yeniden gruplandıysa) `False`.
    """

    candidate_type: CandidateDocumentType
    created: bool
    counted: bool


def record_candidate_type_sighting(
    session: Session, *, proposed_name: str, upload_id: str, page_id: int
) -> CandidateTypeSighting:
    """Katalog dışı bir belge adayının önerdiği türü aday tür olarak kaydeder (04.6.1).

    `page_id` adayın ilk sayfasıdır (`pages.id`). Ad kayıtlı değilse kayıt `pending` açılır
    (`first_seen_upload_id = upload_id`); kayıtlıysa ve sayfa henüz sayılmadıysa sayfa
    `sample_page_ids`'e eklenir ve `seen_count` artar. Ad, durum ve ilk görülen parti değişmez:
    reddedilen aday yeniden görülünce listeye geri düşmez (11.5.4).

    Sözleşme ve eşzamanlılık garantisi `allocate_employee_number` ile aynıdır: aynı adı aynı anda
    kaydeden işlemler sıraya girer (SQLite `BEGIN IMMEDIATE`, PostgreSQL işlem ömürlü advisory
    kilit), tekillik ihlali yerine tek kayıt ve doğru sayı oluşur.
    """
    normalized = normalize_candidate_type_name(proposed_name)
    if session.get_bind().dialect.name == "postgresql":
        session.execute(select(func.pg_advisory_xact_lock(_CANDIDATE_TYPE_LOCK_KEY)))
    session.flush()
    candidate_type = session.scalar(
        select(CandidateDocumentType).where(CandidateDocumentType.normalized_name == normalized)
    )
    if candidate_type is None:
        candidate_type = CandidateDocumentType(
            proposed_name=" ".join(proposed_name.split()),
            normalized_name=normalized,
            first_seen_upload_id=upload_id,
            sample_page_ids=[page_id],
            seen_count=1,
            status=CandidateTypeStatus.PENDING.value,
        )
        session.add(candidate_type)
        session.flush()
        return CandidateTypeSighting(candidate_type, created=True, counted=True)
    if page_id in candidate_type.sample_page_ids:
        return CandidateTypeSighting(candidate_type, created=False, counted=False)
    # JSON sütunu yerinde değişikliği izlemez; liste yeniden atanır.
    candidate_type.sample_page_ids = [*candidate_type.sample_page_ids, page_id]
    candidate_type.seen_count += 1
    session.flush()
    return CandidateTypeSighting(candidate_type, created=False, counted=True)


def decide_candidate_type(
    session: Session, candidate_type_id: int, status: CandidateTypeStatus
) -> bool:
    """Bekleyen aday türün kararını yazar: onay (11.5.2) ya da ret (11.5.4); yazıldıysa `True`.

    Yalnız `pending` kayıt karara bağlanır ve karar geri alınmaz. Koşullu güncellemedir
    (`status = 'pending'`): aynı adayı aynı anda karara bağlayan iki işlemden yalnız biri geçer;
    kayıt yoksa ya da karara bağlanmışsa `False` döner, hiçbir şey değişmez. Kayıt silinmez (K16);
    ad, görülme sayısı ve örnek sayfalar değişmez. Oturum commit edilmez.
    """
    if status is CandidateTypeStatus.PENDING:
        raise ValueError("Aday tür kararı onay ya da rettir; 'pending' karar değildir")
    decided = session.execute(
        update(CandidateDocumentType)
        .where(
            CandidateDocumentType.id == candidate_type_id,
            CandidateDocumentType.status == CandidateTypeStatus.PENDING.value,
        )
        .values(status=status.value)
    )
    return decided.rowcount == 1


# --- iletişim bilgisi birikimi (05.8.1, 05.8.2) ---------------------------------------------


@dataclass(frozen=True, slots=True)
class ContactSighting:
    """`record_contact_sighting` sonucu. `changed`: bu çağrıda yeni güncel satır açıldı (05.8.2);
    aynı değer tekrar görüldüyse yalnız `last_seen_at` ilerler, `changed: False`."""

    contact: EmployeeContact
    changed: bool


def record_contact_sighting(
    session: Session,
    *,
    employee_id: str,
    kind: str,
    value: str,
    source_document_id: int | None = None,
) -> ContactSighting:
    """Çalışanın iletişim bilgisini günceller (`employee_contacts`; 05.8.1, 05.8.2).

    Türün (`phone`/`email`/`address`) güncel (`is_current`) kaydı aynı değeri taşıyorsa yalnız
    `last_seen_at` ilerletilir — yeni satır açılmaz. Farklı bir değer geldiyse güncel kayıt
    kapatılır (`is_current: False`) ve yeni değer ayrı bir satır olarak eklenir: eski kayıt
    silinmez ya da üzerine yazılmaz (K16), geçmiş olarak kalır. Çalışanın o türde hiç kaydı
    yoksa yalnız yeni satır açılır. Oturum commit edilmez.
    """
    now = utcnow()
    current = session.scalar(
        select(EmployeeContact).where(
            EmployeeContact.employee_id == employee_id,
            EmployeeContact.kind == kind,
            EmployeeContact.is_current.is_(True),
        )
    )
    if current is not None and current.value == value:
        current.last_seen_at = now
        session.flush()
        return ContactSighting(current, changed=False)
    if current is not None:
        current.is_current = False
    contact = EmployeeContact(
        employee_id=employee_id,
        kind=kind,
        value=value,
        source_document_id=source_document_id,
        first_seen_at=now,
        last_seen_at=now,
        is_current=True,
    )
    session.add(contact)
    session.flush()
    return ContactSighting(contact, changed=True)
