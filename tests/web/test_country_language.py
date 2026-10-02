"""10.10.5 — ülke adları ve JavaScript metinleri seçili dilde: Belge Türleri ülke süzgecinin
seçenekleri isteğin dilindeki adlarla ve o dilin harf sırasıyla, "Hepsi" / "Genel — ülkesiz"
çevrili; `country-select.js` ve `copy-link.js` görünen metni sunucudan (`data-*`) alır, `.js`
dosyalarında Türkçe görünen dizge yoktur; arama katlaması Türkçe ve Sırpça işaretleri kaldırır
(PLAN.md §D92 i, j; tm 157). Veri sentetiktir.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from html import unescape
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.storage import DataLayout
from app.telegram.link import write_bot_info
from app.web.auth import PanelUser, get_current_user
from tests.web.conftest import SIGNED_IN

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "app" / "web" / "static"
SCRIPTS = ("copy-link.js", "country-select.js", "upload.js")
TURKISH_LETTERS = re.compile(r"[çğıİöşüÇĞÖŞÜ]")


@pytest.fixture
def speak(app: FastAPI):
    """Oturumdaki kullanıcının dil tercihini koyar (girişli istekte dil hesabın tercihidir)."""

    def choose(language: str) -> None:
        user = PanelUser(SIGNED_IN.id, SIGNED_IN.username, SIGNED_IN.role, language=language)
        app.dependency_overrides[get_current_user] = lambda: user

    return choose


def _create(client: TestClient, slug: str, country: str | None) -> None:
    data = {
        "slug": slug,
        "name": slug.title(),
        "file_label": slug.title(),
        "country": country or "",
        "description": "",
        "expected_file_types": ["pdf"],
        "pages_min": "1",
        "pages_max": "1",
        "sides": "single",
        "analyze": "on",
        "required_fields": "surname",
        "allowed_conversions": ["merge"],
        "output_format": "pdf",
        "acceptance_criteria": ["Edges visible"],
        "prompt_description": "",
    }
    response = client.post("/document-types", data=data, follow_redirects=False)
    assert response.status_code == 303, response.text


def _country_catalog(client: TestClient) -> None:
    """Sentetik katalog: dil sırası tuzakları (C < Č, D < Dž < Đ, S < Š; Türkçede C < Ç) ve ülkesiz
    bir tür."""
    for code in ("SE", "DJ", "DK", "CZ", "TD", "CF", "RS"):
        _create(client, f"type_{code.lower()}", code)
    _create(client, "type_general", None)


def _options(html: str) -> list[tuple[str, str]]:
    found = re.search(r'<select id="country"[^>]*>(.*?)</select>', html, re.S)
    assert found is not None
    return [
        (value, unescape(label))
        for value, label in re.findall(
            r'<option value="([^"]*)"[^>]*>([^<]*)</option>', found.group(1)
        )
    ]


def _select_tag(html: str) -> str:
    found = re.search(r'<select id="country"[^>]*>', html)
    assert found is not None
    return unescape(found.group(0))


EXPECTED = {
    "en": [
        ("all", "All (8)"),
        ("general", "General — no country (1)"),
        ("CF", "Central African Republic (1)"),
        ("TD", "Chad (1)"),
        ("CZ", "Czechia (1)"),
        ("DK", "Denmark (1)"),
        ("DJ", "Djibouti (1)"),
        ("RS", "Serbia (1)"),
        ("SE", "Sweden (1)"),
    ],
    "sr": [
        ("all", "Svi (8)"),
        ("general", "Opšte — bez zemlje (1)"),
        ("CF", "Centralnoafrička Republika (1)"),
        ("TD", "Čad (1)"),
        ("CZ", "Češka (1)"),
        ("DK", "Danska (1)"),
        ("DJ", "Džibuti (1)"),
        ("RS", "Srbija (1)"),
        ("SE", "Švedska (1)"),
    ],
    "tr": [
        ("all", "Hepsi (8)"),
        ("general", "Genel — ülkesiz (1)"),
        ("DJ", "Cibuti (1)"),
        ("TD", "Çad (1)"),
        ("CZ", "Çekya (1)"),
        ("DK", "Danimarka (1)"),
        ("SE", "İsveç (1)"),
        ("CF", "Orta Afrika Cumhuriyeti (1)"),
        ("RS", "Sırbistan (1)"),
    ],
}


@pytest.mark.parametrize("language", ["en", "sr", "tr"])
def test_country_filter_options_follow_the_language_names_and_order(
    client: TestClient, speak, language: str
) -> None:
    _country_catalog(client)
    speak(language)

    page = client.get("/document-types")

    assert page.status_code == 200
    assert _options(page.text) == EXPECTED[language]
    # Süzgeç değeri dilden bağımsız koddur.
    filtered = client.get("/document-types?country=cz")
    assert 'value="CZ"' in filtered.text and " selected>" in filtered.text


SEARCH_TEXTS = {
    "en": ("Search country", "Search country…", "No matching country."),
    "sr": ("Pretraži zemlje", "Pretraži zemlje…", "Nema odgovarajuće zemlje."),
    "tr": ("Ülke ara", "Ülke ara…", "Eşleşen ülke yok."),
}


@pytest.mark.parametrize("language", ["en", "sr", "tr"])
def test_the_country_select_carries_its_texts_in_the_language(
    client: TestClient, speak, language: str
) -> None:
    _country_catalog(client)
    speak(language)

    tag = _select_tag(client.get("/document-types").text)

    label, placeholder, empty = SEARCH_TEXTS[language]
    assert f'data-search-label="{label}"' in tag
    assert f'data-search-placeholder="{placeholder}"' in tag
    assert f'data-empty-text="{empty}"' in tag


@pytest.mark.parametrize(
    ("language", "copied", "button"),
    [("en", "Copied", "Copy link"), ("sr", "Kopirano", "Kopiraj link"), ("tr", "Kopyalandı", None)],
)
def test_the_copy_button_carries_the_copied_text_in_the_language(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    speak,
    language: str,
    copied: str,
    button: str | None,
) -> None:
    write_bot_info(layout, "documania_test_bot")
    speak(language)

    page = client.post("/account/telegram/link", follow_redirects=False)

    assert page.status_code == 200
    button_tag = r'<button type="button" data-copy-target="telegram-link-url"[^>]*>'
    found = re.search(button_tag + r"([^<]*)</button>", page.text)
    assert found is not None
    tag = unescape(found.group(0))
    assert f'data-copied-text="{copied}"' in tag
    assert unescape(found.group(1)) == (button or "Bağlantıyı kopyala")


# --- `.js` dosyalarında görünen dizge yok (statik tarama) ---------------------------------------


def _code_without_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", source)


def _string_literals(code: str) -> list[str]:
    return [
        double or single
        for double, single in re.findall(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'', code)
    ]


@pytest.mark.parametrize("name", SCRIPTS)
def test_scripts_have_no_turkish_visible_strings(name: str) -> None:
    code = _code_without_comments((STATIC / name).read_text(encoding="utf-8"))

    literals = _string_literals(code)
    assert literals  # tarama boşa çalışmıyor
    assert [text for text in literals if TURKISH_LETTERS.search(text)] == []
    for word in ("Kopyalandı", "Ülke", "ülke", "Eşleşen", "Kopyala"):
        assert word not in code, (name, word)


def test_the_scanner_catches_a_turkish_string() -> None:
    # Kural bozması sınaması: tarayıcı Türkçe dizgeyi görür, yorumdakini görmez.
    code = _code_without_comments('/* Ülke */\n// Ülke ara\nbutton.textContent = "Kopyalandı";')
    assert [text for text in _string_literals(code) if TURKISH_LETTERS.search(text)] == [
        "Kopyalandı"
    ]


def test_the_scripts_read_their_texts_from_data_attributes() -> None:
    select = (STATIC / "country-select.js").read_text(encoding="utf-8")
    for attribute in ("data-search-label", "data-search-placeholder", "data-empty-text"):
        assert f'select.getAttribute("{attribute}")' in select
    copy = (STATIC / "copy-link.js").read_text(encoding="utf-8")
    assert 'button.getAttribute("data-copied-text")' in copy


# --- arama katlaması (node birim testi) ------------------------------------------------------


NODE_SEARCH = """
const fs = require("fs");
const vm = require("vm");
const context = {};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
const search = context.documaniaCountrySearch;
const cases = JSON.parse(process.argv[2]);
const found = cases.map(([label, query]) => search.matches(search.searchable(label), query));
console.log(JSON.stringify(found));
"""

SEARCH_CASES = [
    ("Srbija (2)", "srbija", True),
    ("Češka (1)", "cesk", True),
    ("Češka (1)", "češk", True),
    ("Türkiye (1)", "turkiye", True),
    ("Sırbistan (1)", "sirb", True),
    ("İsveç (1)", "isvec", True),
    ("IRAK (1)", "irak", True),
    ("Švedska (1)", "svedska", True),
    ("Ćirilica", "cir", True),
    ("Žuta", "zut", True),
    ("Đibuti (1)", "djibuti", True),
    ("Đibuti (1)", "dibuti", True),
    ("Đibuti (1)", "Đibuti", True),
    ("Rusija (1) RU", "ru", True),
    ("Anything", "", True),
    ("Srbija (2)", "hrvat", False),
    ("Češka (1)", "cz x", False),
]


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_search_folding_removes_turkish_and_serbian_marks() -> None:
    result = subprocess.run(
        [
            "node",
            "-e",
            NODE_SEARCH,
            str(STATIC / "country-select.js"),
            json.dumps([[label, query] for label, query, _ in SEARCH_CASES]),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [expected for _, _, expected in SEARCH_CASES]


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
@pytest.mark.parametrize("name", SCRIPTS)
def test_the_scripts_parse(name: str) -> None:
    result = subprocess.run(
        ["node", "--check", str(STATIC / name)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
