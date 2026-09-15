"""Uygulayıcı — planın seçtiği fiziksel işlemler (PRD 07.x, §20.5).

Bu modül planlayıcının (`app/pipeline/plan.py`) `operation` alanına yazdığı kararı yürütür;
işlemi yeniden seçmez ya da izinlerini yeniden denetlemez (06.2.1–06.4.1 planlayıcının işidir).
Ortak kural (K11): hiçbir işlem içeriği üretmez, kırpmaz ya da değiştirmez.

Şimdilik `passthrough` (07.1.1) ve `extract` (07.2.1) uygulanır. Öteki işlemler (`merge`,
`wrap_image`, `extract_image`, `render_image`) ve ortak çıktı yazma — köken kaydı, `documents`
satırı, `OUTPUT_SAVED` olayı, `Alinan` kopyası (07.7.1) — sonraki görevlerdedir.
"""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from itertools import pairwise
from pathlib import Path

import pymupdf
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError

from app.storage import (
    FileKind,
    StoredFile,
    UnsupportedFileTypeError,
    copy_file,
    detect_file_kind,
    sha256_file,
    write_file,
)


class PassthroughIntegrityError(RuntimeError):
    """passthrough (07.1.1, §20.5): yayınlanan dosyanın SHA-256'sı kaynağınkiyle eşleşmiyor.

    Aynı bayt akışının kopyalanmasında bu beklenmez; çıktı sessizce kabul edilmez.
    """


class ExtractSourceError(ValueError):
    """extract (07.2.1): kaynak okunabilir bir PDF değil ya da istenen sayfa kaynakta yok.

    Hedefe hiçbir şey yazılmaz.
    """


class ExtractIntegrityError(RuntimeError):
    """extract (07.2.1, §20.5): çıktının sayfa sayısı ya da bir sayfasının metin katmanı kaynağa
    uymuyor.

    Sayfa nesnesi kopyasında bu beklenmez; çıktı yayınlanmaz.
    """


def execute_passthrough(source: Path, destination: Path) -> StoredFile:
    """Kaynak dosyayı hedefe bayt bayt kopyalar (07.1.1, §20.5).

    Yeniden yazma, yeniden kaydetme ya da kütüphaneden geçirme yoktur: `copy_file` kaynağı
    olduğu gibi okuyup atomik olarak yayınlar (K10, K11). Doğrulama: yayınlanan dosyanın
    SHA-256'sı kaynağınkine **eşit** olmalıdır; değilse `PassthroughIntegrityError`.
    """
    expected_sha256 = sha256_file(source)
    stored = copy_file(source, destination)
    if stored.sha256 != expected_sha256:
        raise PassthroughIntegrityError(
            f"passthrough bütünlük hatası: kaynak {expected_sha256}, çıktı {stored.sha256}"
        )
    return stored


def execute_extract(source: Path, destination: Path, *, pages: Sequence[int]) -> StoredFile:
    """Kaynak PDF'in `pages` sayfalarını yeni bir PDF olarak hedefe çıkarır (07.2.1, §20.5).

    `pages` plan kaynağının sayfalarıdır (`PlanSource.pages`: 0 tabanlı `pages.index`, artan ve
    tekrarsız); sayfalar bu sırayla alınır, yeniden sıralanmaz. Aksi `ValueError`.

    Yöntem pypdf sayfa nesnesi kopyasıdır: `writer.add_page(reader.pages[i])`. İçerik akışı,
    gömülü fontlar ve görüntüler olduğu gibi taşınır. Sayfa yeniden render edilmez, içerik akışı
    sıkıştırılmaz ya da yeniden yazılmaz (`compress_content_streams` çağrılmaz), sayfa boyutu ve
    döndürmesi değişmez (K3, K11).

    Kaynak PDF değilse, açılamıyorsa (bozuk, parola korumalı) ya da iki okuyucu (sayfa dizinlerini
    veren MuPDF ve kopyalayan pypdf) sayfa sayısında anlaşamıyorsa ya da istenen sayfa kaynakta
    yoksa `ExtractSourceError`.

    Doğrulama çıktı yayınlanmadan bellekte yapılır: çıktının sayfa sayısı `len(pages)` olmalı ve
    her çıktı sayfasının metin katmanı kaynaktaki karşılık gelen sayfanınkiyle **birebir aynı**
    olmalıdır; değilse `ExtractIntegrityError`. Hatada hedefe hiçbir şey yazılmaz. Geçen çıktı
    `write_file` ile atomik yayınlanır; hedef zaten varsa `FileExistsError` (üzerine yazma yok).
    """
    selected = tuple(pages)
    if not selected:
        raise ValueError("extract en az bir sayfa ister")
    if selected[0] < 0 or any(first >= second for first, second in pairwise(selected)):
        raise ValueError("extract sayfaları 0 veya büyük, artan sırada ve tekrarsız olmalı")

    content = source.read_bytes()
    with _open_source(content) as source_document:
        reader = _read_source(content, expected_page_count=source_document.page_count)
        if selected[-1] >= source_document.page_count:
            raise ExtractSourceError(
                f"extract sayfası kaynakta yok: sayfa {selected[-1]}, "
                f"kaynak {source_document.page_count} sayfa"
            )
        writer = PdfWriter()
        for index in selected:
            writer.add_page(reader.pages[index])
        buffer = BytesIO()
        writer.write(buffer)
        output = buffer.getvalue()
        _verify_extract(source_document, output, selected)
    return write_file(destination, output)


def _open_source(content: bytes) -> pymupdf.Document:
    try:
        kind = detect_file_kind(content)
    except UnsupportedFileTypeError:
        kind = None
    # MuPDF JPEG/PNG baytlarını da tek sayfalık belge olarak açar; tür önce içerik imzasından.
    if kind is not FileKind.PDF:
        raise ExtractSourceError("extract kaynağı PDF değil")
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except RuntimeError as exc:
        raise ExtractSourceError("extract kaynağı açılamadı; PDF bozuk olabilir") from exc
    if document.needs_pass:
        document.close()
        raise ExtractSourceError("extract kaynağı parola korumalı")
    return document


def _read_source(content: bytes, *, expected_page_count: int) -> PdfReader:
    try:
        reader = PdfReader(BytesIO(content))
        page_count = len(reader.pages)
    except PyPdfError as exc:
        raise ExtractSourceError("extract kaynağı pypdf ile okunamadı") from exc
    if page_count != expected_page_count:
        # Bozuk PDF'i iki kütüphane farklı onarabilir; o zaman plandaki sayfa dizini pypdf'te
        # başka bir sayfayı gösterebilir — tahmin edilmez.
        raise ExtractSourceError(
            f"extract kaynağının sayfa sayısı okuyucular arasında farklı: "
            f"MuPDF {expected_page_count}, pypdf {page_count}"
        )
    return reader


def _verify_extract(
    source_document: pymupdf.Document, output: bytes, selected: tuple[int, ...]
) -> None:
    try:
        output_document = pymupdf.open(stream=output, filetype="pdf")
    except RuntimeError as exc:
        raise ExtractIntegrityError("extract çıktısı PDF olarak açılamadı") from exc
    with output_document:
        if output_document.page_count != len(selected):
            raise ExtractIntegrityError(
                f"extract sayfa sayısı hatası: beklenen {len(selected)}, "
                f"çıktı {output_document.page_count}"
            )
        for output_index, source_index in enumerate(selected):
            if output_document[output_index].get_text() != source_document[source_index].get_text():
                raise ExtractIntegrityError(
                    f"extract metin katmanı hatası: çıktı sayfası {output_index}, "
                    f"kaynak sayfası {source_index}"
                )
