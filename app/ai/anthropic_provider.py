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

Tür açıklaması (11.3.1) aynı biçimde istenir: kullanıcı turunda türün örnek sayfaları (sırayla,
birkaç görüntü), sonra türe özgü metin; zorlanmış araç `DESCRIPTION_TOOL_NAME`, girdi şeması
`TypeDescription.model_json_schema()`.

Tür taslağı (11.5.5) da aynı biçimdedir: kullanıcı turunda aday türün örnek sayfaları (sırayla,
birkaç görüntü), sonra adaya özgü metin; zorlanmış araç `PROPOSAL_TOOL_NAME`, girdi şeması
`TypeProposal.model_json_schema()`.

Eğitim sınıflandırması (11.9.3) da aynı biçimdedir: kullanıcı turunda belgenin ilk sayfası (PDF'te
ilk iki sayfası, sırayla), sonra öğeye özgü metin; zorlanmış araç `TRAINING_TOOL_NAME`, girdi şeması
`TrainingClassification.model_json_schema()`.

Fotoğraf kontrolü (11.7.1) de aynı biçimdedir: kullanıcı turunda fotoğraf sayfasının görüntüsü,
sonra değerlendirilecek kuralların metni; zorlanmış araç `PHOTO_CHECK_TOOL_NAME`, girdi şeması
`PhotoCheck.model_json_schema()`.

Şablon incelemesi (15.1.2) de aynı biçimdedir: kullanıcı turunda şablonun bütün sayfaları (sırayla),
sonra şablona özgü metin; zorlanmış araç `TEMPLATE_MAP_TOOL_NAME`, girdi şeması
`TemplateFieldMap.model_json_schema()`.

Belge isteği (12.3.1) görüntüsüzdür: kullanıcı turunda yalnız katalog ve İK'nın mesajı; zorlanmış
araç `DOCUMENT_QUERY_TOOL_NAME`, girdi şeması `DocumentQuery.model_json_schema()`.

SDK'nın kendi yeniden denemesi kapalıdır (`max_retries=0`): geri çekilmeli deneme 03.5'in işidir,
iki katman üst üste denemesin.

**Efor ve istek biçimi (03.8.2; PLAN.md §D124).** Efor seçilmişse `output_config.effort` gider,
"varsayılan"da gönderilmez. Zorlanmış araç + kapalı düşünme yalnız onu kabul eden model/efor
bileşiminde kullanılır (`app.ai.model_list.anthropic_request_format`); öteki bileşimlerde (Opus 5.5,
Sonnet 5.5, Fable 5.1; Opus 5 ve Haiku 5.5'te `xhigh`/`max`) istek `tool_choice: auto` (paralel araç
kapalı) ile gider, `thinking` hiç gönderilmez (model uyarlanabilir düşünür), sistem talimatının
sonuna aracın adını söyleyen tek cümle eklenir ve araç şeması izin veriyorsa katıdır (`strict:
true`, şema SDK'nın `transform_schema`'sıyla). Katı şema açık sözlük (`patternProperties`) taşıyamaz
— sayfa analizinin `fields`'ı katı biçimde boş nesneye iner (§C13) — bu yüzden o araç katı
gönderilmez. Düşünme açıkken çıktı sınırı en az `THINKING_MIN_OUTPUT_TOKENS`'tır: düşünme aynı
sınırdan harcar. Araç çağrısı gelmezse ya da kesikse yanıt bugünkü hata yoluyla reddedilir; kabul
yine şema doğrulamasıdır (`validate_*`). `temperature`/`top_p` hiçbir biçimde gönderilmez.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Sequence
from functools import cache
from typing import Any

import anthropic
import httpx2
from anthropic.types import Message, MessageParam, ToolParam

from app.ai.document_query import DocumentQuery, DocumentQueryError
from app.ai.model_list import RequestFormat, anthropic_request_format, check_effort
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

THINKING_MIN_OUTPUT_TOKENS = 16_000
"""Düşünme açıkken (`AUTO_TOOL`) çıktı sınırının alt sınırı: düşünme `max_tokens`'tan harcar, araç
girdisi kesilmesin. Akışsız istekte SDK'nın zaman aşımı sınırının altındadır."""

TOOL_NAME = "record_page_analysis"

ANALYSIS_TOOL: ToolParam = {
    "name": TOOL_NAME,
    "description": (
        "Tek sayfanın analiz sonucunu kaydeder. Girdi, sayfa analizi şemasındaki her anahtarı "
        "taşıyan tek bir nesnedir."
    ),
    "input_schema": PageAnalysis.model_json_schema(),
}

DESCRIPTION_TOOL_NAME = "record_type_description"

DESCRIPTION_TOOL: ToolParam = {
    "name": DESCRIPTION_TOOL_NAME,
    "description": (
        "Belge türünün örneklerinden çıkarılan yapılandırılmış açıklamayı kaydeder. Girdi, tür "
        "açıklaması şemasındaki her anahtarı taşıyan tek bir nesnedir."
    ),
    "input_schema": TypeDescription.model_json_schema(),
}

PROPOSAL_TOOL_NAME = "record_type_proposal"

PROPOSAL_TOOL: ToolParam = {
    "name": PROPOSAL_TOOL_NAME,
    "description": (
        "Katalog dışı belge türünün örneklerinden çıkarılan tam katalog kaydı taslağını kaydeder. "
        "Girdi, tür taslağı şemasındaki her anahtarı taşıyan tek bir nesnedir."
    ),
    "input_schema": TypeProposal.model_json_schema(),
}

TRAINING_TOOL_NAME = "record_training_classification"

TRAINING_TOOL: ToolParam = {
    "name": TRAINING_TOOL_NAME,
    "description": (
        "Eğitim modundaki belgenin türünü kaydeder: katalog türü, ülke, tür, önerilen ad ve yüz. "
        "Girdi, eğitim sınıflandırması şemasındaki her anahtarı taşıyan tek bir nesnedir."
    ),
    "input_schema": TrainingClassification.model_json_schema(),
}

PHOTO_CHECK_TOOL_NAME = "record_photo_check"

PHOTO_CHECK_TOOL: ToolParam = {
    "name": PHOTO_CHECK_TOOL_NAME,
    "description": (
        "Profil fotoğrafının kurallara göre değerlendirmesini kaydeder. Girdi, sorulan her kural "
        "için bir satır taşıyan tek bir nesnedir."
    ),
    "input_schema": PhotoCheck.model_json_schema(),
}

DOCUMENT_QUERY_TOOL_NAME = "record_document_query"

DOCUMENT_QUERY_TOOL: ToolParam = {
    "name": DOCUMENT_QUERY_TOOL_NAME,
    "description": (
        "İK'nın bota yazdığı mesajın okunmasını kaydeder: kimin hangi belgeleri, bilgisi "
        "ya da eksik belgeleri istendi, mesaj hangi dilde ya da mesajın istek olmadığı. "
        "Tek bir nesnedir; şemadaki her anahtarı taşır."
    ),
    "input_schema": DocumentQuery.model_json_schema(),
}

TEMPLATE_MAP_TOOL_NAME = "record_template_field_map"

TEMPLATE_MAP_TOOL: ToolParam = {
    "name": TEMPLATE_MAP_TOOL_NAME,
    "description": (
        "Hazır şablonun alan haritasını kaydeder: doldurulacak boşluklar ve doldurulmayacak imza, "
        "kaşe, logo, fotoğraf, çerçeve alanları. Girdi, alan haritası şemasındaki her anahtarı "
        "taşıyan tek bir nesnedir."
    ),
    "input_schema": TemplateFieldMap.model_json_schema(),
}


PROFILE_ANSWER_TOOL_NAME = "record_profile_answer"

PROFILE_ANSWER_TOOL: ToolParam = {
    "name": PROFILE_ANSWER_TOOL_NAME,
    "description": (
        "İK'nın çalışanlar hakkındaki sorusuna, yalnız verilen profillerden yazılmış kısa yanıtı "
        "kaydeder."
    ),
    "input_schema": ProfileAnswer.model_json_schema(),
}


class AnthropicProvider(AnalysisProvider):
    """Anthropic Messages API ile sayfa analizi, tür açıklaması, tür taslağı, eğitim
    sınıflandırması, fotoğraf kontrolü, belge isteği ve şablon incelemesi
    (`AI_PROVIDER=anthropic`)."""

    name = "anthropic"

    def __init__(
        self,
        client: anthropic.Anthropic,
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
    ) -> AnthropicProvider:
        """Ayarlardan istemci kurar; `ANTHROPIC_API_KEY` boşsa ya da efor modelde seçilemiyorsa
        `ProviderConfigError`.

        `http_client` yalnız taşıma katmanını değiştirmek içindir (test, vekil).
        """
        api_key = settings.anthropic_api_key
        if api_key is None or not api_key.get_secret_value().strip():
            raise ProviderConfigError(
                "AI_PROVIDER=anthropic için ANTHROPIC_API_KEY tanımlı olmalı. "
                "Bkz. .env.example dosyasındaki açıklama."
            )
        try:
            check_effort(cls.name, settings.anthropic_model, settings.anthropic_effort)
        except ValueError as exc:
            raise ProviderConfigError(str(exc)) from None
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
            prescreen_model=settings.anthropic_prescreen_model,
            effort=settings.anthropic_effort,
        )

    def _with_model(self, model: str) -> AnthropicProvider:
        # Ön eleme kopyası aynı istemciyi (anahtar, zaman aşımı, taşıma) paylaşır (13.2.1). Efor ana
        # modelin seçimidir; ön eleme modeli kendi varsayılan eforu ve kendi biçimiyle çalışır.
        return AnthropicProvider(
            self._client, model=model, max_output_tokens=self._max_output_tokens
        )

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        return self._tool_call(
            request.instructions,
            (request.image,),
            request.prompt,
            ANALYSIS_TOOL,
            label="analiz aracı",
            error=PageAnalysisError,
        )

    def _request_description(self, request: TypeDescriptionRequest) -> object:
        return self._tool_call(
            request.instructions,
            request.images,
            request.prompt,
            DESCRIPTION_TOOL,
            label="tür açıklaması aracı",
            error=TypeDescriptionError,
        )

    def _request_type_proposal(self, request: TypeProposalRequest) -> object:
        return self._tool_call(
            request.instructions,
            request.images,
            request.prompt,
            PROPOSAL_TOOL,
            label="tür taslağı aracı",
            error=TypeProposalError,
        )

    def _request_template_map(self, request: TemplateMapRequest) -> object:
        return self._tool_call(
            request.instructions,
            request.images,
            request.prompt,
            TEMPLATE_MAP_TOOL,
            label="alan haritası aracı",
            error=TemplateFieldMapError,
        )

    def _request_training_classification(self, request: TrainingClassificationRequest) -> object:
        return self._tool_call(
            request.instructions,
            request.images,
            request.prompt,
            TRAINING_TOOL,
            label="eğitim sınıflandırması aracı",
            error=TrainingClassificationError,
        )

    def _request_photo_check(self, request: PhotoCheckRequest) -> object:
        return self._tool_call(
            request.instructions,
            (request.image,),
            request.prompt,
            PHOTO_CHECK_TOOL,
            label="fotoğraf kontrolü aracı",
            error=PhotoCheckError,
        )

    def _request_document_query(self, request: DocumentQueryRequest) -> object:
        return self._tool_call(
            request.instructions,
            (),
            request.prompt,
            DOCUMENT_QUERY_TOOL,
            label="belge isteği aracı",
            error=DocumentQueryError,
        )

    def _request_profile_answer(self, request: ProfileAnswerRequest) -> object:
        return self._tool_call(
            request.instructions,
            (),
            request.prompt,
            PROFILE_ANSWER_TOOL,
            label="profil yanıtı aracı",
            error=ProfileAnswerError,
        )

    def _tool_call(
        self,
        instructions: str,
        images: Sequence[PageImage],
        prompt: str,
        tool: ToolParam,
        *,
        label: str,
        error: Callable[[list[str]], Exception],
    ) -> object:
        """Görüntüler (sırayla; olmayabilir) ve metinle tek istek; `tool`'un girdisi doğrulanmadan
        döner. İstek biçimi modele ve efora göredir (modül açıklaması). Yanıtta tek ve tamamlanmış
        `tool` çağrısı yoksa `error` (`label` mesajdaki araç adıdır)."""
        message: MessageParam = {
            "role": "user",
            "content": [
                *(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image.media_type,
                            "data": base64.b64encode(image.data).decode("ascii"),
                        },
                    }
                    for image in images
                ),
                {"type": "text", "text": prompt},
            ],
        }
        try:
            response = self._client.messages.create(
                messages=[message], **self._request_options(instructions, tool)
            )
        except anthropic.APIStatusError as exc:
            raise _status_error(exc) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderConnectionError(f"Anthropic'e ulaşılamadı: {type(exc).__name__}") from exc
        except anthropic.AnthropicError as exc:
            raise ProviderError(f"Anthropic isteği başarısız: {type(exc).__name__}") from exc
        usage = getattr(response, "usage", None)
        self.usage.add(getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None))
        return _tool_input(response, tool["name"], label, error)

    def _request_options(self, instructions: str, tool: ToolParam) -> dict[str, Any]:
        """İsteğin mesaj dışı alanları; biçim modele ve efora göredir (modül açıklaması)."""
        options: dict[str, Any] = {"model": self.model}
        if self.effort is not None:
            options["output_config"] = {"effort": self.effort}
        if anthropic_request_format(self.model, self.effort) is RequestFormat.FORCED_TOOL:
            return options | {
                "max_tokens": self._max_output_tokens,
                "system": instructions,
                "tools": [tool],
                "tool_choice": {
                    "type": "tool",
                    "name": tool["name"],
                    "disable_parallel_tool_use": True,
                },
                "thinking": {"type": "disabled"},
            }
        return options | {
            "max_tokens": max(self._max_output_tokens, THINKING_MIN_OUTPUT_TOKENS),
            "system": instructions + tool_instruction(tool["name"]),
            "tools": [_strict_tool(tool["name"])],
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
        }


def tool_instruction(name: str) -> str:
    """`AUTO_TOOL` biçiminde sistem talimatının sonuna eklenen cümle: yanıt aracın tek
    çağrısıdır."""
    return (
        f"\n\nYanıtını yalnız `{name}` aracını tam bir kez çağırarak ver; araç dışında metin yazma."
    )


_TOOLS: dict[str, ToolParam] = {
    tool["name"]: tool
    for tool in (
        ANALYSIS_TOOL,
        DESCRIPTION_TOOL,
        PROPOSAL_TOOL,
        TRAINING_TOOL,
        PHOTO_CHECK_TOOL,
        DOCUMENT_QUERY_TOOL,
        TEMPLATE_MAP_TOOL,
        PROFILE_ANSWER_TOOL,
    )
}


@cache
def _strict_tool(name: str) -> ToolParam:
    """`AUTO_TOOL` biçimindeki araç: şeması katı biçime uyabiliyorsa `strict: true` ile SDK'nın
    dönüştürdüğü şema; açık sözlük (`patternProperties`) taşıyorsa olduğu gibi (modül
    açıklaması)."""
    tool = _TOOLS[name]
    if "patternProperties" in json.dumps(tool["input_schema"]):
        return tool
    return {
        **tool,
        "input_schema": anthropic.transform_schema(dict(tool["input_schema"])),
        "strict": True,
    }


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


def _tool_input(
    response: Message, name: str, label: str, error: Callable[[list[str]], Exception]
) -> object:
    """Yanıttaki tek `name` aracı çağrısının girdisi; çağrı tamamlanmadıysa yanıt `error` ile
    reddedilir."""
    if response.stop_reason != "tool_use":
        # `max_tokens` kesik, `refusal` boş, `end_turn` araçsız yanıttır — hiçbiri kabul edilmez.
        raise error([f"yanıt: {label} çağrısı tamamlanmadı (stop_reason={response.stop_reason})"])
    calls = [block for block in response.content if block.type == "tool_use"]
    if len(calls) != 1 or calls[0].name != name:
        raise error([f"yanıt: yalnız bir '{name}' çağrısı olmalı ({len(calls)} araç çağrısı)"])
    return calls[0].input
