"""Stable exception classes and the execution error tuple."""

from __future__ import annotations

from enum import StrEnum


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


class PdfProtection(StrEnum):
    """Sayfaları kopyalanamayan şifreli PDF'in korunma biçimi (08.1.3, PLAN.md §D76)."""

    PASSWORD = "password"  # açmak için parola gerekiyor (MuPDF `needs_pass`)
    AES = "aes"  # sahip parolalı AES: parolasız açılır, pypdf `cryptography` olmadan çözemez


class EncryptedSourceError(ValueError):
    """extract/merge (08.1.3; K11, §D76): kaynak şifreli bir PDF, sayfaları kopyalanamıyor.

    Kaynak hatalarının şifre kaynaklı alt kümesidir (`ExtractEncryptedSourceError`,
    `MergeEncryptedSourceError`): bozuk PDF, okuyucular arasında sayfa sayısı uyuşmazlığı ve
    bütünlük hataları bu sınıftan değildir. Uygulama durmaz, öğe Unreadable kuyruğuna gider
    (`app.pipeline.orchestrate.execute_plan`). Şifre kaldırılmaz, dosya yeniden yazılmaz.

    `source_position` kaynağın plan öğesinin `sources` dizisindeki konumu, `protection` şifrenin
    biçimidir. Hedefe hiçbir şey yazılmaz.
    """

    def __init__(self, message: str, *, source_position: int, protection: PdfProtection) -> None:
        super().__init__(message)
        self.source_position = source_position
        self.protection = protection


class ExtractEncryptedSourceError(ExtractSourceError, EncryptedSourceError):
    """extract (07.2.1, 08.1.3): kaynak şifreli PDF; sayfaları kopyalanamıyor."""


class MergeEncryptedSourceError(MergeSourceError, EncryptedSourceError):
    """merge (07.3.1, 08.1.3): kaynaklardan biri şifreli PDF; sayfaları kopyalanamıyor."""


class WrapImageSourceError(ValueError):
    """wrap_image (07.4.1): kaynak okunabilir bir JPEG/PNG değil ya da görüntüsü img2pdf ile
    kayıpsız PDF'e sarılamıyor (açılamayan/bozuk dosya, aynalı/geçersiz EXIF yönelimi, >8 bit
    alfa kanalı — D17/D18).

    Hedefe hiçbir şey yazılmaz; belge kuyruğa gider, tahmin edilmez.
    """


class ExtractImageSourceError(ValueError):
    """extract_image (07.5.1): kaynak okunabilir bir PDF değil, istenen sayfa yok, sayfa tek tam
    sayfa gömülü görüntü değil (02.5.1) ya da gömülü görüntü JPEG/PNG olarak kayıpsız çıkarılamıyor
    (JPEG/PNG dışı biçim, 8 bitten derin örnek, MuPDF'in okuyamadığı görüntü — D19).

    Hedefe hiçbir şey yazılmaz; sayfa `render_image`'a düşmez (K12), belge kuyruğa gider.
    """


class ExtractImageIntegrityError(RuntimeError):
    """extract_image (§20.5, D19): çıkarılan baytlar gömülü görüntünün kendisi değil — JPEG gömülü
    akışın orijinal baytlarına, PNG gömülü görüntünün piksellerine birebir uymuyor.

    Çıktı yayınlanmaz; belge kuyruğa gider.
    """


class RenderImageSourceError(ValueError):
    """render_image (07.6.1): kaynak okunabilir bir PDF değil, açılamıyor (bozuk, parola korumalı)
    ya da istenen sayfa kaynakta yok.

    Hedefe hiçbir şey yazılmaz.
    """


class PlanItemReferenceError(LookupError):
    """07.7: `hazir` öğenin gösterdiği kayıt yok — çalışan (`employee.employee_id`), belge türü
    (`document_type_slug`) ya da kaynak dosya (`sources[i].file_id`; planın partisinde değilse de).

    Hiçbir kaynak okunmaz, hiçbir şey yazılmaz.
    """


class SourceIntegrityError(RuntimeError):
    """07.7 (K10): Inbox'taki kaynak dosyanın SHA-256'sı yüklemede kaydedilenle
    (`upload_files.sha256`) eşleşmiyor — orijinal değişmiş.

    İşlem yürütülmez, hiçbir şey yazılmaz.
    """


EXECUTION_ERRORS: tuple[type[Exception], ...] = (
    PlanItemReferenceError,
    SourceIntegrityError,
    PassthroughIntegrityError,
    ExtractSourceError,
    ExtractIntegrityError,
    DirectDocumentMergeError,
    MergeSourceError,
    MergeIntegrityError,
    WrapImageSourceError,
    ExtractImageSourceError,
    ExtractImageIntegrityError,
    RenderImageSourceError,
)

# Pipeline failure events persist the fully-qualified exception name; the public module path is
# part of that schema, so moving implementations must not rewrite existing/audited event values.
for _error_type in (
    *EXECUTION_ERRORS,
    EncryptedSourceError,
    ExtractEncryptedSourceError,
    MergeEncryptedSourceError,
):
    _error_type.__module__ = "app.pipeline.execute"
