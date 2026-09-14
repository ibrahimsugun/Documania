"""Sentetik test belgeleri üretir (CONVENTIONS §6) — gerçek kimlik belgesi kullanılmaz.

Yalnız fiziksel yapı gerektiren testler (boyut/sayfa sınırı, sayfa gruplama vb.) içindir;
içerik boş sayfadır, hiçbir kişisel veri taşımaz.
"""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfWriter


def make_pdf_bytes(page_count: int = 1) -> bytes:
    """`page_count` boş sayfalık gerçek (pypdf ile okunabilir) bir PDF döner."""
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=595, height=842)  # A4
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
