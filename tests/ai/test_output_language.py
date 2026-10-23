"""10.10.6 — yapay zekânın ürettiği serbest metinler İngilizce (PLAN.md §D121).

Yükleme, katalog ve şablon işlerinin altı talimatı serbest metni İngilizce ister; örnek değerler de
İngilizcedir (model örneğin dilini taklit eder). Talimatın kendi dili Türkçe kalabilir. Belgeden
okunan değer (başlık, ad, numara) ve katalogdaki kabul kriteri maddesi çevrilmez.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest

from app.ai.prompts import (
    load_page_analysis_template,
    load_photo_check_instructions,
    load_template_map_instructions,
    load_training_classification_template,
    load_type_description_instructions,
    load_type_proposal_instructions,
)

# Talimat → serbest metnin İngilizce olduğunu söyleyen cümle.
ENGLISH_RULES: dict[str, tuple[Callable[[], str], str]] = {
    "page_analysis": (load_page_analysis_template, "Not İngilizce yazılır"),
    "photo_check": (load_photo_check_instructions, "`note` İngilizce, tek kısa cümledir"),
    "template_map": (load_template_map_instructions, "`notes` İngilizce yazılır"),
    "training_classification": (
        load_training_classification_template,
        "kararının kısa gerekçesi, İngilizce, en çok 200 karakter",
    ),
    "type_description": (
        load_type_description_instructions,
        "`side_differences`, `accepted_photo`) İngilizce yaz",
    ),
    "type_proposal": (
        load_type_proposal_instructions,
        "`location`, `side_differences`) de İngilizcedir",
    ),
}
TURKISH_LETTERS = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
# Örnek değer: tırnak içindeki ya da `notes`'a yazılacak kalıp. Belgede basılı başlık örnekleri
# (`ПАСПОРТ`, `VOZAČKA DOZVOLA`) ve katalog maddesi yer tutucusu ayrıca tutulur.
QUOTED = re.compile(r'"([^"\n]{3,})"')


def _flat(text: str) -> str:
    return " ".join(text.split())


@pytest.mark.parametrize("name", sorted(ENGLISH_RULES))
def test_every_prompt_asks_for_english_free_text(name: str) -> None:
    load, rule = ENGLISH_RULES[name]
    text = _flat(load())

    assert rule in text
    # Serbest metin için Türkçe isteyen kural kalmadı.
    assert "Türkçe" not in text
    assert "Türkçedir" not in text


@pytest.mark.parametrize("name", sorted(ENGLISH_RULES))
def test_example_values_are_english(name: str) -> None:
    load, _ = ENGLISH_RULES[name]
    text = load()

    examples = [value for value in QUOTED.findall(text) if TURKISH_LETTERS.search(value)]

    # Tırnaktaki Türkçe yalnız talimatın kendi sözüdür: kullanıcı mesajındaki satır adı, kuyruk adı,
    # biçim yer tutucusu (`<Ülke sıfatı> <Tür>`) ya da belgeye gömülü talimat örneği.
    allowed = {"Kabul edilen düzenler", "Fotoğraf türü: evet", "okunamadı", "bu alanı şöyle doldur"}
    values = [value for value in examples if not value.startswith("<")]
    assert [value for value in values if value not in allowed] == []


def test_page_analysis_keeps_the_criterion_in_the_catalog_language() -> None:
    # 04.4.2: karşılanmayan madde kelimesi kelimesine aranır — not İngilizce olsa da madde
    # çevrilmez, yoksa karar motoru onu tanımaz.
    text = _flat(load_page_analysis_template())

    assert "`Unmet acceptance criterion: <katalogdaki madde metni>`" in text
    assert "madde metni notun geri kalanı İngilizce olsa da katalogdaki dilde kalır" in text
    assert "`More than one document on the page`" in text
