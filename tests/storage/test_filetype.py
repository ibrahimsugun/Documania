"""01.2 — içerik tabanlı dosya türü tespiti ve desteklenmeyen türün reddi.

İçerikler sentetik bayt dizileridir; gerçek belge kullanılmaz (CONVENTIONS §6).
"""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from app.storage.filetype import FileKind, UnsupportedFileTypeError, detect_file_kind


def _zip_with(*entries: str) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for entry in entries:
            archive.writestr(entry, "sentetik icerik")
    return buffer.getvalue()


# --- 01.2.1: içerik uzantıdan önce gelir -----------------------------------------------------


def test_pdf_content_with_jpg_extension_is_detected_as_pdf() -> None:
    # Dosya adı/uzantısı hiç okunmaz; yalnız içerik verilir — `.jpg` olarak gelmiş olsa da
    # sonuç PDF'tir (01.2.1).
    content = b"%PDF-1.7 sentetik\n1 0 obj\n<< >>\nendobj\n%%EOF"

    assert detect_file_kind(content) == FileKind.PDF


def test_jpeg_signature_detected() -> None:
    assert detect_file_kind(b"\xff\xd8\xff\xe0sentetik jpeg govdesi") == FileKind.JPEG


def test_png_signature_detected() -> None:
    assert detect_file_kind(b"\x89PNG\r\n\x1a\nsentetik png govdesi") == FileKind.PNG


def test_docx_zip_entry_detected() -> None:
    content = _zip_with("[Content_Types].xml", "word/document.xml")

    assert detect_file_kind(content) == FileKind.DOCX


def test_xlsx_zip_entry_detected() -> None:
    content = _zip_with("[Content_Types].xml", "xl/workbook.xml")

    assert detect_file_kind(content) == FileKind.XLSX


def test_legacy_doc_ole_marker_detected() -> None:
    content = (
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32 + "WordDocument".encode("utf-16-le")
    )

    assert detect_file_kind(content) == FileKind.DOC


@pytest.mark.parametrize("marker", ["Workbook", "Book"])
def test_legacy_xls_ole_marker_detected(marker: str) -> None:
    content = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32 + marker.encode("utf-16-le")

    assert detect_file_kind(content) == FileKind.XLS


# --- 01.2.2: desteklenmeyen tür anlaşılır mesajla reddedilir ----------------------------------


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"sadece duz metin, hicbir imzaya uymaz",
        b"\x1f\x8bgzip sentetik govde",
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64,  # OLE ama Word/Excel isareti yok
    ],
)
def test_unrecognized_content_is_rejected(content: bytes) -> None:
    with pytest.raises(UnsupportedFileTypeError, match="Desteklenmeyen dosya türü"):
        detect_file_kind(content)


def test_zip_without_ooxml_entries_is_rejected() -> None:
    content = _zip_with("readme.txt")

    with pytest.raises(UnsupportedFileTypeError):
        detect_file_kind(content)


def test_corrupt_zip_signature_is_rejected() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        detect_file_kind(b"PK\x03\x04" + b"bozuk zip govdesi")
