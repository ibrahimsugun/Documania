"""Katalog yönetimi — panelden tür oluşturma, düzenleme, pasifleştirme (11.1.1).

Veritabanındaki `known_document_types` kataloğun çalışma zamanı kaynağıdır: her analiz
`export_catalog` ile tabloyu baştan okur (`orchestrate.py`), bu yüzden burada yazılan değişiklik
**bir sonraki analizde** geçerli olur (11.1.3); süren analiz kendi başladığı andaki kataloğu, donmuş
plan (K9) kendi planını kullanır. `catalog.yaml` yalnız tohum ve dışa aktarım dosyasıdır
(`python -m app.catalog export`); bu modül onu yazmaz.

- **Silme yok** (K16, R11): tür pasifleştirilir ya da arşivlenir. Pasif tür yeni belgeye atanmaz
  (analiz talimatına girmez) ama var olan belgelerin türü olarak kalır ve listede görünür.
- **Arşiv (11.1.6, PLAN.md §C92-a).** Arşivli tür (`archived_at` dolu) ayrıca listeden
  (`list_types` varsayılanı), tür seçicilerden ve eğitimin bilinen türlerinden kalkar; kaydı ve
  belgeleri yerinde kalır, `load_record` onu okumaya devam eder (belge listeleri adını gösterir).
  Boru hattının adıyla andığı türler (`PROTECTED_SLUGS`) arşivlenemez. Arşivleme, geri alma,
  etkinleştirme ve pasifleştirme olayı kullanıcı adıyla yazılır (`TYPE_*`).
- `slug` değişmez: belgeler ve çıktı adları ona bağlıdır. Düzenleme yalnız form alanlarını yazar;
  `active` (`set_type_active`) ve `photo_rules` (`set_photo_rules`, 11.6.1) dışarıda kalır.
- Hiçbir fonksiyon commit etmez; iş birimini çağıran kapatır (`sync.py` ile aynı sözleşme).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog.photo_rules import PHOTO_RULE_TYPES
from app.catalog.schema import CatalogEntry, CatalogError, validate_catalog
from app.catalog.sync import entry_to_columns, row_to_record
from app.db.models import KnownDocumentType, utcnow
from app.events import EventType, record_event

# Formdan değişmeyen sütunlar: pasifleştirme ve fotoğraf kuralları ayrı işlemlerdir.
_NOT_EDITED = frozenset({"active", "photo_rules"})

# Word/Excel eklerinin türü (K2): grup adımı onu `unanalyzed_entry_for` ile bulur (04.7.1).
ATTACHMENT_SLUG = "attachment"
PROFILE_PICTURE_SLUG = "profile_picture"
# 11.1.6: boru hattının ve panelin adıyla andığı türler arşivlenemez. Kodda `*_SLUG = "..."`
# sabitiyle anılan her tür burada olmalıdır (`tests/catalog/test_archive.py` kodu tarar).
PROTECTED_SLUGS = frozenset({ATTACHMENT_SLUG, PROFILE_PICTURE_SLUG}) | PHOTO_RULE_TYPES


class TypeNotFoundError(LookupError):
    """`slug` katalogda yok."""


class TypeExistsError(ValueError):
    """`slug` katalogda zaten var."""


class PhotoRulesUnsupportedError(ValueError):
    """`slug` türünün fotoğraf kuralı yok (`PHOTO_RULE_TYPES` dışında)."""


class TypeProtectedError(ValueError):
    """`slug` boru hattının andığı korunan türdür (`PROTECTED_SLUGS`); arşivlenemez."""


def _row(session: Session, slug: str) -> KnownDocumentType:
    row = session.get(KnownDocumentType, slug)
    if row is None:
        raise TypeNotFoundError(slug)
    return row


@dataclass(frozen=True, slots=True)
class TypeSummary:
    """Yönetim listesinin bir satırı; `problems` doluysa kayıtlı tür §8.6'ya uymuyor."""

    slug: str
    name: str
    file_label: str
    country: str | None
    sides: str
    direct: bool
    analyze: bool
    criteria_count: int
    active: bool
    problems: tuple[str, ...]
    archived_at: datetime | None = None
    archived_by: str | None = None

    @property
    def protected(self) -> bool:
        """Arşivlenemeyen tür (`PROTECTED_SLUGS`)."""
        return self.slug in PROTECTED_SLUGS


def record_problems(record: dict[str, Any]) -> tuple[str, ...]:
    """Tek kaydın §8.6 doğrulaması; geçerliyse boş."""
    try:
        validate_catalog([record])
    except CatalogError as exc:
        return tuple(exc.problems)
    return ()


def load_record(session: Session, slug: str) -> dict[str, Any]:
    """Türün ham §8.6 kaydı (doğrulanmamış); yok → `TypeNotFoundError`."""
    return row_to_record(_row(session, slug))


def list_types(session: Session, *, include_archived: bool = False) -> list[TypeSummary]:
    """Türler (pasifler dahil; arşivliler yalnız `include_archived` ile), slug sırasıyla. Her satır
    ayrı doğrulanır: tutarsız bir satır listeyi düşürmez, `problems` taşır — panelin onu
    düzeltebilmesi için görünür kalır."""
    query = select(KnownDocumentType).order_by(KnownDocumentType.slug)
    if not include_archived:
        query = query.where(KnownDocumentType.archived_at.is_(None))
    summaries = []
    for row in session.scalars(query):
        record = row_to_record(row)
        summaries.append(
            TypeSummary(
                slug=row.slug,
                name=row.name,
                file_label=row.file_label,
                country=row.country,
                sides=row.sides,
                direct=row.direct,
                analyze=row.analyze,
                criteria_count=len(row.acceptance_criteria or ()),
                active=row.active,
                problems=record_problems(record),
                archived_at=row.archived_at,
                archived_by=row.archived_by,
            )
        )
    return summaries


def create_type(session: Session, entry: CatalogEntry) -> None:
    """Yeni tür ekler; slug varsa `TypeExistsError`. Aynı anda iki istek biri kazanır."""
    if session.get(KnownDocumentType, entry.slug) is not None:
        raise TypeExistsError(entry.slug)
    try:
        with session.begin_nested():
            session.add(KnownDocumentType(slug=entry.slug, **entry_to_columns(entry)))
    except IntegrityError:
        raise TypeExistsError(entry.slug) from None


def update_type(session: Session, entry: CatalogEntry) -> bool:
    """Var olan türün form alanlarını yazar; bir şey değiştiyse `True`."""
    row = _row(session, entry.slug)
    changed = False
    for key, value in entry_to_columns(entry).items():
        if key not in _NOT_EDITED and getattr(row, key) != value:
            setattr(row, key, value)
            changed = True
    session.flush()
    return changed


def _event_data(slug: str, bulk: bool) -> dict[str, Any]:
    return {"slug": slug, "bulk": True} if bulk else {"slug": slug}


def set_type_active(
    session: Session, slug: str, active: bool, *, actor: str, bulk: bool = False
) -> bool:
    """Türü pasifleştirir ya da yeniden etkinleştirir; durum değiştiyse `True` ve
    `TYPE_ACTIVATED`/`TYPE_DEACTIVATED` kullanıcı adıyla (`actor`) yazılır (toplu işlemde
    `bulk: true`). Durum zaten istenen gibiyse hiçbir şey yazılmaz."""
    row = _row(session, slug)
    if row.active == active:
        return False
    row.active = active
    record_event(
        session,
        EventType.TYPE_ACTIVATED if active else EventType.TYPE_DEACTIVATED,
        actor=actor,
        data=_event_data(slug, bulk),
    )
    session.flush()
    return True


def check_archivable(session: Session, slug: str) -> KnownDocumentType:
    """Arşivlenebilir türün satırı; yoksa `TypeNotFoundError`, korunan türse `TypeProtectedError`.
    Yazmaz."""
    row = _row(session, slug)
    if slug in PROTECTED_SLUGS:
        raise TypeProtectedError(slug)
    return row


def archive_type(session: Session, slug: str, *, actor: str, bulk: bool = False) -> bool:
    """11.1.6 — türü arşivler: `archived_at`/`archived_by` dolar, `TYPE_ARCHIVED` kullanıcı adıyla
    yazılır; `True`. Zaten arşivliyse hiçbir şey yazılmaz (`False`). Yoksa `TypeNotFoundError`,
    korunan türse `TypeProtectedError`. Kayıt ve belgeleri yerinde kalır (R11)."""
    row = check_archivable(session, slug)
    if row.archived_at is not None:
        return False
    row.archived_at = utcnow()
    row.archived_by = actor
    record_event(session, EventType.TYPE_ARCHIVED, actor=actor, data=_event_data(slug, bulk))
    session.flush()
    return True


def restore_type(session: Session, slug: str, *, actor: str) -> bool:
    """11.1.6 — arşivli türü geri alır: iki arşiv alanı boşalır, `TYPE_RESTORED` kullanıcı adıyla
    yazılır; `True`. Arşivde değilse hiçbir şey yazılmaz (`False`); yoksa `TypeNotFoundError`.
    Etkin/pasif durumu değişmez."""
    row = _row(session, slug)
    if row.archived_at is None:
        return False
    row.archived_at = None
    row.archived_by = None
    record_event(session, EventType.TYPE_RESTORED, actor=actor, data={"slug": slug})
    session.flush()
    return True


def set_photo_rules(session: Session, slug: str, rules: dict[str, Any]) -> bool:
    """Türün fotoğraf kural setini yazar (11.6.1); kayıt değiştiyse `True`.

    `rules` `build_photo_rules`tan gelir (doğrulanmış, bütün kurallar açık). Kural yalnız
    `PHOTO_RULE_TYPES` türlerindedir: başka türde `PhotoRulesUnsupportedError`, tür yoksa
    `TypeNotFoundError`. Kural değişikliği belge içeriğine dokunmaz (K17).
    """
    row = _row(session, slug)
    if slug not in PHOTO_RULE_TYPES:
        raise PhotoRulesUnsupportedError(slug)
    if row.photo_rules == rules:
        return False
    row.photo_rules = rules
    session.flush()
    return True
