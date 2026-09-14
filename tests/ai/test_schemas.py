"""03.1.1–03.1.4 — model yanıtı §8.4 şemasına uyar, uymayan yanıt reddedilir; dil/alfabe kapalı
kümededir; ek isimler ayrı döner ve çalışan kaydına taşınır; iletişim bilgisi yoksa `null`dır."""

import copy
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.ai import (
    EMPLOYEE_FIELDS,
    ISO_639_1_CODES,
    PageAnalysis,
    PageAnalysisError,
    PageContact,
    PagePerson,
    Script,
    Side,
    validate_page_analysis,
)
from app.catalog import load_seed_catalog
from app.db.models import Base, ContactKind, Employee
from app.db.session import create_db_engine, create_session_factory

# PRD §8.4 örneği, harfiyen (sentetik kişi).
SECTION_8_4_EXAMPLE = """\
{
  "page_index": 0,
  "is_blank": false,
  "is_readable": true,
  "language": "ru",
  "script": "cyrillic",
  "document_type_slug": "russian_passport",
  "candidate_type_name": null,
  "side": "single",
  "continues_previous_page": false,
  "person": {
    "surname": "VASILIEV",
    "given_names": "DMITRY",
    "other_names": null,
    "original_script_name": "Васильев Дмитрий",
    "date_of_birth": "1990-04-12",
    "nationality": "RUS",
    "document_number": "71 1234567",
    "mrz_lines": ["...", "..."],
    "contact": {
      "phone": null,
      "email": null,
      "address": "ул. Ленина, д. 5, кв. 12, Москва"
    }
  },
  "fields": {
    "surname": {"value": "VASILIEV", "legible": true},
    "document_number": {"value": "71 1234567", "legible": true},
    "expiry_date": {"value": null, "legible": false}
  },
  "notes": "Alt kenar hafif bulanık."
}
"""

SLUGS = load_seed_catalog().slugs()

TOP_LEVEL_KEYS = [
    "page_index",
    "is_blank",
    "is_readable",
    "language",
    "script",
    "document_type_slug",
    "candidate_type_name",
    "side",
    "continues_previous_page",
    "person",
    "fields",
    "notes",
]
PERSON_KEYS = [
    "surname",
    "given_names",
    "other_names",
    "original_script_name",
    "date_of_birth",
    "nationality",
    "document_number",
    "mrz_lines",
    "contact",
]
CONTACT_KEYS = ["phone", "email", "address"]


def example(**top: Any) -> dict[str, Any]:
    data = json.loads(SECTION_8_4_EXAMPLE)
    data.update(top)
    return data


def with_person(**person: Any) -> dict[str, Any]:
    data = example()
    data["person"].update(person)
    return data


def rejected(data: object, *, known_slugs: tuple[str, ...] = SLUGS) -> list[str]:
    with pytest.raises(PageAnalysisError) as caught:
        validate_page_analysis(data, known_slugs=known_slugs)
    return caught.value.problems


# --- 03.1.1 — §8.4 şemasına uyum ----------------------------------------------------------


def test_section_8_4_example_is_accepted_verbatim() -> None:
    analysis = validate_page_analysis(SECTION_8_4_EXAMPLE, known_slugs=SLUGS)

    assert analysis.page_index == 0
    assert analysis.is_blank is False
    assert analysis.is_readable is True
    assert analysis.language == "ru"
    assert analysis.script is Script.CYRILLIC
    assert analysis.document_type_slug == "russian_passport"
    assert analysis.candidate_type_name is None
    assert analysis.side is Side.SINGLE
    assert analysis.continues_previous_page is False
    assert analysis.person.surname == "VASILIEV"
    assert analysis.person.original_script_name == "Васильев Дмитрий"
    assert analysis.person.date_of_birth == date(1990, 4, 12)
    assert analysis.person.nationality == "RUS"
    assert analysis.person.document_number == "71 1234567"
    assert analysis.person.mrz_lines == ("...", "...")
    assert analysis.fields["surname"].value == "VASILIEV"
    assert analysis.fields["expiry_date"].legible is False
    assert analysis.notes == "Alt kenar hafif bulanık."


@pytest.mark.parametrize(
    "raw",
    [SECTION_8_4_EXAMPLE, SECTION_8_4_EXAMPLE.encode(), json.loads(SECTION_8_4_EXAMPLE)],
    ids=["str", "bytes", "dict"],
)
def test_json_text_and_decoded_object_give_the_same_result(raw: object) -> None:
    expected = validate_page_analysis(SECTION_8_4_EXAMPLE, known_slugs=SLUGS)
    assert validate_page_analysis(raw, known_slugs=SLUGS) == expected


def test_schema_keys_are_exactly_the_section_8_4_keys() -> None:
    raw = json.loads(SECTION_8_4_EXAMPLE)

    assert list(PageAnalysis.model_fields) == TOP_LEVEL_KEYS == list(raw)
    assert list(PagePerson.model_fields) == PERSON_KEYS == list(raw["person"])
    assert list(PageContact.model_fields) == CONTACT_KEYS == list(raw["person"]["contact"])


@pytest.mark.parametrize("key", TOP_LEVEL_KEYS)
def test_missing_top_level_key_is_rejected(key: str) -> None:
    data = example()
    del data[key]
    assert f"{key}: Field required" in rejected(data)


@pytest.mark.parametrize("key", PERSON_KEYS)
def test_missing_person_key_is_rejected(key: str) -> None:
    data = example()
    del data["person"][key]
    assert f"person.{key}: Field required" in rejected(data)


@pytest.mark.parametrize("key", CONTACT_KEYS)
def test_missing_contact_key_is_rejected(key: str) -> None:
    data = example()
    del data["person"]["contact"][key]
    assert f"person.contact.{key}: Field required" in rejected(data)


@pytest.mark.parametrize(
    "path",
    [(), ("person",), ("person", "contact"), ("fields", "surname")],
    ids=["top", "person", "contact", "field_reading"],
)
def test_unknown_key_is_rejected(path: tuple[str, ...]) -> None:
    data = example()
    target = data
    for part in path:
        target = target[part]
    target["confidence"] = 0.97
    assert rejected(data) == [".".join((*path, "confidence")) + ": Extra inputs are not permitted"]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("page_index", -1),
        ("page_index", "0"),
        ("page_index", True),
        ("page_index", 0.0),
        ("page_index", None),
        ("is_blank", "false"),
        ("is_blank", 0),
        ("is_readable", None),
        ("continues_previous_page", "no"),
        ("side", "left"),
        ("side", "SINGLE"),
        ("side", None),
        ("candidate_type_name", ""),
        ("notes", ""),
        ("notes", 5),
        ("person", None),
        ("person", "VASILIEV DMITRY"),
        ("fields", None),
        ("fields", []),
    ],
)
def test_top_level_value_outside_schema_is_rejected(key: str, value: object) -> None:
    problems = rejected(example(**{key: value}))
    assert problems and all(problem.startswith(key) for problem in problems)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("surname", ""),
        ("surname", "   "),
        ("given_names", ["DMITRY"]),
        ("surname", "X" * 256),
        ("date_of_birth", "12.04.1990"),
        ("date_of_birth", "19900412"),
        ("date_of_birth", "1990-02-30"),
        ("date_of_birth", "1990-04-12T00:00:00"),
        ("date_of_birth", 639878400),
        ("nationality", "Russia"),
        ("nationality", "rus"),
        ("nationality", "RUSS"),
        ("document_number", 711234567),
        ("document_number", "7" * 129),
        ("mrz_lines", []),
        ("mrz_lines", "P<RUSVASILIEV<<DMITRY"),
        ("mrz_lines", ["P<RUS", ""]),
        ("contact", None),
        ("contact", "+381 11 123 4567"),
    ],
)
def test_person_value_outside_schema_is_rejected(key: str, value: object) -> None:
    problems = rejected(with_person(**{key: value}))
    assert problems and all(problem.startswith(f"person.{key}") for problem in problems)


@pytest.mark.parametrize("raw", ["", "not json", "[]", "null", b"{", [], None, 42])
def test_response_that_is_not_a_json_object_is_rejected(raw: object) -> None:
    assert rejected(raw)


def test_every_violation_is_reported_with_its_location() -> None:
    data = example(side="left", language="xx")
    data["person"]["date_of_birth"] = "12.04.1990"

    problems = rejected(data)

    assert [problem.split(":")[0] for problem in problems] == [
        "language",
        "side",
        "person.date_of_birth",
    ]


def test_rejection_message_does_not_repeat_personal_values() -> None:
    data = with_person(date_of_birth="12.04.1990", document_number=711234567, nationality="Rus")

    with pytest.raises(PageAnalysisError) as caught:
        validate_page_analysis(data, known_slugs=SLUGS)

    message = str(caught.value)
    for personal in ("12.04.1990", "711234567", "Rus'"):
        assert personal not in message


def test_nullable_person_values_are_accepted_as_null() -> None:
    data = with_person(**dict.fromkeys(PERSON_KEYS[:-1]))
    data["person"]["contact"] = dict.fromkeys(CONTACT_KEYS)

    analysis = validate_page_analysis(data, known_slugs=SLUGS)

    assert analysis.person.model_dump(exclude={"contact"}) == dict.fromkeys(PERSON_KEYS[:-1])


@pytest.mark.parametrize("nationality", ["RUS", "SRB", "TUR", "D"])
def test_icao_nationality_codes_are_accepted(nationality: str) -> None:
    analysis = validate_page_analysis(with_person(nationality=nationality), known_slugs=SLUGS)
    assert analysis.person.nationality == nationality


def test_mrz_lines_are_carried_as_read() -> None:
    lines = [
        "P<RUSVASILIEV<<DMITRY<<<<<<<<<<<<<<<<<<<<<<<",
        "7112345670RUS9004124M3001012<<<<<<<<<<<<<<02",
    ]
    analysis = validate_page_analysis(with_person(mrz_lines=lines), known_slugs=SLUGS)
    assert analysis.person.mrz_lines == tuple(lines)


# --- fields: okunaklılık ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reading", "message"),
    [
        ({"value": None, "legible": True}, "legible: true olan alanın value'su dolu olmalı"),
        ({"value": "2031-01-01", "legible": False}, "legible: false olan alanın value'su null"),
        ({"value": "", "legible": True}, "at least 1 character"),
        ({"value": 20310101, "legible": True}, "valid string"),
        ({"value": "2031-01-01", "legible": "true"}, "valid boolean"),
        ({"value": "2031-01-01"}, "Field required"),
    ],
)
def test_field_reading_outside_schema_is_rejected(reading: dict[str, Any], message: str) -> None:
    data = example()
    data["fields"]["expiry_date"] = reading

    problems = rejected(data)

    assert len(problems) == 1
    assert problems[0].startswith("fields.expiry_date")
    assert message in problems[0]


@pytest.mark.parametrize("name", ["Surname", "document-number", "", "1st_name"])
def test_field_name_outside_catalog_field_pattern_is_rejected(name: str) -> None:
    data = example()
    data["fields"][name] = {"value": "VASILIEV", "legible": True}
    assert any(problem.startswith("fields") for problem in rejected(data))


def test_empty_fields_are_accepted() -> None:
    assert validate_page_analysis(example(fields={}), known_slugs=SLUGS).fields == {}


# --- 03.1.2 — dil ve alfabe ---------------------------------------------------------------


def test_iso_639_1_code_set_is_the_two_letter_registry() -> None:
    assert len(ISO_639_1_CODES) == 183
    assert all(len(code) == 2 and code.isascii() and code.islower() for code in ISO_639_1_CODES)
    assert {"bh", "iw", "in", "ji", "mo", "sh"}.isdisjoint(ISO_639_1_CODES)


@pytest.mark.parametrize("language", ["tr", "ru", "sr", "es", "en", "ar", "uk", "kk", "zh"])
def test_iso_639_1_language_is_accepted(language: str) -> None:
    analysis = validate_page_analysis(example(language=language), known_slugs=SLUGS)
    assert analysis.language == language


@pytest.mark.parametrize(
    "language", ["xx", "RU", "Ru", "rus", "ru-RU", "r", "", " ru", "sh", "iw", 7, True]
)
def test_language_outside_iso_639_1_is_rejected(language: object) -> None:
    problems = rejected(example(language=language))
    assert len(problems) == 1 and problems[0].startswith("language")


@pytest.mark.parametrize("script", ["latin", "cyrillic", "arabic", "other"])
def test_defined_script_is_accepted(script: str) -> None:
    analysis = validate_page_analysis(example(script=script), known_slugs=SLUGS)
    assert analysis.script == script
    assert isinstance(analysis.script, Script)


@pytest.mark.parametrize("script", ["greek", "Latin", "LATIN", "latn", "", 0])
def test_script_outside_defined_set_is_rejected(script: object) -> None:
    problems = rejected(example(script=script))
    assert len(problems) == 1 and problems[0].startswith("script")


def test_script_set_is_closed() -> None:
    assert [member.value for member in Script] == ["latin", "cyrillic", "arabic", "other"]


def test_page_without_text_may_leave_language_and_script_null() -> None:
    analysis = validate_page_analysis(example(language=None, script=None), known_slugs=SLUGS)
    assert (analysis.language, analysis.script) == (None, None)


# --- document_type_slug / candidate_type_name ---------------------------------------------


def test_slug_outside_the_catalog_is_rejected() -> None:
    problems = rejected(example(document_type_slug="bulgarian_passport"))
    assert problems == [
        "document_type_slug: 'bulgarian_passport' katalogda yok; katalog dışı tür için slug null, "
        "candidate_type_name dolu olmalı"
    ]


def test_slug_is_checked_against_the_given_catalog() -> None:
    assert rejected(example(), known_slugs=("serbian_passport",))
    assert validate_page_analysis(example(), known_slugs=["russian_passport"])


@pytest.mark.parametrize("slug", ["Russian_Passport", "russian-passport", "", 5])
def test_malformed_slug_is_rejected(slug: object) -> None:
    problems = rejected(example(document_type_slug=slug))
    assert len(problems) == 1 and problems[0].startswith("document_type_slug")


def test_unknown_type_carries_a_candidate_name_without_slug() -> None:
    data = example(document_type_slug=None, candidate_type_name="Bulgarian Passport")

    analysis = validate_page_analysis(data, known_slugs=SLUGS)

    assert analysis.document_type_slug is None
    assert analysis.candidate_type_name == "Bulgarian Passport"


def test_slug_and_candidate_name_together_are_rejected() -> None:
    problems = rejected(example(candidate_type_name="Russian Internal Passport"))
    assert problems == ["yanıt: candidate_type_name yalnız document_type_slug null iken dolar"]


def test_neither_slug_nor_candidate_name_is_accepted() -> None:
    data = example(document_type_slug=None, candidate_type_name=None)
    assert validate_page_analysis(data, known_slugs=SLUGS).document_type_slug is None


def test_ready_instance_is_still_checked_against_the_catalog() -> None:
    analysis = validate_page_analysis(SECTION_8_4_EXAMPLE, known_slugs=SLUGS)
    assert rejected(analysis, known_slugs=("serbian_passport",))


def test_stored_analysis_reloads_without_catalog_after_the_type_is_gone() -> None:
    stored = validate_page_analysis(SECTION_8_4_EXAMPLE, known_slugs=SLUGS).model_dump(mode="json")
    json.dumps(stored)  # `pages.analysis_json` JSON sütununa yazılabilir.

    reloaded = PageAnalysis.model_validate(stored)

    assert reloaded == validate_page_analysis(SECTION_8_4_EXAMPLE, known_slugs=SLUGS)
    assert rejected(stored, known_slugs=())


def test_python_dump_with_date_object_round_trips_but_datetime_does_not() -> None:
    analysis = validate_page_analysis(SECTION_8_4_EXAMPLE, known_slugs=SLUGS)
    dumped = analysis.model_dump()
    assert type(dumped["person"]["date_of_birth"]) is date

    assert validate_page_analysis(dumped, known_slugs=SLUGS) == analysis
    problems = rejected(with_person(date_of_birth=datetime(1990, 4, 12)))
    assert problems == [
        "person.date_of_birth: takvimde geçerli bir ISO 8601 tarihi (YYYY-AA-GG) olmalı"
    ]


# --- 03.1.3 — diğer isimler ---------------------------------------------------------------


def test_other_names_return_separately_from_given_names() -> None:
    data = with_person(given_names="DMITRY", other_names="IVANOVICH")

    person = validate_page_analysis(data, known_slugs=SLUGS).person

    assert person.given_names == "DMITRY"
    assert person.other_names == "IVANOVICH"


def test_employee_fields_are_employee_columns() -> None:
    assert set(EMPLOYEE_FIELDS) <= set(Employee.__table__.columns.keys())
    assert "other_names" in EMPLOYEE_FIELDS


def test_other_names_are_carried_to_the_employee_record(tmp_path: Path) -> None:
    data = with_person(given_names="DMITRY", other_names="IVANOVICH")
    person = validate_page_analysis(data, known_slugs=SLUGS).person
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'ai-test.db').as_posix()}")
    Base.metadata.create_all(engine)
    try:
        with create_session_factory(engine)() as session:
            session.add(
                Employee(
                    id="E0001", folder_name="Dmitry_Vasiliev_E0001", **person.employee_fields()
                )
            )
            session.commit()

        with create_session_factory(engine)() as session:
            employee = session.scalars(select(Employee)).one()
            assert employee.given_names == "DMITRY"
            assert employee.other_names == "IVANOVICH"
            assert employee.surname == "VASILIEV"
            assert employee.original_script_name == "Васильев Дмитрий"
            assert employee.date_of_birth == date(1990, 4, 12)
            assert employee.nationality == "RUS"
    finally:
        engine.dispose()


# --- 03.1.4 — iletişim bilgisi ------------------------------------------------------------


def test_contact_written_on_the_document_is_returned() -> None:
    contact = {"phone": "+381 11 123 4567", "email": "d.vasiliev@example.org", "address": "Beograd"}

    person = validate_page_analysis(with_person(contact=contact), known_slugs=SLUGS).person

    assert person.contact.model_dump() == contact


def test_contact_absent_from_the_document_stays_null() -> None:
    contact = dict.fromkeys(CONTACT_KEYS)

    person = validate_page_analysis(with_person(contact=contact), known_slugs=SLUGS).person

    assert person.contact.model_dump() == contact


@pytest.mark.parametrize("key", CONTACT_KEYS)
@pytest.mark.parametrize("value", ["", "  ", 38111123, ["+381"]])
def test_contact_value_outside_schema_is_rejected(key: str, value: object) -> None:
    data = example()
    data["person"]["contact"][key] = value
    problems = rejected(data)
    assert problems and all(problem.startswith(f"person.contact.{key}") for problem in problems)


def test_contact_keys_are_employee_contact_kinds() -> None:
    assert CONTACT_KEYS == [kind.value for kind in ContactKind]


# --- sözleşmenin sağlayıcıya dönük yüzü ---------------------------------------------------


def test_json_schema_requires_every_key_and_lists_closed_sets() -> None:
    schema = PageAnalysis.model_json_schema()
    defs = schema["$defs"]

    assert schema["required"] == TOP_LEVEL_KEYS
    assert defs["PagePerson"]["required"] == PERSON_KEYS
    assert defs["PageContact"]["required"] == CONTACT_KEYS
    assert defs["FieldReading"]["required"] == ["value", "legible"]
    for model in (schema, defs["PagePerson"], defs["PageContact"], defs["FieldReading"]):
        assert model["additionalProperties"] is False
    assert defs["Script"]["enum"] == ["latin", "cyrillic", "arabic", "other"]
    assert defs["Side"]["enum"] == ["front", "back", "single", "unknown"]
    language = schema["properties"]["language"]["anyOf"]
    assert language == [
        {"type": "string", "enum": sorted(ISO_639_1_CODES)},
        {"type": "null"},
    ]


def test_analysis_is_frozen() -> None:
    analysis = validate_page_analysis(SECTION_8_4_EXAMPLE, known_slugs=SLUGS)

    with pytest.raises(ValidationError):
        analysis.language = "sr"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        analysis.person.other_names = "IVANOVICH"  # type: ignore[misc]


def test_validation_does_not_modify_the_given_object() -> None:
    data = example()
    before = copy.deepcopy(data)

    validate_page_analysis(data, known_slugs=SLUGS)

    assert data == before
