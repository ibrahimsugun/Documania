"""Katalog prompt derleyicisi ve token bütçesi — PRD 11.4.1, 11.4.2.

Analiz talimatının `{{catalog}}` yuvasına giren metin burada üretilir (`compile_catalog`).

- **Hangi türler:** yalnız etkin (`active: true`), arşivsiz (`archived_at` boş, 11.1.6) ve analiz
  edilen (`analyze: true`) türler, slug sırasıyla — aynı katalog her zaman aynı metni üretir.
  Word/Excel türü (`attachment`) analize gitmez (K2), pasif ya da arşivli tür yeni belgeye atanmaz.
- **Kompakt biçim:** tür başına bir başlık (`### `slug` — Ad`) ve kısa satırlar: ülke, yüz yapısı,
  `front_back` türde kabul edilen düzenler (04.1.2) ve beklenen sayfa tek satırda; zorunlu alanlar;
  tanım (`prompt_description`, yoksa `description`); kabul kriterleri madde madde. Yüz değerlerinin
  anlamı talimatın "Yanıt alanları" bölümünde bir kez yazılıdır, tür başına tekrarlanmaz; bilinmeyen
  ülke satıra girmez.
- **Token bütçesi:** metnin tahmini token sayısı (`estimate_tokens`) bütçeyi aşarsa yalnız
  **tanımlar** kısaltılır: bütün tanımlara ortak bir karakter sınırı konur, sınırı aşan tanım kelime
  sınırında kesilip `…` ile biter, hiç kelimesi sığmayan tanımın satırı düşer. Metnin bütçeye
  sığdığı en büyük sınır seçilir — önce en uzun tanımlar kısalır. Slug, ad, yüz yapısı, zorunlu
  alanlar ve kabul kriterleri kısaltılmaz ve hiçbir tür düşürülmez: talimat karşılanmayan kabul
  kriterini kelimesi kelimesine ister (04.4.2), `fields` anahtarları zorunlu alan adlarıdır ve
  talimatta olmayan tür tanınamaz. Kısaltma olduğunda uyarı loglanır; bütün tanımlar düşse de metin
  sığmıyorsa metin yine eksiksiz türlerle döner ve uyarı bunu ayrıca söyler.
- **Etkin bütçe (11.4.3):** analiz yolu bütçeyi `effective_token_budget`'tan alır. Ayar
  (`CATALOG_TOKEN_BUDGET`) verilmişse aynen kullanılır; verilmemişse bütçe aktif analiz edilen tür
  sayısıyla ölçeklenir — `max(CATALOG_TOKEN_BUDGET, TOKENS_PER_TYPE × tür sayısı)` — böylece her
  türün tanımı kesilmeden girer ve büyüyen küme bedelini Belge Türleri sayfasında gösterir.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.catalog.schema import Catalog, CatalogEntry, FrontBackLayout

logger = logging.getLogger(__name__)

CATALOG_TOKEN_BUDGET = 4000
"""Katalog metninin varsayılan token bütçesi (tahmini token, `estimate_tokens`); ölçekli bütçenin
alt sınırı (11.4.3)."""

TOKENS_PER_TYPE = 200
"""Ölçekli bütçede tür başına pay (11.4.3): bir türün başlık, yüz yapısı, zorunlu alan, tanım ve
kriter satırları ~150 tahmini tokendır; pay bunun üstünde bırakılır (bkz. PLAN.md §C88; uzun
tanımlı gerçek katalogdaki ölçüm §D60)."""

BYTES_PER_TOKEN = 3
"""Tahminde bir tokene düşen UTF-8 bayt. Gerçek tokenlaştırıcıdan temkinli (fazla) sayar:
İngilizce metin ~4, Türkçe ~3, Kiril ~2 karakter/token'dır; Latin olmayan harf 2 bayttır."""

ELLIPSIS = "…"

# `front_back` türün kabul ettiği düzenlerin talimattaki adı (04.1.2).
LAYOUT_TEXTS = {
    FrontBackLayout.SEPARATE: "ön ve arka ayrı sayfalarda (`separate`)",
    FrontBackLayout.COMBINED: "iki yüz tek sayfada (`combined`)",
}

NO_TYPES_TEXT = (
    "_Katalogda analiz edilen etkin tür yok: her sayfada `document_type_slug` `null` olur ve "
    "kural 3 uygulanır._"
)


@dataclass(frozen=True, slots=True)
class CompiledCatalog:
    """Derlenen katalog metni ve bütçe sonucu.

    `known_slugs` metindeki türlerin slug'larıdır; `shortened_slugs` tanımı kısaltılan (veya
    düşen) türler, slug sırasıyla — boşsa metin kısaltılmamıştır.
    """

    text: str = field(repr=False)
    known_slugs: frozenset[str]
    estimated_tokens: int
    token_budget: int
    shortened_slugs: tuple[str, ...] = ()

    @property
    def over_budget(self) -> bool:
        """Tanımlar kısaltıldığı (gerekirse düştüğü) hâlde metin bütçeye sığmadı."""
        return self.estimated_tokens > self.token_budget


def estimate_tokens(text: str) -> int:
    """Metnin tahmini token sayısı: UTF-8 bayt / `BYTES_PER_TOKEN`, yukarı yuvarlanmış."""
    return math.ceil(len(text.encode("utf-8")) / BYTES_PER_TOKEN)


def analyzable_types(catalog: Catalog) -> tuple[CatalogEntry, ...]:
    """Talimata giren türler: etkin, arşivsiz (11.1.6) ve analiz edilen, slug sırasıyla."""
    entries = (
        entry for entry in catalog if entry.active and entry.archived_at is None and entry.analyze
    )
    return tuple(sorted(entries, key=lambda entry: entry.slug))


def effective_token_budget(catalog: Catalog, configured: int | None = None) -> int:
    """Katalog metninin etkin bütçesi (11.4.3): `configured` (`Settings.catalog_token_budget`)
    verilmişse o; yoksa `max(CATALOG_TOKEN_BUDGET, TOKENS_PER_TYPE × analiz edilen etkin tür)`."""
    if configured is not None:
        return configured
    return max(CATALOG_TOKEN_BUDGET, TOKENS_PER_TYPE * len(analyzable_types(catalog)))


def compile_catalog(
    catalog: Catalog, *, token_budget: int = CATALOG_TOKEN_BUDGET, warn: bool = True
) -> CompiledCatalog:
    """Aktif türleri kompakt katalog metnine derler; bütçe aşılırsa tanımları kısaltır.

    `warn=False` kısaltma uyarısını loglamaz: talimat kurulmadan yalnız durum gösterilirken
    (Belge Türleri sayfası, 11.4.3) her istek aynı uyarıyı yinelemesin."""
    if token_budget < 1:
        raise ValueError(f"katalog token bütçesi pozitif olmalı; verilen: {token_budget}")
    entries = analyzable_types(catalog)
    descriptions = tuple(_description(entry) for entry in entries)
    text = _render(entries, descriptions)
    estimated = estimate_tokens(text)
    shortened: tuple[str, ...] = ()
    if estimated > token_budget:
        full_estimate = estimated
        limit = _largest_fitting_limit(entries, descriptions, token_budget)
        cut = tuple(_shorten(description, limit) for description in descriptions)
        shortened = tuple(
            entry.slug
            for entry, before, after in zip(entries, descriptions, cut, strict=True)
            if before != after
        )
        text = _render(entries, cut)
        estimated = estimate_tokens(text)
        if warn:
            _warn(full_estimate, estimated, token_budget, shortened)
    return CompiledCatalog(
        text=text,
        known_slugs=frozenset(entry.slug for entry in entries),
        estimated_tokens=estimated,
        token_budget=token_budget,
        shortened_slugs=shortened,
    )


def _description(entry: CatalogEntry) -> str | None:
    description = entry.prompt_description or entry.description
    return None if description is None else _one_line(description)


def _largest_fitting_limit(
    entries: Sequence[CatalogEntry], descriptions: Sequence[str | None], token_budget: int
) -> int:
    # Metin boyu tanım sınırıyla azalmadan büyür; sınır = en uzun tanım kısaltmasız metindir ve
    # bütçeyi aştığı bilinir. Bütçeye sığan en büyük sınır aranır; hiçbiri sığmıyorsa 0 (bütün
    # tanımlar düşer).
    fits, too_long = 0, max((len(d) for d in descriptions if d is not None), default=0)
    while too_long - fits > 1:
        middle = (fits + too_long) // 2
        cut = [_shorten(description, middle) for description in descriptions]
        if estimate_tokens(_render(entries, cut)) <= token_budget:
            fits = middle
        else:
            too_long = middle
    return fits


def _shorten(description: str | None, limit: int) -> str | None:
    """Tanımı en çok `limit` karaktere kelime sınırında kısaltır; hiç kelime sığmazsa `None`."""
    if description is None or len(description) <= limit:
        return description
    kept = ""
    for word in description.split(" "):
        candidate = f"{kept} {word}" if kept else word
        if len(candidate) + len(ELLIPSIS) > limit:
            break
        kept = candidate
    kept = kept.rstrip(",;:")
    return kept + ELLIPSIS if kept else None


def _render(entries: Sequence[CatalogEntry], descriptions: Sequence[str | None]) -> str:
    blocks = [
        _render_entry(entry, description)
        for entry, description in zip(entries, descriptions, strict=True)
    ]
    return "\n\n".join(blocks) if blocks else NO_TYPES_TEXT


def _render_entry(entry: CatalogEntry, description: str | None) -> str:
    facts = [f"Ülke: {entry.country}"] if entry.country else []
    facts.append(f"Yüz yapısı: `{entry.sides}`")
    if entry.front_back_layouts:
        layouts = ", ".join(LAYOUT_TEXTS[layout] for layout in entry.front_back_layouts)
        facts.append(f"Kabul edilen düzenler: {layouts}")
    if entry.expected_pages is not None:
        low, high = entry.expected_pages.min, entry.expected_pages.max
        facts.append(f"Beklenen sayfa: {low if low == high else f'{low}–{high}'}")
    required = ", ".join(f"`{name}`" for name in entry.required_fields) or "yok"
    lines = [
        f"### `{entry.slug}` — {_one_line(entry.name)}",
        f"- {' · '.join(facts)}",
        f"- Zorunlu alanlar: {required}",
    ]
    if description is not None:
        lines.append(f"- Tanım: {description}")
    if entry.acceptance_criteria:
        lines.append("- Kabul kriterleri:")
        lines.extend(f"  - {_one_line(criterion)}" for criterion in entry.acceptance_criteria)
    return "\n".join(lines)


def _warn(
    full_estimate: int, estimated: int, token_budget: int, shortened: tuple[str, ...]
) -> None:
    names = ", ".join(shortened) or "yok"
    if estimated <= token_budget:
        logger.warning(
            "Katalog metni token bütçesini aştı (tahmini %d > %d): %d türün tanımı kısaltıldı "
            "(%s); derlenen metin tahmini %d token.",
            full_estimate,
            token_budget,
            len(shortened),
            names,
            estimated,
        )
    else:
        logger.warning(
            "Katalog metni token bütçesini aştı (tahmini %d > %d): %d türün tanımı kısaltıldı "
            "(%s); tanımlar düştüğü hâlde metin tahmini %d token, bütçeye sığmıyor.",
            full_estimate,
            token_budget,
            len(shortened),
            names,
            estimated,
        )


def _one_line(text: str) -> str:
    # Katalog metni (YAML `>` blokları dahil) talimatın liste yapısını bozmasın.
    return " ".join(text.split())
