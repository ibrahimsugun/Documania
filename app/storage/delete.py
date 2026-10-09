"""Belgeyi kalıcı silme — PRD 10.5.12 (R11, K10, K15, K16; PLAN.md §D110 a, b, g; §D113).

Sistem kendiliğinden hiçbir şey silmez (R11): bu modülü yalnız İK'nın iki aşamalı onayla (K16,
§20.6 "Belgeyi kalıcı sil") yaptığı elle işlem çağırır. Silme geri alınamaz ve iki adımdır; sıra
bilerek böyledir:

1. `delete_document` yalnız veritabanını değiştirir, commit etmez: belge satırı `deleted`
   iskeletine döner — `path` boşalır (dosya adı kişi adı taşır, K8), `deleted_at`/`deleted_by`
   dolar; kimlik, tür, çalışan, sıra numarası, köken (`plan_id`, `source_refs_json`) ve tarihler
   kalır. Belgeyle birlikte giden sayfaların `image_path`, `analysis_json` ve `text_layer`'ı
   boşalır.
   `DOCUMENT_DELETED` kullanıcı adıyla yazılır; verisi yalnız kimlik ve sayıdır (§8.3:
   `document_id`, `document_type_slug`, `previous_status`, `files_deleted`, `files_kept`; ayrıca
   `pages_cleared`). Silinen belge kalem karşılamaz: sahibinin paketleri yenilenir (14.2.2) ve
   `profil.md`'si yeniden üretilir (09.1.1).
2. Çağıran commit eder, sonra `remove_document_files` dosyaları diskten kaldırır. Kaldırılamayan
   dosya (Windows'ta açık dosya, izin) işlemi geri sarmaz: logda belge kimliği ve dosyanın rolü
   yazılır (yol değil — yol kişi adı taşır, CONVENTIONS §6), sayısı aynı olayın verisine
   `files_failed` olarak eklenir; çağıran yine commit eder.

Önce veritabanı: dosya silindikten sonra commit düşseydi satır var olmayan dosyayı gösterirdi;
bu sırada en kötü sonuç diskte kalan, sayısı olayda görünen yetim dosyadır.

**Hangi dosya gider (`plan_document_deletion`).** Plan hiçbir şey yazmaz; ikinci onay metninin
`<N>` (`files_deleted`) ve `<M>` (`files_kept`) sayıları ondan gelir. Belgeye dayanmaya devam
eden şey, bu belge dışındaki silinmemiş (`active`, `superseded`, `archived`) belgelerdir — eski
sürüm (K18) ve arşiv de kaynağa dayanır.

- **Belge dosyası** (`Hazir/` ya da `Archive/<yyyy-mm>/`) her zaman gider; diskte yoksa sayılmaz.
- **`Alinan/` kopyası** (K10; içerikle bulunur, ad değil — `copy_to_received` aynı SHA-256'yı
  tekrar kopyalamaz): sahibin ve belgeyi daha önce taşıyanların (`MANUAL_MOVE` olayının
  `from_employee_id`'si; eski sahibin kopyası taşımada kalır, 10.8.2) klasöründe aranır. O
  çalışanın silinmemiş başka belgesi aynı kaynak dosyaya dayanıyorsa kalır (`<M>`), yoksa gider.
- **Inbox orijinali** yalnız şu üçü birlikte doğruysa gider: dosyaya dayanan başka silinmemiş
  belge yok (hangi çalışanın olursa olsun — S3/S4'te aynı PDF'ten birden çok belge çıkar), dosyayı
  kaynak gösteren açık (`resolved_at` boş) kuyruk öğesi yok ve partisi işlenmeyi bitirmiş
  (`done`, `partial`, `failed`). Aksi hâlde kalır (`<M>`). Gidiyorsa aynı içeriğin tekrar
  yüklemeleri de (`is_duplicate_of`; çıktı üretmez, aynı baytlardır) aynı ölçütle gider.
- **Kuyruk kopyaları** (`Unknown/`, `Unreadable/`, `Unresolved/<parti>/`; içerikle bulunur,
  `reason.json` dışı) orijinalin kaderini paylaşır: orijinal gidiyorsa öğeleri çözülmüştür
  (çözüldü, kapatıldı, yoksayıldı) ve kopyalar da gider; kalıyorsa kalır (`<M>`).
- **Sayfa görüntüsü ve analizi** (`cache/pages/<dosya>/`, `pages.analysis_json`, `text_layer`):
  belgenin kaynak sayfası, başka silinmemiş belgenin ya da açık kuyruk öğesinin sayfası değilse
  ve partisi bitmişse görüntü gider, analiz ve metin katmanı boşalır. Görüntüler `<N>`'ye girmez
  (türetilmiş önbellektir), olayda `pages_cleared` olarak sayılır.

Açık kuyruk öğesinin kaynağı okunamıyorsa (`payload_json` bozuk) öğe partisinin bütün dosyalarına
dayanıyor sayılır: emin olunamayan dosya silinmez.
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    Event,
    Page,
    Plan,
    QueueItem,
    QueueKind,
    Upload,
    UploadFile,
    UploadStatus,
    utcnow,
)
from app.events import EventType, record_event
from app.storage.archive import DocumentNotFoundError
from app.storage.atomic import is_partial_write, sha256_file
from app.storage.layout import REASON_FILE, DataLayout

logger = logging.getLogger(__name__)

# Partisi bu durumlardan birinde olan dosya ve sayfaları silinebilir; öbür durumlar işlenmektedir
# (09.2.1) — boru hattının okuyacağı dosya silinmez.
_SETTLED_UPLOADS = frozenset(
    {UploadStatus.DONE.value, UploadStatus.PARTIAL.value, UploadStatus.FAILED.value}
)
# (dosya, sayfa sırası); sayfa `None` ise dosyanın bütünü (köken kaydında boş sayfa listesi).
_WHOLE_FILE = None


class DocumentNotDeletableError(ValueError):
    """10.5.12: belge zaten kalıcı silinmiş; hiçbir şey değişmedi."""


class DeletionChangedError(ValueError):
    """10.5.12: ikinci onaydan sonra silinecek ya da kalacak dosya sayısı değişti (başka bir işlem
    belgenin kaynağına dokundu); hiçbir şey değişmedi, onay yeniden istenir."""

    def __init__(self, expected: tuple[int, int], actual: tuple[int, int]) -> None:
        super().__init__(
            f"Silinecek/kalacak dosya sayısı onaydan sonra değişti: {expected} → {actual}"
        )
        self.expected = expected
        self.actual = actual


class FileRole(enum.StrEnum):
    """Planlanan dosyanın yeri; log ve testler yol yerine bunu kullanır (yol kişi adı taşır)."""

    DOCUMENT = "document"  # belgenin kendisi: Hazir/ ya da Archive/<yyyy-mm>/
    RECEIVED = "received"  # çalışanın Alinan/ kopyası
    INBOX = "inbox"  # yüklenen orijinal ya da tekrar yüklemesi
    QUEUE = "queue"  # Unknown/, Unreadable/, Unresolved/ altındaki kopya
    PAGE_IMAGE = "page_image"  # cache/pages/<dosya>/ altındaki analiz görüntüsü


@dataclass(frozen=True, slots=True)
class PlannedFile:
    role: FileRole
    path: Path


@dataclass(frozen=True, slots=True)
class PlannedPage:
    """Belgeyle birlikte boşalacak sayfa ve (diskteyse) görüntüsü."""

    page_id: int
    image: Path | None


@dataclass(frozen=True, slots=True)
class DocumentDeletionPlan:
    """`plan_document_deletion` sonucu: diskten gidecek ve kalacak dosyalar, boşalacak sayfalar."""

    document_id: int
    remove: tuple[PlannedFile, ...]
    keep: tuple[PlannedFile, ...]
    pages: tuple[PlannedPage, ...]

    @property
    def files_deleted(self) -> int:
        """İkinci onay metninin `<N>`'si: belge dosyası ve kopyaları."""
        return len(self.remove)

    @property
    def files_kept(self) -> int:
        """İkinci onay metninin `<M>`'si: başka belgeye ya da açık kuyruk öğesine kaynak olduğu
        için kalan kopyalar."""
        return len(self.keep)

    @property
    def counts(self) -> tuple[int, int]:
        return (self.files_deleted, self.files_kept)


@dataclass(frozen=True, slots=True)
class DeletedDocument:
    """`delete_document` sonucu: iskelete dönen satır, eski durumu, uygulanan plan ve olay."""

    document: Document
    previous_status: str
    plan: DocumentDeletionPlan
    event: Event


@dataclass(slots=True)
class _Sources:
    """Belgenin kaynak dosyaları ve onlara dayanmaya devam eden kayıtlar."""

    refs: list[tuple[int, tuple[int, ...] | None]]
    files: dict[int, UploadFile]
    upload_status: dict[str, str]
    survivors: list[Document]
    open_items: list[QueueItem]
    duplicates: dict[int, list[UploadFile]] = field(default_factory=dict)


def plan_document_deletion(
    session: Session, layout: DataLayout, document: Document
) -> DocumentDeletionPlan:
    """Belgeyi silmek diskte neyi kaldırır, neyi bırakır (modül açıklamasındaki ölçütler).

    Hiçbir şey yazmaz; hazırlık adımı `<N>`/`<M>`'yi, `delete_document` aynı planı işlem anında
    yeniden hesaplar.
    """
    remove, keep, pages = plan_documents_files(session, layout, [document])
    return DocumentDeletionPlan(document_id=document.id, remove=remove, keep=keep, pages=pages)


def plan_documents_files(
    session: Session,
    layout: DataLayout,
    documents: Sequence[Document],
    *,
    clear_gone_files: bool = False,
) -> tuple[tuple[PlannedFile, ...], tuple[PlannedFile, ...], tuple[PlannedPage, ...]]:
    """Belgelerin **birlikte** silinmesi diskte neyi kaldırır, neyi bırakır: `(remove, keep,
    pages)`. Ölçütler modül açıklamasındadır; birlikte silinen belgeler birbirine dayanmaz (çalışanı
    silme, 10.5.13 — aynı PDF'ten çıkan iki belgesi orijinali birbirine bırakmaz).
    `clear_gone_files` doğruysa orijinali giden dosyanın belgeye girmemiş sayfaları da (boş sayfa,
    atlanan sayfa) boşalır: dosyanın hiçbir sayfası artık başka kayda kaynak değildir (çalışanı
    silme, PLAN.md §D116 c). Hiçbir şey yazmaz."""
    sources = _load_sources(session, documents)
    remove: dict[Path, FileRole] = {}
    keep: dict[Path, FileRole] = {}

    for document in documents:
        own_file = _stored(layout, document.path)
        if own_file is not None:
            remove[own_file] = FileRole.DOCUMENT

    holders = list(
        {
            employee.id: employee
            for document in documents
            for employee in _received_holders(session, document)
        }.values()
    )
    gone_files: set[int] = set()
    for file_id in dict.fromkeys(file_id for file_id, _ in sources.refs):
        upload_file = sources.files.get(file_id)
        if upload_file is None:
            continue
        gone = not _file_still_needed(sources, upload_file)
        if gone:
            gone_files.add(file_id)
        target = remove if gone else keep
        inbox = _stored(layout, upload_file.stored_path)
        if inbox is not None:
            target[inbox] = FileRole.INBOX
        for copy in _queue_copies(layout, upload_file):
            target[copy] = FileRole.QUEUE
        for duplicate in sources.duplicates.get(file_id, ()):
            copy = _stored(layout, duplicate.stored_path)
            if copy is not None:
                needed = not gone or _file_still_needed(sources, duplicate)
                (keep if needed else remove)[copy] = FileRole.INBOX
        for employee in holders:
            needed = any(
                other.employee_id == employee.id and _refers_to(other, file_id)
                for other in sources.survivors
            )
            for copy in _content_copies(layout.received_dir(employee.folder_name), upload_file):
                (keep if needed else remove)[copy] = FileRole.RECEIVED

    return (
        tuple(PlannedFile(role, path) for path, role in remove.items()),
        tuple(PlannedFile(role, path) for path, role in keep.items() if path not in remove),
        _pages_to_clear(session, layout, sources, gone_files if clear_gone_files else set()),
    )


def delete_document(
    session: Session,
    layout: DataLayout,
    document_id: int,
    *,
    actor: str,
    expected_counts: tuple[int, int] | None = None,
    now: datetime | None = None,
) -> DeletedDocument:
    """Belgeyi kalıcı siler — veritabanı adımı (modül açıklaması, adım 1); commit etmez.

    `actor` iki aşamalı onayı tamamlamış kullanıcının adıdır; boşsa `ValueError`. Belge yoksa
    `DocumentNotFoundError`, zaten silinmişse `DocumentNotDeletableError`. `expected_counts`
    ikinci onayda gösterilen `(<N>, <M>)`'dir: işlem anındaki plan başka sayı veriyorsa
    `DeletionChangedError`. Üçünde de hiçbir şey yazılmaz. Durum denetimi (profilden yalnız etkin
    ve arşivdeki belge) çağıranındır; eski sürüm de burada silinebilir (çalışanı silme, 10.5.13).

    Dosyalar commit'ten sonra `remove_document_files` ile kaldırılır.
    """
    # `app.profiles` ve `app.groups` `app.storage`'ı içe aktarır (bkz. `archive_document`).
    from app.groups import refresh_employee_packages
    from app.profiles import write_profile

    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")
    document = session.get(Document, document_id, with_for_update=True, populate_existing=True)
    if document is None:
        raise DocumentNotFoundError(f"Belge bulunamadı: {document_id}")
    if document.status == DocumentStatus.DELETED.value:
        raise DocumentNotDeletableError(f"Belge {document.id} zaten kalıcı silinmiş")
    plan = plan_document_deletion(session, layout, document)
    if expected_counts is not None and expected_counts != plan.counts:
        raise DeletionChangedError(expected_counts, plan.counts)

    previous_status = document.status
    document.status = DocumentStatus.DELETED.value
    document.path = None
    document.deleted_at = now or utcnow()
    document.deleted_by = actor
    for planned in plan.pages:
        page = session.get_one(Page, planned.page_id)
        page.image_path = None
        page.analysis_json = None
        page.text_layer = None
    session.flush()

    event = record_event(
        session,
        EventType.DOCUMENT_DELETED,
        document_id=document.id,
        employee_id=document.employee_id,
        actor=actor,
        data={
            "document_id": document.id,
            "document_type_slug": document.type_slug,
            "previous_status": previous_status,
            "files_deleted": plan.files_deleted,
            "files_kept": plan.files_kept,
            "pages_cleared": len(plan.pages),
        },
    )
    # 14.2.2: silinen belge kalem karşılamaz; tamamlanmış paket açığa döner.
    refresh_employee_packages(session, document.employee_id, actor=actor)
    # 09.1.1: profil belgeyi artık listelemez; son adım.
    write_profile(session, layout, session.get_one(Employee, document.employee_id))
    return DeletedDocument(document, previous_status, plan, event)


def remove_document_files(session: Session, deleted: DeletedDocument) -> int:
    """Commit edilmiş silmenin dosyalarını diskten kaldırır (modül açıklaması, adım 2).

    Kaldırılamayan dosya sayılır, loglanır ve olayın verisine `files_failed` olarak eklenir;
    hiçbir şey geri sarılmaz. Kaldırılamayan dosya sayısını döndürür; olay değiştiyse çağıran
    commit eder.
    """
    planned = [
        *deleted.plan.remove,
        *(
            PlannedFile(FileRole.PAGE_IMAGE, page.image)
            for page in deleted.plan.pages
            if page.image is not None
        ),
    ]
    failed = 0
    for target in planned:
        try:
            target.path.unlink(missing_ok=True)
        except OSError as exc:
            failed += 1
            logger.warning(
                "Belge %s kalıcı silindi ama bir %s dosyası diskten kaldırılamadı (%s)",
                deleted.plan.document_id,
                target.role.value,
                type(exc).__name__,
            )
    if failed:
        event = deleted.event
        event.data_json = {**(event.data_json or {}), "files_failed": failed}
        session.flush()
    return failed


# --- plan yardımcıları ---------------------------------------------------------------------------


def _refs(raw: Any) -> list[tuple[int, tuple[int, ...] | None]]:
    """`source_refs_json` → `(dosya, sayfalar)`; boş sayfa listesi dosyanın bütünüdür (`None`).
    Bozuk kayıt atlanır."""
    if not isinstance(raw, list):
        return []
    refs: list[tuple[int, tuple[int, ...] | None]] = []
    for ref in raw:
        if not isinstance(ref, Mapping):
            continue
        file_id, pages = ref.get("file_id"), ref.get("pages")
        if not isinstance(file_id, int) or isinstance(file_id, bool):
            continue
        if not isinstance(pages, list):
            continue
        indexes = tuple(page for page in pages if isinstance(page, int))
        refs.append((file_id, indexes or _WHOLE_FILE))
    return refs


def _queue_refs(item: QueueItem) -> list[tuple[int, tuple[int, ...] | None]] | None:
    """Kuyruk öğesinin kaynakları; okunamıyorsa `None` (öğe partisinin bütününe dayanır)."""
    payload = item.payload_json
    if not isinstance(payload, Mapping):
        return None
    refs = _refs(payload.get("sources"))
    return refs or None


def _load_sources(session: Session, documents: Sequence[Document]) -> _Sources:
    refs = [ref for document in documents for ref in _refs(document.source_refs_json)]
    deleting = {document.id for document in documents}
    file_ids = {file_id for file_id, _ in refs}
    files = {
        upload_file.id: upload_file
        for upload_file in session.scalars(select(UploadFile).where(UploadFile.id.in_(file_ids)))
    }
    duplicates: dict[int, list[UploadFile]] = {}
    for duplicate in session.scalars(
        select(UploadFile).where(UploadFile.is_duplicate_of.in_(file_ids)).order_by(UploadFile.id)
    ):
        assert duplicate.is_duplicate_of is not None  # sorgunun koşulu
        duplicates.setdefault(duplicate.is_duplicate_of, []).append(duplicate)
    upload_ids = {upload_file.upload_id for upload_file in files.values()}
    upload_ids.update(d.upload_id for group in duplicates.values() for d in group)

    # Bir dosyaya yalnız kendi partisinin planlarının çıktısı dayanır (07.7: kaynak planın
    # partisinde olmalıdır); plansız satır (elle kayıt) da sayılır.
    plans = select(Plan.id).where(Plan.upload_id.in_(upload_ids))
    survivors = list(
        session.scalars(
            select(Document)
            .where(
                Document.id.not_in(deleting),
                Document.status != DocumentStatus.DELETED.value,
                or_(Document.plan_id.in_(plans), Document.plan_id.is_(None)),
            )
            .order_by(Document.id)
        )
    )
    open_items = list(
        session.scalars(
            select(QueueItem)
            .where(QueueItem.upload_id.in_(upload_ids), QueueItem.resolved_at.is_(None))
            .order_by(QueueItem.id)
        )
    )
    upload_status = {
        upload.id: upload.status
        for upload in session.scalars(select(Upload).where(Upload.id.in_(upload_ids)))
    }
    return _Sources(refs, files, upload_status, survivors, open_items, duplicates)


def _refers_to(document: Document, file_id: int, page: int | None = _WHOLE_FILE) -> bool:
    return any(
        ref_file == file_id and (page is None or pages is None or page in pages)
        for ref_file, pages in _refs(document.source_refs_json)
    )


def _queue_refers_to(item: QueueItem, upload_file: UploadFile, page: int | None) -> bool:
    if item.upload_id != upload_file.upload_id:
        return False
    refs = _queue_refs(item)
    if refs is None:
        return True  # kaynak okunamıyor: emin olunamayan dosya silinmez
    return any(
        ref_file == upload_file.id and (page is None or pages is None or page in pages)
        for ref_file, pages in refs
    )


def _file_still_needed(
    sources: _Sources, upload_file: UploadFile, page: int | None = _WHOLE_FILE
) -> bool:
    """Dosya (ya da tek sayfası) başka silinmemiş belgeye, açık kuyruk öğesine ya da hâlâ işlenen
    partiye kaynak mı."""
    if sources.upload_status.get(upload_file.upload_id) not in _SETTLED_UPLOADS:
        return True
    if any(_refers_to(other, upload_file.id, page) for other in sources.survivors):
        return True
    return any(_queue_refers_to(item, upload_file, page) for item in sources.open_items)


def _received_holders(session: Session, document: Document) -> list[Employee]:
    """`Alinan/` kopyası aranacak çalışanlar: sahip ve belgeyi taşıyanlar (10.8.2)."""
    employee_ids = [document.employee_id]
    for data in session.scalars(
        select(Event.data_json)
        .where(Event.document_id == document.id, Event.type == EventType.MANUAL_MOVE.value)
        .order_by(Event.id)
    ):
        previous = data.get("from_employee_id") if isinstance(data, Mapping) else None
        if isinstance(previous, str):
            employee_ids.append(previous)
    holders: list[Employee] = []
    for employee_id in dict.fromkeys(employee_ids):
        employee = session.get(Employee, employee_id)
        if employee is not None:
            holders.append(employee)
    return holders


def _pages_to_clear(
    session: Session, layout: DataLayout, sources: _Sources, gone_files: set[int]
) -> tuple[PlannedPage, ...]:
    wanted = {(file_id, pages) for file_id, pages in sources.refs if file_id in sources.files}
    if not wanted:
        return ()
    rows = session.scalars(
        select(Page)
        .where(Page.file_id.in_({file_id for file_id, _ in wanted}))
        .order_by(Page.file_id, Page.index)
    )
    planned: list[PlannedPage] = []
    for page in rows:
        if page.file_id in gone_files:
            planned.append(PlannedPage(page.id, _stored(layout, page.image_path)))
            continue
        if not any(
            file_id == page.file_id and (pages is None or page.index in pages)
            for file_id, pages in wanted
        ):
            continue
        if _file_still_needed(sources, sources.files[page.file_id], page.index):
            continue
        planned.append(PlannedPage(page.id, _stored(layout, page.image_path)))
    return tuple(planned)


def _stored(layout: DataLayout, relative_path: str | None) -> Path | None:
    """Saklanan göreli yolun diskteki dosyası; yol boşsa, kökten kaçıyorsa ya da dosya yoksa
    `None`."""
    if not relative_path:
        return None
    try:
        path = layout.resolve(relative_path)
    except ValueError:
        return None
    return path if path.is_file() else None


def _queue_copies(layout: DataLayout, upload_file: UploadFile) -> list[Path]:
    copies: list[Path] = []
    for kind in QueueKind:
        copies.extend(
            _content_copies(layout.queue_dir(kind.value, upload_file.upload_id), upload_file)
        )
    return copies


def _content_copies(directory: Path, upload_file: UploadFile) -> list[Path]:
    """`directory`'de yüklenen dosyayla aynı içeriği (SHA-256) taşıyan dosyalar; kopyalar adla
    değil içerikle bulunur (`copy_to_received`, kuyruk kopyası). `reason.json` ve yarım yazmalar
    sayılmaz."""
    if not directory.is_dir():
        return []
    return [
        path
        for path in _files(directory)
        if path.name != REASON_FILE and sha256_file(path) == upload_file.sha256
    ]


def _files(directory: Path) -> Iterable[Path]:
    return sorted(
        path for path in directory.iterdir() if path.is_file() and not is_partial_write(path.name)
    )


__all__ = [
    "DeletedDocument",
    "DeletionChangedError",
    "DocumentDeletionPlan",
    "DocumentNotDeletableError",
    "FileRole",
    "PlannedFile",
    "PlannedPage",
    "delete_document",
    "plan_document_deletion",
    "plan_documents_files",
    "remove_document_files",
]
