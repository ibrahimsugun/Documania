"""13.1.1 — token kullanımı ölçümü: `TokenUsage`, ölçüm bağlamı ve maliyet hesabı; iki somut
sağlayıcının yanıttaki sayıları bildirmesi (ağ yok: `httpx2.MockTransport`)."""

from __future__ import annotations

import threading
from decimal import Decimal

import httpx2
import pytest

from app.ai import PageAnalysisError, ProviderError
from app.ai.usage import TokenUsage, measure_usage, report_usage, token_cost
from app.config import ModelPrice
from tests.ai import test_anthropic_provider as anthropic_tests
from tests.ai import test_openai_provider as openai_tests
from tests.ai.payloads import analysis_payload, page_request

# --- TokenUsage -------------------------------------------------------------------------------


def test_usage_adds_and_totals() -> None:
    usage = TokenUsage(1200, 300) + TokenUsage(800, 200)

    assert usage == TokenUsage(2000, 500)
    assert usage.total_tokens == 2500
    assert TokenUsage() == TokenUsage(0, 0)


@pytest.mark.parametrize("bad", [-1, 1.5, "12", None, True])
def test_usage_rejects_anything_but_a_non_negative_integer(bad: object) -> None:
    with pytest.raises(ValueError, match="input_tokens"):
        TokenUsage(bad, 0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="output_tokens"):
        TokenUsage(0, bad)  # type: ignore[arg-type]


def test_usage_round_trips_through_event_data() -> None:
    usage = TokenUsage(1200, 300)

    assert usage.to_event_data() == {"input_tokens": 1200, "output_tokens": 300}
    assert TokenUsage.from_event_data(usage.to_event_data()) == usage


@pytest.mark.parametrize(
    "data",
    [
        None,
        "1200",
        [],
        {},
        {"input_tokens": 1},
        {"input_tokens": 1, "output_tokens": "2"},
        {"input_tokens": -1, "output_tokens": 2},
    ],
)
def test_missing_or_broken_event_data_reads_as_unmeasured(data: object) -> None:
    assert TokenUsage.from_event_data(data) is None


# --- ölçüm bağlamı ----------------------------------------------------------------------------


def test_meter_sums_reports_and_counts_calls() -> None:
    with measure_usage() as meter:
        report_usage(1000, 100)
        report_usage(200, 50)

    assert meter.usage == TokenUsage(1200, 150)
    assert meter.calls == 2


def test_report_outside_a_meter_is_ignored() -> None:
    report_usage(1000, 100)

    with measure_usage() as meter:
        pass
    assert meter.calls == 0
    assert meter.usage == TokenUsage()


def test_report_after_the_block_does_not_reach_the_meter() -> None:
    with measure_usage() as meter:
        report_usage(10, 1)
    report_usage(999, 999)

    assert meter.usage == TokenUsage(10, 1)


def test_nested_meters_both_count() -> None:
    with measure_usage() as outer:
        report_usage(1, 1)
        with measure_usage() as inner:
            report_usage(10, 10)
        report_usage(100, 100)

    assert inner.usage == TokenUsage(10, 10)
    assert outer.usage == TokenUsage(111, 111)


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens"), [(None, 5), (5, None), (-1, 5), ("5", 5), (1.5, 5)]
)
def test_unusable_numbers_are_not_reported_as_zero(
    input_tokens: object, output_tokens: object
) -> None:
    with measure_usage() as meter:
        report_usage(input_tokens, output_tokens)

    assert meter.calls == 0
    assert meter.usage == TokenUsage()


def test_meters_of_concurrent_threads_do_not_mix() -> None:
    seen: dict[str, TokenUsage] = {}
    barrier = threading.Barrier(2)

    def work(name: str, tokens: int) -> None:
        with measure_usage() as meter:
            barrier.wait()
            report_usage(tokens, tokens)
            barrier.wait()
        seen[name] = meter.usage

    threads = [
        threading.Thread(target=work, args=("a", 7)),
        threading.Thread(target=work, args=("b", 900)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert seen == {"a": TokenUsage(7, 7), "b": TokenUsage(900, 900)}


# --- maliyet ----------------------------------------------------------------------------------


def test_cost_is_tokens_times_price_per_million() -> None:
    price = ModelPrice(input_per_mtok=Decimal(5), output_per_mtok=Decimal(25))

    assert token_cost(TokenUsage(1_000_000, 1_000_000), price) == Decimal(30)
    assert token_cost(TokenUsage(1200, 300), price) == Decimal("0.0135")
    assert token_cost(TokenUsage(), price) == Decimal(0)


def test_price_rejects_negative_and_unknown_fields() -> None:
    with pytest.raises(ValueError):
        ModelPrice(input_per_mtok=Decimal(-1), output_per_mtok=Decimal(1))
    with pytest.raises(ValueError):
        ModelPrice.model_validate({"input_per_mtok": 1, "output_per_mtok": 1, "currency": "TRY"})


# --- sağlayıcılar yanıttaki sayıları bildirir -------------------------------------------------


def test_anthropic_reports_input_and_output_tokens() -> None:
    api = anthropic_tests.FakeApi(
        anthropic_tests.message([anthropic_tests.tool_use(analysis_payload())])
    )

    with measure_usage() as meter:
        api.provider().analyze_page(page_request())

    assert meter.usage == TokenUsage(1200, 300)
    assert meter.calls == 1


def test_anthropic_reports_tokens_of_a_rejected_response() -> None:
    api = anthropic_tests.FakeApi(
        anthropic_tests.message(
            [anthropic_tests.tool_use({"page_index": 0})], stop_reason="max_tokens"
        )
    )

    with measure_usage() as meter, pytest.raises(PageAnalysisError):
        api.provider().analyze_page(page_request())

    assert meter.usage == TokenUsage(1200, 300)


def test_anthropic_failed_call_reports_nothing() -> None:
    api = anthropic_tests.FakeApi(anthropic_tests.api_error(401, "authentication_error"))

    with measure_usage() as meter, pytest.raises(ProviderError, match="401"):
        api.provider().analyze_page(page_request())

    assert meter.calls == 0


def test_anthropic_response_without_usage_reports_nothing() -> None:
    response = anthropic_tests.message([anthropic_tests.tool_use(analysis_payload())])
    body = response.json()
    del body["usage"]
    api = anthropic_tests.FakeApi(httpx2.Response(200, json=body))

    with measure_usage() as meter:
        api.provider().analyze_page(page_request())

    assert meter.calls == 0


def test_openai_reports_prompt_and_completion_tokens() -> None:
    api = openai_tests.FakeApi(
        openai_tests.completion(tool_calls=[openai_tests.function_call(analysis_payload())])
    )

    with measure_usage() as meter:
        api.provider().analyze_page(page_request())

    assert meter.usage == TokenUsage(1200, 300)
    assert meter.calls == 1


def test_openai_reports_tokens_of_a_rejected_response() -> None:
    api = openai_tests.FakeApi(openai_tests.completion(tool_calls=[], finish_reason="stop"))

    with measure_usage() as meter, pytest.raises(PageAnalysisError):
        api.provider().analyze_page(page_request())

    assert meter.usage == TokenUsage(1200, 300)


def test_openai_response_without_usage_reports_nothing() -> None:
    response = openai_tests.completion(tool_calls=[openai_tests.function_call(analysis_payload())])
    body = response.json()
    del body["usage"]
    api = openai_tests.FakeApi(httpx2.Response(200, json=body))

    with measure_usage() as meter:
        api.provider().analyze_page(page_request())

    assert meter.calls == 0


def test_every_call_of_a_page_adds_to_one_meter() -> None:
    api = anthropic_tests.FakeApi(
        anthropic_tests.message([anthropic_tests.tool_use(analysis_payload())]),
        anthropic_tests.message([anthropic_tests.tool_use(analysis_payload())]),
    )
    provider = api.provider()

    with measure_usage() as meter:
        provider.analyze_page(page_request())
        provider.analyze_page(page_request())

    assert meter.usage == TokenUsage(2400, 600)
    assert meter.calls == 2


# --- önbellekten okunan girdi (C77) -----------------------------------------------------------


def test_cached_input_is_part_of_the_input_and_adds_and_subtracts() -> None:
    usage = TokenUsage(1000, 100, 600) + TokenUsage(500, 50, 100)

    assert usage == TokenUsage(1500, 150, 700)
    assert usage.uncached_input_tokens == 800
    assert usage.total_tokens == 1650
    assert usage - TokenUsage(500, 50, 100) == TokenUsage(1000, 100, 600)


@pytest.mark.parametrize("bad", [-1, 1.5, "3", None])
def test_cached_input_must_be_a_non_negative_integer(bad: object) -> None:
    with pytest.raises(ValueError, match="cached_input_tokens"):
        TokenUsage(10, 1, bad)  # type: ignore[arg-type]


def test_cached_input_cannot_exceed_the_input() -> None:
    with pytest.raises(ValueError, match="cached_input_tokens"):
        TokenUsage(10, 1, 11)


def test_event_data_carries_the_cached_share_only_when_there_is_one() -> None:
    cached = TokenUsage(1200, 300, 1000)

    assert TokenUsage(1200, 300).to_event_data() == {"input_tokens": 1200, "output_tokens": 300}
    assert cached.to_event_data() == {
        "input_tokens": 1200,
        "output_tokens": 300,
        "cached_input_tokens": 1000,
    }
    assert TokenUsage.from_event_data(cached.to_event_data()) == cached


@pytest.mark.parametrize("cached", [-1, "çok", 1201, None, 1.5])
def test_broken_cached_share_in_an_event_is_read_as_zero_not_as_unmeasured(
    cached: object,
) -> None:
    data = {"input_tokens": 1200, "output_tokens": 300, "cached_input_tokens": cached}

    assert TokenUsage.from_event_data(data) == TokenUsage(1200, 300)


def test_report_carries_the_cached_share() -> None:
    with measure_usage() as meter:
        report_usage(1000, 100, 800)
        report_usage(200, 50)

    assert meter.usage == TokenUsage(1200, 150, 800)


@pytest.mark.parametrize("cached", [None, -5, "800", 1001, 2.0])
def test_unusable_cached_share_is_reported_as_zero(cached: object) -> None:
    with measure_usage() as meter:
        report_usage(1000, 100, cached)

    assert meter.calls == 1
    assert meter.usage == TokenUsage(1000, 100)


def test_cached_input_is_priced_at_the_cached_rate() -> None:
    # gpt-5.6-luna: girdi 0.20, önbellek 0.02, çıktı 1.20 USD / 1M.
    price = ModelPrice(
        input_per_mtok=Decimal("0.2"),
        output_per_mtok=Decimal("1.2"),
        cached_input_per_mtok=Decimal("0.02"),
    )

    # (2000 × 0.2 + 8000 × 0.02 + 1000 × 1.2) / 1e6
    assert token_cost(TokenUsage(10_000, 1000, 8000), price) == Decimal("0.00176")
    assert token_cost(TokenUsage(10_000, 1000), price) == Decimal("0.0032")


def test_without_a_cached_rate_cached_input_is_priced_as_normal_input() -> None:
    price = ModelPrice(input_per_mtok=Decimal(5), output_per_mtok=Decimal(25))

    assert token_cost(TokenUsage(1200, 300, 1000), price) == token_cost(
        TokenUsage(1200, 300), price
    )


def test_price_accepts_an_optional_cached_rate() -> None:
    price = ModelPrice.model_validate(
        {"input_per_mtok": 5, "output_per_mtok": 25, "cached_input_per_mtok": "0.5"}
    )

    assert price.cached_input_per_mtok == Decimal("0.5")
    with pytest.raises(ValueError):
        ModelPrice(input_per_mtok=1, output_per_mtok=1, cached_input_per_mtok=-1)


def test_openai_reports_cached_prompt_tokens() -> None:
    body = openai_tests.completion(
        tool_calls=[openai_tests.function_call(analysis_payload())]
    ).json()
    body["usage"]["prompt_tokens_details"] = {"cached_tokens": 1024, "audio_tokens": 0}
    api = openai_tests.FakeApi(httpx2.Response(200, json=body))

    with measure_usage() as meter:
        api.provider().analyze_page(page_request())

    assert meter.usage == TokenUsage(1200, 300, 1024)


def test_openai_without_prompt_details_reports_no_cached_share() -> None:
    body = openai_tests.completion(
        tool_calls=[openai_tests.function_call(analysis_payload())]
    ).json()
    body["usage"]["prompt_tokens_details"] = None
    api = openai_tests.FakeApi(httpx2.Response(200, json=body))

    with measure_usage() as meter:
        api.provider().analyze_page(page_request())

    assert meter.usage == TokenUsage(1200, 300)


def test_anthropic_adds_cache_reads_and_writes_to_the_input() -> None:
    # Anthropic'in `input_tokens`'ı önbellek okuma/yazmasını içermez.
    body = anthropic_tests.message([anthropic_tests.tool_use(analysis_payload())]).json()
    body["usage"].update({"cache_read_input_tokens": 900, "cache_creation_input_tokens": 100})
    api = anthropic_tests.FakeApi(httpx2.Response(200, json=body))

    with measure_usage() as meter:
        api.provider().analyze_page(page_request())

    assert meter.usage == TokenUsage(2200, 300, 900)


def test_anthropic_with_null_cache_fields_reports_the_plain_input() -> None:
    body = anthropic_tests.message([anthropic_tests.tool_use(analysis_payload())]).json()
    body["usage"].update({"cache_read_input_tokens": None, "cache_creation_input_tokens": None})
    api = anthropic_tests.FakeApi(httpx2.Response(200, json=body))

    with measure_usage() as meter:
        api.provider().analyze_page(page_request())

    assert meter.usage == TokenUsage(1200, 300)
