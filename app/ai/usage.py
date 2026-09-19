"""Token kullanımı ölçümü ve maliyet hesabı — PRD 13.1.1.

Somut sağlayıcı her başarıyla dönen yanıtın token sayılarını `report_usage` ile bildirir; bildirim
etkin ölçüm bağlamlarına (`measure_usage`) eklenir, bağlam yoksa yok sayılır. Böylece sağlayıcı
arayüzü (`analyze_page` → `PageAnalysis`) değişmez ve tek sayfa için yapılan çağrılar — analiz ve
varsa fotoğraf kontrolü — bir bağlamda toplanır. Bağlam `ContextVar`'dadır: eşzamanlı iş
parçacıkları birbirinin sayısını görmez.

Yanıt gelmeden biten çağrı (hız sınırı, 5xx, bağlantı) token harcamaz ve bildirilmez. Yanıt geldi
ama şemaya uymadıysa token harcanmıştır: sağlayıcı yanıtı reddetmeden önce bildirir.

Maliyet, sayıların fiyat tablosuyla (`Settings.ai_model_prices`) çarpımıdır ve gösterim anında
hesaplanır (`token_cost`); olaylar yalnız ölçümü taşır. Önbellek okuma/yazma tokenları ayrı
fiyatlanır ama bu yapı önbellek kullanmaz, sayılmaz.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal

from app.config import ModelPrice

_TOKENS_PER_PRICE_UNIT = Decimal(1_000_000)


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Bir ya da birkaç sağlayıcı çağrısının girdi ve çıktı token toplamı."""

    input_tokens: int = 0
    output_tokens: int = 0

    def __post_init__(self) -> None:
        for name in ("input_tokens", "output_tokens"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} 0 veya pozitif tamsayı olmalı")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens
        )

    def to_event_data(self) -> dict[str, int]:
        """Olay verisinde `usage` anahtarının değeri (`app.events.USAGE_DATA_KEY`)."""
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens}

    @classmethod
    def from_event_data(cls, data: object) -> TokenUsage | None:
        """`to_event_data`'nın tersi; yok, bozuk ya da eksik veri `None` (ölçülmemiş)."""
        if not isinstance(data, Mapping):
            return None
        try:
            return cls(data["input_tokens"], data["output_tokens"])
        except (KeyError, ValueError):
            return None


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


def report_usage(input_tokens: object, output_tokens: object) -> None:
    """Bir sağlayıcı yanıtının token sayılarını etkin ölçümlere ekler.

    Sayılar sağlayıcı SDK'sından gelir; eksik ya da geçersizse (`None`, negatif, sayı olmayan)
    kullanım bildirilmez — uydurulan sıfır, ölçülmemiş çağrıyı ölçülmüş gösterirdi.
    """
    meters = _active_meters.get()
    if not meters:
        return
    try:
        usage = TokenUsage(input_tokens, output_tokens)
    except ValueError:
        return
    for meter in meters:
        meter.add(usage)


def token_cost(usage: TokenUsage, price: ModelPrice) -> Decimal:
    """`usage`'ın `price` fiyatıyla maliyeti (USD)."""
    return (
        Decimal(usage.input_tokens) * price.input_per_mtok
        + Decimal(usage.output_tokens) * price.output_per_mtok
    ) / _TOKENS_PER_PRICE_UNIT
