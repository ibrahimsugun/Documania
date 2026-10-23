"""03.8.2 — model ve efor: istek gövdesi modele ve efora göre seçilir (PLAN.md §D124 c).

Sağlayıcılar `httpx2.MockTransport` arkasındadır (ağsız, 03.6.1): Anthropic'te zorlanmış araç +
kapalı düşünme yalnız onu kabul eden model/efor bileşiminde gider, ötekilerde `tool_choice: auto` +
katı araç (şema izin veriyorsa) + talimatta aracın adı; OpenAI'de `reasoning_effort`.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.ai import DocumentQueryError, ProviderConfigError
from app.ai.anthropic_provider import (
    DOCUMENT_QUERY_TOOL_NAME,
    THINKING_MIN_OUTPUT_TOKENS,
    TOOL_NAME,
    tool_instruction,
)
from app.ai.model_list import (
    ANTHROPIC_EFFORTS,
    MODELS,
    OPENAI_EFFORTS,
    SOURCE_DATE,
    RequestFormat,
    anthropic_request_format,
    models_for,
)
from app.events import ai_call_event_data
from tests.ai.payloads import analysis_payload, page_request, query_payload, query_request
from tests.ai.test_anthropic_provider import FakeApi, message, tool_use
from tests.ai.test_openai_provider import FakeApi as OpenAIFakeApi
from tests.ai.test_openai_provider import completion, function_call

THINKING = {"type": "thinking", "thinking": "", "signature": "imza"}


def _anthropic_body(model: str, effort: str | None) -> dict[str, Any]:
    api = FakeApi(message([tool_use(analysis_payload())]))
    api.provider(anthropic_model=model, anthropic_effort=effort).analyze_page(page_request())
    return api.body()


def test_model_list_carries_source_and_each_providers_effort_set() -> None:
    assert SOURCE_DATE
    assert [m.model_id for m in models_for("anthropic")] == [
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-sonnet-5-5",
        "claude-haiku-5-5",
        "claude-fable-5-1",
    ]
    for model in MODELS:
        allowed = ANTHROPIC_EFFORTS if model.provider == "anthropic" else OPENAI_EFFORTS
        assert set(model.efforts) <= set(allowed) and model.default_effort in allowed
    # GPT-6 Luna Chat Completions'ta işlevi yalnız `none` ile çağırır (OpenAI model dokümanı).
    (luna,) = models_for("openai")
    assert luna.efforts == ("none",) and luna.request_effort_default == "none"


def test_opus_5_up_to_high_keeps_the_forced_tool_with_thinking_disabled() -> None:
    body = _anthropic_body("claude-opus-5", "high")

    assert body["output_config"] == {"effort": "high"}
    assert body["thinking"] == {"type": "disabled"}
    assert body["tool_choice"]["type"] == "tool"
    assert body["max_tokens"] == 2048
    assert "temperature" not in body and "top_p" not in body


@pytest.mark.parametrize(
    ("model", "effort"),
    [
        ("claude-opus-5-5", None),
        ("claude-sonnet-5-5", "medium"),
        ("claude-fable-5-1", "max"),
        ("claude-opus-5", "xhigh"),
        ("claude-haiku-5-5", "max"),
    ],
    ids=["opus-5-5", "sonnet-5-5", "fable-5-1", "opus-5-xhigh", "haiku-5-5-max"],
)
def test_models_that_refuse_forcing_get_auto_tool_choice_without_thinking(
    model: str, effort: str | None
) -> None:
    body = _anthropic_body(model, effort)

    assert "thinking" not in body
    assert body["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert body["system"].endswith(tool_instruction(TOOL_NAME))
    assert body["max_tokens"] == THINKING_MIN_OUTPUT_TOKENS
    assert body.get("output_config") == (None if effort is None else {"effort": effort})
    # Sayfa analizinin `fields` sözlüğü katı şemaya sığmaz (§C13): araç katı gönderilmez.
    assert "strict" not in body["tools"][0]
    assert "temperature" not in body and "top_p" not in body


def test_auto_tool_choice_sends_a_strict_tool_when_the_schema_allows() -> None:
    api = FakeApi(
        message([THINKING, tool_use(query_payload("Ornekova"), name=DOCUMENT_QUERY_TOOL_NAME)])
    )

    query = api.provider(anthropic_model="claude-sonnet-5-5", anthropic_effort="low")
    query.read_document_query(query_request())

    (tool,) = api.body()["tools"]
    assert tool["strict"] is True
    assert tool["name"] == DOCUMENT_QUERY_TOOL_NAME
    assert tool["input_schema"]["additionalProperties"] is False


def test_auto_tool_choice_without_a_tool_call_is_rejected_as_before() -> None:
    api = FakeApi(message([THINKING], stop_reason="end_turn"))

    with pytest.raises(DocumentQueryError, match="stop_reason=end_turn"):
        api.provider(anthropic_model="claude-opus-5-5").read_document_query(query_request())


def test_unlisted_and_default_models_keep_todays_request() -> None:
    assert anthropic_request_format("claude-test", "max") is RequestFormat.FORCED_TOOL
    assert anthropic_request_format("claude-opus-5", None) is RequestFormat.FORCED_TOOL
    assert anthropic_request_format("claude-haiku-5-5", None) is RequestFormat.FORCED_TOOL
    assert "output_config" not in _anthropic_body("claude-test", None)


def test_effort_outside_the_models_set_is_a_config_error() -> None:
    with pytest.raises(ProviderConfigError, match="none"):
        FakeApi().provider(anthropic_model="claude-opus-5-5", anthropic_effort="none")
    with pytest.raises(ProviderConfigError, match="high"):
        OpenAIFakeApi().provider(openai_model="gpt-6-luna", openai_effort="high")


@pytest.mark.parametrize(
    ("model", "effort", "sent"),
    [("gpt-6-luna", None, "none"), ("gpt-test", None, "none"), ("gpt-test", "high", "high")],
    ids=["luna-default", "unlisted-default", "unlisted-high"],
)
def test_openai_sends_the_selected_or_function_compatible_reasoning_effort(
    model: str, effort: str | None, sent: str
) -> None:
    api = OpenAIFakeApi(completion(tool_calls=[function_call(analysis_payload())]))

    provider = api.provider(openai_model=model, openai_effort=effort)
    provider.analyze_page(page_request())

    assert api.body()["reasoning_effort"] == sent
    assert provider.effort == effort


def test_event_data_carries_the_selected_effort_and_never_a_key() -> None:
    provider = FakeApi().provider(anthropic_model="claude-opus-5-5", anthropic_effort="high")

    data = ai_call_event_data(provider=provider.name, model=provider.model, effort=provider.effort)

    assert data == {"provider": "anthropic", "model": "claude-opus-5-5", "effort": "high"}
    assert "effort" not in ai_call_event_data(provider="anthropic", model="m")
    assert "test-key" not in str(data)
