"""Bilinen belge türleri — eğitim modunun (11.9) yerleştirebileceği türler (PLAN.md §C86).

İnsan kararı (2026-09-26): bilinen belgeler = katalog türleri + hazır önerilen türler.

- **Önerilen tür kaydı.** `app/catalog/suggested_types.csv`: harici toplayıcı aracının ürettiği
  `data/KnownDocuments/_onerilen_turler.csv`'nin repodaki kopyası (`data/` git dışındadır).
  `utf-8-sig` okunur, baştaki `#` satırları yorumdur. Satır: `slug`, `onerilen_name`,
  `onerilen_file_label`, `country_iso3`, `country_iso2` (29 satırda boş: `EU`, `INT`, `KKTC`),
  `kaynak_tur` (kapalı tür sözlüğü: `pasaport`, `kimlik_karti`, `ehliyet` …), sayaçlar ve örnek
  klasörü. Yalnız tür adları taşır, kişisel değer yoktur.
- **Birleşim (`build_known_types`).** Katalog (`export_catalog`) ∪ önerilen kayıt. Slug çakışmasında
  katalog kazanır: ad, etiket, ülke (ISO2) ve katalog kaydı katalogdan gelir. Kataloğun kendi
  (`country_iso3`, `kaynak_tur`) alanı yoktur; bu çift açık eşlemeden (`CATALOG_KINDS`) gelir,
  eşlemesi olmayan katalog türü aynı slug'lı önerilen satırın çiftini alır (onaylanan aday türü
  önerilen slug'ı taşır, §C85), o da yoksa çiftsizdir (`work_permit`, `profile_picture`,
  `attachment`). Aynı slug'lı önerilen satırın adı katalog türüne ikinci ad olarak bağlanır.
- **Ad eşleşmesi (`KnownTypes.match_name`).** `normalize_type_name`: harf büyüklüğü (casefold),
  boşluk sadeleştirme, `licence` → `license`. Birden çok slug'a inen ad belirsizdir (ör. "Turkish
  Driving License": `turkish_driving_license` ve `turkish_international_driving_permit`) → eşleşme
  yok; tahmin edilmez.
- **Tür eşleşmesi (`KnownTypes.match_kind`).** (`country_iso3`, `kaynak_tur`) → tekil tür. Birden
  çok slug'a inen çift belirsizdir (RUS/`kimlik_karti`, TUR/`ehliyet`) → eşleşme yok.

Modül veritabanına yazmaz; `load_known_types` katalogu okur.
"""

from __future__ import annotations

import csv
import enum
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from types import MappingProxyType

from sqlalchemy.orm import Session

from app.catalog.schema import Catalog, CatalogEntry
from app.catalog.sync import export_catalog

SUGGESTED_TYPES_PACKAGE = "app.catalog"
SUGGESTED_TYPES_RESOURCE = "suggested_types.csv"
SUGGESTED_TYPES_COLUMNS = (
    "slug",
    "onerilen_name",
    "onerilen_file_label",
    "country_iso3",
    "country_iso2",
    "kaynak_tur",
    "ornek_sayisi",
    "referans_sayisi",
    "ornek_klasoru",
)
_COMMENT = "#"
_SLUG = re.compile(r"[a-z][a-z0-9_]{0,63}")
_DOC_KIND = re.compile(r"[a-z][a-z0-9_]*")
# ISO 3166-1 alpha-3 ve toplayıcının bölge kodları (`EU`, `INT`, `KKTC`).
_COUNTRY_ISO3 = re.compile(r"[A-Z]{2,4}")
_COUNTRY_ISO2 = re.compile(r"[A-Z]{2}")

CATALOG_KINDS: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        "russian_passport": ("RUS", "pasaport"),
        "serbian_driving_license": ("SRB", "ehliyet"),
        "serbian_passport": ("SRB", "pasaport"),
        "serbian_residence_card": ("SRB", "oturum_izni"),
        "turkish_passport": ("TUR", "pasaport"),
    }
)
"""Katalog türlerinin (`country_iso3`, `kaynak_tur`) çifti (§C86). `work_permit`, `profile_picture`
ve `attachment` bilinçli olarak eşlemesizdir: ülkeye ya da kimlik türüne bağlı değildir."""


class SuggestedTypesError(ValueError):
    """Önerilen tür kaydı okunamadı; mesaj satırı ve sorunu söyler."""


class KnownTypeSource(enum.StrEnum):
    """Bilinen türün kaynağı: katalog kaydı ya da hazır önerilen tür."""

    CATALOG = "catalog"
    SUGGESTED = "suggested"


@dataclass(frozen=True, slots=True)
class SuggestedTypeRow:
    """Önerilen tür kaydının bir satırı (sayaçlar ve örnek klasörü taşınmaz)."""

    slug: str
    name: str
    file_label: str
    country_iso3: str | None
    country_iso2: str | None
    doc_kind: str


@dataclass(frozen=True, slots=True)
class KnownType:
    """Eğitim modunun yerleştirebileceği bir tür. `entry` katalog türünün kaydıdır (dosya türü ve
    sayfa aralığı kuralları, 11.9.2); önerilen türde `None`."""

    slug: str
    name: str
    file_label: str
    source: KnownTypeSource
    country_iso2: str | None = None
    country_iso3: str | None = None
    doc_kind: str | None = None
    entry: CatalogEntry | None = field(default=None, compare=False)

    @property
    def in_catalog(self) -> bool:
        return self.source is KnownTypeSource.CATALOG


def normalize_type_name(name: str) -> str:
    """Tür adının karşılaştırma anahtarı: casefold, boşluk sadeleştirme, `licence` → `license`."""
    return " ".join(name.casefold().replace("licence", "license").split())


def _kind_key(country_iso3: str, doc_kind: str) -> tuple[str, str]:
    return country_iso3.strip().upper(), doc_kind.strip().casefold()


class KnownTypes:
    """Bilinen türler: slug sırasıyla gezilir, slug, ad ve (ülke, tür) ile aranır."""

    def __init__(
        self, types: Iterable[KnownType], *, aliases: Iterable[tuple[str, str]] = ()
    ) -> None:
        """`aliases` türe bağlanan ek adlardır: `(ad, slug)`."""
        self._types = {known.slug: known for known in sorted(types, key=lambda t: t.slug)}
        names: defaultdict[str, set[str]] = defaultdict(set)
        kinds: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
        for known in self._types.values():
            names[normalize_type_name(known.name)].add(known.slug)
            if known.country_iso3 and known.doc_kind:
                kinds[_kind_key(known.country_iso3, known.doc_kind)].add(known.slug)
        for name, slug in aliases:
            if slug in self._types:
                names[normalize_type_name(name)].add(slug)
        self._names = dict(names)
        self._kinds = dict(kinds)

    def __iter__(self) -> Iterator[KnownType]:
        return iter(self._types.values())

    def __len__(self) -> int:
        return len(self._types)

    def __contains__(self, slug: object) -> bool:
        return slug in self._types

    def get(self, slug: str) -> KnownType | None:
        return self._types.get(slug)

    @property
    def doc_kinds(self) -> frozenset[str]:
        """Bilinen türlerin `kaynak_tur` sözlüğü (yapay zekâ sınıflandırmasının kapalı kümesi)."""
        return frozenset(known.doc_kind for known in self if known.doc_kind)

    def match_name(self, name: str) -> KnownType | None:
        """Adı normalize edilince tek bir türe inen tür; eşleşme yoksa ya da belirsizse `None`."""
        return self._single(self._names.get(normalize_type_name(name)))

    def name_matches(self, name: str) -> tuple[KnownType, ...]:
        """Adı normalize edilince inen bütün türler, slug sırasıyla (belirsiz adda birden çok)."""
        slugs = self._names.get(normalize_type_name(name), set())
        return tuple(self._types[slug] for slug in sorted(slugs))

    def match_kind(self, country_iso3: str, doc_kind: str) -> KnownType | None:
        """(`country_iso3`, `kaynak_tur`) çifti tek bir türe inerse o tür; yoksa ya da belirsizse
        `None`."""
        return self._single(self._kinds.get(_kind_key(country_iso3, doc_kind)))

    def _single(self, slugs: set[str] | None) -> KnownType | None:
        if not slugs or len(slugs) > 1:
            return None
        (slug,) = slugs
        return self._types[slug]


def parse_suggested_types(text: str) -> tuple[SuggestedTypeRow, ...]:
    """Önerilen tür kaydının metnini okur ve doğrular; sorun varsa `SuggestedTypesError`."""
    lines = text.removeprefix("﻿").splitlines()
    first = 0
    while first < len(lines) and lines[first].startswith(_COMMENT):
        first += 1
    reader = csv.DictReader(lines[first:])
    if sorted(reader.fieldnames or ()) != sorted(SUGGESTED_TYPES_COLUMNS):
        raise SuggestedTypesError(
            f"Önerilen tür kaydının sütunları beklenenden farklı: {reader.fieldnames}"
        )
    rows: dict[str, SuggestedTypeRow] = {}
    for raw in reader:
        line = first + reader.line_num
        row = _row(raw, line)
        if row.slug in rows:
            raise SuggestedTypesError(f"satır {line}: slug tekrarlanıyor: {row.slug!r}")
        rows[row.slug] = row
    return tuple(rows.values())


def _row(raw: Mapping[str, str | None], line: int) -> SuggestedTypeRow:
    if None in raw:
        raise SuggestedTypesError(f"satır {line}: sütun sayısı başlıktan fazla")
    values = {key: (value or "").strip() for key, value in raw.items() if key is not None}
    problems = []
    if not _SLUG.fullmatch(values["slug"]):
        problems.append(f"geçersiz slug {values['slug']!r}")
    if not values["onerilen_name"] or not values["onerilen_file_label"]:
        problems.append("ad ya da dosya etiketi boş")
    if not _DOC_KIND.fullmatch(values["kaynak_tur"]):
        problems.append(f"geçersiz kaynak_tur {values['kaynak_tur']!r}")
    for column, pattern in (("country_iso3", _COUNTRY_ISO3), ("country_iso2", _COUNTRY_ISO2)):
        if values[column] and not pattern.fullmatch(values[column]):
            problems.append(f"geçersiz {column} {values[column]!r}")
    if problems:
        raise SuggestedTypesError(f"satır {line}: {'; '.join(problems)}")
    return SuggestedTypeRow(
        slug=values["slug"],
        name=values["onerilen_name"],
        file_label=values["onerilen_file_label"],
        country_iso3=values["country_iso3"] or None,
        country_iso2=values["country_iso2"] or None,
        doc_kind=values["kaynak_tur"],
    )


@cache
def load_suggested_types() -> tuple[SuggestedTypeRow, ...]:
    """Paketle gelen önerilen tür kaydı (`app/catalog/suggested_types.csv`)."""
    resource = resources.files(SUGGESTED_TYPES_PACKAGE).joinpath(SUGGESTED_TYPES_RESOURCE)
    return parse_suggested_types(resource.read_text(encoding="utf-8-sig"))


def build_known_types(
    catalog: Catalog, suggested: Sequence[SuggestedTypeRow] | None = None
) -> KnownTypes:
    """Katalog ∪ önerilen kayıt; `suggested` verilmezse paketle gelen kayıt kullanılır."""
    rows = {row.slug: row for row in (load_suggested_types() if suggested is None else suggested)}
    types = [_catalog_type(entry, rows.get(entry.slug)) for entry in catalog]
    aliases = [(rows[entry.slug].name, entry.slug) for entry in catalog if entry.slug in rows]
    types.extend(
        KnownType(
            slug=row.slug,
            name=row.name,
            file_label=row.file_label,
            source=KnownTypeSource.SUGGESTED,
            country_iso2=row.country_iso2,
            country_iso3=row.country_iso3,
            doc_kind=row.doc_kind,
        )
        for slug, row in rows.items()
        if catalog.get(slug) is None
    )
    return KnownTypes(types, aliases=aliases)


def _catalog_type(entry: CatalogEntry, row: SuggestedTypeRow | None) -> KnownType:
    country_iso3, doc_kind = CATALOG_KINDS.get(entry.slug) or (
        (row.country_iso3, row.doc_kind) if row is not None else (None, None)
    )
    return KnownType(
        slug=entry.slug,
        name=entry.name,
        file_label=entry.file_label,
        source=KnownTypeSource.CATALOG,
        country_iso2=entry.country,
        country_iso3=country_iso3,
        doc_kind=doc_kind,
        entry=entry,
    )


def load_known_types(session: Session) -> KnownTypes:
    """Veritabanındaki katalog ∪ paketle gelen önerilen kayıt."""
    return build_known_types(export_catalog(session))
