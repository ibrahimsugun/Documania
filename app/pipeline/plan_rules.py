"""Pure operation selection and policy checks for plan decisions (PRD 06.2–06.4)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import ClassVar

from app.ai.photo_check import PhotoCheck, PhotoRuleResult, PhotoRuleVerdict
from app.catalog import CatalogEntry, Conversion, FileType, OutputFormat
from app.catalog.photo_rules import RESOLUTION_RULE, PhotoRuleSetting
from app.db.models import QueueKind, UploadFile
from app.pipeline.validate import file_types_text, unexpected_file_types
from app.storage import FileKind

from .plan_models import (
    Operation,
    PlanSource,
)


@dataclass(frozen=True, slots=True)
class OperationSource:
    """İşlem seçiminin okuduğu tek kaynak dosya (§20.3 girdileri).

    `kind` içerikten tespit edilen biçimdir (01.2.1); tanınmıyorsa `None`. `pages` öğenin bu
    dosyadan aldığı sayfalardır (`pages.index`); boşsa dosya bütün olarak alınır (Word/Excel, K2).
    `file_pages` dosyanın bütün sayfaları, `blank_pages` boş sayfaları (02.4.1 ve analizcinin boş
    dediği; başka belgeye ait sayılmaz), `single_image_pages` tek tam sayfa gömülü görüntüden oluşan
    sayfalarıdır (02.5.1).
    """

    file_id: int
    kind: FileKind | None
    pages: tuple[int, ...] = ()
    file_pages: frozenset[int] = frozenset()
    blank_pages: frozenset[int] = frozenset()
    single_image_pages: frozenset[int] = frozenset()

    @property
    def whole(self) -> bool:
        """Kapsama: dosyanın bütün sayfaları mı alınıyor; alınmayan tek sayfa alt küme yapar."""
        return not self.pages or frozenset(self.pages) == self.file_pages

    @property
    def contiguous(self) -> bool:
        """Ardışıklık (K5): alınan sayfaların arasında yalnız boş sayfa olabilir."""
        taken = frozenset(self.pages)
        if not taken:
            return True
        return taken.union(self.blank_pages).issuperset(range(min(taken), max(taken) + 1))


@dataclass(frozen=True, slots=True)
class SelectedOperation:
    """§20.3 satır 1–6'nın seçtiği işlem ve çıktının biçimi."""

    operation: Operation
    target_format: FileType


@dataclass(frozen=True, slots=True)
class NoApplicableOperation:
    """§20.3 satır 7: kaynak, kapsama ve biçim için tabloda uyan işlem yok; belge dönüştürülmez.

    Belge gerekçesiyle Unresolved'a gider. `sources` öğenin kaynaklarıdır; `target_format` türün
    hedef biçimidir (`keep`'te kaynakların ortak biçimi yoksa `None`). Gerekçe dosya kimliği, 1'den
    başlayan sayfa numarası ve biçim taşır; kişisel değer taşımaz.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED

    sources: tuple[OperationSource, ...]
    target_format: FileType | None

    @property
    def reason(self) -> str:
        label = "Kaynak" if len(self.sources) == 1 else "Kaynaklar"
        described = "; ".join(_operation_source_text(source) for source in self.sources)
        if self.target_format is not None:
            target = self.target_format.value
        elif any(source.kind is None for source in self.sources):
            target = "belirlenemedi (output_format: keep, kaynak biçimi tanınmadı)"
        else:
            target = "belirlenemedi (output_format: keep, kaynaklar farklı biçimde)"
        return (
            f"İşlem seçilemedi (06.2.1): {label}: {described}. Hedef biçim: {target}. §20.3'te bu "
            "kaynak, kapsama ve biçim için uyan fiziksel işlem yok; belge dönüştürülmez."
        )


def select_operation(
    sources: Sequence[OperationSource], *, output_format: OutputFormat
) -> SelectedOperation | NoApplicableOperation:
    """Öğenin fiziksel işlemini §20.3 karar tablosuyla seçer (06.2.1); kurallar modül açıklamasında.

    `sources` öğenin en az bir kaynak dosyasıdır (plandaki `sources` sırasıyla); `output_format`
    türün çıktı biçimidir. Saf işlevdir. Direkt Belge kuralı (06.3: `check_direct_file_types` önce,
    `check_direct_operation` sonra) ve dönüşüm izni (06.4.1: `check_conversion`) planlayıcıda
    uygulanır; bu işlev onlara bakmaz.
    """
    target = _target_format(sources, output_format)
    operation = _table_operation(sources, target)
    if operation is None or target is None:
        return NoApplicableOperation(tuple(sources), target)
    return SelectedOperation(operation, target)


def _target_format(
    sources: Sequence[OperationSource], output_format: OutputFormat
) -> FileType | None:
    # Hedef biçim türün `output_format`'ıdır; `keep` kaynakların ortak biçimidir.
    if output_format is not OutputFormat.KEEP:
        return FileType(output_format.value)
    kinds = {source.kind for source in sources}
    if len(kinds) != 1:
        return None
    (kind,) = kinds
    return None if kind is None else FileType(kind.value)


def _table_operation(
    sources: Sequence[OperationSource], target: FileType | None
) -> Operation | None:
    # §20.3 satırları sırayla, ilk uyan kazanır. Satır 3 dışındaki satırlar tek dosya ister; satır
    # 3'ün yeri sonucu değiştirmez.
    if len(sources) > 1:
        return Operation.MERGE if target is FileType.PDF else None  # satır 3
    (source,) = sources
    kind = None if source.kind is None else FileType(source.kind.value)
    single_page = len(source.pages) == 1
    if kind is not None and kind is target and source.whole:
        return Operation.PASSTHROUGH  # satır 1
    if kind is FileType.PDF and target is FileType.PDF and not source.whole and source.contiguous:
        return Operation.EXTRACT  # satır 2
    if kind in (FileType.JPEG, FileType.PNG) and single_page and target is FileType.PDF:
        return Operation.WRAP_IMAGE  # satır 4
    if kind is FileType.PDF and single_page and target is FileType.JPEG:
        if source.pages[0] in source.single_image_pages:
            return Operation.EXTRACT_IMAGE  # satır 5
        return Operation.RENDER_IMAGE  # satır 6
    return None  # satır 7


def operation_source(
    upload_file: UploadFile,
    source: PlanSource,
    *,
    kind: FileKind | None,
    blank_pages: frozenset[int],
) -> OperationSource:
    """Plan kaynağının §20.3 girdisi: `upload_file` kaynağın dosyası, `kind` içerikten tespit
    edilen biçimi (01.2.1), `blank_pages` dosyanın boş sayfalarıdır.

    Planlayıcı ve kuyruk ataması (08.2.1) kaynağı bu tek kuralla kurar. Dosyanın sayfaları ve tek
    tam sayfa gömülü görüntülü sayfaları (02.5.1) `pages` satırlarından okunur. Saf işlevdir.
    """
    pages = upload_file.pages
    return OperationSource(
        file_id=source.file_id,
        kind=kind,
        pages=source.pages,
        # Satırı açılmamış sayfa da dosyanındır: kapsamayı alt kümeye çevirir.
        file_pages=frozenset(page.index for page in pages).union(
            range(upload_file.page_count or 0)
        ),
        blank_pages=blank_pages,
        single_image_pages=frozenset(
            page.index for page in pages if page.has_single_embedded_image
        ),
    )


def _pages_text(file_id: int, pages: Iterable[int]) -> str:
    # Sayfa numarası kullanıcının gördüğü gibi 1'den başlar.
    return f"dosya {file_id}, sayfa " + ", ".join(str(index + 1) for index in pages)


def _operation_source_text(source: OperationSource) -> str:
    kind = "biçimi tanınmadı" if source.kind is None else source.kind.value
    if not source.pages:
        return f"dosya {source.file_id} ({kind}, bütün dosya)"
    if source.whole:
        coverage = "dosyanın tüm sayfaları"
    elif source.contiguous:
        coverage = "dosyanın ardışık alt kümesi"
    else:
        coverage = "dosyanın ardışık olmayan alt kümesi"
    return f"{_pages_text(source.file_id, source.pages)} ({kind}, {coverage})"


DIRECT_OPERATIONS = frozenset({Operation.PASSTHROUGH, Operation.EXTRACT})


@dataclass(frozen=True, slots=True)
class DirectFileTypeMismatch:
    """§20.4.1 (06.3.2): Direkt Belge kaynağının biçimi türün `expected_file_types`'ında yok.

    İşlem seçilmez ve uygulanmaz; belge dönüştürülerek kurtarılmaz (K3), gerekçesiyle Unresolved'a
    gider. `received` beklenmeyen kaynakların biçimleridir (tanınmayan biçim `None`), kaynak
    sırasıyla ve tekrarsız. Gerekçe kişisel değer taşımaz.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED
    check: ClassVar[str] = "file_type"

    expected_file_types: tuple[FileType, ...]
    received: tuple[FileType | None, ...]

    @property
    def reason(self) -> str:
        return (
            f"Direkt Belge: beklenen dosya türü {file_types_text(self.expected_file_types)}, gelen "
            f"{file_types_text(self.received)}. Uygun formatta yeniden gönderin."
        )


@dataclass(frozen=True, slots=True)
class DirectOperationForbidden:
    """§20.4 (06.3.1): seçilen işlem Direkt Belge türünde yasak.

    Birleştirme, sarma, gömülü görüntü çıkarma ve render belgeyi başka kaynaklardan kurar ya da
    biçimini değiştirir (K3); işlem uygulanmaz, belge gerekçesiyle Unresolved'a gider.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED
    check: ClassVar[str] = "operation"

    operation: Operation

    @property
    def reason(self) -> str:
        return f"Direkt Belge: {self.operation.value} bu tür için yapılamaz."


def check_direct_file_types(
    sources: Sequence[OperationSource], *, entry: CatalogEntry
) -> DirectFileTypeMismatch | None:
    """Direkt Belge format kontrolü (06.3.2, §20.4.1); işlem seçiminden önce yapılır.

    `direct: false` türde ya da her kaynağın içerikten tespit edilen biçimi (01.2.1) türün
    `expected_file_types`'ında olduğunda `None`. Tanınmayan biçim beklenen türlerden değildir. Saf
    işlevdir. Direkt Belge türünün `file_type` doğrulamasıdır (06.5.1); öteki türlerde aynı kontrol
    `app.pipeline.validate.check_file_type`'tır.
    """
    if not entry.direct:
        return None
    received = unexpected_file_types(sources, entry=entry)
    if not received:
        return None
    return DirectFileTypeMismatch(entry.expected_file_types, received)


def check_direct_operation(
    operation: Operation, *, entry: CatalogEntry
) -> DirectOperationForbidden | None:
    """Direkt Belge izin matrisi (06.3.1, §20.4); §20.3'ün seçtiği işleme uygulanır.

    `direct: true` türde yalnız `passthrough` ve `extract` izinlidir. `direct: false` türde matris
    her işleme izin verir; dönüşümün türün `allowed_conversions`'ında olması 06.4.1'in kontrolüdür
    (`check_conversion`). Saf işlevdir.
    """
    if not entry.direct or operation in DIRECT_OPERATIONS:
        return None
    return DirectOperationForbidden(operation)


CONVERSION_OPERATIONS = frozenset(
    {Operation.MERGE, Operation.WRAP_IMAGE, Operation.EXTRACT_IMAGE, Operation.RENDER_IMAGE}
)


@dataclass(frozen=True, slots=True)
class ConversionNotAllowed:
    """§20.3 (06.4.1): seçilen dönüşüm türün `allowed_conversions`'ında yok (K12).

    İşlem uygulanmaz ve başka bir satıra düşülmez; belge dönüştürülmez, gerekçesiyle Unresolved'a
    gider. `allowed_conversions` türün listesidir (boş olabilir). Gerekçe kişisel değer taşımaz.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED

    operation: Operation
    allowed_conversions: tuple[Conversion, ...]

    @property
    def reason(self) -> str:
        allowed = "/".join(conversion.value for conversion in self.allowed_conversions) or "boş"
        return (
            f"Dönüşüm izni yok (06.4.1): {self.operation.value} bu türün izinli dönüşümleri "
            f"arasında değil (allowed_conversions: {allowed}). Belge dönüştürülmez."
        )


def check_conversion(operation: Operation, *, entry: CatalogEntry) -> ConversionNotAllowed | None:
    """Dönüşüm izni kontrolü (06.4.1, §20.3); Direkt Belge matrisinden sonra uygulanır.

    `passthrough` ve `extract` dönüşüm değildir, her türde `None`. Satır 3–6'nın işlemi türün
    `allowed_conversions`'ında değilse ret. Saf işlevdir.
    """
    if operation not in CONVERSION_OPERATIONS:
        return None
    if Conversion(operation.value) in entry.allowed_conversions:
        return None
    return ConversionNotAllowed(operation, entry.allowed_conversions)


@dataclass(frozen=True, slots=True)
class PhotoRulesNotMet:
    """11.7.1: fotoğraf türündeki adayın açık kurallarından biri `fail` ya da değerlendirilmemiş.

    Belge gerekçesiyle Unresolved'a gider; fotoğraf değiştirilmez (11.7.2). `failed` ihlal edilen
    kuralların, `unchecked` sonucu olmayan kuralların metnidir, ikisi de katalog sırasıyla. Gerekçe
    kural adlarını taşır (çözünürlükte ölçülen boyutla); kişisel değer ve yapay zekâ notu taşımaz.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED

    failed: tuple[str, ...]
    unchecked: tuple[str, ...]

    @property
    def reason(self) -> str:
        parts: list[str] = []
        if self.failed:
            parts.append(f"Fotoğraf kurallarına uymuyor (11.7.1): {'; '.join(self.failed)}.")
        if self.unchecked:
            parts.append(
                f"Fotoğraf kuralları değerlendirilmedi (11.7.1): {', '.join(self.unchecked)}."
            )
        return " ".join(parts)


def check_photo_rules(
    rules: Sequence[PhotoRuleSetting], checks: Sequence[PhotoCheck | None]
) -> PhotoRulesNotMet | None:
    """Fotoğraf türündeki adayın açık kurallarını sayfalarının saklanan kontrolleriyle karşılaştırır
    (11.7.1); saf işlevdir.

    `rules` türün planlama anındaki açık kurallarıdır (katalog sırasıyla), `checks` adayın
    sayfalarının kontrolleri, sayfa sırasıyla (`None`: kontrol yok ya da okunamadı). Bir sayfada
    `fail` olan kural ihlaldir; bir sayfada sonucu olmayan kural değerlendirilmemiştir. İkisi de
    yoksa `None` — `unsure` yalnız nottur, kapalı kurala bakılmaz.
    """
    failed: list[str] = []
    unchecked: list[str] = []
    for rule in rules:
        verdicts = [None if check is None else check.verdict(rule.id) for check in checks]
        violation = next(
            (
                verdict
                for verdict in verdicts
                if verdict is not None and verdict.result is PhotoRuleResult.FAIL
            ),
            None,
        )
        if violation is not None:
            failed.append(_photo_rule_text(rule, violation))
        elif any(verdict is None for verdict in verdicts):
            unchecked.append(rule.label)
    if not failed and not unchecked:
        return None
    return PhotoRulesNotMet(tuple(failed), tuple(unchecked))


def _photo_rule_text(rule: PhotoRuleSetting, verdict: PhotoRuleVerdict) -> str:
    # Çözünürlüğün notu sistemin kendi ölçümüdür (`measure_resolution`); öteki notlar yapay
    # zekânındır ve gerekçeye girmez.
    if rule.id == RESOLUTION_RULE and verdict.note is not None:
        return f"{rule.label} ({verdict.note.rstrip('.')})"
    return rule.label
