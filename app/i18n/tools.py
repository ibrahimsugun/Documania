"""Çeviri kataloğu araçları (PRD 10.10.3; PLAN.md §D92 e) — `python -m app.i18n <komut>`.

- `extract`: işaretli metinleri (`_`, `gettext`, `ngettext`, `N_`; Jinja2'de `{% trans %}`)
  kaynaktan (`babel.cfg`: `app/` altındaki Python dosyaları ve panel şablonları)
  `locales/messages.pot`'a yazar.
- `update`: her dilin `.po`'sunu şablona eşitler. Yeni msgid boş çeviriyle girer, kaynaktan kalkan
  silinir; bulanık eşleştirme yapılmaz (benzer bir metnin çevirisi sessizce sızmasın).
- `compile`: her `.po`'yu `.mo`'ya derler; çalışma zamanı yalnız `.mo` okur (`app.i18n.catalog`).
- `check`: kataloğun bütünlüğü (aynı denetim testte, DoD kapısının parçası): şablon ve her `.po`
  kaynakla aynı msgid'leri taşır; boş ya da bulanık (`fuzzy`) çeviri, eski (`#~`) kayıt yok; yer
  tutucular (`%(ad)s`, `%%`, `{ad}`, `<…>` etiketleri ve `<Ad Soyad>` biçimi) msgid ile her
  msgstr'de aynı; `Plural-Forms` dilin CLDR kuralı; her `.mo` kendi `.po`'sunun güncel derlemesi.

Çıktılar kararlıdır: msgid sırası alfabetik, konumlarda satır numarası yok, içerik değişmediyse
dosya yeniden yazılmaz (başlıktaki tarih boşuna oynamaz).
"""

from __future__ import annotations

import io
import re
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from babel.messages.catalog import Catalog, Message
from babel.messages.extract import extract_from_dir
from babel.messages.frontend import parse_mapping_cfg
from babel.messages.mofile import write_mo
from babel.messages.plurals import get_plural
from babel.messages.pofile import read_po, write_po

from app.i18n.catalog import DOMAIN, LOCALES_DIR, mo_path, po_path
from app.i18n.languages import CATALOG_LANGUAGES, SUPPORTED_LANGUAGES

PROJECT = "Documania"
VERSION = "panel"
SOURCE_DIR = Path(__file__).resolve().parents[1]  # `app/`
MAPPING_FILE = SOURCE_DIR.parent / "babel.cfg"
TEMPLATE_NAME = f"{DOMAIN}.pot"
KEYWORDS = {"_": None, "gettext": None, "ngettext": (1, 2), "N_": None}
COMMENT_TAGS = ("Translators:",)
# Katalog başlığındaki dil: `sr` Latin alfabesiyledir (§D92 a); çoğul kuralı CLDR'den.
CATALOG_LOCALES = {"en": "en", "sr": "sr_Latn"}
# Yeni açılan kataloğun çevirmeni: pencere çevirir, ana dili o dil olan biri gözden geçirmeli.
NEW_CATALOG_TRANSLATOR = "Documania görev penceresi (gözden geçirilmeli)"
PLACEHOLDER = re.compile(r"%\(\w+\)[sdifr]|%%|\{\w*\}|<[^<>]+>")

MessageKey = tuple[str | tuple[str, ...], str | None]


def template_path(locales_dir: Path = LOCALES_DIR) -> Path:
    return locales_dir / TEMPLATE_NAME


# --- extract ----------------------------------------------------------------------------------


def extract_messages(source_dir: Path = SOURCE_DIR, mapping_file: Path = MAPPING_FILE) -> Catalog:
    """Kaynaktaki işaretli metinlerin şablon kataloğu (`messages.pot` içeriği)."""
    with mapping_file.open(encoding="utf-8") as handle:
        method_map, options_map = parse_mapping_cfg(handle, str(mapping_file))
    catalog = Catalog(
        header_comment=(
            f"# {PROJECT} arayüz metinleri — çeviri şablonu. Kaynak dil Türkçedir (msgid).\n"
            "# Elle düzenlenmez: `python -m app.i18n extract` kaynaktan üretir."
        ),
        project=PROJECT,
        version=VERSION,
        charset="utf-8",
        fuzzy=False,
    )
    for filename, lineno, message, comments, context in extract_from_dir(
        str(source_dir),
        method_map,
        options_map,
        keywords=KEYWORDS,
        comment_tags=COMMENT_TAGS,
        strip_comment_tags=True,
    ):
        location = f"{source_dir.name}/{filename}".replace("\\", "/")
        catalog.add(message, None, [(location, lineno)], auto_comments=comments, context=context)
    return catalog


def _po_bytes(catalog: Catalog) -> bytes:
    buffer = io.BytesIO()
    write_po(buffer, catalog, sort_output=True, include_lineno=False, ignore_obsolete=True)
    return buffer.getvalue()


def _write_if_changed(path: Path, catalog: Catalog, stamp: Iterable[str]) -> bool:
    """`catalog`'u `path`'e yazar; yalnız `stamp`'teki tarih alanları değişecekse yazmaz.

    Dosyadaki tarih alanları önce yeni kataloğa aktarılır; içerik aynıysa dosya olduğu gibi kalır,
    değilse tarih alanları şimdiye çekilerek yazılır."""
    if path.exists():
        with path.open("rb") as handle:
            current = read_po(handle)
        for attribute in stamp:
            setattr(catalog, attribute, getattr(current, attribute))
        if _po_bytes(catalog) == path.read_bytes():
            return False
    now = datetime.now(UTC)
    for attribute in stamp:
        setattr(catalog, attribute, now)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_po_bytes(catalog))
    return True


def extract(
    locales_dir: Path = LOCALES_DIR,
    source_dir: Path = SOURCE_DIR,
    mapping_file: Path = MAPPING_FILE,
) -> bool:
    """`messages.pot`'u kaynaktan yeniden üretir; dosya değiştiyse `True`."""
    template = extract_messages(source_dir, mapping_file)
    return _write_if_changed(template_path(locales_dir), template, ("creation_date",))


# --- update -----------------------------------------------------------------------------------


def _read(path: Path) -> Catalog:
    with path.open("rb") as handle:
        return read_po(handle)


def _empty_string(message: Message, catalog: Catalog) -> str | tuple[str, ...]:
    return ("",) * catalog.num_plurals if message.pluralizable else ""


def _merged(template: Catalog, code: str, previous: Catalog | None) -> Catalog:
    language = SUPPORTED_LANGUAGES[code].name
    catalog = Catalog(
        locale=CATALOG_LOCALES[code],
        domain=DOMAIN,
        header_comment=(
            f"# {PROJECT} arayüz metinleri: {language} ({code}). Kaynak dil Türkçe (msgid).\n"
            '# Terimler: app/i18n/GLOSSARY.md. Akış: README, "Arayüz dili".'
        ),
        project=PROJECT,
        version=VERSION,
        last_translator=NEW_CATALOG_TRANSLATOR,
        language_team=language,
        charset="utf-8",
        fuzzy=False,
    )
    if previous is not None:
        catalog.last_translator = previous.last_translator
        catalog.language_team = previous.language_team
    for message in template:
        if not message.id:
            continue
        old = previous.get(message.id, message.context) if previous is not None else None
        kept = old is not None and old.id == message.id
        catalog.add(
            message.id,
            old.string if kept else _empty_string(message, catalog),
            locations=message.locations,
            flags=(old.flags if kept else set()) | (message.flags - {"fuzzy"}),
            auto_comments=message.auto_comments,
            user_comments=old.user_comments if kept else (),
            context=message.context,
        )
    return catalog


def update(locales_dir: Path = LOCALES_DIR) -> list[Path]:
    """Her dilin `.po`'sunu `messages.pot`'a eşitler; değişen dosyaları döner."""
    template = _read(template_path(locales_dir))
    changed = []
    for code in CATALOG_LANGUAGES:
        path = po_path(code, locales_dir)
        previous = _read(path) if path.exists() else None
        catalog = _merged(template, code, previous)
        if _write_if_changed(path, catalog, ("creation_date", "revision_date")):
            changed.append(path)
    return changed


# --- compile ----------------------------------------------------------------------------------


def compiled(po: Path) -> bytes:
    """`.po` dosyasının `.mo` derlemesi (bulanık çeviriler alınmaz)."""
    buffer = io.BytesIO()
    write_mo(buffer, _read(po), use_fuzzy=False)
    return buffer.getvalue()


def compile_catalogs(locales_dir: Path = LOCALES_DIR) -> list[Path]:
    """Her dilin `.mo`'sunu `.po`'sundan üretir; değişen dosyaları döner."""
    changed = []
    for code in CATALOG_LANGUAGES:
        target = mo_path(code, locales_dir)
        data = compiled(po_path(code, locales_dir))
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)
            changed.append(target)
    return changed


# --- check ------------------------------------------------------------------------------------


def _key(message: Message) -> MessageKey:
    identifier = message.id
    return (
        tuple(identifier) if isinstance(identifier, list | tuple) else identifier,
        message.context,
    )


def _keys(catalog: Catalog) -> set[MessageKey]:
    return {_key(message) for message in catalog if message.id}


def _label(key: MessageKey) -> str:
    identifier = key[0]
    return repr(identifier[0] if isinstance(identifier, tuple) else identifier)


def placeholders(text: str) -> Counter[str]:
    """Metindeki yer tutucular: `%(ad)s`, `%%`, `{ad}`, `<…>` (HTML etiketi ya da `<Ad Soyad>`)."""
    return Counter(PLACEHOLDER.findall(text))


def _message_problems(message: Message, catalog: Catalog) -> list[str]:
    label = _label(_key(message))
    if message.fuzzy:
        return [f"{label}: bulanık (fuzzy) çeviri"]
    if message.pluralizable:
        singular, plural = message.id
        forms = list(message.string) if isinstance(message.string, list | tuple) else []
        if len(forms) != catalog.num_plurals:
            return [f"{label}: {catalog.num_plurals} çoğul biçim beklenir, {len(forms)} var"]
        if any(not form for form in forms):
            return [f"{label}: boş çeviri"]
        allowed = (placeholders(singular), placeholders(plural))
        if any(placeholders(form) not in allowed for form in forms):
            return [f"{label}: yer tutucular kaynakla uyuşmuyor"]
        return []
    if not message.string:
        return [f"{label}: boş çeviri"]
    if placeholders(message.string) != placeholders(message.id):
        return [f"{label}: yer tutucular kaynakla uyuşmuyor"]
    return []


def _catalog_problems(code: str, locales_dir: Path, expected: set[MessageKey]) -> list[str]:
    po = po_path(code, locales_dir)
    name = f"{code}/{po.name}"
    if not po.exists():
        return [f"{name}: yok — `python -m app.i18n update`"]
    catalog = _read(po)
    problems = []
    if catalog.fuzzy:
        problems.append(f"{name}: başlık bulanık (fuzzy) işaretli")
    rule = get_plural(CATALOG_LOCALES[code])
    if (catalog.num_plurals, catalog.plural_expr) != (rule.num_plurals, rule.plural_expr):
        problems.append(f"{name}: Plural-Forms dilin CLDR kuralı değil ({rule.plural_forms})")
    keys = _keys(catalog)
    problems += [f"{name}: {_label(key)} katalogda yok" for key in sorted(expected - keys, key=str)]
    problems += [f"{name}: {_label(key)} kaynakta yok" for key in sorted(keys - expected, key=str)]
    problems += [f"{name}: eski (#~) kayıt {_label(_key(m))}" for m in catalog.obsolete.values()]
    for message in catalog:
        if message.id:
            problems += [f"{name}: {problem}" for problem in _message_problems(message, catalog)]
    mo = mo_path(code, locales_dir)
    if not mo.exists():
        problems.append(f"{code}/{mo.name}: yok — `python -m app.i18n compile`")
    elif mo.read_bytes() != compiled(po):
        problems.append(f"{code}/{mo.name}: .po ile güncel değil — `python -m app.i18n compile`")
    return problems


def check(locales_dir: Path = LOCALES_DIR, source: Catalog | None = None) -> list[str]:
    """Kataloğun bütünlük sorunları; boş liste temiz demektir. `source` verilmezse kaynaktan
    çıkarılır (`extract_messages`)."""
    expected = _keys(source if source is not None else extract_messages())
    problems = []
    template = template_path(locales_dir)
    if not template.exists():
        problems.append(f"{template.name}: yok — `python -m app.i18n extract`")
    elif _keys(_read(template)) != expected:
        problems.append(f"{template.name}: kaynakla güncel değil — `python -m app.i18n extract`")
    for code in CATALOG_LANGUAGES:
        problems += _catalog_problems(code, locales_dir, expected)
    return problems
