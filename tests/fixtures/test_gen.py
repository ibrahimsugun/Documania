"""09.3.1 — sentetik belge üreteci: testler gerçek belge kullanmadan çalışır; kontrol hanesi geçerli
sahte MRZ dahil belge üretilir.

Üretecin MRZ yazıcısı ayrıştırıcıdan (`app.matching.mrz`) bağımsızdır: alanları anlamlarıyla
birleştirir, ayrıştırıcı konumlardan okur. İki taraf aynı haneleri bulmalıdır (§20.1.5 "üreteç
yazar, ayrıştırıcı okur"). Üretilen her sayfa §8.4 yanıtını taşır; depodaki kayıtlı yanıtların
hepsi üreteçle birebir yeniden üretilir, yani kabul senaryolarının kullandığı kişiler ve belgeler
tek kaynaktan gelir.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from PIL import Image

from app.ai.schemas import PageAnalysis, validate_page_analysis
from app.matching.mrz import COMPOSITE, MrzStatus, apply_mrz_priority, parse_mrz
from app.pipeline.render import (
    detect_pdf_blank_pages,
    detect_pdf_single_image_pages,
    single_full_page_image_xref,
)
from tests.ai.payloads import page_request
from tests.fixtures.gen import (
    CATALOG,
    PAGE_FIELDS,
    PERSON_ORNEKOVA,
    PERSON_PRUEBA,
    PERSON_SIDOROV,
    PERSON_TESTOVA_SHCHELKINA,
    SyntheticPage,
    SyntheticPerson,
    batch_analyses,
    blank_page,
    document_page,
    driving_license_pages,
    file_analyses,
    make_document_pdf_bytes,
    make_mrz_lines,
    make_page_image_bytes,
    make_portrait_image_bytes,
    mrz_check_digit,
    mrz_name,
    passport_page,
    profile_picture_page,
    recorded_provider,
    residence_card_pages,
    unknown_document_page,
    work_permit_page,
    write_recordings,
)
from tests.matching.test_mrz import SPECIMEN_TD1, SPECIMEN_TD2, SPECIMEN_TD3

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
RECORDINGS = TESTS / "fixtures" / "ai" / "recordings"
SLUGS = CATALOG.slugs()
TODAY = date(2026, 9, 18)

S9_NOTES = (
    "Belge numarası ve MRZ bölgesi bulanık, karakterler seçilemiyor. Karşılanmayan kabul "
    "kriteri: MRZ iki satırı da okunabilir olmalı"
)
S14_NOTES = "Katalogda Peru diploması türü yok; belge aday tür olarak önerildi."
S3_BACK_NOTES = (
    "Arka yüzde yalnız ehliyet sınıfları tablosu var; önceki sayfa başka bir belgenin arka yüzü."
)


def _ornekova_passport(**changes: Any) -> SyntheticPage:
    return passport_page(
        PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1), **changes
    )


def _sidorov_license() -> tuple[SyntheticPage, SyntheticPage]:
    return driving_license_pages(
        PERSON_SIDOROV, document_number="000123456", expiry_date=date(2031, 6, 30)
    )


def _sidorov_residence(**changes: Any) -> tuple[SyntheticPage, SyntheticPage]:
    return residence_card_pages(
        PERSON_SIDOROV, document_number="AB1234567", expiry_date=date(2029, 12, 31), **changes
    )


def _sidorov_work_permit() -> SyntheticPage:
    return work_permit_page(
        PERSON_SIDOROV, document_number="WP-0000042", expiry_date=date(2027, 3, 31)
    )


def _mrz(fmt: str, **changes: Any) -> tuple[str, ...]:
    fields: dict[str, Any] = {
        "document_code": "P",
        "issuing_state": "UTO",
        "surname": "ORNEK-SOYAD",
        "given_names": "TEST IKINCI",
        "document_number": "AB 12.34-56",
        "nationality": "UTO",
        "date_of_birth": date(1988, 11, 30),
        "sex": "M",
        "expiry_date": date(2031, 2, 28),
    }
    fields.update(changes)
    return make_mrz_lines(fmt, **fields)  # type: ignore[arg-type]


def _changed(lines: tuple[str, ...], line: int, position: int) -> list[str]:
    """1 tabanlı konumdaki haneyi bir sonraki rakama çevirir."""
    row = lines[line - 1]
    digit = str((int(row[position - 1]) + 1) % 10)
    changed = list(lines)
    changed[line - 1] = row[: position - 1] + digit + row[position:]
    return changed


def _accepted(analysis: dict[str, Any]) -> PageAnalysis:
    return validate_page_analysis(analysis, known_slugs=SLUGS)


def _recorded(name: str) -> list[dict[str, Any]]:
    paths = sorted((RECORDINGS / name).glob("*.json"))
    assert paths, name
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def _pdf_text(content: bytes) -> list[str]:
    with pymupdf.open(stream=content, filetype="pdf") as document:
        return [page.get_text() for page in document]


def _write(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


# --- §20.1.4 kontrol hanesi ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("characters", "expected"),
    [("L898902C3", "6"), ("690806", "1"), ("940623", "6")],
    ids=["belge-numarasi", "dogum-tarihi", "son-gecerlilik"],
)
def test_check_digit_matches_the_mandatory_icao_examples(characters: str, expected: str) -> None:
    assert mrz_check_digit(characters) == expected


def test_check_digit_uses_letter_values_filler_zero_and_repeating_weights() -> None:
    assert mrz_check_digit("") == "0"
    assert mrz_check_digit("<<<<<<<<<") == "0"
    assert mrz_check_digit("A") == "0"  # 10 × 7 = 70
    assert mrz_check_digit("Z") == "5"  # 35 × 7 = 245
    assert mrz_check_digit("<1") == "3"  # 1 × 3
    assert mrz_check_digit("<<1") == "1"  # 1 × 1
    assert mrz_check_digit("<<<1") == "7"  # ağırlık dördüncü karakterde yine 7


@pytest.mark.parametrize("characters", ["l898902c3", "AB 12", "Ç", "١"])
def test_check_digit_rejects_characters_outside_the_mrz_set(characters: str) -> None:
    with pytest.raises(ValueError, match="A-Z, 0-9 veya <"):
        mrz_check_digit(characters)


# --- §20.1.3 ve §20.1.5: üreteç yazar, ayrıştırıcı okur -----------------------------------------


@pytest.mark.parametrize(
    ("fmt", "changes", "specimen"),
    [
        (
            "TD3",
            {"document_number": "L898902C3", "optional_data": "ZE184226B"},
            SPECIMEN_TD3,
        ),
        ("TD2", {"document_code": "I", "document_number": "D23145890"}, SPECIMEN_TD2),
        ("TD1", {"document_code": "I", "document_number": "D23145890"}, SPECIMEN_TD1),
    ],
    ids=["TD3", "TD2", "TD1"],
)
def test_generator_reproduces_the_icao_specimens(
    fmt: str, changes: dict[str, Any], specimen: list[str]
) -> None:
    # ICAO Doc 9303'ün kurgusal "Utopia" örnekleri: kontrol haneleri ve bileşik hane birebir.
    lines = _mrz(
        fmt,
        surname="ERIKSSON",
        given_names="ANNA MARIA",
        date_of_birth=date(1974, 8, 12),
        sex="F",
        expiry_date=date(2012, 4, 15),
        **changes,
    )
    assert list(lines) == specimen


@pytest.mark.parametrize("fmt", ["TD1", "TD2", "TD3"])
def test_generated_mrz_is_parsed_back_to_the_same_values_with_every_check_holding(
    fmt: str,
) -> None:
    lines = _mrz(fmt, optional_data="PN123", **({"optional_data_2": "X9"} if fmt == "TD1" else {}))

    mrz = parse_mrz(lines, today=TODAY)

    assert mrz is not None
    assert (mrz.format, mrz.document_code, mrz.issuing_state) == (fmt, "P", "UTO")
    assert (mrz.surname, mrz.given_names) == ("ORNEK SOYAD", "TEST IKINCI")
    assert (mrz.document_number, mrz.nationality, mrz.sex) == ("AB123456", "UTO", "M")
    assert (mrz.date_of_birth, mrz.expiry_date) == (date(1988, 11, 30), date(2031, 2, 28))
    assert mrz.optional_data == {"TD1": ("PN123", "X9"), "TD2": ("PN123",), "TD3": ("PN123",)}[fmt]
    assert (mrz.failed_checks, mrz.illegible_fields, mrz.composite_valid) == ((), (), True)


# (satır, konum, alan) — §20.1.3'teki hane konumları. Alan haneleri bileşik hanenin kapsamındadır.
CHECK_POSITIONS = {
    "TD3": [
        (2, 10, "document_number"),
        (2, 20, "date_of_birth"),
        (2, 28, "expiry_date"),
        (2, 43, "optional_data"),
        (2, 44, COMPOSITE),
    ],
    "TD2": [
        (2, 10, "document_number"),
        (2, 20, "date_of_birth"),
        (2, 28, "expiry_date"),
        (2, 36, COMPOSITE),
    ],
    "TD1": [
        (1, 15, "document_number"),
        (2, 7, "date_of_birth"),
        (2, 15, "expiry_date"),
        (2, 30, COMPOSITE),
    ],
}


@pytest.mark.parametrize("fmt", ["TD1", "TD2", "TD3"])
def test_every_check_digit_the_generator_writes_is_the_one_the_parser_verifies(fmt: str) -> None:
    lines = _mrz(fmt)
    for line, position, name in CHECK_POSITIONS[fmt]:
        mrz = parse_mrz(_changed(lines, line, position), today=TODAY)
        assert mrz is not None
        expected = (COMPOSITE,) if name == COMPOSITE else (name, COMPOSITE)
        assert mrz.failed_checks == expected, (line, position)


@pytest.mark.parametrize(
    ("fmt", "surname", "given_names", "expected"),
    [
        ("TD3", "TESTOVA-SHCHELKINA", "IULIA", "P<RUSTESTOVA<SHCHELKINA<<IULIA<<<<<<<<<<<<<<"),
        ("TD3", "de la Prueba", "Ana Maria", "P<RUSDE<LA<PRUEBA<<ANA<MARIA<<<<<<<<<<<<<<<<"),
        ("TD3", "O'TEST", None, "P<RUSO<TEST<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"),
    ],
)
def test_name_field_uses_single_and_double_fillers(
    fmt: str, surname: str, given_names: str | None, expected: str
) -> None:
    lines = _mrz(fmt, issuing_state="RUS", surname=surname, given_names=given_names)
    assert lines[0] == expected
    assert mrz_name(surname, given_names) in expected


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"surname": "Орнекова"}, "Latin harflerle"),
        ({"surname": "ORNEK1"}, "Latin harflerle"),
        ({"surname": " - "}, "Latin harflerle"),
        ({"surname": "A" * 40}, "en çok 39"),
        ({"document_number": "1234567890"}, "en çok 9"),
        ({"document_number": "AB#123"}, "en çok 9"),
        ({"nationality": "RUSX"}, "en çok 3"),
        ({"optional_data": "A" * 15}, "en çok 14"),
        ({"sex": "X"}, "cinsiyet"),
        ({"optional_data_2": "X"}, "yalnız TD1"),
    ],
)
def test_values_that_do_not_fit_the_mrz_are_refused_not_truncated(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _mrz("TD3", **changes)


# --- §8.4 kayıtlı yanıt -------------------------------------------------------------------------


def _every_page() -> list[SyntheticPage]:
    return [
        _ornekova_passport(),
        _ornekova_passport(blurred={"document_number"}, mrz_legible=False, notes=S9_NOTES),
        passport_page(
            PERSON_TESTOVA_SHCHELKINA, document_number="00 0000013", expiry_date=date(2032, 3, 15)
        ),
        passport_page(
            SyntheticPerson("PETROVIC", "MARKO", date(1991, 7, 1), "SRB", "M"),
            document_number="000000077",
            expiry_date=date(2033, 1, 31),
            slug="serbian_passport",
        ),
        passport_page(
            SyntheticPerson("DENEME", "AYSE", date(1993, 2, 2), "TUR", "F"),
            document_number="U00000088",
            expiry_date=date(2034, 5, 5),
            slug="turkish_passport",
        ),
        *_sidorov_license(),
        *_sidorov_residence(),
        *_sidorov_residence(with_mrz=True),
        _sidorov_work_permit(),
        profile_picture_page(),
        unknown_document_page(
            PERSON_PRUEBA,
            candidate_type_name="Peruvian Diploma",
            title="DIPLOMA",
            document_number="DIP-0000077",
            notes=S14_NOTES,
        ),
    ]


def test_every_generated_page_is_an_acceptable_page_analysis() -> None:
    for page in _every_page():
        analysis = _accepted(page.analysis())
        # Okunaklı alanın değeri dolu, okunamayanın değeri yok (K1); tür alanları katalogdan.
        entry = CATALOG.get(analysis.document_type_slug) if analysis.document_type_slug else None
        expected = () if entry is None else tuple(entry.required_fields)
        assert tuple(analysis.fields) == expected


@pytest.mark.parametrize(
    "page",
    [
        _ornekova_passport(),
        passport_page(
            PERSON_TESTOVA_SHCHELKINA, document_number="00 0000013", expiry_date=date(2032, 3, 15)
        ),
        passport_page(
            SyntheticPerson("PETROVIC", "MARKO", date(1991, 7, 1), "SRB", "M"),
            document_number="000000077",
            expiry_date=date(2033, 1, 31),
            slug="serbian_passport",
        ),
    ],
    ids=["ru", "ru-kiril-tireli", "rs"],
)
def test_passport_mrz_is_valid_and_agrees_with_the_visible_text(page: SyntheticPage) -> None:
    analysis = _accepted(page.analysis())

    resolution = apply_mrz_priority(analysis, today=TODAY)

    assert resolution.status is MrzStatus.READ
    assert resolution.mrz is not None and resolution.mrz.format == "TD3"
    assert (resolution.mrz.failed_checks, resolution.conflicts) == ((), ())
    assert resolution.allows_clean_document_number
    # MRZ görünen okumayla aynı anahtara iniyor: yanıt olduğu gibi kalır, not eklenmez (05.3.3).
    assert resolution.analysis == analysis


def test_residence_card_back_can_carry_a_valid_td1_mrz() -> None:
    front, back = _sidorov_residence(with_mrz=True)
    assert front.mrz_lines == ()
    analysis = _accepted(back.analysis(1))

    resolution = apply_mrz_priority(analysis, today=TODAY)

    assert resolution.status is MrzStatus.READ
    assert resolution.mrz is not None and resolution.mrz.format == "TD1"
    assert (resolution.mrz.document_code, resolution.mrz.issuing_state) == ("IR", "SRB")
    assert (resolution.mrz.failed_checks, resolution.conflicts) == ((), ())
    assert resolution.allows_clean_document_number
    # Arka yüz ismi göstermez; MRZ'yi okuyan analizcinin kişisi MRZ'den dolar.
    assert analysis.person.surname is None
    person = resolution.analysis.person
    assert (person.surname, person.given_names, person.document_number) == (
        "SIDOROV",
        "IVAN",
        "AB1234567",
    )
    assert resolution.analysis.fields["expiry_date"].value == "2029-12-31"


def test_a_given_broken_mrz_is_written_as_is() -> None:
    valid = _ornekova_passport().mrz_lines
    broken = tuple(_changed(valid, 2, 10))

    page = _ornekova_passport(mrz_lines=broken)

    assert page.mrz_lines == broken
    resolution = apply_mrz_priority(_accepted(page.analysis()), today=TODAY)
    assert resolution.mrz is not None
    assert resolution.mrz.failed_checks == ("document_number", COMPOSITE)
    assert resolution.analysis.fields["document_number"].legible is False


def test_blurred_fields_are_unreadable_in_the_reading_and_smudged_on_the_page() -> None:
    page = _ornekova_passport(blurred={"document_number"}, mrz_legible=False)
    analysis = _accepted(page.analysis())

    assert analysis.person.document_number is None
    assert analysis.person.mrz_lines is None
    assert analysis.fields["document_number"].model_dump() == {"value": None, "legible": False}
    others = [reading for name, reading in analysis.fields.items() if name != "document_number"]
    assert all(reading.legible for reading in others)
    (text,) = _pdf_text(make_document_pdf_bytes([page]))
    assert "Document No.:" in text and "0000001" not in text
    assert "P<RUS" not in text  # MRZ lekelendi, metin katmanında yok
    assert "ORNEKOVA" in text


def test_blurred_name_hides_the_original_script_name_as_well() -> None:
    page = document_page(
        "russian_passport",
        title="T",
        person=PERSON_ORNEKOVA,
        shows=("surname", "given_names"),
        blurred=("surname",),
    )
    person = _accepted(page.analysis()).person

    assert (person.surname, person.original_script_name, person.given_names) == (None, None, "TEST")
    assert ("Name", None) in page.lines


def test_other_names_are_read_with_the_given_names() -> None:
    person = replace(PERSON_ORNEKOVA, other_names="IVANOVNA")
    page = document_page("work_permit", title="T", person=person, shows=("surname", "given_names"))

    analysis = _accepted(page.analysis())

    assert (analysis.person.given_names, analysis.person.other_names) == ("TEST", "IVANOVNA")
    assert ("Other names", "IVANOVNA") in page.lines


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"shows": ("surname", "tckn")}, "bilinmeyen sayfa alanı"),
        ({"shows": ("surname",), "blurred": ("given_names",)}, "sayfada yazılı olmalı"),
        ({"shows": ("document_number",)}, "değeri yok"),
    ],
)
def test_inconsistent_page_definitions_are_refused(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        document_page("work_permit", title="T", person=PERSON_SIDOROV, **changes)


def test_type_outside_the_seed_catalog_needs_its_required_fields() -> None:
    with pytest.raises(ValueError, match="tohum katalogda yok"):
        document_page("peruvian_diploma", title="T")

    page = document_page(
        "peruvian_diploma",
        title="T",
        person=PERSON_PRUEBA,
        shows=("surname",),
        required_fields=("surname", "document_number"),
    )

    assert page.analysis()["fields"] == {
        "surname": {"value": "PRUEBA", "legible": True},
        "document_number": {"value": None, "legible": False},
    }


def test_documents_with_an_mrz_need_birth_date_and_nationality() -> None:
    with pytest.raises(ValueError, match="doğum tarihi ve uyruk"):
        passport_page(PERSON_PRUEBA, document_number="000000001", expiry_date=date(2030, 1, 1))
    # Oturma izninin ön yüzü uyruğu yazar; uyruğu olmayan kişiyle kart (MRZ'li ya da değil) olmaz.
    with pytest.raises(ValueError, match="nationality sayfada yazılı ama değeri yok"):
        residence_card_pages(
            PERSON_PRUEBA,
            document_number="AB1234567",
            expiry_date=date(2030, 1, 1),
            with_mrz=True,
        )


def test_the_reading_is_a_new_dictionary_each_time_and_notes_can_be_replaced() -> None:
    page = _ornekova_passport()
    first = page.analysis()
    first["person"]["surname"] = "DEGISTI"

    assert page.analysis()["person"]["surname"] == "ORNEKOVA"
    noted = page.with_notes("not")
    assert (noted.analysis()["notes"], page.analysis()["notes"]) == ("not", None)
    assert noted.lines == page.lines


def test_a_blank_page_has_no_reading() -> None:
    assert blank_page().is_blank
    with pytest.raises(ValueError, match="boş sayfa analize gitmez"):
        blank_page().analysis()


# --- depodaki kayıtlı yanıtlar üreteçten gelir --------------------------------------------------


def _s3_pages() -> list[SyntheticPage]:
    license_front, license_back = _sidorov_license()
    residence_front, residence_back = _sidorov_residence()
    return [
        license_front,
        profile_picture_page(),
        _sidorov_work_permit(),
        residence_front,
        residence_back,
        license_back.with_notes(S3_BACK_NOTES),
    ]


RECORDED_BATCHES: dict[str, Any] = {
    "russian_passport": lambda: [[_ornekova_passport()]],
    "s9_blurred_passport": lambda: [
        [_ornekova_passport(blurred={"document_number"}, mrz_legible=False, notes=S9_NOTES)]
    ],
    "s13_cyrillic_name": lambda: [
        [
            passport_page(
                PERSON_TESTOVA_SHCHELKINA,
                document_number="00 0000013",
                expiry_date=date(2032, 3, 15),
            )
        ]
    ],
    "s14_peruvian_diploma": lambda: [
        [
            unknown_document_page(
                PERSON_PRUEBA,
                candidate_type_name="Peruvian Diploma",
                title="DIPLOMA",
                document_number="DIP-0000077",
                notes=S14_NOTES,
            )
        ]
    ],
    "s3_interleaved_pdf": lambda: [_s3_pages()],
    "s4_sequential_pdf": lambda: [
        [*_sidorov_license(), profile_picture_page(), *_sidorov_residence()]
    ],
    "s5_front_back_images": lambda: [[page] for page in _sidorov_license()],
    "serbian_residence_card": lambda: [list(_sidorov_residence())],
}


@pytest.mark.parametrize("name", sorted(RECORDED_BATCHES))
def test_committed_recordings_are_reproduced_by_the_generator(name: str) -> None:
    files = RECORDED_BATCHES[name]()
    assert batch_analyses(*files) == _recorded(name)


def test_every_committed_recording_directory_is_covered() -> None:
    directories = {path.name for path in RECORDINGS.iterdir() if path.is_dir()}
    assert directories == set(RECORDED_BATCHES)


# --- dosya sırası ve kayıt yazımı ---------------------------------------------------------------


def test_blank_pages_are_not_analyzed_and_keep_their_neighbours_indexes() -> None:
    front, back = _sidorov_license()
    analyses = file_analyses([blank_page(), front, blank_page(), back, blank_page()])

    assert [(a["page_index"], a["side"], a["continues_previous_page"]) for a in analyses] == [
        (1, "front", False),
        (3, "back", True),  # arada yalnız boş sayfa var: önceki analiz edilen sayfa ön yüz
    ]


def test_continuation_needs_the_previous_part_of_the_same_document() -> None:
    first_front, first_back = _sidorov_license()
    second_front, second_back = _sidorov_license()

    analyses = file_analyses([first_front, second_back, second_front, second_back, first_back])

    # Başka belgenin arka yüzü ve ters sıra devam sayılmaz; yalnız kendi ön yüzünün hemen
    # ardından gelen arka yüz devamdır (S3: araya başka belge giren ehliyet arka yüzü değildir).
    assert [a["continues_previous_page"] for a in analyses] == [False, False, False, True, False]


def test_the_batch_order_is_file_order_then_page_order() -> None:
    passport = _ornekova_passport()
    front, back = _sidorov_license()

    analyses = batch_analyses([passport, blank_page()], [], [front], [back])

    assert [(a["document_type_slug"], a["page_index"]) for a in analyses] == [
        ("russian_passport", 0),
        ("serbian_driving_license", 0),
        ("serbian_driving_license", 0),
    ]
    # Ayrı görüntü dosyalarındaki yüzler dosya içinde devam değildir (S5 kaydı gibi).
    assert [a["continues_previous_page"] for a in analyses] == [False, False, False]


def test_recordings_are_written_for_the_recording_provider_in_call_order(tmp_path: Path) -> None:
    pages = [_sidorov_work_permit() for _ in range(12)]
    provider = recorded_provider(tmp_path / "kayit", pages)

    names = sorted(path.name for path in (tmp_path / "kayit").iterdir())
    assert names == [f"{index:04d}.json" for index in range(12)]
    # Sıfır dolgusu: onuncu yanıt ikinciden önce okunmaz — sağlayıcı istenen sayfanın yanıtını
    # döndürmeseydi `page_index` denetimi yanıtı reddederdi.
    read = [provider.analyze_page(page_request(page_index=index)) for index in range(12)]
    assert [analysis.page_index for analysis in read] == list(range(12))
    assert len(provider.requests) == 12


def test_recordings_are_not_written_over_existing_ones(tmp_path: Path) -> None:
    directory = write_recordings(tmp_path / "kayit", [_ornekova_passport().analysis()])

    with pytest.raises(FileExistsError, match="zaten kayıt var"):
        write_recordings(directory, [_ornekova_passport().analysis()])
    assert json.loads((directory / "0000.json").read_text(encoding="utf-8"))["page_index"] == 0


# --- dosyanın kendisi ---------------------------------------------------------------------------


def test_pdf_pages_carry_the_visible_values_and_the_mrz_in_their_text_layer() -> None:
    passport = _ornekova_passport()
    front, back = _sidorov_residence(with_mrz=True)

    texts = _pdf_text(make_document_pdf_bytes([passport, front, back]))

    assert len(texts) == 3
    for expected in ("ПАСПОРТ", "ORNEKOVA", "Орнекова Тест", "01.01.1990", "00 0000001"):
        assert expected in texts[0]
    for line in passport.mrz_lines:
        assert line in texts[0]
    assert "AB1234567" in texts[1] and "IR" not in texts[1]
    assert "31.12.2029" in texts[2] and "Belgrade, Test Street 1" in texts[2]
    for line in back.mrz_lines:
        assert line in texts[2]


def test_blank_and_photo_pages_are_what_the_render_step_detects(tmp_path: Path) -> None:
    pages = [*_s3_pages()[:3], blank_page()]
    path = _write(tmp_path, "belge.pdf", make_document_pdf_bytes(pages))

    assert detect_pdf_blank_pages(path) == [False, False, False, True]
    assert detect_pdf_single_image_pages(path) == [False, True, False, False]
    # Vesikalık sayfasının gömülü görüntüsü üretilen JPEG'in kendisidir (extract_image kayıpsız).
    with pymupdf.open(path) as document:
        xref = single_full_page_image_xref(document[1])
        assert xref is not None
        assert document.extract_image(xref)["image"] == make_portrait_image_bytes()


def test_same_pages_give_the_same_bytes_and_different_pages_do_not() -> None:
    first = make_document_pdf_bytes(_s3_pages())

    assert make_document_pdf_bytes(_s3_pages()) == first
    other = [*_s3_pages()[:-1], blank_page()]
    assert make_document_pdf_bytes(other) != first
    assert make_page_image_bytes(_ornekova_passport()) == make_page_image_bytes(
        _ornekova_passport()
    )


@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
def test_pages_can_be_image_files(fmt: str) -> None:
    front, _ = _sidorov_license()

    for page in (front, profile_picture_page()):
        with Image.open(BytesIO(make_page_image_bytes(page, fmt))) as image:
            assert image.format == fmt
            assert image.width > 0 and image.height > 0
    assert make_page_image_bytes(profile_picture_page(), fmt) == make_portrait_image_bytes(fmt)


def test_only_jpeg_and_png_images_are_made() -> None:
    with pytest.raises(ValueError, match="JPEG veya PNG"):
        make_page_image_bytes(_ornekova_passport(), "TIFF")


# --- testler gerçek belge kullanmaz -------------------------------------------------------------

DOCUMENT_SUFFIXES = frozenset(
    ".pdf .jpg .jpeg .png .gif .bmp .tif .tiff .webp .heic .heif .doc .docx .xls .xlsx".split()
)
DOCUMENT_SIGNATURES = (
    b"%PDF",
    b"\xff\xd8\xff",
    b"\x89PNG",
    b"GIF8",
    b"II*\x00",
    b"MM\x00*",
    b"PK\x03\x04",
    b"\xd0\xcf\x11\xe0",
)


def test_the_test_tree_holds_no_document_files() -> None:
    # Testlerin kullandığı her belge çalışma anında bu üreteçle üretilir (CONVENTIONS §6); test
    # ağacında belge dosyası (PDF, görüntü, Office) yoktur — kayıtlı yanıtlar yalnız JSON'dur.
    found = []
    for path in TESTS.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        with path.open("rb") as handle:
            head = handle.read(8)
        if path.suffix.lower() in DOCUMENT_SUFFIXES or head.startswith(DOCUMENT_SIGNATURES):
            found.append(path.relative_to(ROOT).as_posix())
    assert found == []
    assert {path.suffix for path in RECORDINGS.rglob("*") if path.is_file()} == {".json"}


def test_every_page_field_can_be_shown() -> None:
    page = document_page(
        "russian_passport",
        title="T",
        person=PERSON_ORNEKOVA,
        document_number="00 0000001",
        expiry_date=date(2030, 1, 1),
        shows=PAGE_FIELDS,
    )
    person = _accepted(page.analysis()).person

    assert [label for label, _ in page.lines] == [
        "Surname",
        "Name",
        "Given names",
        "Date of birth",
        "Nationality",
        "Document No.",
        "Date of expiry",
    ]
    assert (person.date_of_birth, person.nationality) == (date(1990, 1, 1), "RUS")
