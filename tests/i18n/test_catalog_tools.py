"""10.10.3 çeviri kataloğunun bütünlüğü — `python -m app.i18n extract|update|compile|check`
(PLAN.md §D92 e).

Depodaki katalog temizdir ve kaynakla günceldir; geçici olarak bozulan bir katalogda boş ya da
bulanık çeviri, eksik/fazla msgid, eski kayıt, uyuşmayan yer tutucu, yanlış çoğul kuralı ve eski
`.mo` her biri ayrı ayrı yakalanır.
"""

from __future__ import annotations

import gettext as stdlib_gettext
import io
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from babel.messages.catalog import Catalog
from babel.messages.pofile import read_po, write_po

from app.i18n import tools
from app.i18n.__main__ import main
from app.i18n.catalog import LOCALES_DIR, mo_path, po_path

BANNER = "Sunucu eski sürümle çalışıyor — yeniden başlatın (<code>baslat.bat</code>)."


def _read(path: Path) -> Catalog:
    with path.open("rb") as handle:
        return read_po(handle)


def _write(path: Path, catalog: Catalog) -> None:
    buffer = io.BytesIO()
    write_po(buffer, catalog, sort_output=True, include_lineno=False)
    path.write_bytes(buffer.getvalue())


def _edit(path: Path, change: Callable[[Catalog], None]) -> None:
    catalog = _read(path)
    change(catalog)
    _write(path, catalog)


@pytest.fixture
def locales(tmp_path: Path) -> Path:
    """Depodaki kataloğun geçici kopyası (bozma testleri depoya dokunmaz)."""
    target = tmp_path / "locales"
    shutil.copytree(LOCALES_DIR, target)
    return target


@pytest.fixture(scope="module")
def source() -> Catalog:
    return tools.extract_messages()


# --- depodaki katalog -------------------------------------------------------------------------


def test_repository_catalog_is_clean() -> None:
    assert tools.check() == []


def test_repository_catalog_is_current_with_the_source(locales: Path) -> None:
    # Kaynaktan yeniden çıkarmak, eşitlemek ve derlemek hiçbir dosyayı değiştirmez.
    assert tools.extract(locales_dir=locales) is False
    assert tools.update(locales_dir=locales) == []
    assert tools.compile_catalogs(locales_dir=locales) == []
    for path in sorted(LOCALES_DIR.rglob("*.*")):
        assert (locales / path.relative_to(LOCALES_DIR)).read_bytes() == path.read_bytes()


def test_catalogs_cover_english_and_serbian_with_the_skeleton_texts(source: Catalog) -> None:
    ids = {message.id for message in source if message.id}

    assert {"Çalışanlar", "Kullanıcılar", "Çıkış", "Giriş yap", "Ana menü", BANNER} <= ids
    assert "Kullanıcı adı veya parola hatalı." in ids
    for code in ("en", "sr"):
        assert po_path(code).is_file() and mo_path(code).is_file()


def test_serbian_header_declares_latin_script_and_the_cldr_plural_rule() -> None:
    header = _read(po_path("sr")).mime_headers

    assert dict(header)["Language"] == "sr_Latn"
    assert dict(header)["Plural-Forms"] == (
        "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && "
        "(n%100<10 || n%100>=20) ? 1 : 2);"
    )


def test_translations_follow_the_glossary() -> None:
    glossary = (LOCALES_DIR.parent / "GLOSSARY.md").read_text(encoding="utf-8")
    rows = {
        cells[0]: (cells[1], cells[2])
        for line in glossary.splitlines()
        if line.startswith("| ") and not line.startswith("| Türkçe") and "---" not in line
        for cells in [[cell.strip() for cell in line.strip("|").split("|")]]
    }
    english, serbian = _read(po_path("en")), _read(po_path("sr"))

    for msgid in ("Çalışanlar", "Yükle", "Belge Türleri", "Kuyruklar", "Eğitim modu"):
        assert (english[msgid].string, serbian[msgid].string) == rows[msgid]


# --- check: her bozulma ayrı yakalanır --------------------------------------------------------


def _set(msgid: str, value: str) -> Callable[[Catalog], None]:
    def change(catalog: Catalog) -> None:
        catalog[msgid].string = value

    return change


def _recompile(locales: Path) -> None:
    tools.compile_catalogs(locales_dir=locales)


def test_empty_translation_is_reported(locales: Path, source: Catalog) -> None:
    _edit(po_path("en", locales), _set("Kuyruklar", ""))
    _recompile(locales)

    assert tools.check(locales, source) == ["en/messages.po: 'Kuyruklar': boş çeviri"]


def test_fuzzy_translation_is_reported(locales: Path, source: Catalog) -> None:
    def change(catalog: Catalog) -> None:
        catalog["Kuyruklar"].flags.add("fuzzy")

    _edit(po_path("sr", locales), change)
    _recompile(locales)

    assert tools.check(locales, source) == ["sr/messages.po: 'Kuyruklar': bulanık (fuzzy) çeviri"]


def test_fuzzy_header_is_reported(locales: Path, source: Catalog) -> None:
    def change(catalog: Catalog) -> None:
        catalog.fuzzy = True

    _edit(po_path("en", locales), change)
    _recompile(locales)

    assert tools.check(locales, source) == ["en/messages.po: başlık bulanık (fuzzy) işaretli"]


def test_stale_mo_is_reported(locales: Path, source: Catalog) -> None:
    _edit(po_path("en", locales), _set("Kuyruklar", "Review queues"))

    assert tools.check(locales, source) == [
        "en/messages.mo: .po ile güncel değil — `python -m app.i18n compile`"
    ]


def test_missing_mo_is_reported(locales: Path, source: Catalog) -> None:
    mo_path("sr", locales).unlink()

    assert tools.check(locales, source) == ["sr/messages.mo: yok — `python -m app.i18n compile`"]


def test_missing_po_is_reported(locales: Path, source: Catalog) -> None:
    po_path("sr", locales).unlink()

    assert tools.check(locales, source) == ["sr/messages.po: yok — `python -m app.i18n update`"]


def test_mismatched_markup_placeholder_is_reported(locales: Path, source: Catalog) -> None:
    _edit(po_path("en", locales), _set(BANNER, "The server is outdated — restart baslat.bat."))
    _recompile(locales)

    assert tools.check(locales, source) == [
        f"en/messages.po: {BANNER!r}: yer tutucular kaynakla uyuşmuyor"
    ]


def test_msgid_missing_from_catalog_and_stale_template_are_reported(
    locales: Path, source: Catalog
) -> None:
    grown = _read(tools.template_path(locales))
    grown.add("Yeni işaretlenen metin", locations=[("app/web/templates/x.html", None)])

    assert tools.check(locales, grown) == [
        "messages.pot: kaynakla güncel değil — `python -m app.i18n extract`",
        "en/messages.po: 'Yeni işaretlenen metin' katalogda yok",
        "sr/messages.po: 'Yeni işaretlenen metin' katalogda yok",
    ]


def test_msgid_no_longer_in_source_and_obsolete_entry_are_reported(
    locales: Path, source: Catalog
) -> None:
    def change(catalog: Catalog) -> None:
        catalog.add("Kaldırılmış metin", "Removed text")
        catalog.obsolete["Eski metin"] = catalog["Kaldırılmış metin"].clone()
        catalog.obsolete["Eski metin"].id = "Eski metin"

    _edit(po_path("en", locales), change)
    _recompile(locales)

    assert tools.check(locales, source) == [
        "en/messages.po: 'Kaldırılmış metin' kaynakta yok",
        "en/messages.po: eski (#~) kayıt 'Eski metin'",
    ]


def test_wrong_plural_rule_is_reported(locales: Path, source: Catalog) -> None:
    path = po_path("sr", locales)
    text = path.read_text(encoding="utf-8")
    start = text.index('"Plural-Forms:')
    end = text.index('"MIME-Version')
    path.write_text(
        text[:start] + '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n' + text[end:],
        encoding="utf-8",
        newline="\n",
    )
    _recompile(locales)

    problems = tools.check(locales, source)

    assert len(problems) == 1
    assert problems[0].startswith("sr/messages.po: Plural-Forms dilin CLDR kuralı değil")


# --- yer tutucular ve çoğul biçimler ----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Merhaba %(ad)s, %(sayi)d belge", {"%(ad)s": 1, "%(sayi)d": 1}),
        ("{sayi} belge · {}", {"{sayi}": 1, "{}": 1}),
        ("%%90 dolu", {"%%": 1}),
        ("<Ad Soyad> belgesi <code>x</code>", {"<Ad Soyad>": 1, "<code>": 1, "</code>": 1}),
        ("yer tutucusuz", {}),
    ],
)
def test_placeholders(text: str, expected: dict[str, int]) -> None:
    assert tools.placeholders(text) == expected


def _mini_source() -> Catalog:
    catalog = Catalog(project="test", fuzzy=False)
    location = [("app/web/templates/x.html", None)]
    catalog.add("Merhaba %(ad)s", locations=location)
    catalog.add("{sayi} parti", locations=location)
    catalog.add("<Ad Soyad> onayı", locations=location)
    catalog.add(("%(n)s belge", "%(n)s belge"), locations=location)
    return catalog


TRANSLATIONS = {
    "en": {
        "Merhaba %(ad)s": "Hello %(ad)s",
        "{sayi} parti": "{sayi} batches",
        "<Ad Soyad> onayı": "Confirmation of <Ad Soyad>",
        "%(n)s belge": ("%(n)s document", "%(n)s documents"),
    },
    "sr": {
        "Merhaba %(ad)s": "Zdravo %(ad)s",
        "{sayi} parti": "{sayi} serija",
        "<Ad Soyad> onayı": "Potvrda za <Ad Soyad>",
        "%(n)s belge": ("%(n)s dokument", "%(n)s dokumenta", "%(n)s dokumenata"),
    },
}


@pytest.fixture
def mini(tmp_path: Path) -> tuple[Path, Catalog]:
    """Yer tutuculu ve çoğullu küçük bir katalog: extract → update → çeviri → compile."""
    locales = tmp_path / "mini"
    source = _mini_source()
    locales.mkdir()
    _write(tools.template_path(locales), source)
    assert sorted(path.parent.parent.name for path in tools.update(locales_dir=locales)) == [
        "en",
        "sr",
    ]
    for code, strings in TRANSLATIONS.items():

        def change(catalog: Catalog, strings: dict[str, object] = strings) -> None:
            for message in catalog:
                if message.id:
                    key = message.id[0] if message.pluralizable else message.id
                    message.string = strings[key]

        _edit(po_path(code, locales), change)
    tools.compile_catalogs(locales_dir=locales)
    return locales, source


def test_update_adds_new_texts_with_empty_translations_and_plural_slots(tmp_path: Path) -> None:
    locales = tmp_path / "yeni"
    locales.mkdir()
    _write(tools.template_path(locales), _mini_source())

    tools.update(locales_dir=locales)

    serbian = _read(po_path("sr", locales))
    assert serbian["Merhaba %(ad)s"].string == ""
    assert serbian["%(n)s belge"].string == ("", "", "")
    assert _read(po_path("en", locales))["%(n)s belge"].string == ("", "")
    assert tools.update(locales_dir=locales) == []


def test_translated_mini_catalog_is_clean_and_serbian_plurals_work(
    mini: tuple[Path, Catalog],
) -> None:
    locales, source = mini

    assert tools.check(locales, source) == []
    translations = stdlib_gettext.GNUTranslations(io.BytesIO(mo_path("sr", locales).read_bytes()))
    forms = [
        translations.ngettext("%(n)s belge", "%(n)s belge", n) % {"n": n} for n in (1, 3, 5, 21)
    ]
    assert forms == ["1 dokument", "3 dokumenta", "5 dokumenata", "21 dokument"]


@pytest.mark.parametrize(
    ("msgid", "broken"),
    [
        ("Merhaba %(ad)s", "Hello %(name)s"),
        ("Merhaba %(ad)s", "Hello"),
        ("{sayi} parti", "{count} batches"),
        ("<Ad Soyad> onayı", "Confirmation of <Full Name>"),
    ],
)
def test_each_placeholder_mismatch_is_reported(
    mini: tuple[Path, Catalog], msgid: str, broken: str
) -> None:
    locales, source = mini
    _edit(po_path("en", locales), _set(msgid, broken))
    _recompile(locales)

    assert tools.check(locales, source) == [
        f"en/messages.po: {msgid!r}: yer tutucular kaynakla uyuşmuyor"
    ]


def test_plural_form_problems_are_reported(mini: tuple[Path, Catalog]) -> None:
    locales, source = mini

    def blank_form(catalog: Catalog) -> None:
        catalog["%(n)s belge"].string = ("%(n)s dokument", "", "%(n)s dokumenata")

    _edit(po_path("sr", locales), blank_form)
    _recompile(locales)
    assert tools.check(locales, source) == ["sr/messages.po: '%(n)s belge': boş çeviri"]

    def lost_number(catalog: Catalog) -> None:
        catalog["%(n)s belge"].string = ("jedan dokument", "%(n)s dokumenta", "%(n)s dokumenata")

    _edit(po_path("sr", locales), lost_number)
    _recompile(locales)
    assert tools.check(locales, source) == [
        "sr/messages.po: '%(n)s belge': yer tutucular kaynakla uyuşmuyor"
    ]


def test_update_keeps_translations_drops_removed_texts_and_never_guesses(
    mini: tuple[Path, Catalog],
) -> None:
    locales, source = mini
    template = _read(tools.template_path(locales))
    del template["{sayi} parti"]
    template.add("Merhaba %(ad)s!", locations=[("app/web/templates/x.html", None)])
    _write(tools.template_path(locales), template)

    tools.update(locales_dir=locales)

    english = _read(po_path("en", locales))
    assert english["Merhaba %(ad)s"].string == "Hello %(ad)s"
    # Benzer metnin çevirisi bulanık eşleşmeyle taşınmaz: boş kalır, check yakalar.
    assert english["Merhaba %(ad)s!"].string == ""
    assert not english["Merhaba %(ad)s!"].fuzzy
    assert english.get("{sayi} parti") is None
    assert not english.obsolete


def test_update_does_not_carry_a_translation_to_a_changed_plural_text(
    mini: tuple[Path, Catalog],
) -> None:
    # Aynı tekil msgid'in çoğulu değişti ya da tekil metin çoğullu oldu: eski çeviri taşınmaz.
    locales, _source = mini
    template = _read(tools.template_path(locales))
    del template["%(n)s belge"]
    del template["Merhaba %(ad)s"]
    location = [("app/web/templates/x.html", None)]
    template.add(("%(n)s belge", "%(n)s belge var"), locations=location)
    template.add(("Merhaba %(ad)s", "Merhaba %(ad)s ve %(n)s kişi"), locations=location)
    _write(tools.template_path(locales), template)

    tools.update(locales_dir=locales)

    serbian = _read(po_path("sr", locales))
    assert serbian["%(n)s belge"].string == ("", "", "")
    assert serbian["Merhaba %(ad)s"].string == ("", "", "")
    assert serbian["{sayi} parti"].string == "{sayi} serija"


# --- komut ------------------------------------------------------------------------------------


def test_check_command_exits_zero_on_the_repository(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check"]) == 0
    assert "katalog temiz" in capsys.readouterr().out


def test_check_command_lists_problems_and_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tools, "check", lambda: ["en/messages.po: 'X': boş çeviri"])

    assert main(["check"]) == 1
    assert "en/messages.po: 'X': boş çeviri" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("command", "function", "unchanged", "changed", "printed"),
    [
        ("extract", "extract", False, True, "messages.pot: güncellendi"),
        ("update", "update", [], [Path("sr.po")], "güncellendi: sr.po"),
        ("compile", "compile_catalogs", [], [Path("sr.mo")], "derlendi: sr.mo"),
    ],
)
def test_commands_report_what_they_changed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    function: str,
    unchanged: object,
    changed: object,
    printed: str,
) -> None:
    # Depodaki dosyalara yazılmasın: komutların işini geçici kopyada
    # `test_repository_catalog_is_current_with_the_source` sınar; burada yalnız komut satırı.
    monkeypatch.setattr(tools, function, lambda: unchanged)
    assert main([command]) == 0
    assert "değişiklik yok" in capsys.readouterr().out

    monkeypatch.setattr(tools, function, lambda: changed)
    assert main([command]) == 0
    assert printed in capsys.readouterr().out


def test_unknown_command_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as raised:
        main(["translate"])
    assert raised.value.code == 2
