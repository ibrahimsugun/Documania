"""Sayfa üretimi — PDF sayfa görüntüsü (PRD 02.1.1), metin katmanı (PRD 02.2.1) ve görüntü
dosyaları için analiz kopyası (PRD 02.3.1).

Inbox'taki PDF'in her sayfası analiz için `cache/pages/<file_id>/<sayfa>.jpg` olarak render
edilir (§8.2). Ölçek iki yapılandırma değerinden gelir:

- `PAGE_RENDER_DPI` — sayfa bu çözünürlükte render edilir.
- `PAGE_RENDER_MAX_LONG_EDGE_PX` — o çözünürlükte görüntünün uzun kenarı sınırı aşacaksa ölçek,
  uzun kenar sınıra oturacak kadar küçültülür. Küçültme render ölçeğine uygulanır: sayfa
  doğrudan hedef boyutta rasterleştirilir. Önce büyük görüntü üretip sonra yeniden örneklemek
  aynı piksel boyutunu daha çok bellekle ve ikinci bir örnekleme adımıyla verirdi.

**Metin katmanı önceliği (13.2.2).** Metin katmanı olan sayfada (02.2.1) yazının kendisi analiz
isteğine metin olarak gider (`app.pipeline.analyze.build_page_prompt`); görüntü düzen, görünüm ve
okunaklılık içindir. Bu sayfalar `PAGE_RENDER_TEXT_LAYER_MAX_LONG_EDGE_PX` sınırıyla — genel
sınırdan küçükse — render edilir; küçültme yine render ölçeğine uygulanır, görüntü yeniden
örneklenmez. Metin katmanı olmayan (taranmış) sayfa ve görüntü dosyası genel ayarla kalır.
`PAGE_RENDERED` verisindeki `text_layer` sayfanın bu sınırla render edildiğini söyler.

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

Gömülü tek görüntü tespiti (02.5.1) sayfanın tek bir tam sayfa görüntüden oluşup oluşmadığını
`pages.has_single_embedded_image`'e işaretler; `extract_image` (§20.5, 07.5.1) yalnız bu işaretli
sayfada seçilir. Karar sayfa MuPDF ile çalıştırılırken çizim komutları kaydedilerek verilir —
görüntüye bakılmaz, yalnız sayfanın ne çizdiğine bakılır. Emin olunamayan her durumda işaret
verilmez: yanlış işaret sayfada görünen içeriğin bir kısmını sessizce düşürür, eksik işaret
yalnız kayıplı ama sayfaya sadık `render_image`'a düşer.

Fotoğrafın piksel boyutu (11.7.1, `photo_pixel_size`) profil fotoğrafının asgari çözünürlük
kuralı için ölçülür: yalnız okunur — görüntü çözülüp yeniden yazılmaz, dosyaya ve önbelleğe
dokunulmaz (K11).
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

# 02.5.1: görüntünün sayfa kutusunu "tam" kaplaması için her kenarda izin verilen en büyük fark
# (nokta). Sayfa boyutunun yuvarlanmasını tolere eder (300 DPI A4 taraması 595,2 pt → 595);
# 1 pt ≈ 0,35 mm, 300 DPI'da ~4 piksel.
FULL_PAGE_TOLERANCE_PT = 1.0

# 02.5.1: görüntü nesnesinin sayfadaki görünüşünü baytlarından farklı kılan anahtarlar —
# yumuşak/renk anahtarı maskesi ve renk çözme dizisi. Biri varsa çıkarılan baytlar sayfada
# görüneni vermez.
_IMAGE_APPEARANCE_KEYS = ("SMask", "Mask", "Decode", "SMaskInData")

# EXIF yönelim etiketi; 5–8 görüntüyü çeyrek tur döndürür (görünen genişlik ile yükseklik yer
# değiştirir).
_EXIF_ORIENTATION = 0x0112
_QUARTER_TURN_ORIENTATIONS = frozenset({5, 6, 7, 8})


class RenderError(ValueError):
    """Dosyadan sayfa görüntüsü üretilemiyor: PDF değil, bozuk, parolalı veya sayfasız."""


@dataclass(frozen=True)
class RenderedPage:
    """Üretilen analiz görüntüsü; uzun kenar sınırı devreye girerse `dpi` ayardan düşüktür.

    Görüntü dosyası analiz kopyalarında (02.3.1) ölçek kavramı yok — `dpi` `None` kalır.
    `text_layer` sayfanın metin katmanı sınırıyla render edildiğidir (13.2.2).
    """

    index: int
    path: Path
    width: int
    height: int
    dpi: float | None = None
    text_layer: bool = False


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


def _rasterize(page: pymupdf.Page, dpi: int, max_long_edge: int) -> tuple[pymupdf.Pixmap, float]:
    """Sayfanın `render_scale` ölçeğindeki görüntüsü ve ölçek."""
    scale = render_scale(page.rect, dpi, max_long_edge)
    return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False), scale


def render_pdf_pages(
    source: Path,
    layout: DataLayout,
    file_id: int,
    *,
    dpi: int,
    max_long_edge: int,
    jpeg_quality: int,
    text_layer_max_long_edge: int | None = None,
) -> list[RenderedPage]:
    """`source` PDF'inin her sayfasını `layout.page_image_path(file_id, i)` altına JPEG yazar.

    `text_layer_max_long_edge` verilirse metin katmanı olan sayfanın uzun kenar sınırı odur —
    `max_long_edge`'den büyük değilse (13.2.2).
    """
    content = source.read_bytes()
    rendered: list[RenderedPage] = []
    with _open_pdf(content) as document:
        for page in document:
            limit, text_layer = max_long_edge, False
            if (
                text_layer_max_long_edge is not None
                and text_layer_max_long_edge < max_long_edge
                and extract_page_text(page) is not None
            ):
                limit, text_layer = text_layer_max_long_edge, True
            pixmap, scale = _rasterize(page, dpi, limit)
            path = layout.page_image_path(file_id, page.number)
            replace_file(path, pixmap.tobytes("jpeg", jpg_quality=jpeg_quality))
            rendered.append(
                RenderedPage(
                    index=page.number,
                    path=path,
                    width=pixmap.width,
                    height=pixmap.height,
                    dpi=scale * POINTS_PER_INCH,
                    text_layer=text_layer,
                )
            )
    return rendered


def render_pdf_images(
    content: bytes, *, dpi: int, max_long_edge: int, jpeg_quality: int, max_pages: int
) -> tuple[list[bytes], int]:
    """PDF'in ilk `max_pages` sayfasının JPEG görüntüsü, bellekte (diske ve önbelleğe yazmadan),
    ve PDF'in toplam sayfa sayısı. Ölçek ve biçim `render_pdf_pages`'inkidir; tür açıklaması
    (11.3.1) örnek belgelerin sayfalarını bununla yapay zekâya verir. PDF açılamazsa `RenderError`.
    """
    if max_pages < 0:
        raise ValueError("max_pages 0 veya pozitif olmalı")
    with _open_pdf(content) as document:
        images = [
            _rasterize(document[index], dpi, max_long_edge)[0].tobytes(
                "jpeg", jpg_quality=jpeg_quality
            )
            for index in range(min(max_pages, document.page_count))
        ]
        return images, document.page_count


def extract_page_text(page: pymupdf.Page) -> str | None:
    """Sayfanın gömülü metin katmanını döner; katman yoksa (taranmış sayfa) `None`."""
    text = page.get_text()
    return text if text.strip() else None


def extract_pdf_text(source: Path) -> list[str | None]:
    """`source` PDF'inin her sayfasının metin katmanını sayfa sırasıyla döner (02.2.1)."""
    return extract_pdf_content_text(source.read_bytes())


def extract_pdf_content_text(content: bytes) -> list[str | None]:
    """PDF baytlarının her sayfasının metin katmanı, bellekte (diske ve önbelleğe yazmadan);
    eğitim modunun mekanik tanıması (11.9.2) MRZ'yi bununla arar. PDF açılamazsa `RenderError`."""
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
        text_layer_max_long_edge=settings.page_render_text_layer_max_long_edge_px,
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
                    "text_layer": item.text_layer,
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
    copy = image_copy(source.read_bytes(), jpeg_quality=jpeg_quality)
    path = layout.page_image_path(file_id, 0, extension=copy.extension)
    replace_file(path, copy.content)
    return RenderedPage(index=0, path=path, width=copy.width, height=copy.height)


@dataclass(frozen=True)
class ImageCopy:
    """Görüntü dosyasının bellekteki analiz kopyası (`image_copy`)."""

    content: bytes
    extension: str
    width: int
    height: int


def image_copy(content: bytes, *, jpeg_quality: int) -> ImageCopy:
    """JPEG/PNG baytlarının EXIF yönelimi uygulanmış analiz kopyası, bellekte (02.3.1; kurallar
    `render_image_copy`'nin). Görüntü değilse `RenderError`; çözülemeyen görüntüde Pillow'un hatası
    yükselir."""
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
    return ImageCopy(content=buffer.getvalue(), extension=extension, width=width, height=height)


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


class _PaintRecorder(pymupdf.mupdf.FzDevice2):
    """Sayfa çalıştırılırken MuPDF'in çizim komutlarını kaydeden aygıt (02.5.1).

    Yalnız karar için gereken tutulur: her görüntü çiziminin dönüşüm matrisi ve alfası, her
    dikdörtgen kırpmanın sınırı. Görüntünün görünüşünü değiştirebilecek her başka komut —
    görünür metin, yol, gölgeleme, görüntü maskesi, yumuşak maske, desen, dikdörtgen olmayan
    kırpma, normal dışı karışım veya yarı saydam grup — `disqualified`'ı işaretler. Görünmez metin
    (OCR katmanı), katman işaretleri ve kırpma/grup kapanışları görünüşü değiştirmez, sayılmaz.
    """

    _DISQUALIFYING_CALLS = (
        "fill_path",
        "stroke_path",
        "clip_stroke_path",
        "fill_text",
        "stroke_text",
        "clip_text",
        "clip_stroke_text",
        "fill_shade",
        "fill_image_mask",
        "clip_image_mask",
        "begin_mask",
        "begin_tile",
    )

    def __init__(self) -> None:
        super().__init__()
        self.images: list[tuple[pymupdf.Matrix, float]] = []
        self.clip_rects: list[pymupdf.Rect] = []
        self.disqualified = False
        # MuPDF yalnız açıkça etkinleştirilen sanal yöntemleri Python'a yönlendirir.
        for name in ("fill_image", "clip_path", "begin_group", *self._DISQUALIFYING_CALLS):
            getattr(self, f"use_virtual_{name}")()

    def _disqualify(self, *args: object) -> int:
        self.disqualified = True
        return 0  # `begin_tile` önbellek kimliği bekler; 0 = önbellekte yok, içerik çalışır.

    fill_path = stroke_path = clip_stroke_path = _disqualify
    fill_text = stroke_text = clip_text = clip_stroke_text = _disqualify
    fill_shade = fill_image_mask = clip_image_mask = begin_mask = begin_tile = _disqualify

    def fill_image(self, ctx, image, ctm, alpha, color_params) -> None:
        m = pymupdf.mupdf.FzMatrix(ctm)
        self.images.append((pymupdf.Matrix(m.a, m.b, m.c, m.d, m.e, m.f), alpha))

    def clip_path(self, ctx, path, even_odd, ctm, scissor) -> None:
        if not pymupdf.mupdf.ll_fz_path_is_rect(path, ctm):
            self.disqualified = True
            return
        bounds = pymupdf.mupdf.ll_fz_bound_path(path, None, ctm)
        self.clip_rects.append(pymupdf.Rect(bounds.x0, bounds.y0, bounds.x1, bounds.y1))

    def begin_group(self, ctx, area, colorspace, isolated, knockout, blendmode, alpha) -> None:
        if blendmode != pymupdf.mupdf.FZ_BLEND_NORMAL or alpha < 1:
            self.disqualified = True


def _covers(outer: pymupdf.Rect, inner: pymupdf.Rect) -> bool:
    tolerance = FULL_PAGE_TOLERANCE_PT
    return (
        outer.x0 - tolerance <= inner.x0
        and outer.y0 - tolerance <= inner.y0
        and outer.x1 + tolerance >= inner.x1
        and outer.y1 + tolerance >= inner.y1
    )


def single_full_page_image_xref(page: pymupdf.Page) -> int | None:
    """Sayfa tek bir tam sayfa gömülü görüntüden oluşuyorsa görüntünün `xref`'ini döner (02.5.1).

    `extract_image` (§20.5) bu xref'in orijinal baytlarını çıkarır; bu yüzden xref yalnız çıkan
    görüntünün sayfada görünenle aynı olduğu kesinse döner, aksi halde `None`. Koşulların hepsi:

    - sayfa `/Rotate` taşımaz;
    - sayfa (açıklamalar dahil) tam olarak bir görüntü çizer ve başka görünür bir şey çizmez
      (görünmez OCR metni serbest — PDF→JPEG'de iki işlem de metin katmanını taşımaz);
    - görüntü döndürülmeden/aynalanmadan, tam opak çizilir ve sayfa kutusunu her kenarda
      `FULL_PAGE_TOLERANCE_PT` içinde kaplar; kırpma varsa yalnız sayfayı kaplayan dikdörtgendir;
    - çizilen görüntü sayfanın tek görüntü nesnesidir (satır içi görüntü değil) ve görünüşünü
      baytlarından farklı kılan maske/`Decode` anahtarı taşımaz.
    """
    if page.rotation:
        return None
    recorder = _PaintRecorder()
    mupdf = pymupdf.mupdf
    mupdf.fz_run_page(page.this, recorder, mupdf.FzMatrix(), mupdf.FzCookie())
    mupdf.fz_close_device(recorder)
    if recorder.disqualified or len(recorder.images) != 1:
        return None
    matrix, alpha = recorder.images[0]
    if alpha < 1 or matrix.b or matrix.c or matrix.a <= 0 or matrix.d <= 0:
        return None
    image_rect = pymupdf.Rect(0, 0, 1, 1) * matrix
    page_rect = page.rect
    if not (_covers(image_rect, page_rect) and _covers(page_rect, image_rect)):
        return None
    if not all(_covers(clip, page_rect) for clip in recorder.clip_rects):
        return None

    images = page.get_images(full=True)
    if len(images) != 1:
        return None
    xref = images[0][0]
    if any(page.parent.xref_get_key(xref, key)[0] != "null" for key in _IMAGE_APPEARANCE_KEYS):
        return None
    # Çizilen görüntü bu nesne mi — kaynakta kullanılmayan bir görüntü + satır içi görüntü değil.
    if len(page.get_image_rects(xref)) != 1:
        return None
    return xref


def photo_pixel_size(content: bytes, page_index: int) -> tuple[int, int] | None:
    """Fotoğraf sayfasının kendi piksel boyutu `(genişlik, yükseklik)` — 11.7.1'in asgari
    çözünürlük ölçümü. Yalnız okunur: hiçbir şey yazılmaz, görüntü değişmez (K11).

    - JPEG/PNG dosyası (tek sayfa, `page_index` 0): görüntünün EXIF yönelimiyle görünen boyutu;
      çeyrek tur döndüren yönelimde genişlik ile yükseklik yer değiştirir. Pikseller çözülmez.
    - PDF sayfası tek tam sayfa gömülü görüntüden oluşuyorsa (02.5.1): o görüntü nesnesinin piksel
      boyutu — `extract_image`'in (§20.5) çıkaracağı görüntünün kendisi.
    - Öteki PDF sayfası: `None`. Sayfanın kendine ait bir piksel boyutu yoktur; çıktı sabit
      çözünürlükte render edilir (K12) ve ölçüm fotoğraf hakkında bir şey söylemez.

    İçerik görüntü ya da PDF değilse, açılamıyorsa veya sayfa yoksa `RenderError`; çözülemeyen
    görüntüde Pillow'un hatası yükselir.
    """
    try:
        kind = detect_file_kind(content)
    except UnsupportedFileTypeError:
        kind = None
    if kind in _IMAGE_COPY_EXTENSIONS:
        if page_index != 0:
            raise RenderError("Görüntü dosyasının tek sayfası vardır.")
        with Image.open(BytesIO(content)) as image:
            width, height = image.size
            orientation = image.getexif().get(_EXIF_ORIENTATION)
        if orientation in _QUARTER_TURN_ORIENTATIONS:
            return height, width
        return width, height
    with _open_pdf(content) as document:
        if not 0 <= page_index < document.page_count:
            raise RenderError("PDF'te istenen sayfa yok.")
        page = document[page_index]
        xref = single_full_page_image_xref(page)
        if xref is None:
            return None
        # `single_full_page_image_xref` sayfanın tek görüntü nesnesini doğruladı: (xref, smask,
        # genişlik, yükseklik, …).
        (image_info,) = page.get_images(full=True)
        return image_info[2], image_info[3]


def detect_pdf_single_image_pages(source: Path) -> list[bool]:
    """`source` PDF'inin her sayfası tek tam sayfa görüntü mü, sayfa sırasıyla döner (02.5.1)."""
    content = source.read_bytes()
    with _open_pdf(content) as document:
        return [single_full_page_image_xref(page) is not None for page in document]


def mark_upload_file_single_image_pages(
    session: Session, layout: DataLayout, upload_file: UploadFile
) -> list[Page]:
    """Yüklenmiş PDF'in tek tam sayfa görüntülü sayfalarını `has_single_embedded_image`'e yazar.

    02.5.1: bu işaret işlem seçiminin (§20.3 satır 5/6) girdisidir. PRD §8.3'ün kapalı olay
    listesinde bu tespit için tür yok; olay yazılmaz (bkz. PLAN.md §D6). Var olan `Page` satırı
    güncellenir, yenisi açılmaz; sayfanın diğer alanlarına dokunulmaz —
    `mark_upload_file_blank_pages`'in sözleşmesiyle simetrik. Oturum commit edilmez.
    """
    flags = detect_pdf_single_image_pages(layout.resolve(upload_file.stored_path))
    existing = {page.index: page for page in upload_file.pages}
    pages: list[Page] = []
    for index, flag in enumerate(flags):
        page = existing.get(index)
        if page is None:
            page = Page(file=upload_file, index=index)
            session.add(page)
        page.has_single_embedded_image = flag
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
