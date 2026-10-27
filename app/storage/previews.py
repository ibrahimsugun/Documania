"""Örnek önizlemeleri (PRD 11.9.7; PLAN.md §D130) — `cache/previews/<tur_slug>/`.

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

from app.pipeline.render import RenderError, render_pdf_images
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
    target = layout.preview_path(type_slug, key, size)
    if target.is_file():
        return Preview(key, target)
    with _render_turn(target, wait=wait):
        if target.is_file():  # beklerken başka istek üretti
            return Preview(key, target)
        long_edge, quality = PREVIEW_SIZES[size]
        try:
            content = _render(source, long_edge, quality)
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


def _render(source: Path, long_edge: int, quality: int) -> bytes:
    if source.suffix.casefold() == ".pdf":
        try:
            images, _ = render_pdf_images(
                source.read_bytes(),
                dpi=_PDF_DPI,
                max_long_edge=long_edge,
                jpeg_quality=quality,
                max_pages=1,
            )
        except (RenderError, OSError, RuntimeError) as exc:
            raise PreviewError(str(exc)) from exc
        if not images:
            raise PreviewError("PDF'te sayfa yok.")
        return images[0]
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
