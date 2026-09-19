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
    PageAnalysis,
    PageAnalysisError,
    PageAnalysisRequest,
    PageImage,
    ProviderConfigError,
    ProviderConnectionError,
    ProviderError,
    ProviderRateLimitError,
    ProviderServerError,
    Script,
    Side,
    create_provider,
    validate_page_analysis,
)
from app.ai import anthropic_provider as anthropic_module
from app.ai.openai_provider import ANALYSIS_TOOL, TOOL_NAME, OpenAIProvider
from app.ai.provider import MAX_ANALYSIS_ATTEMPTS, RETRY_BACKOFF_SECONDS
from app.ai.schemas import ISO_639_1_CODES
from app.config import Settings, load_settings
from tests.ai.payloads import (
    SLUGS,
    SYNTHETIC_DOCUMENT_NUMBER,
    SYNTHETIC_SURNAME,
    analysis_payload,
    page_request,
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
