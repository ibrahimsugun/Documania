"""PDF sayfa sayımı — şifreli PDF'te çökmeyen okuma (01.3.1, 11.2.1; tm 137)."""

from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader
from pypdf.errors import DependencyError

from app.storage import pdfinfo
from app.storage.pdfinfo import count_pdf_pages
from tests.fixtures.gen import make_owner_locked_pdf_bytes, make_pdf_bytes, make_sized_pdf_bytes


def test_plain_pdf_is_counted() -> None:
    assert count_pdf_pages(make_pdf_bytes(3)) == 3


def test_owner_locked_aes_pdf_is_counted_without_a_password() -> None:
    content = make_owner_locked_pdf_bytes(4)

    # Fikstürün varlık sebebi: pypdf bu PDF'te `PyPdfError` ailesinden OLMAYAN bir hata fırlatır.
    with pytest.raises(DependencyError):
        PdfReader(BytesIO(content))
    assert count_pdf_pages(content) == 4


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(make_owner_locked_pdf_bytes(2, user_password="gizli"), id="aes-acma-parolali"),
        pytest.param(
            make_sized_pdf_bytes([(595.0, 842.0)], password="gizli"), id="rc4-acma-parolali"
        ),
        pytest.param(b"%PDF-1.4 bozuk", id="bozuk"),
        pytest.param(b"duz metin", id="pdf-degil"),
    ],
)
def test_pdf_that_needs_a_password_or_cannot_be_read_has_no_count(content: bytes) -> None:
    assert count_pdf_pages(content) is None


def test_aes_pdf_that_mupdf_cannot_open_either_has_no_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # pypdf AES'i çözemez, MuPDF de dosyayı açamazsa sayım yoktur; istisna çağırana geçmez.
    content = make_owner_locked_pdf_bytes(1)

    def broken_open(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("bozuk xref")

    monkeypatch.setattr(pdfinfo.pymupdf, "open", broken_open)

    assert count_pdf_pages(content) is None
