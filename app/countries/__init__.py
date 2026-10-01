"""Ülke başvuru verisi ve bayrak simgeleri (PRD 10.1.6, tm 142; PLAN.md §D77, §D80).

Veri depodadır, çalışma zamanında ağdan bir şey çekilmez (kaynaklar `SOURCES.md`):

- **Ülke tablosu** Unicode CLDR dosyalarından okunur: `data/cldr-tr-territories.json` (alfa-2 →
  Türkçe ad) ve `data/cldr-codeMappings.json` (alfa-2 → `_alpha3`, `_numeric`). Ülke sayılan
  yalnız ISO 3166-1 kodudur: CLDR'de **900'den küçük** sayısal kodu olan iki harfli bölge. Kıta
  ve bölge kodları (`150`), ISO'nun kullanıcıya bıraktığı kodlar (`QO`, `XA`, `ZZ`) ve ISO'da
  ülke olarak atanmamış ayrılmış kodlar (`EU`, `UN`, `AC`, `IC` …) böylece dışarıda kalır.
  Tek istisna Kosova'dır (`XK`, alfa-3 `XKK`): ISO'da kullanıcı koduyla durur ama pasaportlarda
  uyruk olarak geçer.
- **MRZ uyruk kodları** ISO alfa-3'ten yalnız şu noktalarda ayrılır (ICAO Doc 9303 Part 3) ve
  elle tutulur: Almanya `D`, Birleşik Krallık'ın beş vatandaşlık türü (`GBD` … `GBS`), Kosova
  `RKS`. Ülke olmayan kodlar (vatansız, mülteci, BM ve uluslararası kuruluş belgeleri) bayraksız,
  kodun kendisi ve açıklamasıyla gösterilir.
- **Bayraklar** `app/web/static/flags/<alfa2>.svg` (flag-icons). Dosyası olmayan ülkenin adı yine
  yazılır, kırık görüntü çıkmaz.

Panel bu modüle tek yerden bağlanır: `country_badge` Jinja globalidir (`app/web/templating.py`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from importlib import resources

from markupsafe import Markup

FLAG_URL_PREFIX = "/static/flags/"
FLAG_WIDTH = 20
FLAG_HEIGHT = 15

TERRITORIES_RESOURCE = "cldr-tr-territories.json"
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


@cache
def _tables() -> tuple[dict[str, Country], dict[str, Country]]:
    """(alfa-2 → ülke, alfa-3 → ülke); paket verisinden bir kez kurulur."""
    names = _read_json(TERRITORIES_RESOURCE)["main"]["tr"]["localeDisplayNames"]["territories"]
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
        country = Country(alpha2=alpha2, alpha3=alpha3, name_tr=name, flag_url=flag_url)
        by_alpha2[alpha2] = country
        by_alpha3[alpha3] = country
    return by_alpha2, by_alpha3


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


def non_country_label(code: object) -> str | None:
    """Ülke olmayan MRZ kodunun açıklaması (`XXA` → "Vatansız"); öteki her kodda `None`."""
    normalized = normalize_code(code)
    return NON_COUNTRY_CODES.get(normalized) if normalized is not None else None


def country_badge(code: object) -> Markup:
    """Panelde ülke gösterimi: bayrak + Türkçe ad.

    Bayrağın `alt`'ı boştur, çünkü ad yanında metin olarak yazar. Bayrak dosyası yoksa yalnız ad,
    ülke olmayan kodda kod ve açıklaması, tanınmayan kodda kodun kendisi yazılır (görüntü yok).
    Boş ya da eksik değer boş çıktı verir.
    """
    if not isinstance(code, str) or not code.strip():
        return Markup("")
    country = lookup(code)
    if country is None:
        label = non_country_label(code)
        text = code.strip() if label is None else f"{normalize_code(code)} ({label})"
        return Markup('<span class="country">{}</span>').format(text)
    if country.flag_url is None:
        return Markup('<span class="country">{}</span>').format(country.name_tr)
    return Markup(
        '<span class="country"><img src="{}" alt="" width="{}" height="{}" loading="lazy"> {}'
        "</span>"
    ).format(country.flag_url, FLAG_WIDTH, FLAG_HEIGHT, country.name_tr)


__all__ = [
    "Country",
    "countries",
    "country_badge",
    "lookup",
    "non_country_label",
    "normalize_code",
]
