"""OpenAI sağlayıcısı — PRD 03.3.1.

`AnalysisProvider`'ın ikinci somut uygulaması (`AI_PROVIDER=openai`); Anthropic ile aynı sözleşme
ve aynı hata aileleri, yalnız API biçimi farklıdır. Chat Completions API'ye tek bir istek gider:
`system` mesajında sistem talimatı, kullanıcı mesajında önce sayfa görüntüsü (base64 veri URL'si),
sonra sayfaya özgü metin. İstek içeriği `PageAnalysisRequest`'ten olduğu gibi alınır, burada
talimat yazılmaz (03.4).

Yapılandırılmış çıktı Anthropic'teki gibi zorlanmış araç çağrısıyla alınır: tek işlev
(`TOOL_NAME`), parametre şeması `PageAnalysis.model_json_schema()`, `tool_choice` bu işleve sabit.
Katı mod (`strict`) kapalıdır: katı şema her nesnede `additionalProperties: false` ister ve
`patternProperties`'i kabul etmez, §8.4'ün `fields`'ı ise alan adı anahtarlı bir sözlüktür (§C13).
Modelin işlev argümanları ham yanıttır; kabulü `AnalysisProvider.analyze_page`
`validate_page_analysis` ile yapar.

Tür açıklaması (11.3.1) aynı biçimde istenir: kullanıcı mesajında türün örnek sayfaları (sırayla,
birkaç görüntü), sonra türe özgü metin; zorlanmış işlev `DESCRIPTION_TOOL_NAME`, parametre şeması
`TypeDescription.model_json_schema()`.

Tür taslağı (11.5.5) da aynı biçimdedir: kullanıcı mesajında aday türün örnek sayfaları (sırayla,
birkaç görüntü), sonra adaya özgü metin; zorlanmış işlev `PROPOSAL_TOOL_NAME`, parametre şeması
`TypeProposal.model_json_schema()`.

Fotoğraf kontrolü (11.7.1) de aynı biçimdedir: kullanıcı mesajında fotoğraf sayfasının görüntüsü,
sonra değerlendirilecek kuralların metni; zorlanmış işlev `PHOTO_CHECK_TOOL_NAME`, parametre şeması
`PhotoCheck.model_json_schema()`.

Belge isteği (12.3.1) görüntüsüzdür: kullanıcı mesajında yalnız katalog ve İK'nın mesajı; zorlanmış
işlev `DOCUMENT_QUERY_TOOL_NAME`, parametre şeması `DocumentQuery.model_json_schema()`.

SDK'nın kendi yeniden denemesi kapalıdır (`max_retries=0`): geri çekilmeli deneme 03.5'in işidir,
iki katman üst üste denemesin. İstek `store=False` gider: sayfa görüntüsü kimlik belgesi olabilir,
sağlayıcı tarafında saklanmasını istemiyoruz (CONVENTIONS §6).

İstek `reasoning_effort="none"` gider: GPT-6 Luna Chat Completions'ta işlev çağrısını bu ayarla
destekler (OpenAI model dokümanı). Yanıtın kabulü akıl yürütmeye dayanmaz: her yanıt `validate_*`
şemasından geçer.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Sequence

import httpx2
import openai
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionFunctionToolParam,
    ChatCompletionMessageParam,
)

from app.ai.document_query import DocumentQuery, DocumentQueryError
from app.ai.photo_check import PhotoCheck, PhotoCheckError
from app.ai.provider import (
    AnalysisProvider,
    DocumentQueryRequest,
    PageAnalysisRequest,
    PageImage,
    PhotoCheckRequest,
    ProviderConfigError,
    ProviderConnectionError,
    ProviderError,
    ProviderRateLimitError,
    ProviderServerError,
    TypeDescriptionRequest,
    TypeProposalRequest,
)
from app.ai.schemas import PageAnalysis, PageAnalysisError
from app.ai.type_description import TypeDescription, TypeDescriptionError
from app.ai.type_proposal import TypeProposal, TypeProposalError
from app.ai.usage import report_usage
from app.config import Settings

TOOL_NAME = "record_page_analysis"

ANALYSIS_TOOL: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "Tek sayfanın analiz sonucunu kaydeder. Argümanlar, sayfa analizi şemasındaki her "
            "anahtarı taşıyan tek bir nesnedir."
        ),
        "parameters": PageAnalysis.model_json_schema(),
        "strict": False,
    },
}

DESCRIPTION_TOOL_NAME = "record_type_description"

DESCRIPTION_TOOL: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": DESCRIPTION_TOOL_NAME,
        "description": (
            "Belge türünün örneklerinden çıkarılan yapılandırılmış açıklamayı kaydeder. "
            "Argümanlar, tür açıklaması şemasındaki her anahtarı taşıyan tek bir nesnedir."
        ),
        "parameters": TypeDescription.model_json_schema(),
        "strict": False,
    },
}

PROPOSAL_TOOL_NAME = "record_type_proposal"

PROPOSAL_TOOL: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": PROPOSAL_TOOL_NAME,
        "description": (
            "Katalog dışı belge türünün örneklerinden çıkarılan tam katalog kaydı taslağını "
            "kaydeder. Argümanlar, tür taslağı şemasındaki her anahtarı taşıyan tek bir nesnedir."
        ),
        "parameters": TypeProposal.model_json_schema(),
        "strict": False,
    },
}

PHOTO_CHECK_TOOL_NAME = "record_photo_check"

PHOTO_CHECK_TOOL: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": PHOTO_CHECK_TOOL_NAME,
        "description": (
            "Profil fotoğrafının kurallara göre değerlendirmesini kaydeder. Argümanlar, sorulan "
            "her kural için bir satır taşıyan tek bir nesnedir."
        ),
        "parameters": PhotoCheck.model_json_schema(),
        "strict": False,
    },
}

DOCUMENT_QUERY_TOOL_NAME = "record_document_query"

DOCUMENT_QUERY_TOOL: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": DOCUMENT_QUERY_TOOL_NAME,
        "description": (
            "İK'nın mesajının belge isteği olarak okunmasını kaydeder: kimin, hangi tür belgesi "
            "istendi ya da mesajın belge isteği olmadığı. Argümanlar, belge isteği şemasındaki "
            "her anahtarı taşıyan tek bir nesnedir."
        ),
        "parameters": DocumentQuery.model_json_schema(),
        "strict": False,
    },
}

_UNFINISHED_FINISH_REASONS = frozenset({"length", "content_filter"})
"""`length` kesik argüman, `content_filter` süzülmüş çıktıdır — araç çağrısı varmış gibi görünse de
kabul edilmez. (Zorlanmış işlev seçiminde `finish_reason` `tool_calls` yerine `stop` gelebilir; bu
yüzden kabul ölçütü `finish_reason` değil, tek ve tam bir işlev çağrısıdır.)"""

_PERMANENT_RATE_LIMIT_CODES = frozenset({"insufficient_quota"})
"""429 ile dönen ama beklemekle geçmeyen durumlar (kota/bakiye bitti): yeniden denenmez."""


class OpenAIProvider(AnalysisProvider):
    """OpenAI Chat Completions API ile sayfa analizi, tür açıklaması, tür taslağı, fotoğraf kontrolü
    ve belge isteği (`AI_PROVIDER=openai`)."""

    name = "openai"

    def __init__(
        self,
        client: openai.OpenAI,
        *,
        model: str,
        max_output_tokens: int,
        prescreen_model: str | None = None,
    ) -> None:
        super().__init__(model=model, prescreen_model=prescreen_model)
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens pozitif olmalı")
        self._client = client
        self._max_output_tokens = max_output_tokens

    @classmethod
    def from_settings(
        cls, settings: Settings, *, http_client: httpx2.Client | None = None
    ) -> OpenAIProvider:
        """Ayarlardan istemci kurar; `OPENAI_API_KEY` boşsa `ProviderConfigError`.

        `http_client` yalnız taşıma katmanını değiştirmek içindir (test, vekil).
        """
        api_key = settings.openai_api_key
        if api_key is None or not api_key.get_secret_value().strip():
            raise ProviderConfigError(
                "AI_PROVIDER=openai için OPENAI_API_KEY tanımlı olmalı. "
                "Bkz. .env.example dosyasındaki açıklama."
            )
        client = openai.OpenAI(
            api_key=api_key.get_secret_value().strip(),
            max_retries=0,
            timeout=settings.ai_request_timeout_seconds,
            http_client=http_client,
        )
        return cls(
            client,
            model=settings.openai_model,
            max_output_tokens=settings.ai_max_output_tokens,
            prescreen_model=settings.openai_prescreen_model,
        )

    def _with_model(self, model: str) -> OpenAIProvider:
        # Ön eleme kopyası aynı istemciyi (anahtar, zaman aşımı, taşıma) paylaşır (13.2.1).
        return OpenAIProvider(self._client, model=model, max_output_tokens=self._max_output_tokens)

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        return self._forced_function_call(
            request.instructions,
            (request.image,),
            request.prompt,
            ANALYSIS_TOOL,
            label="analiz işlevi",
            error=PageAnalysisError,
        )

    def _request_description(self, request: TypeDescriptionRequest) -> object:
        return self._forced_function_call(
            request.instructions,
            request.images,
            request.prompt,
            DESCRIPTION_TOOL,
            label="tür açıklaması işlevi",
            error=TypeDescriptionError,
        )

    def _request_type_proposal(self, request: TypeProposalRequest) -> object:
        return self._forced_function_call(
            request.instructions,
            request.images,
            request.prompt,
            PROPOSAL_TOOL,
            label="tür taslağı işlevi",
            error=TypeProposalError,
        )

    def _request_photo_check(self, request: PhotoCheckRequest) -> object:
        return self._forced_function_call(
            request.instructions,
            (request.image,),
            request.prompt,
            PHOTO_CHECK_TOOL,
            label="fotoğraf kontrolü işlevi",
            error=PhotoCheckError,
        )

    def _request_document_query(self, request: DocumentQueryRequest) -> object:
        return self._forced_function_call(
            request.instructions,
            (),
            request.prompt,
            DOCUMENT_QUERY_TOOL,
            label="belge isteği işlevi",
            error=DocumentQueryError,
        )

    def _forced_function_call(
        self,
        instructions: str,
        images: Sequence[PageImage],
        prompt: str,
        tool: ChatCompletionFunctionToolParam,
        *,
        label: str,
        error: Callable[[list[str]], Exception],
    ) -> object:
        """Görüntüler (sırayla; olmayabilir) ve metinle tek istek; `tool` işlevi zorlanır,
        argümanları doğrulanmadan döner. Yanıtta tek ve tam bir `tool` çağrısı yoksa `error`
        (`label` mesajdaki işlev adıdır)."""
        name = tool["function"]["name"]
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": [
                    # Kimlik belgesindeki küçük yazıların okunması için en yüksek ayrıntı.
                    *(
                        {
                            "type": "image_url",
                            "image_url": {"url": _data_url(image), "detail": "high"},
                        }
                        for image in images
                    ),
                    {"type": "text", "text": prompt},
                ],
            },
        ]
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                max_completion_tokens=self._max_output_tokens,
                messages=messages,
                tools=[tool],
                tool_choice={"type": "function", "function": {"name": name}},
                parallel_tool_calls=False,
                store=False,
                # Akıl yürütmeli modeller işlevi yalnız bu değerle kabul eder (modül belgesi).
                reasoning_effort="none",
            )
        except openai.APIStatusError as exc:
            raise _status_error(exc) from exc
        except openai.APIConnectionError as exc:
            raise ProviderConnectionError(f"OpenAI'ye ulaşılamadı: {type(exc).__name__}") from exc
        except openai.OpenAIError as exc:
            raise ProviderError(f"OpenAI isteği başarısız: {type(exc).__name__}") from exc
        # Yanıt reddedilse de token harcanmıştır (13.1.1): kabulden önce bildirilir. Çıktı
        # tokenları (`completion_tokens`) akıl yürütme tokenlarını da içerir; `prompt_tokens`
        # önbellekten okunan kısmı (`prompt_tokens_details.cached_tokens`) içerir.
        usage = getattr(response, "usage", None)
        report_usage(
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
            getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", None),
        )
        return _tool_arguments(response, name, label, error)


def _data_url(image: PageImage) -> str:
    return f"data:{image.media_type};base64,{base64.b64encode(image.data).decode('ascii')}"


def _status_error(exc: openai.APIStatusError) -> ProviderError:
    status = exc.status_code
    message = f"OpenAI isteği başarısız: HTTP {status}{_error_detail(exc.body)}"
    if status == 429 and exc.code not in _PERMANENT_RATE_LIMIT_CODES:
        return ProviderRateLimitError(message, status_code=status)
    if status >= 500:
        return ProviderServerError(message, status_code=status)
    return ProviderError(message, status_code=status)


def _error_detail(body: object) -> str:
    # SDK hata gövdesini açar: {"message": ..., "type": ..., "code": ...}. Gövde isteğin
    # içeriğini (görüntü, metin) tekrarlamaz; yalnız tür, kod ve açıklama alınır.
    if not isinstance(body, dict):
        return ""
    parts = [str(body[key]) for key in ("type", "code", "message") if body.get(key)]
    return f" ({': '.join(parts)})" if parts else ""


def _tool_arguments(
    response: ChatCompletion, name: str, label: str, error: Callable[[list[str]], Exception]
) -> object:
    """Yanıttaki tek `name` işlevi çağrısının argümanları; tamamlanmadıysa yanıt `error` ile
    reddedilir."""
    if len(response.choices) != 1:
        raise error([f"yanıt: tek seçenek beklenir ({len(response.choices)} seçenek)"])
    choice = response.choices[0]
    if choice.finish_reason in _UNFINISHED_FINISH_REASONS:
        raise error([f"yanıt: {label} çağrısı tamamlanmadı (finish_reason={choice.finish_reason})"])
    calls = choice.message.tool_calls or []
    if len(calls) != 1 or calls[0].type != "function" or calls[0].function.name != name:
        # Ret (`refusal`) ve işlevsiz yanıt (`stop`) buraya düşer; ret metni mesaja alınmaz.
        reason = "refusal" if choice.message.refusal else choice.finish_reason
        raise error(
            [
                f"yanıt: yalnız bir '{name}' çağrısı olmalı "
                f"({len(calls)} araç çağrısı, finish_reason={reason})"
            ]
        )
    return calls[0].function.arguments
