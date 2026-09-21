"""Token kullanımı ölçümü ve maliyet hesabı — PRD 13.1.1.

Somut sağlayıcı her başarıyla dönen yanıtın token sayılarını `report_usage` ile bildirir; bildirim
etkin ölçüm bağlamlarına (`measure_usage`) eklenir, bağlam yoksa yok sayılır. Böylece sağlayıcı
arayüzü (`analyze_page` → `PageAnalysis`) değişmez ve tek sayfa için yapılan çağrılar — analiz ve
varsa fotoğraf kontrolü — bir bağlamda toplanır. Bağlam `ContextVar`'dadır: eşzamanlı iş
parçacıkları birbirinin sayısını görmez.

Yanıt gelmeden biten çağrı (hız sınırı, 5xx, bağlantı) token harcamaz ve bildirilmez. Yanıt geldi
ama şemaya uymadıysa token harcanmıştır: sağlayıcı yanıtı reddetmeden önce bildirir.

Maliyet, sayıların fiyatla (`app.ai.pricing`: yerleşik tablo + `Settings.ai_model_prices`)
çarpımıdır ve gösterim anında hesaplanır (`token_cost`); olaylar yalnız ölçümü taşır.

Önbellekten okunan girdi (`cached_input_tokens`) girdi tokenlarının bir alt kümesidir ve fiyatın
önbellek oranıyla hesaplanır: OpenAI tekrarlanan istek önekini (sabit talimat) kendiliğinden
önbelleğe alır ve `prompt_tokens_details.cached_tokens` ile bildirir. Anthropic önbelleği yalnız
istekte işaretlenirse kullanır (bu yapı işaretlemez); yine de yanıt `cache_read_input_tokens`
taşırsa girdiye ve önbellek payına eklenir. Önbellek yazma eki (1.25x) ayrıca hesaplanmaz.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal

from app.config import ModelPrice

_TOKENS_PER_PRICE_UNIT = Decimal(1_000_000)

CACHED_INPUT_KEY = "cached_input_tokens"
"""Olay verisindeki `usage` sözlüğünde önbellekten okunan girdi tokenlarının anahtarı."""


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Bir ya da birkaç sağlayıcı çağrısının girdi ve çıktı token toplamı.

    `cached_input_tokens` girdi tokenlarının önbellekten okunan kısmıdır (`input_tokens`'a dahil).
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0

    def __post_init__(self) -> None:
        for name in ("input_tokens", "output_tokens", "cached_input_tokens"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} 0 veya pozitif tamsayı olmalı")
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached_input_tokens, input_tokens değerini aşamaz")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def uncached_input_tokens(self) -> int:
        return self.input_tokens - self.cached_input_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cached_input_tokens + other.cached_input_tokens,
        )

    def __sub__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            self.input_tokens - other.input_tokens,
            self.output_tokens - other.output_tokens,
            self.cached_input_tokens - other.cached_input_tokens,
        )

    def to_event_data(self) -> dict[str, int]:
        """Olay verisinde `usage` anahtarının değeri (`app.events.USAGE_DATA_KEY`).

        Önbellek payı yalnız sıfırdan büyükse yazılır: önbelleksiz ölçümün kaydı eskisiyle aynıdır.
        """
        data = {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens}
        if self.cached_input_tokens:
            data[CACHED_INPUT_KEY] = self.cached_input_tokens
        return data

    @classmethod
    def from_event_data(cls, data: object) -> TokenUsage | None:
        """`to_event_data`'nın tersi; yok, bozuk ya da eksik veri `None` (ölçülmemiş).

        Önbellek payı yoksa 0'dır (önceki kayıtlar); bozuksa yok sayılır — girdi ve çıktı sayısı
        geçerli olan ölçüm, önbellek payı yüzünden ölçülmemiş sayılmaz (tamamı standart fiyatla).
        """
        if not isinstance(data, Mapping):
            return None
        try:
            usage = cls(data["input_tokens"], data["output_tokens"])
        except (KeyError, ValueError):
            return None
        try:
            return cls(usage.input_tokens, usage.output_tokens, data.get(CACHED_INPUT_KEY, 0))
        except ValueError:
            return usage


class UsageMeter:
    """`measure_usage` bağlamı içinde bildirilen kullanımın toplayıcısı."""

    def __init__(self) -> None:
        self.usage = TokenUsage()
        self.calls = 0

    def add(self, usage: TokenUsage) -> None:
        self.usage += usage
        self.calls += 1


_active_meters: ContextVar[tuple[UsageMeter, ...]] = ContextVar("belgeee_usage_meters", default=())


@contextmanager
def measure_usage() -> Iterator[UsageMeter]:
    """Blok içinde bildirilen her kullanımı toplar. İç içe kullanımda dıştaki ölçüm de sayar."""
    meter = UsageMeter()
    token = _active_meters.set((*_active_meters.get(), meter))
    try:
        yield meter
    finally:
        _active_meters.reset(token)


def report_usage(
    input_tokens: object, output_tokens: object, cached_input_tokens: object = None
) -> None:
    """Bir sağlayıcı yanıtının token sayılarını etkin ölçümlere ekler.

    Sayılar sağlayıcı SDK'sından gelir; girdi ya da çıktı sayısı eksik veya geçersizse (`None`,
    negatif, sayı olmayan) kullanım bildirilmez — uydurulan sıfır, ölçülmemiş çağrıyı ölçülmüş
    gösterirdi. Önbellek payı (`input_tokens`'a dahil) eksik ya da geçersizse 0 sayılır: o
    tokenlar standart girdi fiyatıyla hesaplanır, maliyet eksik gösterilmez.
    """
    meters = _active_meters.get()
    if not meters:
        return
    try:
        usage = TokenUsage(input_tokens, output_tokens)
    except ValueError:
        return
    try:
        usage = TokenUsage(usage.input_tokens, usage.output_tokens, cached_input_tokens)
    except ValueError:
        pass
    for meter in meters:
        meter.add(usage)


def token_cost(usage: TokenUsage, price: ModelPrice) -> Decimal:
    """`usage`'ın `price` fiyatıyla maliyeti (USD). Önbellekten okunan girdi, fiyatın önbellek
    oranı varsa onunla, yoksa standart girdi fiyatıyla hesaplanır."""
    cached_rate = (
        price.input_per_mtok if price.cached_input_per_mtok is None else price.cached_input_per_mtok
    )
    return (
        Decimal(usage.uncached_input_tokens) * price.input_per_mtok
        + Decimal(usage.cached_input_tokens) * cached_rate
        + Decimal(usage.output_tokens) * price.output_per_mtok
    ) / _TOKENS_PER_PRICE_UNIT
