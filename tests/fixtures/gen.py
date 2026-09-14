"""Sentetik test belgeleri üretir (CONVENTIONS §6) — gerçek kimlik belgesi kullanılmaz.

Yalnız fiziksel yapı gerektiren testler (boyut/sayfa sınırı, sayfa gruplama, render vb.)
içindir; içerik boş sayfa ya da geometrik desendir, hiçbir kişisel veri taşımaz.
"""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO

import pymupdf
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
