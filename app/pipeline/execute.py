"""Uygulayıcı — planın seçtiği fiziksel işlemler (PRD 07.x, §20.5).

Bu modül planlayıcının (`app/pipeline/plan.py`) `operation` alanına yazdığı kararı yürütür;
işlemi yeniden seçmez ya da izinlerini yeniden denetlemez (06.2.1–06.4.1 planlayıcının işidir).
Tek istisna K3'tür: `merge` Direkt Belge türünde çalışmaz (07.3.1) — plan dondurulduktan sonra
tür Direkt Belge yapılmış olsa bile belge başka kaynaklardan kurulmaz.
Ortak kural (K11): hiçbir işlem içeriği üretmez, kırpmaz ya da değiştirmez.

İşlemler: `passthrough` (07.1.1), `extract` (07.2.1), `merge` (07.3.1), `wrap_image` (07.4.1),
`extract_image` (07.5.1), `render_image` (07.6.1). `execute_<işlem>` işlevleri yalnız işlemin
çekirdeğidir: verilen hedefe yazar, veritabanına ve olay logına dokunmaz.

**Ortak çıktı yazma (07.7.1, 07.7.2; §20.5).** `execute_ready_item` planın tek `hazir` öğesini
uygular:

1. Öğenin çalışanı, belge türü ve kaynak dosyaları veritabanından bulunur; dosya planın partisinin
   olmalıdır (`PlanItemReferenceError`). Inbox'taki her kaynağın SHA-256'sı yüklemede kaydedilenle
   aynı olmalıdır (K10, `SourceIntegrityError`). İkisi de hiçbir şey yazılmadan reddeder.
2. İşlem plandaki `operation`'dır, yeniden seçilmez; `merge`'ün Direkt Belge bekçisi türün güncel
   `direct` bayrağıdır. Çıktı çalışanın `Hazir/` klasörüne planın `target_name`'iyle **atomik**
   yazılır (00.4.4): gövde doluysa K8 sıra eki diskte seçilir (`-2`, `-3`; `write_sequenced`),
   `extract_image` uzantıyı gerçek biçimden alır (§20.5). İşlem hatası olduğu gibi yükselir; hiçbir
   çıktı, kopya, satır ya da olay kalmaz — kuyruğa çevirmek çağıranındır (08.1, 09.2).
3. Çıktı yayınlandıktan sonra (belge çözüldü, K10) her kaynak dosya `sources` sırasıyla çalışanın
   `Alinan/` klasörüne kopyalanır; aynı SHA-256 orada varsa tekrar kopyalanmaz (`copy_to_received`).
   Aynı çalışana yazan uygulamalar (idempotenlik denetimi, çıktı, kopya) PostgreSQL'de çalışan
   başına işlem ömürlü advisory kilitle sıraya girer; SQLite işlemi `BEGIN IMMEDIATE` ile yazma
   kilidini zaten tutar.
4. `documents` satırı (`active`) yazılır: çalışan, tür, veri köküne göreli yol, gerçek biçim, sıra
   numarası, plan kimliği ve köken — `source_refs_json` öğenin `sources`'udur (`file_id` ve 0
   tabanlı `pages`; bütün dosyada `[]`), sırası korunur (K15, R13).
5. İşlemin §8.3 olayı (`PAGE_EXTRACTED`, `PAGES_MERGED`, `IMAGE_WRAPPED`, `IMAGE_EXTRACTED`,
   `IMAGE_RENDERED`; `passthrough`'un türü yok) ve `OUTPUT_SAVED` yazılır. İkisi de partinin,
   ilk kaynağın dosyası ve ilk sayfasıyla, `document_id` ve `employee_id` sütunlarıyla; veri köken
   bilgisidir — `item_id`, `plan_id`, `sources`; `OUTPUT_SAVED` ayrıca tür, işlem, biçim, sıra
   numarası, çıktının SHA-256'sı ve kaynak başına Alinan sonucu (`file_id`, `copied`). Mesaj yok;
   yol ve ad kişi adı taşıdığı için olaya girmez (CONVENTIONS §6).

Oturum commit edilmez. Dosya sistemi işleme bağlı değildir: işlem geri alınırsa yayınlanan çıktı ve
kopya diskte kalır.

**İdempotenlik (07.8.1, S18).** Aynı plan ikinci kez uygulanınca ikinci dosya üretilmez:

- Öğe, planın kimliği ve kaynaklarıyla tanınır: `documents.plan_id` planın, `source_refs_json`
  öğenin `sources`'u olan satır o öğenin çıktısıdır (`executed_document`). Plan bir sayfayı en
  fazla bir öğeye bağladığı için (`PlanDocument`) bu eşleşme tekildir; satırın durumu ve sahibi
  sonradan değişmiş olabilir (eski sürüm, arşiv, başka çalışana taşıma — K16, K18), yine o öğenin
  çıktısıdır. Böyle satır varsa öğe yeniden uygulanmaz: kaynak okunmaz, işlem yürümez, diske ve
  `documents`'a hiçbir şey yazılmaz; `OUTPUT_SKIPPED` o satırla loglanır ve satır döner.
- Uygulama geri alınmışsa (işlem commit edilmeden öldü ya da geri alındı) çıktı diskte kalmış,
  satırı yoktur. Yeniden uygulamada işlem yürür; aynı gövdeyle ve aynı SHA-256'yla `Hazir/`'da
  duran ve hiçbir `documents` satırının göstermediği dosya varsa yeni dosya yazılmaz, o dosya
  çıktı olarak kaydedilir (`find_sequenced`) — Alinan tekilliği gibi doğruluk kaynağı disktir.
  Bu yüzden işlemlerin çıktısı aynı girdiden aynı baytlardır; `wrap_image` tarih ve rastgele
  kimlik taşımasın diye img2pdf'in kendi yazıcısıyla ve tarihsiz sarılır. Başka bir satırın
  gösterdiği dosya — başka öğenin ya da eski sürümün çıktısı, içeriği aynı olsa da — benimsenmez;
  o durumda K8 eki yine diskte seçilir.
- Denetim ile yayın aynı çalışan kilidinin altındadır (madde 3): aynı öğeyi eşzamanlı uygulayan
  ikinci işlem ilki commit edilince onun satırını görür.
"""

from __future__ import annotations

import zlib
from collections.abc import Iterator, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from io import BytesIO
from itertools import pairwise
from pathlib import Path

import img2pdf
import pymupdf
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    KnownDocumentType,
    Plan,
    UploadFile,
)
from app.events import EventType, record_event
from app.pipeline.plan import Operation, PlanItem, Route
from app.pipeline.render import single_full_page_image_xref
from app.storage import (
    ContentMismatchError,
    DataLayout,
    FileKind,
    ReceivedCopy,
    StoredFile,
    UnsupportedFileTypeError,
    copy_file,
    copy_to_received,
    detect_file_kind,
    find_sequenced,
    iter_file_chunks,
    sha256_bytes,
    sha256_file,
    split_document_filename,
    write_file,
    write_sequenced,
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


@dataclass(frozen=True, slots=True)
class ExecutedItem:
    """`execute_ready_item` sonucu: çıktı belgesi satırı, yayınlanan çıktı ve kaynakların Alinan
    kopyaları (`sources` sırasıyla).

    Öğe bu planla daha önce uygulanmışsa (07.8.1) `document` o uygulamanın satırıdır, `output`
    `None` ve `received` boştur: bu çağrı diske dokunmadı.
    """

    document: Document
    output: StoredFile | None
    received: tuple[ReceivedCopy, ...]

    @property
    def applied(self) -> bool:
        """Öğe bu çağrıda uygulandı; `False` ise önceki uygulamanın çıktısı döndü."""
        return self.output is not None


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
    return _verified_passthrough(copy_file(source, destination), expected_sha256)


def _verified_passthrough(stored: StoredFile, expected_sha256: str) -> StoredFile:
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

    Aynı görüntü her seferinde aynı baytlara sarılır (07.8.1): img2pdf'in kendi yazıcısı
    (`Engine.internal`) kimlik (`/ID`) yazmaz ve `nodate` oluşturma/değişiklik tarihini dışarıda
    bırakır. Varsayılan pikepdf yazıcısı her çağrıda başka `/ID` üretir — img2pdf 0.6.3 pikepdf
    sürümünü dize olarak karşılaştırdığı için (`"10…" >= "6.2.0"` yanlış) belirleyici kimlik
    istenmez. Görüntü verisinin taşınması yazıcıdan bağımsızdır.
    """
    return img2pdf.convert(content, engine=img2pdf.Engine.internal, nodate=True)


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


# `extract_image`'in `ext`'i → kabul edilen çıktı biçimi (D19). PDF'teki görüntü akışından PyMuPDF
# yalnız `jpeg` (DCTDecode), `jpx` (JPXDecode) ya da çözülmüş piksellerden `png` döndürür.
_EXTRACTED_IMAGE_KINDS: dict[str, FileKind] = {"jpeg": FileKind.JPEG, "png": FileKind.PNG}

# MuPDF pixmap bileşen sayısı → aynı örnekleri taşıyan PNG kipi.
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


# §8.3: işlemin kendi olayı. `passthrough`'un olay türü yoktur; çıktısı yalnız `OUTPUT_SAVED` atar.
_OPERATION_EVENTS: dict[Operation, EventType] = {
    Operation.EXTRACT: EventType.PAGE_EXTRACTED,
    Operation.MERGE: EventType.PAGES_MERGED,
    Operation.WRAP_IMAGE: EventType.IMAGE_WRAPPED,
    Operation.EXTRACT_IMAGE: EventType.IMAGE_EXTRACTED,
    Operation.RENDER_IMAGE: EventType.IMAGE_RENDERED,
}

# Aynı çalışana yazan uygulamalar — idempotenlik denetimi, çıktının yayını, Alinan kopyası — sıraya
# girer (PostgreSQL advisory kilidinin ad alanı).
_EMPLOYEE_LOCK_NAMESPACE = "belgeee.employees.outputs"


def execute_ready_item(
    session: Session,
    layout: DataLayout,
    plan: Plan,
    item: PlanItem,
    *,
    render_image_dpi: int,
    render_image_jpeg_quality: int,
) -> ExecutedItem:
    """Planın `hazir` öğesini uygular: çıktıyı `Hazir/`'a atomik yazar, kökenini kaydeder ve
    kaynakları `Alinan/`'a kopyalar (07.7.1, 07.7.2; §20.5). Sözleşmesi modül açıklamasındadır.

    İdempotenttir (07.8.1): öğe bu planla daha önce uygulanmışsa (`executed_document`) kaynak
    okunmaz, hiçbir şey yazılmaz; `OUTPUT_SKIPPED` loglanır ve o uygulamanın satırı döner
    (`ExecutedItem.applied` yanlış). Geri alınmış bir uygulamadan diskte kalan aynı çıktı ikinci
    kez yazılmaz, kaydedilir.

    `item` `plan`'ın doğrulanmış (`read_plan`) öğesidir. `render_image_dpi` ve
    `render_image_jpeg_quality` `render_image` işleminin yapılandırma değerleridir
    (`Settings.render_image_dpi`, `Settings.render_image_jpeg_quality`).

    `hazir` olmayan ya da türsüz öğe, tek kaynaklı işlemde (`merge` dışındakiler) birden çok kaynak
    ve `extract_image`/`render_image`'da tek olmayan sayfa `ValueError`. Bunlarda, kayıt ve kaynak
    hatalarında ve işlem hatalarında (`passthrough`'un bütünlük hatası dahil, yayından önce
    denetlenir) hiçbir şey yazılmaz. Oturum commit edilmez.
    """
    operation, target_name = item.operation, item.target_name
    if (
        item.route is not Route.READY
        or item.document_type_slug is None
        or operation is None
        or target_name is None
        or item.employee.employee_id is None
    ):
        raise ValueError("Yalnız çalışanı, türü, işlemi ve hedefi olan hazir öğe uygulanır")
    employee = session.get(Employee, item.employee.employee_id)
    if employee is None:
        raise PlanItemReferenceError(f"{item.item_id} öğesinin çalışanı kayıtlı değil")
    document_type = session.get(KnownDocumentType, item.document_type_slug)
    if document_type is None:
        raise PlanItemReferenceError(f"{item.item_id} öğesinin belge türü katalogda yok")

    _lock_employee_outputs(session, employee.id)
    source_refs = _source_refs(item)
    first = item.sources[0]
    origin = {
        "upload_id": plan.upload_id,
        "file_id": first.file_id,
        "page_index": first.pages[0] if first.pages else None,
    }
    provenance = {"item_id": item.item_id, "plan_id": plan.id, "sources": source_refs}
    existing = executed_document(session, plan, item)
    if existing is not None:
        record_event(
            session,
            EventType.OUTPUT_SKIPPED,
            **origin,
            document_id=existing.id,
            employee_id=existing.employee_id,
            data=provenance,
        )
        return ExecutedItem(existing, None, ())

    sources = _item_sources(session, layout, plan, item)
    ready = _ready_output(
        operation,
        target_name,
        sources,
        direct=document_type.direct,
        render_image_dpi=render_image_dpi,
        render_image_jpeg_quality=render_image_jpeg_quality,
    )
    output = _publish_ready_output(
        session, layout, ready, directory=layout.ready_dir(employee.folder_name)
    )
    received = tuple(
        copy_to_received(layout, employee.folder_name, source.path, sha256=source.sha256)
        for source in sources
    )

    output_format = output.path.suffix.removeprefix(".")
    document = Document(
        employee_id=employee.id,
        type_slug=document_type.slug,
        path=layout.relative(output.path),
        format=output_format,
        sequence_no=output.sequence_no,
        plan_id=plan.id,
        source_refs_json=source_refs,
        status=DocumentStatus.ACTIVE.value,
    )
    session.add(document)
    session.flush()

    operation_event = _OPERATION_EVENTS.get(operation)
    if operation_event is not None:
        record_event(
            session,
            operation_event,
            **origin,
            document_id=document.id,
            employee_id=employee.id,
            data=provenance,
        )
    record_event(
        session,
        EventType.OUTPUT_SAVED,
        **origin,
        document_id=document.id,
        employee_id=employee.id,
        data={
            **provenance,
            "document_type_slug": document_type.slug,
            "operation": operation.value,
            "format": output_format,
            "sequence_no": output.sequence_no,
            "sha256": output.sha256,
            "received": [
                {"file_id": source.file_id, "copied": received_copy.copied}
                for source, received_copy in zip(item.sources, received, strict=True)
            ],
        },
    )
    return ExecutedItem(document, output, received)


def executed_document(session: Session, plan: Plan, item: PlanItem) -> Document | None:
    """Öğenin bu planla önceki uygulamasının çıktı satırı; uygulanmamışsa `None` (07.8.1).

    Satır planın kimliği (`documents.plan_id`) ve öğenin kaynaklarıyla (`source_refs_json`) bulunur;
    plan bir sayfayı en fazla bir öğeye bağladığı için eşleşme tekildir. Satırın durumuna ve
    sahibine bakılmaz: eski sürüm, arşivlenmiş ya da başka çalışana taşınmış çıktı da öğenin
    uygulandığını gösterir. `item` `plan`'ın öğesidir.
    """
    source_refs = _source_refs(item)
    documents = session.scalars(
        select(Document).where(Document.plan_id == plan.id).order_by(Document.id)
    )
    return next(
        (document for document in documents if document.source_refs_json == source_refs), None
    )


def _source_refs(item: PlanItem) -> list[dict[str, object]]:
    # K15 köken: öğenin `sources`'u olduğu gibi — `file_id`, 0 tabanlı `pages`, plan sırası.
    return [source.model_dump(mode="json") for source in item.sources]


@dataclass(frozen=True, slots=True)
class _ItemSource:
    """Öğenin doğrulanmış tek kaynağı: Inbox yolu, alınan sayfalar ve yüklemede kaydedilen hash."""

    path: Path
    pages: tuple[int, ...]
    sha256: str


def _item_sources(
    session: Session, layout: DataLayout, plan: Plan, item: PlanItem
) -> list[_ItemSource]:
    files: list[UploadFile] = []
    for position, source in enumerate(item.sources):
        upload_file = session.get(UploadFile, source.file_id)
        if upload_file is None or upload_file.upload_id != plan.upload_id:
            raise PlanItemReferenceError(
                f"{item.item_id} öğesinin sources[{position}] dosyası planın partisinde yok"
            )
        files.append(upload_file)
    sources: list[_ItemSource] = []
    for position, (source, upload_file) in enumerate(zip(item.sources, files, strict=True)):
        path = layout.resolve(upload_file.stored_path)
        if sha256_file(path) != upload_file.sha256:
            raise SourceIntegrityError(
                f"{item.item_id} öğesinin sources[{position}] kaynağı yüklemede kaydedilen "
                "SHA-256'yı taşımıyor (K10)"
            )
        sources.append(_ItemSource(path, source.pages, upload_file.sha256))
    return sources


def _lock_employee_outputs(session: Session, employee_id: str) -> None:
    # İdempotenlik denetimi (07.8.1) ile çıktının yayını ve `copy_to_received`'ın hash taraması ile
    # yayını arasına aynı çalışana yazan başka işlem girmesin; aynı öğeyi eşzamanlı uygulayan ikinci
    # işlem ilkinin satırını görür. SQLite işlemi `BEGIN IMMEDIATE` ile yazma kilidini zaten baştan
    # tutar.
    if session.get_bind().dialect.name == "postgresql":
        key = zlib.crc32(f"{_EMPLOYEE_LOCK_NAMESPACE}.{employee_id}".encode())
        session.execute(select(func.pg_advisory_xact_lock(key)))


@dataclass(frozen=True, slots=True)
class _ReadyOutput:
    """Yayınlanacak çıktı: K8 gövdesi, gerçek uzantısı, içeriği ve içeriğin SHA-256'sı ile boyu.

    `expected_sha256` doluysa içerik akıştır ve yayından önce o hash'le karşılaştırılır
    (`passthrough`).
    """

    stem: str
    extension: str
    content: bytes | Iterator[bytes]
    sha256: str
    size: int
    expected_sha256: str | None = None


def _ready_output(
    operation: Operation,
    target_name: str,
    sources: Sequence[_ItemSource],
    *,
    direct: bool,
    render_image_dpi: int,
    render_image_jpeg_quality: int,
) -> _ReadyOutput:
    """İşlemi yürütür ve çıktısını planın adıyla yayına hazırlar; diske yazmaz."""
    stem, extension = split_document_filename(target_name)
    if operation is Operation.MERGE:
        merged = _merge_output(
            [MergeSource(source.path, source.pages) for source in sources], direct=direct
        )
        return _in_memory(stem, extension, merged)
    if len(sources) != 1:
        raise ValueError(f"{operation.value} tek kaynak ister: {len(sources)} kaynak")
    (source,) = sources
    if operation is Operation.PASSTHROUGH:
        # Kaynak belleğe alınmaz, akışla kopyalanır; içeriği yüklemede kaydedilen ve az önce
        # doğrulanan hash'tir.
        return _ReadyOutput(
            stem,
            extension,
            iter_file_chunks(source.path),
            sha256=source.sha256,
            size=source.path.stat().st_size,
            expected_sha256=source.sha256,
        )
    if operation is Operation.EXTRACT:
        return _in_memory(stem, extension, _extract_output(source.path, source.pages))
    if operation is Operation.WRAP_IMAGE:
        return _in_memory(stem, extension, _wrap_image_output(source.path))
    if len(source.pages) != 1:
        raise ValueError(f"{operation.value} tek sayfa ister: {len(source.pages)} sayfa")
    (page,) = source.pages
    if operation is Operation.EXTRACT_IMAGE:
        image, kind = _extract_image_output(source.path, page)
        return _in_memory(stem, kind.value, image)
    rendered = _render_image_output(
        source.path, page, dpi=render_image_dpi, jpeg_quality=render_image_jpeg_quality
    )
    return _in_memory(stem, extension, rendered)


def _in_memory(stem: str, extension: str, content: bytes) -> _ReadyOutput:
    return _ReadyOutput(stem, extension, content, sha256=sha256_bytes(content), size=len(content))


def _publish_ready_output(
    session: Session, layout: DataLayout, output: _ReadyOutput, *, directory: Path
) -> StoredFile:
    """Çıktıyı `directory`'ye planın adıyla ve K8 sıra ekiyle atomik yayınlar.

    Aynı içerik bu gövdeyle diskte duruyor ve hiçbir `documents` satırı onu göstermiyorsa — geri
    alınmış bir uygulamanın çıktısı — yeni dosya yazılmaz, o dosya döner (07.8.1).
    """
    for candidate in find_sequenced(
        directory, output.stem, output.extension, sha256=output.sha256, size=output.size
    ):
        if not _is_recorded(session, layout, candidate.path):
            return candidate
    try:
        return write_sequenced(
            directory,
            output.stem,
            output.extension,
            output.content,
            expected_sha256=output.expected_sha256,
        )
    except ContentMismatchError as exc:
        # Beklenen hash'i yalnız `passthrough` verir.
        raise PassthroughIntegrityError(f"passthrough bütünlük hatası: {exc}") from exc


def _is_recorded(session: Session, layout: DataLayout, path: Path) -> bool:
    recorded = select(Document.id).where(Document.path == layout.relative(path)).limit(1)
    return session.scalar(recorded) is not None


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
