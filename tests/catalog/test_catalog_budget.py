"""11.4.3 — ölçekli katalog bütçesi: bütçe `CATALOG_TOKEN_BUDGET` ile ayarlanır, verilmezse aktif
analiz edilen tür sayısıyla ölçeklenir (`max(4000, 200 × tür)`); hedef her türün tanımının
kesilmeden talimata girmesidir. Kesme kuralı (11.4.2) değişmez.

Türler sentetiktir; sağlayıcı çağrısı yoktur.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from app.ai import build_page_analysis_instructions
from app.ai.prompts import build_training_classification_instructions
from app.catalog import (
    CATALOG_TOKEN_BUDGET,
    TOKENS_PER_TYPE,
    Catalog,
    compile_catalog,
    effective_token_budget,
    load_seed_catalog,
    validate_catalog,
)
from app.config import Settings, load_settings
from tests.catalog.conftest import RecordFactory

LOGGER = "app.catalog.prompt_builder"
SEED = load_seed_catalog()
DOC_KINDS = ("passport", "id_card")

# Gerçekçi bir analizci tanımı (~150 karakter): tür başına pay bunun için seçildi (PLAN.md §C88).
DESCRIPTION = (
    "Kartın üst kenarında ülke adı ve arması, sol yanda vesikalık fotoğraf, sağ yanda numaralı "
    "alanlar ve altta iki satırlık makine okunur bölge bulunur."
)


def synthetic_catalog(make_record: RecordFactory, count: int, **overrides: Any) -> Catalog:
    return validate_catalog(
        [
            make_record(
                slug=f"type_{index:03d}",
                name=f"Sentetik Tür {index:03d}",
                prompt_description=DESCRIPTION,
                acceptance_criteria=["Kenarlar görünür", "Yüz net"],
                **overrides,
            )
            for index in range(count)
        ]
    )


# --- etkin bütçe ------------------------------------------------------------------------------


def test_small_catalog_keeps_the_seed_budget_as_the_floor(make_record: RecordFactory) -> None:
    assert len([entry for entry in SEED if entry.active and entry.analyze]) <= 20
    assert effective_token_budget(SEED) == CATALOG_TOKEN_BUDGET == 4000
    assert effective_token_budget(synthetic_catalog(make_record, 8)) == 4000
    assert effective_token_budget(synthetic_catalog(make_record, 20)) == 4000
    assert effective_token_budget(validate_catalog([])) == 4000


def test_budget_grows_with_the_number_of_analyzed_active_types(make_record: RecordFactory) -> None:
    assert TOKENS_PER_TYPE == 200
    assert effective_token_budget(synthetic_catalog(make_record, 21)) == 4200
    assert effective_token_budget(synthetic_catalog(make_record, 100)) == 20000
    assert effective_token_budget(synthetic_catalog(make_record, 400)) == 80000


def test_passive_and_not_analyzed_types_do_not_grow_the_budget(make_record: RecordFactory) -> None:
    active = [
        make_record(slug=f"active_{index:03d}", prompt_description=DESCRIPTION)
        for index in range(30)
    ]
    passive = [
        make_record(slug=f"passive_{index:03d}", active=False, prompt_description=DESCRIPTION)
        for index in range(40)
    ]
    skipped = [
        make_record(
            slug=f"skipped_{index:03d}",
            analyze=False,
            required_fields=[],
            expected_file_types=["docx"],
            allowed_conversions=[],
            output_format="keep",
            direct=True,
        )
        for index in range(40)
    ]

    catalog = validate_catalog([*active, *passive, *skipped])

    assert effective_token_budget(catalog) == 30 * TOKENS_PER_TYPE


def test_a_configured_budget_is_used_as_given(make_record: RecordFactory) -> None:
    catalog = synthetic_catalog(make_record, 100)

    assert effective_token_budget(catalog, 1500) == 1500
    assert effective_token_budget(catalog, 250_000) == 250_000


# --- ayar (00.2: isteğe bağlı, varsayılan yerleşik) --------------------------------------------


def test_setting_is_unset_by_default() -> None:
    assert Settings(_env_file=None, database_url="sqlite://").catalog_token_budget is None


def test_setting_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("CATALOG_TOKEN_BUDGET", "12000")

    assert load_settings(_env_file=None).catalog_token_budget == 12000


def test_blank_setting_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("CATALOG_TOKEN_BUDGET", " ")

    assert load_settings(_env_file=None).catalog_token_budget is None


@pytest.mark.parametrize("value", ["0", "-5", "çok"])
def test_setting_must_be_a_positive_number(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("CATALOG_TOKEN_BUDGET", value)

    with pytest.raises(ValueError, match="catalog_token_budget"):
        load_settings(_env_file=None)


# --- derleme: ölçekli bütçe tanımları kesmez -----------------------------------------------------


def test_a_hundred_types_compile_with_every_description_whole(
    make_record: RecordFactory, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER)
    catalog = synthetic_catalog(make_record, 100)

    compiled = compile_catalog(catalog, token_budget=effective_token_budget(catalog))

    assert compiled.token_budget == 20000
    assert compiled.shortened_slugs == ()
    assert not compiled.over_budget
    assert compiled.text.count(f"- Tanım: {DESCRIPTION}") == 100
    assert caplog.records == []
    # Aynı küme 11.4.2'nin sabit bütçesinde tanımlarını yitirirdi.
    assert compile_catalog(catalog).shortened_slugs


def test_the_cutting_rule_is_unchanged_when_the_budget_is_too_small(
    make_record: RecordFactory, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER)
    catalog = synthetic_catalog(make_record, 100)

    compiled = compile_catalog(catalog, token_budget=effective_token_budget(catalog, 5000))

    assert compiled.token_budget == 5000
    assert len(compiled.shortened_slugs) == 100
    # Alanlar ve kabul kriterleri kesilmez; hiçbir tür düşmez.
    assert compiled.text.count("- Zorunlu alanlar: `surname`, `document_number`") == 100
    assert compiled.text.count("  - Kenarlar görünür") == 100
    assert len(compiled.known_slugs) == 100
    assert [record.name for record in caplog.records] == [LOGGER]


def test_compiling_only_to_show_the_state_logs_nothing(
    make_record: RecordFactory, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=LOGGER)
    catalog = synthetic_catalog(make_record, 100)

    quiet = compile_catalog(catalog, token_budget=1000, warn=False)

    assert quiet.shortened_slugs
    assert quiet == compile_catalog(catalog, token_budget=1000)
    assert [record.name for record in caplog.records] == [LOGGER]  # yalnız ikinci derleme


# --- talimat: etkin bütçeyle kurulur -------------------------------------------------------------


def test_page_analysis_instructions_use_the_scaled_budget_by_default(
    make_record: RecordFactory,
) -> None:
    catalog = synthetic_catalog(make_record, 100)
    expected = compile_catalog(catalog, token_budget=20000)

    instructions = build_page_analysis_instructions(catalog)

    assert expected.text in instructions.text
    assert expected.shortened_slugs == ()
    assert instructions.catalog_tokens == expected.estimated_tokens
    assert instructions.known_slugs == expected.known_slugs


def test_page_analysis_instructions_follow_the_configured_budget(
    make_record: RecordFactory,
) -> None:
    catalog = synthetic_catalog(make_record, 100)
    expected = compile_catalog(catalog, token_budget=5000)

    instructions = build_page_analysis_instructions(catalog, configured_budget=5000)

    assert expected.shortened_slugs
    assert expected.text in instructions.text
    assert instructions.catalog_tokens == expected.estimated_tokens


def test_an_explicit_budget_still_wins(make_record: RecordFactory) -> None:
    catalog = synthetic_catalog(make_record, 100)

    instructions = build_page_analysis_instructions(
        catalog, token_budget=3000, configured_budget=50_000
    )

    assert compile_catalog(catalog, token_budget=3000).text in instructions.text


def test_seed_instructions_are_unchanged_by_the_scaling() -> None:
    before = compile_catalog(SEED, token_budget=CATALOG_TOKEN_BUDGET)

    instructions = build_page_analysis_instructions(SEED)

    assert before.text in instructions.text
    assert instructions.catalog_tokens == before.estimated_tokens


def test_training_instructions_share_the_budget_of_the_page_analysis(
    make_record: RecordFactory,
) -> None:
    catalog = synthetic_catalog(make_record, 100)

    scaled = build_training_classification_instructions(catalog, DOC_KINDS)
    configured = build_training_classification_instructions(
        catalog, DOC_KINDS, configured_budget=5000
    )

    assert compile_catalog(catalog, token_budget=20000).text in scaled.text
    assert compile_catalog(catalog, token_budget=5000).text in configured.text
