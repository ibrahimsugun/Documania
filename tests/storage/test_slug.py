"""00.4.2 — Türkçe, Kiril ve Arap isimler `[A-Za-z0-9_-]` kümesine iner."""

import re

import pytest

from app.storage.slug import SlugError, slugify, transliterate

ALLOWED = re.compile(r"[A-Za-z0-9_-]+")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Çağrı Şükrü Öztürk", "Cagri_Sukru_Ozturk"),
        ("İPEK IŞIK ĞÜLÜM", "IPEK_ISIK_GULUM"),
        ("ığdış çöğüş", "igdis_cogus"),
    ],
)
def test_turkish_letters_map_to_latin(text: str, expected: str) -> None:
    assert slugify(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Дмитрий Васильев", "Dmitrii_Vasilev"),
        ("Щукина Юлия Жановна", "Shchukina_Iuliia_Zhanovna"),
        ("Хабибуллин Эдуард Цой", "Khabibullin_Eduard_Tsoi"),
        ("Мар'яна Коваль", "Mariana_Koval"),  # Ukraynaca kesme işareti kelimeyi bölmez
        ("Ђорђе Јовановић", "Dorde_Jovanovic"),  # Sırpça
        ("Жанна Қайратқызы", "Zhanna_Kairatkyzy"),  # Kazakça
    ],
)
def test_cyrillic_maps_to_latin(text: str, expected: str) -> None:
    assert slugify(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("محمد علي", "mhmd_aly"),
        ("فاطمة الزهراء", "fatma_alzhra"),
        ("خالد شريف", "khald_shryf"),
        ("مُحَمَّد", "mhmd"),  # harekeler düşer
        ("ﻻ", "la"),  # sunum biçimi önce temel harfe iner
        ("پرویز ٣٤", "prwyz_34"),  # Farsça harf + Arap-Hint rakamı
    ],
)
def test_arabic_maps_to_latin(text: str, expected: str) -> None:
    assert slugify(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Çağrı Şükrü Öztürk İnce",
        "Дмитрий Васильев",
        "محمد بن عبد الله",
        "José Müller-Straße O'Brien",
        "  --Ömer   Faruk.. ",
        "Łukasz Øster Þór Ħamrun Đorđe",
    ],
)
def test_output_is_within_allowed_set(text: str) -> None:
    for separator in ("_", "-"):
        result = slugify(text, separator)
        assert ALLOWED.fullmatch(result)
        assert not result.startswith(separator)
        assert not result.endswith(separator)
        assert f"{separator}{separator}" not in result


@pytest.mark.parametrize(
    ("first", "last"),
    [
        (0x00C0, 0x024F),  # Latin-1 eki, Latin Genişletilmiş A/B (Türkçe harfler dahil)
        (0x0400, 0x052F),  # Kiril + Kiril eki
        (0x0600, 0x06FF),  # Arapça
        (0xFB50, 0xFDFF),  # Arapça sunum biçimleri A
        (0xFE70, 0xFEFF),  # Arapça sunum biçimleri B
    ],
)
def test_every_character_of_three_scripts_reduces_to_allowed_set(first: int, last: int) -> None:
    for codepoint in range(first, last + 1):
        text = f"Ad{chr(codepoint)}Soyad"
        assert ALLOWED.fullmatch(slugify(text)), f"U+{codepoint:04X}"


def test_capitalize_normalizes_case_per_word() -> None:
    assert slugify("DMITRII VASILEV", capitalize=True) == "Dmitrii_Vasilev"
    assert slugify("ЩУКИНА юлия", capitalize=True) == "Shchukina_Iuliia"
    assert slugify("çağrı ÖZTÜRK", capitalize=True) == "Cagri_Ozturk"


def test_slugify_is_idempotent() -> None:
    once = slugify("Дмитрий Çağrı محمد", "-")
    assert slugify(once, "-") == once


def test_max_length_cuts_at_word_boundary() -> None:
    assert slugify("alpha beta gamma", max_length=11) == "alpha_beta"
    assert slugify("alpha beta gamma", max_length=10) == "alpha_beta"
    assert slugify("abcdefghij klm", max_length=4) == "abcd"


@pytest.mark.parametrize("text", ["", "   ", "---", "张伟", "'’"])
def test_text_without_usable_characters_raises(text: str) -> None:
    with pytest.raises(SlugError):
        slugify(text)


def test_invalid_arguments_rejected() -> None:
    with pytest.raises(ValueError, match="Ayırıcı"):
        slugify("Ad Soyad", ".")
    with pytest.raises(ValueError, match="max_length"):
        slugify("Ad Soyad", max_length=0)


def test_transliterate_returns_ascii() -> None:
    assert transliterate("Şeyma Дарья").isascii()
