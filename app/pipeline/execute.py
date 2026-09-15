"""Uygulayıcı — planın seçtiği fiziksel işlemler (PRD 07.x, §20.5).

Bu modül planlayıcının (`app/pipeline/plan.py`) `operation` alanına yazdığı kararı yürütür;
işlemi yeniden seçmez ya da izinlerini yeniden denetlemez (06.2.1–06.4.1 planlayıcının işidir).
Tek istisna K3'tür: `merge` Direkt Belge türünde çalışmaz (07.3.1) — plan dondurulduktan sonra
tür Direkt Belge yapılmış olsa bile belge başka kaynaklardan kurulmaz.
Ortak kural (K11): hiçbir işlem içeriği üretmez, kırpmaz ya da değiştirmez.

Şimdilik `passthrough` (07.1.1), `extract` (07.2.1), `merge` (07.3.1) ve `wrap_image` (07.4.1)
uygulanır. Öteki işlemler (`extract_image`, `render_image`) ve ortak çıktı yazma — köken kaydı,
`documents` satırı, `OUTPUT_SAVED` olayı, `Alinan` kopyası (07.7.1) — sonraki görevlerdedir.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from io import BytesIO
from itertools import pairwise
from pathlib import Path

import img2pdf
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


class DirectDocumentMergeError(ValueError):
    """merge (07.3.1, §20.4, K3): Direkt Belge türünde belge başka kaynaklardan kurulmaz.

    Hiçbir kaynak okunmaz, hedefe hiçbir şey yazılmaz.
    """


class MergeSourceError(ValueError):
    """merge (07.3.1): bir kaynak okunabilir bir PDF/JPEG/PNG değil, görüntüsü kayıpsız sarılamıyor
    ya da istenen sayfa kaynakta yok.

    Hedefe hiçbir şey yazılmaz.
    """


class MergeIntegrityError(RuntimeError):
    """merge (07.3.1, §20.5): çıktının sayfa sayısı ya da bir sayfasının metin katmanı karşılık
    gelen kaynak sayfaya uymuyor.

    Sayfa nesnesi kopyasında bu beklenmez; çıktı yayınlanmaz.
    """


class WrapImageSourceError(ValueError):
    """wrap_image (07.4.1): kaynak okunabilir bir JPEG/PNG değil ya da görüntüsü img2pdf ile
    kayıpsız PDF'e sarılamıyor (açılamayan/bozuk dosya, aynalı/geçersiz EXIF yönelimi, >8 bit
    alfa kanalı — D17/D18).

    Hedefe hiçbir şey yazılmaz; belge kuyruğa gider, tahmin edilmez.
    """


@dataclass(frozen=True, slots=True)
class MergeSource:
    """merge'ün tek kaynağı: dosya ve ondan alınan sayfalar (`PlanSource.pages`).

    Sayfalar 0 tabanlı, artan ve tekrarsızdır; JPEG/PNG kaynağın tek sayfası `0`'dır.
    """

    path: Path
    pages: tuple[int, ...]


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
    selected = _page_selection(pages, subject="extract")
    content = source.read_bytes()
    # MuPDF JPEG/PNG baytlarını da tek sayfalık belge olarak açar; tür önce içerik imzasından.
    if _file_kind(content) is not FileKind.PDF:
        raise ExtractSourceError("extract kaynağı PDF değil")
    output = _copy_pages(
        [_PdfPages(content, selected)],
        operation="extract",
        source_error=ExtractSourceError,
        integrity_error=ExtractIntegrityError,
    )
    return write_file(destination, output)


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
    output = _copy_pages(
        pdf_pages,
        operation="merge",
        source_error=MergeSourceError,
        integrity_error=MergeIntegrityError,
    )
    return write_file(destination, output)


def execute_wrap_image(source: Path, destination: Path) -> StoredFile:
    """Kaynak JPEG/PNG'yi kayıpsız biçimde tek sayfalık bir PDF'e sarar (07.4.1, §20.5).

    Yöntem `img2pdf.convert()` — `merge`'ün görüntü kaynağıyla ortak (`_wrap_image_to_pdf`,
    D17): JPEG akışı yeniden kodlanmadan PDF içine gömülür; PNG pikselleri kayıpsız taşınır, 8
    bit alfa kanalı ayrı bir `/SMask` görüntüsünde saklanır. EXIF yönelimi img2pdf varsayılanıyla
    yalnız sayfanın `/Rotate` değerine yazılır, piksel döndürülmez.

    **Beyaz zemine düzleştirme uygulanmaz.** §20.5 img2pdf'in alfa kanallı PNG'leri reddettiğini
    ve bu durumda düzleştirme yapılacağını söyler; D17 img2pdf 0.6.3'ün yalnız >8 bit alfada
    (`AlphaChannelError`) reddettiğini bulmuştur. Düzleştirme bir piksel dönüşümüdür; K11 içeriği
    hiçbir koşulda değiştirmez ve izinli işlemler listesinde alfa kompozisyonu yoktur —
    `MASTER-PROMPT.md` §2 çelişki sırasında kilitli kural PRD metninin önündedir (D18). Bu yüzden
    img2pdf'in sarılamadığı görüntü (>8 bit alfa dahil) düzleştirilmeye çalışılmaz;
    `WrapImageSourceError` verir ve belge kuyruğa gider (tahmin edilmez).

    Kaynak JPEG/PNG değilse de `WrapImageSourceError`. Hedef zaten varsa `write_file`'ın
    `FileExistsError`'ı (üzerine yazma yok).
    """
    content = source.read_bytes()
    if _file_kind(content) not in (FileKind.JPEG, FileKind.PNG):
        raise WrapImageSourceError("wrap_image kaynağı JPEG ya da PNG değil")
    try:
        output = _wrap_image_to_pdf(content)
    except _IMAGE_WRAP_ERRORS as exc:
        raise WrapImageSourceError(
            f"wrap_image kaynağı görüntüsü kayıpsız PDF'e sarılamadı: {type(exc).__name__}"
        ) from exc
    return write_file(destination, output)


# img2pdf'in kayıpsız saramadığı görüntü için verdiği hatalar; ortak bir taban sınıfları yok.
_IMAGE_WRAP_ERRORS = (
    img2pdf.ImageOpenError,
    img2pdf.ExifOrientationError,
    img2pdf.AlphaChannelError,
    img2pdf.JpegColorspaceError,
    img2pdf.UnsupportedColorspaceError,
    img2pdf.NegativeDimensionError,
    img2pdf.PdfTooLargeError,
)


def _wrap_image_to_pdf(content: bytes) -> bytes:
    """JPEG/PNG baytlarını img2pdf ile kayıpsız tek sayfalık PDF'e sarar (§20.5 wrap_image yöntemi).

    `merge` ve `wrap_image`'in ortak çekirdeği (D17/D18): sarılamayan görüntü için
    `_IMAGE_WRAP_ERRORS` olduğu gibi yükselir, çağıran kendi hata türüne çevirir.
    """
    return img2pdf.convert(content)


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
