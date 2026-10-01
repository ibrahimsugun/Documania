"""10.1.6 — ülke başvuru verisi ve bayrak simgeleri (tm 142, PLAN.md §D77, §D80).

Veri depodaki CLDR dosyalarından ve flag-icons SVG'lerinden gelir; testler ağ kullanmaz.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest
from markupsafe import Markup

import app.countries as countries_module
from app.countries import (
    MRZ_COUNTRY_CODES,
    NON_COUNTRY_CODES,
    Country,
    countries,
    country_badge,
    lookup,
    non_country_label,
    normalize_code,
)
from app.web.templating import templates

ROOT = Path(__file__).resolve().parents[2]
COUNTRIES_DIR = ROOT / "app" / "countries"
FLAGS_DIR = ROOT / "app" / "web" / "static" / "flags"

RU_BADGE = (
    '<span class="country"><img src="/static/flags/ru.svg" alt="" width="20" height="15" '
    'loading="lazy"> Rusya</span>'
)


@pytest.fixture
def fresh_tables() -> Iterator[None]:
    """Tabloyu taklit edilen koşulla yeniden kurar, sonra gerçek veriye döner."""
    countries_module._tables.cache_clear()
    yield
    countries_module._tables.cache_clear()


# --- veri bütünlüğü -------------------------------------------------------------------------


def test_table_holds_every_iso_country_and_kosovo() -> None:
    table = countries()
    alpha2 = [country.alpha2 for country in table]

    # ISO 3166-1'in 249 ülke kodu + Kosova.
    assert len(table) == 250
    assert alpha2 == sorted(alpha2)
    assert len(set(alpha2)) == len(alpha2)
    assert len({country.alpha3 for country in table}) == len(table)
    assert "XK" in alpha2


@pytest.mark.parametrize("country", countries(), ids=lambda country: country.alpha2)
def test_every_country_has_codes_name_and_flag(country: Country) -> None:
    assert re.fullmatch(r"[A-Z]{2}", country.alpha2)
    assert re.fullmatch(r"[A-Z]{3}", country.alpha3)
    assert country.name_tr.strip() == country.name_tr != ""
    assert country.flag_url == f"/static/flags/{country.alpha2.lower()}.svg"
    assert (FLAGS_DIR / f"{country.alpha2.lower()}.svg").is_file()


@pytest.mark.parametrize(
    ("alpha2", "alpha3", "name"),
    [
        ("TR", "TUR", "Türkiye"),
        ("RU", "RUS", "Rusya"),
        ("RS", "SRB", "Sırbistan"),
        ("DE", "DEU", "Almanya"),
        ("GB", "GBR", "Birleşik Krallık"),
        ("XK", "XKK", "Kosova"),
        ("CI", "CIV", "Côte d’Ivoire"),
    ],
)
def test_known_countries(alpha2: str, alpha3: str, name: str) -> None:
    country = lookup(alpha2)

    assert country is not None
    assert (country.alpha2, country.alpha3, country.name_tr) == (alpha2, alpha3, name)


@pytest.mark.parametrize("code", ["EU", "UN", "ZZ", "QO", "XA", "XB", "AC", "IC", "EA", "EZ"])
def test_regions_groups_and_reserved_codes_are_not_countries(code: str) -> None:
    # CLDR'de adı olan ama ISO'da ülke olarak atanmamış kodlar (birlik, BM, kullanıcı kodu,
    # ayrılmış bölge) ülke tablosuna girmez.
    assert lookup(code) is None
    assert code not in {country.alpha2 for country in countries()}


def test_mrz_exceptions_resolve_to_countries_and_do_not_shadow_iso_codes() -> None:
    alpha3 = {country.alpha3 for country in countries()}

    for code, alpha2 in MRZ_COUNTRY_CODES.items():
        country = lookup(code)
        assert country is not None and country.alpha2 == alpha2, code
        assert code not in alpha3, code


def test_non_country_codes_are_not_countries() -> None:
    alpha3 = {country.alpha3 for country in countries()}

    assert set(NON_COUNTRY_CODES) == {
        "UNO", "UNA", "UNK", "XXA", "XXB", "XXC", "XXX",
        "XOM", "XPO", "XES", "XMP", "XCC", "XBA", "XIM",
    }  # fmt: skip
    for code, label in NON_COUNTRY_CODES.items():
        assert lookup(code) is None, code
        assert code not in alpha3 and code not in MRZ_COUNTRY_CODES, code
        assert label.strip() == label != "", code


def test_sources_and_licenses_are_in_the_repository() -> None:
    sources = (COUNTRIES_DIR / "SOURCES.md").read_text(encoding="utf-8")

    assert "2026-09-30" in sources
    assert (COUNTRIES_DIR / "data" / "LICENSE-CLDR").is_file()
    assert (FLAGS_DIR / "LICENSE").is_file()
    assert "MIT" in (FLAGS_DIR / "LICENSE").read_text(encoding="utf-8")
    for name in ("cldr-tr-territories.json", "cldr-codeMappings.json"):
        digest = hashlib.sha256((COUNTRIES_DIR / "data" / name).read_bytes()).hexdigest()
        # Dosya indirildiği gibi durur: özet kaynak kaydındakiyle aynıdır.
        assert f"`{name}`" in sources
        assert digest in sources, name


def test_flag_files_are_plain_svg_without_scripts() -> None:
    svgs = sorted(FLAGS_DIR.glob("*.svg"))

    assert len(svgs) == 257
    for path in svgs:
        assert re.fullmatch(r"[a-z]{2}\.svg", path.name), path.name
        text = path.read_text(encoding="utf-8")
        assert text.lstrip().startswith("<svg"), path.name
        assert "<script" not in text.lower(), path.name
        assert not re.search(r"\son\w+\s*=", text, re.IGNORECASE), path.name
        assert "http" not in text.replace("http://www.w3.org/", ""), path.name


def test_data_and_flags_ship_as_package_data() -> None:
    package_data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "setuptools"
    ]["package-data"]

    def shipped(package: str) -> set[Path]:
        base = ROOT / Path(*package.split("."))
        return {path for pattern in package_data[package] for path in base.glob(pattern)}

    web, countries_data = shipped("app.web"), shipped("app.countries")
    assert set(FLAGS_DIR.iterdir()) <= web
    assert set((COUNTRIES_DIR / "data").iterdir()) <= countries_data
    assert COUNTRIES_DIR / "SOURCES.md" in countries_data


# --- kod çözme ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("RU", "RU"),
        ("rus", "RUS"),
        (" r u s ", "RUS"),
        ("D<<", "D"),
        ("\tgbd\n", "GBD"),
        ("", None),
        ("<<<", None),
        ("RUSS", None),
        ("R1", None),
        ("Ру", None),
        (None, None),
        (643, None),
    ],
)
def test_normalize_code(code: object, expected: str | None) -> None:
    assert normalize_code(code) == expected


@pytest.mark.parametrize(
    ("code", "alpha2"),
    [
        ("RU", "RU"),
        ("RUS", "RU"),
        ("rus", "RU"),
        (" Ru ", "RU"),
        ("D", "DE"),
        ("d<<", "DE"),
        ("DEU", "DE"),
        ("GBD", "GB"),
        ("GBN", "GB"),
        ("GBO", "GB"),
        ("GBP", "GB"),
        ("gbs", "GB"),
        ("GBR", "GB"),
        ("RKS", "XK"),
        ("XKK", "XK"),
        ("XK", "XK"),
        ("TUR", "TR"),
        ("SRB", "RS"),
    ],
)
def test_lookup_accepts_alpha2_alpha3_and_mrz(code: str, alpha2: str) -> None:
    country = lookup(code)

    assert country is not None
    assert country.alpha2 == alpha2


@pytest.mark.parametrize("code", ["XXA", "UNO", "ZZZ", "QQQ", "UK", "<<<", "", None, 7])
def test_lookup_returns_none_for_non_countries_and_unknown_codes(code: object) -> None:
    assert lookup(code) is None


def test_non_country_label() -> None:
    assert non_country_label("XXA") == "Vatansız"
    assert non_country_label(" xxb ") == "Mülteci, 1951 Sözleşmesi"
    assert non_country_label("UNO") == "Birleşmiş Milletler"
    assert non_country_label("RUS") is None
    assert non_country_label("ZZZ") is None
    assert non_country_label(None) is None


# --- panel gösterimi ------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["RU", "RUS", "rus"])
def test_badge_shows_flag_and_turkish_name(code: str) -> None:
    badge = country_badge(code)

    assert isinstance(badge, Markup)
    assert str(badge) == RU_BADGE


def test_badge_resolves_mrz_codes() -> None:
    assert "/static/flags/de.svg" in country_badge("D") and "Almanya" in country_badge("D")
    assert "/static/flags/gb.svg" in country_badge("GBD")
    assert "/static/flags/xk.svg" in country_badge("RKS")


def test_badge_for_non_country_has_code_and_label_but_no_flag() -> None:
    assert str(country_badge("xxa")) == '<span class="country">XXA (Vatansız)</span>'
    assert "<img" not in country_badge("UNO")


def test_badge_for_unknown_code_shows_only_the_escaped_code() -> None:
    assert str(country_badge("ZZZ")) == '<span class="country">ZZZ</span>'
    assert str(country_badge(" <b>x</b> ")) == '<span class="country">&lt;b&gt;x&lt;/b&gt;</span>'
    assert "<img" not in country_badge("EU")


@pytest.mark.parametrize("value", [None, "", "   ", 643])
def test_badge_for_missing_value_is_empty(value: object) -> None:
    assert country_badge(value) == Markup("")


def test_badge_escapes_the_country_name(
    fresh_tables: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = countries_module._read_json

    def read_json(name: str) -> dict:
        data = real(name)
        if name == countries_module.TERRITORIES_RESOURCE:
            data["main"]["tr"]["localeDisplayNames"]["territories"]["RU"] = "R<u>&"
        return data

    monkeypatch.setattr(countries_module, "_read_json", read_json)

    assert "> R&lt;u&gt;&amp;</span>" in str(country_badge("RU"))

    # Bayraksız gösterimde de ad kaçışlanır.
    monkeypatch.setattr(countries_module, "_flag_exists", lambda alpha2: False)
    countries_module._tables.cache_clear()
    assert str(country_badge("RU")) == '<span class="country">R&lt;u&gt;&amp;</span>'


def test_missing_flag_file_still_shows_the_name(
    fresh_tables: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(countries_module, "_flag_exists", lambda alpha2: alpha2 != "RU")

    assert lookup("RUS") == Country("RU", "RUS", "Rusya", None)
    assert str(country_badge("RUS")) == '<span class="country">Rusya</span>'
    assert "<img" in country_badge("TUR")


def test_badge_is_a_panel_template_global() -> None:
    page = templates.env.from_string("<td>{{ country_badge(code) }}</td>")

    assert page.render(code="RUS") == f"<td>{RU_BADGE}</td>"
    assert page.render(code=None) == "<td></td>"
    assert page.render(code="<i>") == '<td><span class="country">&lt;i&gt;</span></td>'


def test_stylesheet_aligns_the_flag() -> None:
    css = (ROOT / "app" / "web" / "static" / "panel.css").read_text(encoding="utf-8")

    assert re.search(r"\.country\s*\{[^}]*align-items:\s*center", css)
    assert re.search(r"\.country img\s*\{[^}]*height:\s*15px", css)
