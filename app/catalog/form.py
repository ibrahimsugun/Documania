"""Katalog tür formu — ham form değerlerinden doğrulanmış `CatalogEntry` (11.1.2, 11.1.3).

Panelin tür formu (`app/web/routers/catalog.py`) yalnız metin gönderir; bu modül metni §8.6
kaydına çevirir ve **aynı** `CatalogEntry` sözleşmesinden geçirir: form ile YAML/veritabanı iki ayrı
kural kümesi taşımaz. Doğrulama sonucu alan alan bildirilir (`TypeFormError.problems`), böylece
form her mesajı kendi alanının yanında gösterebilir:

- Direkt türde (`direct: true`) dönüşüm listesi boş olmalıdır (K3, R5) — katalog şemasının kuralı;
- `analyze: false` türde zorunlu alan listesi boştur — katalog şemasının kuralı;
- `front_back` türde en az bir kabul edilen düzen seçilidir ("Ön ve arka ayrı sayfalarda",
  "İki yüz tek sayfada"); tek yüzlü türde düzen seçilmez — katalog şemasının kuralı (04.1.2).
  `front_back` türün sayfa aralığı elle girilmez: düzenlerden hesaplanır (ayrı sayfalar 2, tek
  sayfa 1; ikisi 1–2, `layout_pages`), formdaki sayfa alanları o türde okunmaz (PLAN.md §C78).

`acceptance_criteria` (11.1.3) formda madde madde düzenlenir; boş bırakılan madde kaydedilmez.
Form yalnız kayıt alanlarını taşır — `active` (pasifleştirme ayrı işlemdir) ve `photo_rules` (11.6)
formdan değişmez.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.catalog.schema import CONSISTENCY_ERROR, CatalogEntry, FrontBackLayout, layout_pages

# Zorunlu alan adları tek satırda virgülle (ya da boşlukla/satırla) yazılır.
# `new` panelde yeni tür formunun adresidir (`/document-types/new`): bu slug'la tür açılamaz.
RESERVED_SLUGS = frozenset({"new"})
_FIELD_SEPARATOR = re.compile(r"[\s,;]+")


class TypeFormError(ValueError):
    """Form reddedildi; `problems` alan adı → mesajlar (alan adı `CatalogEntry` alanıdır)."""

    def __init__(self, problems: dict[str, list[str]]) -> None:
        self.problems = problems
        lines = [f"- {name}: {text}" for name, texts in problems.items() for text in texts]
        super().__init__("Tür formu reddedildi:\n" + "\n".join(lines))


@dataclass(frozen=True, slots=True)
class TypeForm:
    """Formun ham değerleri (doğrulanmamış); hata olursa sayfaya aynen geri yazılır.

    Varsayılanlar yeni tür formunun açılış değerleridir.
    """

    slug: str = ""
    name: str = ""
    file_label: str = ""
    country: str = ""
    description: str = ""
    expected_file_types: tuple[str, ...] = ("pdf",)
    pages_min: str = ""
    pages_max: str = ""
    sides: str = "single"
    front_back_layouts: tuple[str, ...] = ()
    direct: bool = False
    analyze: bool = True
    required_fields: str = ""
    allowed_conversions: tuple[str, ...] = ()
    output_format: str = "keep"
    acceptance_criteria: tuple[str, ...] = ()
    prompt_description: str = ""

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> TypeForm:
        """Kayıtlı türün form değerleri (düzenleme formunun açılışı).

        `record` doğrulanmamış §8.6 kaydıdır (`row_to_record`): tutarsız kayıtlı tür de formda
        açılır, böylece formun kendisi onu düzeltmenin yolu olur.
        """
        pages = record.get("expected_pages") or {}
        return cls(
            slug=str(record["slug"]),
            name=str(record.get("name") or ""),
            file_label=str(record.get("file_label") or ""),
            country=str(record.get("country") or ""),
            description=str(record.get("description") or ""),
            expected_file_types=tuple(map(str, record.get("expected_file_types") or ())),
            pages_min="" if pages.get("min") is None else str(pages["min"]),
            pages_max="" if pages.get("max") is None else str(pages["max"]),
            sides=str(record.get("sides") or ""),
            front_back_layouts=tuple(map(str, record.get("front_back_layouts") or ())),
            direct=bool(record.get("direct")),
            analyze=bool(record.get("analyze")),
            required_fields=", ".join(map(str, record.get("required_fields") or ())),
            allowed_conversions=tuple(map(str, record.get("allowed_conversions") or ())),
            output_format=str(record.get("output_format") or ""),
            acceptance_criteria=tuple(map(str, record.get("acceptance_criteria") or ())),
            prompt_description=str(record.get("prompt_description") or ""),
        )


def clean_criteria(items: Iterable[str]) -> tuple[str, ...]:
    """Kabul kriteri maddelerini kırpar ve boş olanları atar (11.1.3: boş satır madde değildir)."""
    return tuple(text for item in items if (text := item.strip()))


def split_field_names(text: str) -> tuple[str, ...]:
    """Form metnini alan adlarına böler; sıra korunur, boş parça atılır."""
    return tuple(name for name in _FIELD_SEPARATOR.split(text.strip()) if name)


def _optional(text: str) -> str | None:
    return text.strip() or None


def _pages(form: TypeForm, problems: dict[str, list[str]]) -> dict[str, int] | None:
    low, high = form.pages_min.strip(), form.pages_max.strip()
    if not low and not high:
        return None
    if not low or not high:
        problems.setdefault("expected_pages", []).append(
            "en az ve en çok sayfa birlikte yazılmalı (ya da ikisi de boş bırakılmalı)"
        )
        return None
    if not (low.isascii() and low.isdigit() and high.isascii() and high.isdigit()):
        problems.setdefault("expected_pages", []).append("sayfa sayıları tam sayı olmalı")
        return None
    return {"min": int(low), "max": int(high)}


def _layout_pages(form: TypeForm) -> dict[str, int] | None:
    """`front_back` türün sayfa aralığı, seçilen düzenlerden (11.1.2). Düzen seçilmemişse ya da
    tanımsız bir düzen gönderilmişse aralık yoktur; hatayı düzen alanı söyler."""
    known = set(FrontBackLayout)
    if not all(value in known for value in form.front_back_layouts):
        return None
    derived = layout_pages(tuple(FrontBackLayout(value) for value in form.front_back_layouts))
    return None if derived is None else derived.model_dump()


def _record(form: TypeForm, problems: dict[str, list[str]]) -> dict[str, Any]:
    """Form → §8.6 kaydı (doğrulanmamış). Kırpma ve boş → yok dönüşümü yalnız burada yapılır."""
    slug = form.slug.strip()
    if slug in RESERVED_SLUGS:
        problems.setdefault("slug", []).append(f"{slug!r} ayrılmış bir ad; başka bir slug seçin")
    front_back = form.sides == "front_back"
    return {
        "slug": slug,
        "name": form.name,
        "file_label": form.file_label,
        "country": _optional(form.country.upper()),
        "description": _optional(form.description),
        "expected_file_types": list(form.expected_file_types),
        "expected_pages": _layout_pages(form) if front_back else _pages(form, problems),
        "sides": form.sides,
        "front_back_layouts": list(form.front_back_layouts),
        "direct": form.direct,
        "analyze": form.analyze,
        "required_fields": list(split_field_names(form.required_fields)),
        "allowed_conversions": list(form.allowed_conversions),
        "output_format": form.output_format,
        "acceptance_criteria": list(clean_criteria(form.acceptance_criteria)),
        "prompt_description": _optional(form.prompt_description),
    }


def _message(name: str, error: Any) -> str:
    """Pydantic hatasını Türkçe, alanın yanında okunacak bir cümleye çevirir."""
    kind = error["type"]
    ctx = error.get("ctx") or {}
    if kind == "too_short":
        return "en az bir seçim yapılmalı"
    if kind == "string_too_short":
        return "boş olamaz"
    if kind == "string_too_long":
        return f"en çok {ctx.get('max_length')} karakter olmalı"
    if kind == "string_pattern_mismatch":
        return {
            "slug": "küçük harfle başlamalı; yalnız a-z, 0-9 ve _ içerebilir (en çok 64 karakter)",
            "country": "iki büyük harf olmalı (ör. RU)",
            "required_fields": (
                f"geçersiz alan adı {error['input']!r}: küçük harfle başlamalı; "
                "yalnız a-z, 0-9 ve _ içerebilir"
            ),
        }.get(name, "geçerli biçimde değil")
    if kind in {"enum", "literal_error"}:
        return "geçersiz seçim"
    return str(error["msg"]).removeprefix("Value error, ")


def _describe(exc: ValidationError) -> dict[str, list[str]]:
    problems: dict[str, list[str]] = {}
    for error in exc.errors():
        if error["type"] == CONSISTENCY_ERROR:
            for name, message in error["ctx"]["problems"]:
                problems.setdefault(name, []).append(message)
            continue
        name = str(error["loc"][0]) if error["loc"] else "form"
        problems.setdefault(name, []).append(_message(name, error))
    return problems


def build_entry(form: TypeForm) -> CatalogEntry:
    """Formu doğrulanmış kayda çevirir; geçersizse `TypeFormError` (hiçbir şey yazılmaz)."""
    problems: dict[str, list[str]] = {}
    record = _record(form, problems)
    try:
        entry = CatalogEntry.model_validate(record)
    except ValidationError as exc:
        # Sayfa sayıları okunamadıysa o alanın asıl sorunu budur; aralık yokmuş gibi türeyen
        # tutarlılık mesajı onu gölgelemesin.
        for name, messages in _describe(exc).items():
            problems.setdefault(name, messages)
        raise TypeFormError(problems) from None
    if problems:
        raise TypeFormError(problems)
    return entry
