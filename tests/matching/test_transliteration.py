"""05.2.1 — Kiril ve Arap yazımlar ICAO Doc 9303 Bölüm 3 §6 tablolarıyla Latin karşılığına
çevrilir; orijinal yazım da saklanır (§20.2.1). Kabul senaryosu: S13.

Beklenen değerler tablonun satırlarından elle yazılmıştır (Tablo B: Kiril, Tablo C: Arap MRZ
sütunu); isimler sentetiktir.
"""

from __future__ import annotations

import dataclasses
import unicodedata
from pathlib import Path

import pytest

from app.ai import validate_page_analysis
from app.catalog import load_seed_catalog
from app.matching.names import TransliteratedName, normalize_name, transliterate_name
from app.storage.naming import employee_folder_name

ROOT = Path(__file__).resolve().parents[2]
S13_RECORDING = ROOT / "tests" / "fixtures" / "ai" / "recordings" / "s13_cyrillic_name" / "0.json"


def _latin(text: str, language: str | None = None) -> str:
    return transliterate_name(text, language=language).latin


def test_russian_alphabet_follows_table_b() -> None:
    upper = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
    expected = "ABVGDEEZHZIIKLMNOPRSTUFKHTSCHSHSHCHIEYEIUIA"
    assert _latin(upper) == expected
    assert _latin(upper.lower()) == expected.lower()


@pytest.mark.parametrize(
    ("letter", "latin"),
    [
        ("Ђ", "D"),
        ("Є", "IE"),
        ("Ѕ", "DZ"),
        ("І", "I"),
        ("Ї", "I"),
        ("Ј", "J"),
        ("Љ", "LJ"),
        ("Њ", "NJ"),
        ("Ќ", "K"),
        ("Ў", "U"),
        ("Џ", "DZ"),
        ("Ѫ", "U"),
        ("Ѵ", "Y"),
        ("Ґ", "G"),
        ("Ғ", "G"),
        ("Һ", "C"),
    ],
)
def test_other_table_b_rows_use_the_default_column(letter: str, latin: str) -> None:
    assert _latin(letter * 2) == latin * 2
    assert _latin(letter.lower()) == latin.lower()


@pytest.mark.parametrize(
    ("text", "latin"),
    [
        ("Дмитрий Васильев", "Dmitrii Vasilev"),
        ("ЩУКИНА ЮЛИЯ ЖАНОВНА", "SHCHUKINA IULIIA ZHANOVNA"),
        ("Хабибуллин Эдуард Цой", "Khabibullin Eduard Tsoi"),
        ("Подъячев Чернышёв", "Podieiachev Chernyshev"),
        ("Ю. Щ. Жуков", "Iu. Shch. Zhukov"),
        ("Жуков-ЖУКОВ", "Zhukov-ZHUKOV"),
    ],
)
def test_multi_letter_capitals_follow_neighbouring_case(text: str, latin: str) -> None:
    assert _latin(text) == latin


def test_letters_without_a_table_row() -> None:
    # Ь yazılmaz, Ћ → C (C24); ayrışan harf temel harfiyle çevrilir.
    assert _latin("Ольга Игорь Петровић") == "Olga Igor Petrovic"
    assert normalize_name("Ѝван Ӣсмоил Ѓорѓи") == normalize_name("Ivan Ismoil Gorgi")
    # Ne satırı olan ne ayrışan harf tahminle indirilmez: Latin yazımla eşleşmez.
    assert _latin("Қайрат") == "Қairat"
    assert normalize_name("Қайрат") != normalize_name("Kairat")


@pytest.mark.parametrize(
    ("language", "text", "latin"),
    [
        ("be", "Алёна Гарэцкая", "Aliona Haretskaia"),
        ("bg", "Щерев", "Shterev"),
        ("mk", "Ќосе Џафер Христо Цветан Ғани", "Kjose Djafer Hristo Cvetan Gjani"),
        ("sr", "Живковић Чедомир Шћекић Хаџић Цвијета", "Zivkovic Cedomir Scekic Hadzic Cvijeta"),
        ("sr", "Горан", "Horan"),  # tablonun yazdığı gibi (D7)
        ("uk", "Микола Григорій", "Mykola Hryhorii"),
        ("uk", "Юлія Єва Їжак Йосип Яна Моє", "Yuliia Yeva Yizhak Yosyp Yana Moie"),
        ("uk", "Мар'яна Ющенко-Ярова", "Mar'iana Yushchenko-Yarova"),
        ("uk", "ЮЛІЯ ЇЖАК", "YULIIA YIZHAK"),
        ("UK", "Юрій", "Yurii"),
    ],
)
def test_language_exceptions_of_table_b(language: str, text: str, latin: str) -> None:
    assert _latin(text, language) == latin


@pytest.mark.parametrize("language", [None, "ru", "kk", "tr"])
def test_other_languages_use_the_default_column(language: str | None) -> None:
    assert _latin("Юлія Григорій Щерев Живковић", language) == "Iuliia Grigorii Shcherev Zhivkovic"


@pytest.mark.parametrize(
    ("letter", "mrz"),
    [
        ("ء", "XE"),
        ("آ", "XAA"),
        ("أ", "XAE"),
        ("ؤ", "U"),
        ("إ", "I"),
        ("ئ", "XI"),
        ("ا", "A"),
        ("ب", "B"),
        ("ت", "T"),
        ("ث", "XTH"),
        ("ج", "J"),
        ("ح", "XH"),
        ("خ", "XKH"),
        ("د", "D"),
        ("ذ", "XDH"),
        ("ر", "R"),
        ("ز", "Z"),
        ("س", "S"),
        ("ش", "XSH"),
        ("ص", "XSS"),
        ("ض", "XDZ"),
        ("ط", "XTT"),
        ("ظ", "XZZ"),
        ("ع", "E"),
        ("غ", "G"),
        ("ـ", ""),
        ("ف", "F"),
        ("ق", "Q"),
        ("ك", "K"),
        ("ل", "L"),
        ("م", "M"),
        ("ن", "N"),
        ("ه", "H"),
        ("و", "W"),
        ("ى", "XAY"),
        ("ي", "Y"),
        ("ً", ""),
        ("ٌ", ""),
        ("ٍ", ""),
        ("َ", ""),
        ("ُ", ""),
        ("ِ", ""),
        ("ْ", ""),
        ("ٰ", ""),
        ("ٱ", "XXA"),
        ("ٹ", "XXT"),
        ("ټ", "XRT"),
        ("پ", "P"),
        ("ځ", "XKE"),
        ("څ", "XXH"),
        ("چ", "XC"),
        ("ڈ", "XXD"),
        ("ډ", "XDR"),
        ("ڑ", "XXR"),
        ("ړ", "XRR"),
        ("ږ", "XRX"),
        ("ژ", "XJ"),
        ("ښ", "XXS"),
        ("ڜ", ""),
        ("ڢ", ""),
        ("ڧ", ""),
        ("ڨ", ""),
        ("ک", "XKK"),
        ("ګ", "XXK"),
        ("ڭ", "XNG"),
        ("گ", "XGG"),
        ("ں", "XNN"),
        ("ڼ", "XXN"),
        ("ھ", "XDO"),
        ("ۀ", "XYH"),
        ("ہ", "XXG"),
        ("ۂ", "XGE"),
        ("ۃ", "XTG"),
        ("ی", "XYA"),
        ("ۍ", "XXY"),
        ("ې", "Y"),
        ("ے", "XYB"),
        ("ۓ", "XBE"),
    ],
)
def test_arabic_letters_follow_table_c(letter: str, mrz: str) -> None:
    assert _latin(letter) == mrz
    assert _latin(unicodedata.normalize("NFD", letter)) == mrz


@pytest.mark.parametrize(
    ("text", "latin"),
    [
        ("محمد علي", "MXHMD ELY"),
        ("عبّاس", "EBBAS"),  # tablonun şedde örneği
        ("فضّة", "FXDZXDZXAH"),  # tablonun şedde örneği: çok harfli karşılık ikilenir
        ("مُحَمَّد", "MXHMMD"),  # harekeler yazılmaz, şedde hareke arkasından da ikiler
        ("فاطمة الزهراء", "FAXTTMXAH ALZHRAXE"),
        ("فاطمةً", "FAXTTMXAH"),  # sondaki harekeli ة yine ad parçasının sonu
        ("ةم", "XTAM"),  # ad parçasının sonunda değil
        ("محـــمد", "MXHMD"),  # tatvil yazılmaz, kelimeyi bölmez
        ("ﻣﺤﻤﺪ ﻻ", "MXHMD LA"),  # sunum biçimleri temel harfe iner
        ("پرویز", "PRWXYAZ"),
        ("ّب ّ", "B "),  # önünde harf olmayan şedde yazılmaz
        ("Ali محمد", "Ali MXHMD"),
    ],
)
def test_arabic_names_follow_table_c_rules(text: str, latin: str) -> None:
    assert _latin(text) == latin


@pytest.mark.parametrize(
    "text",
    [
        "Дмитрий Васильев",
        unicodedata.normalize("NFD", "Йосип Щёлкин"),
        "ﻣﺤﻤﺪ",
        "مُحَمَّد",
        "José Müller",
        "",
    ],
)
def test_original_spelling_is_kept_untouched(text: str) -> None:
    name = transliterate_name(text, language="uk")
    assert name == TransliteratedName(original=text, latin=name.latin)
    assert name.original == text
    with pytest.raises(dataclasses.FrozenInstanceError):
        name.original = "başka"  # type: ignore[misc]


@pytest.mark.parametrize("text", ["José Müller", "O'Brien, Jean-Pierre", "Çağrı İpek", "Γιώργος"])
def test_names_without_cyrillic_or_arabic_are_not_changed(text: str) -> None:
    assert _latin(text) == text


@pytest.mark.parametrize(
    ("spellings", "language", "key"),
    [
        (
            ("Дмитрий Васильев", "ВАСИЛЬЕВ ДМИТРИЙ", "VASILEV DMITRII", "VASILEV<<DMITRII"),
            None,
            "dmitrii vasilev",
        ),
        (("Микола Григоренко", "HRYHORENKO MYKOLA"), "uk", "hryhorenko mykola"),
        (("Живковић Чедомир", "ŽIVKOVIĆ ČEDOMIR", "Zivkovic Cedomir"), "sr", "cedomir zivkovic"),
        (("محمد علي", "علي مُحَمَد", "ELY MXHMD"), None, "ely mxhmd"),
    ],
)
def test_script_spellings_reduce_to_the_same_key(
    spellings: tuple[str, ...], language: str | None, key: str
) -> None:
    assert {normalize_name(spelling, language=language) for spelling in spellings} == {key}


def test_non_icao_spelling_is_not_folded_into_the_icao_key() -> None:
    # §20.2.1 örneği `Dmitry Vasiliev`'i Kiril yazımla aynı anahtara indirir; ICAO tablosu
    # `Dmitrii Vasilev` verir. Yazım varyantı katlaması uydurulmadı (PLAN.md D7).
    assert normalize_name("Дмитрий Васильев") != normalize_name("Dmitry Vasiliev")


@pytest.mark.parametrize("language", [None, "uk", "sr", "be", "bg", "mk", "ru", "ar"])
def test_language_changes_only_cyrillic_letters(language: str | None) -> None:
    assert normalize_name("Hryhorii Cedomir محمد", language=language) == "cedomir hryhorii mxhmd"


@pytest.mark.parametrize(
    ("name", "language"),
    [("Юлія Григорій", "uk"), ("فاطمة الزهراء", None), ("Қайрат Щерев", "bg")],
)
def test_transliterated_key_is_idempotent(name: str, language: str | None) -> None:
    key = normalize_name(name, language=language)
    assert normalize_name(key, language=language) == key


def test_s13_cyrillic_named_document_gets_latin_name_and_keeps_original() -> None:
    # S13: Kiril isimli belge → Latin dosya adı + orijinal yazım. Profile yazılması 09.1'in.
    catalog = load_seed_catalog()
    analysis = validate_page_analysis(
        S13_RECORDING.read_text(encoding="utf-8"), known_slugs=catalog.slugs()
    )
    person = analysis.person
    assert person is not None
    assert person.original_script_name is not None
    assert person.mrz_lines is not None

    name = transliterate_name(person.original_script_name, language=analysis.language)
    assert name.original == "Тестова-Щёлкина Юлья"
    assert name.latin == "Testova-Shchelkina Iulia"

    key = normalize_name(person.given_names, person.surname)
    assert key == "iulia shchelkina testova"
    assert normalize_name(person.original_script_name, language=analysis.language) == key
    assert normalize_name(name.latin) == key
    assert normalize_name(person.mrz_lines[0][5:]) == key

    folder = employee_folder_name(person.given_names, person.surname, "E0001")
    assert folder == "Iulia_Testova_Shchelkina_E0001"
    surname, given_names = person.original_script_name.split(" ")
    assert employee_folder_name(_latin(given_names), _latin(surname), "E0001") == folder
    assert employee_folder_name(given_names, surname, "E0001") == folder
