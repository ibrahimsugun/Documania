"""Belge türü örnekleri (PRD 11.2.1) — `KnownDocuments/examples/<tur_slug>/`.

Örnek, bir belge türünün nasıl göründüğünü gösteren örnek belgedir (tür açıklaması üretimi 11.3'ün
girdisi). **Çalışan verisi değildir:** `Inbox/`, `Employees/` ya da kuyruk dizinlerine yazılmaz;
`uploads`, `upload_files` ya da `documents` tablosuna satır eklenmez. Çalışan ve belge aramaları
(10.4.2) yalnız o tabloları okuduğu, tekrar yükleme tespiti (K10, `find_original_by_sha256`)
`upload_files`'a baktığı için örnek hiçbir aramada görünmez ve gerçek bir yüklemeyi "tekrar"
işaretlemez.

**Kayıt ve olay (PLAN.md §D58 e).** Tür sayfasından el ile yükleme (11.2.1) yalnız dosyayı yazar:
`example_files` kaydı ve olay yazmaz, örnek etiketsizdir. Eğitim modunun (11.9) yerleştirmesi bu
modülün `store_example`'ını kullanır, örneği ayrıca `example_files`'a (yöntem, etiket, not)
kaydeder ve olay yazar (`app.training.placement`, K15). Türler arası tekrar tespiti o kaydın
işidir; bu modül yalnız aynı klasöre bakar.

- **Türler:** yalnız PDF, JPEG ve PNG (K2: analiz edilenler). Tür dosya adına değil içeriğin
  imzasına bakılarak belirlenir; uzantı içeriğe göre yeniden yazılır (`.pdf`, `.jpg`, `.png`) — adı
  `.jpg` olan PDF `.pdf` olarak saklanır. İçerik okunamıyorsa (bozuk PDF/görüntü) reddedilir.
- **Ad:** yüklenen adın gövdesi `[A-Za-z0-9-]` kelimelerine sadeleştirilir (`slugify`); dizinde
  varsa `-2`, `-3` eki alır. Yol parçası yükleyenden gelmez.
- **Tekrar:** dizinde aynı SHA-256'lı örnek varsa yeni dosya yazılmaz, var olan bildirilir.
- **İçerik değişmez** (K11, K17): baytlar olduğu gibi yazılır; yeniden kodlama, kırpma yok. Silme
  yok (K16'nın ruhu).
- **Taşıma (11.9.4, PLAN.md §D58).** İK'nın etiket kararı örneği başka türün klasörüne
  (`relocate_example`) ya da eğitim arşivine (`archive_example`, `_egitim/cikarilan/<tur_slug>/`)
  taşır: içerik hedefe atomik yazılır (`write_unique`; ad doluysa `-2`, `-3`), SHA-256'sı
  kaydınkiyle tutmazsa hiçbir şey yayınlanmaz (`ContentMismatchError`); yayından sonra kaynak ad
  kaldırılır — kopya bırakılmaz, içerik yeni yerinde bayt bayt aynıdır (K11: yalnız taşıma).

Dizin, bu modülden önce elle yerleştirilmiş dosyaları da içerebilir; liste yalnız izinli uzantılı
düz dosyaları gösterir.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath

from PIL import Image
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.storage.atomic import (
    StoredFile,
    is_partial_write,
    iter_file_chunks,
    sha256_bytes,
    sha256_file,
    write_unique,
)
from app.storage.filetype import FileKind, UnsupportedFileTypeError, detect_file_kind
from app.storage.layout import DataLayout
from app.storage.slug import SlugError, slugify

# Kabul edilen içerik türü → saklanan uzantı.
EXAMPLE_EXTENSIONS = {FileKind.PDF: "pdf", FileKind.JPEG: "jpg", FileKind.PNG: "png"}
# Listede gösterilen uzantılar (elle yerleştirilen `.jpeg`/büyük harfli adlar dahil).
_LISTED_SUFFIXES = frozenset({".pdf", ".jpg", ".jpeg", ".png"})
_PILLOW_FORMATS = {FileKind.JPEG: "JPEG", FileKind.PNG: "PNG"}
_FALLBACK_STEM = "ornek"
_STEM_MAX_LENGTH = 80


class ExampleRejectedError(ValueError):
    """Dosya örnek olarak kabul edilmedi; mesaj kullanıcıya gösterilir."""


@dataclass(frozen=True, slots=True)
class ExampleFile:
    """Türün örnek dizinindeki bir dosya."""

    name: str
    size: int


@dataclass(frozen=True, slots=True)
class StoredExample:
    """`store_example` sonucu: örnek dosyanın adı; `duplicate` doluysa aynı içerik zaten vardı
    ve hiçbir şey yazılmadı."""

    name: str
    size: int
    sha256: str
    duplicate: bool


def check_example(original_name: str, content: bytes, *, max_bytes: int) -> FileKind:
    """Dosyanın örnek olabileceğini denetler ve içerik türünü döner; olamazsa
    `ExampleRejectedError` (yazmadan önce çağrılır)."""
    label = _display_name(original_name)
    if not content:
        raise ExampleRejectedError(f"'{label}' dosyası boş.")
    if len(content) > max_bytes:
        raise ExampleRejectedError(
            f"'{label}' dosyası {max_bytes / (1024 * 1024):.0f} MB sınırını aşıyor."
        )
    try:
        kind = detect_file_kind(content)
    except UnsupportedFileTypeError:
        raise _unsupported(label) from None
    if kind not in EXAMPLE_EXTENSIONS:
        raise _unsupported(label)
    if not _is_readable(kind, content):
        raise ExampleRejectedError(f"'{label}' dosyası açılamadı; bozuk olabilir.")
    return kind


def store_example(
    layout: DataLayout, type_slug: str, original_name: str, content: bytes, kind: FileKind
) -> StoredExample:
    """Örneği `KnownDocuments/examples/<tur_slug>/` altına yazar; `kind` `check_example`'ın
    döndüğüdür. Aynı içerik dizinde varsa yazmaz."""
    directory = layout.type_examples_dir(type_slug)
    sha256 = sha256_bytes(content)
    existing = find_example(layout, type_slug, sha256)
    if existing is not None:
        return StoredExample(existing.name, existing.size, sha256, duplicate=True)
    name = f"{_stem(original_name)}.{EXAMPLE_EXTENSIONS[kind]}"
    stored = write_unique(directory, name, content, expected_sha256=sha256)
    return StoredExample(stored.path.name, stored.size, sha256, duplicate=False)


def list_examples(layout: DataLayout, type_slug: str) -> list[ExampleFile]:
    """Türün örnekleri ad sırasıyla; dizin yoksa boş. Yalnız izinli uzantılı düz dosyalar."""
    directory = layout.type_examples_dir(type_slug)
    try:
        with os.scandir(directory) as scanned:
            entries = sorted(scanned, key=lambda entry: entry.name.casefold())
    except FileNotFoundError:
        return []
    return [
        ExampleFile(entry.name, entry.stat().st_size)
        for entry in entries
        if _is_example_file(entry)
    ]


def example_path(layout: DataLayout, type_slug: str, name: str) -> Path | None:
    """Listelenen örneğin yolu; `name` listede yoksa `None`. Yol adla kurulmadan önce liste ile
    eşlenir: yükleyenin/isteğin verdiği ad dizinden çıkamaz."""
    if any(example.name == name for example in list_examples(layout, type_slug)):
        return layout.type_examples_dir(type_slug) / name
    return None


def find_example(layout: DataLayout, type_slug: str, sha256: str) -> ExampleFile | None:
    """Türün klasöründe aynı içerikli (SHA-256) örnek; yoksa `None`."""
    directory = layout.type_examples_dir(type_slug)
    for example in list_examples(layout, type_slug):
        if sha256_file(directory / example.name) == sha256:
            return example
    return None


def relocate_example(
    layout: DataLayout, type_slug: str, name: str, to_slug: str, *, expected_sha256: str
) -> StoredFile:
    """Listelenen örneği `to_slug` türünün klasörüne taşır (11.9.4); ad doluysa `-2` eki alır.
    `name` listede yoksa `FileNotFoundError`, içerik `expected_sha256` ile tutmazsa
    `ContentMismatchError` — ikisinde de hiçbir şey taşınmaz."""
    return _move(layout, type_slug, name, layout.type_examples_dir(to_slug), expected_sha256)


def archive_example(
    layout: DataLayout, type_slug: str, name: str, *, expected_sha256: str
) -> StoredFile:
    """Listelenen örneği eğitim arşivine (`_egitim/cikarilan/<tur_slug>/`) taşır; silinmez
    (11.9.4, §D58 d). Hatalar `relocate_example`'daki gibidir."""
    return _move(layout, type_slug, name, layout.training_removed_dir(type_slug), expected_sha256)


def _move(
    layout: DataLayout, type_slug: str, name: str, directory: Path, expected_sha256: str
) -> StoredFile:
    source = example_path(layout, type_slug, name)
    if source is None:
        raise FileNotFoundError(f"Örnek bulunamadı: {type_slug}/{name}")
    stored = write_unique(
        directory, source.name, iter_file_chunks(source), expected_sha256=expected_sha256
    )
    source.unlink()
    return stored


def _is_example_file(entry: os.DirEntry[str]) -> bool:
    return (
        not entry.name.startswith(".")
        and not is_partial_write(entry.name)
        and Path(entry.name).suffix.casefold() in _LISTED_SUFFIXES
        and entry.is_file(follow_symlinks=False)
    )


def _unsupported(label: str) -> ExampleRejectedError:
    return ExampleRejectedError(f"'{label}' örnek olamaz: yalnız PDF, JPEG ve PNG kabul edilir.")


def _display_name(original_name: str) -> str:
    return PurePosixPath(original_name.replace("\\", "/")).name or "adsız dosya"


def _stem(original_name: str) -> str:
    """Yüklenen adın gövdesinden dosya adı gövdesi; sadeleştirilemezse `ornek`."""
    stem = PurePosixPath(original_name.replace("\\", "/")).stem
    try:
        return slugify(stem, "-", max_length=_STEM_MAX_LENGTH)
    except SlugError:
        return _FALLBACK_STEM


def _is_readable(kind: FileKind, content: bytes) -> bool:
    if kind is FileKind.PDF:
        try:
            return len(PdfReader(BytesIO(content)).pages) > 0
        except PdfReadError:
            return False
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
            return image.format == _PILLOW_FORMATS[kind]
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        return False
