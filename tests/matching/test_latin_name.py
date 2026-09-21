"""05.2.2 — Latin ad ve orijinal yazım ayrımı (PLAN.md §C81).

Çalışanın ad, soyad ve diğer isimler alanı yalnız Latin harfi taşır; Latin yazım önce belgede
basılı Latin addan, sonra kontrol haneleri geçen MRZ'den, bunlar yoksa yalnız Kiril için kural
tabanlı çeviriden alınır (`sr`, `mk` resmî Latin; öteki Kiril ICAO). Arap ve öteki alfabelerde
tahminle çeviri yapılmaz. Eşleştirme anahtarı değişmez.

Sayfalar `tests.ai.payloads` sentetik yanıtından kurulur, MRZ satırları `test_mrz.make_mrz` ile
üretilir; adlar sentetiktir. Gerçek kişi/belge yok.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.ai import PageAnalysis
from app.catalog import load_seed_catalog
from app.matching.match import (
    PENDING_PROFILE_LATIN_REASON,
    EmployeeMatch,
    MatchRule,
    PersonKey,
    UnmatchedRule,
    build_person_key,
    resolve_unmatched,
)
from app.matching.mrz import MrzFormat
from app.matching.names import (
    LatinSource,
    LatinSpelling,
    detect_script,
    is_latin_name,
    latin_person_name,
    normalize_name,
    transliterate_cyrillic,
)
from tests.ai.payloads import analysis_payload
from tests.matching.test_mrz import make_mrz

CATALOG = load_seed_catalog()
PASSPORT = CATALOG.get("russian_passport")
assert PASSPORT is not None
TODAY = date(2026, 9, 15)
NO_MATCH = EmployeeMatch(MatchRule.NO_MATCH)

# Sırpçanın resmî Latin alfabesi (Gaj): Kiril harfi → baş harfi büyük Latin karşılığı.
SERBIAN = {
    "А": "A",
    "Б": "B",
    "В": "V",
    "Г": "G",
    "Д": "D",
    "Ђ": "Đ",
    "Е": "E",
    "Ж": "Ž",
    "З": "Z",
    "И": "I",
    "Ј": "J",
    "К": "K",
    "Л": "L",
    "Љ": "Lj",
    "М": "M",
    "Н": "N",
    "Њ": "Nj",
    "О": "O",
    "П": "P",
    "Р": "R",
    "С": "S",
    "Т": "T",
    "Ћ": "Ć",
    "У": "U",
    "Ф": "F",
    "Х": "H",
    "Ц": "C",
    "Ч": "Č",
    "Џ": "Dž",
    "Ш": "Š",
}
# Makedoncanın resmî Latin alfabesi.
MACEDONIAN = {
    "А": "A",
    "Б": "B",
    "В": "V",
    "Г": "G",
    "Д": "D",
    "Ѓ": "Gj",
    "Е": "E",
    "Ж": "Ž",
    "З": "Z",
    "Ѕ": "Dz",
    "И": "I",
    "Ј": "J",
    "К": "K",
    "Л": "L",
    "Љ": "Lj",
    "М": "M",
    "Н": "N",
    "Њ": "Nj",
    "О": "O",
    "П": "P",
    "Р": "R",
    "С": "S",
    "Т": "T",
    "Ќ": "Kj",
    "У": "U",
    "Ф": "F",
    "Х": "H",
    "Ц": "C",
    "Ч": "Č",
    "Џ": "Dž",
    "Ш": "Š",
}


# --- resmî Latin tabloları: her harf --------------------------------------------------------------


@pytest.mark.parametrize(("language", "table"), [("sr", SERBIAN), ("mk", MACEDONIAN)])
def test_official_latin_tables_cover_every_letter_in_every_case(
    language: str, table: dict[str, str]
) -> None:
    assert len(table) == (30 if language == "sr" else 31)
    for cyrillic, latin in table.items():
        # Tek başına büyük harf baş harfi büyük, küçük harf küçük, büyük harfli kelimede büyük.
        assert transliterate_cyrillic(cyrillic, language=language) == latin, cyrillic
        assert transliterate_cyrillic(cyrillic.lower(), language=language) == latin.lower()
        assert transliterate_cyrillic(cyrillic * 2, language=language) == (latin * 2).upper()


@pytest.mark.parametrize(
    ("text", "language", "expected"),
    [
        ("Ђорђе Јовановић", "sr", "Đorđe Jovanović"),
        ("ЉУБИЦА ЏАКОВИЋ-ШЋЕКИЋ", "sr", "LJUBICA DŽAKOVIĆ-ŠĆEKIĆ"),
        ("Горан Жарковић", "sr", "Goran Žarković"),  # ICAO'nun Sırpça `Г → H` istisnası değil
        ("Ѓорѓи Ќосевски", "mk", "Gjorgji Kjosevski"),
        ("Ѕвонко Џафери", "mk", "Dzvonko Džaferi"),
        ("Ѝван", "mk", "Ìvan"),  # ünlüdeki vurgu ayrı harf değildir, Latin ünlüde kalır
        ("ОБРАЗЕЦ", "ru", "OBRAZETS"),
        ("Юлия Щёлкина", "ru", "Iuliia Shchelkina"),
        ("Олександр Гнатюк", "uk", "Oleksandr Hnatiuk"),
        ("Ярослава", "uk", "Yaroslava"),  # Ukraynaca kelime başı `Я → YA`
        ("Щерев", "bg", "Shterev"),
        ("Ёлка", "be", "Iolka"),
        ("Жуков", None, "Zhukov"),  # dil bilinmiyor: ICAO varsayılan sütun
        ("Мар'яна", "uk", "Mar'iana"),
    ],
)
def test_cyrillic_is_transliterated_by_the_language_rule(
    text: str, language: str | None, expected: str
) -> None:
    assert transliterate_cyrillic(text, language=language) == expected


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Ѓорѓи", "sr"),  # Makedon harfi Sırpça tabloda yok
        ("Ђорђе", "mk"),  # Sırp harfi Makedonca tabloda yok
        ("Ыван", "sr"),
        ("ҚАЙРАТ", "kk"),  # Kazakça: ICAO tablosunda yok
        ("Қайрат", None),
        ("Ѣвгения", "ru"),
    ],
)
def test_cyrillic_letter_outside_the_table_is_not_transliterated(
    text: str, language: str | None
) -> None:
    assert transliterate_cyrillic(text, language=language) is None


@pytest.mark.parametrize(
    "text",
    [
        "محمد علي",  # Arap: kısa ünlüler yazılmaz, ICAO karşılığı (MXHMD) kişinin adı değil
        "王小明",  # Çince
        "გიორგი",  # Gürcü
        "Γιώργος",  # Yunan (ELOT 743 kapsam dışı)
        "Արամ",  # Ermeni
        "דוד",  # İbrani
        "Иван محمد",  # Kiril ve Arap karışık
        "Ivan Petrov",  # Kiril yok: çevrilecek bir şey yok
    ],
)
@pytest.mark.parametrize("language", [None, "ru", "sr", "ar"])
def test_non_cyrillic_scripts_are_never_transliterated(text: str, language: str | None) -> None:
    assert transliterate_cyrillic(text, language=language) is None


# --- alfabe ve Latin denetimi ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "latin"),
    [
        ("Đorđe Šćepanović", True),
        ("O'Brien-Smith", True),
        ("Oʻzbek", True),  # değiştirici harf alfabe söylemez
        ("MÜLLER Ölçer", True),
        ("123", True),
        ("ОБРАЗЕЦ", False),
        ("Ivan Ѕ", False),
        ("محمد", False),
        ("王", False),
    ],
)
def test_latin_name_has_only_latin_letters(text: str, latin: bool) -> None:
    assert is_latin_name(text) is latin


@pytest.mark.parametrize(
    ("text", "script"),
    [
        ("Ivan", "latin"),
        ("Иван", "cyrillic"),
        ("محمد", "arabic"),
        ("王", "other"),
        ("12-34", None),
        ("ʻAli", "latin"),
    ],
)
def test_script_detection_reads_the_first_letter(text: str, script: str | None) -> None:
    assert detect_script(text) == script


# --- kaynak önceliği: basılı Latin > MRZ > çeviri ------------------------------------------------


@pytest.mark.parametrize(
    ("readings", "mrz", "expected"),
    [
        (
            [("ŽIVKOVIĆ", "sr")],
            ("ZIVKOVIC",),
            LatinSpelling("ŽIVKOVIĆ", LatinSource.PRINTED),
        ),
        (
            [("ЖИВКОВИЋ", "sr"), ("Živković", "sr")],
            ("ZIVKOVIC",),
            LatinSpelling("Živković", LatinSource.PRINTED),
        ),
        (
            [("ZIVKOVIC", "sr"), ("ЖИВКОВИЋ", "sr")],
            ("ZIVKOVIC",),
            LatinSpelling("ZIVKOVIC", LatinSource.MRZ),
        ),
        ([("ЖИВКОВИЋ", "sr")], ("ZIVKOVIC",), LatinSpelling("ZIVKOVIC", LatinSource.MRZ)),
        ([("ЖИВКОВИЋ", "sr")], (), LatinSpelling("ŽIVKOVIĆ", LatinSource.TRANSLITERATION)),
        ([("ЖИВКОВИЋ", None)], (), LatinSpelling("ZHIVKOVIC", LatinSource.TRANSLITERATION)),
        (
            [("ҚАЙРАТ", "kk"), ("КАЙРАТ", "kk")],
            (),
            LatinSpelling("KAIRAT", LatinSource.TRANSLITERATION),
        ),
        ([("علي", "ar")], ("ALI",), LatinSpelling("ALI", LatinSource.MRZ)),
        ([("علي", "ar")], (), None),
        ([("ҚАЙРАТ", "kk")], (), None),
        ([], (), None),
    ],
    ids=[
        "printed-latin-beats-mrz",
        "printed-latin-after-a-cyrillic-reading",
        "reading-written-from-the-mrz-is-the-mrz",
        "mrz-beats-transliteration",
        "serbian-official-latin",
        "icao-without-language",
        "first-transliterable-reading",
        "arabic-only-from-mrz",
        "arabic-without-mrz",
        "cyrillic-outside-the-table",
        "nothing-read",
    ],
)
def test_latin_spelling_follows_the_source_priority(
    readings: list[tuple[str, str | None]], mrz: tuple[str, ...], expected: LatinSpelling | None
) -> None:
    assert latin_person_name(readings, mrz=mrz) == expected


# --- kişi anahtarı: yapay zekâ çıktısının korunması -----------------------------------------------

NO_PERSON = dict.fromkeys(
    (
        "surname",
        "given_names",
        "other_names",
        "original_script_name",
        "date_of_birth",
        "nationality",
        "document_number",
    )
)
SERBIAN_MRZ = {
    "code": "P",
    "state": "SRB",
    "name": "ZIVKOVIC<<MARKO",
    "number": "000000021",
    "nationality": "SRB",
    "birth": "900101",
    "sex": "M",
    "expiry": "300101",
}


def _readings(**values: str | None) -> dict[str, Any]:
    return {name: {"value": value, "legible": value is not None} for name, value in values.items()}


def _page(
    *,
    language: str = "ru",
    fields: dict[str, Any] | None = None,
    mrz: list[str] | None = None,
    top: dict[str, Any] | None = None,
    **person: Any,
) -> PageAnalysis:
    payload = analysis_payload(language=language)
    payload["fields"] = fields if fields is not None else {}
    payload.update(top or {})
    payload["person"].update(NO_PERSON, mrz_lines=mrz)
    payload["person"].update(person)
    return PageAnalysis.model_validate(payload)


def _serbian_page(*, mrz: list[str] | None = None, **person: Any) -> PageAnalysis:
    values = {"surname": "ЖИВКОВИЋ", "given_names": "МАРКО", "document_number": "000000021"}
    return _page(
        language="sr",
        fields=_readings(surname=person.pop("fields_surname", values["surname"])),
        mrz=mrz,
        **(values | person),
    )


def _key(*pages: PageAnalysis) -> PersonKey:
    return build_person_key(pages, today=TODAY)


def test_cyrillic_in_the_latin_fields_is_moved_and_the_latin_comes_from_the_mrz() -> None:
    # E0001 bulgusu: Latin ad yalnız MRZ'de; yapay zekâ Kiril yazımı `surname`/`given_names`'e
    # koydu, orijinal yazımı boş bıraktı. Kod Kiril'i orijinal yazıma taşır, Latin'i MRZ'den alır.
    page = _page(
        surname="ОРНЕКОВА",
        given_names="ТЕСТ",
        document_number="000000001",
        fields=_readings(surname="ОРНЕКОВА", given_names="ТЕСТ"),
        mrz=make_mrz(MrzFormat.TD3, state="RUS", name="ORNEKOVA<<TEST", number="000000001"),
    )

    key = _key(page)

    assert (key.latin_surname, key.latin_given_names, key.latin_other_names) == (
        "ORNEKOVA",
        "TEST",
        None,
    )
    assert key.original_spelling == "ТЕСТ ОРНЕКОВА"
    fields = key.employee_fields()
    assert (fields["surname"], fields["given_names"], fields["original_script_name"]) == (
        "ORNEKOVA",
        "TEST",
        "ТЕСТ ОРНЕКОВА",
    )
    # Eşleştirme anahtarı ve isim yazımı değişmez: okuma Kiril kalır, anahtar aynı.
    assert (key.surname, key.given_names) == ("ОРНЕКОВА", "ТЕСТ")
    assert key.normalized_name == normalize_name("ТЕСТ", "ОРНЕКОВА", language="ru")
    assert key.normalized_name == normalize_name("TEST ORNEKOVA")


def test_original_spelling_read_by_the_page_is_kept_over_the_moved_reading() -> None:
    page = _page(
        surname="ОРНЕКОВА",
        given_names="ТЕСТ",
        original_script_name="Орнекова Тест",
        document_number="000000001",
    )

    key = _key(page)

    assert key.original_spelling == "Орнекова Тест"
    assert (key.latin_surname, key.latin_given_names) == ("ORNEKOVA", "TEST")


@pytest.mark.parametrize(
    ("mrz", "fields_surname", "expected"),
    [
        (make_mrz(MrzFormat.TD3, **SERBIAN_MRZ), "ЖИВКОВИЋ", "ZIVKOVIC"),
        (make_mrz(MrzFormat.TD3, **SERBIAN_MRZ), "Živković", "Živković"),
        (
            make_mrz(MrzFormat.TD3, **SERBIAN_MRZ, checks={"document_number": "0"}),
            "ЖИВКОВИЋ",
            "ŽIVKOVIĆ",
        ),
        (None, "ЖИВКОВИЋ", "ŽIVKOVIĆ"),
    ],
    ids=["valid-mrz", "printed-latin-beats-mrz", "mrz-check-digit-fails", "no-mrz"],
)
def test_latin_source_priority_in_the_person_key(
    mrz: list[str] | None, fields_surname: str, expected: str
) -> None:
    key = _key(_serbian_page(mrz=mrz, fields_surname=fields_surname))

    assert key.latin_surname == expected
    assert key.latin_given_names == "MARKO"
    assert key.normalized_name == "marko zivkovic"
    assert key.surname == "ЖИВКОВИЋ"


def test_printed_latin_of_the_front_side_beats_the_mrz_of_the_back_side() -> None:
    front = _page(
        language="sr",
        top={"side": "front"},
        surname="Živković",
        given_names="Marko",
        fields=_readings(surname="Živković"),
    )
    back = _page(
        language="sr",
        top={"side": "back"},
        fields=_readings(surname=None),
        mrz=make_mrz(MrzFormat.TD3, **SERBIAN_MRZ),
    )

    key = _key(front, back)

    assert (key.latin_surname, key.latin_given_names) == ("Živković", "Marko")
    assert key.normalized_name == "marko zivkovic"


def test_mrz_given_names_carrying_the_patronymic_are_split_at_a_word_boundary() -> None:
    page = _page(
        surname="ВАСИЛЬЕВ",
        given_names="ДМИТРИЙ",
        other_names="ИВАНОВИЧ",
        document_number="000000031",
        mrz=make_mrz(
            MrzFormat.TD3, state="RUS", name="VASILEV<<DMITRII<IVANOVICH", number="000000031"
        ),
    )

    key = _key(page)

    assert (key.latin_surname, key.latin_given_names, key.latin_other_names) == (
        "VASILEV",
        "DMITRII",
        "IVANOVICH",
    )
    assert key.original_spelling == "ДМИТРИЙ ИВАНОВИЧ ВАСИЛЬЕВ"


def test_arabic_reading_contradicted_by_the_mrz_takes_the_mrz_latin() -> None:
    # 05.3.3: görünen Arap yazım MRZ'yle aynı anahtara inmiyor → MRZ kazanır; Latin MRZ'dir.
    page = _page(
        language="ar",
        top={"script": "arabic"},
        surname="علي",
        given_names="محمد",
        original_script_name="محمد علي",
        document_number="000000041",
        mrz=make_mrz(MrzFormat.TD3, state="EGY", name="ALI<<MUHAMMAD", number="000000041"),
    )

    key = _key(page)

    assert (key.latin_surname, key.latin_given_names) == ("ALI", "MUHAMMAD")
    assert key.original_spelling == "محمد علي"


@pytest.mark.parametrize(
    ("language", "surname", "given_names"),
    [
        ("ar", "علي", "محمد"),
        ("ka", "ბერიძე", "გიორგი"),
        ("zh", "王", "小明"),
        ("kk", "ҚАЙРАТОВ", "ҚАЙРАТ"),
    ],
    ids=["arabic", "georgian", "chinese", "cyrillic-outside-the-table"],
)
def test_name_without_latin_spelling_becomes_a_pending_profile(
    language: str, surname: str, given_names: str
) -> None:
    # Temiz numara (belge numarası okunaklı, MRZ yok) olsa da çalışan otomatik açılmaz.
    page = _page(
        language=language,
        surname=surname,
        given_names=given_names,
        document_number="000000051",
        fields=_readings(document_number="000000051"),
    )

    key = _key(page)

    assert (key.latin_surname, key.latin_given_names) == (None, None)
    assert key.employee_fields()["original_script_name"] == f"{given_names} {surname}"
    resolution = resolve_unmatched(key, NO_MATCH, entry=PASSPORT)
    assert (resolution.rule, resolution.latin_missing) == (UnmatchedRule.PENDING_PROFILE, True)
    assert resolution.reason == PENDING_PROFILE_LATIN_REASON
    profile = resolution.proposed_profile
    assert profile is not None
    assert (profile.given_names, profile.surname) == (None, None)
    assert profile.original_script_name == f"{given_names} {surname}"


def test_latin_reading_is_its_own_latin_spelling() -> None:
    key = PersonKey((), None, None, None, None, True, (), surname="Ornekova", given_names="Тест")

    assert (key.latin_surname, key.latin_given_names) == ("Ornekova", None)
    assert key.original_spelling == "Тест"


def test_mrz_without_given_names_gives_only_the_surname() -> None:
    # MRZ'nin verilen adlar kısmı boş: soyad MRZ'den, ad Kiril çevirisinden.
    page = _page(
        surname="ОРНЕКОВА",
        given_names="ТЕСТ",
        document_number="000000001",
        mrz=make_mrz(MrzFormat.TD3, state="RUS", name="ORNEKOVA", number="000000001"),
    )

    key = _key(page)

    assert (key.latin_surname, key.latin_given_names) == ("ORNEKOVA", "TEST")
