"""Desteklenen arayüz dilleri ve isteğin dilini seçme kuralı (PRD 10.10.1; PLAN.md §D92 a, b).

Diller ve hangisinin seçileceği yalnız burada tanımlıdır; başka modül dil kodu karşılaştırmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class Language:
    """Arayüz dili: `code` hesapta, çerezde ve katalog dizininde geçer; `html_lang` sayfanın
    `<html lang>` özniteliği; `name` dilin kendi dilindeki adı (dil seçici)."""

    code: str
    html_lang: str
    name: str


# Sıra dil seçicideki sıradır: English · Türkçe · Srpski. Sırpça Latin alfabesiyledir (§D92 a).
SUPPORTED_LANGUAGES = MappingProxyType(
    {
        "en": Language("en", "en", "English"),
        "tr": Language("tr", "tr", "Türkçe"),
        "sr": Language("sr", "sr-Latn", "Srpski"),
    }
)
# Açılış dili: girişsiz sayfa (çerezde geçerli dil yoksa) ve tercihi olmayan hesap. Panelde
# `Settings.panel_default_language` değiştirir; istek dışı kod (işçi, bot) bunu görür.
DEFAULT_LANGUAGE = "en"
# Kaynak dil: msgid'ler Türkçe metnin kendisidir, bu dilin kataloğu yoktur.
SOURCE_LANGUAGE = "tr"
# Çeviri kataloğu olan diller (`app/i18n/locales/<kod>/LC_MESSAGES/messages.po`).
CATALOG_LANGUAGES = tuple(code for code in SUPPORTED_LANGUAGES if code != SOURCE_LANGUAGE)
# Girişsiz istekte dilin taşındığı çerez (yazan: 10.10.2 dil seçici).
LANGUAGE_COOKIE = "documania_lang"


def is_supported(value: object) -> bool:
    """`value` desteklenen bir dil kodu mu (tam yazımıyla: `en`, `tr`, `sr`)."""
    return isinstance(value, str) and value in SUPPORTED_LANGUAGES


def resolve_language(
    *, signed_in: bool, user_language: str | None, cookie: str | None, default: str
) -> str:
    """İsteğin dili (§D92 b): girişli istekte hesabın tercihi, girişsizde geçerli çerez; ikisi de
    yoksa ya da geçersizse `default`. Tarayıcının `Accept-Language`'ı kullanılmaz."""
    if not is_supported(default):
        raise ValueError(f"desteklenmeyen varsayılan dil: {default!r}")
    chosen = user_language if signed_in else cookie
    return chosen if is_supported(chosen) else default
