"""Image wrapping, embedded-image extraction, and PDF-page rendering."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image

from app.pipeline.render import single_full_page_image_xref
from app.storage import FileKind, StoredFile, write_file

from .execute_errors import (
    ExtractImageIntegrityError,
    ExtractImageSourceError,
    RenderImageSourceError,
    WrapImageSourceError,
)
from .execute_image_utils import (
    _IMAGE_WRAP_ERRORS,
    _wrap_image_to_pdf,
)
from .execute_pdf import (
    _file_kind,
    _open_pdf,
)


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
    return write_file(destination, _wrap_image_output(source))


def _wrap_image_output(source: Path) -> bytes:
    content = source.read_bytes()
    if _file_kind(content) not in (FileKind.JPEG, FileKind.PNG):
        raise WrapImageSourceError("wrap_image kaynağı JPEG ya da PNG değil")
    try:
        return _wrap_image_to_pdf(content)
    except _IMAGE_WRAP_ERRORS as exc:
        raise WrapImageSourceError(
            f"wrap_image kaynağı görüntüsü kayıpsız PDF'e sarılamadı: {type(exc).__name__}"
        ) from exc


def execute_extract_image(source: Path, destination: Path, *, page: int) -> StoredFile:
    """Kaynak PDF'in `page` sayfasındaki gömülü görüntüyü orijinal baytlarıyla çıkarır (07.5.1,
    §20.5).

    `page` plan kaynağının tek sayfasıdır (`PlanSource.pages`, 0 tabanlı `pages.index`); negatifse
    `ValueError`. Dosya çok sayfalı olabilir (S3/S4).

    Yöntem PyMuPDF'tir: sayfadaki görüntü nesnesinin `xref`'i 02.5.1'in kuralıyla
    (`single_full_page_image_xref`) bulunur ve `doc.extract_image(xref)` çağrılır; dönen `image`
    baytları diske olduğu gibi yazılır. Sayfa tek tam sayfa gömülü görüntü değilse — çıkan
    görüntünün sayfada görünenle aynı olduğu kesin değilse — `ExtractImageSourceError`; sayfa
    render edilmez (K12: başka satıra düşülmez). Pillow ile açıp kaydetme, yeniden boyutlandırma,
    kalite ayarı yoktur (K11).

    Çıkan biçim `ext`'ten okunur ve yalnız JPEG ya da PNG kabul edilir; başka biçim (JPEG 2000) ya
    da 8 bitten derin örnekli görüntü (MuPDF PNG'ye 8 bite indirerek yazar)
    `ExtractImageSourceError` (D19). Yayınlanan dosyanın uzantısı bu gerçek biçimdir (§20.5):
    `destination`'ın dizini ve gövdesi korunur, uzantısı `jpeg`/`png` olur — planın
    `target_format`'ı `jpeg`'dir, gömülü PNG `.png` olarak yazılır. Yayınlanan yol
    `StoredFile.path`'tir.

    Doğrulama yayından önce bellekte yapılır (D19): baytların içerik imzası `ext`'in biçimi olmalı;
    JPEG baytları PDF'teki gömülü akışın ham baytlarıyla **birebir aynı**, PNG'nin pikselleri
    MuPDF'in gömülü görüntüden çözdüğü piksellerle **birebir aynı** olmalıdır. Değilse — PyMuPDF
    CMYK JPEG'i yeniden kodlar, CMYK pikselleri RGB'ye çevirir — `ExtractImageIntegrityError`.
    Hatada hedefe hiçbir şey yazılmaz; hedef zaten varsa `write_file`'ın `FileExistsError`'ı
    (üzerine yazma yok).

    Kaynak PDF değilse, açılamıyorsa (bozuk, parola korumalı), sayfa kaynakta yoksa ya da MuPDF
    sayfayı veya görüntüyü okuyamıyorsa da `ExtractImageSourceError`.
    """
    image, kind = _extract_image_output(source, page)
    return write_file(destination.with_suffix(f".{kind.value}"), image)


def _extract_image_output(source: Path, page: int) -> tuple[bytes, FileKind]:
    if page < 0:
        raise ValueError("extract_image sayfası 0 veya büyük olmalı")
    content = source.read_bytes()
    # MuPDF JPEG/PNG baytlarını da tek sayfalık belge olarak açar; tür önce içerik imzasından.
    if _file_kind(content) is not FileKind.PDF:
        raise ExtractImageSourceError("extract_image kaynağı PDF değil")
    with _open_pdf(
        content, operation="extract_image", where="", error=ExtractImageSourceError
    ) as document:
        if page >= document.page_count:
            raise ExtractImageSourceError(
                f"extract_image sayfası kaynakta yok: sayfa {page}, "
                f"kaynak {document.page_count} sayfa"
            )
        try:
            return _extract_embedded_image(document, page)
        except pymupdf.mupdf.FzErrorBase as exc:
            raise ExtractImageSourceError(
                f"extract_image sayfası {page} MuPDF ile okunamadı: {type(exc).__name__}"
            ) from exc


_EXTRACTED_IMAGE_KINDS: dict[str, FileKind] = {"jpeg": FileKind.JPEG, "png": FileKind.PNG}

_PIXMAP_MODES: dict[int, str] = {1: "L", 3: "RGB"}


def _extract_embedded_image(document: pymupdf.Document, page: int) -> tuple[bytes, FileKind]:
    """Sayfanın tek tam sayfa gömülü görüntüsünü `extract_image` ile çıkarır ve doğrular (§20.5).

    Çıkan baytlar ve biçimleri döner; hiçbir şey yazılmaz.
    """
    xref = single_full_page_image_xref(document[page])
    if xref is None:
        raise ExtractImageSourceError(
            f"extract_image sayfası {page} tek tam sayfa gömülü görüntü değil (02.5.1); "
            "sayfa render edilmez (K12)"
        )
    extracted = document.extract_image(xref)
    kind = _EXTRACTED_IMAGE_KINDS.get(extracted["ext"])
    if kind is None:
        raise ExtractImageSourceError(
            f"extract_image gömülü görüntüsü JPEG ya da PNG değil: {extracted['ext']}"
        )
    image = extracted["image"]
    if _file_kind(image) is not kind:
        raise ExtractImageIntegrityError(f"extract_image baytlarının biçimi {kind.value} değil")
    if kind is FileKind.JPEG:
        # JPEG gömülü akışın kendisidir: PDF'teki ham baytlar birebir, yeniden kodlama yok.
        if image != document.xref_stream_raw(xref):
            raise ExtractImageIntegrityError(
                "extract_image JPEG baytları gömülü akışın orijinal baytları değil"
            )
        return image, kind
    # PNG akışta dosya olarak yoktur; MuPDF çözdüğü pikselleri yazar. 8 bitten derin örnek 8 bite
    # indirilir — kayıptır ve piksel karşılaştırması onu göremez (iki taraf da 8 bit).
    if extracted["bpc"] > 8:
        raise ExtractImageSourceError(
            f"extract_image gömülü görüntüsü {extracted['bpc']} bit; PNG'ye kayıpsız yazılamaz"
        )
    if not _png_matches_pixels(image, pymupdf.Pixmap(document, xref)):
        raise ExtractImageIntegrityError(
            "extract_image PNG pikselleri gömülü görüntünün piksellerine uymuyor"
        )
    return image, kind


def _png_matches_pixels(image: bytes, reference: pymupdf.Pixmap) -> bool:
    """PNG'nin pikselleri MuPDF'in gömülü görüntüden çözdüğü piksellerle birebir aynı mı.

    Pillow yalnız ölçer (boyut, kip, örnekler); görüntü kaydedilmez. MuPDF ICCBased gri görüntüyü
    RGB PNG'ye yazar — o zaman her kanal gri değerin kendisi olmalıdır. Başka her kip farkı
    (CMYK'nin RGB'ye çevrilmesi gibi) uyuşmazlıktır.
    """
    with Image.open(BytesIO(image)) as decoded:
        if decoded.size != (reference.width, reference.height):
            return False
        if decoded.mode == _PIXMAP_MODES.get(reference.n):
            return decoded.tobytes() == reference.samples
        if reference.n == 1 and decoded.mode == "RGB":
            return all(channel.tobytes() == reference.samples for channel in decoded.split())
        return False


def execute_render_image(
    source: Path, destination: Path, *, page: int, dpi: int, jpeg_quality: int
) -> StoredFile:
    """Kaynak PDF'in `page` sayfasını sabit çözünürlükte JPEG'e rasterleştirir (07.6.1, §20.5).

    Gömülü tek görüntü yoksa son çaredir ve **kayıplıdır**: sayfa `page.get_pixmap(dpi=…)` ile
    sabit çözünürlükte render edilir ve JPEG olarak kaydedilir. `dpi` ve `jpeg_quality` çağıranın
    verdiği yapılandırma değerleridir (`Settings.render_image_dpi`,
    `Settings.render_image_jpeg_quality`); burada sabit yazılmaz.

    `page` plan kaynağının tek sayfasıdır (`PlanSource.pages`, 0 tabanlı `pages.index`); negatifse
    `ValueError`. Dosya çok sayfalı olabilir (S3/S4); yalnız planlanan sayfa render edilir, ötekiler
    okunmaz.

    Kaynak PDF değilse, açılamıyorsa (bozuk, parola korumalı) ya da sayfa kaynakta yoksa
    `RenderImageSourceError`; hedefe hiçbir şey yazılmaz. Hedef zaten varsa `write_file`'ın
    `FileExistsError`'ı (üzerine yazma yok).
    """
    return write_file(
        destination, _render_image_output(source, page, dpi=dpi, jpeg_quality=jpeg_quality)
    )


def _render_image_output(source: Path, page: int, *, dpi: int, jpeg_quality: int) -> bytes:
    if page < 0:
        raise ValueError("render_image sayfası 0 veya büyük olmalı")
    content = source.read_bytes()
    # MuPDF JPEG/PNG baytlarını da tek sayfalık belge olarak açar; tür önce içerik imzasından.
    if _file_kind(content) is not FileKind.PDF:
        raise RenderImageSourceError("render_image kaynağı PDF değil")
    with _open_pdf(
        content, operation="render_image", where="", error=RenderImageSourceError
    ) as document:
        if page >= document.page_count:
            raise RenderImageSourceError(
                f"render_image sayfası kaynakta yok: sayfa {page}, "
                f"kaynak {document.page_count} sayfa"
            )
        pixmap = document[page].get_pixmap(dpi=dpi, alpha=False)
        return pixmap.tobytes("jpeg", jpg_quality=jpeg_quality)
