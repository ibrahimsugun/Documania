"""Sayfa analizi sistem talimatı — PRD 03.4.1 (fotoğraf kuralları: 11.7.1).

Talimat metni aynı dizindeki `page_analysis.md`'dir ve üç disiplin kuralını taşır: tahmin etme,
okuyamadığını `legible: false` yap, katalogda yoksa aday öner. Metin paketle birlikte gelir;
şablondaki tek `{{catalog}}` yuvasına analizde kullanılan kataloğun türleri yazılır.

- Katalog metnini prompt derleyicisi üretir (`app.catalog.prompt_builder.compile_catalog`, 11.4):
  yalnız etkin ve analiz edilen türler, slug sırasıyla, kompakt biçimde ve token bütçesi içinde.
- `PageAnalysisInstructions.known_slugs` talimattaki türlerin slug'larıdır ve isteğe
  (`PageAnalysisRequest.known_slugs`) aynen verilir: talimatta olmayan bir slug yanıt kabulünde
  reddedilir.
- `PageAnalysisInstructions.photo_rules` fotoğraf kontrolü (11.7.1) istenen türlerin aynı katalogdan
  okunan açık kurallarıdır (`enabled_photo_rules`, 11.6.1): talimattaki türlerden kural seti olanlar
  (`PHOTO_RULE_TYPES`) ve en az bir kuralı açık olanlar. Kurallar sayfa analizi talimatına girmez;
  analiz çalıştırıcısı o türde tanınan sayfa için ayrı bir fotoğraf kontrolü isteği yapar
  (`app.pipeline.analyze`). Talimat ve kurallar aynı anda aynı katalogdan alınır — plan da aynı
  katalogla üretilir (09.2.2, 06.6.2).
- `PageAnalysisInstructions.required_fields` talimattaki her türün zorunlu alanlarıdır (katalog
  sırasıyla; zorunlu alanı olmayan türde boş). Ucuz model ön elemesi (13.2.1) bir yanıtın kolay
  sayfa olup olmadığına bunlarla karar verir: zorunlu alanlar talimattakiyle aynı katalogdan okunur.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import resources
from types import MappingProxyType

from app.catalog.photo_rules import PHOTO_RULE_TYPES, PhotoRuleSetting, enabled_photo_rules
from app.catalog.prompt_builder import CATALOG_TOKEN_BUDGET, compile_catalog
from app.catalog.schema import Catalog

PROMPT_RESOURCE = "page_analysis.md"
CATALOG_SLOT = "{{catalog}}"


class PromptTemplateError(ValueError):
    """Talimat şablonu kullanılamaz: katalog yuvası yok veya birden fazla."""


@dataclass(frozen=True, slots=True)
class PageAnalysisInstructions:
    """Sistem talimatı ve talimattaki kataloğun slug'ları; ikisi birlikte isteğe verilir.

    `photo_rules` slug → o türün açık fotoğraf kuralları (katalog sırasıyla); anahtarı olmayan tür
    için fotoğraf kontrolü yapılmaz. `required_fields` slug → o türün zorunlu alanları (13.2.1);
    anahtarı olmayan türün zorunlu alanları bilinmiyor sayılır.
    """

    text: str = field(repr=False)
    known_slugs: frozenset[str]
    photo_rules: Mapping[str, tuple[PhotoRuleSetting, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    required_fields: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )


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
        text=before + compiled.text + after,
        known_slugs=compiled.known_slugs,
        photo_rules=photo_rules_by_type(catalog, compiled.known_slugs),
        required_fields=MappingProxyType(
            {
                entry.slug: tuple(entry.required_fields)
                for entry in catalog
                if entry.slug in compiled.known_slugs
            }
        ),
    )


def photo_rules_by_type(
    catalog: Catalog, known_slugs: frozenset[str]
) -> Mapping[str, tuple[PhotoRuleSetting, ...]]:
    """Talimattaki (`known_slugs`) fotoğraf türlerinin açık kuralları; kuralı açık olmayan tür
    girmez (11.7.1)."""
    rules: dict[str, tuple[PhotoRuleSetting, ...]] = {}
    for entry in catalog:
        if entry.slug in known_slugs and entry.slug in PHOTO_RULE_TYPES:
            enabled = enabled_photo_rules(entry.photo_rules)
            if enabled:
                rules[entry.slug] = enabled
    return MappingProxyType(rules)
