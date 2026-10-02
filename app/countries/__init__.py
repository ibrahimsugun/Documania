"""Ülke başvuru verisi ve bayrak simgeleri (PRD 10.1.6, 10.10.5; tm 142, 157; PLAN.md §D77, §D80,
§D92 i).

Veri depodadır, çalışma zamanında ağdan bir şey çekilmez (kaynaklar `SOURCES.md`):

- **Ülke tablosu** Unicode CLDR dosyalarından okunur: `data/cldr-tr-territories.json` (alfa-2 →
  Türkçe ad) ve `data/cldr-codeMappings.json` (alfa-2 → `_alpha3`, `_numeric`). Ülke kümesini
  Türkçe dosya belirler; İngilizce ve Sırpça (Latin) adlar `data/cldr-en-territories.json` ve
  `data/cldr-sr-Latn-territories.json`'dan aynı alfa-2 koduyla okunur. Ülke sayılan
  yalnız ISO 3166-1 kodudur: CLDR'de **900'den küçük** sayısal kodu olan iki harfli bölge. Kıta
  ve bölge kodları (`150`), ISO'nun kullanıcıya bıraktığı kodlar (`QO`, `XA`, `ZZ`) ve ISO'da
  ülke olarak atanmamış ayrılmış kodlar (`EU`, `UN`, `AC`, `IC` …) böylece dışarıda kalır.
  Tek istisna Kosova'dır (`XK`, alfa-3 `XKK`): ISO'da kullanıcı koduyla durur ama pasaportlarda
  uyruk olarak geçer.
- **MRZ uyruk kodları** ISO alfa-3'ten yalnız şu noktalarda ayrılır (ICAO Doc 9303 Part 3) ve
  elle tutulur: Almanya `D`, Birleşik Krallık'ın beş vatandaşlık türü (`GBD` … `GBS`), Kosova
  `RKS`. Ülke olmayan kodlar (vatansız, mülteci, BM ve uluslararası kuruluş belgeleri) bayraksız,
  kodun kendisi ve açıklamasıyla gösterilir; açıklama üç dilde elle tutulur.
- **Bayraklar** `app/web/static/flags/<alfa2>.svg` (flag-icons). Dosyası olmayan ülkenin adı yine
  yazılır, kırık görüntü çıkmaz.

Panel bu modüle tek yerden bağlanır: `country_badge` ve profildeki uyruk için `nationality_badge`
Jinja globalidir (`app/web/templating.py`). Gösterim dili verilmezse isteğin dilidir
(`app.i18n.current_language`); ülke süzgeci adları o dilin harf sırasıyla dizer (`sort_key`).
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from types import MappingProxyType

from markupsafe import Markup

from app.i18n import SOURCE_LANGUAGE, SUPPORTED_LANGUAGES, current_language

FLAG_URL_PREFIX = "/static/flags/"
FLAG_WIDTH = 20
FLAG_HEIGHT = 15

TERRITORIES_RESOURCE = "cldr-tr-territories.json"
# Arayüz dili → (CLDR ad dosyası, dosyadaki yerel ayar anahtarı). Türkçe dosya ülke kümesini de
# belirler (`TERRITORIES_RESOURCE`); Sırpça Latin alfabesiyledir (§D92 a).
TERRITORY_RESOURCES: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        "en": ("cldr-en-territories.json", "en"),
        "tr": (TERRITORIES_RESOURCE, "tr"),
        "sr": ("cldr-sr-Latn-territories.json", "sr-Latn"),
    }
)
CODE_MAPPINGS_RESOURCE = "cldr-codeMappings.json"

# ISO 3166-1 sayısal kodlarında 900–999 kullanıcıya bırakılmıştır; CLDR `EU`, `QO`, `XA`, `ZZ`
# gibi ülke olmayan kodlara bu aralıktan numara verir.
ISO_NUMERIC_USER_ASSIGNED = 900

# ISO'da ülke olarak atanmamış ama uyruk olarak geçen bölge: Kosova.
EXTRA_COUNTRIES = frozenset({"XK"})

# ICAO Doc 9303 Part 3: ISO alfa-3'ten ayrılan MRZ uyruk kodları → alfa-2.
MRZ_COUNTRY_CODES: dict[str, str] = {
    "D": "DE",  # Almanya
    "GBD": "GB",  # British Overseas Territories Citizen
    "GBN": "GB",  # British National (Overseas)
    "GBO": "GB",  # British Overseas Citizen
    "GBP": "GB",  # British Protected Person
    "GBS": "GB",  # British Subject
    "RKS": "XK",  # Kosova (CLDR alfa-3'ü `XKK`)
}

# ICAO Doc 9303 Part 3: ülke olmayan MRZ kodları — bayrak yok, kod açıklamasıyla gösterilir.
NON_COUNTRY_CODES: dict[str, str] = {
    "UNO": "Birleşmiş Milletler",
    "UNA": "BM uzman kuruluşu",
    "UNK": "UNMIK, Kosova sakini",
    "XXA": "Vatansız",
    "XXB": "Mülteci, 1951 Sözleşmesi",
    "XXC": "Mülteci, diğer",
    "XXX": "Uyruğu belirtilmemiş",
    "XOM": "Malta Egemen Askerî Tarikatı",
    "XPO": "Interpol",
    "XES": "Doğu Karayip Devletleri Örgütü",
    "XMP": "Akdeniz Parlamenter Asamblesi",
    "XCC": "Karayip Topluluğu",
    "XBA": "Afrika Kalkınma Bankası",
    "XIM": "Afrika İhracat-İthalat Bankası",
}
NON_COUNTRY_CODES_EN: dict[str, str] = {
    "UNO": "United Nations",
    "UNA": "UN specialized agency",
    "UNK": "UNMIK, resident of Kosovo",
    "XXA": "Stateless",
    "XXB": "Refugee, 1951 Convention",
    "XXC": "Refugee, other",
    "XXX": "Unspecified nationality",
    "XOM": "Sovereign Military Order of Malta",
    "XPO": "Interpol",
    "XES": "Organisation of Eastern Caribbean States",
    "XMP": "Parliamentary Assembly of the Mediterranean",
    "XCC": "Caribbean Community",
    "XBA": "African Development Bank",
    "XIM": "African Export-Import Bank",
}
NON_COUNTRY_CODES_SR: dict[str, str] = {
    "UNO": "Ujedinjene nacije",
    "UNA": "Specijalizovana agencija UN",
    "UNK": "UNMIK, stanovnik Kosova",
    "XXA": "Lice bez državljanstva",
    "XXB": "Izbeglica, Konvencija iz 1951.",
    "XXC": "Izbeglica, ostalo",
    "XXX": "Nenavedeno državljanstvo",
    "XOM": "Suvereni malteški viteški red",
    "XPO": "Interpol",
    "XES": "Organizacija istočnokaripskih država",
    "XMP": "Parlamentarna skupština Mediterana",
    "XCC": "Karipska zajednica",
    "XBA": "Afrička razvojna banka",
    "XIM": "Afrička izvozno-uvozna banka",
}
NON_COUNTRY_CODES_BY_LANGUAGE: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {"en": NON_COUNTRY_CODES_EN, "tr": NON_COUNTRY_CODES, "sr": NON_COUNTRY_CODES_SR}
)

# Ülke süzgecinin harf sırası (PRD 11.1.7; §D92 i). Dilde olmayan Latin harfleri (`q`, `w`, `x`,
# `y`) Latin alfabesindeki yerlerine konur. Sırpça Latin alfabesinde `dž`, `lj`, `nj` tek harftir.
TURKISH_ALPHABET = "abcçdefgğhıijklmnoöpqrsştuüvwxyz"
ENGLISH_ALPHABET = "abcdefghijklmnopqrstuvwxyz"
SERBIAN_ALPHABET: tuple[str, ...] = (
    *"abcčćd",
    "dž",
    *"đefghijkl",
    "lj",
    *"mn",
    "nj",
    *"opqrsštuvwxyzž",
)
ALPHABETS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {"en": tuple(ENGLISH_ALPHABET), "tr": tuple(TURKISH_ALPHABET), "sr": SERBIAN_ALPHABET}
)
_RANKS: Mapping[str, Mapping[str, int]] = MappingProxyType(
    {
        language: {letter: rank for rank, letter in enumerate(alphabet, start=1)}
        for language, alphabet in ALPHABETS.items()
    }
)


def _letter_pattern(alphabet: tuple[str, ...]) -> re.Pattern[str]:
    """Metni alfabenin harflerine bölen desen: önce çok karakterli harfler (`dž`), sonra tek
    karakter."""
    digraphs = [re.escape(letter) for letter in alphabet if len(letter) > 1]
    return re.compile("|".join([*digraphs, "."]), re.DOTALL)


_LETTERS: Mapping[str, re.Pattern[str]] = MappingProxyType(
    {language: _letter_pattern(alphabet) for language, alphabet in ALPHABETS.items()}
)
# NFD ile ayrışmayan işaretli harfler: dilin alfabesinde yoksa işaretsiz hâlinin yerini alır.
_UNDECOMPOSED = {"đ": "d", "ı": "i", "ł": "l", "ø": "o"}

_CODE = re.compile(r"[A-Z]{1,3}")
_SPACE = re.compile(r"\s+")
_ALPHA2 = re.compile(r"[A-Z]{2}")


@dataclass(frozen=True, slots=True)
class Country:
    alpha2: str
    alpha3: str
    name_tr: str
    flag_url: str | None
    """`/static/flags/<alfa2>.svg`; bayrak dosyası pakette yoksa `None`."""
    names: Mapping[str, str] = field(default_factory=dict, compare=False, repr=False)
    """Arayüz dili → CLDR adı (`en`, `tr`, `sr`)."""

    def name(self, language: str | None = None) -> str:
        """Ülkenin `language` dilindeki adı (verilmezse isteğin dili); o dilde ad yoksa Türkçe
        ad."""
        return self.names.get(language or current_language()) or self.name_tr


def normalize_code(code: object) -> str | None:
    """Kodu karşılaştırılabilir biçime getirir: boşluklar ve MRZ dolgu karakteri (`<`) atılır,
    harfler büyütülür. Bir–üç Latin harfi dışındaki her şey `None` döner."""
    if not isinstance(code, str):
        return None
    normalized = _SPACE.sub("", code).strip("<").upper()
    return normalized if _CODE.fullmatch(normalized) else None


def _read_json(name: str) -> dict:
    return json.loads(
        resources.files(__package__).joinpath("data", name).read_text(encoding="utf-8")
    )


def _flag_exists(alpha2: str) -> bool:
    return resources.files("app.web").joinpath("static", "flags", f"{alpha2.lower()}.svg").is_file()


def _territory_names(language: str) -> dict[str, str]:
    """Dilin CLDR bölge adları (alfa-2/bölge kodu → ad)."""
    resource, locale = TERRITORY_RESOURCES[language]
    return _read_json(resource)["main"][locale]["localeDisplayNames"]["territories"]


@cache
def _tables() -> tuple[dict[str, Country], dict[str, Country]]:
    """(alfa-2 → ülke, alfa-3 → ülke); paket verisinden bir kez kurulur."""
    names = _territory_names(SOURCE_LANGUAGE)
    localized = {language: _territory_names(language) for language in TERRITORY_RESOURCES}
    mappings = _read_json(CODE_MAPPINGS_RESOURCE)["supplemental"]["codeMappings"]
    by_alpha2: dict[str, Country] = {}
    by_alpha3: dict[str, Country] = {}
    for alpha2, name in names.items():
        if not _ALPHA2.fullmatch(alpha2):
            continue  # kıta/bölge kodları (`150`) ve ad varyantları (`GB-alt-short`)
        mapping = mappings.get(alpha2, {})
        numeric = mapping.get("_numeric")
        is_iso_country = numeric is not None and int(numeric) < ISO_NUMERIC_USER_ASSIGNED
        if not is_iso_country and alpha2 not in EXTRA_COUNTRIES:
            continue
        alpha3 = mapping["_alpha3"]
        flag_url = f"{FLAG_URL_PREFIX}{alpha2.lower()}.svg" if _flag_exists(alpha2) else None
        country_names = MappingProxyType(
            {
                language: table.get(alpha2) or name
                for language, table in localized.items()
                if language != SOURCE_LANGUAGE
            }
            | {SOURCE_LANGUAGE: name}
        )
        country = Country(
            alpha2=alpha2, alpha3=alpha3, name_tr=name, flag_url=flag_url, names=country_names
        )
        by_alpha2[alpha2] = country
        by_alpha3[alpha3] = country
    return by_alpha2, by_alpha3


def _rank(letter: str, ranks: Mapping[str, int]) -> int:
    """Harfin alfabedeki sırası; alfabede olmayan işaretli harf (`å`, `ô`, İngilizcede `ç`)
    işaretsiz hâlinin yerini alır, harf olmayan karakter (boşluk, tire, ayraç) `0` olup harflerden
    önce gelir."""
    rank = ranks.get(letter)
    if rank is None:
        base = _UNDECOMPOSED.get(letter) or unicodedata.normalize("NFD", letter)[0]
        rank = ranks.get(base, 0)
    return rank


def sort_key(text: str, language: str | None = None) -> tuple[tuple[int, ...], str]:
    """Ada göre sıralama anahtarı, `language` dilinin harf sırasıyla (verilmezse isteğin dili):
    Türkçede `ç`, `ğ`, `ı`, `ö`, `ş`, `ü`, Sırpçada `č`, `ć`, `dž`, `đ`, `lj`, `nj`, `š`, `ž` kendi
    harflerinden sonra gelir. Türkçede büyük `I` küçük `ı`, `İ` küçük `i` sayılır. Eşit anahtarda
    metnin kendisi sırayı sabitler."""
    language = language or current_language()
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"desteklenmeyen dil: {language!r}")
    if language == "tr":
        text_lowered = text.replace("I", "ı").replace("İ", "i").lower()
    else:
        text_lowered = text.lower()
    ranks = _RANKS[language]
    letters = _LETTERS[language].findall(text_lowered)
    return tuple(_rank(letter, ranks) for letter in letters), text


def turkish_sort_key(text: str) -> tuple[tuple[int, ...], str]:
    """Türkçe ada göre sıralama anahtarı (`sort_key(text, "tr")`)."""
    return sort_key(text, "tr")


def countries() -> tuple[Country, ...]:
    """Bütün ülkeler, alfa-2 sırasıyla."""
    by_alpha2, _ = _tables()
    return tuple(by_alpha2[code] for code in sorted(by_alpha2))


def lookup(code: object) -> Country | None:
    """Alfa-2 (`RU`), alfa-3 (`RUS`) ya da MRZ uyruk kodundan (`D`, `GBD`, `RKS`) ülke.

    Harf büyüklüğü ve boşluk fark etmez. Ülke olmayan (`XXA`, `UNO`) ve tanınmayan kod `None`
    döner; ülke olmayan kodun açıklaması `non_country_label`'dadır.
    """
    normalized = normalize_code(code)
    if normalized is None:
        return None
    by_alpha2, by_alpha3 = _tables()
    if normalized in MRZ_COUNTRY_CODES:
        return by_alpha2.get(MRZ_COUNTRY_CODES[normalized])
    if len(normalized) == 2:
        return by_alpha2.get(normalized)
    return by_alpha3.get(normalized)


def non_country_label(code: object, language: str | None = None) -> str | None:
    """Ülke olmayan MRZ kodunun `language` dilindeki açıklaması (verilmezse isteğin dili; `XXA` →
    "Stateless" / "Vatansız" / "Lice bez državljanstva"); öteki her kodda `None`."""
    normalized = normalize_code(code)
    if normalized is None:
        return None
    labels = NON_COUNTRY_CODES_BY_LANGUAGE.get(language or current_language(), NON_COUNTRY_CODES)
    return labels.get(normalized)


def country_badge(code: object, language: str | None = None) -> Markup:
    """Panelde ülke gösterimi: bayrak + `language` dilindeki ad (verilmezse isteğin dili).

    Bayrağın `alt`'ı boştur, çünkü ad yanında metin olarak yazar. Bayrak dosyası yoksa yalnız ad,
    ülke olmayan kodda kod ve açıklaması, tanınmayan kodda kodun kendisi yazılır (görüntü yok).
    Boş ya da eksik değer boş çıktı verir.
    """
    if not isinstance(code, str) or not code.strip():
        return Markup("")
    country = lookup(code)
    if country is None:
        label = non_country_label(code, language)
        text = code.strip() if label is None else f"{normalize_code(code)} ({label})"
        return Markup('<span class="country">{}</span>').format(text)
    name = country.name(language)
    if country.flag_url is None:
        return Markup('<span class="country">{}</span>').format(name)
    return Markup(
        '<span class="country"><img src="{}" alt="" width="{}" height="{}" loading="lazy"> {}'
        "</span>"
    ).format(country.flag_url, FLAG_WIDTH, FLAG_HEIGHT, name)


def nationality_badge(code: object, language: str | None = None) -> Markup:
    """Profildeki "Vatandaşlık" gösterimi (PRD 10.5.11): bayrak + `language` dilindeki ad
    (verilmezse isteğin dili) + parantez içinde kod, örn. `RUS` → bayrak + "Russia (RUS)" /
    "Rusya (RUS)" / "Rusija (RUS)".

    Tanınmayan ya da ülke olmayan kodda (`XXA`, `UNO`) bayrak ve ad yoktur, yalnız değerin kendisi
    yazılır. Boş ya da eksik değer boş çıktı verir; "—" koymak şablonun işidir.
    """
    if not isinstance(code, str):
        return Markup("")
    if lookup(code) is None:
        return Markup.escape(code.strip())
    return Markup("{} ({})").format(country_badge(code, language), normalize_code(code))


__all__ = [
    "Country",
    "countries",
    "country_badge",
    "lookup",
    "nationality_badge",
    "non_country_label",
    "normalize_code",
    "sort_key",
    "turkish_sort_key",
]
