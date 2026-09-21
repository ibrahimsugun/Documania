"""Katalog kaydı sözleşmesi — PRD §8.6 (00.6.1).

Bir kayıt bir belge türüdür. Katalog **bütün olarak** doğrulanır: tek bir kayıt bile geçersizse
yükleme reddedilir, hiçbir kayıt kısmen alınmaz. Tutarlılık kuralları:

- `direct: true` olan türde `allowed_conversions` boştur (K3, R5) — Direkt Belge'de birleştirme
  ve format dönüşümü yapılmaz, yalnız tek kaynaktan sayfa çıkarılır.
- `analyze: false` olan türde `required_fields` boştur — analiz edilmeyen belgede okunaklılık
  (K1) değerlendirilemez.
- `front_back_layouts` (04.1.2, 11.1.2): `sides: front_back` türde en az bir düzen seçilidir,
  tek yüzlü türde liste boştur. `front_back` türün `expected_pages`'i düzenlerden türetilir ve
  kayıt onunla çelişemez: yalnız `separate` 2–2, yalnız `combined` 1–1, ikisi 1–2 (`layout_pages`).
- Slug katalogda tekildir; listelerde tekrar yoktur; `expected_pages.min <= max`.

`allowed_conversions` §20.3'teki dönüşüm işlemlerinin adlarını taşır (satır 3–6: `merge`,
`wrap_image`, `extract_image`, `render_image`). `passthrough` ve `extract` dönüşüm değildir,
her türde izinlidir ve listeye yazılmaz.
"""

from __future__ import annotations

import enum
from collections.abc import Iterator
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StrictBool,
    StrictInt,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.storage import SlugError, slugify


class CatalogError(ValueError):
    """Katalog reddedildi; `problems` her geçersiz alan için bir satır taşır."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("Katalog reddedildi:\n" + "\n".join(f"- {p}" for p in problems))


class FileType(enum.StrEnum):
    """Kaynak dosya biçimi (K2): PDF/JPEG/PNG analiz edilir, Word/Excel yalnız saklanır."""

    PDF = "pdf"
    JPEG = "jpeg"
    PNG = "png"
    DOC = "doc"
    DOCX = "docx"
    XLS = "xls"
    XLSX = "xlsx"


class Sides(enum.StrEnum):
    """Belgenin yüz yapısı; `front_back` türde ön ve arka yüz eşleşir (04.1.2)."""

    SINGLE = "single"
    FRONT_BACK = "front_back"


class FrontBackLayout(enum.StrEnum):
    """`front_back` türün kabul ettiği düzen (04.1.2, §8.6).

    `separate`: ön ve arka yüz ayrı sayfalarda (2 sayfa); `combined`: iki yüz tek sayfada (1 sayfa).
    Tek sayfadaki iki yüz ayrılmaz, kırpılmaz; sayfa olduğu gibi çıktı olur (K17).
    """

    SEPARATE = "separate"
    COMBINED = "combined"


# Düzenin sayfa sayısı; `front_back` türün `expected_pages`'i bunlardan türetilir.
LAYOUT_PAGE_COUNTS = {FrontBackLayout.SEPARATE: 2, FrontBackLayout.COMBINED: 1}


class Conversion(enum.StrEnum):
    """Türün izin verebileceği dönüşüm işlemleri (§20.3 satır 3–6, K12)."""

    MERGE = "merge"
    WRAP_IMAGE = "wrap_image"
    EXTRACT_IMAGE = "extract_image"
    RENDER_IMAGE = "render_image"


class OutputFormat(enum.StrEnum):
    """Çıktı biçimi; `keep` kaynağın biçimini korur (§20.3)."""

    KEEP = "keep"
    PDF = "pdf"
    JPEG = "jpeg"


Slug = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
FieldName = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]*$")]
Text = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
ShortText = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=255)
]
CountryCode = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Z]{2}$")]
PageCount = Annotated[StrictInt, Field(ge=1)]


def _unique[T](values: tuple[T, ...]) -> tuple[T, ...]:
    seen: set[T] = set()
    duplicates: dict[T, None] = {}
    for value in values:
        if value in seen:
            duplicates[value] = None
        seen.add(value)
    if duplicates:
        raise ValueError(f"Tekrarlanan değer: {', '.join(map(str, duplicates))}")
    return values


class PageRange(BaseModel):
    """Beklenen sayfa sayısı aralığı (kapalı aralık)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    min: PageCount
    max: PageCount

    @model_validator(mode="after")
    def _ordered(self) -> PageRange:
        if self.min > self.max:
            raise ValueError(f"expected_pages.min ({self.min}) max'tan ({self.max}) büyük olamaz")
        return self


def layout_pages(layouts: tuple[FrontBackLayout, ...]) -> PageRange | None:
    """`front_back` türün düzenlerinden türeyen sayfa aralığı; düzen yoksa `None`.

    Yalnız `separate` 2–2, yalnız `combined` 1–1, ikisi 1–2.
    """
    counts = [LAYOUT_PAGE_COUNTS[layout] for layout in layouts]
    return PageRange(min=min(counts), max=max(counts)) if counts else None


def _layout_names(layouts: tuple[FrontBackLayout, ...]) -> str:
    return ", ".join(layouts)


CONSISTENCY_ERROR = "catalog_consistency"


class CatalogEntry(BaseModel):
    """Tek belge türü — §8.6 alanları; veritabanı karşılığı `known_document_types` (§8.1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: Slug
    name: ShortText
    file_label: ShortText
    country: CountryCode | None = None
    description: Text | None = None
    expected_file_types: Annotated[tuple[FileType, ...], Field(min_length=1)]
    expected_pages: PageRange | None = None
    sides: Sides
    front_back_layouts: tuple[FrontBackLayout, ...] = ()
    direct: StrictBool
    analyze: StrictBool
    required_fields: tuple[FieldName, ...]
    allowed_conversions: tuple[Conversion, ...]
    output_format: OutputFormat
    acceptance_criteria: tuple[Text, ...] = ()
    prompt_description: Text | None = None
    photo_rules: dict[str, Any] | None = None
    active: StrictBool = True

    @field_validator(
        "expected_file_types", "front_back_layouts", "required_fields", "allowed_conversions"
    )
    @classmethod
    def _no_duplicates(cls, values: tuple[Any, ...]) -> tuple[Any, ...]:
        return _unique(values)

    @field_validator("file_label")
    @classmethod
    def _label_makes_file_name(cls, value: str) -> str:
        # Etiket çıktı adına girer (K8: `Ad_Soyad-Belge-Turu.pdf`); ad üretemeyen etiket geçersiz.
        try:
            slugify(value, "-")
        except SlugError as exc:
            raise ValueError(f"file_label dosya adına çevrilemiyor: {exc}") from None
        return value

    def consistency_problems(self) -> list[tuple[str, str]]:
        """Alanlar arası tutarlılık ihlalleri: `(alan, mesaj)` çiftleri, yoksa boş liste.

        Doğrulama tek hata fırlatabildiği için ihlaller tek `catalog_consistency` hatasında
        toplanır; panel formu (11.1.2) `ctx["problems"]`tan her ihlali kendi alanına yazar.
        """
        problems: list[tuple[str, str]] = []
        if self.direct and self.allowed_conversions:
            names = ", ".join(self.allowed_conversions)
            problems.append(
                (
                    "allowed_conversions",
                    f"Direkt Belge (direct: true) türünde allowed_conversions boş olmalı; "
                    f"verilen: {names}",
                )
            )
        if not self.analyze and self.required_fields:
            problems.append(
                ("required_fields", "analyze: false olan türde required_fields boş olmalı")
            )
        problems.extend(self._layout_problems())
        return problems

    def _layout_problems(self) -> list[tuple[str, str]]:
        # 04.1.2: düzen yalnız `front_back` türdedir ve o türün sayfa aralığını belirler.
        layouts = self.front_back_layouts
        if self.sides is not Sides.FRONT_BACK:
            if not layouts:
                return []
            return [
                (
                    "front_back_layouts",
                    "tek yüzlü (sides: single) türde kabul edilen düzen seçilmez, "
                    f"front_back_layouts boş olmalı; verilen: {_layout_names(layouts)}",
                )
            ]
        derived = layout_pages(layouts)
        if derived is None:
            return [
                (
                    "front_back_layouts",
                    "ön ve arka yüzlü (sides: front_back) türde en az bir kabul edilen düzen "
                    "seçilmeli: ayrı sayfalar (separate) ya da tek sayfa (combined)",
                )
            ]
        if self.expected_pages == derived:
            return []
        given = self.expected_pages
        return [
            (
                "expected_pages",
                "sides: front_back türünde expected_pages kabul edilen düzenlerden türetilir "
                f"({_layout_names(layouts)} → min: {derived.min}, max: {derived.max}); "
                f"verilen: {'yazılmamış' if given is None else f'{given.min}-{given.max}'}",
            )
        ]

    @model_validator(mode="after")
    def _consistent(self) -> CatalogEntry:
        problems = self.consistency_problems()
        if problems:
            raise PydanticCustomError(
                CONSISTENCY_ERROR,
                "{message}",
                {"message": "; ".join(text for _, text in problems), "problems": problems},
            )
        return self


class Catalog(RootModel[tuple[CatalogEntry, ...]]):
    """Belge türü kataloğunun tamamı; slug'lar tekildir."""

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _unique_slugs(self) -> Catalog:
        try:
            _unique(self.slugs())
        except ValueError as exc:
            raise ValueError(f"slug katalogda tekil olmalı. {exc}") from None
        return self

    def __iter__(self) -> Iterator[CatalogEntry]:  # type: ignore[override]
        return iter(self.root)

    def __len__(self) -> int:
        return len(self.root)

    def slugs(self) -> tuple[str, ...]:
        return tuple(entry.slug for entry in self.root)

    def get(self, slug: str) -> CatalogEntry | None:
        return next((entry for entry in self.root if entry.slug == slug), None)

    def unanalyzed_entry_for(self, file_type: FileType) -> CatalogEntry | None:
        """`analyze: false` olan ve `file_type`i `expected_file_types`de taşıyan kaydı döner.

        K2: Word/Excel gibi analiz edilmeyen türler sayfa analizinden değil, içerik türünden
        eşlenir (04.7.1). `analyze: true` türler bu eşlemeye girmez — onların türü sayfa
        analiziyle belirlenir.
        """
        return next(
            (
                entry
                for entry in self.root
                if not entry.analyze and file_type in entry.expected_file_types
            ),
            None,
        )


def validate_catalog(data: object) -> Catalog:
    """Ham kayıt listesini doğrular; tek kayıt bile geçersizse tüm katalog reddedilir."""
    if not isinstance(data, list | tuple):
        raise CatalogError([f"Katalog kökü kayıt listesi olmalı; gelen: {type(data).__name__}"])
    try:
        return Catalog.model_validate(data)
    except ValidationError as exc:
        raise CatalogError(_describe(exc, data)) from None


def _describe(exc: ValidationError, data: list[Any] | tuple[Any, ...]) -> list[str]:
    problems: list[str] = []
    for error in exc.errors():
        loc = list(error["loc"])
        where = "katalog"
        if loc and isinstance(loc[0], int):
            index = loc.pop(0)
            raw = data[index] if index < len(data) else None
            slug = raw.get("slug") if isinstance(raw, dict) else None
            where = f"kayıt #{index + 1}" + (f" ({slug})" if isinstance(slug, str) else "")
        field = ".".join(str(part) for part in loc)
        message = error["msg"].removeprefix("Value error, ")
        problems.append(f"{where}{' ' + field if field else ''}: {message}")
    return problems
