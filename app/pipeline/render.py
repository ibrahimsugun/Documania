"""Sayfa üretimi — PDF sayfa görüntüsü (PRD 02.1.1).

Inbox'taki PDF'in her sayfası analiz için `cache/pages/<file_id>/<sayfa>.jpg` olarak render
edilir (§8.2). Ölçek iki yapılandırma değerinden gelir:

- `PAGE_RENDER_DPI` — sayfa bu çözünürlükte render edilir.
- `PAGE_RENDER_MAX_LONG_EDGE_PX` — o çözünürlükte görüntünün uzun kenarı sınırı aşacaksa ölçek,
  uzun kenar sınıra oturacak kadar küçültülür. Küçültme render ölçeğine uygulanır: sayfa
  doğrudan hedef boyutta rasterleştirilir. Önce büyük görüntü üretip sonra yeniden örneklemek
  aynı piksel boyutunu daha çok bellekle ve ikinci bir örnekleme adımıyla verirdi.

Görüntü yalnız analiz kopyasıdır, çıktı belge değildir. Orijinal PDF'e dokunulmaz (K10); en-boy
oranı korunur, sayfa kırpılmaz, PDF'in kendi `/Rotate` değeri dışında döndürülmez, içerik
değiştirilmez (K11). Önbellek türev veridir: aynı dosya yeniden render edilirse görüntüler
atomik olarak yeniden üretilir.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Page, UploadFile
from app.events import EventType, event_context, record_event
from app.storage import (
    DataLayout,
    FileKind,
    UnsupportedFileTypeError,
    detect_file_kind,
    replace_file,
)

POINTS_PER_INCH = 72


class RenderError(ValueError):
    """Dosyadan sayfa görüntüsü üretilemiyor: PDF değil, bozuk, parolalı veya sayfasız."""


@dataclass(frozen=True)
class RenderedPage:
    """Üretilen analiz görüntüsü; uzun kenar sınırı devreye girerse `dpi` ayardan düşüktür."""

    index: int
    path: Path
    width: int
    height: int
    dpi: float


def render_scale(page_rect: pymupdf.Rect, dpi: int, max_long_edge: int) -> float:
    """Sayfa noktasını piksele çeviren ölçek: `dpi`, gerekirse uzun kenar sınırına küçültülmüş."""
    if dpi <= 0 or max_long_edge <= 0:
        raise ValueError("DPI ve uzun kenar sınırı pozitif olmalı")
    long_side = max(page_rect.width, page_rect.height)
    if long_side <= 0:
        raise RenderError("Sayfa boyutu geçersiz.")
    scale = dpi / POINTS_PER_INCH
    if long_side * scale > max_long_edge:
        scale = max_long_edge / long_side
    # MuPDF piksel kutusunu dışa yuvarlar; kayan nokta artığı sınırı bir piksel aşmasın.
    while (long_px := _long_edge_px(page_rect, scale)) > max_long_edge:
        scale *= (max_long_edge - 0.5) / long_px
    return scale


def render_pdf_pages(
    source: Path,
    layout: DataLayout,
    file_id: int,
    *,
    dpi: int,
    max_long_edge: int,
    jpeg_quality: int,
) -> list[RenderedPage]:
    """`source` PDF'inin her sayfasını `layout.page_image_path(file_id, i)` altına JPEG yazar."""
    content = source.read_bytes()
    try:
        kind = detect_file_kind(content)
    except UnsupportedFileTypeError:
        kind = None
    # MuPDF, `filetype="pdf"` verilse de JPEG/PNG baytlarını tek sayfalık belge olarak açar;
    # tür bu yüzden önce içerik imzasından denetlenir.
    if kind is not FileKind.PDF:
        raise RenderError("Dosya PDF değil; sayfa görüntüsü yalnız PDF için üretilir.")
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except RuntimeError as exc:
        raise RenderError("PDF açılamadı; dosya bozuk olabilir.") from exc

    rendered: list[RenderedPage] = []
    with document:
        if document.needs_pass:
            raise RenderError("PDF parola korumalı; sayfa görüntüsü üretilemez.")
        if document.page_count == 0:
            raise RenderError("PDF'te sayfa yok.")
        for page in document:
            scale = render_scale(page.rect, dpi, max_long_edge)
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            path = layout.page_image_path(file_id, page.number)
            replace_file(path, pixmap.tobytes("jpeg", jpg_quality=jpeg_quality))
            rendered.append(
                RenderedPage(
                    index=page.number,
                    path=path,
                    width=pixmap.width,
                    height=pixmap.height,
                    dpi=scale * POINTS_PER_INCH,
                )
            )
    return rendered


def render_upload_file(
    session: Session, layout: DataLayout, settings: Settings, upload_file: UploadFile
) -> list[Page]:
    """Yüklenmiş PDF'in sayfalarını render eder; `pages` satırlarını ve `page_count`'u yazar.

    Her sayfa için `PAGE_RENDERED` olayı dosya ve sayfa sırasına bağlı yazılır (K15). Yeniden
    çalıştırmada var olan `Page` satırı güncellenir, yenisi açılmaz; sayfanın diğer alanlarına
    dokunulmaz. Oturum commit edilmez — işlem sınırı çağıranındır.
    """
    rendered = render_pdf_pages(
        layout.resolve(upload_file.stored_path),
        layout,
        upload_file.id,
        dpi=settings.page_render_dpi,
        max_long_edge=settings.page_render_max_long_edge_px,
        jpeg_quality=settings.page_render_jpeg_quality,
    )
    existing = {page.index: page for page in upload_file.pages}
    pages: list[Page] = []
    with event_context(upload_id=upload_file.upload_id, file_id=upload_file.id):
        for item in rendered:
            page = existing.get(item.index)
            if page is None:
                page = Page(file=upload_file, index=item.index)
                session.add(page)
            page.image_path = item.path.relative_to(layout.root).as_posix()
            record_event(
                session,
                EventType.PAGE_RENDERED,
                page_index=item.index,
                data={
                    "image_path": page.image_path,
                    "width": item.width,
                    "height": item.height,
                    "dpi": round(item.dpi, 2),
                },
            )
            pages.append(page)
        upload_file.page_count = len(rendered)
        session.flush()
    return pages


def _long_edge_px(page_rect: pymupdf.Rect, scale: float) -> int:
    pixel_box = (page_rect * pymupdf.Matrix(scale, scale)).irect
    return max(pixel_box.width, pixel_box.height)
