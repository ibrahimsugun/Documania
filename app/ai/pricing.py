"""Model fiyatları — yerleşik tablo ve fiyat çözümleme (PRD 13.1.1; PLAN.md §C77).

Maliyet paneli (`app.web.routers.metrics`) olaydaki model adının fiyatını buradan alır. İki kaynak
vardır, sıra şöyledir:

1. `.env`'deki `AI_MODEL_PRICES` (`Settings.ai_model_prices`) — insanın elle girdiği fiyat;
   aynı model için yerleşik tablonun önüne geçer.
2. Yerleşik tablo `app/ai/model_prices.yaml` — sağlayıcı fiyat sayfalarından aktarılmış, kaynağı
   ve tarihi dosyada yazılı; paketle birlikte gelir, ayar gerektirmez.

Eşleşme önce birebir (büyük/küçük harf ve baştaki/sondaki boşluk gözetilmez), sonra sondaki tarih
eki atılarak yapılır (`claude-haiku-4-5-20251001` → `claude-haiku-4-5`, `gpt-4o-2024-08-06` →
`gpt-4o`). Her adımda önce `.env`, sonra yerleşik tabloya bakılır. Başka bir ek atılmaz: `-pro`,
`-mini` ya da `-preview` farklı fiyatlı ayrı modeldir. İki kaynakta da olmayan modelin fiyatı
yoktur (`None`); panel tokenlarını sayar, maliyetini hesaplamaz — fiyat uydurulmaz.

Fiyat olaya dondurulmaz (C70): tablo güncellenince geçmiş aylar da yeni fiyatla hesaplanır.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from functools import lru_cache
from importlib import resources
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import ModelPrice, Settings

PRICE_RESOURCE = "model_prices.yaml"

_MODEL_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_DATE_SUFFIX = re.compile(r"-(?:\d{8}|\d{4}-\d{2}-\d{2})$")


class PriceEntry(ModelPrice):
    """Yerleşik tablodaki bir modelin fiyatı ve kaydı."""

    provider: str = Field(min_length=1)
    name: str = Field(min_length=1)
    id_source: Literal["page", "derived"]
    note: str | None = None


class PriceList(BaseModel):
    """Yerleşik fiyat tablosu: kaynak sayfalar, eşitleme tarihi ve model → fiyat."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    synced: date
    sources: dict[str, str] = Field(min_length=1)
    models: dict[str, PriceEntry] = Field(min_length=1)

    @field_validator("models")
    @classmethod
    def _keys_are_model_names(cls, models: dict[str, PriceEntry]) -> dict[str, PriceEntry]:
        for key in models:
            if not _MODEL_KEY.fullmatch(key):
                raise ValueError(f"geçersiz model adı: {key!r} (küçük harf, rakam, . _ -)")
            if _DATE_SUFFIX.search(key):
                raise ValueError(f"model adı tarih ekiyle yazılmaz: {key!r}")
        return models


class PriceSource(StrEnum):
    SETTINGS = "settings"
    BUILTIN = "builtin"


@dataclass(frozen=True, slots=True)
class ResolvedPrice:
    """Bir model adının çözülen fiyatı: eşleşen anahtar ve kaynağı ile."""

    model: str
    key: str
    price: ModelPrice
    source: PriceSource


def parse_price_list(content: str | bytes) -> PriceList:
    """YAML metnini doğrulanmış fiyat tablosuna çevirir; hata `ValueError`'dır."""
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ValueError(f"fiyat tablosu YAML olarak okunamadı: {exc}") from exc
    return PriceList.model_validate(data)


@lru_cache
def builtin_price_list() -> PriceList:
    """Paketle gelen fiyat tablosu (süreç boyunca bir kez okunur)."""
    content = resources.files("app.ai").joinpath(PRICE_RESOURCE).read_bytes()
    return parse_price_list(content)


def _candidates(model: str) -> tuple[str, ...]:
    exact = model.strip().lower()
    undated = _DATE_SUFFIX.sub("", exact)
    return (exact,) if undated == exact else (exact, undated)


class PriceBook:
    """Model adına fiyat veren okuyucu: önce `.env` fiyatları, sonra yerleşik tablo."""

    def __init__(
        self, overrides: Mapping[str, ModelPrice], builtin: PriceList | None = None
    ) -> None:
        self._overrides = {key.strip().lower(): price for key, price in overrides.items()}
        self._builtin: Mapping[str, PriceEntry] = {} if builtin is None else builtin.models
        self.price_list = builtin

    def __bool__(self) -> bool:
        return bool(self._overrides or self._builtin)

    def resolve(self, model: str) -> ResolvedPrice | None:
        for key in _candidates(model):
            if key in self._overrides:
                return ResolvedPrice(model, key, self._overrides[key], PriceSource.SETTINGS)
            if key in self._builtin:
                return ResolvedPrice(model, key, self._builtin[key], PriceSource.BUILTIN)
        return None

    def get(self, model: str) -> ModelPrice | None:
        resolved = self.resolve(model)
        return None if resolved is None else resolved.price


def price_book(settings: Settings) -> PriceBook:
    """Uygulamanın fiyat okuyucusu: `.env`'deki `AI_MODEL_PRICES` + yerleşik tablo."""
    return PriceBook(settings.ai_model_prices, builtin_price_list())
