"""Kişi anahtarı ve çalışan eşleştirme sırası — PRD 05.4.1, 05.5.1–05.5.3 (§20.2; K6, R7, R8).

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
(tür, uzunluk) 05.6'nın kararıdır. `build_person_key` saf işlevdir: veritabanına ve olay loguna
yazmaz; anahtarda kişisel değer vardır, loga açık yazılmaz (CONVENTIONS §6).

**Eşleştirme (05.5).** `match_employee` anahtarı kayıtlı çalışanlarla §20.2.2 karar tablosunun
sırasıyla karşılaştırır; ilk uyan satır kazanır, alttakilere bakılmaz:

1. Belge numarası `employee_identifiers.value` ile eşleşiyor ve tek çalışana ait → eşleşme
   (`matched_by: document_number`).
2. Numara birden fazla çalışana ait → belirsiz eşleşme, Unresolved + `PERSON_AMBIGUOUS`.
3. Numara eşleşmedi; isim anahtarlarından biri (`name_keys`) `employee_aliases.normalized_name` ile
   eşleşiyor ve çalışanın doğum tarihi belgeninkine eşit, tek çalışan → eşleşme
   (`matched_by: name_dob`).
4. İsim + doğum tarihi birden fazla çalışana uyuyor → belirsiz eşleşme, Unresolved +
   `PERSON_AMBIGUOUS`.
5. Yalnız isim eşleşti (doğum tarihi belgede ya da çalışanda yok, veya farklı) → Unresolved (R8):
   otomatik eşleştirme sayılmaz, alttaki satırlara da inilmez — yeni çalışan açılmaz.

Hiçbiri uymazsa hüküm `NO_MATCH`'tir: satır 6–8 (yeni çalışan, onay bekleyen profil, kişi tespit
edilemedi) temiz numara tanımına (§20.2.3) bağlıdır ve 05.6/05.7'nin kararıdır. Tabloda karşılığı
olmayan **çelişkili anahtar** (`conflicts` dolu: adayın sayfaları bir kimlik alanını farklı okuyor)
hiçbir satıra girmeden Unresolved'a gider (PLAN.md D8). Karşılaştırma tam eşitliktir: numara ve
alias'lar yazan adımın (05.6, 05.7.2) §20.2.1 ile normalize ettiği biçimde saklanır. Her hüküm olay
loguna yazılır — eşleşme `PERSON_MATCHED`, belirsiz eşleşme `PERSON_AMBIGUOUS`, öteki hükümler
`PERSON_NOT_MATCHED`; olay kişisel değer taşımaz, yalnız kural, E numaraları ve alan adları.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schemas import PageAnalysis
from app.db.models import Employee, EmployeeAlias, EmployeeIdentifier, QueueKind
from app.events import EventType, record_event
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


# --- çalışan eşleştirme sırası (05.5) ------------------------------------------------------


class EmployeeAction(enum.StrEnum):
    """Plan JSON `employee.action` (§8.5)."""

    MATCH = "match"
    CREATE = "create"
    PENDING = "pending"
    NONE = "none"


class MatchedBy(enum.StrEnum):
    """Plan JSON `employee.matched_by` (§8.5, §20.2.2)."""

    DOCUMENT_NUMBER = "document_number"
    NAME_DOB = "name_dob"


class MatchRule(enum.StrEnum):
    """`match_employee` hükmü: §20.2.2 satırı ya da tablo dışı çelişkili anahtar (D8)."""

    CONFLICTING_KEY = "conflicting_key"
    DOCUMENT_NUMBER = "document_number"  # satır 1
    DOCUMENT_NUMBER_AMBIGUOUS = "document_number_ambiguous"  # satır 2
    NAME_DOB = "name_dob"  # satır 3
    NAME_DOB_AMBIGUOUS = "name_dob_ambiguous"  # satır 4
    NAME_ONLY = "name_only"  # satır 5
    NO_MATCH = "no_match"  # satır 6–8: 05.6 / 05.7


# §20.2.2 satır 5'in gerekçesi, PRD'deki yazımıyla.
NAME_ONLY_REASON = "İsim eşleşti ama doğum tarihi veya belge numarası doğrulanamadı"

_MATCHED_BY = {
    MatchRule.DOCUMENT_NUMBER: MatchedBy.DOCUMENT_NUMBER,
    MatchRule.NAME_DOB: MatchedBy.NAME_DOB,
}
_EVENT_TYPES = {
    MatchRule.DOCUMENT_NUMBER: EventType.PERSON_MATCHED,
    MatchRule.NAME_DOB: EventType.PERSON_MATCHED,
    MatchRule.DOCUMENT_NUMBER_AMBIGUOUS: EventType.PERSON_AMBIGUOUS,
    MatchRule.NAME_DOB_AMBIGUOUS: EventType.PERSON_AMBIGUOUS,
}


@dataclass(frozen=True, slots=True)
class EmployeeMatch:
    """Belge adayının çalışan eşleştirme hükmü (05.5); kurallar modül açıklamasındadır.

    `employee_ids` hükmün dayandığı çalışanlardır (E numarası sırasıyla): eşleşmede tek çalışan,
    belirsiz eşleşmede uyan bütün çalışanlar, yalnız isim eşleşmesinde ismi eşleşen bütün
    çalışanlar; çelişkili anahtarda ve `NO_MATCH`'te boştur. `conflicts` çelişkili anahtarın
    çelişen alan adlarıdır (`KEY_FIELDS` sırasıyla).
    """

    rule: MatchRule
    employee_ids: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()

    @property
    def matched_by(self) -> MatchedBy | None:
        return _MATCHED_BY.get(self.rule)

    @property
    def employee_id(self) -> str | None:
        """Eşleşen çalışan; yalnız satır 1 ve 3'te dolu."""
        return self.employee_ids[0] if self.matched_by is not None else None

    @property
    def action(self) -> EmployeeAction | None:
        """Eşleşmede `match`, Unresolved'a giden hükümde `none`.

        `NO_MATCH`'te `None`'dır: satır 6–8'in eylemi (`create`, `pending`, `none`) bu adımda
        verilmez, 05.6/05.7 temiz numara ve okunan ad-soyadla belirler.
        """
        if self.rule is MatchRule.NO_MATCH:
            return None
        return EmployeeAction.MATCH if self.matched_by is not None else EmployeeAction.NONE

    @property
    def queue(self) -> QueueKind | None:
        """Belge otomatik eşleştirilmeyip Unresolved'a gidiyorsa `QueueKind.UNRESOLVED`."""
        return QueueKind.UNRESOLVED if self.action is EmployeeAction.NONE else None

    @property
    def reason(self) -> str | None:
        """Unresolved gerekçesi; kişisel değer taşımaz, yalnız alan adları ve E numaraları."""
        employees = ", ".join(self.employee_ids)
        match self.rule:
            case MatchRule.CONFLICTING_KEY:
                return (
                    "Kişi anahtarı çelişkili: adayın sayfaları şu alanları farklı okuyor: "
                    f"{', '.join(self.conflicts)}. Çalışan otomatik eşleştirilmez."
                )
            case MatchRule.DOCUMENT_NUMBER_AMBIGUOUS:
                return (
                    f"Belirsiz eşleşme: belge numarası birden fazla çalışana ait ({employees}). "
                    "Çalışan otomatik eşleştirilmez."
                )
            case MatchRule.NAME_DOB_AMBIGUOUS:
                return (
                    "Belirsiz eşleşme: ad-soyad ve doğum tarihi birden fazla çalışana uyuyor "
                    f"({employees}). Çalışan otomatik eşleştirilmez."
                )
            case MatchRule.NAME_ONLY:
                label = "çalışan" if len(self.employee_ids) == 1 else "çalışanlar"
                return (
                    f"{NAME_ONLY_REASON}. İsmi eşleşen {label}: {employees}. Yalnız isim "
                    "eşleşmesi otomatik eşleştirme sayılmaz (R8)."
                )
            case _:
                return None


def match_employee(
    session: Session,
    key: PersonKey,
    *,
    file_id: int | None = None,
    page_index: int | None = None,
) -> EmployeeMatch:
    """Kişi anahtarını kayıtlı çalışanlarla §20.2.2 sırasıyla eşleştirir, hükmü olay loguna yazar.

    Olay dışında veritabanına yazmaz: eşleşmede alias ve numara birikimi (05.7.2), yeni çalışan
    (05.6) ve kuyruk kaydı (08.1) sonraki adımlardır. `file_id`/`page_index` olayın yeridir
    (adayın ilk sayfası); verilmezse etkin `event_context`ten alınır. Oturum commit edilmez.
    """
    result = _decide(session, key)
    data: dict[str, object] = {"rule": result.rule.value}
    if result.matched_by is not None:
        data["matched_by"] = result.matched_by.value
    if result.queue is not None:
        data["queue"] = result.queue.value
    if result.employee_ids:
        data["employee_ids"] = list(result.employee_ids)
    if result.conflicts:
        data["conflicts"] = list(result.conflicts)
    record_event(
        session,
        _EVENT_TYPES.get(result.rule, EventType.PERSON_NOT_MATCHED),
        file_id=file_id,
        page_index=page_index,
        employee_id=result.employee_id,
        message=result.reason,
        data=data,
    )
    return result


def _decide(session: Session, key: PersonKey) -> EmployeeMatch:
    if key.conflicts:
        return EmployeeMatch(MatchRule.CONFLICTING_KEY, conflicts=key.conflicts)
    numbers = [number.value for number in key.document_numbers]
    if numbers:
        owners = _employee_ids(
            session.scalars(
                select(EmployeeIdentifier.employee_id).where(EmployeeIdentifier.value.in_(numbers))
            )
        )
        if len(owners) == 1:
            return EmployeeMatch(MatchRule.DOCUMENT_NUMBER, owners)
        if owners:
            return EmployeeMatch(MatchRule.DOCUMENT_NUMBER_AMBIGUOUS, owners)
    if not key.name_keys:
        return EmployeeMatch(MatchRule.NO_MATCH)
    named = session.execute(
        select(Employee.id, Employee.date_of_birth)
        .join(EmployeeAlias, EmployeeAlias.employee_id == Employee.id)
        .where(EmployeeAlias.normalized_name.in_(key.name_keys))
    ).all()
    if not named:
        return EmployeeMatch(MatchRule.NO_MATCH)
    born = key.date_of_birth
    fitting = _employee_ids(
        employee_id for employee_id, birth in named if born is not None and birth == born
    )
    if len(fitting) == 1:
        return EmployeeMatch(MatchRule.NAME_DOB, fitting)
    if fitting:
        return EmployeeMatch(MatchRule.NAME_DOB_AMBIGUOUS, fitting)
    return EmployeeMatch(
        MatchRule.NAME_ONLY, _employee_ids(employee_id for employee_id, _ in named)
    )


def _employee_ids(ids: Iterable[str]) -> tuple[str, ...]:
    # Tekrarsız, E numarası sırasıyla (`E9999` < `E10000`): hüküm sorgu sırasına bağlı kalmaz.
    return tuple(sorted(set(ids), key=lambda employee_id: (len(employee_id), employee_id)))
