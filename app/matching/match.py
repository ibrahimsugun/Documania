"""Kişi anahtarı, çalışan eşleştirme sırası, otomatik çalışan oluşturma, onay bekleyen profil,
profil onayı ve alias birikimi — PRD 05.4.1, 05.5.1–05.5.4, 05.6.1, 05.6.2, 05.7.1, 05.7.2, 08.3.1,
05.2.2 (§20.2; K6, K7, K8, K16, R7, R8, R9).

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
- `date_of_birth_legible` tekil doğum tarihinin bir sayfanın okunaklı `fields` okumasından ya da
  kontrol hanesi tutan MRZ'den geldiğini söyler (§20.2.4 koşul 3); yalnız `person`'dan okunan tarih
  alan okunaklılığı taşımaz. Eşleştirme (satır 3–5) bu bayrağa bakmaz.
- Normalize ad-soyad `given_names` ve `surname`'ün ikisi de okunmuşsa üretilir; parçalar adayın
  farklı sayfalarından gelebilir. `other_names` (baba adı, ikinci ad) ad-soyada girmez.
- Orijinal yazım görüldüğü gibi, ICAO Latin karşılığıyla (`TransliteratedName`, 05.2.1) ve
  normalize anahtarıyla saklanır.

Anahtar ayrıca yeni çalışan kaydının (03.1.3, `employee_fields`) okumalarını taşır: `surname` ve
`given_names` parçanın anahtara inen ilk okuması, yazıldığı gibi; `other_names` isim anahtarıyla,
`nationality` ICAO uyruk koduyla (`RUS`, `D`) karşılaştırılır. Bu iki alan kimlik alanı değildir:
okunmazsa ya da çelişirse `None` olur, `conflicts`'e yazılmaz.

**Latin ad (05.2.2, PLAN.md §C81).** Çalışan kaydının ad, soyad ve diğer isimler alanları yalnız
Latin harfi taşır; anahtar her parçanın Latin yazımını ayrıca verir (`latin_*`,
`app.matching.names.latin_person_name`): anahtara inen basılı Latin okuma, sonra kontrol haneleri
geçen MRZ, sonra yalnız Kiril için kural tabanlı çeviri. Yapay zekâ Latin alana Latin olmayan
yazım koyduysa o yazım çalışan kaydında orijinal yazıma taşınır (`original_spelling`, belgenin
orijinal yazımı okunmadıysa). Eşleştirme anahtarı ve isim yazımları (alias) değişmez: belgede
okunduğu alfabededir. Ad-soyad okunmuş ama Latin yazımı yoksa (Arap ve öteki alfabeler) çalışan
otomatik açılmaz; profil önerisi "Latin yazım belgede yok" gerekçesiyle Unresolved'a düşer, İK
Latin adı onayda yazar.

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
5a. Numara eşleşmedi ve anahtarda doğum tarihi yok (tür taşımıyor ya da okunmadı); isim
   anahtarlarından biri birleştirilmemiş (etkin ya da pasif) **tek** çalışanın alias'ıyla eşleşiyor
   → eşleşme (`matched_by: name`; 05.5.4, PLAN.md §D109). Aynı çalışanın iki alias'ı tek kayıttır.
   İsim birden fazla çalışana uyuyorsa (biri pasif olsa da) belirsiz eşleşme, Unresolved +
   `PERSON_AMBIGUOUS` (satır 4 gibi). Satır 5a'nın eşleşmesi hiçbir şey biriktirmez: isim yazımı,
   numara, profil alanı ve iletişim bilgisi eklenmez (`accumulate_identity` reddeder; planlayıcı
   alan ve iletişim adımlarını çağırmaz). Doğum tarihi zorunlu alan olan türde okunmayan tarih K1
   gereği Unreadable'dır; belge düzeyinde reddedilen belgede planlayıcı satır 5a'dan kişi tahmini
   de vermez.
5. Yalnız isim eşleşti ve satır 5a uymuyor (belgedeki doğum tarihi farklı ya da çalışanınki kayıtlı
   değil) → Unresolved (R8): otomatik eşleştirme sayılmaz, alttaki satırlara da inilmez — yeni
   çalışan açılmaz.

Hiçbiri uymazsa hüküm `NO_MATCH`'tir: satır 6–8 (yeni çalışan, onay bekleyen profil, kişi tespit
edilemedi) temiz numara (§20.2.3) ve ad + doğum tarihi (§20.2.4) tanımlarına bağlıdır ve
`resolve_unmatched`'in kararıdır. Tabloda
karşılığı olmayan **çelişkili anahtar** (`conflicts` dolu: adayın sayfaları bir kimlik alanını
farklı okuyor) hiçbir satıra girmeden Unresolved'a gider (PLAN.md D8). Karşılaştırma tam eşitliktir:
numara ve alias'lar yazan adımın (05.6, 05.7.2) §20.2.1 ile normalize ettiği biçimde saklanır. Her
hüküm olay loguna yazılır — eşleşme `PERSON_MATCHED`, belirsiz eşleşme `PERSON_AMBIGUOUS`, öteki
hükümler `PERSON_NOT_MATCHED`; olay kişisel değer taşımaz, yalnız kural, E numaraları ve alan
adları.

**Otomatik çalışan oluşturma (05.6, R9, K7).** Hiç eşleşme yoksa yeni çalışan ve klasörü iki
dayanaktan biriyle açılır (`CreationBasis`, `EMPLOYEE_CREATED` verisinde `basis`):

- §20.2.2 satır 6 (`document_number`, 05.6.1) — temiz belge numarası var. Numara §20.2.3'ün üç
  koşuluyla temizdir (`clean_document_number`): türün `required_fields`'ında `document_number` var,
  numara okunaklı ve normalize hâli en az 5 karakter, MRZ'den geldiyse alan ve bileşik haneleri
  tutuyor.
- Satır 6b (`name_dob`, 05.6.2, PLAN.md §C84) — temiz numara yok ama §20.2.4'ün koşulları
  sağlanıyor: türün `required_fields`'ında `date_of_birth` var (başkasının doğum tarihini taşıyan
  tür bu yolu kullanmaz; kural türün adına değil zorunlu alanlarına bakar), doğum tarihi okunaklı
  (`date_of_birth_legible`), anahtarda tek ve sayfalar arasında çelişkisiz, makul yaş
  doğrulamasından (`dob_plausible`, §20.1.6) geçmiş. Koşul 4 — tarih ucuz ön eleme modelinin
  doğrulanmamış okuması değil — ön elemenin işidir: doğum tarihi zorunlu türün MRZ'siz sayfası ana
  modele yükseltilir (`app.pipeline.analyze.prescreen_escalation`, `unverified_date_of_birth`).
  Satır 6b'de belge numarası hiçbir yere yazılmaz: temiz değildir (D11).

Klasör adı (K8) ad-soyaddan kurulduğu için ikisinde de ad-soyad Latin yazımıyla okunmuş ve klasör
adı veriyor olmalıdır (05.2.2, PLAN.md D9). `can_create_employee` bu kararı yan etkisiz verir;
`create_employee` hükmü veritabanında yeniden değerlendirir, satır 6 ya da 6b uymuyorsa hiçbir şey
yazmadan reddeder, uyuyorsa E numarası verir (K8), çalışan kaydını, isim yazımlarını
(`employee_aliases`), satır 6'da temiz numarayı (`employee_identifiers`) ve
`Employees/<Ad_Soyad_E0001>/` klasörünü açar, `EMPLOYEE_CREATED` yazar.

**Onay bekleyen profil (05.7.1, K7).** `resolve_unmatched` `NO_MATCH` hükmünü satır 6–8'e çevirir:
temiz numara ve klasör adı veren ad-soyad → satır 6 (`create`); temiz numara yok, klasör adı veren
ad-soyad ve §20.2.4'e uyan doğum tarihi → satır 6b (`create`); ad-soyad klasör adı verecek biçimde
okunmuş ama satır 6 ve 6b uymuyor → satır 7 (`pending`, Unresolved, önerilen profil); ne isim ne
numara okunmuş → satır 8 (`none`, Unresolved). Tabloda karşılığı olmayan eksik kişi — temiz numara
var ama ad-soyad kullanılamıyor (D9), ya da ad-soyad kullanılamıyor ama bir numara veya isim
okunmuş (D10) — `none` ile Unresolved'a gider, profil önerilmez. `propose_pending_profile` satır
7'yi veritabanında yeniden değerlendirir ve yalnız `EMPLOYEE_PENDING` olayını yazar: çalışan, isim
yazımı, numara ve klasör onaysız oluşmaz; önerilen profil kuyruk kaydının payload'ına girer (08.1),
çalışan onayla açılır (08.3).

**Profil onayı (08.3.1, K16).** `approve_pending_profile` satır 7'yi onay anında veritabanında
yeniden değerlendirir — öneriden sonra kişi kayıtlı bir çalışanla eşleşiyorsa (ör. aynı kişinin
öteki belgesi onaylandı) ikinci çalışan açılmaz — ve uyuyorsa önerilen profilden çalışanı açar:
satır 6'nın (`create_employee`) yazdıklarının hepsi, temiz olmayan belge numarası hariç. Satır
6b'nin (05.6.2) gelmesinden önce kuyruğa düşmüş öneri geriye dönük açılmaz ama onaylanabilir:
anahtarı bugün satır 6b'ye uyan öneri satır 7 gibi onaylanır (PLAN.md §C84). İK önerinin çalışan
kaydına yazılacak alanlarını (`ProfileFields`) onaydan önce düzeltebilir (10.7.3): düzeltme yalnız
çalışan kaydını değiştirir, belge içeriğini ve okumalarını değil (K17); düzeltilmiş ad ya da doğum
tarihi kayıtlı bir çalışana uyuyorsa (satır 3–5) ikinci çalışan açılmaz.

**Alias ve numara birikimi (05.7.2).** Satır 1 ve 3'teki eşleşmede (5a'da değil)
`accumulate_identity` belgedeki yeni isim yazımlarını `employee_aliases`'a, yeni belge numarasını
`employee_identifiers`'a ekler.
Numara yalnız §20.2.3'e göre temizse eklenir: yanlış okunmuş numara başka birinin belgesini satır
1'le bu çalışana bağlayabilir (D11).

**Kaldırılmış alt kayıt (10.5.8).** İK'nın profilden kaldırdığı isim yazımı ve belge numarası
eşleştirmeye girmez: satır 1–5 yalnız etkin kayıtlarla karar verir (`app.matching.records`).
Kaldırılmış değer belgeden yeniden gelirse birikim onu geri açmaz, yeni satır da açmaz; kaldırılmış
kaydı işaretler, profil uyarı gösterir (PLAN.md §D68).
"""

from __future__ import annotations

import enum
import re
import unicodedata
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schemas import PageAnalysis
from app.catalog import CatalogEntry
from app.db.models import (
    Employee,
    EmployeeAlias,
    EmployeeIdentifier,
    EmployeeStatus,
    QueueKind,
    allocate_employee_number,
)
from app.events import EventType, record_event
from app.i18n import N_, Translatable
from app.matching.mrz import MRZ_FIELDS, MrzResolution, MrzStatus, apply_mrz_priority
from app.matching.names import (
    EmptyNameError,
    TransliteratedName,
    detect_script,
    is_latin_name,
    latin_person_name,
    normalize_name,
    transliterate_name,
)
from app.matching.records import ACTIVE_ALIAS, note_seen_after_removal, number_owners
from app.storage import DataLayout, SlugError, employee_folder_name, person_slug

DOCUMENT_NUMBER = "document_number"
SURNAME = "surname"
GIVEN_NAMES = "given_names"
DATE_OF_BIRTH = "date_of_birth"
ORIGINAL_SCRIPT_NAME = "original_script_name"
OTHER_NAMES = "other_names"
NATIONALITY = "nationality"
# Anahtarın okuduğu §8.4 `person` alanları; `conflicts` bu sırayla yazılır.
KEY_FIELDS = (DOCUMENT_NUMBER, SURNAME, GIVEN_NAMES, DATE_OF_BIRTH, ORIGINAL_SCRIPT_NAME)
# Yalnız Latin harfi taşıyan çalışan alanları (05.2.2) → `PersonKey`'deki Latin yazımları.
_LATIN_FIELDS = {
    SURNAME: "latin_surname",
    GIVEN_NAMES: "latin_given_names",
    OTHER_NAMES: "latin_other_names",
}

# §20.2.1 belge numarası normalizasyonu: boşluk, tire, nokta, eğik çizgi silinir.
_NUMBER_SEPARATORS = re.compile(r"[\s./-]+")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# ICAO 9303 uyruk kodu (§8.4 `nationality`): üç harf, Almanya için tek harf.
_NATIONALITY = re.compile(r"[A-Z]{1,3}")


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
    """Belge adayının kişi anahtarı (05.4.1); alanların kuralları modül açıklamasındadır.

    `surname`, `given_names`, `other_names` ve `nationality` karşılaştırmaya girmez; `surname`,
    `given_names`, `other_names` belgedeki okumadır, yazıldığı alfabede (isim yazımı, 05.7.2).
    `latin_*` aynı parçanın Latin yazımıdır (05.2.2, `latin_person_name`): yeni çalışan kaydına
    (05.6) bunlar yazılır; Latin yazım yoksa `None`. Latin okuma kendi Latin yazımıdır: `latin_*`
    verilmezse Latin harfli okuma oraya da yazılır. `date_of_birth_legible` yalnız satır 6b'nin
    (§20.2.4) koşuludur; verilmezse tarih okunaklı sayılmaz ve ad + doğum tarihiyle çalışan açılmaz.
    """

    document_numbers: tuple[DocumentNumberKey, ...]
    normalized_name: str | None
    date_of_birth: date | None
    original_script_name: TransliteratedName | None
    normalized_original_name: str | None
    mrz_allows_clean_document_number: bool
    conflicts: tuple[str, ...]
    surname: str | None = None
    given_names: str | None = None
    other_names: str | None = None
    nationality: str | None = None
    latin_surname: str | None = None
    latin_given_names: str | None = None
    latin_other_names: str | None = None
    date_of_birth_legible: bool = False

    def __post_init__(self) -> None:
        for name, latin_name in _LATIN_FIELDS.items():
            reading = getattr(self, name)
            if getattr(self, latin_name) is None and reading is not None and is_latin_name(reading):
                object.__setattr__(self, latin_name, reading)

    @property
    def name_keys(self) -> tuple[str, ...]:
        """`employee_aliases.normalized_name` ile karşılaştırılacak isim anahtarları, tekrarsız:
        önce ad-soyad, sonra orijinal yazım."""
        keys = (self.normalized_name, self.normalized_original_name)
        return tuple(dict.fromkeys(key for key in keys if key is not None))

    @property
    def original_spelling(self) -> str | None:
        """Çalışan kaydının orijinal yazımı (05.2.2): ismin belgede basılı hâli, alfabesi ne
        olursa olsun — Latin belgede de doludur.

        Belgeden okunan orijinal yazım varsa odur. Okunmadıysa: önce ad, diğer isimler ve soyad
        okumalarındaki Latin olmayan parçalar (yapay zekâ Latin olmayan yazımı Latin alanlara
        koyduysa orijinal yazıma taşınır), onlar da yoksa okumaların kendisi — hepsi Latin'se
        basılı isim odur."""
        if self.original_script_name is not None:
            return self.original_script_name.original
        parts = [part for part in (self.given_names, self.other_names, self.surname) if part]
        foreign = [part for part in parts if not is_latin_name(part)]
        return " ".join(foreign or parts) or None

    def employee_fields(self) -> dict[str, str | date | None]:
        """Çalışan kaydına taşınan alanlar (03.1.3); anahtarlar `employees` sütun adlarıdır. İsim
        alanları Latin yazımdır, Latin olmayan yazım yalnız orijinal yazımdadır (05.2.2)."""
        return {
            SURNAME: self.latin_surname,
            GIVEN_NAMES: self.latin_given_names,
            OTHER_NAMES: self.latin_other_names,
            ORIGINAL_SCRIPT_NAME: self.original_spelling,
            DATE_OF_BIRTH: self.date_of_birth,
            NATIONALITY: self.nationality,
        }


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
    other_names = _collect(pages, OTHER_NAMES, _name_key)
    nationalities = _collect(pages, NATIONALITY, _nationality_key)
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
    latin = _latin_names(
        pages, {SURNAME: surnames, GIVEN_NAMES: given_names, OTHER_NAMES: other_names}
    )
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
        surname=_single_reading(surnames),
        given_names=_single_reading(given_names),
        other_names=_single_reading(other_names),
        nationality=_single(nationalities),
        latin_surname=latin[SURNAME],
        latin_given_names=latin[GIVEN_NAMES],
        latin_other_names=latin[OTHER_NAMES],
        date_of_birth_legible=_legible_single(births)
        or (len(births) == 1 and any(_mrz_carries(page, DATE_OF_BIRTH) for page in pages)),
    )


def _latin_names(
    pages: Sequence[MrzResolution], collected: Mapping[str, dict[str, _Reading]]
) -> dict[str, str | None]:
    # 05.2.2: tekil okunmuş isim parçasının Latin yazımı (`latin_person_name`). Okumalar bütün
    # sayfalardan alınır — anahtara inen okuma aynı adın yazımıdır: kartın ön yüzündeki basılı
    # Latin ad, MRZ'si arka yüzde olsa da önce gelir.
    keys = {name: _single(readings) for name, readings in collected.items()}
    mrz = _mrz_name_parts(pages, keys)
    latin: dict[str, str | None] = {}
    for name, key in keys.items():
        readings = [
            (str(raw), page.analysis.language)
            for page in pages
            for raw, _ in _readings(page.analysis, name)
            if key is not None and _name_key(raw, page.analysis.language) == key
        ]
        spelling = latin_person_name(readings, mrz=mrz[name]) if readings else None
        latin[name] = None if spelling is None else spelling.text
    return latin


def _mrz_name_parts(
    pages: Sequence[MrzResolution], keys: Mapping[str, str | None]
) -> dict[str, tuple[str, ...]]:
    # Kontrol haneleri geçen MRZ'lerin anahtara inen isim parçaları. MRZ'nin verilen adları ayrı
    # okunmuş baba adını da taşıyabilir (05.3.3): `DMITRII<IVANOVICH` ad ve diğer isimler
    # okumalarına kelime sınırından bölünür.
    parts: dict[str, list[str]] = {name: [] for name in keys}
    for page in pages:
        mrz = page.mrz
        if page.status is not MrzStatus.READ or mrz is None or mrz.failed_checks:
            continue
        surname, given = mrz.surname, mrz.given_names
        if surname is not None and _agrees_with(surname, keys[SURNAME]):
            parts[SURNAME].append(surname)
        if given is None:
            continue
        if _agrees_with(given, keys[GIVEN_NAMES]):
            parts[GIVEN_NAMES].append(given)
            continue
        words = given.split()
        for index in range(1, len(words)):
            head, tail = " ".join(words[:index]), " ".join(words[index:])
            if _agrees_with(head, keys[GIVEN_NAMES]) and _agrees_with(tail, keys[OTHER_NAMES]):
                parts[GIVEN_NAMES].append(head)
                parts[OTHER_NAMES].append(tail)
                break
    return {name: tuple(values) for name, values in parts.items()}


def _agrees_with(spelling: str, key: str | None) -> bool:
    return key is not None and _name_key(spelling, None) == key


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


def _nationality_key(raw: str | date, language: str | None) -> str | None:
    code = str(raw).upper()
    return code if _NATIONALITY.fullmatch(code) else None


def _single[K](collected: dict[K, _Reading]) -> K | None:
    return next(iter(collected)) if len(collected) == 1 else None


def _single_reading[K](collected: dict[K, _Reading]) -> str | None:
    # Tekil alanın anahtara inen ilk okuması, yazıldığı gibi.
    return str(next(iter(collected.values())).raw) if len(collected) == 1 else None


def _legible_single[K](collected: dict[K, _Reading]) -> bool:
    # Tekil alan bir sayfanın okunaklı `fields` okumasından da geldi.
    return len(collected) == 1 and next(iter(collected.values())).legible


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
    NAME = "name"  # satır 5a (05.5.4): kimlik birikmez


class MatchRule(enum.StrEnum):
    """`match_employee` hükmü: §20.2.2 satırı ya da tablo dışı çelişkili anahtar (D8)."""

    CONFLICTING_KEY = "conflicting_key"
    DOCUMENT_NUMBER = "document_number"  # satır 1
    DOCUMENT_NUMBER_AMBIGUOUS = "document_number_ambiguous"  # satır 2
    NAME_DOB = "name_dob"  # satır 3
    NAME_DOB_AMBIGUOUS = "name_dob_ambiguous"  # satır 4
    NAME = "name"  # satır 5a
    NAME_AMBIGUOUS = "name_ambiguous"  # satır 5a, birden fazla çalışan
    NAME_ONLY = "name_only"  # satır 5
    NO_MATCH = "no_match"  # satır 6–8: 05.6 / 05.7


# §20.2.2 satır 5'in gerekçesi, PRD'deki yazımıyla.
NAME_ONLY_REASON = "İsim eşleşti ama doğum tarihi veya belge numarası doğrulanamadı"

_MATCHED_BY = {
    MatchRule.DOCUMENT_NUMBER: MatchedBy.DOCUMENT_NUMBER,
    MatchRule.NAME_DOB: MatchedBy.NAME_DOB,
    MatchRule.NAME: MatchedBy.NAME,
}
_EVENT_TYPES = {
    MatchRule.DOCUMENT_NUMBER: EventType.PERSON_MATCHED,
    MatchRule.NAME_DOB: EventType.PERSON_MATCHED,
    MatchRule.NAME: EventType.PERSON_MATCHED,
    MatchRule.DOCUMENT_NUMBER_AMBIGUOUS: EventType.PERSON_AMBIGUOUS,
    MatchRule.NAME_DOB_AMBIGUOUS: EventType.PERSON_AMBIGUOUS,
    MatchRule.NAME_AMBIGUOUS: EventType.PERSON_AMBIGUOUS,
}


@dataclass(frozen=True, slots=True)
class EmployeeMatch:
    """Belge adayının çalışan eşleştirme hükmü (05.5); kurallar modül açıklamasındadır.

    `employee_ids` hükmün dayandığı çalışanlardır (E numarası sırasıyla): eşleşmede (satır 5a dahil)
    tek çalışan, belirsiz eşleşmede uyan bütün çalışanlar, yalnız isim eşleşmesinde ismi eşleşen
    bütün çalışanlar; çelişkili anahtarda ve `NO_MATCH`'te boştur. `conflicts` çelişkili anahtarın
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
        """Eşleşen çalışan; yalnız satır 1, 3 ve 5a'da dolu."""
        return self.employee_ids[0] if self.matched_by is not None else None

    @property
    def action(self) -> EmployeeAction | None:
        """Eşleşmede `match`, Unresolved'a giden hükümde `none`.

        `NO_MATCH`'te `None`'dır: satır 6–8'in eylemi (`create`, `pending`, `none`) bu adımda
        verilmez, `resolve_unmatched` temiz numara ve okunan ad-soyadla belirler.
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
            case MatchRule.NAME_AMBIGUOUS:
                return (
                    "Belirsiz eşleşme: belgede doğum tarihi yok, ad-soyad birden fazla çalışana "
                    f"uyuyor ({employees}). Çalışan otomatik eşleştirilmez."
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

    Olay dışında veritabanına yazmaz: eşleşmede alias ve numara birikimi (`accumulate_identity`),
    yeni çalışan (`create_employee`), onay bekleyen profil (`propose_pending_profile`) ve kuyruk
    kaydı (08.1) sonraki adımlardır. `file_id`/`page_index` olayın yeridir
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
        # Kaldırılmış numara (10.5.8) sahiplik saymaz: satır 1–2 yalnız etkin kayıtlarla.
        owners = _employee_ids(number_owners(session, numbers))
        if len(owners) == 1:
            return EmployeeMatch(MatchRule.DOCUMENT_NUMBER, owners)
        if owners:
            return EmployeeMatch(MatchRule.DOCUMENT_NUMBER_AMBIGUOUS, owners)
    return _decide_by_name(session, key.name_keys, key.date_of_birth)


def _decide_by_name(session: Session, name_keys: Sequence[str], born: date | None) -> EmployeeMatch:
    # §20.2.2 satır 3–5: isim anahtarlarından biri bir alias'la eşleşiyor mu, doğum tarihi tutuyor
    # mu; doğum tarihi yoksa satır 5a. Profil onayı (08.3.1, 10.7.3) çalışana yazılacak yazımları
    # da bununla sınar.
    if not name_keys:
        return EmployeeMatch(MatchRule.NO_MATCH)
    # Birleştirilmiş çalışan (10.5.9) aranmaz: yazımları kalan kayda taşınmıştır.
    named = session.execute(
        select(Employee.id, Employee.date_of_birth)
        .join(EmployeeAlias, EmployeeAlias.employee_id == Employee.id)
        .where(
            EmployeeAlias.normalized_name.in_(name_keys),
            ACTIVE_ALIAS,
            Employee.status != EmployeeStatus.MERGED.value,
        )
    ).all()
    if not named:
        return EmployeeMatch(MatchRule.NO_MATCH)
    fitting = _employee_ids(
        employee_id for employee_id, birth in named if born is not None and birth == born
    )
    if len(fitting) == 1:
        return EmployeeMatch(MatchRule.NAME_DOB, fitting)
    if fitting:
        return EmployeeMatch(MatchRule.NAME_DOB_AMBIGUOUS, fitting)
    employees = _employee_ids(employee_id for employee_id, _ in named)
    if born is None:
        # Satır 5a (05.5.4): sayım çalışan başınadır — aynı çalışanın iki alias'ı tek kayıt.
        rule = MatchRule.NAME if len(employees) == 1 else MatchRule.NAME_AMBIGUOUS
        return EmployeeMatch(rule, employees)
    return EmployeeMatch(MatchRule.NAME_ONLY, employees)


def _employee_ids(ids: Iterable[str]) -> tuple[str, ...]:
    # Tekrarsız, E numarası sırasıyla (`E9999` < `E10000`): hüküm sorgu sırasına bağlı kalmaz.
    return tuple(sorted(set(ids), key=lambda employee_id: (len(employee_id), employee_id)))


# --- otomatik çalışan oluşturma (05.6) -------------------------------------------------------

# §20.2.3 koşul 2: normalize numara en az bu kadar karakterdir.
CLEAN_DOCUMENT_NUMBER_MIN_LENGTH = 5
# §20.1.6 makul yaş (`dob_plausible`, 06.5.1): tamamlanmış yıl, iki uç dahil. Doğrulayıcı
# (`app.pipeline.validate`) ve satır 6b (§20.2.4 koşul 3) aynı ölçüyü kullanır.
MIN_AGE = 16
MAX_AGE = 90


class CreationBasis(enum.StrEnum):
    """Otomatik yeni çalışanın açılış dayanağı: `EMPLOYEE_CREATED` verisinde `basis` (§8.3)."""

    DOCUMENT_NUMBER = "document_number"  # §20.2.2 satır 6, 05.6.1
    NAME_DOB = "name_dob"  # §20.2.2 satır 6b, 05.6.2


class EmployeeCreationRefusedError(ValueError):
    """`create_employee` §20.2.2 satır 6 ve 6b'nin uymadığı anahtarla çağrıldı (R9); hiçbir şey
    yazılmadı.

    Mesaj yalnız ret gerekçesini taşır (hüküm, koşul), kişisel değer taşımaz.
    """


@dataclass(frozen=True, slots=True)
class _ProfileName:
    # Klasör adı veren ad-soyad okuması (K8, D9).
    given_names: str
    surname: str
    normalized_name: str


@dataclass(frozen=True, slots=True)
class _NewEmployee:
    # Satır 6'da temiz numara, satır 6b'de `None`: temiz olmayan numara yazılmaz (D11).
    document_number: str | None
    name: _ProfileName
    basis: CreationBasis


def dob_plausible(date_of_birth: date, *, today: date) -> bool:
    """§20.1.6: doğum tarihi `today`'den önce ve o gün 16–90 yaşta (tamamlanmış yıl, iki uç dahil).

    `today` referans gündür — planda partinin alındığı gün (06.1.2). Doğrulayıcı `dob_plausible`
    (06.5.1) ve satır 6b (§20.2.4) bu ölçüyü kullanır.
    """
    return date_of_birth < today and MIN_AGE <= _age(date_of_birth, today) <= MAX_AGE


def _age(date_of_birth: date, today: date) -> int:
    # Tamamlanmış yıl: yıl dönümü `today`'e gelmemişse bir eksik (29 Şubat'ta doğan 28 Şubat'ta).
    birthday_ahead = (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
    return today.year - date_of_birth.year - birthday_ahead


def clean_document_number(key: PersonKey, entry: CatalogEntry) -> str | None:
    """§20.2.3: anahtarın belge numarası temizse normalize değerini, değilse `None` döner.

    `entry` adayın katalog türüdür. Koşullar: (1) türün `required_fields`'ında `document_number`
    var; (2) numara okunaklı (`DocumentNumberKey.legible`) ve normalize hâli en az 5 karakter;
    (3) MRZ'den okunduysa alan ve bileşik kontrol haneleri tutuyor
    (`mrz_allows_clean_document_number`). Anahtarda tek numara olmalıdır: birden fazla numara
    çelişkidir (D8), hangisinin temiz olduğu seçilmez.
    """
    if DOCUMENT_NUMBER not in entry.required_fields or len(key.document_numbers) != 1:
        return None
    (number,) = key.document_numbers
    if not number.legible or len(number.value) < CLEAN_DOCUMENT_NUMBER_MIN_LENGTH:
        return None
    return number.value if key.mrz_allows_clean_document_number else None


def can_create_employee(
    key: PersonKey, match: EmployeeMatch, *, entry: CatalogEntry, today: date | None = None
) -> bool:
    """§20.2.2 satır 6 ya da 6b uyuyor mu: `match` hiç eşleşme bulmadı, numara temiz ya da doğum
    tarihi §20.2.4'e uyuyor, ad-soyad klasör adı verecek biçimde Latin okunmuş (05.2.2, D9). Yan
    etkisizdir; `employee.action: create` kararı budur. `today` doğum tarihinin makul yaş
    doğrulamasının referans günüdür (`dob_plausible`), verilmezse bugündür."""
    return not isinstance(_new_employee(key, match, entry, today=today), str)


def create_employee(
    session: Session,
    layout: DataLayout,
    key: PersonKey,
    *,
    entry: CatalogEntry,
    today: date | None = None,
    file_id: int | None = None,
    page_index: int | None = None,
) -> Employee:
    """§20.2.2 satır 6 ya da 6b: kayıtlı çalışanla eşleşmeyen anahtardan temiz belge numarasıyla
    (05.6.1) ya da Latin ad-soyad ve doğum tarihiyle (05.6.2, §20.2.4) yeni çalışan ve klasörünü
    açar (R9, K7).

    Hüküm çağıranın elindeki eşleştirmeye güvenilmeden veritabanında yeniden değerlendirilir (olay
    yazılmaz): satır 6 ve 6b uymuyorsa `EmployeeCreationRefusedError` — kayıt, klasör ve olay
    yazılmaz. `today` doğum tarihinin makul yaş doğrulamasının referans günüdür (planda partinin
    alındığı gün), verilmezse bugündür. Uyuyorsa aynı işlemde:

    - `allocate_employee_number` ile E numarası (K8) ve `Ad_Soyad_E0001` klasör adı,
    - `employees` satırı `PersonKey.employee_fields()` okumalarıyla,
    - `employee_aliases`: `Ad Soyad` yazımı ve varsa orijinal yazım, anahtarın normalize değeriyle
      (aynı yazım bir kez), `script` yazımın alfabesiyle (`detect_script`, 05.8.3),
    - `employee_identifiers`: yalnız satır 6'da, temiz numara §20.2.1 normalize değeriyle, `kind`
      türün slug'ı; satır 6b'de numara hiçbir yere yazılmaz (temiz değildir, D11),
    - `Employees/<klasör>/Alinan/` ve `Hazir/` dizinleri,
    - `EMPLOYEE_CREATED` olayı (`employee_id` sütunu; veri `action`, `basis` — `CreationBasis` —
      ve `document_type_slug`).

    `file_id`/`page_index` olayın yeridir (adayın ilk sayfası); verilmezse etkin `event_context`ten
    alınır. Oturum commit edilmez; dizin işlem geri alınsa da diskte kalır (boş klasör).
    """
    new = _new_employee(key, _decide(session, key), entry, today=today)
    if isinstance(new, str):
        raise EmployeeCreationRefusedError(
            f"Yeni çalışan açılmaz (§20.2.2 satır 6, 6b; R9): {new}."
        )
    employee_id = allocate_employee_number(session)
    folder_name = employee_folder_name(new.name.given_names, new.name.surname, employee_id)
    employee = Employee(id=employee_id, folder_name=folder_name, **key.employee_fields())
    session.add(employee)
    for raw_name, normalized in _spellings(key).items():
        session.add(
            EmployeeAlias(
                employee=employee,
                raw_name=raw_name,
                normalized_name=normalized,
                script=detect_script(raw_name),
            )
        )
    if new.document_number is not None:
        session.add(
            EmployeeIdentifier(employee=employee, kind=entry.slug, value=new.document_number)
        )
    session.flush()
    layout.ensure_employee_tree(folder_name)
    record_event(
        session,
        EventType.EMPLOYEE_CREATED,
        file_id=file_id,
        page_index=page_index,
        employee_id=employee_id,
        data={
            "action": EmployeeAction.CREATE.value,
            "basis": new.basis.value,
            "document_type_slug": entry.slug,
        },
    )
    return employee


def _new_employee(
    key: PersonKey, match: EmployeeMatch, entry: CatalogEntry, *, today: date | None
) -> _NewEmployee | str:
    # Satır 6 ya da 6b uyuyorsa açılacak çalışanın zorunlu değerleri ve dayanağı, uymuyorsa kişisel
    # değer taşımayan ret gerekçesi. Temiz numara önce gelir (satır 6), ad + doğum tarihi sonra.
    if match.rule is not MatchRule.NO_MATCH:
        return f"eşleştirme hükmü {match.rule.value}"
    number = clean_document_number(key, entry)
    if number is None:
        problem = _name_dob_problem(key, entry, today=today)
        if problem is not None:
            return f"temiz belge numarası yok (§20.2.3) ve {problem} (§20.2.4)"
    name = _profile_name(key)
    if isinstance(name, str):
        return name
    if number is None:
        return _NewEmployee(None, name, CreationBasis.NAME_DOB)
    return _NewEmployee(number, name, CreationBasis.DOCUMENT_NUMBER)


def _name_dob_problem(key: PersonKey, entry: CatalogEntry, *, today: date | None) -> str | None:
    # §20.2.4 koşul 1 ve 3; uyuyorsa `None`, uymuyorsa kişisel değer taşımayan sorun. Koşul 2
    # (Latin ad-soyad) `_profile_name`'in, koşul 4 (ucuz modelin doğrulanmamış okuması dayanak
    # olmaz) ön elemenin işidir (`unverified_date_of_birth`).
    if DATE_OF_BIRTH not in entry.required_fields:
        return "doğum tarihi türün zorunlu alanı değil"
    born = key.date_of_birth
    if born is None or DATE_OF_BIRTH in key.conflicts:
        return "doğum tarihi okunmadı ya da sayfalar arasında çelişiyor"
    if not key.date_of_birth_legible:
        return "doğum tarihi okunaklı okunmadı"
    if not dob_plausible(born, today=date.today() if today is None else today):
        return "doğum tarihi makul yaş doğrulamasından geçmedi (dob_plausible)"
    return None


def _profile_name(key: PersonKey) -> _ProfileName | str:
    # Ad-soyad okunmuş, Latin yazımı var (05.2.2) ve klasör adı veriyorsa çalışan kaydına yazılacak
    # Latin değerleri, değilse kişisel değer taşımayan sorun.
    if key.given_names is None or key.surname is None or key.normalized_name is None:
        return "ad-soyad okunmadı"
    given_names, surname = key.latin_given_names, key.latin_surname
    if given_names is None or surname is None:
        return LATIN_MISSING
    try:
        person_slug(given_names, surname)
    except SlugError:
        return "ad-soyad klasör adına çevrilemiyor (K8)"
    return _ProfileName(given_names, surname, key.normalized_name)


def _spellings(key: PersonKey) -> dict[str, str]:
    # Belgedeki isim yazımları (ham → normalize anahtar), aynı ham yazım bir kez: önce
    # `Ad Soyad`, sonra orijinal yazım.
    spellings: dict[str, str] = {}
    given_names, surname, normalized_name = key.given_names, key.surname, key.normalized_name
    if given_names is not None and surname is not None and normalized_name is not None:
        spellings[f"{given_names} {surname}"] = normalized_name
    original, normalized_original = key.original_script_name, key.normalized_original_name
    if original is not None and normalized_original is not None:
        spellings.setdefault(original.original, normalized_original)
    return spellings


# --- onay bekleyen profil (05.7.1) -----------------------------------------------------------


class UnmatchedRule(enum.StrEnum):
    """`NO_MATCH` hükmünün §20.2.2 satır 6–8 karşılığı ya da tablo dışı eksik kişi (D9, D10)."""

    CREATE = "create"  # satır 6 ve 6b; dayanak `UnmatchedResolution.basis`
    PENDING_PROFILE = "pending_profile"  # satır 7
    NO_PERSON = "no_person"  # satır 8
    INCOMPLETE_PERSON = "incomplete_person"  # tabloda yok: D9, D10


PENDING_PROFILE_REASON = (
    "Onay bekleyen profil: kayıtlı çalışanla eşleşme yok, temiz belge numarası yok (§20.2.3) ve "
    "doğum tarihi yeni çalışan açmaya yetmiyor (§20.2.4: türün zorunlu alanı değil, okunmadı, "
    "sayfalar arasında çelişiyor ya da doğrulanmadı). Yeni çalışan yalnız onayla açılır (K7)."
)
# 05.2.2: ad-soyad okundu ama Latin yazımı ne belgede basılı, ne MRZ'de var, ne Kiril çevirisiyle
# bulunuyor; temiz numara olsa da çalışan otomatik açılmaz.
LATIN_MISSING = "Latin yazım belgede yok"
PENDING_PROFILE_LATIN_REASON = (
    f"Onay bekleyen profil: {LATIN_MISSING}. Ad-soyad yalnız Latin olmayan alfabeyle okundu ve "
    "tahminle çevrilmez (05.2.2); İK onayda Latin adı yazar. Yeni çalışan yalnız onayla açılır "
    "(K7)."
)
NO_PERSON_REASON = "Kişi tespit edilemedi: belgede ne ad-soyad ne belge numarası okundu."


class PendingProfileRefusedError(ValueError):
    """`propose_pending_profile` §20.2.2 satır 7'nin uymadığı anahtarla çağrıldı; hiçbir şey
    yazılmadı. Mesaj yalnız ret gerekçesini taşır, kişisel değer taşımaz."""


@dataclass(frozen=True, slots=True)
class ProposedProfile:
    """§20.2.2 satır 7'nin önerilen profili: onayla (08.3) açılacak çalışanın okumaları.

    Alanlar `create_employee`'nin çalışan kaydına yazdıklarıdır (`PersonKey.employee_fields()`);
    `aliases` onayda `employee_aliases`'a yazılacak `(raw_name, normalized_name)` çiftleridir
    (orijinal yazımın anahtarı sayfanın diliyle normalize edildiği için yeniden hesaplanmaz).
    Belge numarası taşınmaz: temiz değildir (§20.2.3). Kişisel değer taşır — olay loguna yazılmaz,
    yalnız kuyruk kaydının payload'ına girer.

    Ad ve soyad Latin yazımdır (05.2.2); Latin yazım belgede yoksa ikisi de `None`'dır
    (`latin_missing`) ve onayda İK yazar — öneri kendi başına onaylanamaz.
    """

    given_names: str | None
    surname: str | None
    other_names: str | None
    original_script_name: str | None
    date_of_birth: date | None
    nationality: str | None
    aliases: tuple[tuple[str, str], ...]

    @property
    def latin_missing(self) -> bool:
        """Latin yazım belgede yok (05.2.2): ad ve soyadı onayda İK yazar."""
        return self.given_names is None or self.surname is None

    def fields(self) -> ProfileFields:
        """Önerinin çalışan kaydına yazılacak alanları: panelin düzenleme formunun başlangıcı.
        Latin yazımı olmayan ad ve soyad boş metindir (formda İK doldurur)."""
        return ProfileFields(
            given_names=self.given_names or "",
            surname=self.surname or "",
            other_names=self.other_names,
            original_script_name=self.original_script_name,
            date_of_birth=self.date_of_birth,
            nationality=self.nationality,
        )

    def payload(self) -> dict[str, object]:
        """Kuyruk kaydı payload'ının JSON uyumlu `proposed_profile` bölümü (08.1)."""
        born = self.date_of_birth
        return {
            "proposed_profile": {
                GIVEN_NAMES: self.given_names,
                SURNAME: self.surname,
                OTHER_NAMES: self.other_names,
                ORIGINAL_SCRIPT_NAME: self.original_script_name,
                DATE_OF_BIRTH: None if born is None else born.isoformat(),
                NATIONALITY: self.nationality,
                "aliases": [
                    {"raw_name": raw_name, "normalized_name": normalized}
                    for raw_name, normalized in self.aliases
                ],
            }
        }


@dataclass(frozen=True, slots=True)
class UnmatchedResolution:
    """`NO_MATCH` hükmünün satır 6–8 kararı (05.6, 05.7.1); `EmployeeMatch` ile aynı `action`,
    `queue` ve `reason` okumalarını verir.

    `basis` yalnız `create`'te doludur: satır 6 (`document_number`) ya da 6b (`name_dob`).
    `proposed_profile` yalnız satır 7'de doludur. `detail` eksik kişide okunamayanı söyler
    (kişisel değer yok). `latin_missing` satır 7'nin Latin yazımı olmayan öneriyle verildiğini
    söyler (05.2.2): temiz numara ya da doğum tarihi olsa da çalışan otomatik açılmaz.
    """

    rule: UnmatchedRule
    proposed_profile: ProposedProfile | None = None
    detail: str | None = None
    latin_missing: bool = False
    basis: CreationBasis | None = None

    @property
    def action(self) -> EmployeeAction:
        match self.rule:
            case UnmatchedRule.CREATE:
                return EmployeeAction.CREATE
            case UnmatchedRule.PENDING_PROFILE:
                return EmployeeAction.PENDING
            case _:
                return EmployeeAction.NONE

    @property
    def queue(self) -> QueueKind | None:
        """Satır 6 ve 6b Hazir'a gider (`None`); onay bekleyen profil ve kişisiz belge
        Unresolved'a."""
        return None if self.rule is UnmatchedRule.CREATE else QueueKind.UNRESOLVED

    @property
    def reason(self) -> str | None:
        match self.rule:
            case UnmatchedRule.PENDING_PROFILE if self.latin_missing:
                return PENDING_PROFILE_LATIN_REASON
            case UnmatchedRule.PENDING_PROFILE:
                return PENDING_PROFILE_REASON
            case UnmatchedRule.NO_PERSON:
                return NO_PERSON_REASON
            case UnmatchedRule.INCOMPLETE_PERSON:
                return (
                    f"Kişi eksik okundu: kayıtlı çalışanla eşleşme yok, {self.detail}. "
                    "Yeni çalışan açılmaz, profil önerilmez."
                )
            case _:
                return None


def resolve_unmatched(
    key: PersonKey, match: EmployeeMatch, *, entry: CatalogEntry, today: date | None = None
) -> UnmatchedResolution:
    """§20.2.2 satır 6–8: hiç eşleşme bulunmayan anahtarın çalışan kararını verir (yan etkisiz).

    - Satır 6 (`create`, `basis: document_number`): temiz numara (§20.2.3) ve klasör adı veren
      Latin ad-soyad (`can_create_employee`).
    - Satır 6b (`create`, `basis: name_dob`, 05.6.2): temiz numara yok, klasör adı veren Latin
      ad-soyad ve §20.2.4'e uyan doğum tarihi — türün zorunlu alanı, okunaklı, anahtarda tek,
      sayfalar arasında çelişkisiz, `today`e göre makul yaş (`dob_plausible`; verilmezse bugün).
    - Satır 7 (`pending`, Unresolved): ad-soyad klasör adı verecek biçimde okunmuş ama satır 6 ve
      6b uymuyor; önerilen profil kararın içindedir. Ad-soyad okunmuş ama Latin yazımı yoksa
      (05.2.2) numara temiz ya da doğum tarihi uygun olsa da satır 7'dir: öneride ad ve soyad
      boştur, İK onayda yazar.
    - Satır 8 (`none`, Unresolved): ne ad ya da soyad parçası, ne orijinal yazım, ne belge numarası
      okunmuş.
    - Eksik kişi (`none`, Unresolved; tabloda yok): temiz numara var ama ad-soyad okunmamış ya da
      klasör adı vermiyor (D9); ya da ad-soyad kullanılamıyor ama bir numara veya isim okunmuş
      (D10).

    `match` `NO_MATCH` değilse satır 1–5 ya da çelişkili anahtar hükmü verilmiştir; `ValueError`.
    """
    if match.rule is not MatchRule.NO_MATCH:
        raise ValueError(
            "§20.2.2 satır 6–8 yalnız eşleşme bulunmayan hükme uygulanır: "
            f"eşleştirme hükmü {match.rule.value}"
        )
    number = clean_document_number(key, entry)
    name = _profile_name(key)
    if not isinstance(name, str):
        new = _new_employee(key, match, entry, today=today)
        if not isinstance(new, str):
            return UnmatchedResolution(UnmatchedRule.CREATE, basis=new.basis)
        return UnmatchedResolution(UnmatchedRule.PENDING_PROFILE, _proposed_profile(key, name))
    if name == LATIN_MISSING:
        return UnmatchedResolution(
            UnmatchedRule.PENDING_PROFILE, _proposed_profile(key, None), latin_missing=True
        )
    read_nothing = (
        not key.document_numbers
        and not key.name_keys
        and key.surname is None
        and key.given_names is None
    )
    if read_nothing:
        return UnmatchedResolution(UnmatchedRule.NO_PERSON)
    numbered = "var" if number is not None else "yok"
    return UnmatchedResolution(
        UnmatchedRule.INCOMPLETE_PERSON, detail=f"{name}, temiz belge numarası {numbered}"
    )


def propose_pending_profile(
    session: Session,
    key: PersonKey,
    *,
    entry: CatalogEntry,
    today: date | None = None,
    file_id: int | None = None,
    page_index: int | None = None,
) -> ProposedProfile:
    """§20.2.2 satır 7: kayıtlı çalışanla eşleşmeyen, satır 6 ve 6b'ye uymayan anahtarın profilini
    onaya önerir (05.7.1, K7).

    Hüküm veritabanında olaysız yeniden değerlendirilir (`today` `resolve_unmatched`'inki): satır 7
    uymuyorsa (eşleşme var, satır 6, 6b, satır 8 ya da eksik kişi) `PendingProfileRefusedError` —
    hiçbir şey yazılmaz. Uyuyorsa yalnız `EMPLOYEE_PENDING` olayı yazılır (veri `action`, `queue`,
    `document_type_slug`; mesaj gerekçe; kişisel değer yok). Çalışan, isim yazımı, numara ve klasör
    yazılmaz — onaysız çalışan oluşmaz. Kuyruk kaydı (08.1) ve onay (08.3) sonraki adımlardır.
    Oturum commit edilmez.
    """
    match = _decide(session, key)
    if match.rule is not MatchRule.NO_MATCH:
        raise _pending_refused(f"eşleştirme hükmü {match.rule.value}")
    resolution = resolve_unmatched(key, match, entry=entry, today=today)
    profile = resolution.proposed_profile
    if profile is None:
        raise _pending_refused(f"satır 6–8 kararı {resolution.rule.value}")
    record_event(
        session,
        EventType.EMPLOYEE_PENDING,
        file_id=file_id,
        page_index=page_index,
        message=resolution.reason,
        data={
            "action": resolution.action.value,
            "queue": QueueKind.UNRESOLVED.value,
            "document_type_slug": entry.slug,
        },
    )
    return profile


def _pending_refused(verdict: str) -> PendingProfileRefusedError:
    return PendingProfileRefusedError(
        f"Onay bekleyen profil önerilmez (§20.2.2 satır 7, K7): {verdict}."
    )


def _approvable_profile(key: PersonKey, resolution: UnmatchedResolution) -> ProposedProfile | None:
    # Onayın okuyacağı öneri: satır 7'ninki. Satır 6b'nin (05.6.2) gelmesinden önce kuyruğa düşmüş
    # öneri geriye dönük açılmaz ama onaylanabilir: anahtarı bugün 6b'ye uyan öneri satır 7 gibi
    # onaylanır (§C84); numara yine yazılmaz. Satır 6 (temiz numara) öneri vermez.
    if resolution.proposed_profile is not None or resolution.basis is not CreationBasis.NAME_DOB:
        return resolution.proposed_profile
    name = _profile_name(key)
    return None if isinstance(name, str) else _proposed_profile(key, name)


def _proposed_profile(key: PersonKey, name: _ProfileName | None) -> ProposedProfile:
    # `name` yoksa Latin yazım belgede yok (05.2.2): ad ve soyadı İK onayda yazar.
    return ProposedProfile(
        given_names=None if name is None else name.given_names,
        surname=None if name is None else name.surname,
        other_names=key.latin_other_names,
        original_script_name=key.original_spelling,
        date_of_birth=key.date_of_birth,
        nationality=key.nationality,
        aliases=tuple(_spellings(key).items()),
    )


# --- onay bekleyen profili onaylama (08.3.1) -------------------------------------------------


class ProfileApprovalRefusedError(ValueError):
    """`approve_pending_profile` §20.2.2 satır 7'nin onay anında uymadığı anahtarla çağrıldı;
    hiçbir şey yazılmadı. Mesaj yalnız hükmü taşır, kişisel değer taşımaz."""


# Düzenlenebilir profil alanları (10.7.3), formdaki ve olay verisindeki sırasıyla.
PROFILE_FIELDS = (
    GIVEN_NAMES,
    SURNAME,
    OTHER_NAMES,
    ORIGINAL_SCRIPT_NAME,
    DATE_OF_BIRTH,
    NATIONALITY,
)
# `employees` isim sütunları `String(255)`dir.
PROFILE_TEXT_MAX_LENGTH = 255
_REQUIRED_NAMES = (GIVEN_NAMES, SURNAME)
# 05.2.2: ad, soyad ve diğer isimler yalnız Latin harfi taşır.
# Form sorunları kaynak dildedir; panel gösterirken çevirir (10.10.3).
LATIN_ONLY_PROBLEM = N_("Latin harfleriyle yazılmalı; Latin olmayan yazım Orijinal yazım alanına")
LATIN_MISSING_PROBLEM = f"{LATIN_MISSING}; onayda Latin harfleriyle yazılmalı (05.2.2)"


@dataclass(frozen=True, slots=True)
class ProfileFields:
    """İK'nın onayladığı profil (10.7.3): önerilen profilin (`ProposedProfile.fields()`) çalışan
    kaydına yazılacak alanları, panelde düzeltilmiş olabilir.

    Yalnız çalışan kaydıdır: belge içeriği (sayfalar, tür, sayfa okumaları, plan) bununla
    değişmez (K9, K17). Belge numarası alanı yoktur: temiz olmayan numara yazılmaz (§20.2.3, D11).
    Kişisel değer taşır — olay loguna yalnız alan adları girer.
    """

    given_names: str
    surname: str
    other_names: str | None = None
    original_script_name: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None

    def values(self) -> dict[str, str | None]:
        """JSON uyumlu değerler (`PROFILE_FIELDS` sırasıyla; tarih `YYYY-AA-GG`)."""
        born = self.date_of_birth
        return {
            GIVEN_NAMES: self.given_names,
            SURNAME: self.surname,
            OTHER_NAMES: self.other_names,
            ORIGINAL_SCRIPT_NAME: self.original_script_name,
            DATE_OF_BIRTH: None if born is None else born.isoformat(),
            NATIONALITY: self.nationality,
        }


class ProfileFieldsError(ProfileApprovalRefusedError):
    """Onaylanan profilin alanları çalışan kaydına yazılamaz; `errors` alan adı → sorun.

    Mesaj ve `errors` kişisel değer taşımaz. Hiçbir şey yazılmadı.
    """

    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        problems = "; ".join(f"{name}: {problem}" for name, problem in errors.items())
        super().__init__(f"Profil alanları geçersiz: {problems}.")


def check_profile_fields(fields: ProfileFields, *, today: date | None = None) -> dict[str, str]:
    """Onaylanacak profilin sorunları (10.7.3): alan adı → sorun; boş sözlük geçerlidir.

    Ad ve soyad zorunludur; isim alanları boş, 255 karakterden uzun, denetim karakterli ya da
    harfsiz/rakamsız olamaz (alias anahtarı çıkmalı, §20.2.1) ve ad-soyad klasör adı vermelidir
    (K8). Ad, soyad ve diğer isimler yalnız Latin harfi taşır (aksanlı Latin serbest); Latin
    olmayan yazımın yeri orijinal yazımdır (05.2.2). Doğum tarihi `today`den (verilmezse bugün)
    sonra olamaz; vatandaşlık ICAO kodudur (`RUS`, `D`). İsteğe bağlı alan yoksa `None`'dır, boş
    metin değil. Kişisel değer dönmez.
    """
    errors: dict[str, str] = {}
    names = {
        GIVEN_NAMES: fields.given_names,
        SURNAME: fields.surname,
        OTHER_NAMES: fields.other_names,
        ORIGINAL_SCRIPT_NAME: fields.original_script_name,
    }
    for name, value in names.items():
        if value is None and name not in _REQUIRED_NAMES:
            continue
        problem = _name_problem(value)
        if problem is None and name in _LATIN_FIELDS and not is_latin_name(str(value)):
            problem = LATIN_ONLY_PROBLEM
        if problem is not None:
            errors[name] = problem
    if not errors.keys() & _REQUIRED_NAMES:
        try:
            person_slug(fields.given_names, fields.surname)
        except SlugError:
            errors[GIVEN_NAMES] = N_("ad-soyad klasör adına çevrilemiyor (K8)")
    born = fields.date_of_birth
    if born is not None and born > (today or date.today()):
        errors[DATE_OF_BIRTH] = N_("gelecekte olamaz")
    nationality = fields.nationality
    if nationality is not None and not _NATIONALITY.fullmatch(nationality):
        errors[NATIONALITY] = N_("ICAO uyruk kodu olmalı (1–3 büyük harf, ör. RUS, D)")
    return errors


def _name_problem(value: str | None) -> str | None:
    if value is None or not value.strip():
        return N_("boş olamaz")
    if len(value) > PROFILE_TEXT_MAX_LENGTH:
        return Translatable(N_("en fazla {limit} karakter olabilir"), limit=PROFILE_TEXT_MAX_LENGTH)
    if any(unicodedata.category(char) == "Cc" for char in value):
        return N_("denetim karakteri içeremez")
    try:
        normalize_name(value)
    except EmptyNameError:
        return N_("harf ya da rakam içermiyor")
    return None


def edited_profile_fields(profile: ProposedProfile, fields: ProfileFields) -> tuple[str, ...]:
    """Önerilen profilden farklı onaylanan alanların adları (`PROFILE_FIELDS` sırasıyla)."""
    proposed, confirmed = profile.fields().values(), fields.values()
    return tuple(name for name in PROFILE_FIELDS if proposed[name] != confirmed[name])


def review_pending_profile(
    session: Session, key: PersonKey, *, entry: CatalogEntry, fields: ProfileFields | None = None
) -> ProposedProfile:
    """Onay anındaki önerilen profil (08.3.1, 10.7.3): onayın hükmü olaysız verilir, hiçbir şey
    yazılmaz.

    Satır 7 veritabanında yeniden değerlendirilir; artık uymuyorsa (kişi kayıtlı bir çalışanla
    eşleşiyor, satır 6, satır 8 ya da eksik kişi) `ProfileApprovalRefusedError`. Anahtarı bugün
    satır 6b'ye uyan öneri (05.6.2'den önce kuyruğa düşmüş) satır 7 gibi onaylanır. `fields` İK'nın
    düzelttiği profildir: `check_profile_fields`'tan geçmezse `ProfileFieldsError`, çalışana
    yazılacak yazımlar doğum tarihiyle kayıtlı bir çalışana uyuyorsa (satır 3–5; hükmün dayandığı
    E numaralarıyla) `ProfileApprovalRefusedError`. Panel öneriyi ve düzeltmeyi onaydan önce bununla
    sınar; `approve_pending_profile` aynı hükmü E numarası kilidinin içinde yeniden verir.
    """
    if fields is not None:
        errors = check_profile_fields(fields)
        if errors:
            raise ProfileFieldsError(errors)
    match = _decide(session, key)
    if match.rule is not MatchRule.NO_MATCH:
        raise _approval_refused(f"eşleştirme hükmü {match.rule.value}")
    resolution = resolve_unmatched(key, match, entry=entry)
    profile = _approvable_profile(key, resolution)
    if profile is None:
        raise _approval_refused(f"satır 6–8 kararı {resolution.rule.value}")
    confirmed = profile.fields() if fields is None else fields
    # Belgenin yazımları satır 7'de kimseye uymadı; düzeltilmiş yazım ya da doğum tarihi uyabilir.
    verdict = _decide_by_name(
        session,
        tuple(dict.fromkeys(_employee_aliases(profile, confirmed).values())),
        confirmed.date_of_birth,
    )
    if verdict.rule is not MatchRule.NO_MATCH:
        raise _approval_refused(
            "onaylanan profil kayıtlı çalışanla eşleşiyor: eşleştirme hükmü "
            f"{verdict.rule.value} ({', '.join(verdict.employee_ids)})"
        )
    return profile


def approve_pending_profile(
    session: Session,
    layout: DataLayout,
    key: PersonKey,
    *,
    entry: CatalogEntry,
    actor: str,
    fields: ProfileFields | None = None,
    file_id: int | None = None,
    page_index: int | None = None,
) -> Employee:
    """Onay bekleyen profili İK'nın onayıyla çalışana çevirir (08.3.1, 10.7.3; §20.2.2 satır 7,
    K7, K16).

    `actor` iki aşamalı onayı tamamlamış kullanıcının adıdır; boşsa `ValueError`. Hüküm çağıranın
    elindeki öneriye güvenilmeden veritabanında olaysız yeniden değerlendirilir
    (`review_pending_profile`): satır 7 artık uymuyorsa `ProfileApprovalRefusedError` — kayıt,
    klasör ve olay yazılmaz. Öneriden sonra kişinin numarası ya da ismi kayıtlı bir çalışanda
    görünüyorsa (satır 1–5) yeni çalışan açılmaz; belge çalışana atanarak çözülür (08.2.1).

    `fields` İK'nın panelde düzelttiği profildir (10.7.3); verilmezse önerinin alanları yazılır —
    Latin yazımı belgede olmayan öneride (05.2.2) ad ve soyadı İK yazmalıdır, `fields` verilmezse
    `ProfileFieldsError`.
    Verilirse `check_profile_fields`'tan geçmelidir (`ProfileFieldsError`) ve çalışana yazılacak
    bütün yazımlar doğum tarihiyle birlikte satır 3–5'e karşı yeniden sınanır: düzeltilmiş ad ya
    da doğum tarihi kayıtlı bir çalışana uyuyorsa ikinci çalışan açılmaz
    (`ProfileApprovalRefusedError`, hükmün dayandığı E numaralarıyla). Uyuyorsa aynı işlemde:

    - `allocate_employee_number` ile E numarası (K8) ve `Ad_Soyad_E0001` klasör adı,
    - `employees` satırı onaylanan alanlarla,
    - `employee_aliases`: belgenin yazımları (`Ad Soyad` ve varsa orijinal yazım, anahtarın
      normalize değeriyle) ve düzeltilmiş ad-soyad ya da orijinal yazım belgede yoksa o yazım
      (§20.2.1 normalize değeriyle), `script` yazımın alfabesiyle,
    - `Employees/<klasör>/Alinan/` ve `Hazir/` dizinleri,
    - `EMPLOYEE_CREATED` olayı kullanıcı adıyla (`employee_id` sütunu; veri `action: pending`,
      `document_type_slug`; öneriden farklı onaylanan alan varsa adları `edited_fields`'ta —
      değerleri değil).

    Belge numarası yazılmaz: temiz değildir (§20.2.3) ve yanlış okunmuş numara başka birinin
    belgesini satır 1'le bu çalışana bağlayabilir (D11). `entry` belgenin katalog türüdür;
    `file_id`/`page_index` olayın yeridir, verilmezse etkin `event_context`ten alınır. Oturum
    commit edilmez; dizin işlem geri alınsa da diskte kalır (boş klasör).
    """
    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")
    # E numarası hükümden önce ayrılır: tahsis kilidi işlem sonuna kadar tutulur, aynı kişinin
    # eşzamanlı ikinci onayı hükmü ilk onayın commit'inden sonra okur ve satır 3/5'e düşer.
    employee_id = allocate_employee_number(session)
    profile = review_pending_profile(session, key, entry=entry, fields=fields)
    if fields is None and profile.latin_missing:
        raise ProfileFieldsError(dict.fromkeys(_REQUIRED_NAMES, LATIN_MISSING_PROBLEM))
    confirmed = profile.fields() if fields is None else fields
    edited = edited_profile_fields(profile, confirmed)
    aliases = _employee_aliases(profile, confirmed)
    folder_name = employee_folder_name(confirmed.given_names, confirmed.surname, employee_id)
    employee = Employee(
        id=employee_id,
        folder_name=folder_name,
        given_names=confirmed.given_names,
        surname=confirmed.surname,
        other_names=confirmed.other_names,
        original_script_name=confirmed.original_script_name,
        date_of_birth=confirmed.date_of_birth,
        nationality=confirmed.nationality,
    )
    session.add(employee)
    for raw_name, normalized in aliases.items():
        session.add(
            EmployeeAlias(
                employee=employee,
                raw_name=raw_name,
                normalized_name=normalized,
                script=detect_script(raw_name),
            )
        )
    session.flush()
    layout.ensure_employee_tree(folder_name)
    data: dict[str, object] = {
        "action": EmployeeAction.PENDING.value,
        "document_type_slug": entry.slug,
    }
    if edited:
        data["edited_fields"] = list(edited)
    record_event(
        session,
        EventType.EMPLOYEE_CREATED,
        file_id=file_id,
        page_index=page_index,
        employee_id=employee_id,
        actor=actor,
        data=data,
    )
    return employee


def _employee_aliases(profile: ProposedProfile, fields: ProfileFields) -> dict[str, str]:
    # Çalışana yazılacak yazımlar (ham → normalize anahtar): önce belgeninkiler (anahtarı sayfanın
    # diliyle normalize edildi), sonra belgede olmayan onaylanmış ad-soyad ve orijinal yazım
    # (§20.2.1).
    aliases = dict(profile.aliases)
    name = f"{fields.given_names} {fields.surname}"
    # Latin yazımı belgede olmayan önerinin (05.2.2) ad-soyadı onaydan önce boştur.
    if fields.given_names and fields.surname and name not in aliases:
        aliases[name] = normalize_name(fields.given_names, fields.surname)
    original = fields.original_script_name
    if original is not None and original not in aliases:
        aliases[original] = normalize_name(original)
    return aliases


def _approval_refused(verdict: str) -> ProfileApprovalRefusedError:
    return ProfileApprovalRefusedError(
        f"Onay bekleyen profil onaylanmaz (§20.2.2 satır 7, K7): {verdict}."
    )


# --- alias ve numara birikimi (05.7.2) -------------------------------------------------------


class IdentityAccumulationRefusedError(ValueError):
    """`accumulate_identity` §20.2.2 satır 1 ya da 3'e uymayan anahtarla çağrıldı; hiçbir şey
    yazılmadı. Mesaj yalnız hükmü taşır, kişisel değer taşımaz."""


@dataclass(frozen=True, slots=True)
class IdentityAccumulation:
    """Eşleşen çalışana eklenenler (05.7.2): `aliases` yeni ham isim yazımları, `identifiers` yeni
    belge numaralarının §20.2.1 normalize değerleri; yeni bir şey yoksa boştur."""

    employee_id: str
    aliases: tuple[str, ...] = ()
    identifiers: tuple[str, ...] = ()


def accumulate_identity(
    session: Session, key: PersonKey, *, entry: CatalogEntry
) -> IdentityAccumulation:
    """§20.2.2 satır 1 ve 3'teki eşleşmede belgedeki yeni isim yazımını `employee_aliases`'a, yeni
    belge numarasını `employee_identifiers`'a ekler (05.7.2).

    Hüküm veritabanında olaysız yeniden değerlendirilir: satır 1 ya da 3 uymuyorsa (satır 5a'nın
    isim eşleşmesi dahil, 05.5.4) `IdentityAccumulationRefusedError` — hiçbir şey yazılmaz.
    Uyuyorsa eşleşen çalışana:

    - `employee_aliases`: `Ad Soyad` yazımı ve orijinal yazım, anahtarın normalize değeriyle —
      çalışanda aynı ham yazım (`raw_name`) yoksa; `script` yazımın alfabesidir (`detect_script`,
      05.8.3),
    - `employee_identifiers`: numara yalnız §20.2.3'e göre temizse (`clean_document_number`),
      çalışanda aynı değer yoksa; `kind` türün slug'ı, `source_document_id` boş (D11).

    İK'nın kaldırdığı kayıt (10.5.8) da bilinir: aynı ham yazım ya da numara geri açılmaz, yeni
    satır da açılmaz; kaldırılmış kaydın `seen_after_removal_at`'i dolar (profil uyarısı, PLAN.md
    §D68). Ham yazımı farklı ama normalize anahtarı kaldırılmış bir yazımınkiyle aynı olan yazım da
    eklenmez — etkin bir yazım o anahtarı zaten taşımıyorsa; yoksa kaldırılan isim başka harf
    büyüklüğüyle eşleştirmeye geri dönerdi (S12).

    `entry` adayın katalog türüdür. Tekrar çağrı bir şey eklemez. Olay yazılmaz (§8.3'te tür yok,
    D11); oturum commit edilmez.
    """
    match = _decide(session, key)
    # Satır 5a'nın eşleşmesi kimlik biriktirmez (05.5.4): yanlış isim eşleşmesi yayılmasın.
    employee_id = None if match.matched_by is MatchedBy.NAME else match.employee_id
    if employee_id is None:
        raise IdentityAccumulationRefusedError(
            "İsim yazımı ve belge numarası eklenmez (§20.2.2 satır 1, 3): "
            f"eşleştirme hükmü {match.rule.value}."
        )
    employee = session.get_one(Employee, employee_id)
    # Bilinen kayıtlar veritabanından okunur (autoflush): yüklü ilişki koleksiyonu bayat olabilir.
    known_aliases = session.scalars(
        select(EmployeeAlias).where(EmployeeAlias.employee == employee)
    ).all()
    known_identifiers = session.scalars(
        select(EmployeeIdentifier).where(EmployeeIdentifier.employee == employee)
    ).all()
    by_raw_name = {alias.raw_name: alias for alias in known_aliases}
    active_keys = {alias.normalized_name for alias in known_aliases if alias.removed_at is None}
    seen_removed: list[EmployeeAlias | EmployeeIdentifier] = []
    aliases: list[tuple[str, str]] = []
    for raw_name, normalized in _spellings(key).items():
        known = by_raw_name.get(raw_name)
        if known is not None:
            seen_removed.append(known)
            continue
        removed_key = [
            alias
            for alias in known_aliases
            if alias.removed_at is not None and alias.normalized_name == normalized
        ]
        if removed_key and normalized not in active_keys:
            seen_removed.extend(removed_key)
            continue
        aliases.append((raw_name, normalized))
    for raw_name, normalized in aliases:
        session.add(
            EmployeeAlias(
                employee=employee,
                raw_name=raw_name,
                normalized_name=normalized,
                script=detect_script(raw_name),
            )
        )
    number = clean_document_number(key, entry)
    same_number = [each for each in known_identifiers if each.value == number]
    identifiers = () if number is None or same_number else (number,)
    for value in identifiers:
        session.add(EmployeeIdentifier(employee=employee, kind=entry.slug, value=value))
    if all(each.removed_at is not None for each in same_number):
        seen_removed.extend(same_number)
    note_seen_after_removal(seen_removed)
    session.flush()
    return IdentityAccumulation(
        employee_id, tuple(raw_name for raw_name, _ in aliases), identifiers
    )
