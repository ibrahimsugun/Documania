"""05.3.1 — TD1, TD2, TD3 biçimleri ayrıştırılır; 05.3.2 — kontrol hanesi tutmayan alan geçersiz,
bileşik hanesi tutmayan MRZ şüphelidir; 05.3.3 — görünen metinle çelişkide MRZ kazanır ve çelişki
nota yazılır (§20.1).

MRZ satırları ICAO Doc 9303'ün kurgusal "Utopia" (`UTO`) örnekleri ya da bu dosyadaki yazıcıyla
üretilmiş sentetik satırlardır; gerçek kişi/belge yok. Yazıcı alanları anlamlarıyla birleştirir
(belge no + hane + doğum + hane …), ayrıştırıcı konumlardan okur: iki taraf aynı haneyi bulmalıdır
(§20.1.5). Beklenen konumlar §20.1.3 ve §20.1.5 tablolarından elle yazılmıştır.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.ai import PageAnalysis
from app.ai.schemas import validate_page_analysis
from app.catalog import load_seed_catalog
from app.matching.mrz import (
    COMPOSITE,
    FILLER,
    InvalidMrzError,
    Mrz,
    MrzFormat,
    MrzStatus,
    apply_mrz_priority,
    compute_check_digit,
    detect_format,
    parse_mrz,
)
from app.pipeline.group import CandidatePage, DocumentCandidate
from app.pipeline.legibility import IllegibleRequiredFields, check_legibility
from tests.ai.payloads import analysis_payload

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = ROOT / "tests" / "fixtures" / "ai" / "recordings"
CATALOG = load_seed_catalog()
TODAY = date(2026, 9, 15)

# ICAO Doc 9303 Bölüm 4, 5 ve 6'daki kurgusal örnek belgeler.
SPECIMEN_TD3 = [
    "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
    "L898902C36UTO7408122F1204159ZE184226B<<<<<10",
]
SPECIMEN_TD2 = [
    "I<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<",
    "D231458907UTO7408122F1204159<<<<<<<6",
]
SPECIMEN_TD1 = [
    "I<UTOD231458907<<<<<<<<<<<<<<<",
    "7408122F1204159UTO<<<<<<<<<<<6",
    "ERIKSSON<<ANNA<MARIA<<<<<<<<<<",
]

# (satır, ilk konum, son konum), 1 tabanlı ve dahil. Alanın kendi hanesi aralığa dahildir; bileşik
# aralığa bileşik hanenin kendisi de eklenmiştir (onu bozmak da bileşik haneyi tutmaz yapar).
CHECK_SPANS: dict[MrzFormat, dict[str, list[tuple[int, int, int]]]] = {
    MrzFormat.TD3: {
        "document_number": [(2, 1, 10)],
        "date_of_birth": [(2, 14, 20)],
        "expiry_date": [(2, 22, 28)],
        "optional_data": [(2, 29, 43)],
        COMPOSITE: [(2, 1, 10), (2, 14, 20), (2, 22, 43), (2, 44, 44)],
    },
    MrzFormat.TD2: {
        "document_number": [(2, 1, 10)],
        "date_of_birth": [(2, 14, 20)],
        "expiry_date": [(2, 22, 28)],
        COMPOSITE: [(2, 1, 10), (2, 14, 20), (2, 22, 35), (2, 36, 36)],
    },
    MrzFormat.TD1: {
        "document_number": [(1, 6, 15)],
        "date_of_birth": [(2, 1, 7)],
        "expiry_date": [(2, 9, 15)],
        COMPOSITE: [(1, 6, 30), (2, 1, 7), (2, 9, 15), (2, 19, 29), (2, 30, 30)],
    },
}


def _pad(value: str, width: int) -> str:
    assert len(value) <= width, (value, width)
    return value + FILLER * (width - len(value))


def _with_check(value: str, width: int, check: str | None) -> str:
    padded = _pad(value, width)
    return padded + (str(compute_check_digit(padded)) if check is None else check)


def make_mrz(
    fmt: MrzFormat,
    *,
    code: str = "P",
    state: str = "UTO",
    name: str = "ERIKSSON<<ANNA<MARIA",
    number: str = "L898902C3",
    nationality: str = "UTO",
    birth: str = "740812",
    sex: str = "F",
    expiry: str = "120415",
    optional: str = "",
    optional2: str = "",
    checks: dict[str, str] | None = None,
    composite: str | None = None,
) -> list[str]:
    """Alanları ICAO yapısıyla birleştirir; `checks`/`composite` verilen hane aynen yazılır."""
    checks = checks or {}
    number_part = _with_check(number, 9, checks.get("document_number"))
    birth_part = _with_check(birth, 6, checks.get("date_of_birth"))
    expiry_part = _with_check(expiry, 6, checks.get("expiry_date"))
    head = _pad(code, 2) + _pad(state, 3)
    if fmt is MrzFormat.TD3:
        optional_part = _with_check(optional, 14, checks.get("optional_data"))
        covered = number_part + birth_part + expiry_part + optional_part
        body = number_part + _pad(nationality, 3) + birth_part + sex + expiry_part + optional_part
        lines = [head + _pad(name, 39), body]
    elif fmt is MrzFormat.TD2:
        optional_part = _pad(optional, 7)
        covered = number_part + birth_part + expiry_part + optional_part
        body = number_part + _pad(nationality, 3) + birth_part + sex + expiry_part + optional_part
        lines = [head + _pad(name, 31), body]
    else:
        first, second = _pad(optional, 15), _pad(optional2, 11)
        covered = number_part + first + birth_part + expiry_part + second
        body = birth_part + sex + expiry_part + _pad(nationality, 3) + second
        lines = [head + number_part + first, body, _pad(name, 30)]
    lines[1] += str(compute_check_digit(covered)) if composite is None else composite
    return lines


def _mutated(lines: list[str], line: int, position: int) -> list[str]:
    """Konumdaki karakteri değeri bir farklı izinli karaktere çevirir (hane toplamı değişir)."""
    char = lines[line - 1][position - 1]
    replacement = {"<": "1", "9": "8", "Z": "Y"}.get(char) or chr(ord(char) + 1)
    changed = list(lines)
    row = changed[line - 1]
    changed[line - 1] = row[: position - 1] + replacement + row[position:]
    return changed


def _parse(lines: list[str], *, today: date = TODAY) -> Mrz:
    mrz = parse_mrz(lines, today=today)
    assert mrz is not None
    return mrz


# --- §20.1.4 kontrol hanesi algoritması --------------------------------------------------------


@pytest.mark.parametrize(
    ("characters", "expected"),
    [("L898902C3", 6), ("690806", 1), ("940623", 6)],
    ids=["belge-numarasi", "dogum-tarihi", "son-gecerlilik"],
)
def test_check_digit_matches_the_mandatory_icao_examples(characters: str, expected: int) -> None:
    assert compute_check_digit(characters) == expected


@pytest.mark.parametrize(
    ("characters", "expected"),
    [
        ("", 0),
        ("<", 0),
        ("<<<<<<<<<", 0),
        ("1", 7),  # ağırlık 7
        ("01", 3),  # ağırlık 3
        ("001", 1),  # ağırlık 1
        ("0001", 7),  # dizi tekrar eder
        ("A", 0),  # 10 × 7 = 70
        ("B", 7),  # 11 × 7 = 77
        ("Z", 5),  # 35 × 7 = 245
        ("<Z", 5),  # 35 × 3 = 105
        ("<<Z", 5),  # 35 × 1 = 35
        ("<<<C", 4),  # 12 × 7 = 84
        ("L<", 7),  # 21 × 7 = 147; `<` sıfır
    ],
)
def test_check_digit_uses_character_values_and_repeating_weights(
    characters: str, expected: int
) -> None:
    assert compute_check_digit(characters) == expected


@pytest.mark.parametrize("characters", ["a", " ", "Ö", "-", "٣"])
def test_check_digit_rejects_characters_outside_the_mrz_set(characters: str) -> None:
    with pytest.raises(ValueError, match="A-Z, 0-9 veya <"):
        compute_check_digit(f"12{characters}")


# --- §20.1.1 biçimler ve §20.1.3 alan yerleşimi -----------------------------------------------


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (
            SPECIMEN_TD3,
            Mrz(
                format=MrzFormat.TD3,
                document_code="P",
                issuing_state="UTO",
                surname="ERIKSSON",
                given_names="ANNA MARIA",
                document_number="L898902C3",
                nationality="UTO",
                date_of_birth=date(1974, 8, 12),
                sex="F",
                expiry_date=date(2012, 4, 15),
                optional_data=("ZE184226B",),
                failed_checks=(),
                illegible_fields=(),
            ),
        ),
        (
            SPECIMEN_TD2,
            Mrz(
                format=MrzFormat.TD2,
                document_code="I",
                issuing_state="UTO",
                surname="ERIKSSON",
                given_names="ANNA MARIA",
                document_number="D23145890",
                nationality="UTO",
                date_of_birth=date(1974, 8, 12),
                sex="F",
                expiry_date=date(2012, 4, 15),
                optional_data=("",),
                failed_checks=(),
                illegible_fields=(),
            ),
        ),
        (
            SPECIMEN_TD1,
            Mrz(
                format=MrzFormat.TD1,
                document_code="I",
                issuing_state="UTO",
                surname="ERIKSSON",
                given_names="ANNA MARIA",
                document_number="D23145890",
                nationality="UTO",
                date_of_birth=date(1974, 8, 12),
                sex="F",
                expiry_date=date(2012, 4, 15),
                optional_data=("", ""),
                failed_checks=(),
                illegible_fields=(),
            ),
        ),
    ],
    ids=["TD3", "TD2", "TD1"],
)
def test_icao_specimens_are_parsed_in_all_three_formats(lines: list[str], expected: Mrz) -> None:
    mrz = _parse(lines)
    assert mrz == expected
    assert mrz.composite_valid


@pytest.mark.parametrize(
    ("fmt", "specimen", "changes"),
    [
        (MrzFormat.TD3, SPECIMEN_TD3, {"optional": "ZE184226B"}),
        (MrzFormat.TD2, SPECIMEN_TD2, {"code": "I", "number": "D23145890"}),
        (MrzFormat.TD1, SPECIMEN_TD1, {"code": "I", "number": "D23145890"}),
    ],
    ids=["TD3", "TD2", "TD1"],
)
def test_writer_reproduces_the_icao_specimens(
    fmt: MrzFormat, specimen: list[str], changes: dict[str, str]
) -> None:
    # Yazıcı ICAO örneğini birebir üretiyorsa ondan üretilen satırlar ayrıştırıcı için bağımsız bir
    # sınamadır: bileşik haneyi konumlardan değil alanların anlamından hesaplar.
    assert make_mrz(fmt, **changes) == specimen


@pytest.mark.parametrize("fmt", list(MrzFormat))
def test_generated_mrz_round_trips_every_field(fmt: MrzFormat) -> None:
    optional = {"TD3": "PN1234567890<1", "TD2": "X12<7", "TD1": "AB<12<<9"}[fmt]
    lines = make_mrz(
        fmt,
        code="AC",
        state="D",
        name="ORNEK<SOYAD<<TEST<IKINCI<AD",
        number="Z9<",
        nationality="D",
        birth="051130",
        sex="M",
        expiry="310228",
        optional=optional,
        optional2="PERS0NAL",
    )

    mrz = _parse(lines)

    assert mrz.format is fmt
    assert (mrz.document_code, mrz.issuing_state) == ("AC", "D")
    assert (mrz.surname, mrz.given_names) == ("ORNEK SOYAD", "TEST IKINCI AD")
    assert (mrz.document_number, mrz.nationality, mrz.sex) == ("Z9", "D", "M")
    assert (mrz.date_of_birth, mrz.expiry_date) == (date(2005, 11, 30), date(2031, 2, 28))
    expected_optional = {
        "TD3": ("PN1234567890<1",),
        "TD2": ("X12<7",),
        "TD1": ("AB<12<<9", "PERS0NAL"),
    }[fmt]
    assert mrz.optional_data == expected_optional
    assert (mrz.failed_checks, mrz.illegible_fields) == ((), ())


@pytest.mark.parametrize(
    ("fmt", "lines"),
    [
        (MrzFormat.TD3, SPECIMEN_TD3),
        (MrzFormat.TD2, SPECIMEN_TD2),
        (MrzFormat.TD1, SPECIMEN_TD1),
        (MrzFormat.TD3, make_mrz(MrzFormat.TD3)),  # isteğe bağlı veri tümüyle dolgu, hanesi 0
    ],
    ids=["TD3", "TD2", "TD1", "TD3-bos-istege-bagli"],
)
def test_every_position_is_covered_by_exactly_the_check_digits_in_the_table(
    fmt: MrzFormat, lines: list[str]
) -> None:
    # Her konumdaki tek karakter bozulur: yalnız o konumu kapsayan haneler tutmaz. Bileşik hanenin
    # bitişik olmayan aralıkları (cinsiyet, uyruk, isim, veren devlet dışarıda) burada sabitlenir.
    spans = CHECK_SPANS[fmt]
    for line_number, line in enumerate(lines, start=1):
        for position in range(1, len(line) + 1):
            expected = tuple(
                name
                for name, ranges in spans.items()
                if any(
                    row == line_number and start <= position <= end for row, start, end in ranges
                )
            )
            mrz = _parse(_mutated(lines, line_number, position))
            assert mrz.failed_checks == expected, (line_number, position)


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (SPECIMEN_TD3, MrzFormat.TD3),
        (SPECIMEN_TD2, MrzFormat.TD2),
        (SPECIMEN_TD1, MrzFormat.TD1),
        ([], None),
        (SPECIMEN_TD3[:1], None),
        (SPECIMEN_TD1[:2], None),  # 2 × 30
        ([*SPECIMEN_TD1, SPECIMEN_TD1[0]], None),  # 4 × 30
        ([*SPECIMEN_TD3, SPECIMEN_TD3[1]], None),  # 3 × 44
        ([SPECIMEN_TD3[0], SPECIMEN_TD3[1][:-1]], None),  # 44 + 43
        ([SPECIMEN_TD3[0][:-1], SPECIMEN_TD3[1][:-1]], None),  # 2 × 43
        ([SPECIMEN_TD3[0] + " ", SPECIMEN_TD3[1] + " "], None),  # 2 × 45
        ([SPECIMEN_TD2[0], SPECIMEN_TD3[1]], None),  # 36 + 44
        ([SPECIMEN_TD1[0], SPECIMEN_TD1[1], SPECIMEN_TD2[0]], None),  # 30 + 30 + 36
    ],
)
def test_format_is_decided_by_line_count_and_length_only(
    lines: list[str], expected: MrzFormat | None
) -> None:
    assert detect_format(lines) is expected
    if expected is None:
        assert parse_mrz(lines, today=TODAY) is None


# --- §20.1.2 karakter kümesi ------------------------------------------------------------------


def test_lowercase_letters_are_uppercased_before_reading() -> None:
    lowered = [line.lower() for line in SPECIMEN_TD3]
    assert _parse(lowered) == _parse(SPECIMEN_TD3)


@pytest.mark.parametrize(
    "character",
    [" ", "«", "-", ".", "Ö", "ı", "ß", "А", "Ａ", "٣", "\t"],
    ids=[
        "bosluk",
        "acili-tirnak",
        "tire",
        "nokta",
        "o-umlaut",
        "noktasiz-i",
        "eszett",
        "kiril-a",
        "tam-genislik-a",
        "arap-rakami",
        "sekme",
    ],
)
def test_character_outside_the_set_after_uppercasing_makes_the_mrz_invalid(character: str) -> None:
    line = SPECIMEN_TD3[1]
    lines = [SPECIMEN_TD3[0], line[:20] + character + line[21:]]

    with pytest.raises(InvalidMrzError) as raised:
        parse_mrz(lines, today=TODAY)

    message = str(raised.value)
    assert "2. satır" in message
    assert "L898902C3" not in message and "ERIKSSON" not in message


# --- isim alanı ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "surname", "given_names"),
    [
        ("VASILIEV<<DMITRY<IVANOVICH", "VASILIEV", "DMITRY IVANOVICH"),  # §20.1.2 örneği
        ("ERIKSSON", "ERIKSSON", None),  # `<<` yok: yalnız birincil tanımlayıcı
        ("VAN<DER<BERG<<ANNA", "VAN DER BERG", "ANNA"),
        ("<<ANNA", None, "ANNA"),
        ("ORNEK<<TEST<<IKINCI", "ORNEK", "TEST IKINCI"),
        ("ORNEK<<<TEST", "ORNEK", "TEST"),
        ("", None, None),
    ],
)
def test_name_field_splits_primary_and_secondary_identifiers(
    name: str, surname: str | None, given_names: str | None
) -> None:
    mrz = _parse(make_mrz(MrzFormat.TD3, name=name))

    assert (mrz.surname, mrz.given_names) == (surname, given_names)
    assert mrz.illegible_fields == ()


@pytest.mark.parametrize("fmt", list(MrzFormat))
def test_name_field_with_a_digit_is_illegible_but_the_rest_is_kept(fmt: MrzFormat) -> None:
    mrz = _parse(make_mrz(fmt, name="ER1KSSON<<ANNA"))

    assert (mrz.surname, mrz.given_names) == (None, None)
    assert mrz.illegible_fields == ("surname", "given_names")
    assert mrz.document_number == "L898902C3" and mrz.composite_valid


def test_full_width_name_field_is_read_to_its_last_character() -> None:
    name = "ABCDEFGHIJKLMNOPQRS<<TUVWXYZABCDEFGHIJK"  # 39 karakter, dolgu yok
    mrz = _parse(make_mrz(MrzFormat.TD3, name=name))
    assert (mrz.surname, mrz.given_names) == ("ABCDEFGHIJKLMNOPQRS", "TUVWXYZABCDEFGHIJK")


# --- §20.1.7 kontrol hanesi tutmayan alan ve bileşik hane ----------------------------------------


@pytest.mark.parametrize("fmt", list(MrzFormat))
@pytest.mark.parametrize(
    ("field", "check"),
    [
        ("document_number", "5"),
        ("date_of_birth", "7"),
        ("expiry_date", "0"),
        ("document_number", "<"),
    ],
)
def test_failing_field_check_digit_invalidates_only_that_field(
    fmt: MrzFormat, field: str, check: str
) -> None:
    # Bileşik hane bozuk haneyle yeniden hesaplanır: yalnız alan hanesi tutmuyor.
    mrz = _parse(make_mrz(fmt, checks={field: check}))

    assert mrz.failed_checks == (field,)
    assert mrz.illegible_fields == (field,)
    assert getattr(mrz, field) is None
    assert mrz.composite_valid
    kept = {"document_number", "date_of_birth", "expiry_date"} - {field}
    assert all(getattr(mrz, name) is not None for name in kept)
    assert (mrz.surname, mrz.given_names, mrz.nationality) == ("ERIKSSON", "ANNA MARIA", "UTO")


@pytest.mark.parametrize("fmt", list(MrzFormat))
@pytest.mark.parametrize("composite", ["<", "A"])
def test_failing_composite_check_digit_keeps_fields_but_marks_the_mrz_suspicious(
    fmt: MrzFormat, composite: str
) -> None:
    correct = _parse(make_mrz(fmt))
    wrong = next(digit for digit in "0123456789" if make_mrz(fmt, composite=digit) != make_mrz(fmt))

    for value in (composite, wrong):
        mrz = _parse(make_mrz(fmt, composite=value))
        assert mrz.failed_checks == (COMPOSITE,)
        assert not mrz.composite_valid
        assert mrz.illegible_fields == ()
        assert (mrz.document_number, mrz.date_of_birth) == (
            correct.document_number,
            correct.date_of_birth,
        )


@pytest.mark.parametrize(
    ("optional", "check", "valid"),
    [
        ("", "<", True),  # tümüyle dolgu: `<` geçerli
        ("", "0", True),  # tümüyle dolgu: `0` geçerli
        ("", "5", False),
        ("ZE184226B", "1", True),
        ("ZE184226B", "<", False),  # dolgu olmayan verinin hanesi rakam olmalı
        ("ZE184226B", "2", False),
    ],
)
def test_td3_optional_data_check_digit(optional: str, check: str, valid: bool) -> None:
    mrz = _parse(make_mrz(MrzFormat.TD3, optional=optional, checks={"optional_data": check}))

    assert mrz.composite_valid
    if valid:
        assert mrz.failed_checks == () and mrz.optional_data == (optional,)
    else:
        assert mrz.failed_checks == ("optional_data",)
        assert mrz.illegible_fields == ("optional_data",)
        assert mrz.optional_data is None
        assert mrz.document_number == "L898902C3"


def test_empty_document_number_is_illegible_even_though_its_check_digit_holds() -> None:
    mrz = _parse(make_mrz(MrzFormat.TD1, number=""))
    assert mrz.failed_checks == ()
    assert mrz.document_number is None
    assert mrz.illegible_fields == ("document_number",)


# --- §20.1.6 tarih ve yüzyıl kuralı -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("991231", date(2099, 12, 31)),
        ("000101", date(2000, 1, 1)),
        ("260914", date(2026, 9, 14)),
        ("500615", date(2050, 6, 15)),
    ],
)
def test_expiry_date_is_always_in_the_2000s(raw: str, expected: date) -> None:
    assert _parse(make_mrz(MrzFormat.TD3, expiry=raw)).expiry_date == expected


@pytest.mark.parametrize(
    ("raw", "today", "expected"),
    [
        ("260915", TODAY, date(2026, 9, 15)),  # bugün gelecek değildir
        ("260916", TODAY, date(1926, 9, 16)),
        ("900101", TODAY, date(1990, 1, 1)),
        ("051130", TODAY, date(2005, 11, 30)),
        ("000229", TODAY, date(2000, 2, 29)),
        ("000229", date(1999, 12, 31), None),  # 2000 gelecekte, 1900 artık yıl değil
        ("991231", date(1999, 12, 31), date(1999, 12, 31)),
    ],
)
def test_birth_date_tries_2000s_first_and_falls_back_to_1900s_when_in_the_future(
    raw: str, today: date, expected: date | None
) -> None:
    mrz = _parse(make_mrz(MrzFormat.TD1, birth=raw), today=today)
    assert mrz.date_of_birth == expected
    assert ("date_of_birth" in mrz.illegible_fields) is (expected is None)


def test_birth_date_century_defaults_to_the_current_day() -> None:
    mrz = parse_mrz(make_mrz(MrzFormat.TD3, birth="900101"))
    assert mrz is not None and mrz.date_of_birth == date(1990, 1, 1)


@pytest.mark.parametrize("field", ["birth", "expiry"])
@pytest.mark.parametrize(
    "raw", ["901301", "900001", "900100", "900230", "010229", "900431", "9A0101", "<<<<<<"]
)
def test_calendar_invalid_date_is_illegible_but_the_mrz_is_not_rejected(
    field: str, raw: str
) -> None:
    mrz = _parse(make_mrz(MrzFormat.TD3, **{field: raw}))

    name = {"birth": "date_of_birth", "expiry": "expiry_date"}[field]
    assert getattr(mrz, name) is None
    assert mrz.illegible_fields == (name,)
    assert mrz.failed_checks == ()
    assert mrz.document_number == "L898902C3" and mrz.surname == "ERIKSSON"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("UTO", "UTO"), ("D", "D"), ("GB", "GB"), ("U1O", None), ("", None), ("<UT", None)],
)
def test_nationality_is_an_icao_code_of_one_to_three_letters(
    raw: str, expected: str | None
) -> None:
    mrz = _parse(make_mrz(MrzFormat.TD2, nationality=raw))
    assert mrz.nationality == expected
    assert ("nationality" in mrz.illegible_fields) is (expected is None)


@pytest.mark.parametrize(("raw", "expected"), [("M", "M"), ("F", "F"), ("<", None)])
def test_sex(raw: str, expected: str | None) -> None:
    assert _parse(make_mrz(MrzFormat.TD1, sex=raw)).sex == expected


# --- 05.3.3 MRZ önceliği ------------------------------------------------------------------------

PASSPORT = {
    "code": "P",
    "state": "RUS",
    "name": "ORNEKOVA<<TEST",
    "number": "000000001",
    "nationality": "RUS",
    "birth": "900101",
    "sex": "F",
    "expiry": "300101",
}
VISIBLE = {
    "surname": "ORNEKOVA",
    "given_names": "TEST",
    "date_of_birth": "1990-01-01",
    "document_number": "00 0000001",
    "expiry_date": "2030-01-01",
}
PERSON_FIELDS = ("surname", "given_names", "document_number", "nationality", "date_of_birth")


def _passport_mrz(**changes: Any) -> list[str]:
    return make_mrz(MrzFormat.TD3, **(PASSPORT | changes))


def _readings(**changes: str | None) -> dict[str, Any]:
    return {
        name: {"value": value, "legible": value is not None}
        for name, value in (VISIBLE | changes).items()
    }


def _page(
    mrz: list[str] | None,
    *,
    fields: dict[str, Any] | None = None,
    notes: str | None = None,
    top: dict[str, Any] | None = None,
    **person: Any,
) -> PageAnalysis:
    payload = analysis_payload(fields=_readings() if fields is None else fields, notes=notes)
    payload.update(top or {})
    payload["person"].update(person, mrz_lines=mrz)
    return PageAnalysis.model_validate(payload)


def _resolve(page: PageAnalysis, *, today: date = TODAY) -> Any:
    return apply_mrz_priority(page, today=today)


def test_page_without_mrz_is_left_untouched() -> None:
    page = _page(None, document_number="00 0000009")

    resolution = _resolve(page)

    assert resolution.status is MrzStatus.ABSENT
    assert resolution.analysis is page
    assert (resolution.mrz, resolution.conflicts) == (None, ())
    assert resolution.allows_clean_document_number


def test_agreeing_visible_text_is_kept_as_written() -> None:
    page = _page(_passport_mrz())

    resolution = _resolve(page)

    assert resolution.status is MrzStatus.READ
    assert resolution.analysis == page
    assert resolution.analysis.person.document_number == "00 0000001"
    assert resolution.analysis.notes is None
    assert resolution.conflicts == ()
    assert resolution.mrz is not None and resolution.mrz.document_number == "000000001"
    assert resolution.allows_clean_document_number


@pytest.mark.parametrize(
    ("field", "visible", "mrz_text"),
    [
        ("surname", "ORNEKOVAA", "ORNEKOVA"),
        ("surname", "-", "ORNEKOVA"),  # kelimesiz görünen okuma MRZ'yle aynı olamaz
        ("given_names", "TESTA", "TEST"),
        ("document_number", "00 0000002", "000000001"),
        ("date_of_birth", "1990-01-02", "1990-01-01"),
        ("nationality", "SRB", "RUS"),
        ("expiry_date", "2030-01-02", "2030-01-01"),
    ],
)
def test_conflicting_visible_text_loses_to_the_mrz_and_the_conflict_is_noted(
    field: str, visible: str, mrz_text: str
) -> None:
    person = {field: visible} if field in PERSON_FIELDS else {}
    fields = _readings(**{field: visible}) if field in VISIBLE else None
    page = _page(_passport_mrz(), fields=fields, notes="Alt kenar hafif bulanık.", **person)

    resolution = _resolve(page)
    resolved = resolution.analysis

    assert resolution.conflicts == (field,)
    if field in PERSON_FIELDS:
        expected = date.fromisoformat(mrz_text) if field == "date_of_birth" else mrz_text
        assert getattr(resolved.person, field) == expected
    if field in VISIBLE:
        assert resolved.fields[field].model_dump() == {"value": mrz_text, "legible": True}
    assert resolved.notes == (
        f"Alt kenar hafif bulanık. MRZ ile görünen metin çelişiyor, MRZ değeri kullanıldı: {field}."
    )
    assert visible not in resolved.notes and mrz_text not in resolved.notes
    untouched = page.model_dump(exclude={"person", "fields", "notes"})
    assert resolved.model_dump(exclude={"person", "fields", "notes"}) == untouched
    assert resolution.allows_clean_document_number


def test_one_conflicting_reading_overwrites_both_places() -> None:
    # `person` MRZ'yle aynı, türün okuması farklı: iki yer de MRZ değerini alır.
    page = _page(_passport_mrz(), fields=_readings(document_number="00 0000002"))

    resolved = _resolve(page).analysis

    assert resolved.person.document_number == "000000001"
    assert resolved.fields["document_number"].value == "000000001"


def test_several_conflicts_are_noted_in_mrz_field_order() -> None:
    page = _page(
        _passport_mrz(),
        fields=_readings(expiry_date="2031-01-01", surname="PETROVA"),
        surname="PETROVA",
        document_number="11 1111111",
        nationality="SRB",
    )

    resolution = _resolve(page)

    assert resolution.conflicts == ("surname", "document_number", "nationality", "expiry_date")
    assert resolution.analysis.notes == (
        "MRZ ile görünen metin çelişiyor, MRZ değeri kullanıldı: "
        "surname, document_number, nationality, expiry_date."
    )


@pytest.mark.parametrize(
    ("field", "visible"),
    [
        ("document_number", "00-0000001"),
        ("document_number", "00.000.0001"),
        ("document_number", "00/0000001"),
        ("document_number", "000000001"),
        ("surname", "Ornekova"),
        ("surname", "ÖRNEKOVA"),
        ("surname", "  ORNEKOVA "),
        ("given_names", "test"),
    ],
)
def test_spelling_differences_that_normalize_away_are_not_conflicts(
    field: str, visible: str
) -> None:
    page = _page(_passport_mrz(), fields=_readings(**{field: visible}), **{field: visible})

    resolution = _resolve(page)

    assert resolution.conflicts == ()
    assert resolution.analysis == page


@pytest.mark.parametrize(
    ("mrz_name", "given_names", "other_names", "conflict", "resolved_given"),
    [
        ("VASILEV<<DMITRII<IVANOVICH", "DMITRII", "IVANOVICH", False, "DMITRII"),
        ("VASILEV<<DMITRII", "DMITRII", "IVANOVICH", False, "DMITRII"),
        ("VASILEV<<DMITRII<IVANOVICH", "DMITRII IVANOVICH", None, False, "DMITRII IVANOVICH"),
        ("VASILEV<<DMITRII<PETROVICH", "DMITRII", "IVANOVICH", True, "DMITRII PETROVICH"),
        ("VASILEV<<IVANOVICH", "DMITRII", "IVANOVICH", True, "IVANOVICH"),
    ],
)
def test_given_names_may_include_the_separately_read_other_names(
    mrz_name: str,
    given_names: str,
    other_names: str | None,
    conflict: bool,
    resolved_given: str,
) -> None:
    page = _page(
        _passport_mrz(name=mrz_name),
        fields=_readings(surname="VASILEV", given_names=given_names),
        surname="VASILEV",
        given_names=given_names,
        other_names=other_names,
    )

    resolution = _resolve(page)

    assert resolution.conflicts == (("given_names",) if conflict else ())
    assert resolution.analysis.person.given_names == resolved_given
    assert resolution.analysis.person.other_names == other_names


def test_german_umlaut_spelling_conflicts_with_mrz_transcription_and_the_mrz_wins() -> None:
    # C23: `ü → u`; MRZ `MUELLER` yazımı `Müller`le aynı anahtara inmez — MRZ önceliği karar verir.
    page = _page(
        _passport_mrz(name="MUELLER<<JOSE"),
        fields=_readings(surname="MÜLLER", given_names="JOSÉ"),
        surname="MÜLLER",
        given_names="JOSÉ",
    )

    resolution = _resolve(page)

    assert resolution.conflicts == ("surname",)
    assert resolution.analysis.person.surname == "MUELLER"
    assert resolution.analysis.person.given_names == "JOSÉ"


def test_visible_cyrillic_name_is_compared_with_the_documents_language() -> None:
    # Ukraynaca `Г → H` (Tablo B istisnası): dil verilmeden `GRYGORENKO` olur ve çelişki sanılırdı.
    page = _page(
        _passport_mrz(name="HRYHORENKO<<MYKOLA"),
        fields=_readings(surname="Григоренко", given_names="Микола"),
        top={"language": "uk"},
        surname="Григоренко",
        given_names="Микола",
    )

    resolution = _resolve(page)

    assert resolution.conflicts == ()
    assert resolution.analysis == page


def test_visible_hyphenated_surname_agrees_with_the_mrz_filler() -> None:
    page = _page(
        _passport_mrz(name="TESTOVA<SHCHELKINA<<IULIA"),
        fields=_readings(surname="TESTOVA-SHCHELKINA", given_names="IULIA"),
        surname="TESTOVA-SHCHELKINA",
        given_names="IULIA",
    )
    assert _resolve(page).conflicts == ()


def test_mrz_fills_readings_the_visible_text_could_not_give_without_a_note() -> None:
    page = _page(
        _passport_mrz(),
        fields=_readings(document_number=None, date_of_birth=None, expiry_date=None),
        document_number=None,
        date_of_birth=None,
        nationality=None,
    )

    resolution = _resolve(page)
    resolved = resolution.analysis

    assert resolution.conflicts == ()
    assert resolved.notes is None
    assert resolved.person.document_number == "000000001"
    assert resolved.person.date_of_birth == date(1990, 1, 1)
    assert resolved.person.nationality == "RUS"
    assert resolved.fields["document_number"].model_dump() == {
        "value": "000000001",
        "legible": True,
    }
    assert resolved.fields["date_of_birth"].value == "1990-01-01"
    assert resolved.fields["expiry_date"].value == "2030-01-01"


def test_mrz_does_not_add_readings_the_type_does_not_require() -> None:
    fields = {"surname": {"value": "ORNEKOVA", "legible": True}}
    page = _page(_passport_mrz(), fields=fields, top={"document_type_slug": None}, nationality=None)

    resolved = _resolve(page).analysis

    assert set(resolved.fields) == {"surname"}
    assert resolved.person.nationality == "RUS"


def test_absent_mrz_name_part_leaves_the_visible_reading_alone() -> None:
    page = _page(_passport_mrz(name="ORNEKOVA"))

    resolution = _resolve(page)

    assert resolution.analysis.person.given_names == "TEST"
    assert resolution.analysis.fields["given_names"].value == "TEST"
    assert resolution.conflicts == ()


@pytest.mark.parametrize(
    ("field", "check"),
    [("document_number", "7"), ("date_of_birth", "2"), ("expiry_date", "<")],
)
def test_field_with_failing_check_digit_becomes_illegible_even_if_visible_text_agrees(
    field: str, check: str
) -> None:
    page = _page(_passport_mrz(checks={field: check}), notes="Parlama yok.")

    resolution = _resolve(page)
    resolved = resolution.analysis

    assert resolved.fields[field].model_dump() == {"value": None, "legible": False}
    if field in PERSON_FIELDS:
        assert getattr(resolved.person, field) is None
    assert resolved.notes == (
        f"Parlama yok. MRZ kontrol hanesi tutmuyor, alan okunamadı sayıldı: {field}."
    )
    assert resolution.conflicts == ()
    others = {name for name in VISIBLE if name != field}
    assert all(resolved.fields[name] == page.fields[name] for name in others)
    assert resolution.allows_clean_document_number is (field != "document_number")


def test_failing_check_digit_wins_over_a_conflicting_visible_reading() -> None:
    page = _page(
        _passport_mrz(checks={"document_number": "3"}),
        fields=_readings(document_number="00 0000002"),
        document_number="00 0000002",
    )

    resolution = _resolve(page)

    assert resolution.conflicts == ()
    assert resolution.analysis.person.document_number is None
    assert not resolution.analysis.fields["document_number"].legible


def test_failing_composite_keeps_the_values_but_blocks_a_clean_document_number() -> None:
    page = _page(_passport_mrz(composite="9"), document_number=None)

    resolution = _resolve(page)

    assert not resolution.allows_clean_document_number
    assert resolution.analysis.person.document_number == "000000001"
    assert resolution.analysis.fields["document_number"].legible
    assert resolution.analysis.notes == (
        "MRZ bileşik kontrol hanesi tutmuyor; MRZ bütün olarak şüpheli."
    )


def test_malformed_mrz_value_becomes_illegible_with_its_own_note() -> None:
    page = _page(_passport_mrz(birth="901301", name="0RNEKOVA<<TEST"))

    resolution = _resolve(page)
    resolved = resolution.analysis

    assert resolved.person.date_of_birth is None
    assert (resolved.person.surname, resolved.person.given_names) == (None, None)
    assert not resolved.fields["date_of_birth"].legible
    assert not resolved.fields["surname"].legible
    assert resolved.notes == (
        "MRZ değeri geçersiz, alan okunamadı sayıldı: surname, given_names, date_of_birth."
    )
    assert resolution.allows_clean_document_number


def test_all_notes_come_together_without_personal_values() -> None:
    lines = _passport_mrz(checks={"expiry_date": "5"}, birth="900230")
    lines[1] = lines[1][:-1] + str((int(lines[1][-1]) + 1) % 10)  # bileşik hane de bozuk
    page = _page(lines, fields=_readings(surname="PETROVA"), surname="PETROVA")

    resolution = _resolve(page)
    notes = resolution.analysis.notes

    assert notes == (
        "MRZ kontrol hanesi tutmuyor, alan okunamadı sayıldı: expiry_date. "
        "MRZ bileşik kontrol hanesi tutmuyor; MRZ bütün olarak şüpheli. "
        "MRZ değeri geçersiz, alan okunamadı sayıldı: date_of_birth. "
        "MRZ ile görünen metin çelişiyor, MRZ değeri kullanıldı: surname."
    )
    for value in ("ORNEKOVA", "PETROVA", "TEST", "000000001", "0000001", "1990", "900230", "RUS"):
        assert value not in notes


def test_priority_is_idempotent_and_keeps_the_analysts_notes() -> None:
    criterion = (
        "Karşılanmayan kabul kriteri: Kimlik sayfası tam görünür olmalı, kenarlar kesilmemiş"
    )
    page = _page(
        _passport_mrz(checks={"document_number": "4"}),
        fields=_readings(surname="PETROVA"),
        notes=criterion,
        surname="PETROVA",
    )

    first = _resolve(page).analysis
    second = _resolve(first)

    assert first.notes is not None and first.notes.startswith(criterion + " MRZ ")
    assert second.analysis == first
    assert second.conflicts == ()


@pytest.mark.parametrize(
    "lines",
    [
        ["P<RUSORNEKOVA<<TEST"],
        [SPECIMEN_TD3[0], SPECIMEN_TD3[1][:-1]],
        [line + "\n" for line in SPECIMEN_TD3],
    ],
    ids=["tek-kisa-satir", "eksik-karakter", "satir-sonu"],
)
def test_unrecognized_mrz_is_ignored_with_a_note(lines: list[str]) -> None:
    page = _page(lines, fields=_readings(surname="PETROVA"), surname="PETROVA")

    resolution = _resolve(page)

    assert resolution.status is MrzStatus.UNRECOGNIZED
    assert resolution.mrz is None and resolution.conflicts == ()
    assert resolution.analysis.person.surname == "PETROVA"
    assert resolution.analysis.notes == (
        "MRZ satırları TD1, TD2 veya TD3 biçimine uymuyor; MRZ yok sayıldı."
    )
    assert resolution.analysis.model_dump(exclude={"notes"}) == page.model_dump(exclude={"notes"})
    assert resolution.allows_clean_document_number


def test_invalid_mrz_is_not_used_and_blocks_a_clean_document_number() -> None:
    lines = _passport_mrz()
    lines[1] = lines[1][:9] + "«" + lines[1][10:]
    page = _page(lines, fields=_readings(surname="PETROVA"), surname="PETROVA")

    resolution = _resolve(page)

    assert resolution.status is MrzStatus.INVALID
    assert resolution.mrz is None
    assert resolution.analysis.person.surname == "PETROVA"
    assert resolution.analysis.notes == (
        "MRZ satırlarında izin verilmeyen karakter var; MRZ geçersiz sayıldı."
    )
    assert not resolution.allows_clean_document_number


@pytest.mark.parametrize("top", [{"is_readable": False}, {"is_blank": True}])
def test_mrz_on_a_page_that_calls_itself_unreadable_is_not_trusted(top: dict[str, Any]) -> None:
    page = _page(_passport_mrz(), fields=_readings(document_number=None), top=top)

    resolution = _resolve(page)

    assert resolution.status is MrzStatus.UNTRUSTED
    assert resolution.analysis is page
    assert not resolution.allows_clean_document_number


def test_birth_century_follows_the_given_day() -> None:
    page = _page(_passport_mrz(birth="260916"), fields=_readings(date_of_birth=None))
    resolved = _resolve(page).analysis
    assert resolved.fields["date_of_birth"].value == "1926-09-16"


# --- entegrasyon: kayıtlı yanıtlar ve okunaklılık kapısı (04.4) --------------------------------


def _recording(name: str) -> dict[str, Any]:
    return json.loads((RECORDINGS / name / "0.json").read_text("utf-8"))


def _accepted(payload: dict[str, Any]) -> PageAnalysis:
    return validate_page_analysis(payload, known_slugs=CATALOG.slugs())


def test_every_recorded_mrz_is_valid_and_agrees_with_its_visible_text() -> None:
    recorded = sorted(RECORDINGS.glob("*/*.json"))
    with_mrz = 0
    for path in recorded:
        analysis = validate_page_analysis(path.read_text("utf-8"), known_slugs=CATALOG.slugs())
        resolution = _resolve(analysis)
        if analysis.person.mrz_lines is None:
            assert resolution.status is MrzStatus.ABSENT, path
            continue
        with_mrz += 1
        assert resolution.status is MrzStatus.READ, path
        assert resolution.mrz is not None and resolution.mrz.failed_checks == (), path
        assert resolution.conflicts == (), path
        assert resolution.analysis == analysis, path
        assert resolution.allows_clean_document_number, path
    assert with_mrz >= 2


def test_s13_recording_reads_the_same_person_from_its_mrz() -> None:
    mrz = _resolve(_accepted(_recording("s13_cyrillic_name"))).mrz

    assert mrz is not None and mrz.format is MrzFormat.TD3
    assert (mrz.surname, mrz.given_names) == ("TESTOVA SHCHELKINA", "IULIA")
    assert (mrz.document_number, mrz.date_of_birth) == ("000000013", date(1992, 3, 15))
    assert mrz.expiry_date == date(2032, 3, 15)


def _legibility(analysis: PageAnalysis) -> Any:
    candidate = DocumentCandidate((CandidatePage(1, analysis.page_index, analysis),))
    return check_legibility(candidate, catalog=CATALOG)


def test_recorded_passport_with_a_broken_number_check_digit_goes_to_unreadable() -> None:
    payload = _recording("russian_passport")
    line = payload["person"]["mrz_lines"][1]
    payload["person"]["mrz_lines"][1] = line[:9] + str((int(line[9]) + 1) % 10) + line[10:]
    analysis = _accepted(payload)
    assert _legibility(analysis).illegible_fields is None  # görünen metin tek başına okunaklı

    resolution = _resolve(analysis)
    check = _legibility(resolution.analysis)

    assert check.illegible_fields == IllegibleRequiredFields(("document_number",))
    assert check.reason == "Okunamayan alanlar: document_number"
    assert not resolution.allows_clean_document_number


def test_recorded_passport_with_a_blurred_number_is_read_from_its_valid_mrz() -> None:
    payload = _recording("russian_passport")
    payload["person"]["document_number"] = None
    payload["fields"]["document_number"] = {"value": None, "legible": False}
    analysis = _accepted(payload)
    assert _legibility(analysis).reason == "Okunamayan alanlar: document_number"

    resolution = _resolve(analysis)
    check = _legibility(resolution.analysis)

    assert check.illegible_fields is None and check.queue is None
    assert resolution.analysis.person.document_number == "000000001"
    assert resolution.allows_clean_document_number
