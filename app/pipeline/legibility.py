"""Zorunlu alan okunaklılık kapısı ve kabul kriteri değerlendirmesi — PRD 04.4.1, 04.4.2.

Katalog türündeki bir belge adayı (04.1–04.3) iki ölçütle değerlendirilir:

1. **Zorunlu alan okunaklılığı (R1, K1).** Türün `required_fields` listesindeki her alan adayın en
   az bir sayfasında okunaklıysa ölçüt sağlanır. Sayfa analizi alanları sayfa başına yazar ve o
   sayfada bulunmayan alanı (ör. kartın öteki yüzündekini) `legible: false` okur (03.4); okumalar bu
   yüzden adayın sayfaları üzerinden birleştirilir. Okunaklı okuma yalnız yanıtı kendi sayfasını
   okunabilir (`is_readable: true`) ve boş olmayan diye veren sayfadan sayılır: sayfanın bütün
   olarak okunamadığını söyleyen yanıttaki okunaklı alan çelişkidir, ona güvenilmez (R7). Hiçbir
   sayfada okunaklı olmayan ya da hiç yazılmamış zorunlu alan okunamayan alandır; biri bile varsa
   aday Unreadable'a gider ve gerekçe alan adlarını katalogdaki sırasıyla yazar
   (`Okunamayan alanlar: document_number`). Ayrı bir güven skoru yoktur: `is_readable` tek başına
   rota vermez, zorunlu alanı olmayan türde ölçüt her zaman sağlanır.
2. **Kabul kriterleri (04.4.2).** Türün `acceptance_criteria` maddeleri analizciye tür tanımıyla
   verilir (03.4) ve analizci bir sayfada açıkça karşılanmayan maddeyi `notes`'a katalogda yazıldığı
   gibi yazar; §8.4'te maddeler için ayrı bir alan yoktur. Madde, adayın herhangi bir sayfasının
   notunda kelimesi kelimesine geçiyorsa karşılanmamıştır. Karşılaştırma kelime dizisiyle yapılır:
   harf büyüklüğü, aksan, noktalama ve boşluk farkı yok sayılır; notlar sayfa sayfa aranır. Bir
   madde daha uzun bir maddenin içinde geçebilir: uzun maddenin eşleştiği yerin içinde kalan kısa
   madde ayrıca sayılmaz. Notta geçmeyen madde karşılanmış sayılır — analizciye yalnız açıkça
   karşılanmayanı yazması söylenir. Karşılanmayan madde varsa aday Unresolved'a gider ve gerekçe
   maddeleri adıyla (katalogdaki metin, tek satır) yazar. Liste boşsa tek ölçüt 1'dir.

İki ölçüt her zaman birlikte değerlendirilir; ikisi de sağlanmıyorsa kuyruk Unreadable'dır: K1
kabulün tek ölçütüdür, kabul kriterleri onun ötesindeki koşullardır (§8.6). Katalog dışı, türü
belirlenemeyen ya da slug'ı katalogda olmayan aday değerlendirilmez — zorunlu alanları bilinmez,
rotası 04.6'nındır.

Hüküm adayın sayfalarının bütün bir belge olduğu varsayımıyla verilir; eksik ya da parça adayın
yapısal hükmüyle (04.2, 04.3.2, 04.5) sırası planın (06.1) işidir. Modül saf işlevdir: veritabanına
ve olay loguna yazmaz, hüküm plana (K9) ve kuyruk kaydına (08.1) oradan geçer.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import ClassVar

from app.ai.schemas import PageAnalysis
from app.catalog import Catalog
from app.db.models import QueueKind
from app.pipeline.group import DocumentCandidate

_NON_WORD = re.compile(r"[\W_]+")
_Words = tuple[str, ...]
_Span = tuple[int, int]


@dataclass(frozen=True, slots=True)
class IllegibleRequiredFields:
    """R1 (K1): türün zorunlu alanlarından en az biri adayın hiçbir sayfasında okunaklı değil.

    `fields` okunamayan alan adlarıdır, katalogdaki `required_fields` sırasıyla.
    """

    rule: ClassVar[str] = "R1"
    queue: ClassVar[QueueKind] = QueueKind.UNREADABLE

    fields: tuple[str, ...]

    @property
    def reason(self) -> str:
        """Okunamayan alan adları; değer taşımaz."""
        return f"Okunamayan alanlar: {', '.join(self.fields)}"


@dataclass(frozen=True, slots=True)
class UnmetAcceptanceCriteria:
    """04.4.2: türün kabul kriterlerinden en az biri adayın bir sayfasında karşılanmıyor.

    `criteria` karşılanmayan maddelerin katalogdaki metnidir (tek satır), katalog sırasıyla.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED

    criteria: tuple[str, ...]

    @property
    def reason(self) -> str:
        """Karşılanmayan maddeler adlarıyla; madde katalog metnidir, kişisel değer taşımaz."""
        names = "; ".join(f'"{criterion}"' for criterion in self.criteria)
        return f"Karşılanmayan kabul kriterleri: {names}"


@dataclass(frozen=True, slots=True)
class LegibilityCheck:
    """Katalog türündeki adayın okunaklılık ve kabul kriteri hükmü.

    İki alan da boşsa aday kabul edilir. Kuyruk ve gerekçe öncelikli hükmündür: önce zorunlu alan
    okunaklılığı (Unreadable), sonra kabul kriterleri (Unresolved); öteki hüküm alanında kalır.
    """

    document_type_slug: str
    illegible_fields: IllegibleRequiredFields | None = None
    unmet_criteria: UnmetAcceptanceCriteria | None = None

    @property
    def accepted(self) -> bool:
        return self.illegible_fields is None and self.unmet_criteria is None

    @property
    def queue(self) -> QueueKind | None:
        verdict = self._verdict
        return None if verdict is None else verdict.queue

    @property
    def reason(self) -> str | None:
        verdict = self._verdict
        return None if verdict is None else verdict.reason

    @property
    def _verdict(self) -> IllegibleRequiredFields | UnmetAcceptanceCriteria | None:
        if self.illegible_fields is not None:
            return self.illegible_fields
        return self.unmet_criteria


def check_legibility(candidate: DocumentCandidate, *, catalog: Catalog) -> LegibilityCheck | None:
    """Adayı türünün zorunlu alanları (04.4.1) ve kabul kriterleriyle (04.4.2) değerlendirir.

    `catalog` güncel katalogdur (`export_catalog(session)`): zorunlu alanlar ve maddeler analiz
    anındaki değil, karar anındaki türden okunur. Aday katalog türünde değilse `None`.
    """
    slug = candidate.document_type_slug
    entry = None if slug is None else catalog.get(slug)
    if entry is None:
        return None
    analyses = [page.analysis for page in candidate.pages]
    illegible = _illegible_fields(analyses, entry.required_fields)
    unmet = _unmet_criteria(analyses, entry.acceptance_criteria)
    return LegibilityCheck(
        document_type_slug=entry.slug,
        illegible_fields=IllegibleRequiredFields(illegible) if illegible else None,
        unmet_criteria=UnmetAcceptanceCriteria(unmet) if unmet else None,
    )


def _illegible_fields(
    analyses: Sequence[PageAnalysis], required_fields: Iterable[str]
) -> tuple[str, ...]:
    trusted = [analysis for analysis in analyses if analysis.is_readable and not analysis.is_blank]
    return tuple(
        name
        for name in required_fields
        if not any(_reads_legibly(analysis, name) for analysis in trusted)
    )


def _reads_legibly(analysis: PageAnalysis, name: str) -> bool:
    reading = analysis.fields.get(name)
    return reading is not None and reading.legible


def _unmet_criteria(analyses: Sequence[PageAnalysis], criteria: Iterable[str]) -> tuple[str, ...]:
    words_by_criterion = {criterion: _words(criterion) for criterion in criteria}
    # Aynı kelime dizisine inen maddeler birlikte karşılanır ya da karşılanmaz; kelimesi olmayan
    # madde notta alıntılanamaz. Uzun madde önce aranır.
    searched = sorted(
        {words for words in words_by_criterion.values() if words},
        key=lambda words: (-len(words), words),
    )
    quoted: set[_Words] = set()
    for analysis in analyses:
        if analysis.notes is not None:
            quoted.update(_quoted_criteria(_words(analysis.notes), searched))
    return tuple(
        dict.fromkeys(
            " ".join(criterion.split())
            for criterion, words in words_by_criterion.items()
            if words in quoted
        )
    )


def _quoted_criteria(notes: _Words, searched: Sequence[_Words]) -> set[_Words]:
    found: set[_Words] = set()
    counted: list[_Span] = []
    for criterion in searched:
        spans = [
            span
            for span in _spans(notes, criterion)
            if not any(start <= span[0] and span[1] <= end for start, end in counted)
        ]
        if spans:
            found.add(criterion)
            counted.extend(spans)
    return found


def _spans(words: _Words, criterion: _Words) -> Iterator[_Span]:
    size = len(criterion)
    for start in range(len(words) - size + 1):
        if words[start : start + size] == criterion:
            yield start, start + size


def _words(text: str) -> _Words:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    letters = "".join(char for char in decomposed if not unicodedata.combining(char))
    # Noktasız `ı`nın ayrışmış biçimi yok; `I`nın küçük harfiyle (`i`) aynı kelimeye iner.
    return tuple(_NON_WORD.sub(" ", letters.replace("ı", "i")).split())
