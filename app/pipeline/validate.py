"""Doğrulayıcı seti — PRD 06.5.1, 06.5.2 (§20.1.6, §20.1.7; K1, K3, K5).

Plan öğesi uygulanmadan önce mekanik kurallardan geçer: yapay zekânın okuması ve karar motorunun
hükmü burada yeniden sınanır. 06.5.1'in yedi doğrulayıcısı, plandaki adları ve sırasıyla
(`ValidationName`):

1. **`required_fields`** — türün zorunlu alanlarının hepsi okunaklı (K1). Hükmü 04.4.1'in
   okunaklılık kapısıdır (`IllegibleRequiredFields`) ve kuyruğu Unreadable'dır: 06.5.2'nin genel
   Unresolved'ı bu doğrulayıcıya uygulanmaz (PLAN.md C21).
2. **`page_count`** — adayın sayfa sayısı türün `expected_pages` aralığında. Hükmü 04.5.1'indir
   (`PageCountViolation`, gruplama işaretler); aralık yoksa sınır yoktur.
3. **`sides`** — `front_back` türdeki belge önce bir ön, sonra bir arka yüzden oluşur (04.1.2):
   yalnız ön ya da yalnız arka yüz, ters sıra ve yüzü ön/arka okunmamış sayfa geçmez. Tek yüzlü
   türde yüz sınır değildir.
4. **`direct_single_source`** — Direkt Belge türünde (K3) çıktı tek kaynak dosyanın ardışık
   sayfalarıdır. Ardışıklık K5'tir: alınan sayfaların arasında yalnız boş sayfa olabilir (C31).
   `direct: false` türde koşul yoktur.
5. **`file_type`** — her kaynağın içerikten tespit edilen biçimi (01.2.1) türün
   `expected_file_types`'ındadır; tanınmayan biçim beklenen türlerden değildir. Belge dönüştürülerek
   kurtarılmaz. Direkt Belge türünde aynı hüküm §20.4.1'in format kontrolüdür; planlayıcı onu o
   bölümün gerekçesiyle yazar (`app.pipeline.plan.check_direct_file_types`).
6. **`mrz_checksum`** — sayfalardaki MRZ'nin kontrol haneleri tutar; kontrol hanesi tutmayan MRZ
   geçersiz sayılır (05.3.2). §20.1.7'ye göre alan haneleri, isteğe bağlı veri hanesi (tümüyle
   dolgu alanda `<` da `0` da geçerlidir) ve bileşik hane sayılır. İzin verilmeyen karakterli MRZ
   (§20.1.2) geçersizdir: haneleri doğrulanamaz, geçmez. Hiçbir biçime uymayan satırlar MRZ
   değildir (§20.1.1, hata değil); MRZ'siz sayfa ve kendini boş ya da okunamaz veren sayfanın
   MRZ'si (C21) doğrulayıcıya girmez. MRZ ile görünen metnin çelişkisi doğrulama hatası değil,
   bilgi notudur. Doğrulayıcı okumayı değiştirmez: hanesi tutmayan alanın okunamadı sayılması ve
   numaranın temiz sayılmaması 05.3.3'ün ve §20.2.3'ündür.
7. **`dob_plausible`** — belgeden okunan doğum tarihi geçmişte ve referans güne göre 16–90 yaştadır
   (tamamlanmış yıl, iki uç dahil; §20.1.6). Tarih kişi anahtarınınkidir (05.4): MRZ önce okunur,
   MRZ yüzyılı §20.1.6 ile seçilmiştir. Okunmamış ya da sayfalar arasında çelişen tarih
   doğrulayıcıya girmez — çelişki eşleştirmenin hükmüdür (D8). Başarısızlık Unreadable değildir:
   tarih okunmuştur ama inanılır değildir.

Her doğrulayıcı saf işlevdir: geçerse `None`, geçmezse kuyruğu ve gerekçesi olan bir hüküm döner
(`ValidationFailure`). Gerekçe alan adı, dosya kimliği, 1'den başlayan sayfa numarası ve biçim
taşır; kişisel değer (ad, numara, tarih, yaş) taşımaz (CONVENTIONS §6). Hangi öğenin hangi
doğrulayıcılardan geçtiği, gerekçelerin rotaya nasıl bağlandığı ve başarısızlığın olayı
(`VALIDATION_FAILED`) planlayıcının işidir (`app/pipeline/plan.py`, 06.5.2).
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import ClassVar, Protocol

from app.ai.schemas import Side
from app.catalog import CatalogEntry, FileType, Sides
from app.db.models import QueueKind
from app.matching.mrz import MrzStatus, apply_mrz_priority
from app.pipeline.group import DocumentCandidate, PageCountViolation, PageRef
from app.pipeline.legibility import IllegibleRequiredFields, LegibilityCheck
from app.storage import FileKind

# `dob_plausible` yaş aralığı (§20.1.6): tamamlanmış yıl, iki uç dahil.
MIN_AGE = 16
MAX_AGE = 90
# `sides`: `front_back` türdeki belgenin yüzleri, belgedeki sırasıyla.
FRONT_BACK_SIDES = (Side.FRONT, Side.BACK)


class ValidationName(enum.StrEnum):
    """Plan JSON `validations[].name` (§8.5); tanım sırası 06.5.1'in ve plandaki sıradır."""

    REQUIRED_FIELDS = "required_fields"
    PAGE_COUNT = "page_count"
    SIDES = "sides"
    DIRECT_SINGLE_SOURCE = "direct_single_source"
    FILE_TYPE = "file_type"
    MRZ_CHECKSUM = "mrz_checksum"
    DOB_PLAUSIBLE = "dob_plausible"


class ValidationFailure(Protocol):
    """Geçmeyen doğrulamanın hükmü: öğeyi gönderdiği kuyruk ve kişisel değer taşımayan gerekçe."""

    @property
    def queue(self) -> QueueKind: ...

    @property
    def reason(self) -> str: ...


@dataclass(frozen=True, slots=True)
class Validation:
    """Tek doğrulayıcının sonucu; `failure` boşsa doğrulama geçti."""

    name: ValidationName
    failure: ValidationFailure | None = None

    @property
    def ok(self) -> bool:
        return self.failure is None


class ValidatedSource(Protocol):
    """Kaynak doğrulayıcılarının okuduğu kaynak dosya (`app.pipeline.plan.OperationSource`).

    `kind` içerikten tespit edilen biçimdir, tanınmıyorsa `None`; `pages` alınan sayfalardır (boşsa
    dosya bütün olarak alınır); `contiguous` alınan sayfaların arasında boş sayfa dışında sayfa
    olmadığını söyler (K5).
    """

    @property
    def file_id(self) -> int: ...

    @property
    def kind(self) -> FileKind | None: ...

    @property
    def pages(self) -> tuple[int, ...]: ...

    @property
    def contiguous(self) -> bool: ...


# --- required_fields, page_count ---------------------------------------------------------------


def check_required_fields(legibility: LegibilityCheck | None) -> IllegibleRequiredFields | None:
    """`required_fields` (K1): `check_legibility`'nin zorunlu alan hükmü, kuyruğu Unreadable.

    Katalog türünde olmayan adayın (`None`) zorunlu alanları bilinmez; planlayıcı onu doğrulamaz.
    """
    return None if legibility is None else legibility.illegible_fields


def check_page_count(candidate: DocumentCandidate) -> PageCountViolation | None:
    """`page_count`: gruplamanın 04.5.1 hükmü; türün aralığı yoksa sınır yoktur.

    Gruplama sayfa sayısını ardışıklık (04.2.1) ya da belirsiz eşleştirme (04.3.2) hükmü taşımayan
    katalog türündeki adaya uygular; planlayıcı da yalnız o adayı doğrular.
    """
    return candidate.page_count_violation


# --- sides -------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SidesMismatch:
    """`sides` (04.1.2): `front_back` türdeki aday önce bir ön, sonra bir arka yüzden oluşmuyor.

    `pages` adayın sayfaları (dosya kimliği ve dosyadaki sırası), `sides` analizde okunan
    yüzleridir; ikisi de adaydaki sırayla. Aday otomatik tamamlanmaz, Unresolved'a gider.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED

    pages: tuple[PageRef, ...]
    sides: tuple[Side, ...]

    @property
    def reason(self) -> str:
        faces = "; ".join(
            f"dosya {page.file_id}, sayfa {page.index + 1}: {side.value}"
            for page, side in zip(self.pages, self.sides, strict=True)
        )
        return (
            "Yüz doğrulaması (06.5.1, sides): tür önce bir ön, sonra bir arka yüz bekliyor "
            f"(front, back); bu adayın yüzleri: {faces}."
        )


def check_sides(candidate: DocumentCandidate, *, entry: CatalogEntry) -> SidesMismatch | None:
    """`sides`: `front_back` türde adayın yüzleri tam olarak `(front, back)`; tek yüzlüde geçer."""
    if entry.sides is not Sides.FRONT_BACK or candidate.sides == FRONT_BACK_SIDES:
        return None
    pages = tuple(PageRef(page.file_id, page.index) for page in candidate.pages)
    return SidesMismatch(pages, candidate.sides)


# --- direct_single_source ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DirectSourceNotSingle:
    """`direct_single_source` (K3, K5): Direkt Belge tek kaynak dosyanın ardışık sayfaları değil.

    `file_ids` belgenin kaynak dosyalarıdır (plandaki sırayla); `scattered` sayfaları ardışık
    olmayan kaynakların dosya kimliği ve alınan sayfalarıdır (`pages.index`). Belge başka
    kaynaklardan kurulmaz; gerekçesiyle Unresolved'a gider.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED

    file_ids: tuple[int, ...]
    scattered: tuple[tuple[int, tuple[int, ...]], ...] = ()

    @property
    def reason(self) -> str:
        findings: list[str] = []
        if len(self.file_ids) != 1:
            findings.append(f"belgenin sayfaları {len(self.file_ids)} kaynak dosyadan geliyor")
        findings.extend(
            f"{_pages_text(file_id, pages)} ardışık değil" for file_id, pages in self.scattered
        )
        return (
            "Direkt Belge tek kaynak doğrulaması (06.5.1, direct_single_source): çıktı tek kaynak "
            f"dosyanın ardışık sayfalarından oluşur (K3); {'; '.join(findings)}."
        )


def check_direct_single_source(
    sources: Sequence[ValidatedSource], *, entry: CatalogEntry
) -> DirectSourceNotSingle | None:
    """`direct_single_source`: Direkt Belge'nin tek kaynağı ve o kaynakta ardışık sayfaları.

    `sources` öğenin kaynaklarıdır. `direct: false` türde geçer.
    """
    if not entry.direct:
        return None
    scattered = tuple((source.file_id, source.pages) for source in sources if not source.contiguous)
    if len(sources) == 1 and not scattered:
        return None
    return DirectSourceNotSingle(tuple(source.file_id for source in sources), scattered)


# --- file_type ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FileTypeMismatch:
    """`file_type`: kaynak biçimi türün `expected_file_types`'ında yok; belge dönüştürülmez.

    `received` beklenmeyen kaynakların biçimleridir (tanınmayan biçim `None`), kaynak sırasıyla ve
    tekrarsız. Gerekçesiyle Unresolved'a gider.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED

    expected_file_types: tuple[FileType, ...]
    received: tuple[FileType | None, ...]

    @property
    def reason(self) -> str:
        return (
            f"Dosya türü doğrulaması (06.5.1, file_type): beklenen dosya türü "
            f"{file_types_text(self.expected_file_types)}, gelen {file_types_text(self.received)}. "
            "Uygun formatta yeniden gönderin."
        )


def unexpected_file_types(
    sources: Iterable[ValidatedSource], *, entry: CatalogEntry
) -> tuple[FileType | None, ...]:
    """Biçimi türün `expected_file_types`'ında olmayan kaynakların biçimleri.

    Kaynak sırasıyla ve tekrarsızdır; tanınmayan biçim `None`dır ve hiçbir zaman beklenmez.
    """
    received: dict[FileType | None, None] = {}
    for source in sources:
        kind = None if source.kind is None else FileType(source.kind.value)
        if kind not in entry.expected_file_types:
            received[kind] = None
    return tuple(received)


def check_file_type(
    sources: Sequence[ValidatedSource], *, entry: CatalogEntry
) -> FileTypeMismatch | None:
    """`file_type`: her kaynağın biçimi türün `expected_file_types`'ında (her türde)."""
    received = unexpected_file_types(sources, entry=entry)
    if not received:
        return None
    return FileTypeMismatch(entry.expected_file_types, received)


def file_types_text(file_types: Iterable[FileType | None]) -> str:
    """Gerekçedeki biçim listesi: `/` ile (virgül gerekçenin cümlesiyle karışır, C32)."""
    return "/".join(
        "tanınmayan biçim" if file_type is None else file_type.value for file_type in file_types
    )


# --- mrz_checksum ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MrzPageFailure:
    """Tek sayfanın geçmeyen MRZ'si.

    `failed_checks` tutmayan hanelerdir, MRZ sırasıyla (`document_number`, `date_of_birth`,
    `expiry_date`, `optional_data`, `composite`); `invalid` MRZ'de izin verilmeyen karakter
    kaldığını, hanelerin hesaplanamadığını söyler (§20.1.2).
    """

    page: PageRef
    failed_checks: tuple[str, ...] = ()
    invalid: bool = False

    @property
    def text(self) -> str:
        where = f"dosya {self.page.file_id}, sayfa {self.page.index + 1}"
        if self.invalid:
            return f"{where}: izin verilmeyen karakter var, kontrol haneleri doğrulanamadı"
        return f"{where}: tutmayan kontrol haneleri {', '.join(self.failed_checks)}"


@dataclass(frozen=True, slots=True)
class MrzChecksumFailure:
    """`mrz_checksum` (05.3.2, §20.1.7): adayın en az bir sayfasındaki MRZ geçersiz.

    `pages` geçmeyen sayfalardır, adaydaki sırayla. Gerekçe alan adı taşır, MRZ değeri taşımaz;
    belge gerekçesiyle Unresolved'a gider.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED

    pages: tuple[MrzPageFailure, ...]

    @property
    def reason(self) -> str:
        described = "; ".join(page.text for page in self.pages)
        return (
            f"MRZ kontrol hanesi doğrulaması (06.5.1, mrz_checksum): {described}. Kontrol hanesi "
            "tutmayan MRZ geçersiz sayılır."
        )


def check_mrz_checksum(candidate: DocumentCandidate, *, today: date) -> MrzChecksumFailure | None:
    """`mrz_checksum`: adayın her sayfasındaki MRZ'nin kontrol haneleri tutuyor.

    Sayfalar `apply_mrz_priority` ile okunur (idempotent; önceliği uygulanmış sayfa değişmez).
    `today` MRZ doğum tarihinin yüzyılını seçer (§20.1.6); hanelerin sonucunu değiştirmez.
    """
    failures: list[MrzPageFailure] = []
    for page in candidate.pages:
        resolution = apply_mrz_priority(page.analysis, today=today)
        ref = PageRef(page.file_id, page.index)
        if resolution.status is MrzStatus.INVALID:
            failures.append(MrzPageFailure(ref, invalid=True))
        elif resolution.mrz is not None and resolution.mrz.failed_checks:
            failures.append(MrzPageFailure(ref, failed_checks=resolution.mrz.failed_checks))
    return MrzChecksumFailure(tuple(failures)) if failures else None


# --- dob_plausible -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ImplausibleDateOfBirth:
    """`dob_plausible` (§20.1.6): okunan doğum tarihi inanılır değil; tarih yanlış okunmuş olabilir.

    `future` tarihin referans günden önce olmadığını, değilse yaşın 16–90 dışında kaldığını söyler.
    Tarih ve yaş taşınmaz. Belge Unreadable değil, gerekçesiyle Unresolved'a gider.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED

    future: bool

    @property
    def reason(self) -> str:
        if self.future:
            finding = "geçmişte değil"
        else:
            finding = f"referans güne göre {MIN_AGE}–{MAX_AGE} yaş aralığı dışında"
        return (
            f"Doğum tarihi doğrulaması (06.5.1, dob_plausible): okunan doğum tarihi {finding}; "
            "tarih yanlış okunmuş olabilir."
        )


def check_dob_plausible(
    date_of_birth: date | None, *, today: date
) -> ImplausibleDateOfBirth | None:
    """`dob_plausible`: doğum tarihi `today`'den önce ve o gün 16–90 yaş (iki uç dahil).

    `date_of_birth` kişi anahtarının tarihidir (05.4); `None` (okunmamış ya da çelişen) geçer.
    `today` referans gündür — planda partinin alındığı gün (06.1.2), saat değil.
    """
    if date_of_birth is None:
        return None
    if date_of_birth >= today:
        return ImplausibleDateOfBirth(future=True)
    if MIN_AGE <= _age(date_of_birth, today) <= MAX_AGE:
        return None
    return ImplausibleDateOfBirth(future=False)


def _age(date_of_birth: date, today: date) -> int:
    # Tamamlanmış yıl: yıl dönümü `today`'e gelmemişse bir eksik (29 Şubat'ta doğan 28 Şubat'ta).
    birthday_ahead = (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
    return today.year - date_of_birth.year - birthday_ahead


def _pages_text(file_id: int, pages: Iterable[int]) -> str:
    # Sayfa numarası kullanıcının gördüğü gibi 1'den başlar.
    return f"dosya {file_id}, sayfa " + ", ".join(str(index + 1) for index in pages)
