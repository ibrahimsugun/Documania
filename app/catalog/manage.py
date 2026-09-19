"""Katalog yönetimi — panelden tür oluşturma, düzenleme, pasifleştirme (11.1.1).

Veritabanındaki `known_document_types` kataloğun çalışma zamanı kaynağıdır: her analiz
`export_catalog` ile tabloyu baştan okur (`orchestrate.py`), bu yüzden burada yazılan değişiklik
**bir sonraki analizde** geçerli olur (11.1.3); süren analiz kendi başladığı andaki kataloğu, donmuş
plan (K9) kendi planını kullanır. `catalog.yaml` yalnız tohum ve dışa aktarım dosyasıdır
(`python -m app.catalog export`); bu modül onu yazmaz.

- **Silme yok** (K16): tür pasifleştirilir. Pasif tür yeni belgeye atanmaz (analiz talimatına
  girmez) ama var olan belgelerin türü olarak kalır.
- `slug` değişmez: belgeler ve çıktı adları ona bağlıdır. Düzenleme yalnız form alanlarını yazar;
  `active` (`set_type_active`) ve `photo_rules` (11.6) dışarıda kalır.
- Hiçbir fonksiyon commit etmez; iş birimini çağıran kapatır (`sync.py` ile aynı sözleşme).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog.schema import CatalogEntry, CatalogError, validate_catalog
from app.catalog.sync import entry_to_columns, row_to_record
from app.db.models import KnownDocumentType

# Formdan değişmeyen sütunlar: pasifleştirme ayrı işlemdir, fotoğraf kuralları 11.6'nındır.
_NOT_EDITED = frozenset({"active", "photo_rules"})


class TypeNotFoundError(LookupError):
    """`slug` katalogda yok."""


class TypeExistsError(ValueError):
    """`slug` katalogda zaten var."""


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


def list_types(session: Session) -> list[TypeSummary]:
    """Bütün türler (pasifler dahil), slug sırasıyla. Her satır ayrı doğrulanır: tutarsız bir
    satır listeyi düşürmez, `problems` taşır — panelin onu düzeltebilmesi için görünür kalır."""
    summaries = []
    for row in session.scalars(select(KnownDocumentType).order_by(KnownDocumentType.slug)):
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


def set_type_active(session: Session, slug: str, active: bool) -> bool:
    """Türü pasifleştirir ya da yeniden etkinleştirir; durum değiştiyse `True`."""
    row = _row(session, slug)
    if row.active == active:
        return False
    row.active = active
    session.flush()
    return True
