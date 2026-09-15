"""Kişi anahtarı — PRD 05.4.1 (§20.2.1, §20.2.3; K6).

Bir belge adayının (04.1–04.3) sayfalarından çalışan eşleştirmesinin (05.5) ve profil açmanın
(05.6, 05.7) okuyacağı tek anahtar üretilir: **belge numaraları**, **normalize ad-soyad**, **doğum
tarihi** ve **orijinal yazım**. Anahtar yalnız okunmuş olanı taşır; okunmayan ya da adayın
sayfaları arasında çelişen değer tahminle seçilmez.

**MRZ önce (K6).** Her sayfaya önce `apply_mrz_priority` uygulanır (idempotent; önceden uygulanmış
sayfa değişmez). Aday tek belgedir: kartın arka yüzündeki MRZ ön yüzün görünen metninden de önce
gelir. MRZ'si okunmuş (`MrzStatus.READ`) ve MRZ'si alan için kullanılabilir değer taşıyan bir sayfa
varsa o alan (`document_number`, `surname`, `given_names`, `date_of_birth`) yalnız böyle sayfalardan
okunur; öteki sayfaların görünen okuması o alana girmez. MRZ alanı taşımıyorsa (kontrol hanesi
tutmadı, isim parçası boş) alan bütün sayfalardan okunur.

**Okumalar.** Bir sayfanın alan için okumaları `person` değeri ve okunaklı `fields` okumasıdır
(§8.4 alanı iki yerde yazar). Sayfa kendini boş ya da okunamaz veriyorsa okumalarına güvenilmez
(C21). Sayfanın `fields` okuması alanı `legible: false` veriyorsa o sayfanın `person` değeri de
anahtara girmez — okunamadı denen değer taşınmaz (K1); başka sayfanın okuması etkilenmez (kartın
öteki yüzü o alanı okunamadı yazar, 03.4).

**Karşılaştırma.** Okumalar karşılaştırma anahtarına indirilir: belge numarası §20.2.1'le
(`normalize_document_number`), isim parçaları sayfanın diliyle `normalize_name`'le, doğum tarihi
takvim günüyle (`fields`'teki metin yalnız `YYYY-AA-GG` ise okunur). Kelimesiz isim ve ayırıcıdan
ibaret numara okuma sayılmaz. Aynı anahtara inen okumalar tek değerdir; farklı anahtar kalan alan
**çelişkidir** ve adı `conflicts`'e yazılır:

- Belge numaraları çoğuldur: her farklı numara sayfa sırasıyla kalır. `legible`, numaranın bir
  sayfanın okunaklı `fields` okumasından da geldiğini söyler (§20.2.3 koşul 2'nin okunaklılığı).
- Ad-soyad, doğum tarihi ve orijinal yazım tekildir: çelişen alan `None` olur.
- Normalize ad-soyad `given_names` ve `surname`'ün ikisi de okunmuşsa üretilir; parçalar adayın
  farklı sayfalarından gelebilir. `other_names` (baba adı, ikinci ad) ad-soyada girmez.
- Orijinal yazım görüldüğü gibi, ICAO Latin karşılığıyla (`TransliteratedName`, 05.2.1) ve
  normalize anahtarıyla saklanır.

`mrz_allows_clean_document_number` adayın bütün sayfalarında §20.2.3'ün üçüncü koşulunun
(`MrzResolution.allows_clean_document_number`) sağlandığını söyler. Numaranın temiz sayılması
(tür, uzunluk) 05.6'nın, anahtarla eşleştirme 05.5'in kararıdır. Modül saf işlevdir: veritabanına ve
olay loguna yazmaz; anahtarda kişisel değer vardır, loga açık yazılmaz (CONVENTIONS §6).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date

from app.ai.schemas import PageAnalysis
from app.matching.mrz import MRZ_FIELDS, MrzResolution, MrzStatus, apply_mrz_priority
from app.matching.names import (
    EmptyNameError,
    TransliteratedName,
    normalize_name,
    transliterate_name,
)

DOCUMENT_NUMBER = "document_number"
SURNAME = "surname"
GIVEN_NAMES = "given_names"
DATE_OF_BIRTH = "date_of_birth"
ORIGINAL_SCRIPT_NAME = "original_script_name"
# Anahtarın okuduğu §8.4 `person` alanları; `conflicts` bu sırayla yazılır.
KEY_FIELDS = (DOCUMENT_NUMBER, SURNAME, GIVEN_NAMES, DATE_OF_BIRTH, ORIGINAL_SCRIPT_NAME)

# §20.2.1 belge numarası normalizasyonu: boşluk, tire, nokta, eğik çizgi silinir.
_NUMBER_SEPARATORS = re.compile(r"[\s./-]+")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


@dataclass(frozen=True, slots=True)
class DocumentNumberKey:
    """Anahtardaki tek belge numarası.

    `value` §20.2.1 normalize değeridir. `legible` numara adayın en az bir sayfasında okunaklı
    `fields.document_number` okumasından da geldiyse doğrudur; yalnız `person`'dan okunan numara
    alan okunaklılığı taşımaz.
    """

    value: str
    legible: bool


@dataclass(frozen=True, slots=True)
class PersonKey:
    """Belge adayının kişi anahtarı (05.4.1); alanların kuralları modül açıklamasındadır."""

    document_numbers: tuple[DocumentNumberKey, ...]
    normalized_name: str | None
    date_of_birth: date | None
    original_script_name: TransliteratedName | None
    normalized_original_name: str | None
    mrz_allows_clean_document_number: bool
    conflicts: tuple[str, ...]

    @property
    def name_keys(self) -> tuple[str, ...]:
        """`employee_aliases.normalized_name` ile karşılaştırılacak isim anahtarları, tekrarsız:
        önce ad-soyad, sonra orijinal yazım."""
        keys = (self.normalized_name, self.normalized_original_name)
        return tuple(dict.fromkeys(key for key in keys if key is not None))


def normalize_document_number(value: str) -> str:
    """§20.2.1: büyük harfe çevirir, boşluk / tire / nokta / eğik çizgiyi siler."""
    return _NUMBER_SEPARATORS.sub("", value.upper())


def build_person_key(analyses: Iterable[PageAnalysis], *, today: date | None = None) -> PersonKey:
    """Adayın sayfa analizlerinden (belgedeki sırasıyla) kişi anahtarını üretir.

    `today` MRZ doğum tarihinin yüzyılını seçer (§20.1.6), verilmezse bugündür.
    """
    resolutions = [apply_mrz_priority(analysis, today=today) for analysis in analyses]
    pages = [
        resolution
        for resolution in resolutions
        if resolution.analysis.is_readable and not resolution.analysis.is_blank
    ]
    numbers = _collect(pages, DOCUMENT_NUMBER, _number_key)
    surnames = _collect(pages, SURNAME, _name_key)
    given_names = _collect(pages, GIVEN_NAMES, _name_key)
    births = _collect(pages, DATE_OF_BIRTH, _date_key)
    originals = _collect(pages, ORIGINAL_SCRIPT_NAME, _name_key)
    collected = {
        DOCUMENT_NUMBER: numbers,
        SURNAME: surnames,
        GIVEN_NAMES: given_names,
        DATE_OF_BIRTH: births,
        ORIGINAL_SCRIPT_NAME: originals,
    }

    normalized_name = None
    if len(surnames) == len(given_names) == 1:
        (surname,), (given,) = surnames, given_names
        # Parça anahtarları birleşir: her parça kendi sayfasının diliyle normalize edildi ve
        # `normalize_name(given, surname)` de kelimeleri aynı biçimde sıralayıp birleştirir.
        normalized_name = " ".join(sorted((*surname.split(), *given.split())))
    original, normalized_original = None, None
    if len(originals) == 1:
        ((normalized_original, reading),) = originals.items()
        original = transliterate_name(str(reading.raw), language=reading.language)
    return PersonKey(
        document_numbers=tuple(
            DocumentNumberKey(value, reading.legible) for value, reading in numbers.items()
        ),
        normalized_name=normalized_name,
        date_of_birth=_single(births),
        original_script_name=original,
        normalized_original_name=normalized_original,
        mrz_allows_clean_document_number=all(
            resolution.allows_clean_document_number for resolution in resolutions
        ),
        conflicts=tuple(name for name in KEY_FIELDS if len(collected[name]) > 1),
    )


@dataclass(slots=True)
class _Reading:
    raw: str | date  # anahtara inen ilk okuma, yazıldığı gibi
    language: str | None  # okumanın sayfasının dili
    legible: bool  # bir okuma okunaklı `fields` okumasından geldi


def _collect[K](
    pages: Sequence[MrzResolution],
    name: str,
    key: Callable[[str | date, str | None], K | None],
) -> dict[K, _Reading]:
    mrz_pages = [page for page in pages if _mrz_carries(page, name)]
    collected: dict[K, _Reading] = {}
    for page in mrz_pages or pages:
        analysis = page.analysis
        for raw, from_fields in _readings(analysis, name):
            value = key(raw, analysis.language)
            if value is None:
                continue
            reading = collected.setdefault(value, _Reading(raw, analysis.language, False))
            reading.legible = reading.legible or from_fields
    return collected


def _mrz_carries(page: MrzResolution, name: str) -> bool:
    return (
        name in MRZ_FIELDS
        and page.status is MrzStatus.READ
        and page.mrz is not None
        and getattr(page.mrz, name) is not None
    )


def _readings(analysis: PageAnalysis, name: str) -> Iterator[tuple[str | date, bool]]:
    reading = analysis.fields.get(name)
    if reading is not None and not reading.legible:
        return
    value = getattr(analysis.person, name)
    if value is not None:
        yield value, False
    if reading is not None and reading.value is not None:
        yield reading.value, True


# Numara ve isim okumaları her zaman metindir (§8.4); `date` yalnız doğum tarihi alanından gelir.
def _number_key(raw: str | date, language: str | None) -> str | None:
    return normalize_document_number(str(raw)) or None


def _name_key(raw: str | date, language: str | None) -> str | None:
    try:
        return normalize_name(str(raw), language=language)
    except EmptyNameError:
        return None


def _date_key(raw: str | date, language: str | None) -> date | None:
    if isinstance(raw, date):
        return raw
    if not _ISO_DATE.fullmatch(raw):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _single[K](collected: dict[K, _Reading]) -> K | None:
    return next(iter(collected)) if len(collected) == 1 else None
