"""İçerik tabanlı dosya türü tespiti (PRD 01.2.1, 01.2.2).

Tür, dosya adı/uzantısına değil ilk baytlardaki imzaya bakılarak belirlenir — uzantısı
`.jpg` olan PDF içerikli bir dosya PDF olarak tanınır (01.2.1). Yedi desteklenen türün
(PDF/JPEG/PNG/DOC/DOCX/XLS/XLSX) dışındaki her içerik anlaşılır bir mesajla reddedilir
(01.2.2). K2: DOC/XLS/DOCX/XLSX yalnız tanınır, analiz edilmez.
"""

from __future__ import annotations

import enum
import zipfile
from io import BytesIO
from pathlib import PurePosixPath

from app.i18n import N_, Translatable


class FileKind(enum.StrEnum):
    """İçerikten tespit edilen dosya türü; değerler K8/naming ile aynı küçük harf biçimidir."""

    PDF = "pdf"
    JPEG = "jpeg"
    PNG = "png"
    DOC = "doc"
    DOCX = "docx"
    XLS = "xls"
    XLSX = "xlsx"


# Kabul edilen yedi türün MIME türü → uzantı eşlemesi (yükleme sayfasının `accept` listesi:
# .pdf .jpg .jpeg .png .doc .docx .xls .xlsx). İşletim sisteminin `mimetypes` tablosu kullanılmaz:
# Windows kayıt defterinden `.docx` bulur, `/etc/mime.types`'ı olmayan Linux bulamaz (PLAN.md §D99).
MIME_EXTENSIONS: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}
# Uzantı → MIME türü; `.jpeg` da JPEG'dir.
EXTENSION_MIMES: dict[str, str] = {
    **{extension: mime for mime, extension in MIME_EXTENSIONS.items()},
    ".jpeg": "image/jpeg",
}


def extension_for_mime(mime: str | None) -> str:
    """Kabul edilen türün uzantısı (`.docx`); tür tanınmıyorsa boş dizge."""
    return MIME_EXTENSIONS.get((mime or "").split(";")[0].strip().lower(), "")


def mime_for_name(name: str | None) -> str | None:
    """Dosya adının uzantısından kabul edilen türün MIME türü; tanınmıyorsa `None`."""
    return EXTENSION_MIMES.get(PurePosixPath(name or "").suffix.lower())


class UnsupportedFileTypeError(ValueError):
    """İçerik desteklenen yedi türden hiçbirine uymuyor (01.2.2)."""

    def __init__(self) -> None:
        super().__init__(
            Translatable(
                N_(
                    "Desteklenmeyen dosya türü. "
                    "Yalnız PDF, JPEG, PNG, DOC, DOCX, XLS, XLSX kabul edilir."
                )
            )
        )


_PDF_SIGNATURE = b"%PDF-"
_JPEG_SIGNATURE = b"\xff\xd8\xff"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")

_OLE_WORD_MARKER = "WordDocument".encode("utf-16-le")
_OLE_EXCEL_MARKERS = ("Workbook".encode("utf-16-le"), "Book".encode("utf-16-le"))

_OOXML_DOCX_ENTRY = "word/document.xml"
_OOXML_XLSX_ENTRY = "xl/workbook.xml"


def detect_file_kind(content: bytes) -> FileKind:
    """`content` baytlarının imzasından gerçek türü döner; tanınmazsa reddeder.

    Uzantı hiç okunmaz — tespit tamamen içerik baytlarına dayanır (01.2.1).
    """
    if content.startswith(_PDF_SIGNATURE):
        return FileKind.PDF
    if content.startswith(_JPEG_SIGNATURE):
        return FileKind.JPEG
    if content.startswith(_PNG_SIGNATURE):
        return FileKind.PNG
    if content.startswith(_OLE_SIGNATURE):
        return _detect_ole_kind(content)
    if content.startswith(_ZIP_SIGNATURES):
        return _detect_ooxml_kind(content)
    raise UnsupportedFileTypeError


def _detect_ole_kind(content: bytes) -> FileKind:
    """Eski ikili Word/Excel biçimi (CFBF); akış adları UTF-16LE olarak dizinde tutulur."""
    if _OLE_WORD_MARKER in content:
        return FileKind.DOC
    if any(marker in content for marker in _OLE_EXCEL_MARKERS):
        return FileKind.XLS
    raise UnsupportedFileTypeError


def _detect_ooxml_kind(content: bytes) -> FileKind:
    """OOXML kapsayıcısı (ZIP); iç yol adı DOCX/XLSX'i ayırt eder."""
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        raise UnsupportedFileTypeError from None
    if _OOXML_DOCX_ENTRY in names:
        return FileKind.DOCX
    if _OOXML_XLSX_ENTRY in names:
        return FileKind.XLSX
    raise UnsupportedFileTypeError
