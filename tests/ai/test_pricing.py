"""13.1.1 — yerleşik model fiyat tablosu ve fiyat çözümleme (PLAN.md §C77).

Tablo `app/ai/model_prices.yaml`'dır (benchlm.ai sağlayıcı sayfaları, 18 Eylül 2026). Değer
testleri sayfalardaki satırları birebir kilitler: tablo elle güncellenirken yanlış satıra yazılan
bir fiyat burada kırmızı olur. Ağ yoktur.
"""

from __future__ import annotations

import tomllib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.ai.pricing import (
    PRICE_RESOURCE,
    PriceBook,
    PriceSource,
    builtin_price_list,
    parse_price_list,
    price_book,
)
from app.config import ModelPrice, Settings

ROOT = Path(__file__).resolve().parents[2]


def _price(input_: str, output: str, cached: str | None = None) -> ModelPrice:
    return ModelPrice(
        input_per_mtok=Decimal(input_),
        output_per_mtok=Decimal(output),
        cached_input_per_mtok=None if cached is None else Decimal(cached),
    )


# --- yerleşik tablo ---------------------------------------------------------------------------


def test_builtin_table_names_its_sources_and_sync_date() -> None:
    price_list = builtin_price_list()

    assert price_list.synced == date(2026, 9, 18)
    assert price_list.sources == {
        "openai": "https://benchlm.ai/openai/api-pricing",
        "anthropic": "https://benchlm.ai/anthropic/api-pricing",
        "google": "https://benchlm.ai/google/api-pricing",
        "deepseek": "https://benchlm.ai/deepseek/api-pricing",
    }


def test_every_entry_belongs_to_a_listed_source_and_is_consistent() -> None:
    price_list = builtin_price_list()
    providers = {entry.provider for entry in price_list.models.values()}

    assert providers == set(price_list.sources)
    for key, entry in price_list.models.items():
        if entry.cached_input_per_mtok is not None:
            assert entry.cached_input_per_mtok <= entry.input_per_mtok, key
        # Sütun kayması koruması: sayfalardaki her modelde çıktı girdiden pahalıdır.
        assert entry.output_per_mtok >= entry.input_per_mtok, key


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        # OpenAI — sayfanın kendi API kimliğiyle
        ("gpt-6-luna", ("0.1", "0.5", "0.01")),
        ("gpt-5.6-luna", ("0.2", "1.2", "0.02")),
        ("gpt-5.6-terra", ("2", "12", "0.2")),
        ("gpt-5.6-sol", ("4", "20", "0.4")),
        ("gpt-5.5", ("5", "30", "0.5")),
        ("gpt-5.4-mini", ("0.75", "4.5", "0.075")),
        ("gpt-5.5-pro", ("30", "180", None)),
        ("gpt-6-astra", ("10", "50", "1")),
        ("gpt-6-sol", ("2", "10", "0.2")),
        # OpenAI — sayfada kimlik yok, türetildi
        ("gpt-4o", ("2.5", "10", None)),
        ("o3", ("2", "8", None)),
        ("gpt-5-nano", ("0.05", "0.4", None)),
        # Anthropic
        ("claude-fable-5-1", ("10", "50", "0.25")),
        ("claude-opus-5", ("5", "25", "0.5")),
        ("claude-sonnet-5", ("2", "10", "0.2")),
        ("claude-haiku-4-5", ("1", "5", "0.1")),
        ("claude-opus-4-8", ("5", "25", None)),
        ("claude-3-haiku", ("0.25", "1.25", None)),
        # Google
        ("gemini-3.1-pro-preview", ("2", "12", "0.2")),
        ("gemini-3.6-flash", ("1.5", "7.5", "0.15")),
        ("gemini-2.5-flash-lite", ("0.1", "0.4", "0.01")),
        # DeepSeek (yoğun saat; V4 Pro sayfanın yazdığı güncel birinci taraf fiyatı)
        ("deepseek-flash", ("0.3", "1.2", "0.006")),
        ("deepseek-v4-pro", ("1.32", "3.96", "0.044")),
        ("deepseek-chat", ("0.28", "0.42", "0.028")),
    ],
)
def test_builtin_prices_match_the_source_pages(
    model: str, expected: tuple[str, str, str | None]
) -> None:
    entry = builtin_price_list().models[model]

    assert (entry.input_per_mtok, entry.output_per_mtok, entry.cached_input_per_mtok) == (
        Decimal(expected[0]),
        Decimal(expected[1]),
        None if expected[2] is None else Decimal(expected[2]),
    )


def test_ids_from_the_page_and_derived_ids_are_told_apart() -> None:
    models = builtin_price_list().models

    assert models["gpt-5.6-luna"].id_source == "page"
    assert models["claude-opus-5"].id_source == "page"
    assert models["gpt-4o"].id_source == "derived"
    assert models["claude-opus-4-8"].id_source == "derived"


def test_every_model_the_application_can_be_configured_with_by_default_has_a_price() -> None:
    settings = Settings(database_url="sqlite://", _env_file=None)
    book = price_book(settings)

    # Kod varsayılanları ve bu kurulumun `.env`'deki modeli.
    for model in (settings.anthropic_model, settings.openai_model, "gpt-5.6-luna"):
        assert book.get(model) is not None, model


def test_table_ships_as_package_data() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert PRICE_RESOURCE in pyproject["tool"]["setuptools"]["package-data"]["app.ai"]


# --- tablo doğrulaması ------------------------------------------------------------------------

VALID = """
synced: 2026-09-18
sources: {openai: https://example.test/openai}
models:
  gpt-x:
    provider: openai
    name: GPT X
    input_per_mtok: "1"
    output_per_mtok: "2"
    id_source: page
"""


def test_a_valid_table_parses() -> None:
    price_list = parse_price_list(VALID)

    assert price_list.models["gpt-x"].output_per_mtok == Decimal(2)
    assert price_list.models["gpt-x"].cached_input_per_mtok is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("gpt-x:", "GPT-X:"), "geçersiz model adı"),
        (("gpt-x:", "gpt-x-20250101:"), "tarih ekiyle"),
        (('output_per_mtok: "2"', 'output_per_mtok: "-2"'), "greater than or equal"),
        (("id_source: page", "id_source: guessed"), "id_source"),
        (("id_source: page", "id_source: page\n    currency: TRY"), "currency"),
        (("synced: 2026-09-18", "synced: dün"), "synced"),
    ],
)
def test_a_broken_table_is_rejected(change: tuple[str, str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_price_list(VALID.replace(*change))


def test_unreadable_yaml_is_rejected() -> None:
    with pytest.raises(ValueError, match="YAML"):
        parse_price_list("models: [")


# --- çözümleme --------------------------------------------------------------------------------


def test_exact_name_resolves_from_the_builtin_table() -> None:
    resolved = PriceBook({}, builtin_price_list()).resolve("gpt-5.6-luna")

    assert resolved is not None
    assert (resolved.key, resolved.source) == ("gpt-5.6-luna", PriceSource.BUILTIN)
    assert resolved.price.input_per_mtok == Decimal("0.2")


@pytest.mark.parametrize(
    ("model", "key"),
    [
        ("claude-haiku-4-5-20251001", "claude-haiku-4-5"),
        ("gpt-4o-2024-08-06", "gpt-4o"),
        ("  GPT-5.6-Luna ", "gpt-5.6-luna"),
    ],
)
def test_dated_snapshot_and_case_resolve_to_the_base_model(model: str, key: str) -> None:
    resolved = PriceBook({}, builtin_price_list()).resolve(model)

    assert resolved is not None
    assert resolved.key == key
    assert resolved.model == model


@pytest.mark.parametrize("model", ["gpt-5.5-pro", "gpt-5.4-mini", "gemini-3-flash-preview"])
def test_suffixes_other_than_a_date_are_different_models(model: str) -> None:
    resolved = PriceBook({}, builtin_price_list()).resolve(model)

    assert resolved is not None
    assert resolved.key == model


@pytest.mark.parametrize("model", ["claude-test", "gpt-5.7", "", "gpt-5.6-luna-x"])
def test_unknown_model_has_no_price(model: str) -> None:
    book = PriceBook({}, builtin_price_list())

    assert book.resolve(model) is None
    assert book.get(model) is None


def test_env_price_wins_over_the_builtin_table() -> None:
    own = _price("1", "10")
    book = PriceBook({"GPT-5.6-Luna": own}, builtin_price_list())

    resolved = book.resolve("gpt-5.6-luna")

    assert resolved is not None
    assert (resolved.price, resolved.source) == (own, PriceSource.SETTINGS)


def test_undated_env_name_wins_over_the_undated_builtin_name() -> None:
    own = _price("3", "4")
    book = PriceBook({"claude-haiku-4-5": own}, builtin_price_list())

    assert book.get("claude-haiku-4-5-20251001") == own


def test_book_without_a_builtin_table_uses_only_the_env_prices() -> None:
    book = PriceBook({"gpt-x": _price("1", "2")})

    assert book.get("gpt-x") == _price("1", "2")
    assert book.get("gpt-5.6-luna") is None
    assert book.price_list is None
    assert bool(book)
    assert not PriceBook({})


def test_application_book_combines_env_and_builtin_prices() -> None:
    own = _price("7", "8")
    settings = Settings(database_url="sqlite://", ai_model_prices={"gpt-x": own}, _env_file=None)

    book = price_book(settings)

    assert book.get("gpt-x") == own
    assert book.get("claude-opus-5") is not None
    assert book.price_list is builtin_price_list()
