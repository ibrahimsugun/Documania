"""10.10.5 — ülke adları seçili dilde: İngilizce, Türkçe, Sırpça (Latin) CLDR adları, ülke olmayan
MRZ kodlarının üç dildeki açıklaması ve dilin harf sırası (PLAN.md §D92 i; tm 157).

Veri depodaki CLDR dosyalarından gelir; testler ağ kullanmaz. Türkçe gösterimin ayrıntısı
`test_countries.py`'dedir.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from markupsafe import Markup

from app.countries import (
    ALPHABETS,
    NON_COUNTRY_CODES,
    NON_COUNTRY_CODES_BY_LANGUAGE,
    TERRITORY_RESOURCES,
    countries,
    country_badge,
    lookup,
    nationality_badge,
    non_country_label,
    sort_key,
)
from app.i18n import SUPPORTED_LANGUAGES, use_language
from app.web.templating import templates

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "app" / "countries" / "data"
LANGUAGES = ("en", "sr", "tr")


def _flag(alpha2: str, name: str) -> str:
    return (
        f'<span class="country"><img src="/static/flags/{alpha2}.svg" alt="" width="20" '
        f'height="15" loading="lazy"> {name}</span>'
    )


# --- 1: gösterim -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "name"), [("en", "Russia"), ("sr", "Rusija"), ("tr", "Rusya")]
)
def test_nationality_shows_the_name_in_the_chosen_language(language: str, name: str) -> None:
    assert str(nationality_badge("RUS", language)) == f"{_flag('ru', name)} (RUS)"
    assert str(country_badge("RU", language)) == _flag("ru", name)


@pytest.mark.parametrize(
    ("language", "name"), [("en", "Germany"), ("sr", "Nemačka"), ("tr", "Almanya")]
)
def test_mrz_exception_shows_the_name_in_the_chosen_language(language: str, name: str) -> None:
    assert str(nationality_badge("D", language)) == f"{_flag('de', name)} (D)"


@pytest.mark.parametrize(
    ("language", "label"),
    [("en", "Stateless"), ("sr", "Lice bez državljanstva"), ("tr", "Vatansız")],
)
def test_stateless_has_no_flag_in_any_language(language: str, label: str) -> None:
    badge = str(country_badge("XXA", language))

    assert badge == f'<span class="country">XXA ({label})</span>'
    assert "<img" not in badge
    assert non_country_label("xxa", language) == label
    # Profildeki uyruk ülke olmayan kodda yalnız değerin kendisidir (PRD 10.5.11), her dilde.
    assert nationality_badge("XXA", language) == Markup("XXA")


def test_the_language_defaults_to_the_current_language() -> None:
    # İstek dışında varsayılan `en` (§D92 b); istekte (ya da `use_language` bloğunda) seçili dil.
    assert "Russia" in country_badge("RU")
    assert non_country_label("XXA") == "Stateless"
    with use_language("sr"):
        assert "Rusija" in country_badge("RU")
        assert str(nationality_badge("RUS")).endswith("Rusija</span> (RUS)")
        assert non_country_label("XXA") == "Lice bez državljanstva"
        assert lookup("RS").name() == "Srbija"
    with use_language("tr"):
        assert lookup("RS").name() == "Sırbistan"


@pytest.mark.parametrize(("language", "name"), [("en", "Serbia"), ("sr", "Srbija")])
def test_the_template_globals_use_the_request_language(language: str, name: str) -> None:
    page = templates.env.from_string("{{ country_badge(code) }}|{{ nationality_badge(code) }}")

    with use_language(language):
        assert page.render(code="RS") == f"{_flag('rs', name)}|{_flag('rs', name)} (RS)"


def test_the_name_is_escaped_in_every_language() -> None:
    country = lookup("RU")
    assert country is not None
    assert all("<" not in country.name(language) for language in LANGUAGES)
    assert "Russia" in Markup.escape(country.name("en"))


# --- 2: veri bütünlüğü ---------------------------------------------------------------------------


def test_every_country_has_its_own_cldr_name_in_every_language() -> None:
    table = countries()
    assert len(table) == 250
    for language, (resource, locale) in TERRITORY_RESOURCES.items():
        names = json.loads((DATA_DIR / resource).read_text(encoding="utf-8"))["main"][locale][
            "localeDisplayNames"
        ]["territories"]
        for country in table:
            name = country.name(language)
            assert name == names[country.alpha2], (language, country.alpha2)
            assert name.strip() == name != ""


def test_the_names_differ_between_languages_where_cldr_differs() -> None:
    serbia = lookup("RS")
    assert serbia is not None
    assert {language: serbia.name(language) for language in LANGUAGES} == {
        "en": "Serbia",
        "sr": "Srbija",
        "tr": "Sırbistan",
    }
    assert lookup("CZ").name("sr") == "Češka"
    assert lookup("TR").name("en") == "Türkiye"
    assert lookup("TR").name("sr") == "Turska"


def test_non_country_codes_are_described_in_every_language() -> None:
    assert set(NON_COUNTRY_CODES_BY_LANGUAGE) == set(SUPPORTED_LANGUAGES)
    assert NON_COUNTRY_CODES_BY_LANGUAGE["tr"] is NON_COUNTRY_CODES
    for language, labels in NON_COUNTRY_CODES_BY_LANGUAGE.items():
        assert set(labels) == set(NON_COUNTRY_CODES), language
        assert all(label.strip() == label != "" for label in labels.values()), language
        assert all(lookup(code) is None for code in labels)
    turkish_letters = set("çğıİöşüÇĞÖŞÜ")
    assert not any(
        turkish_letters & set(label) for label in NON_COUNTRY_CODES_BY_LANGUAGE["en"].values()
    )
    assert NON_COUNTRY_CODES_BY_LANGUAGE["en"]["UNO"] == "United Nations"
    assert NON_COUNTRY_CODES_BY_LANGUAGE["sr"]["UNO"] == "Ujedinjene nacije"


def test_sources_record_the_english_and_serbian_files() -> None:
    sources = (ROOT / "app" / "countries" / "SOURCES.md").read_text(encoding="utf-8")

    assert "2026-10-02" in sources
    assert "CLDR 48.2.0" in sources
    for name in ("cldr-en-territories.json", "cldr-sr-Latn-territories.json"):
        digest = hashlib.sha256((DATA_DIR / name).read_bytes()).hexdigest()
        # Dosya indirildiği gibi durur: özet kaynak kaydındakiyle aynıdır.
        assert f"`{name}`" in sources
        assert digest in sources, name


# --- 3: dilin harf sırası ----------------------------------------------------------------------


def _sorted(names: list[str], language: str) -> list[str]:
    return sorted(names, key=lambda name: sort_key(name, language))


def test_serbian_letters_come_after_their_base_letters() -> None:
    names = ["Žuta", "Zambija", "Đibuti", "Džibuti", "Dominika", "Ćirilica", "Čad", "Crna Gora"]
    names += ["Švedska", "Srbija", "Ljubljana", "Luksemburg", "Njemen", "Nepal", "Danska"]

    assert _sorted(names, "sr") == [
        "Crna Gora",
        "Čad",
        "Ćirilica",
        "Danska",
        "Dominika",
        "Džibuti",
        "Đibuti",
        "Luksemburg",
        "Ljubljana",
        "Nepal",
        "Njemen",
        "Srbija",
        "Švedska",
        "Zambija",
        "Žuta",
    ]


def test_turkish_and_english_orders() -> None:
    assert _sorted(["Çad", "Danimarka", "Cabo Verde"], "tr") == ["Cabo Verde", "Çad", "Danimarka"]
    # İngilizcede işaretli harf işaretsiz hâlinin yerindedir: Åland A'da, Curaçao C'de.
    assert _sorted(["Austria", "Åland Islands", "Afghanistan", "Azerbaijan"], "en") == [
        "Afghanistan",
        "Åland Islands",
        "Austria",
        "Azerbaijan",
    ]
    assert _sorted(["Czechia", "Curaçao", "Chad"], "en") == ["Chad", "Curaçao", "Czechia"]


def test_every_country_name_sorts_in_the_language_order() -> None:
    serbian = _sorted([country.name("sr") for country in countries()], "sr")
    assert serbian.index("Crna Gora") < serbian.index("Čad") < serbian.index("Češka")
    assert serbian.index("Češka") < serbian.index("Danska") < serbian.index("Džibuti")
    assert serbian.index("Srbija") < serbian.index("Švedska") < serbian.index("Tajland")
    english = _sorted([country.name("en") for country in countries()], "en")
    assert english.index("Tunisia") < english.index("Türkiye") < english.index("Turkmenistan")


def test_sort_key_follows_the_current_language_and_rejects_unknown_ones() -> None:
    with use_language("sr"):
        assert sort_key("Čad") == sort_key("Čad", "sr")
    with use_language("tr"):
        assert sort_key("Çad") == sort_key("Çad", "tr")
    with pytest.raises(ValueError, match="desteklenmeyen dil"):
        sort_key("Čad", "de")


def test_every_language_has_an_alphabet() -> None:
    assert set(ALPHABETS) == set(SUPPORTED_LANGUAGES) == set(TERRITORY_RESOURCES)
    for alphabet in ALPHABETS.values():
        assert len(set(alphabet)) == len(alphabet)
