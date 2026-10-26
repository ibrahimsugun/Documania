"""Çift inceleme sağlayıcıları — PRD 11.9.3, 11.9.4; PLAN.md §D128.

Eğitim sınıflandırması iki bağımsız yapay zekâyla yapılır: GPT-6.1 Sol (`low`) ve Claude Sonnet 5.5
(`low`). İkisi de aynı bilinen türü verirse sistem türden emindir ve örneği doğrudan "doğrulanmış"
kaydeder (insan onayı beklemez); farklı tür verirlerse, biri türü belirleyemezse ya da çağrılardan
biri hata verirse örnek eskisi gibi "AI kararı" olarak elle kontrol bekler. Panelin "Yapay zekâ
ayarları"ndaki etkin sağlayıcı ve model bu işi etkilemez: çift her zaman bu ikilidir.

Çift yalnız iki sağlayıcının anahtarı da `.env`'de tanımlıyken ve `TRAINING_AUTO_CONFIRM` kapalı
değilken kurulur; yoksa `None` döner ve eğitim tek sağlayıcıyla (etkin olanla) yürür.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.anthropic_provider import AnthropicProvider
from app.ai.openai_provider import OpenAIProvider
from app.ai.provider import AnalysisProvider
from app.ai.runtime import key_defined
from app.config import Settings
from app.db.models import AiProviderName
from app.i18n import N_, Translatable

PAIR_OPENAI_MODEL = "gpt-6.1-sol"
PAIR_ANTHROPIC_MODEL = "claude-sonnet-5-5"
PAIR_EFFORT = "low"

PRICES_DATE = "2026-10-27"
PRICES_USD_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    PAIR_OPENAI_MODEL: (2.0, 10.0),
    PAIR_ANTHROPIC_MODEL: (2.0, 10.0),
}
"""Model → (girdi, çıktı) USD / milyon belirteç; maliyet raporu içindir. Değerler `PRICES_DATE`
tarihinde sağlayıcıların yayımladığı liste fiyatıdır (Anthropic fiyat sayfası, OpenAI
`gpt-6.1-sol` model sayfası); belirteç sayısı kesin, tutar tahmindir."""


@dataclass(frozen=True, slots=True)
class ReviewPair:
    """İki inceleyici: `first` yerleştirmeyi yapan (Sol), `second` onaylayan (Sonnet)."""

    first: AnalysisProvider
    second: AnalysisProvider

    @property
    def providers(self) -> tuple[AnalysisProvider, AnalysisProvider]:
        return (self.first, self.second)


def build_review_pair(settings: Settings) -> ReviewPair | None:
    """Çiftin sağlayıcıları; kapalıysa ya da anahtarlardan biri yoksa `None`."""
    if not settings.training_auto_confirm:
        return None
    if not (
        key_defined(settings, AiProviderName.ANTHROPIC.value)
        and key_defined(settings, AiProviderName.OPENAI.value)
    ):
        return None
    pinned = settings.model_copy(
        update={
            "openai_model": PAIR_OPENAI_MODEL,
            "openai_effort": PAIR_EFFORT,
            "anthropic_model": PAIR_ANTHROPIC_MODEL,
            "anthropic_effort": PAIR_EFFORT,
        }
    )
    return ReviewPair(OpenAIProvider.from_settings(pinned), AnthropicProvider.from_settings(pinned))


def pair_event_data(first: AnalysisProvider, second: AnalysisProvider) -> dict[str, object]:
    """Çift incelemeyle doğrulayan olayın verisi: yöntem ve iki modelin adı."""
    return {
        "review": "pair",
        "models": [f"{first.name}:{first.model}", f"{second.name}:{second.model}"],
    }


def pair_note(first: AnalysisProvider, second: AnalysisProvider) -> str:
    """Çift incelemeyle doğrulanan örneğin notu (Türkçe, kişisel değersiz)."""
    return Translatable(
        N_("Çift inceleme: {first} ve {second} aynı türü verdi; doğrulandı."),
        first=first.model,
        second=second.model,
    )
