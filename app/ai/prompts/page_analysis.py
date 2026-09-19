"""Sayfa analizi sistem talimatı — PRD 03.4.1.

Talimat metni aynı dizindeki `page_analysis.md`'dir ve üç disiplin kuralını taşır: tahmin etme,
okuyamadığını `legible: false` yap, katalogda yoksa aday öner. Metin paketle birlikte gelir;
şablondaki tek `{{catalog}}` yuvasına analizde kullanılan kataloğun türleri yazılır.

- Katalog metnini prompt derleyicisi üretir (`app.catalog.prompt_builder.compile_catalog`, 11.4):
  yalnız etkin ve analiz edilen türler, slug sırasıyla, kompakt biçimde ve token bütçesi içinde.
- `PageAnalysisInstructions.known_slugs` talimattaki türlerin slug'larıdır ve isteğe
  (`PageAnalysisRequest.known_slugs`) aynen verilir: talimatta olmayan bir slug yanıt kabulünde
  reddedilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources

from app.catalog.prompt_builder import CATALOG_TOKEN_BUDGET, compile_catalog
from app.catalog.schema import Catalog

PROMPT_RESOURCE = "page_analysis.md"
CATALOG_SLOT = "{{catalog}}"


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


def build_page_analysis_instructions(
    catalog: Catalog,
    *,
    template: str | None = None,
    token_budget: int = CATALOG_TOKEN_BUDGET,
) -> PageAnalysisInstructions:
    """Kataloğu derleyip şablonun yuvasına yazar. `template` verilmezse paketteki şablon
    kullanılır; `token_budget` katalog metninin bütçesidir (11.4.2).

    Şablonda tam olarak bir `{{catalog}}` yuvası yoksa `PromptTemplateError`.
    """
    source = load_page_analysis_template() if template is None else template
    found = source.count(CATALOG_SLOT)
    if found != 1:
        raise PromptTemplateError(
            f"talimat şablonunda tek bir {CATALOG_SLOT} yuvası olmalı; bulunan: {found}"
        )
    compiled = compile_catalog(catalog, token_budget=token_budget)
    # Yuva bir kez bölünerek doldurulur: katalog metnindeki olası yuva dizgesi yeniden açılmaz.
    before, after = source.split(CATALOG_SLOT)
    return PageAnalysisInstructions(
        text=before + compiled.text + after, known_slugs=compiled.known_slugs
    )
