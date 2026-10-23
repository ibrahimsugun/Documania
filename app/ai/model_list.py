"""Yapay zekâ model listesi — PRD 03.8.2; PLAN.md §D124 (c, d).

Panelde seçilebilen modeller, her modelin efor kümesi ve istek biçimi bilgisi depoda durur (elle
`.env` doldurma yok). Kaynaklar (okunma tarihi `SOURCE_DATE`):

- Anthropic: Anthropic API dokümanı (claude-api başvurusu, model tablosu önbelleği 2026-10-06;
  "Thinking & Effort" tablosu ve "Forced tool use removed" notu). Efor bütün listelenen modellerde
  `output_config.effort` ile `low`–`max`; varsayılan Opus 5.5 ve Haiku 5.5'te `medium`, ötekilerde
  `high`. Zorlanmış araç seçimini (`tool_choice: tool`) Opus 5.5, Sonnet 5.5 ve Fable 5.1 400 ile
  reddeder; `thinking: disabled` Opus 5 ve Haiku 5.5'te yalnız `high` ve altında geçerlidir, öteki
  üç modelde hiç geçerli değildir.
- OpenAI: OpenAI model dokümanı (developers.openai.com/api/docs/models, …/models/gpt-6-luna,
  …/guides/reasoning). GPT-6 Luna `reasoning_effort` olarak `none`–`max` alır (varsayılan
  `medium`), fakat "Chat Completions supports function calling only with `reasoning_effort` set to
  `none`": işlev çağrısıyla uyumlu tek değer `none`'dır ve "varsayılan" seçiminde de o gönderilir.
  GPT-6 Astra ve GPT-6.1 Sol Chat Completions'ta işlev çağrısını hiç desteklemez; Responses API'ye
  geçiş ayrı insan kararıdır (§D124 c), bu yüzden listede değiller.

Listede olmayan bir model (`.env`'den gelen) geçerli kalır: efor sağlayıcının bütün kümesinden
seçilebilir, istek biçimi bugünkü (zorlanmış araç; OpenAI'de `none`) biçimdir.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

SOURCE_DATE = "2026-10-23"

ANTHROPIC_EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")
"""Anthropic `output_config.effort` değerleri (düşükten yükseğe)."""

OPENAI_EFFORTS: tuple[str, ...] = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
"""OpenAI `reasoning_effort` değerleri; desteklenen alt küme modele göredir."""

PROVIDER_EFFORTS: dict[str, tuple[str, ...]] = {
    "anthropic": ANTHROPIC_EFFORTS,
    "openai": OPENAI_EFFORTS,
}


class RequestFormat(StrEnum):
    """Anthropic yapılandırılmış çıktı isteğinin biçimi (§D124 c)."""

    FORCED_TOOL = "forced_tool"
    """`tool_choice: tool` + `thinking: disabled` (bugünkü biçim)."""
    AUTO_TOOL = "auto_tool"
    """`tool_choice: auto` + katı araç (şema izin veriyorsa) + talimatta aracın adı; `thinking`
    gönderilmez (model uyarlanabilir düşünür)."""


@dataclass(frozen=True, slots=True)
class AiModel:
    """Listedeki bir model.

    `efforts` panelde seçilebilen değerlerdir ("varsayılan" ayrıca her zaman seçilebilir).
    `default_effort` sağlayıcının parametre gönderilmediğindeki varsayılanıdır.
    `forced_tool_efforts` (Anthropic) zorlanmış araç + kapalı düşünmenin kabul edildiği efor
    değerleridir; boşsa model bu biçimi hiç kabul etmez. `request_effort_default` (OpenAI) efor
    seçilmemişken gönderilen değerdir (`None` ise parametre gönderilmez).
    """

    provider: str
    model_id: str
    label: str
    efforts: tuple[str, ...]
    default_effort: str
    forced_tool_efforts: frozenset[str] = frozenset()
    request_effort_default: str | None = None


_UP_TO_HIGH = frozenset({"low", "medium", "high"})

MODELS: tuple[AiModel, ...] = (
    AiModel("anthropic", "claude-opus-5-5", "Claude Opus 5.5", ANTHROPIC_EFFORTS, "medium"),
    AiModel("anthropic", "claude-opus-5", "Claude Opus 5", ANTHROPIC_EFFORTS, "high", _UP_TO_HIGH),
    AiModel("anthropic", "claude-sonnet-5-5", "Claude Sonnet 5.5", ANTHROPIC_EFFORTS, "high"),
    AiModel(
        "anthropic",
        "claude-haiku-5-5",
        "Claude Haiku 5.5",
        ANTHROPIC_EFFORTS,
        "medium",
        _UP_TO_HIGH,
    ),
    AiModel("anthropic", "claude-fable-5-1", "Claude Fable 5.1", ANTHROPIC_EFFORTS, "high"),
    AiModel(
        "openai", "gpt-6-luna", "GPT-6 Luna", ("none",), "medium", request_effort_default="none"
    ),
)

_UNLISTED_OPENAI_EFFORT = "none"
"""Listede olmayan OpenAI modelinde efor seçilmemişken gönderilen değer (bugünkü davranış)."""


def models_for(provider: str) -> tuple[AiModel, ...]:
    """Sağlayıcının listedeki modelleri (sırasıyla)."""
    return tuple(model for model in MODELS if model.provider == provider)


def find_model(provider: str, model_id: str) -> AiModel | None:
    """Listedeki model; listede yoksa `None`."""
    for model in MODELS:
        if model.provider == provider and model.model_id == model_id:
            return model
    return None


def allowed_efforts(provider: str, model_id: str) -> tuple[str, ...]:
    """Modelde seçilebilen efor değerleri: listedeyse modelinki, değilse sağlayıcının bütün
    kümesi."""
    model = find_model(provider, model_id)
    if model is not None:
        return model.efforts
    return PROVIDER_EFFORTS.get(provider, ())


def check_effort(provider: str, model_id: str, effort: str | None) -> None:
    """Efor modelde seçilebilir değilse `ValueError`; `None` ("varsayılan") her zaman geçerlidir."""
    if effort is None:
        return
    allowed = allowed_efforts(provider, model_id)
    if effort not in allowed:
        raise ValueError(
            f"'{effort}' eforu {provider} '{model_id}' modelinde seçilemez; geçerli değerler: "
            f"{', '.join(allowed) or '-'}"
        )


def anthropic_request_format(model_id: str, effort: str | None) -> RequestFormat:
    """Anthropic isteğinin biçimi: model zorlanmış araç + kapalı düşünmeyi bu eforla (seçilmemişse
    varsayılan eforuyla) kabul ediyorsa `FORCED_TOOL`, etmiyorsa `AUTO_TOOL`. Listede olmayan model
    bugünkü biçimde (`FORCED_TOOL`) kalır."""
    model = find_model("anthropic", model_id)
    if model is None:
        return RequestFormat.FORCED_TOOL
    effective = effort if effort is not None else model.default_effort
    if effective in model.forced_tool_efforts:
        return RequestFormat.FORCED_TOOL
    return RequestFormat.AUTO_TOOL


def openai_request_effort(model_id: str, effort: str | None) -> str | None:
    """OpenAI isteğinde gönderilecek `reasoning_effort`: seçilmişse o; seçilmemişse modelin işlev
    çağrısıyla uyumlu varsayılanı (listede olmayan modelde bugünkü `none`); `None` gönderilmez."""
    if effort is not None:
        return effort
    model = find_model("openai", model_id)
    if model is None:
        return _UNLISTED_OPENAI_EFFORT
    return model.request_effort_default
