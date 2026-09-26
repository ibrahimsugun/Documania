"""05.4.1 — belge numaraları, normalize ad-soyad, doğum tarihi ve orijinal yazımdan oluşan kişi
anahtarı üretilir (§20.2.1, §20.2.3 koşul 3; K6).

Sayfalar `tests.ai.payloads` sentetik yanıtından ve kayıtlı yanıtlardan kurulur; MRZ satırları
`test_mrz.make_mrz` yazıcısıyla üretilir. Gerçek kişi/belge yok.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.ai import EMPLOYEE_FIELDS, PageAnalysis
from app.ai.schemas import validate_page_analysis
from app.catalog import load_seed_catalog
from app.matching.match import (
    KEY_FIELDS,
    DocumentNumberKey,
    PersonKey,
    build_person_key,
    normalize_document_number,
)
from app.matching.mrz import MrzFormat, apply_mrz_priority
from app.matching.names import TransliteratedName, normalize_name
from app.pipeline.group import GroupingPage, group_across_files, group_file_pages
from tests.ai.payloads import analysis_payload
from tests.matching.test_mrz import PASSPORT, make_mrz

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = ROOT / "tests" / "fixtures" / "ai" / "recordings"
CATALOG = load_seed_catalog()
TODAY = date(2026, 9, 15)

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
# Kartın öteki yüzü gibi: kişi alanlarını bu sayfada okunamadı yazar (03.4).
ILLEGIBLE = {
    name: {"value": None, "legible": False}
    for name in ("surname", "given_names", "date_of_birth", "document_number", "expiry_date")
}


def _readings(**values: str | None) -> dict[str, Any]:
    return {name: {"value": value, "legible": value is not None} for name, value in values.items()}


def _page(
    *,
    fields: dict[str, Any] | None = None,
    top: dict[str, Any] | None = None,
    mrz: list[str] | None = None,
    **person: Any,
) -> PageAnalysis:
    payload = analysis_payload()
    if fields is not None:
        payload["fields"] = fields
    payload.update(top or {})
    payload["person"].update(person, mrz_lines=mrz)
    return PageAnalysis.model_validate(payload)


def _mrz_back(**changes: Any) -> PageAnalysis:
    """Kişiyi yalnız MRZ'sinden veren arka yüz: görünen alanlar boş ve okunamadı."""
    return _page(
        fields=ILLEGIBLE,
        top={"side": "back"},
        mrz=make_mrz(MrzFormat.TD3, **(PASSPORT | changes)),
        **NO_PERSON,
    )


def _key(*pages: PageAnalysis, today: date = TODAY) -> PersonKey:
    return build_person_key(pages, today=today)


def _recording(name: str, index: int = 0) -> PageAnalysis:
    path = RECORDINGS / name / f"{index}.json"
    return validate_page_analysis(path.read_text("utf-8"), known_slugs=CATALOG.slugs())


# --- belge numarası normalizasyonu (§20.2.1) ------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("71 1234567", "711234567"),
        ("71-1234567", "711234567"),
        ("711234567", "711234567"),
        ("ab.12/34 5", "AB12345"),
        (" 71\t12--34 ", "711234"),
        ("-/. ", ""),
    ],
)
def test_document_number_normalization_uppercases_and_drops_separators(
    raw: str, expected: str
) -> None:
    assert normalize_document_number(raw) == expected


# --- kayıtlı yanıtlar ve gruplama çıktısı ---------------------------------------------------------


def test_recorded_cyrillic_passport_gives_the_full_key() -> None:
    key = _key(_recording("s13_cyrillic_name"))

    assert key == PersonKey(
        document_numbers=(DocumentNumberKey("000000013", legible=True),),
        normalized_name="iulia shchelkina testova",
        date_of_birth=date(1992, 3, 15),
        original_script_name=TransliteratedName("Тестова-Щёлкина Юлья", "Testova-Shchelkina Iulia"),
        normalized_original_name="iulia shchelkina testova",
        mrz_allows_clean_document_number=True,
        conflicts=(),
        surname="TESTOVA-SHCHELKINA",
        given_names="IULIA",
        other_names=None,
        nationality="RUS",
        date_of_birth_legible=True,
    )
    assert key.name_keys == ("iulia shchelkina testova",)


def test_front_and_back_of_a_grouped_residence_card_give_one_key() -> None:
    pages = [
        GroupingPage(index, analysis=_recording("serbian_residence_card", index))
        for index in (0, 1)
    ]
    (candidate,) = group_file_pages(7, pages, catalog=CATALOG).candidates
    assert len(candidate.pages) == 2

    key = build_person_key(page.analysis for page in candidate.pages)

    # Arka yüzün `legible: false` okumaları ön yüzün okumalarını silmez.
    assert key == PersonKey(
        document_numbers=(DocumentNumberKey("AB1234567", legible=True),),
        normalized_name="ivan sidorov",
        date_of_birth=date(1985, 5, 5),
        original_script_name=None,
        normalized_original_name=None,
        mrz_allows_clean_document_number=True,
        conflicts=(),
        surname="SIDOROV",
        given_names="IVAN",
        other_names=None,
        nationality="RUS",
        date_of_birth_legible=True,
    )


def test_faces_paired_across_files_give_one_key() -> None:
    groupings = [
        group_file_pages(
            file_id,
            [GroupingPage(0, analysis=_recording("s5_front_back_images", file_id - 1))],
            catalog=CATALOG,
        )
        for file_id in (1, 2)
    ]
    (candidate,) = group_across_files(groupings, catalog=CATALOG).cross_file_candidates

    key = build_person_key(page.analysis for page in candidate.pages)

    assert key.document_numbers == (DocumentNumberKey("000123456", legible=True),)
    assert (key.normalized_name, key.date_of_birth) == ("ivan sidorov", date(1985, 5, 5))
    assert key.conflicts == ()


def test_key_is_the_same_whether_or_not_mrz_priority_was_already_applied() -> None:
    raw = [_page(surname="ORNEKOVA-KAYA", mrz=make_mrz(MrzFormat.TD3, **PASSPORT)), _mrz_back()]
    resolved = [apply_mrz_priority(page, today=TODAY).analysis for page in raw]

    assert resolved != raw
    assert _key(*resolved) == _key(*raw)


# --- ad-soyad ve orijinal yazım -------------------------------------------------------------------


def test_name_key_ignores_case_accents_and_part_order() -> None:
    first = _key(_page(surname="Örnekova", given_names="Test"))
    second = _key(_page(surname="ORNEKOVA", given_names="TEST"))

    assert first.normalized_name == second.normalized_name == "ornekova test"
    assert first.normalized_name == normalize_name("TEST", "ORNEKOVA")


@pytest.mark.parametrize("missing", ["surname", "given_names"])
def test_name_key_needs_both_surname_and_given_names(missing: str) -> None:
    key = _key(_page(fields={}, **{missing: None}))

    assert key.normalized_name is None
    assert key.name_keys == ("ornekova test",)  # yalnız orijinal yazımın anahtarı
    assert key.conflicts == ()


def test_name_parts_may_come_from_different_pages_of_the_candidate() -> None:
    surname_only = _page(fields={}, given_names=None)
    given_only = _page(fields={}, surname=None, given_names="Test")

    assert _key(surname_only, given_only).normalized_name == "ornekova test"


def test_part_a_page_calls_illegible_comes_only_from_the_other_page() -> None:
    front = _page(fields=_readings(given_names=None), given_names="Yanlis")
    back = _page(fields=_readings(surname=None), surname="Yanlis", given_names="Örnek")

    key = _key(front, back)

    assert key.normalized_name == "ornek ornekova"
    assert key.conflicts == ()


def test_other_names_do_not_enter_the_name_key() -> None:
    key = _key(_page(other_names="IVANOVNA"))

    assert key.normalized_name == "ornekova test"


# --- yeni çalışan kaydının okumaları (03.1.3, 05.6) -----------------------------------------------


def test_employee_fields_are_the_first_readings_as_written() -> None:
    page = _page(
        fields=_readings(surname="ORNEKOVA", given_names="TEST"),
        surname="Örnekova",
        given_names="Test",
        other_names="Ivánovna",
    )

    # Diğer isimler de isim anahtarıyla karşılaştırılır: aksan farkı çelişki değildir.
    key = _key(page, _page(fields={}, surname="ORNEKOVA", other_names="IVANOVNA"))

    assert key.employee_fields() == {
        "surname": "Örnekova",
        "given_names": "Test",
        "other_names": "Ivánovna",
        "original_script_name": "Орнекова Тест",
        "date_of_birth": date(1990, 1, 1),
        "nationality": "RUS",
    }
    assert tuple(key.employee_fields()) == EMPLOYEE_FIELDS
    assert key.conflicts == ()


def test_empty_key_has_empty_employee_fields() -> None:
    assert build_person_key([]).employee_fields() == dict.fromkeys(EMPLOYEE_FIELDS)


@pytest.mark.parametrize("field", ["surname", "given_names"])
def test_disagreeing_name_part_has_no_reading(field: str) -> None:
    key = _key(_page(fields={}), _page(fields={}, **{field: "BASKA"}))

    assert key.conflicts == (field,)
    assert getattr(key, field) is None


def test_other_names_and_nationality_that_disagree_are_empty_but_not_conflicts() -> None:
    key = _key(
        _page(fields={}, other_names="IVANOVNA", nationality="RUS"),
        _page(fields={}, other_names="PETROVNA", nationality="SRB"),
    )

    assert (key.other_names, key.nationality, key.conflicts) == (None, None, ())
    assert key.normalized_name == "ornekova test"


@pytest.mark.parametrize(
    ("person", "reading", "expected"),
    [
        ("RUS", {"value": "Russian Federation", "legible": True}, "RUS"),
        (None, {"value": "Russian Federation", "legible": True}, None),
        (None, {"value": "rus", "legible": True}, "RUS"),
        ("RUS", {"value": "rus", "legible": True}, "RUS"),
        ("RUS", {"value": None, "legible": False}, None),
    ],
    ids=[
        "country-name-beside-code",
        "country-name-only",
        "lowercase-code",
        "same-code",
        "illegible",
    ],
)
def test_nationality_is_read_only_as_an_icao_code(
    person: str | None, reading: dict[str, Any], expected: str | None
) -> None:
    key = _key(_page(fields={"nationality": reading}, nationality=person))

    assert (key.nationality, key.conflicts) == (expected, ())


def test_mrz_nationality_wins_over_the_visible_code() -> None:
    own_page = _page(nationality="SRB", mrz=make_mrz(MrzFormat.TD3, **PASSPORT))
    front = _page(top={"side": "front"}, nationality="SRB")

    assert _key(own_page).nationality == "RUS"
    assert _key(front, _mrz_back()).nationality == "RUS"
    assert _key(front, _mrz_back(nationality="D<<")).nationality == "D"


def test_parts_are_normalized_with_their_pages_language() -> None:
    person = {
        "surname": "Григоренко",
        "given_names": "Микола",
        "original_script_name": "Григоренко Микола",
    }

    ukrainian = _key(_page(fields={}, **person, top={"language": "uk"}))
    russian = _key(_page(fields={}, **person, top={"language": "ru"}))

    assert ukrainian.normalized_name == "hryhorenko mykola"
    assert ukrainian.original_script_name == TransliteratedName(
        "Григоренко Микола", "Hryhorenko Mykola"
    )
    assert ukrainian.normalized_original_name == "hryhorenko mykola"
    assert russian.normalized_name == russian.normalized_original_name == "grigorenko mikola"


def test_latin_parts_read_on_a_ukrainian_page_match_the_mrz_spelling() -> None:
    page = _page(fields={}, surname="Григоренко", given_names="Микола", top={"language": "uk"})
    latin = _page(fields={}, surname="HRYHORENKO", given_names="MYKOLA", top={"language": "en"})

    assert _key(page).normalized_name == _key(latin).normalized_name
    assert _key(page, latin).conflicts == ()


def test_arabic_original_script_name_is_kept_with_its_icao_transliteration() -> None:
    key = _key(
        _page(
            fields={},
            surname="ALI",
            given_names="MOHAMMED",
            original_script_name="محمد علي",
            top={"language": "ar", "script": "arabic"},
        )
    )

    assert key.original_script_name == TransliteratedName("محمد علي", "MXHMD ELY")
    assert key.normalized_original_name == "ely mxhmd"
    assert key.name_keys == ("ali mohammed", "ely mxhmd")


def test_non_icao_latin_spelling_and_original_script_are_both_name_keys() -> None:
    key = _key(
        _page(
            fields={},
            surname="VASILIEV",
            given_names="DMITRY",
            original_script_name="Дмитрий Васильев",
        )
    )

    assert key.name_keys == ("dmitry vasiliev", "dmitrii vasilev")
    assert key.conflicts == ()


def test_same_original_spelled_in_another_case_is_one_reading() -> None:
    key = _key(
        _page(original_script_name="Орнекова Тест"),
        _page(original_script_name="ОРНЕКОВА ТЕСТ"),
    )

    assert key.original_script_name == TransliteratedName("Орнекова Тест", "Ornekova Test")
    assert key.conflicts == ()


# --- belge numaraları -----------------------------------------------------------------------------


def test_one_number_written_differently_is_a_single_legible_number() -> None:
    key = _key(
        _page(fields=_readings(document_number="71-1234567"), document_number="71 1234567"),
        _page(fields={}, document_number="711234567"),
    )

    assert key.document_numbers == (DocumentNumberKey("711234567", legible=True),)
    assert key.conflicts == ()


@pytest.mark.parametrize(
    ("pages", "legible"),
    [
        ([{"fields": {}, "document_number": "00 0000001"}], False),
        ([{"fields": _readings(document_number="00 0000001"), "document_number": None}], True),
        (
            [
                {"fields": {}, "document_number": "00 0000001"},
                {"fields": _readings(document_number="000000001"), "document_number": None},
            ],
            True,
        ),
    ],
    ids=["person-only", "fields-only", "legible-on-another-page"],
)
def test_number_is_legible_only_when_a_fields_reading_gives_it(
    pages: list[dict[str, Any]], legible: bool
) -> None:
    key = _key(*(_page(**page) for page in pages))

    assert key.document_numbers == (DocumentNumberKey("000000001", legible=legible),)


def test_different_numbers_are_all_kept_in_page_order_and_reported() -> None:
    key = _key(
        _page(document_number="00 0000002"),
        _page(document_number="00-0000001"),
        _page(document_number="000000002"),
    )

    assert [number.value for number in key.document_numbers] == ["000000002", "000000001"]
    assert key.conflicts == ("document_number",)


def test_person_and_fields_disagreeing_on_one_page_is_a_conflict() -> None:
    key = _key(_page(fields=_readings(document_number="00 0000007"), document_number="00 0000001"))

    assert key.document_numbers == (
        DocumentNumberKey("000000001", legible=False),
        DocumentNumberKey("000000007", legible=True),
    )
    assert key.conflicts == ("document_number",)


# --- tekil alanların çelişkisi, okunamayan ve kullanılamayan okumalar -----------------------------


@pytest.mark.parametrize(
    ("field", "first", "second"),
    [
        ("date_of_birth", "1990-01-01", "1991-01-01"),
        ("surname", "ORNEKOVA", "ORNEKOVA KAYA"),
        ("given_names", "TEST", "TEST ANNA"),
        ("original_script_name", "Орнекова Тест", "Орнекова Анна"),
    ],
)
def test_pages_disagreeing_on_a_single_valued_field_leave_it_empty(
    field: str, first: str, second: str
) -> None:
    key = _key(_page(fields={}, **{field: first}), _page(fields={}, **{field: second}))

    assert key.conflicts == (field,)
    if field == "date_of_birth":
        assert key.date_of_birth is None
    elif field == "original_script_name":
        assert (key.original_script_name, key.normalized_original_name) == (None, None)
        assert key.normalized_name == "ornekova test"
    else:
        assert key.normalized_name is None
        assert key.date_of_birth == date(1990, 1, 1)


def test_several_conflicts_are_reported_in_key_field_order() -> None:
    key = _key(
        _page(fields={}, date_of_birth="1990-01-01", document_number="1", surname="A"),
        _page(fields={}, date_of_birth="1991-01-01", document_number="2", surname="B"),
    )

    assert key.conflicts == ("document_number", "surname", "date_of_birth")
    assert KEY_FIELDS == (
        "document_number",
        "surname",
        "given_names",
        "date_of_birth",
        "original_script_name",
    )


def test_value_the_page_itself_calls_illegible_is_not_used() -> None:
    page = _page(
        fields=_readings(date_of_birth=None, document_number=None),
        date_of_birth="1990-01-01",
        document_number="00 0000001",
    )

    key = _key(page)

    assert (key.date_of_birth, key.document_numbers, key.conflicts) == (None, (), ())
    # Başka sayfanın okuması etkilenmez.
    assert _key(page, _page(fields={}, date_of_birth="1991-01-01")).date_of_birth == date(
        1991, 1, 1
    )


@pytest.mark.parametrize("text", ["01.01.1990", "1990-02-30", "19900101"])
def test_date_text_that_is_not_an_iso_calendar_day_is_not_a_reading(text: str) -> None:
    only_text = _key(_page(fields=_readings(date_of_birth=text), date_of_birth=None))
    with_person = _key(_page(fields=_readings(date_of_birth=text), date_of_birth="1990-01-01"))

    assert (only_text.date_of_birth, only_text.conflicts) == (None, ())
    assert (with_person.date_of_birth, with_person.conflicts) == (date(1990, 1, 1), ())


def test_wordless_name_and_separator_only_number_are_not_readings() -> None:
    key = _key(_page(fields={}, surname="-", original_script_name="…", document_number="- /"))

    assert key.normalized_name is None
    assert (key.original_script_name, key.document_numbers, key.conflicts) == (None, (), ())


@pytest.mark.parametrize("top", [{"is_blank": True}, {"is_readable": False}])
def test_readings_of_a_page_that_calls_itself_blank_or_unreadable_are_not_trusted(
    top: dict[str, Any],
) -> None:
    untrusted = _page(top=top, date_of_birth="1991-01-01", document_number="00 0000009")

    alone = _key(untrusted)
    with_trusted = _key(_page(), untrusted)

    assert alone == PersonKey((), None, None, None, None, True, ())
    assert with_trusted == _key(_page())


# --- MRZ önceliği (K6) ----------------------------------------------------------------------------


def test_mrz_wins_over_the_visible_text_of_its_own_page() -> None:
    page = _page(
        fields=_readings(surname="ORNEKOVA-KAYA", document_number="00 0000009"),
        surname="ORNEKOVA-KAYA",
        document_number="00 0000009",
        date_of_birth="1991-01-01",
        mrz=make_mrz(MrzFormat.TD3, **PASSPORT),
    )

    key = _key(page)

    assert key.document_numbers == (DocumentNumberKey("000000001", legible=True),)
    assert (key.normalized_name, key.date_of_birth) == ("ornekova test", date(1990, 1, 1))
    assert key.conflicts == ()
    assert key.mrz_allows_clean_document_number


def test_mrz_on_the_back_wins_over_the_visible_text_of_the_front() -> None:
    front = _page(
        fields=_readings(given_names="TEST ANNA", document_number="00 0000009"),
        top={"side": "front"},
        given_names="TEST ANNA",
        document_number="00 0000009",
        date_of_birth="1991-01-01",
    )

    key = _key(front, _mrz_back())

    assert key == PersonKey(
        document_numbers=(DocumentNumberKey("000000001", legible=True),),
        normalized_name="ornekova test",
        date_of_birth=date(1990, 1, 1),
        # Orijinal yazım MRZ'de yok: ön yüzden okunur.
        original_script_name=TransliteratedName("Орнекова Тест", "Ornekova Test"),
        normalized_original_name="ornekova test",
        mrz_allows_clean_document_number=True,
        conflicts=(),
        # Adın ve uyruğun görünen yazımı da MRZ'den.
        surname="ORNEKOVA",
        given_names="TEST",
        other_names=None,
        nationality="RUS",
        # Doğum tarihi kontrol hanesi tutan MRZ'den (§20.2.4 koşul 3, 4).
        date_of_birth_legible=True,
    )


# --- doğum tarihinin okunaklılığı (§20.2.4 koşul 3) ---------------------------------------------


def test_birth_date_from_a_legible_field_reading_is_legible() -> None:
    key = _key(_page(fields=_readings(date_of_birth="1990-01-01")))

    assert (key.date_of_birth, key.date_of_birth_legible) == (date(1990, 1, 1), True)


def test_birth_date_read_only_into_person_is_not_legible() -> None:
    # Yalnız `person`'dan okunan tarih alan okunaklılığı taşımaz (belge numarasındaki gibi):
    # eşleştirme (satır 3) onu kullanır, ad + doğum tarihiyle çalışan açılmaz.
    key = _key(_page())

    assert (key.date_of_birth, key.date_of_birth_legible) == (date(1990, 1, 1), False)


def test_birth_date_from_the_mrz_alone_is_legible() -> None:
    # Görünen alan okuması yok; tarih kontrol hanesi tutan MRZ'den gelir.
    page = _page(fields={}, mrz=make_mrz(MrzFormat.TD3, **PASSPORT), **NO_PERSON)

    key = _key(page)

    assert (key.date_of_birth, key.date_of_birth_legible) == (date(1990, 1, 1), True)


def test_birth_date_whose_mrz_check_digit_fails_is_not_taken_from_the_mrz() -> None:
    mrz = make_mrz(MrzFormat.TD3, **PASSPORT, checks={"date_of_birth": "0"})
    page = _page(fields={}, mrz=mrz, **NO_PERSON)

    key = _key(page)

    assert (key.date_of_birth, key.date_of_birth_legible) == (None, False)


def test_birth_date_the_page_calls_illegible_is_not_in_the_key() -> None:
    key = _key(_page(fields=_readings(date_of_birth=None)))

    assert (key.date_of_birth, key.date_of_birth_legible) == (None, False)


def test_conflicting_birth_dates_are_not_legible() -> None:
    first = _page(fields=_readings(date_of_birth="1990-01-01"))
    second = _page(fields=_readings(date_of_birth="1991-01-01"), date_of_birth="1991-01-01")

    key = _key(first, second)

    assert "date_of_birth" in key.conflicts
    assert (key.date_of_birth, key.date_of_birth_legible) == (None, False)


def test_one_legible_reading_makes_the_single_birth_date_legible() -> None:
    # Aynı tarih bir sayfada yalnız `person`'da, ötekinde okunaklı alanda: tek değer, okunaklı.
    key = _key(_page(), _page(fields=_readings(date_of_birth="1990-01-01")))

    assert (key.date_of_birth, key.date_of_birth_legible) == (date(1990, 1, 1), True)


def test_field_the_mrz_does_not_carry_is_read_from_every_page() -> None:
    front = _page(fields={}, surname="ORNEKOVA", given_names="TEST", document_number="00 0000001")
    back = _mrz_back(name="ORNEKOVA", checks={"document_number": "0"})

    key = _key(front, back)

    # MRZ'de verilen ad yok, numarasının hanesi tutmuyor: ikisi ön yüzden okunur.
    assert key.normalized_name == "ornekova test"
    assert key.document_numbers == (DocumentNumberKey("000000001", legible=False),)
    assert key.conflicts == ()
    # MRZ numarayı doğrulayamadığı için temiz numara çıkmaz (§20.2.3 koşul 3).
    assert not key.mrz_allows_clean_document_number


def test_failing_composite_keeps_the_numbers_but_blocks_a_clean_document_number() -> None:
    key = _key(_mrz_back(composite="0"))

    assert key.document_numbers == (DocumentNumberKey("000000001", legible=True),)
    assert not key.mrz_allows_clean_document_number


def test_two_mrz_pages_that_disagree_are_a_conflict() -> None:
    key = _key(_mrz_back(), _mrz_back(number="000000002", birth="910101"))

    assert [number.value for number in key.document_numbers] == ["000000001", "000000002"]
    assert key.date_of_birth is None
    assert key.conflicts == ("document_number", "date_of_birth")


def test_unusable_mrz_blocks_a_clean_number_and_the_visible_text_is_used() -> None:
    invalid = _page(mrz=["p<rusÖRNEKOVA<<TEST" + "<" * 25, "0" * 44])
    unreadable = _page(top={"is_readable": False}, mrz=make_mrz(MrzFormat.TD3, **PASSPORT))

    key = _key(invalid)

    assert key.document_numbers == (DocumentNumberKey("000000001", legible=False),)
    assert key.normalized_name == "ornekova test"
    assert not key.mrz_allows_clean_document_number
    assert not _key(_page(), unreadable).mrz_allows_clean_document_number


def test_unrecognized_mrz_does_not_block_a_clean_number() -> None:
    key = _key(_page(mrz=["NOT AN MRZ"]))

    assert key.document_numbers == (DocumentNumberKey("000000001", legible=False),)
    assert key.mrz_allows_clean_document_number


@pytest.mark.parametrize(
    ("today", "expected"), [(TODAY, date(2010, 1, 1)), (date(2009, 12, 31), date(1910, 1, 1))]
)
def test_mrz_birth_century_follows_the_given_day(today: date, expected: date) -> None:
    key = _key(_mrz_back(birth="100101"), today=today)

    assert key.date_of_birth == expected


# --- sözleşme -------------------------------------------------------------------------------------


def test_empty_candidate_gives_an_empty_key() -> None:
    assert build_person_key([]) == PersonKey((), None, None, None, None, True, ())


def test_key_is_deterministic_and_frozen() -> None:
    pages = [_page(), _mrz_back()]

    key = build_person_key(iter(pages), today=TODAY)

    assert key == build_person_key(pages, today=TODAY)
    assert hash(key) == hash(build_person_key(pages, today=TODAY))
    with pytest.raises(dataclasses.FrozenInstanceError):
        key.normalized_name = "baska"  # type: ignore[misc]
