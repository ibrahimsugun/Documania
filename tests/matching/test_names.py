"""05.1.1 — Aksan, noktalama ve sıra farkları aynı isim anahtarına iner (§20.2.1)."""

import pytest

from app.matching.names import EmptyNameError, normalize_name


def _same_key(*spellings: str) -> str:
    keys = {normalize_name(spelling) for spelling in spellings}
    assert len(keys) == 1, keys
    return keys.pop()


def test_key_is_lowercase_words_sorted_and_single_spaced() -> None:
    assert normalize_name("  VASILIEV   Dmitry ") == "dmitry vasiliev"


@pytest.mark.parametrize(
    ("spellings", "key"),
    [
        (("José Müller", "JOSE MULLER", "jose muller"), "jose muller"),
        (("Zoë Núñez-Ångström", "Zoe Nunez Angstrom"), "angstrom nunez zoe"),
        (("Łukasz Żółć", "Lukasz Zolc"), "lukasz zolc"),
        (("Søren Kierkegaard", "Soren KIERKEGAARD"), "kierkegaard soren"),
        (("Đorđe Þór", "Dorde Thor"), "dorde thor"),
        (("Æsa Œdipe", "AESA OEDIPE"), "aesa oedipe"),
        (("Strauß", "STRAUSS"), "strauss"),
        (("Ștefan Țurcanu", "Stefan Turcanu"), "stefan turcanu"),
    ],
)
def test_accents_reduce_to_the_same_key(spellings: tuple[str, ...], key: str) -> None:
    assert _same_key(*spellings) == key


@pytest.mark.parametrize(
    ("spellings", "key"),
    [
        (("Çağrı Şükrü Öztürk", "CAĞRI ŞÜKRÜ ÖZTÜRK", "Cagri Sukru Ozturk"), "cagri ozturk sukru"),
        (("IŞIK", "Işık", "ışık", "İŞIK", "isik", "ISIK"), "isik"),
        (("İSMAİL İpek", "Ismail IPEK", "ısmaıl ıpek"), "ipek ismail"),
        (("Gül Ağaoğlu", "GUL AGAOGLU"), "agaoglu gul"),
    ],
)
def test_turkish_letters_reduce_to_latin(spellings: tuple[str, ...], key: str) -> None:
    assert _same_key(*spellings) == key


@pytest.mark.parametrize(
    ("spellings", "key"),
    [
        (
            ("Jean-Pierre Dupont", "Jean Pierre Dupont", "JEAN–PIERRE  DUPONT."),
            "dupont jean pierre",
        ),
        (
            ("Dupont, Jean-Pierre", "DUPONT<<JEAN<PIERRE", "Dupont / Jean / Pierre"),
            "dupont jean pierre",
        ),
        (("O'Brien", "O’Brien", "O´Brien", "O`Brien", "O＇Brien", "OBRIEN"), "obrien"),
        (("Saʿid Qurʾan", "Said Quran"), "quran said"),
        (("Wolf\u00adgang", "Wolf\u200bgang", "\ufeffWolfgang"), "wolfgang"),
        (("J. R. Tolkien", "J R TOLKIEN"), "j r tolkien"),
    ],
)
def test_punctuation_and_spacing_reduce_to_the_same_key(
    spellings: tuple[str, ...], key: str
) -> None:
    assert _same_key(*spellings) == key


@pytest.mark.parametrize(
    "spellings",
    [
        ("Dmitry Vasiliev", "VASILIEV DMITRY", "Vasiliev, Dmitry", "VASILIEV<<DMITRY"),
        ("Ahmet Can Yılmaz", "Yılmaz Ahmet Can", "CAN AHMET YILMAZ"),
        ("María José García López", "GARCIA LOPEZ, MARIA JOSE"),
    ],
)
def test_word_order_does_not_change_the_key(spellings: tuple[str, ...]) -> None:
    _same_key(*spellings)


def test_parts_form_one_name_in_any_order() -> None:
    whole = normalize_name("Dmitry Vasiliev")
    assert normalize_name("Dmitry", "Vasiliev") == whole
    assert normalize_name("VASILIEV", "Dmitry") == whole
    assert normalize_name(None, "Dmitry", None, "Vasiliev") == whole


def test_compatibility_forms_fold_to_plain_letters() -> None:
    assert _same_key("ＡＨＭＥＴ", "Ahmet") == "ahmet"
    assert _same_key("ﬁliz", "FILIZ") == "filiz"
    assert _same_key("ℌans", "HANS") == "hans"


def test_marks_that_split_nothing_are_removed() -> None:
    # Birleştirici işaret (U+034F) ve Arapça harekeler kelimeyi bölmeden düşer.
    assert _same_key("A\u034fli", "Ali") == "ali"
    assert normalize_name("مُحَمَّد") == normalize_name("محمد")


def test_apostrophe_revealed_by_folding_does_not_split_the_word() -> None:
    # `ŉ` ayrışınca `ʼn` olur; ortaya çıkan kesme işareti de silinir.
    assert normalize_name("Vanŉ") == normalize_name("Vann")


def test_non_latin_letters_are_kept_and_folded() -> None:
    # Latin'e çeviri 05.2'nindir; o olmadan da harfler düşmez, büyüklük ve sıra yine katlanır.
    cyrillic = normalize_name("Дмитрий Васильев")
    assert normalize_name("ВАСИЛЬЕВ ДМИТРИЙ") == cyrillic
    assert normalize_name("Иван Петров") != cyrillic


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Ahmet Yılmaz", "Ahmet Yılmazer"),
        ("Ali Ali Veli", "Ali Veli"),
        ("Ana-Maria Pop", "Anamaria Pop"),
        ("Ali Rıza", "Alirıza"),
        ("Mehmet2", "Mehmet"),
    ],
)
def test_different_names_keep_different_keys(first: str, second: str) -> None:
    assert normalize_name(first) != normalize_name(second)


@pytest.mark.parametrize(
    "name",
    [
        "Çağrı Şükrü Öztürk",
        "O'Brien, Jean-Pierre",
        "Straße Ⅲ",
        "Дмитрий Васильев",
    ],
)
def test_normalization_is_idempotent(name: str) -> None:
    key = normalize_name(name)
    assert normalize_name(key) == key


@pytest.mark.parametrize(
    "parts",
    [(), ("",), ("   ",), ("-.,'<<",), (None,), (None, " / "), ("\u00ad\u200b",)],
)
def test_name_without_words_has_no_key(parts: tuple[str | None, ...]) -> None:
    with pytest.raises(EmptyNameError):
        normalize_name(*parts)


def test_empty_name_error_is_a_value_error() -> None:
    assert issubclass(EmptyNameError, ValueError)
