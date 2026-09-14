"""Katalog ↔ veritabanı eşitleme (00.6.3).

- **İçe aktarma** (`import_catalog`): doğrulanmış katalog `known_document_types` tablosuna
  slug'a göre yazılır — yeni tür eklenir, var olan türün alanları katalogdakiyle aynı yapılır.
  Katalogda olmayan türe dokunulmaz: silme yoktur (K16) ve çıktı belgeleri türe bağlıdır;
  bu türler sonuçta `not_in_catalog` olarak bildirilir.
- **Dışa aktarma** (`export_catalog`): tablonun tamamı slug sırasıyla, yüklemeyle aynı
  sözleşmeden geçirilerek katalog olarak okunur. Tutarsız bir satır dışa aktarımı da reddeder.

İki fonksiyon da işlemi commit etmez; iş birimini çağıran kapatır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.schema import Catalog, CatalogEntry, validate_catalog
from app.db.models import KnownDocumentType


@dataclass(frozen=True)
class CatalogImportResult:
    created: tuple[str, ...]
    updated: tuple[str, ...]
    unchanged: tuple[str, ...]
    not_in_catalog: tuple[str, ...]


def entry_to_columns(entry: CatalogEntry) -> dict[str, Any]:
    """Katalog kaydı → `known_document_types` sütunları (slug hariç)."""
    columns = entry.model_dump(mode="json", exclude={"slug", "expected_pages"})
    pages = entry.expected_pages
    columns["expected_pages_min"] = pages.min if pages else None
    columns["expected_pages_max"] = pages.max if pages else None
    return columns


def row_to_record(row: KnownDocumentType) -> dict[str, Any]:
    """`known_document_types` satırı → doğrulanmamış §8.6 kaydı."""
    pages = None
    if row.expected_pages_min is not None or row.expected_pages_max is not None:
        pages = {"min": row.expected_pages_min, "max": row.expected_pages_max}
    return {
        "slug": row.slug,
        "name": row.name,
        "file_label": row.file_label,
        "country": row.country,
        "description": row.description,
        "expected_file_types": row.expected_file_types,
        "expected_pages": pages,
        "sides": row.sides,
        "direct": row.direct,
        "analyze": row.analyze,
        "required_fields": row.required_fields,
        "allowed_conversions": row.allowed_conversions,
        "output_format": row.output_format,
        "acceptance_criteria": row.acceptance_criteria,
        "prompt_description": row.prompt_description,
        "photo_rules": row.photo_rules,
        "active": row.active,
    }


def import_catalog(session: Session, catalog: Catalog) -> CatalogImportResult:
    """Kataloğu veritabanına yazar (YAML → DB)."""
    existing = {row.slug: row for row in session.scalars(select(KnownDocumentType))}
    created: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    for entry in catalog:
        columns = entry_to_columns(entry)
        row = existing.get(entry.slug)
        if row is None:
            session.add(KnownDocumentType(slug=entry.slug, **columns))
            created.append(entry.slug)
            continue
        changed = [key for key, value in columns.items() if getattr(row, key) != value]
        for key in changed:
            setattr(row, key, columns[key])
        (updated if changed else unchanged).append(entry.slug)
    session.flush()
    return CatalogImportResult(
        created=tuple(created),
        updated=tuple(updated),
        unchanged=tuple(unchanged),
        not_in_catalog=tuple(sorted(set(existing) - set(catalog.slugs()))),
    )


def export_catalog(session: Session) -> Catalog:
    """Veritabanındaki kataloğu okur (DB → YAML'ın ilk adımı)."""
    rows = session.scalars(select(KnownDocumentType).order_by(KnownDocumentType.slug))
    return validate_catalog([row_to_record(row) for row in rows])
