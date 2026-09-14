"""03.2.1 — sağlayıcı `.env` ile değişir; boru hattı kodu değişmez.

Boru hattı yalnız `create_provider(settings).analyze_page(request)` çağırır. Yanıt kabulü
(§8.4 şeması, katalog, sayfa sırası) sağlayıcıdan bağımsız ortak adımdır ve atlanamaz.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx2
import pytest
from pydantic import ValidationError

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
    create_provider,
    validate_page_analysis,
)
from app.ai.anthropic_provider import TOOL_NAME, AnthropicProvider
from app.ai.provider import MAX_ANALYSIS_ATTEMPTS, RETRY_BACKOFF_SECONDS
from app.config import Settings, load_settings
from tests.ai.payloads import (
    SLUGS,
    SYNTHETIC_DOCUMENT_NUMBER,
    SYNTHETIC_SURNAME,
    analysis_payload,
    page_request,
)
from tests.fixtures.gen import make_half_filled_image_bytes, make_pdf_bytes


class CannedProvider(AnalysisProvider):
    """Ağsız test sağlayıcısı: verilen yanıtı döner veya verilen hatayı fırlatır."""

    name = "kayitli"

    def __init__(self, response: object, *, model: str = "kayitli-model") -> None:
        super().__init__(model=model)
        self.response = response
        self.requests: list[PageAnalysisRequest] = []

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class QueuedProvider(AnalysisProvider):
    """Her çağrıda sırayla bir sonraki yanıtı/hatayı döner (03.5.1 yeniden deneme senaryoları)."""

    name = "kuyruklu"

    def __init__(self, responses: list[object], *, model: str = "kuyruklu-model") -> None:
        super().__init__(model=model)
        self._responses = list(responses)
        self.requests: list[PageAnalysisRequest] = []

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        self.requests.append(request)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def settings(**overrides: object) -> Settings:
    return load_settings(_env_file=None, database_url="sqlite://", **overrides)


# --- İstek sözleşmesi --------------------------------------------------------------------------


@pytest.mark.parametrize(("fmt", "media_type"), [("JPEG", "image/jpeg"), ("PNG", "image/png")])
def test_page_image_media_type_comes_from_content(fmt: str, media_type: str) -> None:
    content = make_half_filled_image_bytes(fmt)

    image = PageImage(content)

    assert image.media_type == media_type
    assert image.data == content


@pytest.mark.parametrize(
    "content",
    [make_pdf_bytes(), b"", b"GIF89a\x01\x00\x01\x00", b"\x00" * 64],
    ids=["pdf", "bos", "gif", "rastgele"],
)
def test_page_image_rejects_non_jpeg_png(content: bytes) -> None:
    with pytest.raises(ValueError, match="JPEG veya PNG"):
        PageImage(content)


def test_page_image_media_type_is_not_caller_supplied() -> None:
    with pytest.raises(TypeError):
        PageImage(make_half_filled_image_bytes("PNG"), media_type="image/jpeg")  # type: ignore[call-arg]


def test_request_copies_known_slugs_and_hides_text_from_repr() -> None:
    slugs = ["russian_passport", "work_permit"]

    request = page_request(
        page_index=3, instructions="GIZLI TALIMAT", prompt=SYNTHETIC_SURNAME, known_slugs=slugs
    )
    slugs.append("sonradan_eklenen")

    assert request.page_index == 3
    assert request.known_slugs == frozenset({"russian_passport", "work_permit"})
    # Metin katmanı ad/numara taşıyabilir; istek loglanırsa açık yazılmasın (CONVENTIONS §6).
    assert SYNTHETIC_SURNAME not in repr(request)
    assert "GIZLI TALIMAT" not in repr(request)
    assert "data" not in repr(request.image)


def test_request_is_immutable() -> None:
    request = page_request()

    with pytest.raises(AttributeError):
        request.page_index = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "error", "message"),
    [
        ({"page_index": -1}, ValueError, "page_index"),
        ({"page_index": True}, ValueError, "page_index"),
        ({"page_index": 1.0}, ValueError, "page_index"),
        ({"instructions": ""}, ValueError, "instructions"),
        ({"instructions": "  \n"}, ValueError, "instructions"),
        ({"prompt": ""}, ValueError, "prompt"),
        ({"image": make_half_filled_image_bytes()}, TypeError, "PageImage"),
        ({"known_slugs": "russian_passport"}, TypeError, "known_slugs"),
    ],
)
def test_request_rejects_invalid_fields(
    changes: dict[str, object], error: type[Exception], message: str
) -> None:
    fields: dict[str, object] = {
        "page_index": 0,
        "image": PageImage(make_half_filled_image_bytes()),
        "instructions": "talimat",
        "prompt": "sayfa",
        "known_slugs": SLUGS,
    }
    fields.update(changes)

    with pytest.raises(error, match=message):
        PageAnalysisRequest(**fields)  # type: ignore[arg-type]


# --- Ortak yanıt kabulü ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "response",
    [analysis_payload(), json.dumps(analysis_payload()), json.dumps(analysis_payload()).encode()],
    ids=["nesne", "json-metni", "json-bayt"],
)
def test_analyze_page_returns_validated_analysis(response: object) -> None:
    provider = CannedProvider(response)
    request = page_request()

    analysis = provider.analyze_page(request)

    assert isinstance(analysis, PageAnalysis)
    assert analysis == validate_page_analysis(analysis_payload(), known_slugs=SLUGS)
    assert provider.requests == [request]


@pytest.mark.parametrize(
    ("response", "location"),
    [
        (analysis_payload(script="greek"), "script"),
        (analysis_payload(extra="x"), "extra"),
        ({k: v for k, v in analysis_payload().items() if k != "fields"}, "fields"),
        ("{bozuk json", "yanıt"),
        (None, "yanıt"),
    ],
    ids=["kume-disi-alfabe", "tanimsiz-anahtar", "eksik-anahtar", "bozuk-json", "null"],
)
def test_analyze_page_rejects_non_conforming_response(response: object, location: str) -> None:
    with pytest.raises(PageAnalysisError) as caught:
        CannedProvider(response).analyze_page(page_request())

    assert any(problem.startswith(location) for problem in caught.value.problems)


def test_analyze_page_checks_slug_against_request_catalog() -> None:
    provider = CannedProvider(analysis_payload(document_type_slug="russian_passport"))

    with pytest.raises(PageAnalysisError, match="document_type_slug"):
        provider.analyze_page(page_request(known_slugs=("work_permit",)))


def test_analyze_page_rejects_answer_for_another_page() -> None:
    provider = CannedProvider(analysis_payload(page_index=1))

    with pytest.raises(PageAnalysisError) as caught:
        provider.analyze_page(page_request(page_index=2))

    assert caught.value.problems == ["page_index: istenen sayfa 2, yanıt sayfa 1 için"]


def test_rejection_does_not_echo_personal_values() -> None:
    payload = analysis_payload()
    payload["person"]["document_number"] = ""  # boş metin reddedilir
    payload["person"]["surname"] = SYNTHETIC_SURNAME * 40  # 255 karakter sınırını aşar

    with pytest.raises(PageAnalysisError) as caught:
        CannedProvider(payload).analyze_page(page_request())

    assert SYNTHETIC_SURNAME not in str(caught.value)
    assert SYNTHETIC_DOCUMENT_NUMBER not in str(caught.value)


def test_provider_requires_model_name() -> None:
    with pytest.raises(ValueError, match="model"):
        CannedProvider(analysis_payload(), model="")


# --- Yeniden deneme (03.5.1) --------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        ProviderRateLimitError("hız sınırı", status_code=429),
        ProviderServerError("sunucu hatası", status_code=503),
    ],
    ids=["hiz-siniri", "5xx"],
)
def test_analyze_page_retries_and_succeeds(error: ProviderError, no_sleep: list[float]) -> None:
    provider = QueuedProvider([error, error, analysis_payload()])
    request = page_request()

    analysis = provider.analyze_page(request)

    assert isinstance(analysis, PageAnalysis)
    assert provider.requests == [request, request, request]
    assert no_sleep == [RETRY_BACKOFF_SECONDS, RETRY_BACKOFF_SECONDS * 2]


@pytest.mark.parametrize(
    "error",
    [
        ProviderRateLimitError("hız sınırı", status_code=429),
        ProviderServerError("sunucu hatası", status_code=503),
    ],
    ids=["hiz-siniri", "5xx"],
)
def test_analyze_page_gives_up_after_max_attempts(
    error: ProviderError, no_sleep: list[float]
) -> None:
    provider = QueuedProvider([error, error, error])

    with pytest.raises(type(error)) as caught:
        provider.analyze_page(page_request())

    assert caught.value is error
    assert isinstance(caught.value, ProviderError)
    assert len(provider.requests) == MAX_ANALYSIS_ATTEMPTS == 3
    assert len(no_sleep) == MAX_ANALYSIS_ATTEMPTS - 1


@pytest.mark.parametrize(
    "error",
    [
        ProviderConnectionError("bağlantı yok"),
        ProviderError("bilinmeyen 4xx", status_code=400),
    ],
    ids=["baglanti", "diger-4xx"],
)
def test_analyze_page_does_not_retry_non_retryable_provider_errors(
    error: ProviderError, no_sleep: list[float]
) -> None:
    provider = CannedProvider(error)

    with pytest.raises(type(error)) as caught:
        provider.analyze_page(page_request())

    assert caught.value is error
    assert len(provider.requests) == 1
    assert no_sleep == []


def test_analyze_page_does_not_retry_page_analysis_error(no_sleep: list[float]) -> None:
    error = PageAnalysisError(["yanıt: analiz aracı çağrısı tamamlanmadı"])
    provider = CannedProvider(error)

    with pytest.raises(PageAnalysisError) as caught:
        provider.analyze_page(page_request())

    assert caught.value is error
    assert len(provider.requests) == 1
    assert no_sleep == []


# --- `.env` ile sağlayıcı seçimi ---------------------------------------------------------------


def analyze_with_configured_provider(env_file: Path, request: PageAnalysisRequest) -> PageAnalysis:
    """Boru hattının sağlayıcıyla konuştuğu tek yol — sağlayıcı değişince bu kod değişmez."""
    provider = create_provider(load_settings(_env_file=env_file))
    return provider.analyze_page(request)


def test_provider_switches_with_env_file_without_pipeline_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("AI_PROVIDER", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    anthropic_calls: list[httpx2.Request] = []

    def anthropic_api(request: httpx2.Request) -> httpx2.Response:
        anthropic_calls.append(request)
        tool_use = {
            "type": "tool_use",
            "id": "toolu_1",
            "name": TOOL_NAME,
            "input": analysis_payload(side="front"),
        }
        body = {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-test",
            "content": [tool_use],
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        return httpx2.Response(200, json=body)

    transport = httpx2.Client(transport=httpx2.MockTransport(anthropic_api))
    # Yalnız taşıma katmanı değişir; sağlayıcı yine `.env`'deki ayarlarla kurulur.
    monkeypatch.setitem(
        PROVIDER_FACTORIES,
        "anthropic",
        lambda s: AnthropicProvider.from_settings(s, http_client=transport),
    )
    canned = CannedProvider(analysis_payload(side="back"))
    monkeypatch.setitem(PROVIDER_FACTORIES, "kayitli", lambda s: canned)
    anthropic_env = tmp_path / "anthropic.env"
    anthropic_env.write_text(
        "DATABASE_URL=sqlite://\nAI_PROVIDER=anthropic\n"
        "ANTHROPIC_API_KEY=test-key\nANTHROPIC_MODEL=claude-test\n",
        encoding="utf-8",
    )
    canned_env = tmp_path / "kayitli.env"
    canned_env.write_text("DATABASE_URL=sqlite://\nAI_PROVIDER=kayitli\n", encoding="utf-8")
    request = page_request()

    from_anthropic = analyze_with_configured_provider(anthropic_env, request)
    from_canned = analyze_with_configured_provider(canned_env, request)

    assert from_anthropic.side == "front"
    assert from_canned.side == "back"
    assert len(anthropic_calls) == 1
    assert json.loads(anthropic_calls[0].content)["model"] == "claude-test"
    assert canned.requests == [request]


def test_default_provider_is_anthropic_with_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_PROVIDER", raising=False)

    provider = create_provider(
        settings(anthropic_api_key="test-key", anthropic_model="claude-test")
    )

    assert isinstance(provider, AnthropicProvider)
    assert provider.name == "anthropic"
    assert provider.model == "claude-test"


def test_unknown_provider_name_is_config_error() -> None:
    with pytest.raises(ProviderConfigError, match="Bilinmeyen AI_PROVIDER 'yok'.*anthropic"):
        create_provider(settings(ai_provider="yok"))


def test_anthropic_without_api_key_is_config_error() -> None:
    with pytest.raises(ProviderConfigError, match="ANTHROPIC_API_KEY"):
        create_provider(settings(anthropic_api_key=None))


@pytest.mark.parametrize("value", ["Anthropic", "", "open ai", "1anthropic"])
def test_provider_name_setting_is_lowercase_identifier(value: str) -> None:
    with pytest.raises(ValidationError, match="ai_provider"):
        settings(ai_provider=value)
