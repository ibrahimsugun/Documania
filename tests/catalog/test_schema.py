"""00.6.1 — katalog şeması §8.6'nın tüm alanlarını tanımlar; Direkt Belge türünde dönüşüm
listesi doluysa katalog yüklemesi reddedilir."""

from typing import Any

import pytest
from sqlalchemy import inspect

from app.catalog import (
    CatalogEntry,
    CatalogError,
    Conversion,
    FileType,
    OutputFormat,
    PageRange,
    Sides,
    parse_catalog_yaml,
    validate_catalog,
)
from app.catalog.sync import entry_to_columns
from app.db.models import KnownDocumentType
from tests.catalog.conftest import RecordFactory

# PRD §8.6 örneği, harfiyen.
SECTION_8_6_EXAMPLE = """\
- slug: russian_passport
  name: Russian Passport
  file_label: Passport
  country: RU
  expected_file_types: [pdf, jpeg]
  expected_pages: {min: 1, max: 1}
  sides: single
  direct: true
  analyze: true
  required_fields: [surname, given_names, date_of_birth, document_number, expiry_date]
  allowed_conversions: []
  output_format: keep
  acceptance_criteria:
    - "Kimlik sayfası tam görünür olmalı, kenarlar kesilmemiş"
    - "MRZ iki satırı da okunabilir olmalı"
  prompt_description: >
    Kiril ve Latin çift yazımlı kimlik sayfası, sağ altta iki satır MRZ.
"""

SECTION_8_6_FIELDS = {
    "slug",
    "name",
    "file_label",
    "country",
    "expected_file_types",
    "expected_pages",
    "sides",
    "direct",
    "analyze",
    "required_fields",
    "allowed_conversions",
    "output_format",
    "acceptance_criteria",
    "prompt_description",
}
# §8.1 `known_document_types` tablosunda olup §8.6 örneğinde geçmeyen alanlar.
SECTION_8_1_ONLY_FIELDS = {"description", "photo_rules", "active"}


def test_schema_defines_every_section_8_6_field() -> None:
    assert set(CatalogEntry.model_fields) == SECTION_8_6_FIELDS | SECTION_8_1_ONLY_FIELDS
    assert "acceptance_criteria" in CatalogEntry.model_fields


def test_schema_covers_every_known_document_types_column(make_record: RecordFactory) -> None:
    entry = CatalogEntry.model_validate(make_record())
    columns = {column.key for column in inspect(KnownDocumentType).columns}

    assert set(entry_to_columns(entry)) | {"slug"} == columns


def test_section_8_6_example_parses_verbatim() -> None:
    (entry,) = parse_catalog_yaml(SECTION_8_6_EXAMPLE)

    assert entry == CatalogEntry(
        slug="russian_passport",
        name="Russian Passport",
        file_label="Passport",
        country="RU",
        expected_file_types=(FileType.PDF, FileType.JPEG),
        expected_pages=PageRange(min=1, max=1),
        sides=Sides.SINGLE,
        direct=True,
        analyze=True,
        required_fields=(
            "surname",
            "given_names",
            "date_of_birth",
            "document_number",
            "expiry_date",
        ),
        allowed_conversions=(),
        output_format=OutputFormat.KEEP,
        acceptance_criteria=(
            "Kimlik sayfası tam görünür olmalı, kenarlar kesilmemiş",
            "MRZ iki satırı da okunabilir olmalı",
        ),
        prompt_description="Kiril ve Latin çift yazımlı kimlik sayfası, sağ altta iki satır MRZ.",
    )
    assert entry.description is None
    assert entry.photo_rules is None
    assert entry.active is True


def test_optional_fields_have_documented_defaults(make_record: RecordFactory) -> None:
    entry = CatalogEntry.model_validate(make_record())

    assert entry.acceptance_criteria == ()  # boşsa tek ölçüt K1 (§8.6)
    assert entry.prompt_description is None
    assert entry.active is True


@pytest.mark.parametrize("conversions", [["merge"], ["wrap_image", "render_image"]])
def test_direct_type_with_conversions_rejects_whole_catalog(
    make_record: RecordFactory, conversions: list[str]
) -> None:
    valid = make_record(slug="valid_type")
    direct = make_record(slug="direct_type", direct=True, allowed_conversions=conversions)

    with pytest.raises(CatalogError) as caught:
        validate_catalog([valid, direct])

    (problem,) = caught.value.problems
    assert problem.startswith("kayıt #2 (direct_type)")
    assert "direct: true" in problem
    assert "allowed_conversions boş olmalı" in problem


def test_direct_type_with_empty_conversions_is_accepted(make_record: RecordFactory) -> None:
    (entry,) = validate_catalog([make_record(direct=True, allowed_conversions=[])])

    assert entry.direct is True
    assert entry.allowed_conversions == ()


def test_non_direct_type_may_allow_every_conversion(make_record: RecordFactory) -> None:
    every = [conversion.value for conversion in Conversion]

    (entry,) = validate_catalog([make_record(allowed_conversions=every)])

    assert entry.allowed_conversions == tuple(Conversion)


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"direct": None}, "direct"),
        ({"direct": "true"}, "direct"),
        ({"analyze": 1}, "analyze"),
        ({"slug": "Russian Passport"}, "slug"),
        ({"slug": ""}, "slug"),
        ({"name": "  "}, "name"),
        ({"file_label": "★★★"}, "file_label dosya adına çevrilemiyor"),
        ({"country": "rs"}, "country"),
        ({"country": False}, "country"),  # YAML 1.1: `country: NO` → False
        ({"expected_file_types": []}, "expected_file_types"),
        ({"expected_file_types": ["jpg"]}, "expected_file_types"),
        ({"expected_file_types": ["pdf", "pdf"]}, "Tekrarlanan değer: pdf"),
        ({"expected_pages": {"min": 2, "max": 1}}, "min (2) max'tan (1) büyük olamaz"),
        ({"expected_pages": {"min": 0, "max": 1}}, "expected_pages.min"),
        ({"expected_pages": {"min": 1}}, "expected_pages.max"),
        ({"expected_pages": {"min": True, "max": 1}}, "expected_pages.min"),
        ({"sides": "double"}, "sides"),
        ({"required_fields": ["Document Number"]}, "required_fields"),
        ({"required_fields": ["surname", "surname"]}, "Tekrarlanan değer: surname"),
        ({"allowed_conversions": ["extract"]}, "allowed_conversions"),
        ({"allowed_conversions": ["passthrough"]}, "allowed_conversions"),
        ({"allowed_conversions": ["merge", "merge"]}, "Tekrarlanan değer: merge"),
        ({"output_format": "png"}, "output_format"),
        ({"acceptance_criteria": [""]}, "acceptance_criteria"),
        ({"acceptance_criteria": "MRZ okunmalı"}, "acceptance_criteria"),
        ({"photo_rules": ["yüz"]}, "photo_rules"),
        ({"allowed_conversion": []}, "allowed_conversion"),  # yazım hatası sessizce geçmez
        ({"analyze": False}, "analyze: false olan türde required_fields boş olmalı"),
    ],
)
def test_invalid_entry_is_rejected(
    make_record: RecordFactory, overrides: dict[str, Any], fragment: str
) -> None:
    with pytest.raises(CatalogError) as caught:
        validate_catalog([make_record(**overrides)])

    assert any(fragment in problem for problem in caught.value.problems), caught.value.problems


@pytest.mark.parametrize("missing", ["slug", "direct", "required_fields", "allowed_conversions"])
def test_required_field_must_be_written(make_record: RecordFactory, missing: str) -> None:
    record = make_record()
    del record[missing]

    with pytest.raises(CatalogError, match=missing):
        validate_catalog([record])


def test_duplicate_slug_rejects_catalog(make_record: RecordFactory) -> None:
    with pytest.raises(CatalogError, match="slug katalogda tekil olmalı. Tekrarlanan değer: dup"):
        validate_catalog([make_record(slug="dup"), make_record(slug="dup", name="Other")])


@pytest.mark.parametrize("root", [None, {"slug": "x"}, "russian_passport"])
def test_catalog_root_must_be_a_list(root: object) -> None:
    with pytest.raises(CatalogError, match="Katalog kökü kayıt listesi olmalı"):
        validate_catalog(root)


def test_every_problem_is_reported(make_record: RecordFactory) -> None:
    records = [
        make_record(slug="first", sides="double"),
        make_record(slug="second", direct=True),
    ]

    with pytest.raises(CatalogError) as caught:
        validate_catalog(records)

    problems = caught.value.problems
    assert len(problems) == 2
    assert problems[0].startswith("kayıt #1 (first) sides")
    assert problems[1].startswith("kayıt #2 (second)")
    assert str(caught.value).startswith("Katalog reddedildi:\n- kayıt #1")


def test_catalog_lookup_helpers(make_record: RecordFactory) -> None:
    catalog = validate_catalog([make_record(slug="a_type"), make_record(slug="b_type")])

    assert len(catalog) == 2
    assert catalog.slugs() == ("a_type", "b_type")
    assert catalog.get("b_type") is not None
    assert catalog.get("missing") is None


def test_entries_are_immutable(make_record: RecordFactory) -> None:
    entry = CatalogEntry.model_validate(make_record())

    with pytest.raises(ValueError):
        entry.direct = True  # type: ignore[misc]
