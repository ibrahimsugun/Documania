"""Arayüz dili: English, Türkçe, Srpski (PRD 10.10.1, 10.10.3; PLAN.md §D92).

Kaynak dil Türkçedir: işaretlenen metnin kendisi msgid'dir, `tr` onu olduğu gibi gösterir; `en` ve
`sr` GNU gettext kataloglarından okunur (`app.i18n.catalog`). Katalog araçları
`python -m app.i18n extract|update|compile|check` (`app.i18n.tools`).

Dil istek başında bir context değişkenine yazılır (`app.i18n.request`); `gettext` ve `ngettext`
her çağrıda oradan okur. İstek dışı kod (işçi, bot) değişkeni yazılmamış görür ve
`DEFAULT_LANGUAGE`'ı alır. Modül düzeyindeki sabit etiketler (`PANEL_MENU` gibi) tanım anında
çevrilmez: `N_()` ile işaretlenir (çıkarıcı bulsun diye), gösterim anında `gettext` ile çevrilir.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from app.i18n.catalog import load_translations
from app.i18n.languages import (
    CATALOG_LANGUAGES,
    DEFAULT_LANGUAGE,
    LANGUAGE_COOKIE,
    SOURCE_LANGUAGE,
    SUPPORTED_LANGUAGES,
    Language,
    is_supported,
    resolve_language,
)

__all__ = [
    "CATALOG_LANGUAGES",
    "DEFAULT_LANGUAGE",
    "LANGUAGE_COOKIE",
    "SOURCE_LANGUAGE",
    "SUPPORTED_LANGUAGES",
    "Language",
    "N_",
    "activate_language",
    "current_html_lang",
    "current_language",
    "gettext",
    "is_supported",
    "ngettext",
    "resolve_language",
    "use_language",
]

_current: ContextVar[str | None] = ContextVar("documania_language", default=None)


def current_language() -> str:
    """Bu bağlamın dili: istekte çözülen dil, istek dışında `DEFAULT_LANGUAGE`."""
    return _current.get() or DEFAULT_LANGUAGE


def current_html_lang() -> str:
    """Sayfanın `<html lang>` değeri (`en`, `tr`, `sr-Latn`)."""
    return SUPPORTED_LANGUAGES[current_language()].html_lang


def activate_language(code: str) -> None:
    """Bu bağlamın (isteğin) dilini yazar; geçersiz kod hatadır."""
    if not is_supported(code):
        raise ValueError(f"desteklenmeyen dil: {code!r}")
    _current.set(code)


@contextmanager
def use_language(code: str) -> Iterator[None]:
    """Blok boyunca dili `code` yapar, çıkışta önceki dile döner (istek dışı kod ve testler)."""
    if not is_supported(code):
        raise ValueError(f"desteklenmeyen dil: {code!r}")
    token = _current.set(code)
    try:
        yield
    finally:
        _current.reset(token)


def gettext(message: str) -> str:
    """`message`'ın (Türkçe msgid) bu bağlamın dilindeki karşılığı."""
    return load_translations(current_language()).gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    """Sayıya göre çoğul biçim; Sırpçada üç biçim vardır (katalog başlığındaki `Plural-Forms`)."""
    return load_translations(current_language()).ngettext(singular, plural, n)


def N_(message: str) -> str:
    """Metni çeviri için işaretler, çevirmez: gösterim anında `gettext(message)` çağrılır."""
    return message
