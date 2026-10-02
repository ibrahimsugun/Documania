"""Profilden yüklemede kişi denetiminin uyarısı — PRD 10.5.5 (PLAN.md §C83).

Bağlam çalışanlı partinin güncel planında `context_person` doğrulaması geçmeyen öğeler — bağlam
çalışanına ait görünmeyen belgeler — yükleme ilerleme/sonuç görünümünde (10.2.2), parti detayında
(10.3.1) ve bağlam çalışanının profil sayfasında (10.5.1) büyük kırmızı kutuyla gösterilir:
"⚠ Bu profile ait olmayan N belge bulundu — profile eklenmedi". Her satır belge türünü, belgede
okunan adı ↔ profil adını ve kuyruk öğesinin bağlantısını taşır.

Belgede okunan ad görünüm anında veritabanından çizilir: öğenin sayfalarının saklanan
analizlerinden planlayıcının kişi anahtarıyla (`build_person_key`; MRZ yüzyılı partinin alındığı
gün). Latin yazım önce gelir, orijinal yazım yanında durur (05.2.2). Ad gerekçeye ve loga
yazılmaz. Kaynak partinin güncel planıdır — eski sürümün öğesi sayılmaz (K18); saklanan plan
doğrulanamıyorsa (`PlanIntegrityError`) kutu çizilmez, parti sayfası nedeni zaten gösterir.

Parti görünümleri partinin bütün bu öğelerini gösterir, çözülmüşü "çözüldü" işaretiyle. Profil
sayfasındaki kutu yalnız çözülmemiş kuyruk öğelerini sayar: öğe çözülünce (08.2.1 atama) satırı
kalkar, satır kalmayınca kutu da. Hiçbiri yazmaz.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.ai.schemas import PageAnalysis
from app.db.models import Employee, KnownDocumentType, QueueItem, Upload
from app.i18n import ngettext
from app.matching.match import PersonKey, build_person_key
from app.pipeline.analyze import PageAnalysisStatus
from app.pipeline.orchestrate import current_plan
from app.pipeline.plan import PlanIntegrityError, PlanItem, read_plan
from app.pipeline.validate import ValidationName

# Kaynak dildeki başlık; panel `title`'ı isteğin dilinde, sayıya göre çoğul biçimle gösterir.
WARNING_TITLE = "⚠ Bu profile ait olmayan {count} belge bulundu — profile eklenmedi"
NO_VALUE = "—"


@dataclass(frozen=True, slots=True)
class ForeignDocumentRow:
    """Bağlam çalışanına ait görünmeyen tek belge: türü, belgede okunan ad, profil adı ve kuyruk
    öğesi (henüz kuyruğa alınmadıysa `None`)."""

    upload_id: str
    type_name: str
    document_name: str
    profile_name: str
    queue_item_id: int | None
    resolved: bool


@dataclass(frozen=True, slots=True)
class ForeignDocumentsWarning:
    """Kutunun içeriği; satırı olmayan uyarı çizilmez (`None` döner)."""

    employee_id: str
    profile_name: str
    rows: tuple[ForeignDocumentRow, ...]

    @property
    def title(self) -> str:
        count = len(self.rows)
        title = ngettext(
            "⚠ Bu profile ait olmayan {count} belge bulundu — profile eklenmedi",
            "⚠ Bu profile ait olmayan {count} belge bulundu — profile eklenmedi",
            count,
        )
        return title.format(count=count)


def upload_warning(session: Session, upload: Upload) -> ForeignDocumentsWarning | None:
    """Partinin güncel planında bağlam çalışanına ait görünmeyen belgeler (10.2.2, 10.3.1).

    Bağlamsız partide, planı olmayan ya da doğrulanamayan partide ve böyle belge yoksa `None`.
    """
    employee = _context_employee(session, upload)
    if employee is None:
        return None
    rows = _upload_rows(session, upload, employee)
    return _warning(employee, rows)


def profile_warning(session: Session, employee_id: str) -> ForeignDocumentsWarning | None:
    """Çalışanın profilinden (bağlamıyla) yüklenmiş partilerde çözülmemiş kuyruk öğesi olan, ona
    ait görünmeyen belgeler (10.5.1); yoksa `None`. Partiler alındıkları sırayla."""
    employee = session.get(Employee, employee_id)
    if employee is None:
        return None
    pending = exists().where(QueueItem.upload_id == Upload.id, QueueItem.resolved_at.is_(None))
    uploads = session.scalars(
        select(Upload)
        .where(Upload.context_employee_id == employee_id, pending)
        .order_by(Upload.created_at, Upload.id)
    )
    rows = [
        row
        for upload in uploads
        for row in _upload_rows(session, upload, employee)
        if row.queue_item_id is not None and not row.resolved
    ]
    return _warning(employee, rows)


def _context_employee(session: Session, upload: Upload) -> Employee | None:
    if upload.context_employee_id is None:
        return None
    return session.get(Employee, upload.context_employee_id)


def _warning(employee: Employee, rows: list[ForeignDocumentRow]) -> ForeignDocumentsWarning | None:
    if not rows:
        return None
    return ForeignDocumentsWarning(employee.id, _profile_name(employee), tuple(rows))


def _upload_rows(session: Session, upload: Upload, employee: Employee) -> list[ForeignDocumentRow]:
    plan = current_plan(session, upload)
    if plan is None:
        return []
    try:
        document = read_plan(plan)
    except PlanIntegrityError:
        return []
    foreign = [item for item in document.items if _is_foreign(item)]
    if not foreign:
        return []
    queued = {
        row.plan_item_id: row
        for row in session.scalars(
            select(QueueItem)
            .where(QueueItem.upload_id == upload.id, QueueItem.plan_id == plan.id)
            .order_by(QueueItem.id)
        )
    }
    profile_name = _profile_name(employee)
    rows: list[ForeignDocumentRow] = []
    for item in foreign:
        queue_item = queued.get(item.item_id)
        key = build_person_key(_analyses(upload, item), today=upload.created_at.date())
        rows.append(
            ForeignDocumentRow(
                upload_id=upload.id,
                type_name=_type_name(session, item.document_type_slug),
                document_name=_document_name(key),
                profile_name=profile_name,
                queue_item_id=None if queue_item is None else queue_item.id,
                resolved=queue_item is not None and queue_item.resolved_at is not None,
            )
        )
    return rows


def _is_foreign(item: PlanItem) -> bool:
    return any(
        validation.name is ValidationName.CONTEXT_PERSON and not validation.ok
        for validation in item.validations
    )


def _analyses(upload: Upload, item: PlanItem) -> list[PageAnalysis]:
    # Planlayıcının kişi anahtarına verdiği okumalar: öğenin sayfaları belgedeki sırasıyla, saklanan
    # analizleriyle. Okunamayan kayıt atlanır — görünüm çizilmeye devam eder.
    files = {upload_file.id: upload_file for upload_file in upload.files}
    analyses: list[PageAnalysis] = []
    for source in item.sources:
        upload_file = files.get(source.file_id)
        if upload_file is None:
            continue
        pages = {page.index: page for page in upload_file.pages}
        for index in source.pages:
            page = pages.get(index)
            if (
                page is None
                or page.analysis_status != PageAnalysisStatus.DONE
                or page.analysis_json is None
            ):
                continue
            try:
                analyses.append(PageAnalysis.model_validate(page.analysis_json))
            except ValidationError:
                continue
    return analyses


def _document_name(key: PersonKey) -> str:
    # Latin yazım önce (05.2.2); orijinal yazım farklıysa yanında.
    latin = " ".join(part for part in (key.latin_given_names, key.latin_surname) if part)
    read = latin or " ".join(part for part in (key.given_names, key.surname) if part)
    original = key.original_spelling
    if read and original and original != read:
        return f"{read} ({original})"
    return read or original or NO_VALUE


def _profile_name(employee: Employee) -> str:
    return f"{employee.given_names} {employee.surname}"


def _type_name(session: Session, slug: str | None) -> str:
    if slug is None:
        return NO_VALUE
    known = session.get(KnownDocumentType, slug)
    return slug if known is None else known.name
