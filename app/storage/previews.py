"""Belge önizlemeleri (PRD 11.9.7, 11.9.9; PLAN.md §D130, §D132) — `cache/previews/`.

Eğitim ve katalog sayfaları örneği orijinal dosya olarak değil, bir kez üretilip saklanan küçük
JPEG olarak gösterir: liste küçük resmi (`small`, uzun kenar 320 px) ve ada tıklayınca açılan büyük
önizleme (`large`, 1280 px; PDF'de ilk sayfa, `app.pipeline.render` çizicisiyle).

- **Belge değil gösterim önbelleğidir** (`cache/pages` gibi): orijinal hiç yazılmaz, bayt bayt aynı
  kalır (K10, K11). Önizleme kaynaktan yeniden üretilir; yedeğe girmez (`scripts/backup.sh`).
- **Anahtar** örneğin adından, boyutundan ve değişme zamanından türer (`preview_key`): örnek
  değişirse önizlemenin adı ve adresi de değişir, tarayıcı eskisini uzun önbellekte tutabilir.
- **Yol istekteki addan kurulmaz:** ad önce türün örnek listesinde aranır (`example_path`).
- **Güvenlik:** görüntü Pillow ile açılır; piksel sınırı (`PREVIEW_MAX_PIXELS`) ve Pillow'un
  sıkıştırma bombası uyarısı hata sayılır. Çıktı yalnız yeniden kodlanmış JPEG'dir: EXIF, GPS ve
  ICC taşımaz (yalnız EXIF yönelimi fiziksel olarak uygulanır). Üretilemeyen örnekte önizleme yoktur
  (`Preview.path` boş): çağıran yer tutucu gösterir, İndir çalışmaya devam eder.
- **Atomik yazım** (`replace_file`): okuyan her an ya tam önizlemeyi görür ya hiç görmez.
- **Sınırlı üretim** (11.9.8; PLAN.md §D131 e): aynı anda en çok `RENDER_SLOTS` önizleme üretilir;
  aynı önizlemeyi isteyen eşzamanlı istekler tek üretimi paylaşır (önizleme başına kilit). Ön
  yükleme beklemez (`wait=False`): yer ya da kilit doluysa `PreviewBusy` alır, uç `503` döner.
- **Genel kaynak** (11.9.9; PLAN.md §D132 a): örnek dışındaki her belge kaynağı (çalışan belgesi,
  yükleme sayfası, üretilen belge, şablon sayfası, profil fotoğrafı) bir `PreviewSource`'tur —
  kaynak türü, kimlik, dosya ve 0 tabanlı sayfa. `ensure_source_preview` örnekle aynı üretimi,
  sınırı ve kilidi kullanır; çıktı `cache/previews/<kaynak-turu>/`'na yazılır. Yolu ve yetkiyi
  çağıran uç kendi kaydından çözer; bu modül yalnız verilen dosyayı okur. Önizleme sayfa sayfadır:
  PDF'in yalnız istenen sayfası çizilir, en çok `PREVIEW_MAX_PAGES` sayfa önizlenir (gerisi İndir).
"""

from __future__ import annotations

import hashlib
import os
import threading
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from app.pipeline.render import RenderError, pdf_page_count, render_pdf_page_image
from app.storage.atomic import replace_file
from app.storage.examples import example_path, list_examples
from app.storage.layout import DataLayout

# Boyut adı → (uzun kenar px, JPEG kalitesi).
PREVIEW_SIZES = {"small": (320, 70), "large": (1280, 80)}
# Bu kadar pikselden büyük görüntünün önizlemesi üretilmez (çözülmeden, başlıktan ölçülür).
PREVIEW_MAX_PIXELS = 50_000_000
# PDF ilk sayfası bu çözünürlükte, uzun kenar boyut sınırına küçültülerek çizilir.
_PDF_DPI = 200
_KEY_LENGTH = 20
_PLACEHOLDER_SIDE = 320
# Çok sayfalı belgede önizlenen en çok sayfa (gerisi yalnız İndir ile; 11.9.9).
PREVIEW_MAX_PAGES = 20
_PDF_MAGIC = b"%PDF-"
# Aynı anda üretilen önizleme sayısının üst sınırı (Pillow/PDF çizimi CPU ve bellek ister).
RENDER_SLOTS = 2

_slots = threading.BoundedSemaphore(RENDER_SLOTS)
_locks_guard = threading.Lock()
# Önizleme yolu → (kilit, bekleyen sayısı); son kullanan kaydı siler.
_locks: dict[Path, tuple[threading.Lock, int]] = {}


class PreviewError(ValueError):
    """Örneğin önizlemesi üretilemedi (bozuk, çok büyük ya da desteklenmeyen dosya)."""


class PreviewBusy(RuntimeError):
    """Üretim yerleri dolu ya da aynı önizleme şu an üretiliyor; bekleme istenmedi (ön yükleme)."""


@dataclass(frozen=True, slots=True)
class Preview:
    """Listelenen örneğin önizlemesi: `key` adresin ve `ETag`'in sürümüdür; `path` boşsa önizleme
    üretilemedi (yer tutucu gösterilir)."""

    key: str
    path: Path | None


def preview_key(path: Path) -> str:
    """Örneğin adı, boyutu ve değişme zamanından türeyen anahtar (içerik okunmaz)."""
    stat = path.stat()
    state = f"{path.name}\0{stat.st_size}\0{stat.st_mtime_ns}"
    return hashlib.sha256(state.encode("utf-8")).hexdigest()[:_KEY_LENGTH]


@dataclass(frozen=True, slots=True)
class PreviewSource:
    """Önizlenecek belge kaynağı (11.9.9): `kind` önbellek dizini (tire taşır,
    `DataLayout.source_preview_path`), `ident` kaynağın kaydındaki kimliği, `path` uçun kendi
    kaydından çözdüğü dosya, `page` 0 tabanlı sayfa."""

    kind: str
    ident: str
    path: Path
    page: int = 0

    def key(self) -> str:
        """Kaynak türü, kimlik, sayfa ve dosyanın adı/boyutu/değişme zamanından türeyen anahtar;
        dosya değişirse adres de değişir. Dosya yoksa `OSError`."""
        stat = self.path.stat()
        state = "\0".join(
            (
                self.kind,
                self.ident,
                str(self.page),
                self.path.name,
                str(stat.st_size),
                str(stat.st_mtime_ns),
            )
        )
        return hashlib.sha256(state.encode("utf-8")).hexdigest()[:_KEY_LENGTH]


def is_pdf(path: Path) -> bool:
    """Dosya PDF mi: uzantıdan ya da (uzantısız saklanan yüklemede) ilk baytlardan."""
    if path.suffix.casefold() == ".pdf":
        return True
    try:
        with path.open("rb") as handle:
            return handle.read(len(_PDF_MAGIC)) == _PDF_MAGIC
    except OSError:
        return False


def document_page_count(path: Path) -> int:
    """Belgenin sayfa sayısı: PDF'te gerçek sayı, görüntüde 1. Açılamayan PDF'te 1 (ilk sayfa yer
    tutucuyla gösterilir, İndir çalışır). Önizlenen en çok `PREVIEW_MAX_PAGES` sayfadır."""
    if not is_pdf(path):
        return 1
    try:
        return max(1, pdf_page_count(path.read_bytes()))
    except (RenderError, OSError, RuntimeError):
        return 1


def ensure_preview(
    layout: DataLayout, type_slug: str, name: str, size: str, *, wait: bool = True
) -> Preview | None:
    """Örneğin `size` boyutlu önizlemesi; yoksa üretir. `name` türün örnek listesinde yoksa ya da
    boyut tanımsızsa `None` (çağıran 404 döner). `wait=False` iken üretim hemen başlayamıyorsa
    `PreviewBusy` (var olan önizleme her zaman beklemeden döner)."""
    if size not in PREVIEW_SIZES:
        return None
    source = example_path(layout, type_slug, name)
    if source is None:
        return None
    key = preview_key(source)
    return _ensure(source, 0, key, layout.preview_path(type_slug, key, size), size, wait=wait)


def ensure_source_preview(
    layout: DataLayout, source: PreviewSource, size: str, *, wait: bool = True
) -> Preview | None:
    """`source`'un `size` boyutlu önizlemesi; yoksa üretir (11.9.9). Boyut tanımsızsa, sayfa
    önizleme sınırının dışındaysa ya da dosya yoksa `None` (çağıran 404 döner). Sayfa belgede
    yoksa ya da dosya üretilemiyorsa `Preview.path` boştur (yer tutucu). `wait` `ensure_preview`
    gibidir."""
    if size not in PREVIEW_SIZES or not 0 <= source.page < PREVIEW_MAX_PAGES:
        return None
    try:
        key = source.key()
    except OSError:
        return None
    target = layout.source_preview_path(source.kind, key, size)
    return _ensure(source.path, source.page, key, target, size, wait=wait)


def _ensure(source: Path, page: int, key: str, target: Path, size: str, *, wait: bool) -> Preview:
    if target.is_file():
        return Preview(key, target)
    with _render_turn(target, wait=wait):
        if target.is_file():  # beklerken başka istek üretti
            return Preview(key, target)
        long_edge, quality = PREVIEW_SIZES[size]
        try:
            content = (
                _render(source, long_edge, quality)
                if page == 0
                else _render(source, long_edge, quality, page=page)
            )
        except PreviewError:
            return Preview(key, None)
        target.parent.mkdir(parents=True, exist_ok=True)
        replace_file(target, content)
    return Preview(key, target)


@contextmanager
def _render_turn(target: Path, *, wait: bool) -> Iterator[None]:
    """`target`'ın kilidi ve bir üretim yeri; `wait=False` iken biri boş değilse `PreviewBusy`."""
    with _locks_guard:
        lock, users = _locks.get(target, (threading.Lock(), 0))
        _locks[target] = (lock, users + 1)
    try:
        if not lock.acquire(blocking=wait):
            raise PreviewBusy(target.name)
        try:
            if not _slots.acquire(blocking=wait):
                raise PreviewBusy(target.name)
            try:
                yield
            finally:
                _slots.release()
        finally:
            lock.release()
    finally:
        with _locks_guard:
            lock, users = _locks[target]
            if users == 1:
                del _locks[target]
            else:
                _locks[target] = (lock, users - 1)


def warm_previews(layout: DataLayout) -> dict[str, int]:
    """Bütün türlerin bütün örneklerinin iki önizlemesini üretir (toplu ısıtma). Var olan atlanır;
    durdurulan koşu yeniden çalışınca kaldığı yerden sürer. Sonuç: `created`, `existing`,
    `failed` sayıları."""
    counts = {"created": 0, "existing": 0, "failed": 0}
    try:
        slugs = sorted(entry.name for entry in os.scandir(layout.examples) if entry.is_dir())
    except FileNotFoundError:
        return counts
    for slug in slugs:
        try:
            examples = list_examples(layout, slug)
        except ValueError:  # yol parçası olamayan dizin adı (elle açılmış)
            continue
        for example in examples:
            for size in PREVIEW_SIZES:
                source = example_path(layout, slug, example.name)
                if source is None:
                    continue
                if layout.preview_path(slug, preview_key(source), size).is_file():
                    counts["existing"] += 1
                    continue
                preview = ensure_preview(layout, slug, example.name, size)
                counts["created" if preview is not None and preview.path else "failed"] += 1
    return counts


@lru_cache(maxsize=1)
def placeholder_jpeg() -> bytes:
    """Önizlemesi üretilemeyen örneğin yer tutucusu: düz gri JPEG."""
    buffer = BytesIO()
    Image.new("RGB", (_PLACEHOLDER_SIDE, _PLACEHOLDER_SIDE), (229, 231, 235)).save(
        buffer, "JPEG", quality=70
    )
    return buffer.getvalue()


def _render(source: Path, long_edge: int, quality: int, *, page: int = 0) -> bytes:
    if is_pdf(source):
        try:
            image, _ = render_pdf_page_image(
                source.read_bytes(),
                page,
                dpi=_PDF_DPI,
                max_long_edge=long_edge,
                jpeg_quality=quality,
            )
        except (RenderError, OSError, RuntimeError) as exc:
            raise PreviewError(str(exc)) from exc
        return image
    if page != 0:
        raise PreviewError("Görüntü dosyası tek sayfadır.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            return _render_image(source, long_edge, quality)
    except (
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise PreviewError(str(exc)) from exc


def _render_image(source: Path, long_edge: int, quality: int) -> bytes:
    with Image.open(source) as opened:
        if opened.width * opened.height > PREVIEW_MAX_PIXELS:
            raise PreviewError("Görüntü önizleme piksel sınırını aşıyor.")
        opened.draft("RGB", (long_edge, long_edge))
        image = ImageOps.exif_transpose(opened)
        if image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info:
            rgba = image.convert("RGBA")
            image = Image.new("RGB", rgba.size, (255, 255, 255))
            image.paste(rgba, mask=rgba.getchannel("A"))
        else:
            image = image.convert("RGB")
        image.thumbnail((long_edge, long_edge))
        buffer = BytesIO()
        # `exif`/`icc_profile` verilmez: yeniden kodlanan JPEG metaveri taşımaz.
        image.save(buffer, "JPEG", quality=quality, optimize=True)
        return buffer.getvalue()
