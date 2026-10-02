"""10.10.1 arayüz dili — desteklenen diller, dilin çözümü, istek dışı varsayılan, katalog yükleme ve
açılış ayarı (PLAN.md §D92 a, b, e)."""

from __future__ import annotations

import contextvars
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.i18n as i18n
from app.config import Settings, get_settings
from app.i18n import (
    CATALOG_LANGUAGES,
    DEFAULT_LANGUAGE,
    LANGUAGE_COOKIE,
    N_,
    SOURCE_LANGUAGE,
    SUPPORTED_LANGUAGES,
    activate_language,
    current_html_lang,
    current_language,
    gettext,
    is_supported,
    ngettext,
    resolve_language,
    use_language,
)
from app.i18n.catalog import load_translations
from app.main import create_app

APP_DIR = Path(i18n.__file__).resolve().parents[1]


def _fresh(function, *args):
    """İstek dışı bağlam: hiçbir dilin yazılmadığı boş bir bağlamda çalıştırır."""
    return contextvars.Context().run(function, *args)


# --- diller -----------------------------------------------------------------------------------


def test_three_languages_in_selector_order_with_native_names_and_html_lang() -> None:
    assert [
        (language.code, language.html_lang, language.name)
        for language in SUPPORTED_LANGUAGES.values()
    ] == [("en", "en", "English"), ("tr", "tr", "Türkçe"), ("sr", "sr-Latn", "Srpski")]
    assert DEFAULT_LANGUAGE == "en"
    assert SOURCE_LANGUAGE == "tr"
    assert CATALOG_LANGUAGES == ("en", "sr")
    assert LANGUAGE_COOKIE == "documania_lang"


@pytest.mark.parametrize("value", ["en", "tr", "sr"])
def test_supported_codes(value: str) -> None:
    assert is_supported(value)


@pytest.mark.parametrize("value", ["", "EN", "de", "sr-Latn", "sr_Latn", "tr ", None, 1, ["en"]])
def test_unsupported_codes(value: object) -> None:
    assert not is_supported(value)


# --- dilin çözümü (§D92 b) --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("signed_in", "user_language", "cookie", "default", "expected"),
    [
        # Girişsiz: geçerli çerez, yoksa varsayılan.
        (False, None, None, "en", "en"),
        (False, None, "sr", "en", "sr"),
        (False, None, "tr", "en", "tr"),
        (False, None, "de", "en", "en"),
        (False, None, "", "tr", "tr"),
        (False, "sr", None, "en", "en"),
        # Girişli: hesabın tercihi, yoksa varsayılan; çerez okunmaz.
        (True, None, "sr", "en", "en"),
        (True, None, None, "tr", "tr"),
        (True, "sr", "tr", "en", "sr"),
        (True, "xx", "sr", "en", "en"),
    ],
)
def test_resolve_language(
    signed_in: bool, user_language: str | None, cookie: str | None, default: str, expected: str
) -> None:
    assert (
        resolve_language(
            signed_in=signed_in, user_language=user_language, cookie=cookie, default=default
        )
        == expected
    )


def test_resolve_language_rejects_an_unsupported_default() -> None:
    with pytest.raises(ValueError, match="varsayılan"):
        resolve_language(signed_in=False, user_language=None, cookie="en", default="de")


# --- bağlamın dili ----------------------------------------------------------------------------


def test_outside_a_request_the_default_language_is_used() -> None:
    # 7) İşçi ve bot isteğe bağlı değildir: dil yazılmamış bağlam varsayılanı (İngilizce) görür.
    assert _fresh(current_language) == "en"
    assert _fresh(current_html_lang) == "en"
    assert _fresh(gettext, "Çalışanlar") == "Employees"
    assert _fresh(gettext, "Çıkış") == "Sign out"


def test_use_language_switches_and_restores() -> None:
    def scenario() -> list[str]:
        seen = [gettext("Çıkış")]
        with use_language("sr"):
            seen += [gettext("Çıkış"), current_html_lang()]
            with use_language("tr"):
                seen += [gettext("Çıkış"), current_html_lang()]
            seen.append(gettext("Çıkış"))
        seen.append(gettext("Çıkış"))
        return seen

    assert _fresh(scenario) == [
        "Sign out",
        "Odjava",
        "sr-Latn",
        "Çıkış",
        "tr",
        "Odjava",
        "Sign out",
    ]


def test_activate_language_sets_the_context_language() -> None:
    def scenario() -> tuple[str, str]:
        activate_language("sr")
        return current_language(), gettext("Kullanıcılar")

    assert _fresh(scenario) == ("sr", "Korisnici")
    # Başka bağlama sızmaz.
    assert _fresh(current_language) == "en"


@pytest.mark.parametrize("value", ["de", "", "sr-Latn"])
def test_unsupported_language_cannot_be_activated(value: str) -> None:
    with pytest.raises(ValueError, match="desteklenmeyen"):
        _fresh(activate_language, value)
    with pytest.raises(ValueError, match="desteklenmeyen"), use_language(value):
        pass


def test_source_language_shows_the_msgid_itself_and_unknown_text_falls_back_to_it() -> None:
    with use_language("tr"):
        assert gettext("Belge Türleri") == "Belge Türleri"
        assert ngettext("%(n)s belge", "%(n)s belgeler", 1) == "%(n)s belge"
        assert ngettext("%(n)s belge", "%(n)s belgeler", 3) == "%(n)s belgeler"
    with use_language("en"):
        assert gettext("Kataloğa henüz girmemiş metin") == "Kataloğa henüz girmemiş metin"
        assert ngettext("bir", "çok", 2) == "çok"


def test_n_marks_without_translating() -> None:
    with use_language("en"):
        assert N_("Çalışanlar") == "Çalışanlar"
        assert gettext(N_("Çalışanlar")) == "Employees"


# --- katalog yükleme --------------------------------------------------------------------------


def test_catalogs_are_loaded_once_per_process() -> None:
    assert load_translations("en") is load_translations("en")
    assert load_translations("sr") is load_translations("sr")
    assert load_translations("en") is not load_translations("sr")


def test_catalog_of_an_unsupported_language_is_an_error() -> None:
    with pytest.raises(ValueError, match="desteklenmeyen"):
        load_translations("de")


def test_serbian_catalog_uses_the_cldr_plural_rule() -> None:
    plural = load_translations("sr").plural
    # one: 1, 21, 101 · few: 2–4, 22–24 · other: 0, 5–20, 25, 111–114
    assert [plural(n) for n in (1, 21, 101, 2, 4, 22, 0, 5, 11, 12, 14, 25, 111, 112)] == [
        0,
        0,
        0,
        1,
        1,
        1,
        2,
        2,
        2,
        2,
        2,
        2,
        2,
        2,
    ]
    assert load_translations("en").plural(1) == 0
    assert load_translations("en").plural(2) == 1


# --- açılış ayarı (§D92 b) --------------------------------------------------------------------


def test_default_language_setting_is_english_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PANEL_DEFAULT_LANGUAGE", raising=False)

    assert Settings(_env_file=None, database_url="sqlite://").panel_default_language == "en"


@pytest.mark.parametrize(
    ("value", "expected"), [("en", "en"), ("tr", "tr"), ("sr", "sr"), (" ", "en")]
)
def test_default_language_setting_accepts_supported_codes(value: str, expected: str) -> None:
    settings = Settings(_env_file=None, database_url="sqlite://", panel_default_language=value)

    assert settings.panel_default_language == expected


@pytest.mark.parametrize("value", ["de", "EN", "sr-Latn", "turkce"])
def test_default_language_setting_rejects_unsupported_values(value: str) -> None:
    with pytest.raises(ValidationError, match="desteklenmeyen arayüz dili"):
        Settings(_env_file=None, database_url="sqlite://", panel_default_language=value)


def test_panel_does_not_start_with_an_unsupported_default_language(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'dil.db').as_posix()}")
    monkeypatch.setenv("PANEL_DEFAULT_LANGUAGE", "de")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValidationError, match="PANEL_DEFAULT_LANGUAGE|panel_default_language"):
            with TestClient(create_app()):
                pass
    finally:
        get_settings.cache_clear()


def test_env_example_documents_the_default_language() -> None:
    example = (APP_DIR.parent / ".env.example").read_text(encoding="utf-8")

    assert re.search(r"^# PANEL_DEFAULT_LANGUAGE=en$", example, re.MULTILINE)


# --- kod düzeni -------------------------------------------------------------------------------


def test_language_choice_lives_only_in_app_i18n() -> None:
    # Başka modül dil kodunu karşılaştırmaz, dil çerezini kendisi okumaz (§D92 a).
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if path.parent.name == "i18n" and path.parent.parent == APP_DIR:
            continue
        text = path.read_text(encoding="utf-8")
        if "documania_lang" in text or re.search(r"current_language\(\)\s*(==|!=|\bin\b)", text):
            offenders.append(path.relative_to(APP_DIR).as_posix())
    assert offenders == []
