"""11.1.2, 11.1.3 — tür formu katalog sözleşmesinden geçer: Direkt türde dönüşüm listesi boş,
`front_back` türde sayfa aralığı 2; kabul kriteri maddeleri madde madde düzenlenir."""

from typing import Any

import pytest

from app.catalog import (
    Sides,
    TypeForm,
    TypeFormError,
    build_entry,
    load_seed_catalog,
    validate_catalog,
)
from app.catalog.form import clean_criteria, split_field_names


def _form(**overrides: Any) -> TypeForm:
    values: dict[str, Any] = {
        "slug": "sample_card",
        "name": "Sample Card",
        "file_label": "Sample Card",
        "expected_file_types": ("pdf",),
        "sides": "single",
        "required_fields": "surname, document_number",
        "output_format": "pdf",
    }
    values.update(overrides)
    return TypeForm(**values)


def _problems(**overrides: Any) -> dict[str, list[str]]:
    with pytest.raises(TypeFormError) as caught:
        build_entry(_form(**overrides))
    return caught.value.problems


# --- 11.1.2: alanlar arası kurallar --------------------------------------------------------------


@pytest.mark.parametrize("conversion", ["merge", "wrap_image", "extract_image", "render_image"])
def test_direct_type_with_any_conversion_is_refused_on_the_conversions_field(
    conversion: str,
) -> None:
    problems = _problems(direct=True, allowed_conversions=(conversion,))

    assert list(problems) == ["allowed_conversions"]
    (message,) = problems["allowed_conversions"]
    assert "Direkt Belge" in message
    assert "allowed_conversions boş olmalı" in message
    assert conversion in message


def test_direct_type_with_an_empty_conversion_list_is_accepted() -> None:
    entry = build_entry(_form(direct=True, allowed_conversions=()))

    assert entry.direct is True
    assert entry.allowed_conversions == ()


def test_indirect_type_may_carry_conversions() -> None:
    entry = build_entry(_form(direct=False, allowed_conversions=("merge", "wrap_image")))

    assert [conversion.value for conversion in entry.allowed_conversions] == [
        "merge",
        "wrap_image",
    ]


@pytest.mark.parametrize(
    ("low", "high"),
    [("1", "1"), ("1", "2"), ("2", "3"), ("3", "3"), ("1", "10")],
)
def test_front_back_type_needs_exactly_two_pages(low: str, high: str) -> None:
    problems = _problems(sides="front_back", pages_min=low, pages_max=high)

    assert list(problems) == ["expected_pages"]
    (message,) = problems["expected_pages"]
    assert "front_back" in message
    assert "tam iki sayfa" in message
    assert f"{low}-{high}" in message


def test_front_back_type_without_a_page_range_is_refused() -> None:
    problems = _problems(sides="front_back", pages_min="", pages_max="")

    assert "yazılmamış" in problems["expected_pages"][0]


def test_front_back_type_with_two_pages_is_accepted() -> None:
    entry = build_entry(_form(sides="front_back", pages_min="2", pages_max="2"))

    assert entry.sides is Sides.FRONT_BACK
    assert (entry.expected_pages.min, entry.expected_pages.max) == (2, 2)  # type: ignore[union-attr]


def test_single_sided_type_may_have_any_page_range_or_none() -> None:
    assert build_entry(_form(pages_min="1", pages_max="5")).expected_pages is not None
    assert build_entry(_form(pages_min="", pages_max="")).expected_pages is None


def test_unanalyzed_type_cannot_list_required_fields() -> None:
    problems = _problems(analyze=False, required_fields="surname")

    assert list(problems) == ["required_fields"]
    assert "analyze: false" in problems["required_fields"][0]


def test_every_rule_is_reported_at_once_each_on_its_own_field() -> None:
    problems = _problems(
        direct=True,
        allowed_conversions=("merge",),
        sides="front_back",
        pages_min="1",
        pages_max="1",
        analyze=False,
        required_fields="surname",
    )

    assert set(problems) == {"allowed_conversions", "expected_pages", "required_fields"}


def test_the_page_rule_is_a_form_rule_and_catalog_loading_keeps_accepting_older_ranges(
    make_record: Any,
) -> None:
    # 11.1.2 yalnız form doğrulamasıdır: eski bir katalog/veritabanı kaydı yüzünden analiz
    # kataloğu okunamaz olmasın (00.6.1 davranışı değişmedi). Kayıt formdan geçince düzelir.
    record = make_record(slug="two_sided", sides="front_back", expected_pages={"min": 1, "max": 2})

    (entry,) = validate_catalog([record])

    assert entry.sides is Sides.FRONT_BACK
    assert (entry.expected_pages.min, entry.expected_pages.max) == (1, 2)  # type: ignore[union-attr]
    with pytest.raises(TypeFormError) as caught:
        build_entry(TypeForm.from_record(entry.model_dump(mode="json")))
    assert set(caught.value.problems) == {"expected_pages"}


# --- alan doğrulaması ----------------------------------------------------------------------------


def test_valid_form_becomes_a_catalog_entry_with_trimmed_values() -> None:
    entry = build_entry(
        _form(
            slug=" sample_card ",
            name="  Sample Card ",
            country="rs",
            description="  ",
            prompt_description=" Kimlik kartı ",
            expected_file_types=("pdf", "jpeg"),
            pages_min="1",
            pages_max="2",
            required_fields="surname\ngiven_names, document_number;expiry_date",
            allowed_conversions=("merge",),
        )
    )

    assert entry.slug == "sample_card"
    assert entry.name == "Sample Card"
    assert entry.country == "RS"
    assert entry.description is None
    assert entry.prompt_description == "Kimlik kartı"
    assert entry.required_fields == ("surname", "given_names", "document_number", "expiry_date")
    assert entry.active is True
    assert entry.photo_rules is None


def test_blank_optional_fields_are_left_out() -> None:
    entry = build_entry(_form(country="", description="", prompt_description=""))

    assert (entry.country, entry.description, entry.prompt_description) == (None, None, None)


@pytest.mark.parametrize("slug", ["", "Upper", "1abc", "has space", "türkçe", "a" * 65, "a-b"])
def test_slug_must_be_a_lowercase_identifier(slug: str) -> None:
    problems = _problems(slug=slug)

    assert "slug" in problems


def test_reserved_slug_is_refused_because_it_is_the_new_type_address() -> None:
    (message,) = _problems(slug="new")["slug"]

    assert "ayrılmış" in message


@pytest.mark.parametrize("field", ["name", "file_label"])
def test_name_and_file_label_are_required(field: str) -> None:
    assert _problems(**{field: "   "})[field] == ["boş olamaz"]


def test_over_long_name_is_refused_with_the_limit() -> None:
    assert _problems(name="x" * 256)["name"] == ["en çok 255 karakter olmalı"]


def test_file_label_must_make_a_file_name() -> None:
    assert "dosya adına çevrilemiyor" in _problems(file_label="???")["file_label"][0]


@pytest.mark.parametrize("country", ["R", "RUS", "1A"])
def test_country_must_be_two_letters(country: str) -> None:
    assert "country" in _problems(country=country)


def test_at_least_one_file_type_is_needed() -> None:
    assert _problems(expected_file_types=())["expected_file_types"] == ["en az bir seçim yapılmalı"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sides", "double"),
        ("output_format", "png"),
        ("expected_file_types", ("pdf", "zip")),
        ("allowed_conversions", ("passthrough",)),
    ],
)
def test_unknown_choices_are_refused(field: str, value: Any) -> None:
    assert _problems(**{field: value})[field] == ["geçersiz seçim"]


def test_required_field_names_are_checked_one_by_one() -> None:
    (message,) = _problems(required_fields="surname, Given-Names")["required_fields"]

    assert "'Given-Names'" in message


def test_duplicate_required_fields_are_refused() -> None:
    (message,) = _problems(required_fields="surname, surname")["required_fields"]

    assert "Tekrarlanan değer: surname" in message


@pytest.mark.parametrize(
    ("low", "high", "fragment"),
    [
        ("1", "", "birlikte"),
        ("", "2", "birlikte"),
        ("a", "2", "tam sayı"),
        ("1.5", "2", "tam sayı"),
        ("-1", "2", "tam sayı"),
        ("١", "2", "tam sayı"),  # Arap-Hint rakamı (isdigit doğru, ASCII değil)
    ],
)
def test_unreadable_page_numbers_are_reported_alone(low: str, high: str, fragment: str) -> None:
    problems = _problems(sides="front_back", pages_min=low, pages_max=high)

    # `front_back` için türeyen "aralık yok" mesajı asıl sorunu gölgelemez.
    assert len(problems["expected_pages"]) == 1
    assert fragment in problems["expected_pages"][0]


@pytest.mark.parametrize(("low", "high"), [("0", "1"), ("3", "2")])
def test_page_range_must_be_positive_and_ordered(low: str, high: str) -> None:
    assert "expected_pages" in _problems(pages_min=low, pages_max=high)


def test_rejection_message_names_every_field() -> None:
    with pytest.raises(TypeFormError, match="- name: boş olamaz") as caught:
        build_entry(_form(name="", slug="Bad"))

    assert "- slug:" in str(caught.value)


# --- 11.1.3: kabul kriteri maddeleri -------------------------------------------------------------


def test_blank_criteria_are_dropped_and_the_order_is_kept() -> None:
    entry = build_entry(_form(acceptance_criteria=(" ilk ", "", "   ", "ikinci")))

    assert entry.acceptance_criteria == ("ilk", "ikinci")


def test_no_criteria_is_valid() -> None:
    assert build_entry(_form(acceptance_criteria=("",))).acceptance_criteria == ()


def test_clean_criteria_and_split_field_names_helpers() -> None:
    assert clean_criteria(["  a ", "", "b"]) == ("a", "b")
    assert split_field_names(" a,b ;\n c ,, ") == ("a", "b", "c")
    assert split_field_names("") == ()


# --- form ↔ kayıt gidiş dönüşü -------------------------------------------------------------------


def test_every_seed_type_survives_the_form_round_trip() -> None:
    seed = load_seed_catalog()

    for entry in seed:
        rebuilt = build_entry(TypeForm.from_record(entry.model_dump(mode="json")))
        # `active` ve `photo_rules` formdan değişmez (pasifleştirme ayrı işlem, kurallar 11.6).
        left = entry.model_dump(exclude={"active", "photo_rules"})
        assert rebuilt.model_dump(exclude={"active", "photo_rules"}) == left, entry.slug


def test_form_opens_an_inconsistent_stored_record_instead_of_failing() -> None:
    record = {
        "slug": "broken_type",
        "name": "Broken",
        "file_label": "Broken",
        "country": None,
        "description": None,
        "expected_file_types": ["pdf"],
        "expected_pages": None,
        "sides": "front_back",
        "direct": True,
        "analyze": True,
        "required_fields": ["surname"],
        "allowed_conversions": ["merge"],
        "output_format": "keep",
        "acceptance_criteria": None,
        "prompt_description": None,
    }

    form = TypeForm.from_record(record)

    assert (form.direct, form.allowed_conversions, form.pages_min) == (True, ("merge",), "")
    assert form.acceptance_criteria == ()
    assert set(_form_problems(form)) == {"allowed_conversions", "expected_pages"}


def _form_problems(form: TypeForm) -> dict[str, list[str]]:
    with pytest.raises(TypeFormError) as caught:
        build_entry(form)
    return caught.value.problems
