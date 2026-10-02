"""Türkçe kalıntı tarama yardımcısının kendisi (PLAN.md §D92 g): neyi görünen metin sayar, neyi
veri sayıp atlar, neyi Türkçe bulur."""

from __future__ import annotations

import pytest

from tests.i18n.residue import assert_no_turkish, turkish_residue, visible_text


def test_visible_text_skips_scripts_styles_and_hidden_values() -> None:
    html = """<!doctype html><html><head><title>Sign in · Documania</title>
    <style>.x::after { content: "Çıkış"; }</style>
    <script>const t = "Çalışanlar";</script></head>
    <body><p>Hello   <b>world</b></p>
    <input type="hidden" name="next" value="Çalışanlar">
    <input name="q" value="Ağaç">
    <input type="submit" value="Send">
    <img src="x.png" alt="Logo"><nav aria-label="Main menu"></nav>
    <span title="Hint" data-x="Çok">x</span></body></html>"""

    assert visible_text(html) == [
        "Sign in · Documania",
        "Hello",
        "world",
        "Send",
        "Logo",
        "Main menu",
        "Hint",
        "x",
    ]


def test_translate_no_subtree_is_data_and_is_skipped() -> None:
    html = (
        '<p>Owner: <span translate="no">Ayşe <b>Yılmaz</b> <span>Öz</span></span> ok</p>'
        '<input type="submit" translate="no" value="Gönder"><em>after</em>'
    )

    assert visible_text(html) == ["Owner:", "ok", "after"]
    assert turkish_residue(html) == []


@pytest.mark.parametrize(
    ("html", "found"),
    [
        ("<p>Çalışan bulunamadı</p>", ["Çalışan bulunamadı"]),
        ("<button>Kaydet</button>", ["Kaydet"]),
        ('<nav aria-label="Ana menü"></nav>', ["Ana menü"]),
        ('<input type="submit" value="Onayla">', ["Onayla"]),
        ("<title>Yeni belge</title>", ["Yeni belge"]),
        ("<p>İ</p>", ["İ"]),
        ("<p>Queues · Documents · Sign out</p>", []),
        ("<p>Kabul Ediliyor? no — ASCII words outside the list pass</p>", []),
    ],
)
def test_turkish_letters_and_dictionary_words_are_found(html: str, found: list[str]) -> None:
    assert turkish_residue(html) == found


def test_serbian_page_does_not_flag_words_that_are_also_serbian() -> None:
    html = "<p>Parola dana</p><p>Lozinka</p>"

    assert turkish_residue(html, "en") == ["Parola dana"]
    assert turkish_residue(html, "sr") == []
    assert turkish_residue("<p>Korisničko ime · Režim obuke · Odjava</p>", "sr") == []


def test_assert_no_turkish_reports_what_remained() -> None:
    assert_no_turkish("<p>Employees</p>")
    with pytest.raises(AssertionError, match="Yüklemeler"):
        assert_no_turkish("<p>Uploads</p><a>Yüklemeler</a>")
