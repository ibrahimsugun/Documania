"""03.3.1 — OpenAI sağlayıcı aynı arayüzü uygular ve görüntü + metin girdisiyle şemaya uygun
yapılandırılmış çıktı üretir.

API ağ yerine `httpx2.MockTransport` ile karşılanır: istek gövdesi (görüntü, metin, zorlanmış
işlev, şema) ve yanıt eşlemesi gerçek SDK istemcisinden geçer. Canlı çağrı `live` işaretlidir.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
import openai
import pytest

from app.ai import (
    PROVIDER_FACTORIES,
    AnalysisProvider,
    DocumentQuery,
    DocumentQueryError,
    PageAnalysis,
    PageAnalysisError,
    PageAnalysisRequest,
    PageImage,
    PhotoCheck,
    PhotoCheckError,
    ProviderConfigError,
    ProviderConnectionError,
    ProviderError,
    ProviderRateLimitError,
    ProviderServerError,
    Script,
    Side,
    TrainingClassification,
    TrainingClassificationError,
    TypeDescription,
    TypeDescriptionError,
    TypeProposal,
    TypeProposalError,
    create_provider,
    validate_document_query,
    validate_page_analysis,
    validate_photo_check,
    validate_training_classification,
    validate_type_description,
    validate_type_proposal,
)
from app.ai import anthropic_provider as anthropic_module
from app.ai.openai_provider import (
    ANALYSIS_TOOL,
    DESCRIPTION_TOOL,
    DESCRIPTION_TOOL_NAME,
    DOCUMENT_QUERY_TOOL,
    DOCUMENT_QUERY_TOOL_NAME,
    PHOTO_CHECK_TOOL,
    PHOTO_CHECK_TOOL_NAME,
    PROPOSAL_TOOL,
    PROPOSAL_TOOL_NAME,
    TOOL_NAME,
    TRAINING_TOOL,
    TRAINING_TOOL_NAME,
    OpenAIProvider,
)
from app.ai.provider import MAX_ANALYSIS_ATTEMPTS, RETRY_BACKOFF_SECONDS
from app.ai.schemas import ISO_639_1_CODES
from app.ai.usage import TokenUsage, measure_usage
from app.config import Settings, load_settings
from tests.ai.payloads import (
    DOC_KINDS,
    PHOTO_RULES,
    SLUGS,
    SYNTHETIC_DOCUMENT_NUMBER,
    SYNTHETIC_SURNAME,
    analysis_payload,
    description_payload,
    description_request,
    page_request,
    photo_check_payload,
    photo_check_request,
    proposal_payload,
    proposal_request,
    query_payload,
    query_request,
    training_payload,
    training_request,
)
from tests.fixtures.gen import make_half_filled_image_bytes

Handler = Callable[[httpx2.Request], httpx2.Response]


def settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "sqlite://",
        "openai_api_key": "test-key",
        "openai_model": "gpt-test",
        "ai_max_output_tokens": 2048,
        "ai_request_timeout_seconds": 30.0,
    }
    values.update(overrides)
    return load_settings(_env_file=None, **values)


class FakeApi:
    """Chat Completions API yerine geçer; her isteği saklar, sıradaki yanıtı döner."""

    def __init__(self, *responses: httpx2.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def client(self) -> httpx2.Client:
        return httpx2.Client(transport=httpx2.MockTransport(self))

    def provider(self, **overrides: Any) -> OpenAIProvider:
        return OpenAIProvider.from_settings(settings(**overrides), http_client=self.client())

    def body(self, index: int = 0) -> dict[str, Any]:
        return json.loads(self.requests[index].content)


def completion(
    *,
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str = "tool_calls",
    content: str | None = None,
    refusal: str | None = None,
    choices: int = 1,
) -> httpx2.Response:
    message = {
        "role": "assistant",
        "content": content,
        "refusal": refusal,
        **({"tool_calls": tool_calls} if tool_calls is not None else {}),
    }
    return httpx2.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1_780_000_000,
            "model": "gpt-test",
            "choices": [
                {"index": index, "finish_reason": finish_reason, "message": message}
                for index in range(choices)
            ],
            "usage": {"prompt_tokens": 1200, "completion_tokens": 300, "total_tokens": 1500},
        },
    )


def function_call(
    arguments: object, *, name: str = TOOL_NAME, call_id: str = "call_1"
) -> dict[str, Any]:
    text = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": text}}


def api_error(
    status: int,
    error_type: str,
    code: str | None = None,
    text: str = "sağlayıcı açıklaması",
) -> httpx2.Response:
    return httpx2.Response(
        status,
        json={"error": {"message": text, "type": error_type, "param": None, "code": code}},
    )


# --- İstek: görüntü + metin, zorlanmış analiz işlevi -------------------------------------------


@pytest.mark.parametrize(("fmt", "media_type"), [("JPEG", "image/jpeg"), ("PNG", "image/png")])
def test_request_sends_image_then_text_with_forced_analysis_function(
    fmt: str, media_type: str
) -> None:
    api = FakeApi(completion(tool_calls=[function_call(analysis_payload())]))
    image_bytes = make_half_filled_image_bytes(fmt)
    request = PageAnalysisRequest(
        page_index=0,
        image=PageImage(image_bytes),
        instructions="Sistem talimatı: tahmin etme.",
        prompt="Sayfa 1 / metin katmanı: yok",
        known_slugs=SLUGS,
    )

    api.provider().analyze_page(request)

    assert len(api.requests) == 1
    sent = api.requests[0]
    assert sent.method == "POST"
    assert sent.url.path == "/v1/chat/completions"
    assert sent.headers["authorization"] == "Bearer test-key"
    body = api.body()
    assert body["model"] == "gpt-test"
    assert body["max_completion_tokens"] == 2048
    assert "max_tokens" not in body
    system, user = body["messages"]
    assert len(body["messages"]) == 2
    assert system == {"role": "system", "content": "Sistem talimatı: tahmin etme."}
    assert user["role"] == "user"
    image_part, text_part = user["content"]
    assert image_part["type"] == "image_url"
    prefix = f"data:{media_type};base64,"
    assert image_part["image_url"]["url"].startswith(prefix)
    assert base64.b64decode(image_part["image_url"]["url"][len(prefix) :]) == image_bytes
    assert image_part["image_url"]["detail"] == "high"
    assert text_part == {"type": "text", "text": "Sayfa 1 / metin katmanı: yok"}
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": TOOL_NAME,
                "description": ANALYSIS_TOOL["function"]["description"],
                "parameters": PageAnalysis.model_json_schema(),
                "strict": False,
            },
        }
    ]
    assert body["tool_choice"] == {"type": "function", "function": {"name": TOOL_NAME}}
    assert body["parallel_tool_calls"] is False
    # Sayfa kimlik belgesi olabilir: sağlayıcı tarafında saklanması istenmez.
    assert body["store"] is False
    assert "response_format" not in body


LIVE_REASONING_REFUSAL = (
    "Function tools with reasoning_effort are not supported for gpt-5.6-luna in "
    "/v1/chat/completions. To use function tools, use /v1/responses or set "
    "reasoning_effort to 'none'."
)


def reasoning_rule_api(reply: httpx2.Response) -> Handler:
    """Canlı API'nin (tm 96) kuralı: işlevli Chat Completions isteği `reasoning_effort: none`
    olmadan 400 ile reddedilir; kural sağlanırsa `reply` döner."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        if body.get("tools") and body.get("reasoning_effort") != "none":
            return api_error(400, "invalid_request_error", None, LIVE_REASONING_REFUSAL)
        return reply

    return handler


def provider_behind(handler: Handler) -> OpenAIProvider:
    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    return OpenAIProvider.from_settings(settings(), http_client=client)


def test_analysis_request_disables_reasoning_so_the_live_api_accepts_the_function() -> None:
    api = reasoning_rule_api(completion(tool_calls=[function_call(analysis_payload())]))

    analysis = provider_behind(api).analyze_page(page_request())

    assert analysis == validate_page_analysis(analysis_payload(), known_slugs=SLUGS)


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(
            lambda provider: provider.describe_type(description_request()),
            id="tur-aciklamasi",
        ),
        pytest.param(lambda provider: provider.propose_type(proposal_request()), id="tur-taslagi"),
        pytest.param(
            lambda provider: provider.classify_training_page(training_request()),
            id="egitim-siniflandirmasi",
        ),
        pytest.param(
            lambda provider: provider.check_photo(photo_check_request()), id="fotograf-kontrolu"
        ),
        pytest.param(
            lambda provider: provider.read_document_query(query_request()), id="belge-istegi"
        ),
    ],
)
def test_every_function_request_carries_reasoning_none(
    call: Callable[[OpenAIProvider], object],
) -> None:
    payloads = {
        DESCRIPTION_TOOL_NAME: description_payload(),
        PROPOSAL_TOOL_NAME: proposal_payload(),
        TRAINING_TOOL_NAME: training_payload(),
        PHOTO_CHECK_TOOL_NAME: photo_check_payload(),
        DOCUMENT_QUERY_TOOL_NAME: query_payload(),
    }
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        sent.append(body)
        name = body["tool_choice"]["function"]["name"]
        return completion(tool_calls=[function_call(payloads[name], name=name)])

    call(provider_behind(handler))

    assert [body["reasoning_effort"] for body in sent] == ["none"]


def test_tool_schema_is_the_page_analysis_contract() -> None:
    schema = ANALYSIS_TOOL["function"]["parameters"]
    defs = schema["$defs"]

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(analysis_payload())
    assert set(defs["PagePerson"]["required"]) == set(analysis_payload()["person"])
    assert defs["Script"]["enum"] == [s.value for s in Script]
    assert defs["Side"]["enum"] == [s.value for s in Side]
    assert set(schema["properties"]["language"]["anyOf"][0]["enum"]) == ISO_639_1_CODES
    # `fields` alan adı anahtarlı sözlüktür; katı mod `patternProperties`'i kabul etmez, bu yüzden
    # işlev katı olmayan modda tanımlıdır.
    fields = schema["properties"]["fields"]
    assert "properties" not in fields
    assert fields["patternProperties"] == {"^[a-z][a-z0-9_]*$": {"$ref": "#/$defs/FieldReading"}}
    assert ANALYSIS_TOOL["function"]["strict"] is False


def test_both_providers_send_the_same_contract() -> None:
    # Sağlayıcı değişince boru hattının gördüğü sözleşme değişmez: aynı araç adı, aynı şema.
    assert TOOL_NAME == anthropic_module.TOOL_NAME
    assert ANALYSIS_TOOL["function"]["parameters"] == anthropic_module.ANALYSIS_TOOL["input_schema"]


# --- Yanıt: yapılandırılmış çıktı → doğrulanmış PageAnalysis ----------------------------------


def test_function_arguments_become_schema_conforming_page_analysis() -> None:
    payload = analysis_payload(page_index=4, side="front", continues_previous_page=True)
    api = FakeApi(completion(tool_calls=[function_call(payload)]))

    analysis = api.provider().analyze_page(page_request(page_index=4))

    assert isinstance(analysis, PageAnalysis)
    assert analysis == validate_page_analysis(payload, known_slugs=SLUGS)
    assert analysis.page_index == 4
    assert analysis.side is Side.FRONT
    assert analysis.person.surname == SYNTHETIC_SURNAME


def test_forced_function_choice_may_finish_with_stop() -> None:
    # Zorlanmış işlev seçiminde API `finish_reason`'ı `tool_calls` yerine `stop` döndürebilir;
    # tam bir işlev çağrısı varsa yanıt geçerlidir.
    api = FakeApi(completion(tool_calls=[function_call(analysis_payload())], finish_reason="stop"))

    analysis = api.provider().analyze_page(page_request())

    assert analysis == validate_page_analysis(analysis_payload(), known_slugs=SLUGS)


@pytest.mark.parametrize(
    ("payload", "location"),
    [
        (analysis_payload(script="greek"), "script"),
        (analysis_payload(language="xx"), "language"),
        (analysis_payload(document_type_slug="bilinmeyen_tur"), "document_type_slug"),
        (analysis_payload(page_index=7), "page_index"),
        ({k: v for k, v in analysis_payload().items() if k != "person"}, "person"),
        (
            analysis_payload(fields={"surname": {"value": "X", "legible": False}}),
            "fields.surname",
        ),
    ],
    ids=["alfabe", "dil", "katalog-disi", "baska-sayfa", "eksik-kisi", "okunaksiz-deger"],
)
def test_non_conforming_function_arguments_are_rejected(payload: dict, location: str) -> None:
    api = FakeApi(completion(tool_calls=[function_call(payload)]))

    with pytest.raises(PageAnalysisError) as caught:
        api.provider().analyze_page(page_request())

    assert any(problem.startswith(location) for problem in caught.value.problems)
    assert SYNTHETIC_SURNAME not in str(caught.value)
    assert SYNTHETIC_DOCUMENT_NUMBER not in str(caught.value)
    assert len(api.requests) == 1


@pytest.mark.parametrize("arguments", ['{"page_index": 0, ', "sayfa boş", "[]"], ids=str)
def test_arguments_that_are_not_a_json_object_are_rejected(arguments: str) -> None:
    api = FakeApi(completion(tool_calls=[function_call(arguments)]))

    with pytest.raises(PageAnalysisError):
        api.provider().analyze_page(page_request())

    assert len(api.requests) == 1


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            completion(tool_calls=[function_call('{"page_index": 0')], finish_reason="length"),
            "finish_reason=length",
        ),
        (
            completion(
                tool_calls=[function_call(analysis_payload())], finish_reason="content_filter"
            ),
            "finish_reason=content_filter",
        ),
        (
            completion(finish_reason="stop", refusal="Bu isteğe yardımcı olamam."),
            "0 araç çağrısı, finish_reason=refusal",
        ),
        (
            completion(finish_reason="stop", content="Sayfa boş görünüyor."),
            "0 araç çağrısı, finish_reason=stop",
        ),
        (completion(tool_calls=[], finish_reason="stop"), "0 araç çağrısı"),
        (
            completion(
                tool_calls=[
                    function_call(analysis_payload()),
                    function_call(analysis_payload(), call_id="call_2"),
                ]
            ),
            "2 araç çağrısı",
        ),
        (
            completion(tool_calls=[function_call(analysis_payload(), name="baska_islev")]),
            "1 araç çağrısı",
        ),
        (
            completion(
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "custom",
                        "custom": {"name": TOOL_NAME, "input": json.dumps(analysis_payload())},
                    }
                ]
            ),
            "1 araç çağrısı",
        ),
        (completion(tool_calls=[function_call(analysis_payload())], choices=2), "2 seçenek"),
        (completion(choices=0), "0 seçenek"),
    ],
    ids=[
        "kesik",
        "icerik-filtresi",
        "ret",
        "islevsiz",
        "bos-cagri-listesi",
        "iki-cagri",
        "baska-islev",
        "ozel-arac",
        "iki-secenek",
        "secenek-yok",
    ],
)
def test_response_without_single_completed_function_call_is_rejected(
    response: httpx2.Response, expected: str
) -> None:
    api = FakeApi(response)

    with pytest.raises(PageAnalysisError) as caught:
        api.provider().analyze_page(page_request())

    assert len(caught.value.problems) == 1
    assert caught.value.problems[0].startswith("yanıt:")
    assert expected in caught.value.problems[0]
    assert "Bu isteğe yardımcı olamam" not in caught.value.problems[0]
    assert len(api.requests) == 1


# --- Çağrı hataları: türüne göre ProviderError, hız sınırı/5xx'te 03.5.1 yeniden denemesi -------


@pytest.mark.parametrize(
    ("status", "error_type", "code"),
    [
        (400, "invalid_request_error", "invalid_image_format"),
        (401, "invalid_request_error", "invalid_api_key"),
        (403, "invalid_request_error", "unsupported_country_region_territory"),
        (404, "invalid_request_error", "model_not_found"),
        (413, "invalid_request_error", None),
        (422, "invalid_request_error", None),
    ],
)
def test_non_retryable_status_errors_map_to_provider_error_without_retry(
    status: int, error_type: str, code: str | None
) -> None:
    response = api_error(status, error_type, code)
    response.headers["retry-after"] = "0"
    api = FakeApi(response)

    with pytest.raises(ProviderError) as caught:
        api.provider().analyze_page(page_request())

    assert type(caught.value) is ProviderError
    assert caught.value.status_code == status
    assert f"HTTP {status}" in str(caught.value)
    assert f"{error_type}" in str(caught.value)
    assert "sağlayıcı açıklaması" in str(caught.value)
    if code:
        assert code in str(caught.value)
    assert isinstance(caught.value.__cause__, openai.APIStatusError)
    # 03.5.1 yalnız hız sınırı/5xx'i yeniden dener; diğer 4xx SDK'ya ikinci istek göndermez.
    assert len(api.requests) == 1


@pytest.mark.parametrize(
    ("status", "error_type", "code", "expected"),
    [
        (429, "requests", "rate_limit_exceeded", ProviderRateLimitError),
        (500, "server_error", None, ProviderServerError),
        (502, "server_error", None, ProviderServerError),
        (503, "server_error", "service_unavailable", ProviderServerError),
        (504, "server_error", None, ProviderServerError),
    ],
)
def test_retryable_status_errors_recover_on_retry(
    status: int,
    error_type: str,
    code: str | None,
    expected: type[ProviderError],
    no_sleep: list[float],
) -> None:
    response = api_error(status, error_type, code)
    response.headers["retry-after"] = "0"
    api = FakeApi(response, completion(tool_calls=[function_call(analysis_payload())]))

    analysis = api.provider().analyze_page(page_request())

    assert isinstance(analysis, PageAnalysis)
    # İlk deneme `expected` türünde hataya düşer, 03.5.1 geri çekilmeli ikinci denemeyi yapar.
    assert len(api.requests) == 2
    assert no_sleep == [RETRY_BACKOFF_SECONDS]


@pytest.mark.parametrize(
    ("status", "error_type", "code", "expected"),
    [
        (429, "requests", "rate_limit_exceeded", ProviderRateLimitError),
        (500, "server_error", None, ProviderServerError),
        (503, "server_error", "service_unavailable", ProviderServerError),
        (504, "server_error", None, ProviderServerError),
    ],
)
def test_retryable_status_errors_give_up_after_max_attempts(
    status: int,
    error_type: str,
    code: str | None,
    expected: type[ProviderError],
    no_sleep: list[float],
) -> None:
    api = FakeApi(*(api_error(status, error_type, code) for _ in range(MAX_ANALYSIS_ATTEMPTS)))

    with pytest.raises(ProviderError) as caught:
        api.provider().analyze_page(page_request())

    assert type(caught.value) is expected
    assert caught.value.status_code == status
    assert len(api.requests) == MAX_ANALYSIS_ATTEMPTS == 3
    assert len(no_sleep) == MAX_ANALYSIS_ATTEMPTS - 1


def test_exhausted_quota_is_not_retried(no_sleep: list[float]) -> None:
    # Kota/bakiye bitince API de 429 döner ama beklemek çözmez: kalıcı hata, yeniden deneme yok.
    api = FakeApi(api_error(429, "insufficient_quota", "insufficient_quota"))

    with pytest.raises(ProviderError) as caught:
        api.provider().analyze_page(page_request())

    assert type(caught.value) is ProviderError
    assert caught.value.status_code == 429
    assert "insufficient_quota" in str(caught.value)
    assert len(api.requests) == 1
    assert no_sleep == []


@pytest.mark.parametrize(
    "body",
    [b"<html>Bad Gateway</html>", b'{"error": {}}', b'{"error": "kisa"}', b"{}"],
    ids=["html", "bos-hata", "metin-hata", "bos-govde"],
)
def test_status_error_without_api_error_detail(body: bytes, no_sleep: list[float]) -> None:
    # 502 sağlayıcı hatasıdır (ProviderServerError) ve 03.5.1 gereği yeniden denenir; üç deneme
    # de aynı ayrıntısız gövdeyi döner.
    api = FakeApi(*(httpx2.Response(502, content=body) for _ in range(MAX_ANALYSIS_ATTEMPTS)))

    with pytest.raises(ProviderServerError) as caught:
        api.provider().analyze_page(page_request())

    assert str(caught.value) == "OpenAI isteği başarısız: HTTP 502"
    assert len(api.requests) == MAX_ANALYSIS_ATTEMPTS


@pytest.mark.parametrize(
    "error",
    [httpx2.ConnectError("bağlantı yok"), httpx2.ReadTimeout("zaman aşımı")],
    ids=["baglanti", "zaman-asimi"],
)
def test_transport_failures_map_to_connection_error_without_retry(error: Exception) -> None:
    api = FakeApi(error, completion(tool_calls=[function_call(analysis_payload())]))

    with pytest.raises(ProviderConnectionError) as caught:
        api.provider().analyze_page(page_request())

    assert caught.value.status_code is None
    assert isinstance(caught.value.__cause__, openai.APIConnectionError)
    assert len(api.requests) == 1


def test_other_sdk_errors_map_to_provider_error() -> None:
    class BrokenCompletions:
        def create(self, **_: object) -> object:
            raise openai.OpenAIError("beklenmeyen")

    class BrokenChat:
        completions = BrokenCompletions()

    class BrokenClient:
        chat = BrokenChat()

    provider = OpenAIProvider(
        BrokenClient(),  # type: ignore[arg-type]
        model="gpt-test",
        max_output_tokens=10,
    )

    with pytest.raises(ProviderError) as caught:
        provider.analyze_page(page_request())

    assert type(caught.value) is ProviderError
    assert str(caught.value) == "OpenAI isteği başarısız: OpenAIError"


# --- Ayarlardan kurulum ve sağlayıcı seçimi ----------------------------------------------------


def test_from_settings_configures_client_from_env_values() -> None:
    provider = OpenAIProvider.from_settings(
        settings(
            openai_api_key="  test-key \n",
            openai_model="gpt-ayar",
            ai_max_output_tokens=1000,
            ai_request_timeout_seconds=12.5,
        )
    )

    assert provider.name == "openai"
    assert provider.model == "gpt-ayar"
    assert provider._max_output_tokens == 1000
    assert provider._client.api_key == "test-key"
    assert provider._client.max_retries == 0
    assert provider._client.timeout == 12.5


@pytest.mark.parametrize("key", [None, "", "   "], ids=["yok", "bos", "bosluk"])
def test_from_settings_requires_api_key(key: str | None) -> None:
    with pytest.raises(ProviderConfigError, match="OPENAI_API_KEY"):
        OpenAIProvider.from_settings(settings(openai_api_key=key))


def test_api_key_is_not_exposed_by_settings_repr() -> None:
    configured = settings(openai_api_key="sk-test-gizli")

    assert "sk-test-gizli" not in repr(configured)


def test_constructor_rejects_non_positive_output_tokens() -> None:
    client = openai.OpenAI(api_key="test-key")

    with pytest.raises(ValueError, match="max_output_tokens"):
        OpenAIProvider(client, model="gpt-test", max_output_tokens=0)


def test_constructor_rejects_empty_model() -> None:
    client = openai.OpenAI(api_key="test-key")

    with pytest.raises(ValueError, match="model"):
        OpenAIProvider(client, model="", max_output_tokens=10)


def test_prescreen_model_from_settings_gives_a_copy_that_asks_the_cheap_model() -> None:
    api = FakeApi(completion(tool_calls=[function_call(analysis_payload())]))
    provider = api.provider(openai_prescreen_model="gpt-ucuz")

    prescreener = provider.prescreen_provider()

    assert isinstance(prescreener, OpenAIProvider)
    assert (prescreener.model, prescreener._max_output_tokens) == ("gpt-ucuz", 2048)
    assert prescreener._client is provider._client
    assert prescreener.prescreen_provider() is None
    assert prescreener.analyze_page(page_request()).document_type_slug == "russian_passport"
    assert api.body()["model"] == "gpt-ucuz"


@pytest.mark.parametrize("model", [None, "", "gpt-test"], ids=["yok", "bos", "ana"])
def test_without_a_distinct_prescreen_model_there_is_no_prescreen(model: str | None) -> None:
    provider = FakeApi().provider(openai_prescreen_model=model)

    assert provider.prescreen_provider() is None


def test_openai_is_a_registered_provider_with_the_shared_interface() -> None:
    provider = create_provider(settings(ai_provider="openai"))

    assert "openai" in PROVIDER_FACTORIES
    assert isinstance(provider, AnalysisProvider)
    assert isinstance(provider, OpenAIProvider)
    assert provider.name == "openai"
    assert provider.model == "gpt-test"
    # Yanıt kabulü ortaktır ve alt sınıf tarafından atlanamaz.
    assert OpenAIProvider.analyze_page is AnalysisProvider.analyze_page


def test_default_openai_model_is_documented_in_env_example() -> None:
    example = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    default_model = Settings.model_fields["openai_model"].default

    assert f"OPENAI_MODEL={default_model}\n" in example
    # Gerçek anahtar şablona yazılmaz.
    assert "OPENAI_API_KEY=\n" in example


def test_openai_without_api_key_is_config_error() -> None:
    with pytest.raises(ProviderConfigError, match="OPENAI_API_KEY"):
        create_provider(settings(ai_provider="openai", openai_api_key=None))


def test_provider_switches_to_openai_with_env_file_without_pipeline_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("AI_PROVIDER", "OPENAI_API_KEY", "OPENAI_MODEL", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    api = FakeApi(completion(tool_calls=[function_call(analysis_payload(side="front"))]))
    # Yalnız taşıma katmanı değişir; sağlayıcı yine `.env`'deki ayarlarla kurulur.
    monkeypatch.setitem(
        PROVIDER_FACTORIES,
        "openai",
        lambda s: OpenAIProvider.from_settings(s, http_client=api.client()),
    )
    env_file = tmp_path / "openai.env"
    env_file.write_text(
        "DATABASE_URL=sqlite://\nAI_PROVIDER=openai\n"
        "OPENAI_API_KEY=test-key\nOPENAI_MODEL=gpt-env\n",
        encoding="utf-8",
    )

    # Boru hattının sağlayıcıyla konuştuğu tek yol — sağlayıcı değişince bu kod değişmez.
    provider = create_provider(load_settings(_env_file=env_file))
    analysis = provider.analyze_page(page_request())

    assert analysis.side is Side.FRONT
    assert len(api.requests) == 1
    assert api.body()["model"] == "gpt-env"


# --- Tür açıklaması (11.3.1): birkaç görüntü + metin, zorlanmış açıklama işlevi ----------------


def test_description_request_sends_images_in_order_then_text_with_forced_function() -> None:
    api = FakeApi(
        completion(tool_calls=[function_call(description_payload(), name=DESCRIPTION_TOOL_NAME)])
    )
    request = description_request(images=2, instructions="Tür talimatı", prompt="Tür metni")

    description = api.provider().describe_type(request)

    assert description == validate_type_description(description_payload())
    body = api.body()
    system, user = body["messages"]
    assert system == {"role": "system", "content": "Tür talimatı"}
    *image_parts, text_part = user["content"]
    assert [part["type"] for part in image_parts] == ["image_url"] * 2
    for part, image in zip(image_parts, request.images, strict=True):
        prefix = f"data:{image.media_type};base64,"
        assert part["image_url"]["url"].startswith(prefix)
        assert base64.b64decode(part["image_url"]["url"].removeprefix(prefix)) == image.data
        assert part["image_url"]["detail"] == "high"
    assert text_part == {"type": "text", "text": "Tür metni"}
    assert body["tools"] == [json.loads(json.dumps(DESCRIPTION_TOOL))]
    assert body["tools"][0]["function"]["parameters"] == TypeDescription.model_json_schema()
    assert body["tool_choice"] == {"type": "function", "function": {"name": DESCRIPTION_TOOL_NAME}}
    assert body["parallel_tool_calls"] is False
    assert body["store"] is False


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            completion(
                tool_calls=[function_call('{"layout": "Ka', name=DESCRIPTION_TOOL_NAME)],
                finish_reason="length",
            ),
            "tür açıklaması işlevi çağrısı tamamlanmadı (finish_reason=length)",
        ),
        (completion(tool_calls=[function_call(description_payload())]), "1 araç çağrısı"),
        (completion(finish_reason="stop", refusal="Yardımcı olamam."), "finish_reason=refusal"),
    ],
    ids=["kesik", "analiz-islevi", "ret"],
)
def test_description_response_without_description_function_call_is_rejected(
    response: httpx2.Response, expected: str
) -> None:
    api = FakeApi(response)

    with pytest.raises(TypeDescriptionError) as caught:
        api.provider().describe_type(description_request())

    assert caught.value.problems[0].startswith("yanıt:")
    assert expected in caught.value.problems[0]
    assert "Yardımcı olamam" not in str(caught.value)


def test_description_arguments_that_do_not_conform_are_rejected() -> None:
    api = FakeApi(
        completion(
            tool_calls=[
                function_call(description_payload(scripts=["runic"]), name=DESCRIPTION_TOOL_NAME)
            ]
        )
    )

    with pytest.raises(TypeDescriptionError) as caught:
        api.provider().describe_type(description_request())

    assert any(problem.startswith("scripts") for problem in caught.value.problems)


def test_description_exhausted_quota_is_not_retried(no_sleep: list[float]) -> None:
    api = FakeApi(api_error(429, "insufficient_quota", code="insufficient_quota"))

    with pytest.raises(ProviderError) as caught:
        api.provider().describe_type(description_request())

    assert not isinstance(caught.value, ProviderRateLimitError)
    assert len(api.requests) == 1
    assert no_sleep == []


# --- Tür taslağı (11.5.5): birkaç görüntü + metin, zorlanmış taslak işlevi ---------------------


def test_proposal_request_sends_images_in_order_then_text_with_forced_function() -> None:
    api = FakeApi(
        completion(tool_calls=[function_call(proposal_payload(), name=PROPOSAL_TOOL_NAME)])
    )
    request = proposal_request(images=3, instructions="Taslak talimatı", prompt="Aday metni")

    proposal = api.provider().propose_type(request)

    assert proposal == validate_type_proposal(proposal_payload())
    body = api.body()
    system, user = body["messages"]
    assert system == {"role": "system", "content": "Taslak talimatı"}
    *image_parts, text_part = user["content"]
    assert [part["type"] for part in image_parts] == ["image_url"] * 3
    for part, image in zip(image_parts, request.images, strict=True):
        prefix = f"data:{image.media_type};base64,"
        assert part["image_url"]["url"].startswith(prefix)
        assert base64.b64decode(part["image_url"]["url"].removeprefix(prefix)) == image.data
        assert part["image_url"]["detail"] == "high"
    assert text_part == {"type": "text", "text": "Aday metni"}
    assert body["tools"] == [json.loads(json.dumps(PROPOSAL_TOOL))]
    assert body["tools"][0]["function"]["parameters"] == TypeProposal.model_json_schema()
    assert body["tools"][0]["function"]["strict"] is False
    assert body["tool_choice"] == {"type": "function", "function": {"name": PROPOSAL_TOOL_NAME}}
    assert body["parallel_tool_calls"] is False
    assert body["store"] is False
    assert body["reasoning_effort"] == "none"


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            completion(
                tool_calls=[function_call('{"name": "Mon', name=PROPOSAL_TOOL_NAME)],
                finish_reason="length",
            ),
            "tür taslağı işlevi çağrısı tamamlanmadı (finish_reason=length)",
        ),
        (
            completion(
                tool_calls=[function_call(description_payload(), name=DESCRIPTION_TOOL_NAME)]
            ),
            "1 araç çağrısı",
        ),
        (completion(finish_reason="stop", refusal="Yardımcı olamam."), "finish_reason=refusal"),
    ],
    ids=["kesik", "aciklama-islevi", "ret"],
)
def test_proposal_response_without_proposal_function_call_is_rejected(
    response: httpx2.Response, expected: str
) -> None:
    api = FakeApi(response)

    with pytest.raises(TypeProposalError) as caught:
        api.provider().propose_type(proposal_request())

    assert caught.value.problems[0].startswith("yanıt:")
    assert expected in caught.value.problems[0]
    assert "Yardımcı olamam" not in str(caught.value)


def test_proposal_arguments_that_do_not_conform_are_rejected() -> None:
    api = FakeApi(
        completion(
            tool_calls=[function_call(proposal_payload(country="MNE"), name=PROPOSAL_TOOL_NAME)]
        )
    )

    with pytest.raises(TypeProposalError) as caught:
        api.provider().propose_type(proposal_request())

    assert any(problem.startswith("country") for problem in caught.value.problems)


def test_proposal_server_errors_are_retried(no_sleep: list[float]) -> None:
    api = FakeApi(
        api_error(503, "server_error"),
        completion(tool_calls=[function_call(proposal_payload(), name=PROPOSAL_TOOL_NAME)]),
    )

    api.provider().propose_type(proposal_request())

    assert len(api.requests) == 2
    assert no_sleep == [RETRY_BACKOFF_SECONDS]


def test_proposal_exhausted_quota_is_not_retried(no_sleep: list[float]) -> None:
    api = FakeApi(api_error(429, "insufficient_quota", code="insufficient_quota"))

    with pytest.raises(ProviderError) as caught:
        api.provider().propose_type(proposal_request())

    assert not isinstance(caught.value, ProviderRateLimitError)
    assert len(api.requests) == 1
    assert no_sleep == []


def test_proposal_usage_is_measured_like_every_call() -> None:
    # 13.1.1: taslak çağrısının tokenları da ölçülür; boş-zaman işi olayına yazar (§C85).
    api = FakeApi(
        completion(tool_calls=[function_call(proposal_payload(), name=PROPOSAL_TOOL_NAME)])
    )

    with measure_usage() as meter:
        api.provider().propose_type(proposal_request())

    assert meter.usage == TokenUsage(1200, 300)
    assert meter.calls == 1


# --- Eğitim sınıflandırması (11.9.3): ilk sayfa(lar) + metin, zorlanmış sınıflandırma işlevi ------


def test_training_request_sends_images_in_order_then_text_with_forced_function() -> None:
    api = FakeApi(
        completion(tool_calls=[function_call(training_payload(), name=TRAINING_TOOL_NAME)])
    )
    request = training_request(images=2, instructions="Eğitim talimatı", prompt="Öğe metni")

    classification = api.provider().classify_training_page(request)

    assert classification == validate_training_classification(
        training_payload(), known_slugs=SLUGS, doc_kinds=DOC_KINDS
    )
    body = api.body()
    system, user = body["messages"]
    assert system == {"role": "system", "content": "Eğitim talimatı"}
    *image_parts, text_part = user["content"]
    assert [part["type"] for part in image_parts] == ["image_url"] * 2
    for part, image in zip(image_parts, request.images, strict=True):
        prefix = f"data:{image.media_type};base64,"
        assert part["image_url"]["url"].startswith(prefix)
        assert base64.b64decode(part["image_url"]["url"].removeprefix(prefix)) == image.data
        assert part["image_url"]["detail"] == "high"
    assert text_part == {"type": "text", "text": "Öğe metni"}
    assert body["tools"] == [json.loads(json.dumps(TRAINING_TOOL))]
    assert body["tools"][0]["function"]["parameters"] == (
        TrainingClassification.model_json_schema()
    )
    assert body["tools"][0]["function"]["strict"] is False
    assert body["tool_choice"] == {"type": "function", "function": {"name": TRAINING_TOOL_NAME}}
    assert body["parallel_tool_calls"] is False
    assert body["store"] is False
    assert body["reasoning_effort"] == "none"


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            completion(
                tool_calls=[function_call('{"catalog_slug": nu', name=TRAINING_TOOL_NAME)],
                finish_reason="length",
            ),
            "eğitim sınıflandırması işlevi çağrısı tamamlanmadı (finish_reason=length)",
        ),
        (
            completion(tool_calls=[function_call(proposal_payload(), name=PROPOSAL_TOOL_NAME)]),
            "1 araç çağrısı",
        ),
        (completion(finish_reason="stop", refusal="Yardımcı olamam."), "finish_reason=refusal"),
    ],
    ids=["kesik", "taslak-islevi", "ret"],
)
def test_training_response_without_training_function_call_is_rejected(
    response: httpx2.Response, expected: str
) -> None:
    api = FakeApi(response)

    with pytest.raises(TrainingClassificationError) as caught:
        api.provider().classify_training_page(training_request())

    assert caught.value.problems[0].startswith("yanıt:")
    assert expected in caught.value.problems[0]
    assert "Yardımcı olamam" not in str(caught.value)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"catalog_slug": "martian_passport"}, "catalog_slug: istemdeki katalogda olmayan tür"),
        ({"doc_kind": "uzay_pasaportu"}, "doc_kind: tür sözlüğünde olmayan değer"),
    ],
    ids=["katalog-disi", "sozluk-disi"],
)
def test_training_arguments_outside_the_prompt_are_rejected(
    change: dict[str, str], expected: str
) -> None:
    api = FakeApi(
        completion(tool_calls=[function_call(training_payload(**change), name=TRAINING_TOOL_NAME)])
    )

    with pytest.raises(TrainingClassificationError) as caught:
        api.provider().classify_training_page(training_request())

    assert caught.value.problems == [expected]


def test_training_server_errors_are_retried(no_sleep: list[float]) -> None:
    api = FakeApi(
        api_error(503, "server_error"),
        completion(tool_calls=[function_call(training_payload(), name=TRAINING_TOOL_NAME)]),
    )

    api.provider().classify_training_page(training_request())

    assert len(api.requests) == 2
    assert no_sleep == [RETRY_BACKOFF_SECONDS]


def test_training_exhausted_quota_is_not_retried(no_sleep: list[float]) -> None:
    api = FakeApi(api_error(429, "insufficient_quota", code="insufficient_quota"))

    with pytest.raises(ProviderError) as caught:
        api.provider().classify_training_page(training_request())

    assert not isinstance(caught.value, ProviderRateLimitError)
    assert len(api.requests) == 1
    assert no_sleep == []


def test_training_usage_is_measured_like_every_call() -> None:
    # 13.1.1: sınıflandırma çağrısının tokenları da ölçülür; boş-zaman işi olayına yazar (§C86).
    api = FakeApi(
        completion(tool_calls=[function_call(training_payload(), name=TRAINING_TOOL_NAME)])
    )

    with measure_usage() as meter:
        api.provider().classify_training_page(training_request())

    assert meter.usage == TokenUsage(1200, 300)
    assert meter.calls == 1


# --- Fotoğraf kontrolü (11.7.1): tek görüntü + kurallar, zorlanmış kontrol işlevi ---------------


def test_photo_check_request_sends_image_then_rules_with_forced_function() -> None:
    api = FakeApi(
        completion(tool_calls=[function_call(photo_check_payload(), name=PHOTO_CHECK_TOOL_NAME)])
    )
    request = photo_check_request(instructions="Foto talimatı", prompt="Kurallar")

    check = api.provider().check_photo(request)

    assert check == validate_photo_check(photo_check_payload(), rules=PHOTO_RULES)
    body = api.body()
    system, user = body["messages"]
    assert system == {"role": "system", "content": "Foto talimatı"}
    image_part, text_part = user["content"]
    prefix = "data:image/jpeg;base64,"
    url = image_part["image_url"]["url"]
    assert base64.b64decode(url.removeprefix(prefix)) == request.image.data
    assert image_part["image_url"]["detail"] == "high"
    assert text_part == {"type": "text", "text": "Kurallar"}
    assert body["tools"] == [json.loads(json.dumps(PHOTO_CHECK_TOOL))]
    assert body["tools"][0]["function"]["parameters"] == PhotoCheck.model_json_schema()
    assert body["tool_choice"] == {"type": "function", "function": {"name": PHOTO_CHECK_TOOL_NAME}}
    assert body["store"] is False


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            completion(
                tool_calls=[function_call('{"rules": [', name=PHOTO_CHECK_TOOL_NAME)],
                finish_reason="length",
            ),
            "fotoğraf kontrolü işlevi çağrısı tamamlanmadı (finish_reason=length)",
        ),
        (completion(tool_calls=[function_call(photo_check_payload())]), "1 araç çağrısı"),
    ],
    ids=["kesik", "analiz-islevi"],
)
def test_photo_check_response_without_photo_check_function_call_is_rejected(
    response: httpx2.Response, expected: str
) -> None:
    api = FakeApi(response)

    with pytest.raises(PhotoCheckError) as caught:
        api.provider().check_photo(photo_check_request())

    assert caught.value.problems[0].startswith("yanıt:")
    assert expected in caught.value.problems[0]


def test_photo_check_arguments_that_do_not_conform_are_rejected() -> None:
    payload = photo_check_payload()
    payload["rules"][0]["result"] = "belki"
    api = FakeApi(completion(tool_calls=[function_call(payload, name=PHOTO_CHECK_TOOL_NAME)]))

    with pytest.raises(PhotoCheckError) as caught:
        api.provider().check_photo(photo_check_request())

    assert any(problem.startswith("rules.0.result") for problem in caught.value.problems)


# --- Belge isteği (12.3.1): görüntüsüz metin, zorlanmış belge isteği işlevi ---------------------


def test_document_query_request_sends_only_text_with_forced_function() -> None:
    api = FakeApi(
        completion(tool_calls=[function_call(query_payload(), name=DOCUMENT_QUERY_TOOL_NAME)])
    )
    request = query_request(instructions="İstek talimatı", prompt="Katalog ve mesaj")

    query = api.provider().read_document_query(request)

    assert query == validate_document_query(query_payload(), known_slugs=SLUGS)
    body = api.body()
    # Görüntü yok: kullanıcı mesajında yalnız metin.
    assert body["messages"] == [
        {"role": "system", "content": "İstek talimatı"},
        {"role": "user", "content": [{"type": "text", "text": "Katalog ve mesaj"}]},
    ]
    assert body["tools"] == [json.loads(json.dumps(DOCUMENT_QUERY_TOOL))]
    assert body["tools"][0]["function"]["parameters"] == DocumentQuery.model_json_schema()
    assert body["tool_choice"] == {
        "type": "function",
        "function": {"name": DOCUMENT_QUERY_TOOL_NAME},
    }
    assert body["store"] is False


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            completion(
                tool_calls=[function_call('{"intent": ', name=DOCUMENT_QUERY_TOOL_NAME)],
                finish_reason="length",
            ),
            "belge isteği işlevi çağrısı tamamlanmadı (finish_reason=length)",
        ),
        (completion(content="Ornekova'nın ehliyeti", finish_reason="stop"), "0 araç çağrısı"),
        (completion(tool_calls=[function_call(query_payload())]), "1 araç çağrısı"),
    ],
    ids=["kesik", "metin", "analiz-islevi"],
)
def test_document_query_response_without_query_function_call_is_rejected(
    response: httpx2.Response, expected: str
) -> None:
    api = FakeApi(response)

    with pytest.raises(DocumentQueryError) as caught:
        api.provider().read_document_query(query_request())

    assert caught.value.problems[0].startswith("yanıt:")
    assert expected in caught.value.problems[0]


def test_document_query_arguments_that_do_not_conform_are_rejected() -> None:
    payload = query_payload()
    payload["intent"] = "send_everything"
    api = FakeApi(completion(tool_calls=[function_call(payload, name=DOCUMENT_QUERY_TOOL_NAME)]))

    with pytest.raises(DocumentQueryError) as caught:
        api.provider().read_document_query(query_request())

    assert any(problem.startswith("intent") for problem in caught.value.problems)


# --- Canlı çağrı (DoD kapısında dışarıda) ------------------------------------------------------


@pytest.mark.live
def test_live_openai_returns_schema_conforming_analysis() -> None:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        pytest.skip("OPENAI_API_KEY tanımlı değil")
    live_settings = load_settings(_env_file=None, database_url="sqlite://", openai_api_key=api_key)
    provider = OpenAIProvider.from_settings(live_settings)
    request = page_request(
        instructions=(
            "Bir belge sayfasının görüntüsünü analiz et ve sonucu record_page_analysis işleviyle "
            "kaydet. Okuyamadığın veya sayfada yazılı olmayan her değer null olsun; tahmin etme. "
            "Katalogdaki türlerden biri değilse document_type_slug null olsun. Katalog: "
            + ", ".join(SLUGS)
        ),
        prompt="page_index: 0. Sayfanın metin katmanı yok.",
    )

    analysis = provider.analyze_page(request)

    assert analysis.page_index == 0
