"""01.2 — içerik tabanlı dosya türü tespiti ve desteklenmeyen türün reddi.

İçerikler sentetik bayt dizileridir; gerçek belge kullanılmaz (CONVENTIONS §6).
"""

from __future__ import annotations

import mimetypes
import re
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from app.storage.filetype import (
    EXTENSION_MIMES,
    MIME_EXTENSIONS,
    FileKind,
    UnsupportedFileTypeError,
    detect_file_kind,
    extension_for_mime,
    mime_for_name,
)


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


# --- tm 162: MIME ↔ uzantı eşlemesi işletim sisteminden bağımsız ---------------------------------

UPLOAD_TEMPLATE = Path(__file__).resolve().parents[2] / "app" / "web" / "templates" / "upload.html"


def _accepted_extensions() -> set[str]:
    (accept,) = re.findall(r'accept="([^"]+)"', UPLOAD_TEMPLATE.read_text(encoding="utf-8"))
    return set(accept.split(","))


def test_the_mapping_covers_every_extension_the_web_upload_accepts() -> None:
    assert _accepted_extensions() == set(EXTENSION_MIMES)
    assert {extension.lstrip(".") for extension in MIME_EXTENSIONS.values()} == {
        "jpg" if kind is FileKind.JPEG else kind.value for kind in FileKind
    }


def test_the_mapping_does_not_use_the_os_mime_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mimetypes, "guess_extension", lambda *args, **kwargs: None)
    monkeypatch.setattr(mimetypes, "guess_type", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(mimetypes, "types_map", {})

    for extension in _accepted_extensions():
        mime = mime_for_name(f"belge{extension.upper()}")
        assert mime is not None
        assert mime_for_name(f"belge{extension}") == mime
        assert extension_for_mime(mime) == (".jpg" if extension == ".jpeg" else extension)


@pytest.mark.parametrize(
    ("mime", "extension"),
    [
        ("application/pdf; charset=binary", ".pdf"),
        ("IMAGE/PNG", ".png"),
        ("text/plain", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_extension_for_mime_ignores_parameters_and_case(mime: str | None, extension: str) -> None:
    assert extension_for_mime(mime) == extension


@pytest.mark.parametrize("name", [None, "", "uzantisiz", "notlar.txt", ".pdf"])
def test_mime_for_name_without_an_accepted_extension_is_none(name: str | None) -> None:
    assert mime_for_name(name) is None
