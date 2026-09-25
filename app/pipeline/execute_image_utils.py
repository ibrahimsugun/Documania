"""Shared lossless image-to-PDF wrapping for image and merge operations."""

from __future__ import annotations

import img2pdf

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

    Aynı görüntü her seferinde aynı baytlara sarılır (07.8.1): img2pdf'in kendi yazıcısı
    (`Engine.internal`) kimlik (`/ID`) yazmaz ve `nodate` oluşturma/değişiklik tarihini dışarıda
    bırakır. Varsayılan pikepdf yazıcısı her çağrıda başka `/ID` üretir — img2pdf 0.6.3 pikepdf
    sürümünü dize olarak karşılaştırdığı için (`"10…" >= "6.2.0"` yanlış) belirleyici kimlik
    istenmez. Görüntü verisinin taşınması yazıcıdan bağımsızdır.
    """
    return img2pdf.convert(content, engine=img2pdf.Engine.internal, nodate=True)
