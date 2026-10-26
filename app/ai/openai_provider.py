"""OpenAI sağlayıcısı — PRD 03.3.1.

`AnalysisProvider`'ın ikinci somut uygulaması (`AI_PROVIDER=openai`); Anthropic ile aynı sözleşme
ve aynı hata aileleri, yalnız API biçimi farklıdır. Responses API'ye tek bir istek gider:
`instructions`'ta sistem talimatı, kullanıcı girdisinde önce sayfa görüntüsü (base64 veri URL'si),
sonra sayfaya özgü metin. (Chat Completions yerine Responses: GPT-6.1 Sol işlev çağrısını yalnız
orada destekler; PLAN.md §D127.) İstek içeriği `PageAnalysisRequest`'ten olduğu gibi alınır, burada
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

Eğitim sınıflandırması (11.9.3) da aynı biçimdedir: kullanıcı mesajında belgenin ilk sayfası (PDF'te
ilk iki sayfası, sırayla), sonra öğeye özgü metin; zorlanmış işlev `TRAINING_TOOL_NAME`, parametre
şeması `TrainingClassification.model_json_schema()`.

Şablon incelemesi (15.1.2) de aynı biçimdedir: kullanıcı mesajında şablonun bütün sayfaları
(sırayla), sonra şablona özgü metin; zorlanmış işlev `TEMPLATE_MAP_TOOL_NAME`, parametre şeması
`TemplateFieldMap.model_json_schema()`.

Fotoğraf kontrolü (11.7.1) de aynı biçimdedir: kullanıcı mesajında fotoğraf sayfasının görüntüsü,
sonra değerlendirilecek kuralların metni; zorlanmış işlev `PHOTO_CHECK_TOOL_NAME`, parametre şeması
`PhotoCheck.model_json_schema()`.

Belge isteği (12.3.1) görüntüsüzdür: kullanıcı mesajında yalnız katalog ve İK'nın mesajı; zorlanmış
işlev `DOCUMENT_QUERY_TOOL_NAME`, parametre şeması `DocumentQuery.model_json_schema()`.

SDK'nın kendi yeniden denemesi kapalıdır (`max_retries=0`): geri çekilmeli deneme 03.5'in işidir,
iki katman üst üste denemesin. İstek `store=False` gider: sayfa görüntüsü kimlik belgesi olabilir,
sağlayıcı tarafında saklanmasını istemiyoruz (CONVENTIONS §6).

Efor (03.8.2; PLAN.md §D124, §D127): seçilmişse `reasoning.effort` o değerle gider; seçilmemişse
parametre gönderilmez ve modelin varsayılanı geçerlidir (`app.ai.model_list.openai_request_effort`).
`max_output_tokens` düşünme belirteçlerini de kapsar; bu yüzden en az `MIN_OUTPUT_TOKENS`'tır.
Yanıtın kabulü akıl yürütmeye dayanmaz: her yanıt `validate_*` şemasından geçer.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Sequence
from typing import Any

import httpx2
import openai
from openai.types.responses import FunctionToolParam, Response, ResponseInputParam

from app.ai.document_query import DocumentQuery, DocumentQueryError
from app.ai.model_list import check_effort, openai_request_effort
from app.ai.photo_check import PhotoCheck, PhotoCheckError
from app.ai.profile_answer import ProfileAnswer, ProfileAnswerError
from app.ai.provider import (
    AnalysisProvider,
    DocumentQueryRequest,
    PageAnalysisRequest,
    PageImage,
    PhotoCheckRequest,
    ProfileAnswerRequest,
    ProviderConfigError,
    ProviderConnectionError,
    ProviderError,
    ProviderRateLimitError,
    ProviderServerError,
    TemplateMapRequest,
    TrainingClassificationRequest,
    TypeDescriptionRequest,
    TypeProposalRequest,
)
from app.ai.schemas import (
    PageAnalysis,
    PageAnalysisError,
    TemplateFieldMap,
    TemplateFieldMapError,
)
from app.ai.training_classification import TrainingClassification, TrainingClassificationError
from app.ai.type_description import TypeDescription, TypeDescriptionError
from app.ai.type_proposal import TypeProposal, TypeProposalError
from app.config import Settings

TOOL_NAME = "record_page_analysis"

ANALYSIS_TOOL: FunctionToolParam = {
    "type": "function",
    "name": TOOL_NAME,
    "description": (
        "Tek sayfanın analiz sonucunu kaydeder. Argümanlar, sayfa analizi şemasındaki her "
        "anahtarı taşıyan tek bir nesnedir."
    ),
    "parameters": PageAnalysis.model_json_schema(),
    "strict": False,
}

DESCRIPTION_TOOL_NAME = "record_type_description"

DESCRIPTION_TOOL: FunctionToolParam = {
    "type": "function",
    "name": DESCRIPTION_TOOL_NAME,
    "description": (
        "Belge türünün örneklerinden çıkarılan yapılandırılmış açıklamayı kaydeder. "
        "Argümanlar, tür açıklaması şemasındaki her anahtarı taşıyan tek bir nesnedir."
    ),
    "parameters": TypeDescription.model_json_schema(),
    "strict": False,
}

PROPOSAL_TOOL_NAME = "record_type_proposal"

PROPOSAL_TOOL: FunctionToolParam = {
    "type": "function",
    "name": PROPOSAL_TOOL_NAME,
    "description": (
        "Katalog dışı belge türünün örneklerinden çıkarılan tam katalog kaydı taslağını "
        "kaydeder. Argümanlar, tür taslağı şemasındaki her anahtarı taşıyan tek bir nesnedir."
    ),
    "parameters": TypeProposal.model_json_schema(),
    "strict": False,
}

TEMPLATE_MAP_TOOL_NAME = "record_template_field_map"

TEMPLATE_MAP_TOOL: FunctionToolParam = {
    "type": "function",
    "name": TEMPLATE_MAP_TOOL_NAME,
    "description": (
        "Hazır şablonun alan haritasını kaydeder: doldurulacak boşluklar ve doldurulmayacak "
        "imza, kaşe, logo, fotoğraf, çerçeve alanları. Argümanlar, alan haritası şemasındaki "
        "her anahtarı taşıyan tek bir nesnedir."
    ),
    "parameters": TemplateFieldMap.model_json_schema(),
    "strict": False,
}

TRAINING_TOOL_NAME = "record_training_classification"

TRAINING_TOOL: FunctionToolParam = {
    "type": "function",
    "name": TRAINING_TOOL_NAME,
    "description": (
        "Eğitim modundaki belgenin türünü kaydeder: katalog türü, ülke, tür, önerilen ad ve "
        "yüz. Argümanlar, eğitim sınıflandırması şemasındaki her anahtarı taşıyan tek bir "
        "nesnedir."
    ),
    "parameters": TrainingClassification.model_json_schema(),
    "strict": False,
}

PHOTO_CHECK_TOOL_NAME = "record_photo_check"

PHOTO_CHECK_TOOL: FunctionToolParam = {
    "type": "function",
    "name": PHOTO_CHECK_TOOL_NAME,
    "description": (
        "Profil fotoğrafının kurallara göre değerlendirmesini kaydeder. Argümanlar, sorulan "
        "her kural için bir satır taşıyan tek bir nesnedir."
    ),
    "parameters": PhotoCheck.model_json_schema(),
    "strict": False,
}

DOCUMENT_QUERY_TOOL_NAME = "record_document_query"

DOCUMENT_QUERY_TOOL: FunctionToolParam = {
    "type": "function",
    "name": DOCUMENT_QUERY_TOOL_NAME,
    "description": (
        "İK'nın bota yazdığı mesajın okunmasını kaydeder: kimin hangi belgeleri, bilgisi "
        "ya da eksik belgeleri istendi, mesaj hangi dilde ya da mesajın istek olmadığı. "
        "Tek bir nesnedir; şemadaki her anahtarı taşır."
    ),
    "parameters": DocumentQuery.model_json_schema(),
    "strict": False,
}

MIN_OUTPUT_TOKENS = 16000
"""Responses API'de `max_output_tokens` düşünme belirteçlerini de sayar; ayar bundan küçükse bu
değer gider (Anthropic `auto` biçimindeki taban ile aynı gerekçe)."""

_PERMANENT_RATE_LIMIT_CODES = frozenset({"insufficient_quota"})
"""429 ile dönen ama beklemekle geçmeyen durumlar (kota/bakiye bitti): yeniden denenmez."""


PROFILE_ANSWER_TOOL_NAME = "record_profile_answer"

PROFILE_ANSWER_TOOL: FunctionToolParam = {
    "type": "function",
    "name": PROFILE_ANSWER_TOOL_NAME,
    "description": (
        "İK'nın çalışanlar hakkındaki sorusuna, yalnız verilen profillerden yazılmış kısa "
        "yanıtı kaydeder."
    ),
    "parameters": ProfileAnswer.model_json_schema(),
    "strict": False,
}


class OpenAIProvider(AnalysisProvider):
    """OpenAI Chat Completions API ile sayfa analizi, tür açıklaması, tür taslağı, eğitim
    sınıflandırması, fotoğraf kontrolü ve belge isteği (`AI_PROVIDER=openai`)."""

    name = "openai"

    def __init__(
        self,
        client: openai.OpenAI,
        *,
        model: str,
        max_output_tokens: int,
        prescreen_model: str | None = None,
        effort: str | None = None,
    ) -> None:
        super().__init__(model=model, prescreen_model=prescreen_model, effort=effort)
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens pozitif olmalı")
        self._client = client
        self._max_output_tokens = max_output_tokens

    @classmethod
    def from_settings(
        cls, settings: Settings, *, http_client: httpx2.Client | None = None
    ) -> OpenAIProvider:
        """Ayarlardan istemci kurar; `OPENAI_API_KEY` boşsa ya da efor modelde seçilemiyorsa
        `ProviderConfigError`.

        `http_client` yalnız taşıma katmanını değiştirmek içindir (test, vekil).
        """
        api_key = settings.openai_api_key
        if api_key is None or not api_key.get_secret_value().strip():
            raise ProviderConfigError(
                "AI_PROVIDER=openai için OPENAI_API_KEY tanımlı olmalı. "
                "Bkz. .env.example dosyasındaki açıklama."
            )
        try:
            check_effort(cls.name, settings.openai_model, settings.openai_effort)
        except ValueError as exc:
            raise ProviderConfigError(str(exc)) from None
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
            effort=settings.openai_effort,
        )

    def _with_model(self, model: str) -> OpenAIProvider:
        # Ön eleme kopyası aynı istemciyi (anahtar, zaman aşımı, taşıma) paylaşır (13.2.1). Efor ana
        # modelin seçimidir; ön eleme modeli kendi varsayılan eforuyla çalışır.
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

    def _request_template_map(self, request: TemplateMapRequest) -> object:
        return self._forced_function_call(
            request.instructions,
            request.images,
            request.prompt,
            TEMPLATE_MAP_TOOL,
            label="alan haritası işlevi",
            error=TemplateFieldMapError,
        )

    def _request_training_classification(self, request: TrainingClassificationRequest) -> object:
        return self._forced_function_call(
            request.instructions,
            request.images,
            request.prompt,
            TRAINING_TOOL,
            label="eğitim sınıflandırması işlevi",
            error=TrainingClassificationError,
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

    def _request_profile_answer(self, request: ProfileAnswerRequest) -> object:
        return self._forced_function_call(
            request.instructions,
            (),
            request.prompt,
            PROFILE_ANSWER_TOOL,
            label="profil yanıtı işlevi",
            error=ProfileAnswerError,
        )

    def _forced_function_call(
        self,
        instructions: str,
        images: Sequence[PageImage],
        prompt: str,
        tool: FunctionToolParam,
        *,
        label: str,
        error: Callable[[list[str]], Exception],
    ) -> object:
        """Görüntüler (sırayla; olmayabilir) ve metinle tek istek; `tool` işlevi zorlanır,
        argümanları doğrulanmadan döner. Yanıtta tek ve tam bir `tool` çağrısı yoksa `error`
        (`label` mesajdaki işlev adıdır)."""
        name = tool["name"]
        content: list[dict[str, str]] = [
            # Kimlik belgesindeki küçük yazıların okunması için en yüksek ayrıntı.
            *(
                {"type": "input_image", "image_url": _data_url(image), "detail": "high"}
                for image in images
            ),
            {"type": "input_text", "text": prompt},
        ]
        user_input: ResponseInputParam = [{"role": "user", "content": content}]  # type: ignore[list-item]
        # Efor: yalnız seçilmişse gider (modül belgesi).
        effort = openai_request_effort(self.model, self.effort)
        options: dict[str, Any] = {} if effort is None else {"reasoning": {"effort": effort}}
        try:
            response = self._client.responses.create(
                model=self.model,
                instructions=instructions,
                input=user_input,
                max_output_tokens=max(self._max_output_tokens, MIN_OUTPUT_TOKENS),
                tools=[tool],
                tool_choice={"type": "function", "name": name},
                parallel_tool_calls=False,
                store=False,
                **options,
            )
        except openai.APIStatusError as exc:
            raise _status_error(exc) from exc
        except openai.APIConnectionError as exc:
            raise ProviderConnectionError(f"OpenAI'ye ulaşılamadı: {type(exc).__name__}") from exc
        except openai.OpenAIError as exc:
            raise ProviderError(f"OpenAI isteği başarısız: {type(exc).__name__}") from exc
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
    response: Response, name: str, label: str, error: Callable[[list[str]], Exception]
) -> object:
    """Yanıttaki tek `name` işlevi çağrısının argümanları. `incomplete` yanıt (`max_output_tokens`
    kesik argüman, `content_filter` süzülmüş çıktı) araç çağrısı varmış gibi görünse de `error` ile
    reddedilir."""
    if response.status == "incomplete":
        reason = response.incomplete_details.reason if response.incomplete_details else None
        raise error([f"yanıt: {label} çağrısı tamamlanmadı (reason={reason})"])
    calls = [item for item in response.output if item.type == "function_call"]
    if len(calls) != 1 or calls[0].name != name:
        # Ret (`refusal`) ve işlevsiz yanıt buraya düşer; ret metni mesaja alınmaz.
        refused = any(
            part.type == "refusal"
            for item in response.output
            if item.type == "message"
            for part in item.content
        )
        reason = "refusal" if refused else response.status
        raise error(
            [
                f"yanıt: yalnız bir '{name}' çağrısı olmalı "
                f"({len(calls)} araç çağrısı, status={reason})"
            ]
        )
    return calls[0].arguments
