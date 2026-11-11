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
işidir; bu modül yalnız aynı türe bakar.

- **Türler:** yalnız PDF, JPEG ve PNG (K2: analiz edilenler). Tür dosya adına değil içeriğin
  imzasına bakılarak belirlenir; uzantı içeriğe göre yeniden yazılır (`.pdf`, `.jpg`, `.png`) — adı
  `.jpg` olan PDF `.pdf` olarak saklanır. İçerik okunamıyorsa (bozuk PDF/görüntü) reddedilir.
- **Ad:** yüklenen adın gövdesi `[A-Za-z0-9-]` kelimelerine sadeleştirilir (`slugify`); klasörde
  ya da dizinde varsa `-2`, `-3` eki alır. Yol parçası yükleyenden gelmez.
- **Tekrar:** türde aynı SHA-256'lı örnek varsa yeni dosya yazılmaz, var olan bildirilir.
- **İçerik değişmez** (K11, K17): baytlar olduğu gibi yazılır; yeniden kodlama, kırpma yok. Silme
  yok (K16'nın ruhu; ham dosyanın boşaltılması ayrı komuttur, 11.9.10).
- **Taşıma (11.9.4, PLAN.md §D58).** İK'nın etiket kararı örneği başka türün klasörüne
  (`relocate_example`) ya da eğitim arşivine (`archive_example`, `_egitim/cikarilan/<tur_slug>/`)
  taşır: içerik hedefe atomik yazılır (`write_unique`; ad doluysa `-2`, `-3`), SHA-256'sı
  kaydınkiyle tutmazsa hiçbir şey yayınlanmaz (`ContentMismatchError`); yayından sonra kaynak ad
  kaldırılır — kopya bırakılmaz, içerik yeni yerinde bayt bayt aynıdır (K11: yalnız taşıma).

Klasör, bu modülden önce elle yerleştirilmiş dosyaları da içerebilir; liste yalnız izinli uzantılı
düz dosyaları gösterir.

**Kalıcı örnek dizini (11.9.10; PLAN.md §D135 a, c).** Her örneğin adı, boyutu, SHA-256'sı, dosya
türü, sayfa sayısı ve önizleme anahtarı `example_index`'tedir (`ExampleIndexEntry`). Ham dosya
silinse de örnek bu kayıt ve kalıcı önizlemesiyle (`KnownDocuments/_onizlemeler/`) yaşar. Oturum
(`session`) verilen fonksiyonlar dizini okur ve yazar; verilmezse yalnız disk okunur (eski
davranış). Dizin şöyle dolar: `store_example` yazdığını, `index_example` tek bir örneği (ilk
önizleme isteğinde), `sync_example_index` bütün klasörleri (kayıtsız elle yerleştirilenler dahil)
kaydeder. Ham dosya varken liste diskten gelir, davranış değişmez; ham dosyası olmayan dizin satırı
listeye aynı ad sırasıyla `present=False` olarak girer. Tekrar tespiti (`find_example`) dizindeki
SHA-256'yı da okur: silinen örneğin içeriği yeniden yüklenince tekrar sayılır. Taşıma ve çıkarma
dizin satırını ve önizleme dosyalarını da taşır (`relocate_indexed_example`,
`archive_indexed_example`); ham dosya yoksa yalnız onları.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Collection
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath

from PIL import Image
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import ExampleIndexEntry, OriginalState, utcnow
from app.i18n import N_, Translatable
from app.storage.atomic import (
    ContentMismatchError,
    StoredFile,
    is_partial_write,
    iter_file_chunks,
    sha256_bytes,
    sha256_file,
    write_unique,
)
from app.storage.filetype import FileKind, UnsupportedFileTypeError, detect_file_kind
from app.storage.layout import DataLayout
from app.storage.pdfinfo import count_pdf_pages
from app.storage.slug import SlugError, slugify

# Kabul edilen içerik türü → saklanan uzantı.
EXAMPLE_EXTENSIONS = {FileKind.PDF: "pdf", FileKind.JPEG: "jpg", FileKind.PNG: "png"}
# Listede gösterilen uzantılar (elle yerleştirilen `.jpeg`/büyük harfli adlar dahil).
_LISTED_SUFFIXES = frozenset({".pdf", ".jpg", ".jpeg", ".png"})
_PILLOW_FORMATS = {FileKind.JPEG: "JPEG", FileKind.PNG: "PNG"}
_FALLBACK_STEM = "ornek"
_STEM_MAX_LENGTH = 80
# Önizleme anahtarı: SHA-256'nın baş kısmı (adres sürümü, ETag ve önizleme dosya adı).
PREVIEW_KEY_LENGTH = 20
# İçerik imzası okunamayan (bozuk) elle yerleştirilmiş dosyada tür uzantıdan gelir.
_KIND_BY_SUFFIX = {
    ".pdf": FileKind.PDF,
    ".jpg": FileKind.JPEG,
    ".jpeg": FileKind.JPEG,
    ".png": FileKind.PNG,
}


class ExampleRejectedError(ValueError):
    """Dosya örnek olarak kabul edilmedi; mesaj kullanıcıya gösterilir."""


@dataclass(frozen=True, slots=True)
class ExampleFile:
    """Türün bir örneği. `present` ham dosyanın klasörde olup olmadığıdır (yoksa örnek dizin kaydı
    ve önizlemesiyle yaşar, 11.9.10); `preview_key` dizindeki önizleme anahtarıdır (örnek henüz
    dizinde değilse ya da dosya değiştiyse boş)."""

    name: str
    size: int
    present: bool = True
    preview_key: str | None = None


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
        raise ExampleRejectedError(Translatable(N_("'{file}' dosyası boş."), file=label))
    if len(content) > max_bytes:
        raise ExampleRejectedError(
            Translatable(
                N_("'{file}' dosyası {limit} MB sınırını aşıyor."),
                file=label,
                limit=f"{max_bytes / (1024 * 1024):.0f}",
            )
        )
    try:
        kind = detect_file_kind(content)
    except UnsupportedFileTypeError:
        raise _unsupported(label) from None
    if kind not in EXAMPLE_EXTENSIONS:
        raise _unsupported(label)
    if not _is_readable(kind, content):
        raise ExampleRejectedError(
            Translatable(N_("'{file}' dosyası açılamadı; bozuk olabilir."), file=label)
        )
    return kind


def store_example(
    layout: DataLayout,
    type_slug: str,
    original_name: str,
    content: bytes,
    kind: FileKind,
    *,
    session: Session | None = None,
) -> StoredExample:
    """Örneği `KnownDocuments/examples/<tur_slug>/` altına yazar; `kind` `check_example`'ın
    döndüğüdür. Aynı içerik türde varsa (oturumla: ham dosyası silinmiş örnek dahil) yazmaz.
    Oturum verilirse dizindeki adlar dolu sayılır ve yazılan örnek dizine kaydedilir; commit
    etmez."""
    directory = layout.type_examples_dir(type_slug)
    sha256 = sha256_bytes(content)
    existing = find_example(layout, type_slug, sha256, session=session)
    if existing is not None:
        return StoredExample(existing.name, existing.size, sha256, duplicate=True)
    name = f"{_stem(original_name)}.{EXAMPLE_EXTENSIONS[kind]}"
    reserved = list(_index_rows(session, type_slug))
    stored = write_unique(directory, name, content, expected_sha256=sha256, reserved=reserved)
    if session is not None:
        record_example_index(
            session,
            type_slug,
            stored.path.name,
            size=stored.size,
            sha256=sha256,
            kind=kind,
            page_count=_page_count(kind, content),
        )
    return StoredExample(stored.path.name, stored.size, sha256, duplicate=False)


def list_examples(
    layout: DataLayout, type_slug: str, session: Session | None = None
) -> list[ExampleFile]:
    """Türün örnekleri ad sırasıyla; klasör yoksa boş. Yalnız izinli uzantılı düz dosyalar.
    Oturum verilirse ham dosyası klasörde olmayan dizin satırları da (`present=False`) aynı ad
    sırasına girer ve her örnek dizindeki önizleme anahtarını taşır."""
    listed = _listed_on_disk(layout, type_slug)
    if session is None:
        return listed
    rows = _index_rows(session, type_slug)
    names = {example.name for example in listed}
    examples = [
        ExampleFile(
            example.name,
            example.size,
            preview_key=_key_if_current(rows.get(example.name), example.size),
        )
        for example in listed
    ]
    examples.extend(
        ExampleFile(row.name, row.size, present=False, preview_key=row.preview_key)
        for name, row in rows.items()
        if name not in names
    )
    return sorted(examples, key=lambda example: example.name.casefold())


def find_listed_example(
    layout: DataLayout, type_slug: str, name: str, session: Session | None = None
) -> ExampleFile | None:
    """Listelenen örnek (oturumla: ham dosyası silinmiş olabilir); `name` listede yoksa `None`."""
    return next(
        (example for example in list_examples(layout, type_slug, session) if example.name == name),
        None,
    )


def example_path(layout: DataLayout, type_slug: str, name: str) -> Path | None:
    """Klasörde duran örneğin yolu; `name` klasörün listesinde yoksa (ham dosyası silinmiş örnek
    dahil) `None`. Yol adla kurulmadan önce liste ile eşlenir: yükleyenin/isteğin verdiği ad
    dizinden çıkamaz."""
    if any(example.name == name for example in _listed_on_disk(layout, type_slug)):
        return layout.type_examples_dir(type_slug) / name
    return None


class ExampleLocator:
    """Çözülmüş bir yolun bir türün örnek klasöründe (`examples/<tur_slug>/`) listelenen örnek olup
    olmadığını söyler (harita satırının yerindeki dosyası, 11.9.5). Örnekler kökü bir kez çözülür,
    her klasör bir kez listelenir: çok satırlı haritada her satırda yeniden okunmaz."""

    def __init__(self, layout: DataLayout) -> None:
        self._layout = layout
        self._examples = layout.examples.resolve()
        self._listed: dict[str, frozenset[str]] = {}

    def slug_of(self, resolved: Path) -> str | None:
        """`resolved` (sembolik bağları çözülmüş yol) listelenen bir örnekse türün slug'ı."""
        if resolved.parent.parent != self._examples:
            return None
        slug = resolved.parent.name
        names = self._listed.get(slug)
        if names is None:
            try:
                names = frozenset(example.name for example in list_examples(self._layout, slug))
            except ValueError:  # slug olamayan klasör adı
                names = frozenset()
            self._listed[slug] = names
        return slug if resolved.name in names else None


def listed_example_slug(layout: DataLayout, path: Path) -> str | None:
    """`path` bir türün örnek klasöründe listelenen örnekse türün slug'ı; değilse `None`."""
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return None
    return ExampleLocator(layout).slug_of(resolved)


def find_example(
    layout: DataLayout, type_slug: str, sha256: str, *, session: Session | None = None
) -> ExampleFile | None:
    """Türde aynı içerikli (SHA-256) örnek; yoksa `None`. Oturum verilirse dizin okunur (ham
    dosyası silinmiş örnek dahil); SHA-256 yalnız dizinde olmayan ya da değişmiş dosyalar için
    hesaplanır."""
    return next(
        (example for example, digest in _hashes(layout, type_slug, session) if digest == sha256),
        None,
    )


def example_hashes(
    layout: DataLayout, type_slug: str, session: Session | None = None
) -> dict[str, str]:
    """Türün örneklerinin SHA-256 → ad dizini (aynı içerikte ilk ad); oturumla dizin okunur."""
    hashes: dict[str, str] = {}
    for example, digest in _hashes(layout, type_slug, session):
        hashes.setdefault(digest, example.name)
    return hashes


def relocate_example(
    layout: DataLayout, type_slug: str, name: str, to_slug: str, *, expected_sha256: str
) -> StoredFile:
    """Klasördeki örneği `to_slug` türünün klasörüne taşır (11.9.4); ad doluysa `-2` eki alır.
    `name` listede yoksa `FileNotFoundError`, içerik `expected_sha256` ile tutmazsa
    `ContentMismatchError` — ikisinde de hiçbir şey taşınmaz. Yalnız diske bakar; dizinli taşıma
    `relocate_indexed_example`'dır."""
    return _move_original(
        layout, type_slug, name, layout.type_examples_dir(to_slug), expected_sha256
    )


def archive_example(
    layout: DataLayout, type_slug: str, name: str, *, expected_sha256: str
) -> StoredFile:
    """Klasördeki örneği eğitim arşivine (`_egitim/cikarilan/<tur_slug>/`) taşır; silinmez
    (11.9.4, §D58 d). Hatalar `relocate_example`'daki gibidir. Yalnız diske bakar; dizinli
    çıkarma `archive_indexed_example`'dır."""
    return _move_original(
        layout, type_slug, name, layout.training_removed_dir(type_slug), expected_sha256
    )


@dataclass(frozen=True, slots=True)
class RelocatedExample:
    """`relocate_indexed_example` sonucu: örneğin yeni türdeki adı ve taşınan ham dosya (ham dosya
    silinmişse boş)."""

    name: str
    stored: StoredFile | None


def relocate_indexed_example(
    session: Session,
    layout: DataLayout,
    type_slug: str,
    name: str,
    to_slug: str,
    *,
    expected_sha256: str,
) -> RelocatedExample:
    """Örneği `to_slug` türüne taşır (11.9.4, 11.9.10): ham dosya (varsa) `relocate_example` gibi
    taşınır, dizin satırı ve önizleme dosyaları yeni türe geçer. Yeni ad klasörde ve dizinde
    boştur (doluysa `-2`). Örnek ne klasörde ne dizinde varsa `FileNotFoundError`, içerik
    `expected_sha256` değilse `ContentMismatchError` — ikisinde de hiçbir şey taşınmaz. Commit
    etmez."""
    row = _active_row(session, layout, type_slug, name, expected_sha256)
    target = layout.type_examples_dir(to_slug)
    reserved = list(_index_rows(session, to_slug))
    stored = None
    if example_path(layout, type_slug, name) is not None:
        stored = _move_original(layout, type_slug, name, target, expected_sha256, reserved=reserved)
        new_name = stored.path.name
    else:
        new_name = _free_name(target, name, reserved)
    _move_previews(session, layout.preview_dir(type_slug), layout.preview_dir(to_slug), row)
    row.type_slug = to_slug
    row.name = new_name
    session.flush()
    return RelocatedExample(new_name, stored)


def archive_indexed_example(
    session: Session,
    layout: DataLayout,
    type_slug: str,
    name: str,
    *,
    expected_sha256: str,
) -> StoredFile | None:
    """Örneği örneklerden çıkarır (11.9.4, 11.9.10): ham dosya (varsa) `archive_example` gibi
    eğitim arşivine taşınır, dizin satırı çıkarıldı olarak işaretlenir (`archived_at`) ve
    önizlemeleri `_onizlemeler/_cikarilan/<tur_slug>/`'a geçer. Dönen değer taşınan ham dosyadır
    (ham dosya silinmişse `None`). Hatalar `relocate_indexed_example`'daki gibidir. Commit etmez."""
    row = _active_row(session, layout, type_slug, name, expected_sha256)
    stored = None
    if example_path(layout, type_slug, name) is not None:
        stored = archive_example(layout, type_slug, name, expected_sha256=expected_sha256)
    _move_previews(
        session, layout.preview_dir(type_slug), layout.archived_preview_dir(type_slug), row
    )
    row.archived_at = utcnow()
    session.flush()
    return stored


def _move_original(
    layout: DataLayout,
    type_slug: str,
    name: str,
    directory: Path,
    expected_sha256: str,
    *,
    reserved: Collection[str] = (),
) -> StoredFile:
    source = example_path(layout, type_slug, name)
    if source is None:
        raise FileNotFoundError(f"Örnek bulunamadı: {type_slug}/{name}")
    stored = write_unique(
        directory,
        source.name,
        iter_file_chunks(source),
        expected_sha256=expected_sha256,
        reserved=reserved,
    )
    source.unlink()
    return stored


# --- kalıcı örnek dizini (11.9.10) ------------------------------------------------------------


def example_preview_key(sha256: str) -> str:
    """Örneğin önizleme anahtarı: içeriğin SHA-256'sından (adından ya da zamanından değil)."""
    return sha256[:PREVIEW_KEY_LENGTH]


def removed_entry(session: Session, type_slug: str, name: str) -> ExampleIndexEntry | None:
    """Ham dosyası silinmiş (`removed`) örneğin dizin satırı; yoksa `None`."""
    row = index_entry(session, type_slug, name)
    if row is None or row.original_state != OriginalState.REMOVED.value:
        return None
    return row


def index_entry(session: Session, type_slug: str, name: str) -> ExampleIndexEntry | None:
    """Türün `name` adlı (çıkarılmamış) dizin satırı; yoksa `None`."""
    return session.scalar(
        select(ExampleIndexEntry).where(
            ExampleIndexEntry.type_slug == type_slug,
            ExampleIndexEntry.name == name,
            ExampleIndexEntry.archived_at.is_(None),
        )
    )


def record_example_index(
    session: Session,
    type_slug: str,
    name: str,
    *,
    size: int,
    sha256: str,
    kind: FileKind | str,
    page_count: int | None,
) -> ExampleIndexEntry:
    """Ham dosyası klasörde olan örneğin dizin satırını yazar ya da günceller; commit etmez.
    Aynı satırı eşzamanlı başka bir işlem açtıysa onunki güncellenir."""
    values = {
        "size": size,
        "sha256": sha256,
        "file_kind": str(kind),
        "page_count": page_count,
        "preview_key": example_preview_key(sha256),
        "original_state": OriginalState.PRESENT.value,
        "removed_at": None,
    }
    row = index_entry(session, type_slug, name)
    if row is None:
        row = ExampleIndexEntry(type_slug=type_slug, name=name, **values)
        try:
            with session.begin_nested():
                session.add(row)
            return row
        except IntegrityError:
            row = index_entry(session, type_slug, name)
            if row is None:
                raise
    for field, value in values.items():
        setattr(row, field, value)
    session.flush()
    return row


def index_example(
    session: Session, layout: DataLayout, type_slug: str, name: str
) -> ExampleIndexEntry | None:
    """Listelenen örneğin dizin satırı. Ham dosya klasördeyse ve satır yoksa ya da boyutu
    tutmuyorsa dosya okunup satır yazılır (SHA-256, tür, sayfa sayısı); ham dosya yoksa var olan
    satır döner. Örnek ne klasörde ne dizinde varsa `None`. Commit etmez."""
    row = index_entry(session, type_slug, name)
    path = example_path(layout, type_slug, name)
    if path is None:
        return row
    try:
        size = path.stat().st_size
        if (
            row is not None
            and row.size == size
            and row.original_state == OriginalState.PRESENT.value
        ):
            return row
        content = path.read_bytes()
    except FileNotFoundError:  # listeleme ile okuma arasında kalktı
        return row
    kind = _content_kind(path.name, content)
    return record_example_index(
        session,
        type_slug,
        name,
        size=len(content),
        sha256=sha256_bytes(content),
        kind=kind,
        page_count=_page_count(kind, content),
    )


@dataclass(frozen=True, slots=True)
class IndexSync:
    """`sync_example_index` sonucu: taranan tür, klasörde duran örnek, yazılan ya da güncellenen
    satır ve ham dosyası artık olmadığı için `removed` işaretlenen satır sayıları."""

    types: int
    present: int
    indexed: int
    removed: int


def sync_example_index(
    session: Session,
    layout: DataLayout,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> IndexSync:
    """Dizini diskle eşitler (PLAN.md §D135 a, d): klasörde duran ama dizinde olmayan ya da
    boyutu değişen örnek (elle yerleştirilen kayıtsız dosyalar dahil) okunup yazılır; dizinde
    `present` görünen ama ham dosyası olmayan satır `removed` olur (`removed_at`). Dosyalara
    dokunulmaz; ikinci koşu hiçbir şey değiştirmez. `progress(i, n)` okunan her dosyadan sonra
    çağrılır. Commit etmez."""
    rows: dict[str, dict[str, ExampleIndexEntry]] = {}
    for row in session.scalars(
        select(ExampleIndexEntry).where(ExampleIndexEntry.archived_at.is_(None))
    ):
        rows.setdefault(row.type_slug, {})[row.name] = row
    slugs = sorted(set(example_slugs(layout)) | set(rows))
    pending: list[tuple[str, str]] = []
    present = 0
    removed = 0
    for slug in slugs:
        listed = {example.name: example for example in _listed_on_disk(layout, slug)}
        present += len(listed)
        indexed = rows.get(slug, {})
        for name, example in listed.items():
            row = indexed.get(name)
            if (
                row is None
                or row.size != example.size
                or row.original_state != OriginalState.PRESENT.value
            ):
                pending.append((slug, name))
        for name, row in indexed.items():
            if name not in listed and row.original_state == OriginalState.PRESENT.value:
                mark_original_removed(row)
                removed += 1
    written = 0
    for number, (slug, name) in enumerate(pending, start=1):
        if index_example(session, layout, slug, name) is not None:
            written += 1
        if progress is not None:
            progress(number, len(pending))
    session.flush()
    return IndexSync(types=len(slugs), present=present, indexed=written, removed=removed)


def mark_original_removed(row: ExampleIndexEntry) -> None:
    """Satırın ham dosyası silindi: örnek bundan sonra dizin kaydı ve önizlemesiyle yaşar."""
    row.original_state = OriginalState.REMOVED.value
    row.removed_at = utcnow()


def example_slugs(layout: DataLayout) -> list[str]:
    """`examples/` altındaki tür klasörleri (slug olabilen adlar, ad sırasıyla)."""
    try:
        with os.scandir(layout.examples) as scanned:
            names = [entry.name for entry in scanned if entry.is_dir(follow_symlinks=False)]
    except FileNotFoundError:
        return []
    slugs = []
    for name in sorted(names):
        try:
            layout.type_examples_dir(name)
        except ValueError:
            continue
        slugs.append(name)
    return slugs


def indexed_slugs(session: Session) -> list[str]:
    """Dizinde çıkarılmamış satırı olan türler (klasörü boşalmış olsa da)."""
    return sorted(
        session.scalars(
            select(ExampleIndexEntry.type_slug)
            .where(ExampleIndexEntry.archived_at.is_(None))
            .distinct()
        )
    )


def _listed_on_disk(layout: DataLayout, type_slug: str) -> list[ExampleFile]:
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


def _index_rows(session: Session | None, type_slug: str) -> dict[str, ExampleIndexEntry]:
    if session is None:
        return {}
    return {
        row.name: row
        for row in session.scalars(
            select(ExampleIndexEntry).where(
                ExampleIndexEntry.type_slug == type_slug, ExampleIndexEntry.archived_at.is_(None)
            )
        )
    }


def _hashes(
    layout: DataLayout, type_slug: str, session: Session | None
) -> list[tuple[ExampleFile, str]]:
    rows = _index_rows(session, type_slug)
    directory = layout.type_examples_dir(type_slug)
    found: list[tuple[ExampleFile, str]] = []
    for example in list_examples(layout, type_slug, session):
        row = rows.get(example.name)
        if row is not None and (not example.present or row.size == example.size):
            found.append((example, row.sha256))
            continue
        try:
            found.append((example, sha256_file(directory / example.name)))
        except FileNotFoundError:  # listeleme ile okuma arasında kalktı
            continue
    return found


def _key_if_current(row: ExampleIndexEntry | None, size: int) -> str | None:
    """Klasördeki dosyanın dizin anahtarı; satır yoksa ya da boyut tutmuyorsa (dosya değişti)
    `None`."""
    if row is None or row.size != size:
        return None
    return row.preview_key


def _active_row(
    session: Session, layout: DataLayout, type_slug: str, name: str, expected_sha256: str
) -> ExampleIndexEntry:
    """Taşınacak örneğin dizin satırı (gerekirse diskten yazılır). Ham dosya klasörde değilse
    satır ancak ham dosyası silinmiş (`removed`) olarak işaretliyse yerine geçer — beklenmedik
    kaybolan dosya taşınmaz. Örnek yoksa `FileNotFoundError`, dizindeki içerik `expected_sha256`
    değilse `ContentMismatchError`; ikisinde de hiçbir şey taşınmaz."""
    row = index_example(session, layout, type_slug, name)
    if row is None or (
        example_path(layout, type_slug, name) is None
        and row.original_state != OriginalState.REMOVED.value
    ):
        raise FileNotFoundError(f"Örnek bulunamadı: {type_slug}/{name}")
    if row.sha256 != expected_sha256:
        raise ContentMismatchError(f"Örnek içeriği kaydındaki SHA-256 ile tutmuyor: {type_slug}")
    return row


def _move_previews(session: Session, source: Path, target: Path, row: ExampleIndexEntry) -> None:
    """Satırın önizleme dosyalarını `source`'tan `target`'a taşır. Aynı içerikli başka bir örnek
    kaynak türde kalıyorsa (aynı anahtar) dosyalar kopyalanır, yerinde de kalır."""
    shared = session.scalar(
        select(ExampleIndexEntry.id).where(
            ExampleIndexEntry.type_slug == row.type_slug,
            ExampleIndexEntry.preview_key == row.preview_key,
            ExampleIndexEntry.archived_at.is_(None),
            ExampleIndexEntry.id != row.id,
        )
    )
    for preview in sorted(source.glob(f"{row.preview_key}-*.jpg")):
        target.mkdir(parents=True, exist_ok=True)
        destination = target / preview.name
        if shared is not None:
            if not destination.exists():
                shutil.copyfile(preview, destination)
        elif destination.exists():  # aynı içerik hedefte zaten önizlenmiş
            preview.unlink()
        else:
            os.replace(preview, destination)


def _free_name(directory: Path, name: str, reserved: Collection[str]) -> str:
    """`write_unique`'in seçeceği ad (yazmadan): `name` ya da ilk boş `gövde-2.uzantı`…"""
    try:
        with os.scandir(directory) as entries:
            taken = {entry.name.casefold() for entry in entries}
    except FileNotFoundError:
        taken = set()
    taken |= {item.casefold() for item in reserved}
    suffix = PurePosixPath(name).suffix
    stem = name.removesuffix(suffix)
    number = 1
    candidate = name
    while candidate.casefold() in taken:
        number += 1
        candidate = f"{stem}-{number}{suffix}"
    return candidate


def _content_kind(name: str, content: bytes) -> FileKind:
    try:
        kind = detect_file_kind(content)
    except UnsupportedFileTypeError:
        kind = None
    if kind is not None and kind in EXAMPLE_EXTENSIONS:
        return kind
    return _KIND_BY_SUFFIX.get(Path(name).suffix.casefold(), FileKind.PDF)


def _page_count(kind: FileKind, content: bytes) -> int | None:
    if kind is FileKind.PDF:
        return count_pdf_pages(content)
    return 1


def _is_example_file(entry: os.DirEntry[str]) -> bool:
    return (
        not entry.name.startswith(".")
        and not is_partial_write(entry.name)
        and Path(entry.name).suffix.casefold() in _LISTED_SUFFIXES
        and entry.is_file(follow_symlinks=False)
    )


def _unsupported(label: str) -> ExampleRejectedError:
    return ExampleRejectedError(
        Translatable(N_("'{file}' örnek olamaz: yalnız PDF, JPEG ve PNG kabul edilir."), file=label)
    )


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
        # Sahip parolalı (AES) PDF parolasız okunur ve örnek olabilir; sayım onda çökmez.
        return (count_pdf_pages(content) or 0) > 0
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
            return image.format == _PILLOW_FORMATS[kind]
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        return False
