"""Sentetik test belgeleri üretir (CONVENTIONS §6) — gerçek kimlik belgesi kullanılmaz.

Yalnız fiziksel yapı gerektiren testler (boyut/sayfa sınırı, sayfa gruplama, render vb.)
içindir; içerik boş sayfa ya da geometrik desendir, hiçbir kişisel veri taşımaz.
"""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from io import BytesIO

import pymupdf
from PIL import Image, ImageDraw
from pypdf import PdfWriter

A4 = (595.0, 842.0)


def make_pdf_bytes(page_count: int = 1) -> bytes:
    """`page_count` boş sayfalık gerçek (pypdf ile okunabilir) bir PDF döner."""
    return make_sized_pdf_bytes([A4] * page_count)


def make_sized_pdf_bytes(
    sizes: Sequence[tuple[float, float]],
    *,
    rotate: int = 0,
    password: str | None = None,
) -> bytes:
    """Her sayfası `sizes`'taki (genişlik, yükseklik) nokta boyutunda boş PDF döner.

    `rotate` her sayfaya PDF `/Rotate` değeri olarak yazılır; `password` verilirse PDF
    kullanıcı parolasıyla şifrelenir.
    """
    writer = PdfWriter()
    for width, height in sizes:
        page = writer.add_blank_page(width=width, height=height)
        if rotate:
            page.rotate(rotate)
    if password is not None:
        writer.encrypt(password)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_text_pdf_bytes(pages: Sequence[str | None], size: tuple[float, float] = A4) -> bytes:
    """Sayfa başına verilen metni gömer; `None` sayfa metinsiz kalır (taranmış sayfa)."""
    document = pymupdf.open()
    for text in pages:
        page = document.new_page(width=size[0], height=size[1])
        if text is not None:
            page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def make_half_filled_image_bytes(
    fmt: str = "JPEG", size: tuple[int, int] = (200, 100), *, orientation: int | None = None
) -> bytes:
    """Sol yarısı siyah, sağ yarısı beyaz `fmt` (JPEG/PNG) görüntü.

    `orientation` verilirse EXIF `Orientation` etiketi (0x0112) olarak gömülür — render testleri
    bununla analiz kopyasının yönelimi fiziksel olarak uyguladığını doğrular.
    """
    width, height = size
    image = Image.new("RGB", (width, height), "white")
    ImageDraw.Draw(image).rectangle([0, 0, width // 2 - 1, height - 1], fill="black")
    save_kwargs: dict[str, object] = {}
    if orientation is not None:
        exif = image.getexif()
        exif[0x0112] = orientation
        save_kwargs["exif"] = exif
    buffer = BytesIO()
    image.save(buffer, format=fmt, **save_kwargs)
    return buffer.getvalue()


def make_half_filled_pdf_bytes(width: float = A4[0], height: float = A4[1]) -> bytes:
    """Tek sayfalı PDF: sol yarı siyah dolgulu, sağ yarının üst şeridinde ince çizgiler.

    Render testleri görüntünün kırpılmadığını/döndürülmediğini piksel konumundan doğrular;
    çizgiler JPEG kalitesinin dosya boyuna etkisini görünür kılar.
    """
    document = pymupdf.open()
    page = document.new_page(width=width, height=height)
    page.draw_rect(pymupdf.Rect(0, 0, width / 2, height), color=(0, 0, 0), fill=(0, 0, 0))
    y = 0.0
    while y < height * 0.1:
        page.draw_line(pymupdf.Point(width / 2, y), pymupdf.Point(width, y), width=0.5)
        y += 3
    content = document.tobytes()
    document.close()
    return content


def _zip_with(*entries: str) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for entry in entries:
            archive.writestr(entry, "sentetik icerik")
    return buffer.getvalue()


def make_docx_bytes() -> bytes:
    """Word (OOXML) içerik imzasını taşıyan en küçük ZIP (K2 — analiz edilmez)."""
    return _zip_with("[Content_Types].xml", "word/document.xml")


def make_xlsx_bytes() -> bytes:
    """Excel (OOXML) içerik imzasını taşıyan en küçük ZIP (K2 — analiz edilmez)."""
    return _zip_with("[Content_Types].xml", "xl/workbook.xml")


def make_legacy_doc_bytes() -> bytes:
    """Eski ikili Word (CFBF/OLE) içerik imzası (K2 — analiz edilmez)."""
    return b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32 + "WordDocument".encode("utf-16-le")


def make_legacy_xls_bytes() -> bytes:
    """Eski ikili Excel (CFBF/OLE) içerik imzası (K2 — analiz edilmez)."""
    return b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32 + "Workbook".encode("utf-16-le")
