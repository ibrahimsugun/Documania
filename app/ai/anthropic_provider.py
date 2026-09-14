"""Anthropic sağlayıcısı — PRD 03.2.2.

Messages API'ye tek bir kullanıcı turu gönderilir: önce sayfa görüntüsü (base64), sonra sayfaya
özgü metin; sistem talimatı `system` alanındadır. İstek içeriği `PageAnalysisRequest`'ten
olduğu gibi alınır, burada talimat yazılmaz (03.4).

Yapılandırılmış çıktı zorlanmış araç çağrısıyla alınır: tek araç (`TOOL_NAME`), girdi şeması
`PageAnalysis.model_json_schema()`, `tool_choice` bu araca sabit. Modelin araç girdisi ham
yanıttır; kabulü `AnalysisProvider.analyze_page` `validate_page_analysis` ile yapar. API'nin katı
`output_config.format` şeması kullanılmaz: her nesnede `additionalProperties: false` ister,
§8.4'ün `fields`'ı ise alan adı anahtarlı bir sözlüktür ve katı şemada boş nesneye iner (§C13).
Zorlanmış araç seçimi genişletilmiş düşünmeyle birlikte kullanılamadığı için düşünme kapalıdır.

SDK'nın kendi yeniden denemesi kapalıdır (`max_retries=0`): geri çekilmeli deneme 03.5'in işidir,
iki katman üst üste denemesin.
"""

from __future__ import annotations

import base64
from typing import Any

import anthropic
import httpx2
from anthropic.types import Message, MessageParam, ToolParam

from app.ai.provider import (
    AnalysisProvider,
    PageAnalysisRequest,
    ProviderConfigError,
    ProviderConnectionError,
    ProviderError,
    ProviderRateLimitError,
    ProviderServerError,
)
from app.ai.schemas import PageAnalysis, PageAnalysisError
from app.config import Settings

TOOL_NAME = "record_page_analysis"

ANALYSIS_TOOL: ToolParam = {
    "name": TOOL_NAME,
    "description": (
        "Tek sayfanın analiz sonucunu kaydeder. Girdi, sayfa analizi şemasındaki her anahtarı "
        "taşıyan tek bir nesnedir."
    ),
    "input_schema": PageAnalysis.model_json_schema(),
}


class AnthropicProvider(AnalysisProvider):
    """Anthropic Messages API ile sayfa analizi (`AI_PROVIDER=anthropic`)."""

    name = "anthropic"

    def __init__(self, client: anthropic.Anthropic, *, model: str, max_output_tokens: int) -> None:
        super().__init__(model=model)
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens pozitif olmalı")
        self._client = client
        self._max_output_tokens = max_output_tokens

    @classmethod
    def from_settings(
        cls, settings: Settings, *, http_client: httpx2.Client | None = None
    ) -> AnthropicProvider:
        """Ayarlardan istemci kurar; `ANTHROPIC_API_KEY` boşsa `ProviderConfigError`.

        `http_client` yalnız taşıma katmanını değiştirmek içindir (test, vekil).
        """
        api_key = settings.anthropic_api_key
        if api_key is None or not api_key.get_secret_value().strip():
            raise ProviderConfigError(
                "AI_PROVIDER=anthropic için ANTHROPIC_API_KEY tanımlı olmalı. "
                "Bkz. .env.example dosyasındaki açıklama."
            )
        client = anthropic.Anthropic(
            api_key=api_key.get_secret_value().strip(),
            max_retries=0,
            timeout=settings.ai_request_timeout_seconds,
            http_client=http_client,
        )
        return cls(
            client,
            model=settings.anthropic_model,
            max_output_tokens=settings.ai_max_output_tokens,
        )

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        message: MessageParam = {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": request.image.media_type,
                        "data": base64.b64encode(request.image.data).decode("ascii"),
                    },
                },
                {"type": "text", "text": request.prompt},
            ],
        }
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self._max_output_tokens,
                system=request.instructions,
                messages=[message],
                tools=[ANALYSIS_TOOL],
                tool_choice={"type": "tool", "name": TOOL_NAME, "disable_parallel_tool_use": True},
                thinking={"type": "disabled"},
            )
        except anthropic.APIStatusError as exc:
            raise _status_error(exc) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderConnectionError(f"Anthropic'e ulaşılamadı: {type(exc).__name__}") from exc
        except anthropic.AnthropicError as exc:
            raise ProviderError(f"Anthropic isteği başarısız: {type(exc).__name__}") from exc
        return _tool_input(response)


def _status_error(exc: anthropic.APIStatusError) -> ProviderError:
    status = exc.status_code
    message = f"Anthropic isteği başarısız: HTTP {status}{_error_detail(exc.body)}"
    if status == 429:
        return ProviderRateLimitError(message, status_code=status)
    if status >= 500:
        return ProviderServerError(message, status_code=status)
    return ProviderError(message, status_code=status)


def _error_detail(body: object) -> str:
    # API hata gövdesi: {"type": "error", "error": {"type": ..., "message": ...}}. Gövde isteğin
    # içeriğini (görüntü, metin) tekrarlamaz; yalnız tür ve açıklama alınır.
    error: Any = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return ""
    parts = [str(error[key]) for key in ("type", "message") if error.get(key)]
    return f" ({': '.join(parts)})" if parts else ""


def _tool_input(response: Message) -> object:
    """Yanıttaki tek analiz aracı çağrısının girdisi; çağrı tamamlanmadıysa yanıt reddedilir."""
    if response.stop_reason != "tool_use":
        # `max_tokens` kesik, `refusal` boş, `end_turn` araçsız yanıttır — hiçbiri kabul edilmez.
        raise PageAnalysisError(
            [f"yanıt: analiz aracı çağrısı tamamlanmadı (stop_reason={response.stop_reason})"]
        )
    calls = [block for block in response.content if block.type == "tool_use"]
    if len(calls) != 1 or calls[0].name != TOOL_NAME:
        raise PageAnalysisError(
            [f"yanıt: yalnız bir '{TOOL_NAME}' çağrısı olmalı ({len(calls)} araç çağrısı)"]
        )
    return calls[0].input
