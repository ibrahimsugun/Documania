"""Arayüz standardı denetimi (docs/ARAYUZ-STANDARDI.md; PLAN.md §D122).

Panelin şablon ve stil sözleşmesinin ölçülebilir maddeleri burada kırmızıya döner: şablonda
tanımsız sınıf, satır içi stil ya da betik, çift `h1`, parçada `h1`, değişken dışı renk, simgesiz
menü girdisi, kabuğun test işaretleri. Standart belgesi §4'teki "anlam sınıfları" listesi bu
testin izin listesidir — belge ile kod birbirini tutar.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.web.templating import PANEL_MENU

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "app" / "web" / "templates"
STATIC = ROOT / "app" / "web" / "static"
STANDARD = ROOT / "docs" / "ARAYUZ-STANDARDI.md"
PANEL_CSS = STATIC / "panel.css"
THEME_CSS = STATIC / "theme.css"

CLASS_ATTR = re.compile(r'class="([^"]*)"')
JINJA_BLOCK = re.compile(r"\{\{.*?\}\}|\{%.*?%\}")
BRANCH = re.compile(r"\{%-?\s*(?:if|elif|else)\b")


def _templates() -> dict[str, str]:
    return {
        path.name: path.read_text(encoding="utf-8") for path in sorted(TEMPLATES.glob("*.html"))
    }


def _static_classes(html: str) -> set[str]:
    """Şablondaki düz sınıf adları; Jinja ifadesi taşıyan parçalar (`status-{{ x }}`) sayılmaz."""
    found: set[str] = set()
    for match in CLASS_ATTR.finditer(html):
        for token in JINJA_BLOCK.sub(" ", match.group(1)).split():
            if re.fullmatch(r"[A-Za-z][\w-]*[A-Za-z0-9]|[A-Za-z]", token):
                found.add(token)
    return found


def _css() -> str:
    return PANEL_CSS.read_text(encoding="utf-8") + THEME_CSS.read_text(encoding="utf-8")


def _css_without_urls(css: str) -> str:
    return re.sub(r'url\("[^"]*"\)', "", css)


def _styled_classes() -> set[str]:
    return set(re.findall(r"\.([A-Za-z][\w-]*)", _css_without_urls(_css())))


def _registered_hooks() -> set[str]:
    text = STANDARD.read_text(encoding="utf-8")
    section = text[text.index("## 4. ") : text.index("## 5. ")]
    return set(re.findall(r"`([a-z][\w-]*)`", section))


# --- şablonlar -----------------------------------------------------------------------------------


def test_every_template_class_is_styled_or_registered_as_a_hook() -> None:
    styled = _styled_classes()
    hooks = _registered_hooks()
    unknown = {
        name: sorted(cls for cls in _static_classes(html) if cls not in styled and cls not in hooks)
        for name, html in _templates().items()
    }
    unknown = {name: classes for name, classes in unknown.items() if classes}

    assert unknown == {}, (
        "Şablonda panel.css'te tanımsız ve docs/ARAYUZ-STANDARDI.md §4'te kayıtsız sınıf: "
        f"{unknown}"
    )


def test_registered_hooks_are_in_use_and_not_also_styled() -> None:
    # Kayıt listesi bayatlamasın: her hook bir şablonda geçer; stillenen sınıf hook değildir.
    used: set[str] = set()
    for html in _templates().values():
        used |= _static_classes(html)
    hooks = _registered_hooks()
    styled = _styled_classes()

    assert sorted(hooks - used) == [], "Hiçbir şablonda geçmeyen hook: listeden sil"
    assert sorted(hooks & styled) == [], "panel.css'te tanımlı sınıf §4 listesinde olmaz: §3'e taşı"


def test_templates_carry_no_inline_style_or_script() -> None:
    offenders: dict[str, list[str]] = {}
    for name, html in _templates().items():
        problems = []
        if re.search(r"\sstyle=", html):
            problems.append("style=")
        if "<style" in html and name != "base.html":  # base.html: yalnız <noscript><style>
            problems.append("<style>")
        if re.search(r"<script(?![^>]*\ssrc=)", html):
            problems.append("satır içi <script>")
        if re.search(r'<link[^>]+href="(?:https?:)?//', html) or re.search(
            r'<script[^>]+src="(?:https?:)?//', html
        ):
            problems.append("dış kaynak")
        if problems:
            offenders[name] = problems

    assert offenders == {}


def test_full_pages_have_a_single_h1_and_fragments_have_none() -> None:
    offenders: dict[str, str] = {}
    for name, html in _templates().items():
        page = '{% extends "base.html" %}' in html
        if name == "base.html":
            continue
        count = len(re.findall(r"<h1[\s>]", html))
        if page and count == 0:
            offenders[name] = "tam sayfada h1 yok"
        if not page and count:
            offenders[name] = "HTMX parçasında h1 var"
        if page and count > 1 and count > len(BRANCH.findall(html)):
            # Birden çok h1 ancak birbirini dışlayan dallarda (`if error` / `elif step`) olabilir;
            # düz akışta ikinci h1 yoktur.
            offenders[name] = f"{count} h1"

    assert offenders == {}


def test_full_pages_set_their_title() -> None:
    missing = [
        name
        for name, html in _templates().items()
        if '{% extends "base.html" %}' in html and "{% block title %}" not in html
    ]

    assert missing == []


def test_every_button_declares_its_type() -> None:
    offenders = {
        name: re.findall(r"<button(?![^>]*\stype=)[^>]*>", html)
        for name, html in _templates().items()
    }

    assert {name: found for name, found in offenders.items() if found} == {}


def test_every_table_is_named() -> None:
    offenders = {
        name: re.findall(r"<table(?![^>]*\sclass=)[^>]*>", html)
        for name, html in _templates().items()
    }

    assert {name: found for name, found in offenders.items() if found} == {}


def test_the_shell_keeps_its_landmarks() -> None:
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")

    for marker in (
        '<header class="topbar">',
        '<nav class="menu" aria-label=',
        "<a class=\"tool-link{% if active == 'access_log' %} active{% endif %}\" "
        'href="/access-log"',
        '<form class="session" method="post" action="/logout">',
        '<button type="submit">{{ _("Çıkış") }}</button>',
        '<div class="page-tools">',
        'class="theme-toggle" data-theme-toggle aria-pressed="false"',
        '<div class="toasts" aria-live="polite" data-close-label=',
        '<main class="content">',
    ):
        assert marker in base, marker
    # Menü bağlantısı çıplaktır: simge CSS'ten gelir, metin testlerin beklediği biçimde kalır.
    assert (
        '<a href="{{ entry.path }}"{% if entry.key == active %} class="active" '
        'aria-current="page"{% endif %}>{{ _(entry.label) }}</a>'
    ) in base


# --- stil ----------------------------------------------------------------------------------------


def test_panel_css_uses_tokens_not_raw_colours() -> None:
    css = PANEL_CSS.read_text(encoding="utf-8")
    root_start = css.index(":root {")
    root_end = css.index("}", root_start)
    outside = _css_without_urls(css[:root_start] + css[root_end:])

    raw = sorted(set(re.findall(r"#[0-9a-fA-F]{6}\b", outside)))
    assert raw == [], f":root dışında altı haneli renk: {raw} — theme.css değişkeni kullan"


def test_every_css_variable_used_is_defined() -> None:
    css = _css()
    defined = set(re.findall(r"(--[\w-]+)\s*:", css))
    used = set(re.findall(r"var\((--[\w-]+)", css))

    assert sorted(used - defined) == []


def test_dark_theme_overrides_every_light_token() -> None:
    theme = THEME_CSS.read_text(encoding="utf-8")
    light = theme[theme.index(":root {") : theme.index("}", theme.index(":root {"))]
    dark_start = theme.index('html[data-theme="dark"] {')
    dark = theme[dark_start : theme.index("}", dark_start)]
    light_tokens = set(re.findall(r"(--[\w-]+)\s*:", light))
    dark_tokens = set(re.findall(r"(--[\w-]+)\s*:", dark))

    assert sorted(light_tokens - dark_tokens) == []


def test_panel_css_has_no_external_resources() -> None:
    css = _css()

    assert "@import" not in css
    assert not re.search(r'url\("?(?:https?:)?//', css)


@pytest.mark.parametrize("entry", PANEL_MENU, ids=[entry.key for entry in PANEL_MENU])
def test_every_menu_entry_has_an_icon(entry) -> None:  # noqa: ANN001
    css = PANEL_CSS.read_text(encoding="utf-8")

    assert f'.menu a[href="{entry.path}"] {{ --icon: url(' in css, entry.path


def test_the_standard_document_names_the_test_and_the_layers() -> None:
    text = STANDARD.read_text(encoding="utf-8")

    assert "tests/web/test_ui_standard.py" in text
    for layer in ("base.html", "panel.css", "theme.css"):
        assert layer in text
