"""03.2.2 — Anthropic sağlayıcı görüntü + metin girdisiyle şemaya uygun yapılandırılmış çıktı
üretir.

API ağ yerine `httpx2.MockTransport` ile karşılanır: istek gövdesi (görüntü, metin, zorlanmış
araç, şema) ve yanıt eşlemesi gerçek SDK istemcisinden geçer. Canlı çağrı `live` işaretlidir.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable
from typing import Any

import anthropic
import httpx2
import pytest

from app.ai import (
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
    validate_document_query,
    validate_page_analysis,
    validate_photo_check,
    validate_training_classification,
    validate_type_description,
    validate_type_proposal,
)
from app.ai import openai_provider as openai_module
from app.ai.anthropic_provider import (
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
    AnthropicProvider,
)
from app.ai.provider import MAX_ANALYSIS_ATTEMPTS, RETRY_BACKOFF_SECONDS
from app.ai.schemas import ISO_639_1_CODES
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
        "anthropic_api_key": "test-key",
        "anthropic_model": "claude-test",
        "ai_max_output_tokens": 2048,
        "ai_request_timeout_seconds": 30.0,
    }
    values.update(overrides)
    return load_settings(_env_file=None, **values)


class FakeApi:
    """Messages API yerine geçer; her isteği saklar, sıradaki yanıtı döner."""

    def __init__(self, *responses: httpx2.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def provider(self, **overrides: Any) -> AnthropicProvider:
        client = httpx2.Client(transport=httpx2.MockTransport(self))
        return AnthropicProvider.from_settings(settings(**overrides), http_client=client)

    def body(self, index: int = 0) -> dict[str, Any]:
        return json.loads(self.requests[index].content)


def message(
    content: list[dict[str, Any]], *, stop_reason: str | None = "tool_use"
) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-test",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 1200, "output_tokens": 300},
        },
    )


def tool_use(payload: object, *, name: str = TOOL_NAME, block_id: str = "toolu_1") -> dict:
    return {"type": "tool_use", "id": block_id, "name": name, "input": payload}


def api_error(status: int, error_type: str, text: str = "sağlayıcı açıklaması") -> httpx2.Response:
    return httpx2.Response(
        status, json={"type": "error", "error": {"type": error_type, "message": text}}
    )


# --- İstek: görüntü + metin, zorlanmış analiz aracı --------------------------------------------


@pytest.mark.parametrize(("fmt", "media_type"), [("JPEG", "image/jpeg"), ("PNG", "image/png")])
def test_request_sends_image_then_text_with_forced_analysis_tool(fmt: str, media_type: str) -> None:
    api = FakeApi(message([tool_use(analysis_payload())]))
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
    assert sent.url.path == "/v1/messages"
    assert sent.headers["x-api-key"] == "test-key"
    body = api.body()
    assert body["model"] == "claude-test"
    assert body["max_tokens"] == 2048
    assert body["system"] == "Sistem talimatı: tahmin etme."
    image_block, text_block = body["messages"][0]["content"]
    assert body["messages"][0]["role"] == "user" and len(body["messages"]) == 1
    assert image_block["type"] == "image"
    assert image_block["source"]["type"] == "base64"
    assert image_block["source"]["media_type"] == media_type
    assert base64.b64decode(image_block["source"]["data"]) == image_bytes
    assert text_block == {"type": "text", "text": "Sayfa 1 / metin katmanı: yok"}
    assert body["tools"] == [
        {
            "name": TOOL_NAME,
            "description": ANALYSIS_TOOL["description"],
            "input_schema": PageAnalysis.model_json_schema(),
        }
    ]
    assert body["tool_choice"] == {
        "type": "tool",
        "name": TOOL_NAME,
        "disable_parallel_tool_use": True,
    }
    assert body["thinking"] == {"type": "disabled"}
    assert "output_config" not in body


def test_tool_schema_is_the_page_analysis_contract() -> None:
    schema = ANALYSIS_TOOL["input_schema"]
    defs = schema["$defs"]

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(analysis_payload())
    assert set(defs["PagePerson"]["required"]) == set(analysis_payload()["person"])
    assert defs["Script"]["enum"] == [s.value for s in Script]
    assert defs["Side"]["enum"] == [s.value for s in Side]
    language = schema["properties"]["language"]["anyOf"][0]
    assert set(language["enum"]) == ISO_639_1_CODES
    # `fields` alan adı anahtarlı sözlüktür (tanımlı `properties` yok); katı şema her nesnede
    # `additionalProperties: false` istediği için onu boş nesneye indirirdi.
    fields = schema["properties"]["fields"]
    assert "properties" not in fields
    assert fields["patternProperties"] == {"^[a-z][a-z0-9_]*$": {"$ref": "#/$defs/FieldReading"}}


# --- Yanıt: yapılandırılmış çıktı → doğrulanmış PageAnalysis ----------------------------------


def test_tool_input_becomes_schema_conforming_page_analysis() -> None:
    payload = analysis_payload(page_index=4, side="front", continues_previous_page=True)
    api = FakeApi(message([{"type": "text", "text": "Kaydediyorum."}, tool_use(payload)]))

    analysis = api.provider().analyze_page(page_request(page_index=4))

    assert isinstance(analysis, PageAnalysis)
    assert analysis == validate_page_analysis(payload, known_slugs=SLUGS)
    assert analysis.page_index == 4
    assert analysis.side is Side.FRONT
    assert analysis.person.surname == SYNTHETIC_SURNAME


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
def test_non_conforming_tool_input_is_rejected(payload: dict, location: str) -> None:
    api = FakeApi(message([tool_use(payload)]))

    with pytest.raises(PageAnalysisError) as caught:
        api.provider().analyze_page(page_request())

    assert any(problem.startswith(location) for problem in caught.value.problems)
    assert SYNTHETIC_SURNAME not in str(caught.value)
    assert SYNTHETIC_DOCUMENT_NUMBER not in str(caught.value)


@pytest.mark.parametrize(
    ("content", "stop_reason", "expected"),
    [
        ([tool_use({"page_index": 0})], "max_tokens", "stop_reason=max_tokens"),
        ([], "refusal", "stop_reason=refusal"),
        ([{"type": "text", "text": "Sayfa boş görünüyor."}], "end_turn", "stop_reason=end_turn"),
        ([tool_use(analysis_payload())], None, "stop_reason=None"),
        (
            [tool_use(analysis_payload()), tool_use(analysis_payload(), block_id="toolu_2")],
            "tool_use",
            "2 araç çağrısı",
        ),
        ([tool_use(analysis_payload(), name="baska_arac")], "tool_use", "1 araç çağrısı"),
    ],
    ids=["kesik", "ret", "aracsiz", "durum-yok", "iki-cagri", "baska-arac"],
)
def test_response_without_single_completed_tool_call_is_rejected(
    content: list[dict[str, Any]], stop_reason: str | None, expected: str
) -> None:
    api = FakeApi(message(content, stop_reason=stop_reason))

    with pytest.raises(PageAnalysisError) as caught:
        api.provider().analyze_page(page_request())

    assert len(caught.value.problems) == 1
    assert caught.value.problems[0].startswith("yanıt:")
    assert expected in caught.value.problems[0]
    assert len(api.requests) == 1


# --- Çağrı hataları: türüne göre ProviderError, hız sınırı/5xx'te 03.5.1 yeniden denemesi -------


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (400, "invalid_request_error"),
        (401, "authentication_error"),
        (403, "permission_error"),
        (404, "not_found_error"),
        (413, "request_too_large"),
    ],
)
def test_non_retryable_status_errors_map_to_provider_error_without_retry(
    status: int, error_type: str
) -> None:
    response = api_error(status, error_type)
    response.headers["retry-after"] = "0"
    api = FakeApi(response)

    with pytest.raises(ProviderError) as caught:
        api.provider().analyze_page(page_request())

    assert type(caught.value) is ProviderError
    assert caught.value.status_code == status
    assert f"HTTP {status}" in str(caught.value)
    assert f"{error_type}: sağlayıcı açıklaması" in str(caught.value)
    assert isinstance(caught.value.__cause__, anthropic.APIStatusError)
    # 03.5.1 yalnız hız sınırı/5xx'i yeniden dener; diğer 4xx SDK'ya ikinci istek göndermez.
    assert len(api.requests) == 1


@pytest.mark.parametrize(
    ("status", "error_type", "expected"),
    [
        (429, "rate_limit_error", ProviderRateLimitError),
        (500, "api_error", ProviderServerError),
        (503, "api_error", ProviderServerError),
        (504, "timeout_error", ProviderServerError),
        (529, "overloaded_error", ProviderServerError),
    ],
)
def test_retryable_status_errors_recover_on_retry(
    status: int, error_type: str, expected: type[ProviderError], no_sleep: list[float]
) -> None:
    response = api_error(status, error_type)
    response.headers["retry-after"] = "0"
    api = FakeApi(response, message([tool_use(analysis_payload())]))

    analysis = api.provider().analyze_page(page_request())

    assert isinstance(analysis, PageAnalysis)
    # İlk deneme `expected` türünde hataya düşer, 03.5.1 geri çekilmeli ikinci denemeyi yapar.
    assert len(api.requests) == 2
    assert no_sleep == [RETRY_BACKOFF_SECONDS]


@pytest.mark.parametrize(
    ("status", "error_type", "expected"),
    [
        (429, "rate_limit_error", ProviderRateLimitError),
        (500, "api_error", ProviderServerError),
        (503, "api_error", ProviderServerError),
        (504, "timeout_error", ProviderServerError),
        (529, "overloaded_error", ProviderServerError),
    ],
)
def test_retryable_status_errors_give_up_after_max_attempts(
    status: int, error_type: str, expected: type[ProviderError], no_sleep: list[float]
) -> None:
    response = api_error(status, error_type)
    api = FakeApi(response, api_error(status, error_type), api_error(status, error_type))

    with pytest.raises(ProviderError) as caught:
        api.provider().analyze_page(page_request())

    assert type(caught.value) is expected
    assert caught.value.status_code == status
    assert len(api.requests) == MAX_ANALYSIS_ATTEMPTS == 3
    assert len(no_sleep) == MAX_ANALYSIS_ATTEMPTS - 1


@pytest.mark.parametrize(
    "body",
    [b"<html>Bad Gateway</html>", b'{"type": "error"}', b'{"error": {}}'],
    ids=["html", "hata-nesnesi-yok", "bos-hata"],
)
def test_status_error_without_api_error_detail(body: bytes, no_sleep: list[float]) -> None:
    # 502 sağlayıcı hatasıdır (ProviderServerError) ve 03.5.1 gereği yeniden denenir; üç deneme
    # de aynı ayrıntısız gövdeyi döner.
    api = FakeApi(*(httpx2.Response(502, content=body) for _ in range(MAX_ANALYSIS_ATTEMPTS)))

    with pytest.raises(ProviderServerError) as caught:
        api.provider().analyze_page(page_request())

    assert str(caught.value) == "Anthropic isteği başarısız: HTTP 502"
    assert len(api.requests) == MAX_ANALYSIS_ATTEMPTS


@pytest.mark.parametrize(
    "error",
    [httpx2.ConnectError("bağlantı yok"), httpx2.ReadTimeout("zaman aşımı")],
    ids=["baglanti", "zaman-asimi"],
)
def test_transport_failures_map_to_connection_error_without_retry(error: Exception) -> None:
    api = FakeApi(error, message([tool_use(analysis_payload())]))

    with pytest.raises(ProviderConnectionError) as caught:
        api.provider().analyze_page(page_request())

    assert caught.value.status_code is None
    assert isinstance(caught.value.__cause__, anthropic.APIConnectionError)
    assert len(api.requests) == 1


def test_other_sdk_errors_map_to_provider_error() -> None:
    class BrokenMessages:
        def create(self, **_: object) -> object:
            raise anthropic.AnthropicError("beklenmeyen")

    class BrokenClient:
        messages = BrokenMessages()

    provider = AnthropicProvider(
        BrokenClient(),  # type: ignore[arg-type]
        model="claude-test",
        max_output_tokens=10,
    )

    with pytest.raises(ProviderError) as caught:
        provider.analyze_page(page_request())

    assert type(caught.value) is ProviderError
    assert str(caught.value) == "Anthropic isteği başarısız: AnthropicError"


# --- Ayarlardan kurulum ------------------------------------------------------------------------


def test_from_settings_configures_client_from_env_values() -> None:
    provider = AnthropicProvider.from_settings(
        settings(
            anthropic_api_key="  test-key \n",
            anthropic_model="claude-ayar",
            ai_max_output_tokens=1000,
            ai_request_timeout_seconds=12.5,
        )
    )

    assert provider.name == "anthropic"
    assert provider.model == "claude-ayar"
    assert provider._max_output_tokens == 1000
    assert provider._client.api_key == "test-key"
    assert provider._client.max_retries == 0
    assert provider._client.timeout == 12.5


@pytest.mark.parametrize("key", [None, "", "   "], ids=["yok", "bos", "bosluk"])
def test_from_settings_requires_api_key(key: str | None) -> None:
    with pytest.raises(ProviderConfigError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider.from_settings(settings(anthropic_api_key=key))


def test_api_key_is_not_exposed_by_settings_repr() -> None:
    configured = settings(anthropic_api_key="sk-ant-test-gizli")

    assert "sk-ant-test-gizli" not in repr(configured)


def test_constructor_rejects_non_positive_output_tokens() -> None:
    client = anthropic.Anthropic(api_key="test-key")

    with pytest.raises(ValueError, match="max_output_tokens"):
        AnthropicProvider(client, model="claude-test", max_output_tokens=0)


# --- Ucuz model ön elemesi (13.2.1): aynı istemci, ucuz model ------------------------------------


def test_prescreen_model_from_settings_gives_a_copy_that_asks_the_cheap_model() -> None:
    api = FakeApi(message([tool_use(analysis_payload())]))
    provider = api.provider(anthropic_prescreen_model="  claude-ucuz ")

    prescreener = provider.prescreen_provider()

    assert isinstance(prescreener, AnthropicProvider)
    assert provider.prescreen_model == "claude-ucuz"
    assert (prescreener.model, prescreener._max_output_tokens) == ("claude-ucuz", 2048)
    assert prescreener._client is provider._client
    # Kopyanın kendi ön elemesi yoktur.
    assert prescreener.prescreen_model is None and prescreener.prescreen_provider() is None
    assert prescreener.analyze_page(page_request()).document_type_slug == "russian_passport"
    assert api.body()["model"] == "claude-ucuz"


@pytest.mark.parametrize(
    "model", [None, "", "  ", "claude-test"], ids=["yok", "bos", "bosluk", "ana"]
)
def test_without_a_distinct_prescreen_model_there_is_no_prescreen(model: str | None) -> None:
    provider = FakeApi().provider(anthropic_prescreen_model=model)

    assert provider.prescreen_model is None
    assert provider.prescreen_provider() is None


# --- Tür açıklaması (11.3.1): birkaç görüntü + metin, zorlanmış açıklama aracı -----------------


def test_description_request_sends_images_in_order_then_text_with_forced_description_tool() -> None:
    api = FakeApi(message([tool_use(description_payload(), name=DESCRIPTION_TOOL_NAME)]))
    request = description_request(images=3, instructions="Tür talimatı", prompt="Tür metni")

    description = api.provider().describe_type(request)

    assert description == validate_type_description(description_payload())
    body = api.body()
    assert body["system"] == "Tür talimatı"
    *image_blocks, text_block = body["messages"][0]["content"]
    assert len(body["messages"]) == 1
    assert [block["type"] for block in image_blocks] == ["image"] * 3
    assert [base64.b64decode(block["source"]["data"]) for block in image_blocks] == [
        image.data for image in request.images
    ]
    assert [block["source"]["media_type"] for block in image_blocks] == [
        image.media_type for image in request.images
    ]
    assert text_block == {"type": "text", "text": "Tür metni"}
    assert body["tools"] == [json.loads(json.dumps(DESCRIPTION_TOOL))]
    assert body["tools"][0]["input_schema"] == TypeDescription.model_json_schema()
    assert body["tool_choice"] == {
        "type": "tool",
        "name": DESCRIPTION_TOOL_NAME,
        "disable_parallel_tool_use": True,
    }
    assert body["thinking"] == {"type": "disabled"}


@pytest.mark.parametrize(
    ("content", "stop_reason", "expected"),
    [
        (
            [tool_use(description_payload(), name=DESCRIPTION_TOOL_NAME)],
            "max_tokens",
            "tür açıklaması aracı çağrısı tamamlanmadı (stop_reason=max_tokens)",
        ),
        ([tool_use(description_payload())], "tool_use", "1 araç çağrısı"),
    ],
    ids=["kesik", "analiz-araci"],
)
def test_description_response_without_description_tool_call_is_rejected(
    content: list[dict[str, Any]], stop_reason: str, expected: str
) -> None:
    api = FakeApi(message(content, stop_reason=stop_reason))

    with pytest.raises(TypeDescriptionError) as caught:
        api.provider().describe_type(description_request())

    assert caught.value.problems[0].startswith("yanıt:")
    assert expected in caught.value.problems[0]


def test_non_conforming_description_is_rejected() -> None:
    api = FakeApi(
        message([tool_use(description_payload(mrz={"line_count": 5}), name=DESCRIPTION_TOOL_NAME)])
    )

    with pytest.raises(TypeDescriptionError) as caught:
        api.provider().describe_type(description_request())

    assert any(problem.startswith("mrz") for problem in caught.value.problems)


def test_description_status_errors_are_retried_like_analysis(no_sleep: list[float]) -> None:
    api = FakeApi(
        api_error(529, "overloaded_error"),
        message([tool_use(description_payload(), name=DESCRIPTION_TOOL_NAME)]),
    )

    api.provider().describe_type(description_request())

    assert len(api.requests) == 2
    assert no_sleep == [RETRY_BACKOFF_SECONDS]


# --- Eğitim sınıflandırması (11.9.3): ilk sayfa(lar) + metin, zorlanmış sınıflandırma aracı -------


def test_training_request_sends_images_in_order_then_text_with_forced_training_tool() -> None:
    api = FakeApi(message([tool_use(training_payload(), name=TRAINING_TOOL_NAME)]))
    request = training_request(images=2, instructions="Eğitim talimatı", prompt="Öğe metni")

    classification = api.provider().classify_training_page(request)

    assert classification == validate_training_classification(
        training_payload(), known_slugs=SLUGS, doc_kinds=DOC_KINDS
    )
    body = api.body()
    assert body["system"] == "Eğitim talimatı"
    *image_blocks, text_block = body["messages"][0]["content"]
    assert len(body["messages"]) == 1
    assert [block["type"] for block in image_blocks] == ["image"] * 2
    assert [base64.b64decode(block["source"]["data"]) for block in image_blocks] == [
        image.data for image in request.images
    ]
    assert [block["source"]["media_type"] for block in image_blocks] == [
        image.media_type for image in request.images
    ]
    assert text_block == {"type": "text", "text": "Öğe metni"}
    assert body["tools"] == [json.loads(json.dumps(TRAINING_TOOL))]
    assert body["tools"][0]["input_schema"] == TrainingClassification.model_json_schema()
    assert body["tool_choice"] == {
        "type": "tool",
        "name": TRAINING_TOOL_NAME,
        "disable_parallel_tool_use": True,
    }
    assert body["thinking"] == {"type": "disabled"}


@pytest.mark.parametrize(
    ("content", "stop_reason", "expected"),
    [
        (
            [tool_use(training_payload(), name=TRAINING_TOOL_NAME)],
            "max_tokens",
            "eğitim sınıflandırması aracı çağrısı tamamlanmadı (stop_reason=max_tokens)",
        ),
        (
            [tool_use(proposal_payload(), name=PROPOSAL_TOOL_NAME)],
            "tool_use",
            "1 araç çağrısı",
        ),
        ([{"type": "text", "text": "Ornekova'nın pasaportu"}], "end_turn", "stop_reason=end_turn"),
    ],
    ids=["kesik", "taslak-araci", "metin"],
)
def test_training_response_without_training_tool_call_is_rejected(
    content: list[dict[str, Any]], stop_reason: str, expected: str
) -> None:
    api = FakeApi(message(content, stop_reason=stop_reason))

    with pytest.raises(TrainingClassificationError) as caught:
        api.provider().classify_training_page(training_request())

    assert caught.value.problems[0].startswith("yanıt:")
    assert expected in caught.value.problems[0]
    assert "Ornekova" not in str(caught.value)


def test_non_conforming_training_classification_is_rejected() -> None:
    api = FakeApi(
        message([tool_use(training_payload(country_iso3="alb"), name=TRAINING_TOOL_NAME)])
    )

    with pytest.raises(TrainingClassificationError) as caught:
        api.provider().classify_training_page(training_request())

    assert any(problem.startswith("country_iso3") for problem in caught.value.problems)


def test_training_status_errors_are_retried_like_analysis(no_sleep: list[float]) -> None:
    api = FakeApi(
        api_error(529, "overloaded_error"),
        api_error(429, "rate_limit_error"),
        message([tool_use(training_payload(), name=TRAINING_TOOL_NAME)]),
    )

    api.provider().classify_training_page(training_request())

    assert len(api.requests) == 3
    assert no_sleep == [RETRY_BACKOFF_SECONDS, RETRY_BACKOFF_SECONDS * 2]


def test_training_client_errors_are_not_retried(no_sleep: list[float]) -> None:
    api = FakeApi(api_error(400, "invalid_request_error"))

    with pytest.raises(ProviderError) as caught:
        api.provider().classify_training_page(training_request())

    assert caught.value.status_code == 400
    assert len(api.requests) == 1
    assert no_sleep == []


def test_both_providers_send_the_same_training_contract() -> None:
    assert TRAINING_TOOL_NAME == openai_module.TRAINING_TOOL_NAME
    assert TRAINING_TOOL["input_schema"] == openai_module.TRAINING_TOOL["function"]["parameters"]


# --- Fotoğraf kontrolü (11.7.1): tek görüntü + kurallar, zorlanmış kontrol aracı ----------------


def test_photo_check_request_sends_image_then_rules_with_forced_photo_check_tool() -> None:
    api = FakeApi(message([tool_use(photo_check_payload(), name=PHOTO_CHECK_TOOL_NAME)]))
    request = photo_check_request(fmt="PNG", instructions="Foto talimatı", prompt="Kurallar")

    check = api.provider().check_photo(request)

    assert check == validate_photo_check(photo_check_payload(), rules=PHOTO_RULES)
    body = api.body()
    assert body["system"] == "Foto talimatı"
    image_block, text_block = body["messages"][0]["content"]
    assert image_block["source"]["media_type"] == "image/png"
    assert base64.b64decode(image_block["source"]["data"]) == request.image.data
    assert text_block == {"type": "text", "text": "Kurallar"}
    assert body["tools"] == [json.loads(json.dumps(PHOTO_CHECK_TOOL))]
    assert body["tools"][0]["input_schema"] == PhotoCheck.model_json_schema()
    assert body["tool_choice"] == {
        "type": "tool",
        "name": PHOTO_CHECK_TOOL_NAME,
        "disable_parallel_tool_use": True,
    }
    assert body["thinking"] == {"type": "disabled"}


@pytest.mark.parametrize(
    ("content", "stop_reason", "expected"),
    [
        (
            [tool_use(photo_check_payload(), name=PHOTO_CHECK_TOOL_NAME)],
            "max_tokens",
            "fotoğraf kontrolü aracı çağrısı tamamlanmadı (stop_reason=max_tokens)",
        ),
        ([tool_use(photo_check_payload())], "tool_use", "1 araç çağrısı"),
    ],
    ids=["kesik", "analiz-araci"],
)
def test_photo_check_response_without_photo_check_tool_call_is_rejected(
    content: list[dict[str, Any]], stop_reason: str, expected: str
) -> None:
    api = FakeApi(message(content, stop_reason=stop_reason))

    with pytest.raises(PhotoCheckError) as caught:
        api.provider().check_photo(photo_check_request())

    assert caught.value.problems[0].startswith("yanıt:")
    assert expected in caught.value.problems[0]


def test_photo_check_answering_other_rules_is_rejected() -> None:
    api = FakeApi(message([tool_use(photo_check_payload(), name=PHOTO_CHECK_TOOL_NAME)]))

    with pytest.raises(PhotoCheckError) as caught:
        api.provider().check_photo(photo_check_request(rules=("face_visible",)))

    assert caught.value.problems == ["rules: sorulmayan 2 kural yanıtlandı"]


# --- Tür taslağı (11.5.5): birkaç görüntü + metin, zorlanmış taslak aracı -----------------------


def test_proposal_request_sends_images_in_order_then_text_with_forced_proposal_tool() -> None:
    api = FakeApi(message([tool_use(proposal_payload(), name=PROPOSAL_TOOL_NAME)]))
    request = proposal_request(images=3, instructions="Taslak talimatı", prompt="Aday metni")

    proposal = api.provider().propose_type(request)

    assert proposal == validate_type_proposal(proposal_payload())
    body = api.body()
    assert body["system"] == "Taslak talimatı"
    *image_blocks, text_block = body["messages"][0]["content"]
    assert len(body["messages"]) == 1
    assert [block["type"] for block in image_blocks] == ["image"] * 3
    assert [base64.b64decode(block["source"]["data"]) for block in image_blocks] == [
        image.data for image in request.images
    ]
    assert [block["source"]["media_type"] for block in image_blocks] == [
        image.media_type for image in request.images
    ]
    assert text_block == {"type": "text", "text": "Aday metni"}
    assert body["tools"] == [json.loads(json.dumps(PROPOSAL_TOOL))]
    assert body["tools"][0]["input_schema"] == TypeProposal.model_json_schema()
    assert body["tool_choice"] == {
        "type": "tool",
        "name": PROPOSAL_TOOL_NAME,
        "disable_parallel_tool_use": True,
    }
    assert body["thinking"] == {"type": "disabled"}


@pytest.mark.parametrize(
    ("content", "stop_reason", "expected"),
    [
        (
            [tool_use(proposal_payload(), name=PROPOSAL_TOOL_NAME)],
            "max_tokens",
            "tür taslağı aracı çağrısı tamamlanmadı (stop_reason=max_tokens)",
        ),
        (
            [tool_use(description_payload(), name=DESCRIPTION_TOOL_NAME)],
            "tool_use",
            "1 araç çağrısı",
        ),
        ([{"type": "text", "text": "Ornekova'nın kartı"}], "end_turn", "stop_reason=end_turn"),
    ],
    ids=["kesik", "aciklama-araci", "metin"],
)
def test_proposal_response_without_proposal_tool_call_is_rejected(
    content: list[dict[str, Any]], stop_reason: str, expected: str
) -> None:
    api = FakeApi(message(content, stop_reason=stop_reason))

    with pytest.raises(TypeProposalError) as caught:
        api.provider().propose_type(proposal_request())

    assert caught.value.problems[0].startswith("yanıt:")
    assert expected in caught.value.problems[0]
    assert "Ornekova" not in str(caught.value)


def test_non_conforming_proposal_is_rejected() -> None:
    api = FakeApi(
        message([tool_use(proposal_payload(required_fields=["Surname"]), name=PROPOSAL_TOOL_NAME)])
    )

    with pytest.raises(TypeProposalError) as caught:
        api.provider().propose_type(proposal_request())

    assert any(problem.startswith("required_fields.0") for problem in caught.value.problems)


def test_proposal_status_errors_are_retried_like_analysis(no_sleep: list[float]) -> None:
    api = FakeApi(
        api_error(529, "overloaded_error"),
        api_error(429, "rate_limit_error"),
        message([tool_use(proposal_payload(), name=PROPOSAL_TOOL_NAME)]),
    )

    api.provider().propose_type(proposal_request())

    assert len(api.requests) == 3
    assert no_sleep == [RETRY_BACKOFF_SECONDS, RETRY_BACKOFF_SECONDS * 2]


def test_proposal_client_errors_are_not_retried(no_sleep: list[float]) -> None:
    api = FakeApi(api_error(400, "invalid_request_error"))

    with pytest.raises(ProviderError) as caught:
        api.provider().propose_type(proposal_request())

    assert caught.value.status_code == 400
    assert len(api.requests) == 1
    assert no_sleep == []


def test_both_providers_send_the_same_proposal_contract() -> None:
    assert PROPOSAL_TOOL_NAME == openai_module.PROPOSAL_TOOL_NAME
    assert PROPOSAL_TOOL["input_schema"] == openai_module.PROPOSAL_TOOL["function"]["parameters"]


# --- Belge isteği (12.3.1): görüntüsüz metin, zorlanmış belge isteği aracı ----------------------


def test_document_query_request_sends_only_text_with_forced_query_tool() -> None:
    api = FakeApi(message([tool_use(query_payload(), name=DOCUMENT_QUERY_TOOL_NAME)]))
    request = query_request(instructions="İstek talimatı", prompt="Katalog ve mesaj")

    query = api.provider().read_document_query(request)

    assert query == validate_document_query(query_payload(), known_slugs=SLUGS)
    body = api.body()
    assert body["system"] == "İstek talimatı"
    # Görüntü yok: kullanıcı turunda yalnız metin.
    assert body["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "Katalog ve mesaj"}]}
    ]
    assert body["tools"] == [json.loads(json.dumps(DOCUMENT_QUERY_TOOL))]
    assert body["tools"][0]["input_schema"] == DocumentQuery.model_json_schema()
    assert body["tool_choice"] == {
        "type": "tool",
        "name": DOCUMENT_QUERY_TOOL_NAME,
        "disable_parallel_tool_use": True,
    }
    assert body["thinking"] == {"type": "disabled"}


@pytest.mark.parametrize(
    ("content", "stop_reason", "expected"),
    [
        (
            [tool_use(query_payload(), name=DOCUMENT_QUERY_TOOL_NAME)],
            "max_tokens",
            "belge isteği aracı çağrısı tamamlanmadı (stop_reason=max_tokens)",
        ),
        (
            [{"type": "text", "text": "Ornekova'nın ehliyeti"}],
            "end_turn",
            "belge isteği aracı çağrısı tamamlanmadı (stop_reason=end_turn)",
        ),
        ([tool_use(query_payload())], "tool_use", "1 araç çağrısı"),
    ],
    ids=["kesik", "metin", "analiz-araci"],
)
def test_document_query_response_without_query_tool_call_is_rejected(
    content: list[dict[str, Any]], stop_reason: str, expected: str
) -> None:
    api = FakeApi(message(content, stop_reason=stop_reason))

    with pytest.raises(DocumentQueryError) as caught:
        api.provider().read_document_query(query_request())

    assert caught.value.problems[0].startswith("yanıt:")
    assert expected in caught.value.problems[0]


def test_document_query_drops_a_slug_outside_the_catalog() -> None:
    # §D109: katalog dışı slug atılır, istek düşmez.
    payload = query_payload(types=("diploma",))
    api = FakeApi(message([tool_use(payload, name=DOCUMENT_QUERY_TOOL_NAME)]))

    query = api.provider().read_document_query(query_request())

    assert query.documents[0].types == ()


# --- Canlı çağrı (DoD kapısında dışarıda) ------------------------------------------------------


@pytest.mark.live
def test_live_anthropic_returns_schema_conforming_analysis() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY tanımlı değil")
    live_settings = load_settings(
        _env_file=None, database_url="sqlite://", anthropic_api_key=api_key
    )
    provider = AnthropicProvider.from_settings(live_settings)
    request = page_request(
        instructions=(
            "Bir belge sayfasının görüntüsünü analiz et ve sonucu record_page_analysis aracıyla "
            "kaydet. Okuyamadığın veya sayfada yazılı olmayan her değer null olsun; tahmin etme. "
            "Katalogdaki türlerden biri değilse document_type_slug null olsun. Katalog: "
            + ", ".join(SLUGS)
        ),
        prompt="page_index: 0. Sayfanın metin katmanı yok.",
    )

    analysis = provider.analyze_page(request)

    assert analysis.page_index == 0
