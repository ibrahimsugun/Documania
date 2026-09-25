"""Loss-preserving PDF extraction and merge operations with integrity checks."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from io import BytesIO
from itertools import pairwise
from pathlib import Path

import pymupdf
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError

from app.storage import FileKind, StoredFile, UnsupportedFileTypeError, detect_file_kind, write_file

from .execute_errors import (
    DirectDocumentMergeError,
    ExtractIntegrityError,
    ExtractSourceError,
    MergeIntegrityError,
    MergeSourceError,
)
from .execute_image_utils import (
    _IMAGE_WRAP_ERRORS,
    _wrap_image_to_pdf,
)
from .execute_types import (
    MergeSource,
)


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
    return write_file(destination, _extract_output(source, pages))


def _extract_output(source: Path, pages: Sequence[int]) -> bytes:
    selected = _page_selection(pages, subject="extract")
    content = source.read_bytes()
    # MuPDF JPEG/PNG baytlarını da tek sayfalık belge olarak açar; tür önce içerik imzasından.
    if _file_kind(content) is not FileKind.PDF:
        raise ExtractSourceError("extract kaynağı PDF değil")
    return _copy_pages(
        [_PdfPages(content, selected)],
        operation="extract",
        source_error=ExtractSourceError,
        integrity_error=ExtractIntegrityError,
    )


def execute_merge(sources: Sequence[MergeSource], destination: Path, *, direct: bool) -> StoredFile:
    """Birden çok kaynağın sayfalarını sırayla tek bir PDF'te birleştirir (07.3.1, §20.5).

    Yalnız `direct: false` türde çalışır: `direct` belge türünün katalogdaki bayrağıdır; doğruysa
    hiçbir kaynak okunmadan `DirectDocumentMergeError` (K3, §20.4).

    `sources` plan öğesinin `sources` dizisidir (aynı partinin dosyaları, K4) ve en az iki kaynak
    ister. Sayfalar bu dizinin sırasıyla, her kaynağın içinde `pages` sırasıyla alınır — yeniden
    sıralama yapılmaz. Her kaynağın sayfa seçimi `execute_extract`'takiyle aynı kurala uyar; aksi
    `ValueError` (kaynaklar okunmadan).

    Yöntem `extract` ile aynıdır: PDF kaynağın sayfası pypdf sayfa nesnesi olarak kopyalanır.
    JPEG/PNG kaynak önce `img2pdf.convert()` ile tek sayfalık PDF'e kayıpsız sarılır — JPEG
    baytları yeniden kodlanmadan gömülür, EXIF yönelimi (1/3/6/8) yalnız sayfanın `/Rotate`
    değerine yazılır — ve o sayfa aynı biçimde kopyalanır (S5). Hiçbir sayfa render edilmez,
    içerik akışı sıkıştırılmaz, görüntü yeniden kodlanmaz (K11).

    Kaynak PDF/JPEG/PNG değilse, açılamıyorsa (bozuk, parola korumalı), iki okuyucu sayfa sayısında
    anlaşamıyorsa, görüntüsü kayıpsız sarılamıyorsa (okunamayan görüntü, aynalı ya da geçersiz EXIF
    yönelimi) ya da istenen sayfa kaynakta yoksa `MergeSourceError`; mesaj kaynağı `sources[i]`
    konumuyla anar, dosya yolunu taşımaz.

    Doğrulama çıktı yayınlanmadan bellekte yapılır: çıktının sayfa sayısı alınan sayfaların
    toplamı olmalı ve her çıktı sayfasının metin katmanı karşılık gelen kaynak sayfanınkiyle
    **birebir aynı** olmalıdır; değilse `MergeIntegrityError`. Hatada hedefe hiçbir şey
    yazılmaz. Geçen çıktı `write_file` ile atomik yayınlanır; hedef zaten varsa `FileExistsError`
    (üzerine yazma yok).
    """
    return write_file(destination, _merge_output(sources, direct=direct))


def _merge_output(sources: Sequence[MergeSource], *, direct: bool) -> bytes:
    if direct:
        raise DirectDocumentMergeError(
            "merge Direkt Belge türünde yapılamaz (§20.4, K3): belge başka kaynaklardan kurulmaz"
        )
    if len(sources) < 2:
        raise ValueError("merge en az iki kaynak ister")
    selections = [
        _page_selection(source.pages, subject=f"merge sources[{position}]")
        for position, source in enumerate(sources)
    ]
    pdf_pages = [
        _PdfPages(
            _merge_source_pdf(source.path.read_bytes(), where=f" sources[{position}]"),
            selected,
            where=f" sources[{position}]",
        )
        for position, (source, selected) in enumerate(zip(sources, selections, strict=True))
    ]
    return _copy_pages(
        pdf_pages,
        operation="merge",
        source_error=MergeSourceError,
        integrity_error=MergeIntegrityError,
    )


@dataclass(frozen=True, slots=True)
class _PdfPages:
    """Sayfaları kopyalanacak tek kaynak: PDF baytları, alınan sayfalar ve mesajdaki konumu."""

    content: bytes
    pages: tuple[int, ...]
    where: str = ""


def _page_selection(pages: Sequence[int], *, subject: str) -> tuple[int, ...]:
    selected = tuple(pages)
    if not selected:
        raise ValueError(f"{subject} en az bir sayfa ister")
    if selected[0] < 0 or any(first >= second for first, second in pairwise(selected)):
        raise ValueError(f"{subject} sayfaları 0 veya büyük, artan sırada ve tekrarsız olmalı")
    return selected


def _file_kind(content: bytes) -> FileKind | None:
    try:
        return detect_file_kind(content)
    except UnsupportedFileTypeError:
        return None


def _merge_source_pdf(content: bytes, *, where: str) -> bytes:
    # PDF olduğu gibi; JPEG/PNG kayıpsız sarılır (§20.5 wrap_image yöntemi). Tür içerik imzasından.
    kind = _file_kind(content)
    if kind is FileKind.PDF:
        return content
    if kind not in (FileKind.JPEG, FileKind.PNG):
        raise MergeSourceError(f"merge kaynağı{where} PDF, JPEG ya da PNG değil")
    try:
        return _wrap_image_to_pdf(content)
    except _IMAGE_WRAP_ERRORS as exc:
        raise MergeSourceError(
            f"merge kaynağı{where} görüntüsü kayıpsız PDF'e sarılamadı: {type(exc).__name__}"
        ) from exc


def _copy_pages(
    sources: Sequence[_PdfPages],
    *,
    operation: str,
    source_error: type[Exception],
    integrity_error: type[Exception],
) -> bytes:
    """Kaynakların sayfalarını sırayla pypdf sayfa nesnesi olarak kopyalar ve çıktıyı doğrular.

    `extract` ve `merge`'ün ortak yöntemi (§20.5). Çıktı baytları döner; hiçbir şey yazılmaz.
    """
    writer = PdfWriter()
    expected: list[tuple[pymupdf.Document, int, str]] = []
    with ExitStack() as stack:
        for source in sources:
            document = stack.enter_context(
                _open_pdf(
                    source.content, operation=operation, where=source.where, error=source_error
                )
            )
            reader = _read_pdf(
                source.content,
                expected_page_count=document.page_count,
                operation=operation,
                where=source.where,
                error=source_error,
            )
            if source.pages[-1] >= document.page_count:
                raise source_error(
                    f"{operation} sayfası kaynakta yok: sayfa {source.pages[-1]}, "
                    f"kaynak{source.where} {document.page_count} sayfa"
                )
            for index in source.pages:
                writer.add_page(reader.pages[index])
                expected.append((document, index, source.where))
        buffer = BytesIO()
        writer.write(buffer)
        output = buffer.getvalue()
        _verify_pages(output, expected, operation=operation, error=integrity_error)
    return output


def _open_pdf(
    content: bytes, *, operation: str, where: str, error: type[Exception]
) -> pymupdf.Document:
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except RuntimeError as exc:
        raise error(f"{operation} kaynağı{where} açılamadı; PDF bozuk olabilir") from exc
    if document.needs_pass:
        document.close()
        raise error(f"{operation} kaynağı{where} parola korumalı")
    return document


def _read_pdf(
    content: bytes,
    *,
    expected_page_count: int,
    operation: str,
    where: str,
    error: type[Exception],
) -> PdfReader:
    try:
        reader = PdfReader(BytesIO(content))
        page_count = len(reader.pages)
    except PyPdfError as exc:
        raise error(f"{operation} kaynağı{where} pypdf ile okunamadı") from exc
    if page_count != expected_page_count:
        # Bozuk PDF'i iki kütüphane farklı onarabilir; o zaman plandaki sayfa dizini pypdf'te
        # başka bir sayfayı gösterebilir — tahmin edilmez.
        raise error(
            f"{operation} kaynağı{where} okuyucular arasında farklı sayfa sayısı veriyor: "
            f"MuPDF {expected_page_count}, pypdf {page_count}"
        )
    return reader


def _verify_pages(
    output: bytes,
    expected: Sequence[tuple[pymupdf.Document, int, str]],
    *,
    operation: str,
    error: type[Exception],
) -> None:
    try:
        output_document = pymupdf.open(stream=output, filetype="pdf")
    except RuntimeError as exc:
        raise error(f"{operation} çıktısı PDF olarak açılamadı") from exc
    with output_document:
        if output_document.page_count != len(expected):
            raise error(
                f"{operation} sayfa sayısı hatası: beklenen {len(expected)}, "
                f"çıktı {output_document.page_count}"
            )
        for output_index, (source_document, source_index, where) in enumerate(expected):
            if output_document[output_index].get_text() != source_document[source_index].get_text():
                raise error(
                    f"{operation} metin katmanı hatası: çıktı sayfası {output_index}, "
                    f"kaynak{where} sayfası {source_index}"
                )
