"""Sayfa analizi sistem talimatı — PRD 03.4.1.

Talimat metni aynı dizindeki `page_analysis.md`'dir ve üç disiplin kuralını taşır: tahmin etme,
okuyamadığını `legible: false` yap, katalogda yoksa aday öner. Metin paketle birlikte gelir;
şablondaki tek `{{catalog}}` yuvasına analizde kullanılan kataloğun türleri yazılır.

- Talimata yalnız etkin (`active: true`) ve analiz edilen (`analyze: true`) türler girer:
  Word/Excel türü (`attachment`) analize hiç gönderilmez (K2), pasif tür yeni belgeye atanmaz.
  Türler slug sırasıyla yazılır; aynı katalog her zaman aynı metni üretir.
- `PageAnalysisInstructions.known_slugs` talimattaki türlerin slug'larıdır ve isteğe
  (`PageAnalysisRequest.known_slugs`) aynen verilir: talimatta olmayan bir slug yanıt kabulünde
  reddedilir.
- Katalog burada sade bir listeye çevrilir (`render_catalog_section`). Kompakt derleme ve token
  bütçesi 11.4'ün işidir; yuva sözleşmesi aynı kalır.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import resources

from app.catalog.schema import Catalog, CatalogEntry, Sides

PROMPT_RESOURCE = "page_analysis.md"
CATALOG_SLOT = "{{catalog}}"

NO_TYPES_TEXT = (
    "_Katalogda analiz edilen etkin tür yok: her sayfada `document_type_slug` `null` olur ve "
    "kural 3 uygulanır._"
)

_SIDES_TEXT = {
    Sides.SINGLE: "tek yüz (`single`) — sayfanın `side` değeri `single`",
    Sides.FRONT_BACK: "ön ve arka yüz (`front_back`) — her sayfa `front` veya `back`",
}


class PromptTemplateError(ValueError):
    """Talimat şablonu kullanılamaz: katalog yuvası yok veya birden fazla."""


@dataclass(frozen=True, slots=True)
class PageAnalysisInstructions:
    """Sistem talimatı ve talimattaki kataloğun slug'ları; ikisi birlikte isteğe verilir."""

    text: str = field(repr=False)
    known_slugs: frozenset[str]


def load_page_analysis_template() -> str:
    """Paketle gelen talimat şablonunun metni (yuva doldurulmamış)."""
    return resources.files(__package__).joinpath(PROMPT_RESOURCE).read_text(encoding="utf-8")


def analyzable_types(catalog: Catalog) -> tuple[CatalogEntry, ...]:
    """Talimata giren türler: etkin ve analiz edilen, slug sırasıyla."""
    entries = (entry for entry in catalog if entry.active and entry.analyze)
    return tuple(sorted(entries, key=lambda entry: entry.slug))


def render_catalog_section(entries: Iterable[CatalogEntry]) -> str:
    """Türleri talimatın katalog bölümüne yazar; tür yoksa bunu açıkça söyler."""
    blocks = [_render_entry(entry) for entry in entries]
    return "\n\n".join(blocks) if blocks else NO_TYPES_TEXT


def build_page_analysis_instructions(
    catalog: Catalog, *, template: str | None = None
) -> PageAnalysisInstructions:
    """Kataloğu şablonun yuvasına yazar. `template` verilmezse paketteki şablon kullanılır.

    Şablonda tam olarak bir `{{catalog}}` yuvası yoksa `PromptTemplateError`.
    """
    source = load_page_analysis_template() if template is None else template
    found = source.count(CATALOG_SLOT)
    if found != 1:
        raise PromptTemplateError(
            f"talimat şablonunda tek bir {CATALOG_SLOT} yuvası olmalı; bulunan: {found}"
        )
    entries = analyzable_types(catalog)
    # Yuva bir kez bölünerek doldurulur: katalog metnindeki olası yuva dizgesi yeniden açılmaz.
    before, after = source.split(CATALOG_SLOT)
    return PageAnalysisInstructions(
        text=before + render_catalog_section(entries) + after,
        known_slugs=frozenset(entry.slug for entry in entries),
    )


def _render_entry(entry: CatalogEntry) -> str:
    lines = [
        f"### `{entry.slug}` — {_one_line(entry.name)}",
        f"- Ülke: {entry.country or 'belirtilmemiş'}",
        f"- Yüz yapısı: {_SIDES_TEXT[entry.sides]}",
    ]
    if entry.expected_pages is not None:
        low, high = entry.expected_pages.min, entry.expected_pages.max
        lines.append(f"- Beklenen sayfa sayısı: {low if low == high else f'{low}–{high}'}")
    if entry.required_fields:
        names = ", ".join(f"`{name}`" for name in entry.required_fields)
        lines.append(f"- Zorunlu alanlar: {names}")
    else:
        lines.append("- Zorunlu alanlar: yok (`fields` boş nesne)")
    description = entry.prompt_description or entry.description
    if description is not None:
        lines.append(f"- Tanım: {_one_line(description)}")
    if entry.acceptance_criteria:
        lines.append("- Kabul kriterleri:")
        lines.extend(f"  - {_one_line(criterion)}" for criterion in entry.acceptance_criteria)
    return "\n".join(lines)


def _one_line(text: str) -> str:
    # Katalog metni (YAML `>` blokları dahil) talimatın liste yapısını bozmasın.
    return " ".join(text.split())
