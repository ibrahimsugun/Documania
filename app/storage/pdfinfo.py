"""PDF sayfa sayımı — şifreli PDF'te de çökmeyen tek okuma noktası (PRD 01.3.1, 11.2.1; tm 137).

Resmî kurum PDF'lerinin çoğu **sahip parolasıyla** (yalnız düzenleme/yazdırma izni kısıtlı, AES)
şifrelidir: parolasız açılır ve okunur. pypdf AES'i çözmek için `cryptography` ister; paket yoksa
`DependencyError` fırlatır ve bu sınıf `PyPdfError` ailesinden **değildir** — yakalanmazsa örnek
yükleme, tür açıklaması üretimi ve yükleme uç noktası 500 ile düşer.

Kural: önce pypdf (her zamanki okuyucu); yalnız AES çözülemediğinde MuPDF'e düşülür. MuPDF sahip
parolalı PDF'i parolasız açar. Açmak için parola gereken (kullanıcı parolalı) ya da okunamayan PDF
`None` döner — çağıran bunu kendi kuralına göre yorumlar. Hiçbir yerde şifre kaldırılmaz, dosya
yeniden yazılmaz (K11, K17).
"""

from __future__ import annotations

from io import BytesIO

import pymupdf
from pypdf import PdfReader
from pypdf.errors import DependencyError, PdfReadError


def count_pdf_pages(content: bytes) -> int | None:
    """PDF'in sayfa sayısı; okunamıyorsa ya da açmak için parola gerekiyorsa `None`."""
    try:
        return len(PdfReader(BytesIO(content)).pages)
    except PdfReadError:
        return None
    except DependencyError:
        return _count_with_mupdf(content)


def _count_with_mupdf(content: bytes) -> int | None:
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                return None
            return int(document.page_count)
    except (RuntimeError, ValueError):
        return None
