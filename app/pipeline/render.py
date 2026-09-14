"""Sayfa üretimi — PDF sayfa görüntüsü (PRD 02.1.1), metin katmanı (PRD 02.2.1) ve görüntü
dosyaları için analiz kopyası (PRD 02.3.1).

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

Metin katmanı çıkarma yalnız PDF'in kendi gömülü metin nesnelerini okur (OCR yapmaz, içerik
üretmez — K11). Metin katmanı olmayan (taranmış) sayfada `text_layer` boş (`None`) kalır.

Görüntü dosyası (JPEG/PNG) analiz kopyası yalnız EXIF yönelim etiketini fiziksel olarak
uygular (Pillow `ImageOps.exif_transpose` — K11'in izin verdiği tek Pillow kullanımı: ölçme/
EXIF/biçim, düzenleme değil). Kopya kaynağın kendi biçiminde `cache/pages/<file_id>/0000.<uzantı>`
altına yazılır; orijinal dosyaya dokunulmaz (K10).

Boş sayfa tespiti (02.4.1) PDF'in kendi içerik nesnelerine bakar: metin katmanı, gömülü görüntü
ve çizim üçü de yoksa sayfa boştur. OCR veya piksel analizi yapılmaz (K11); boş sayfa hata
sayılmaz, yalnız `pages.is_blank` alanına işaretlenir ve `PAGE_BLANK` olayı yazılır.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps
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

# 02.3.1: analiz kopyası kaynağın kendi biçimini korur — PDF render'ının aksine JPEG'e
# dönüştürülmez (PNG şeffaflığı/kaybı gibi bir dönüşüm kararı gerektirmez).
_IMAGE_COPY_EXTENSIONS: dict[FileKind, str] = {FileKind.JPEG: "jpg", FileKind.PNG: "png"}


class RenderError(ValueError):
    """Dosyadan sayfa görüntüsü üretilemiyor: PDF değil, bozuk, parolalı veya sayfasız."""


@dataclass(frozen=True)
class RenderedPage:
    """Üretilen analiz görüntüsü; uzun kenar sınırı devreye girerse `dpi` ayardan düşüktür.

    Görüntü dosyası analiz kopyalarında (02.3.1) ölçek kavramı yok — `dpi` `None` kalır.
    """

    index: int
    path: Path
    width: int
    height: int
    dpi: float | None = None


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


@contextmanager
def _open_pdf(content: bytes) -> Iterator[pymupdf.Document]:
    """`content`'i PDF olarak açar; tür/bozukluk/parola/sayfa sayısı burada denetlenir."""
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
    with document:
        if document.needs_pass:
            raise RenderError("PDF parola korumalı; sayfa görüntüsü üretilemez.")
        if document.page_count == 0:
            raise RenderError("PDF'te sayfa yok.")
        yield document


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
    rendered: list[RenderedPage] = []
    with _open_pdf(content) as document:
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


def extract_page_text(page: pymupdf.Page) -> str | None:
    """Sayfanın gömülü metin katmanını döner; katman yoksa (taranmış sayfa) `None`."""
    text = page.get_text()
    return text if text.strip() else None


def extract_pdf_text(source: Path) -> list[str | None]:
    """`source` PDF'inin her sayfasının metin katmanını sayfa sırasıyla döner (02.2.1)."""
    content = source.read_bytes()
    with _open_pdf(content) as document:
        return [extract_page_text(page) for page in document]


def extract_upload_file_text(
    session: Session, layout: DataLayout, upload_file: UploadFile
) -> list[Page]:
    """Yüklenmiş PDF'in metin katmanını `pages.text_layer`'a yazar (02.2.1).

    Metin katmanı olmayan (taranmış) sayfada `text_layer` `None` kalır. Var olan `Page` satırı
    güncellenir, yenisi açılmaz; sayfanın diğer alanlarına dokunulmaz. Oturum commit edilmez —
    işlem sınırı çağıranındır.
    """
    texts = extract_pdf_text(layout.resolve(upload_file.stored_path))
    existing = {page.index: page for page in upload_file.pages}
    pages: list[Page] = []
    for index, text in enumerate(texts):
        page = existing.get(index)
        if page is None:
            page = Page(file=upload_file, index=index)
            session.add(page)
        page.text_layer = text
        pages.append(page)
    session.flush()
    return pages


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


def render_image_copy(
    source: Path, layout: DataLayout, file_id: int, *, jpeg_quality: int
) -> RenderedPage:
    """`source` görüntüsünün (JPEG/PNG) EXIF yönelimi uygulanmış analiz kopyasını üretir (02.3.1).

    Kopya `cache/pages/<file_id>/0000.<uzantı>` altına kaynağın kendi biçiminde yazılır; kaynağa
    dokunulmaz (K10). Yalnız EXIF yönelim etiketi fiziksel olarak uygulanır — kırpma, boyutlandırma,
    kontrast gibi başka bir piksel dönüşümü yapılmaz (K11). Yönelim etiketi yoksa (ya da zaten
    normalse) kopya kaynakla görsel olarak aynıdır.
    """
    content = source.read_bytes()
    try:
        kind = detect_file_kind(content)
    except UnsupportedFileTypeError:
        kind = None
    extension = _IMAGE_COPY_EXTENSIONS.get(kind)
    if extension is None:
        raise RenderError("Dosya görüntü değil; analiz kopyası yalnız JPEG/PNG için üretilir.")

    with Image.open(BytesIO(content)) as image:
        image_format = image.format
        oriented = ImageOps.exif_transpose(image)
        width, height = oriented.size
        buffer = BytesIO()
        save_kwargs = {"quality": jpeg_quality} if kind is FileKind.JPEG else {}
        oriented.save(buffer, format=image_format, **save_kwargs)

    path = layout.page_image_path(file_id, 0, extension=extension)
    replace_file(path, buffer.getvalue())
    return RenderedPage(index=0, path=path, width=width, height=height)


def is_page_blank(page: pymupdf.Page) -> bool:
    """Sayfa fiziksel olarak boş mu: metin katmanı, gömülü görüntü veya çizim yoksa evet (02.4.1).

    Yalnız PDF'in kendi içerik nesnelerine bakar (OCR/piksel analizi yapmaz — K11). Metin
    katmanı olmayan taranmış bir sayfa (02.2.1) gömülü bir görüntü taşıyorsa boş SAYILMAZ.
    """
    if page.get_text().strip():
        return False
    if page.get_images():
        return False
    if page.get_drawings():
        return False
    return True


def detect_pdf_blank_pages(source: Path) -> list[bool]:
    """`source` PDF'inin her sayfasının boş olup olmadığını sayfa sırasıyla döner (02.4.1)."""
    content = source.read_bytes()
    with _open_pdf(content) as document:
        return [is_page_blank(page) for page in document]


def mark_upload_file_blank_pages(
    session: Session, layout: DataLayout, upload_file: UploadFile
) -> list[Page]:
    """Yüklenmiş PDF'in boş sayfalarını `pages.is_blank`'e işaretler (02.4.1).

    Boş bulunan her sayfa için `PAGE_BLANK` olayı yazılır (K15); boş sayfa hata sayılmaz.
    Analizciye gönderilmemesi bu alanı okuyacak orkestrasyonun (09.x) işidir, burada yapılmaz.
    Var olan `Page` satırı güncellenir, yenisi açılmaz; sayfanın diğer alanlarına dokunulmaz —
    `extract_upload_file_text`'in sözleşmesiyle simetrik. Oturum commit edilmez.
    """
    blanks = detect_pdf_blank_pages(layout.resolve(upload_file.stored_path))
    existing = {page.index: page for page in upload_file.pages}
    pages: list[Page] = []
    with event_context(upload_id=upload_file.upload_id, file_id=upload_file.id):
        for index, blank in enumerate(blanks):
            page = existing.get(index)
            if page is None:
                page = Page(file=upload_file, index=index)
                session.add(page)
            page.is_blank = blank
            if blank:
                record_event(session, EventType.PAGE_BLANK, page_index=index)
            pages.append(page)
    session.flush()
    return pages


def render_image_file(
    session: Session, layout: DataLayout, settings: Settings, upload_file: UploadFile
) -> list[Page]:
    """Yüklenmiş görüntü dosyasının (JPEG/PNG) analiz kopyasını üretir; `pages`/`page_count` yazar.

    Tek sayfalık `PAGE_RENDERED` olayı dosyaya bağlı yazılır (K15). Yeniden çalıştırmada var olan
    `Page` satırı (index 0) güncellenir, yenisi açılmaz; sayfanın diğer alanlarına dokunulmaz.
    Oturum commit edilmez — işlem sınırı çağıranındır.
    """
    item = render_image_copy(
        layout.resolve(upload_file.stored_path),
        layout,
        upload_file.id,
        jpeg_quality=settings.page_render_jpeg_quality,
    )
    existing = {page.index: page for page in upload_file.pages}
    with event_context(upload_id=upload_file.upload_id, file_id=upload_file.id):
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
            },
        )
        upload_file.page_count = 1
        session.flush()
    return [page]
