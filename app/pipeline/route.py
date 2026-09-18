"""Kuyruğa yönlendirme ve gerekçe dosyası — PRD 08.1.1, 08.1.2 (§8.2, §8.3; K9, K10, K15, R7).

Planlayıcının (`app/pipeline/plan.py`) `unknown`/`unreadable`/`unresolved` rotasına yolladığı her
öğe `route_queue_item` ile kuyruğa alınır (07.7'nin `execute_ready_item`'ıyla aynı tanecik: tek
öğe): öğenin kaynak dosyaları `Unknown/`, `Unreadable/` ya da `Unresolved/<upload_id>/` klasörüne
kopyalanır (Alinan'daki gibi orijinal adıyla, `write_unique`; aynı SHA-256 tekrar kopyalanmaz),
klasördeki `reason.json` o kuyruk/parti için kuyruktaki **bütün** öğelerden baştan üretilir (K9:
türetilmiş dosya, `replace_file` — `app/storage/atomic.py`) ve `queue_items` tablosuna bir satır
yazılır. 09.2 planın her kuyruk öğesi için bunu çağırır; `hazir`/`skip` öğe bu modülün konusu
değildir (`skip` bir hata değildir, kuyruğa girmez, S8).

**Gerekçe içeriği (08.1.2).** `PlanItem.route_reason` hangi sayfaların hangi kuralı ihlal ettiğini
serbest metinle anlatır; tür ve kişi tahmini plan öğesinde ayrı alanlardır ve metne girmez
(`plan.py`: "Tür ve kişi tahmini metne girmez, 08.1.2 birleştirir"). `reason.json` üçünü
birleştirir: `sources` (dosya kimliği ve 0 tabanlı sayfalar), `reason` (`route_reason` — kural ve
sayfalar), `document_type_slug` (tür tahmini; bilinmeyen türde `null`) ve `employee_guess` (kişi
tahmini — yalnız satır 1/3 eşleşmesinde dolu, öbür türlü `action: none`). Aynı yapı
`queue_items.payload_json`'a da yazılır (08.2/08.3 buradan okur).

**İdempotenlik.** Öğe aynı planla daha önce kuyruğa alınmışsa (`queue_items.plan_id` +
`plan_item_id`) kaynak yeniden okunmaz, hiçbir şey yazılmaz; var olan satır döner
(`RoutedItem.applied` yanlış) — planın yeniden çalıştırılması (06.6.1) ikinci kopya üretmez ve
`reason.json`'ı gereksiz yeniden yazmaz.

**Kapsam dışı.** Onay bekleyen profilin tam içeriği (§20.2.2 satır 7, `ProposedProfile.payload()`)
bu görevin girdisinde değildir — yeniden kurmak `app.matching.match`'e ve sayfa analizlerine
bağımlılık ister (bu görevin GİRDİ'sü yalnız `plan.py`/`execute.py`/`storage`). `employee_guess`
şimdilik yalnız plan öğesinin taşıdığı `action`/`employee_id`/`matched_by` üçlüsüdür; PLAN.md §D20.

**Kuyruk öğesini çalışana atama (08.2.1; K9, K16).** `assign_queue_item` insanın kararını (öğenin
sahibi) uygular: çıktı üretilir, yapay zekâ çağrılmaz. Atama yalnız sahibi karara bağlar; geri
kalanı donmuş plandandır ve yeniden sorulmaz:

- Öğe partinin **güncel** planının (en yüksek sürüm, `orchestrate.current_plan`) kuyruk öğesidir;
  eski sürümün öğesi atanmaz (K18), plan `read_plan` ile doğrulanır (K9). Çözülmüş öğe yeniden
  atanmaz. Yeni plan sürümü açılmaz: planın öteki öğeleri ve kuyruk kayıtları olduğu gibi kalır,
  yeniden çalıştırma (06.6.1) atanmış öğeyi ikinci kez üretmez.
- Kaynaklar ve tür öğenindir. Türü olmayan öğe (bilinmeyen tür, analizsiz sayfa, işlenemeyen
  dosya) atanamaz: çıktının adı ve işlemi türden seçilir (K8, §20.3).
- Fiziksel kurallar insan kararıyla aşılmaz: işlem planlayıcının kuralıyla seçilir — kaynak
  doğrulayıcıları (`direct_single_source`, `file_type`; Direkt Belge'de §20.4.1), §20.3, Direkt
  Belge matrisi ve dönüşüm izni (K3, K5, K11, K12). Biri reddederse atama yapılmaz, gerekçe
  planlayıcınınkidir. Boş sayfalar planın `skip` öğelerinden okunur (S8). İçerik ve kişi
  hükümleri — okunaklılık (K1), kabul kriteri, MRZ, doğum tarihi, sayfa sayısı, yüzler, çalışan
  eşleştirme — insan kararıyla aşılır: atamanın amacı budur.
- Çıktı `execute_item` ile planın `hazir` öğesi gibi yazılır: hedef ad atanan çalışanın ad-soyadı
  ve türün etiketiyle K8 adıdır, köken `documents.plan_id` + `source_refs_json`'dır (K15).
- Kuyruk kaydı `resolved_at`/`resolved_by` ile çözülür, `MANUAL_ASSIGN` kullanıcı adıyla
  (`actor`) çıktının `document_id`'si ve çalışanıyla yazılır (veri kişisel değer taşımaz),
  `reason.json` yeniden üretilir (çözülen öğe `resolved_at`/`resolved_by` taşır). Kuyruk
  klasöründeki kaynak kopyası silinmez (K16).

İki aşamalı onay (K16, §20.6.1) ve `USER_CONFIRMED` onay mekanizmasınındır (10.8.1): bu işlev
onaylanmış kullanıcının adını (`actor`) alır. Aynı öğeyi eşzamanlı atayan ikinci işlem kuyruk
satırının kilidinde bekler ve öğeyi çözülmüş görür (PostgreSQL `FOR UPDATE`; SQLite `BEGIN
IMMEDIATE`).

Oturum commit edilmez; hata olursa hiçbir şey yazılmaz.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog import CatalogEntry, export_catalog
from app.db.models import Employee, Plan, QueueItem, UploadFile, utcnow
from app.events import EventType, record_event
from app.pipeline.execute import (
    EXECUTION_ERRORS,
    ExecutedItem,
    ItemDecision,
    execute_item,
    executed_document,
)
from app.pipeline.plan import (
    NoApplicableOperation,
    Operation,
    PlanDocument,
    PlanItem,
    Route,
    SelectedOperation,
    check_conversion,
    check_direct_file_types,
    check_direct_operation,
    operation_source,
    read_plan,
    select_operation,
)
from app.pipeline.validate import check_direct_single_source, check_file_type
from app.storage import (
    DataLayout,
    FileKind,
    UnsupportedFileTypeError,
    detect_file_kind,
    document_stem,
    replace_file,
    sequenced_filename,
    sha256_file,
    write_unique,
)
from app.storage.atomic import is_partial_write, iter_file_chunks
from app.storage.layout import REASON_FILE

# Plan JSON `route` → §8.3 olay türü; `hazir`/`skip` kuyruğa girmez (QueueKind'te de yok).
_QUEUE_EVENTS: dict[Route, EventType] = {
    Route.UNKNOWN: EventType.QUEUED_UNKNOWN,
    Route.UNREADABLE: EventType.QUEUED_UNREADABLE,
    Route.UNRESOLVED: EventType.QUEUED_UNRESOLVED,
}


class QueueItemReferenceError(LookupError):
    """08.1: öğenin bir kaynağı (`sources[i].file_id`) planın partisinde yok."""


class QueueSourceIntegrityError(RuntimeError):
    """08.1 (K10): Inbox'taki kaynak dosyanın SHA-256'sı yüklemede kaydedilenle uyuşmuyor."""


class QueueItemNotFoundError(LookupError):
    """08.2.1: atanacak kuyruk kaydı yok."""


class AssigneeNotFoundError(LookupError):
    """08.2.1: öğenin atanacağı çalışan kayıtlı değil."""


class QueueAssignmentError(ValueError):
    """08.2.1: kuyruk öğesi çalışana atanamıyor; hiçbir şey yazılmadı.

    Mesaj nedeni söyler (dosya kimliği, sayfa, kural); kişisel değer taşımaz (CONVENTIONS §6).
    """


class QueueItemResolvedError(QueueAssignmentError):
    """08.2.1: öğe zaten çözülmüş — atanmış (`resolved_at`) ya da çıktısı üretilmiş."""


class QueueItemSupersededError(QueueAssignmentError):
    """08.2.1 (K18): öğe partinin güncel planına ait değil; eski sürümün öğesi atanmaz."""


class QueueItemNotAssignableError(QueueAssignmentError):
    """08.2.1: öğeden çıktı üretilemiyor — türü yok, fiziksel kurallardan biri (K3, K5, K11, K12)
    işlemi reddediyor ya da işlem belgeyi üretemedi."""


@dataclass(frozen=True, slots=True)
class RoutedItem:
    """`route_queue_item` sonucu.

    Öğe bu planla daha önce kuyruğa alınmışsa `applied` yanlıştır: bu çağrı diske ve veritabanına
    dokunmadı, önceki uygulamanın satırı döndü (idempotenlik, 06.6.1).
    """

    queue_item: QueueItem
    applied: bool


def route_queue_item(
    session: Session, layout: DataLayout, plan: Plan, item: PlanItem
) -> RoutedItem:
    """Planın kuyruğa giden öğesini `Unknown`/`Unreadable`/`Unresolved`'a alır (08.1.1, 08.1.2).

    `item` `plan`'ın doğrulanmış (`read_plan`) ve rotası `unknown`/`unreadable`/`unresolved` olan
    öğesidir; başka rota (`hazir`, `skip`) `ValueError`. Kaynak dosyaların hiçbiri planın
    partisinde değilse `QueueItemReferenceError`, Inbox'taki içeriği yüklemede kaydedilen SHA-256
    ile uyuşmuyorsa `QueueSourceIntegrityError` — ikisinde de hiçbir şey yazılmaz.

    Kopyalama, kuyruk kaydı ve `reason.json`'ın yeniden üretilmesi sırayla yapılır; §8.3 olayı
    (`QUEUED_UNKNOWN`/`QUEUED_UNREADABLE`/`QUEUED_UNRESOLVED`) kuyruk satırından sonra, partinin
    ve öğenin ilk kaynağının dosyası/sayfasıyla yazılır (mesaj `route_reason`, veri kişisel değer
    taşımaz). Oturum commit edilmez.
    """
    if item.route not in _QUEUE_EVENTS:
        raise ValueError(f"Yalnız unknown/unreadable/unresolved öğe kuyruğa alınır: {item.route!r}")
    assert item.route_reason is not None  # PlanItem sözleşmesi: hazir olmayan öğede zorunlu

    existing = session.scalar(
        select(QueueItem).where(
            QueueItem.plan_id == plan.id, QueueItem.plan_item_id == item.item_id
        )
    )
    if existing is not None:
        return RoutedItem(existing, applied=False)

    kind = item.route.value
    sources = _resolve_sources(session, layout, plan, item)
    directory = layout.queue_dir(kind, plan.upload_id)
    for source in sources:
        _copy_to_queue(directory, source.path, sha256=source.sha256)

    payload = _payload(item)
    row = QueueItem(
        upload_id=plan.upload_id,
        plan_id=plan.id,
        plan_item_id=item.item_id,
        kind=kind,
        reason=item.route_reason,
        payload_json=payload,
    )
    session.add(row)
    session.flush()

    first = item.sources[0]
    record_event(
        session,
        _QUEUE_EVENTS[item.route],
        upload_id=plan.upload_id,
        file_id=first.file_id,
        page_index=first.pages[0] if first.pages else None,
        message=item.route_reason,
        data={"item_id": item.item_id, "plan_id": plan.id, "queue_item_id": row.id, **payload},
    )
    _replace_reason_file(session, layout, plan.upload_id, kind)
    return RoutedItem(row, applied=True)


@dataclass(frozen=True, slots=True)
class _ResolvedSource:
    """Doğrulanmış tek kaynak: Inbox yolu ve yüklemede kaydedilen hash."""

    path: Path
    sha256: str


def _resolve_sources(
    session: Session, layout: DataLayout, plan: Plan, item: PlanItem
) -> list[_ResolvedSource]:
    resolved: list[_ResolvedSource] = []
    for position, source in enumerate(item.sources):
        upload_file = session.get(UploadFile, source.file_id)
        if upload_file is None or upload_file.upload_id != plan.upload_id:
            raise QueueItemReferenceError(
                f"{item.item_id} öğesinin sources[{position}] dosyası planın partisinde yok"
            )
        path = layout.resolve(upload_file.stored_path)
        if sha256_file(path) != upload_file.sha256:
            raise QueueSourceIntegrityError(
                f"{item.item_id} öğesinin sources[{position}] kaynağı yüklemede kaydedilen "
                "SHA-256'yı taşımıyor (K10)"
            )
        resolved.append(_ResolvedSource(path, upload_file.sha256))
    return resolved


def _payload(item: PlanItem) -> dict[str, Any]:
    return {
        "document_type_slug": item.document_type_slug,
        "sources": [source.model_dump(mode="json") for source in item.sources],
        "employee_guess": item.employee.model_dump(mode="json"),
    }


def _copy_to_queue(directory: Path, source: Path, *, sha256: str) -> None:
    # Alinan kopyasıyla aynı kural (`app/storage/received.py`): aynı içerik klasörde zaten varsa
    # yeniden kopyalanmaz, doğruluk kaynağı diskin kendisidir.
    directory.mkdir(parents=True, exist_ok=True)
    size = source.stat().st_size
    if _same_content(directory, sha256=sha256, size=size) is not None:
        return
    write_unique(directory, source.name, iter_file_chunks(source), expected_sha256=sha256)


def _same_content(directory: Path, *, sha256: str, size: int) -> Path | None:
    with os.scandir(directory) as entries:
        candidates = sorted(
            Path(entry.path)
            for entry in entries
            if entry.is_file(follow_symlinks=False)
            and entry.name != REASON_FILE
            and not is_partial_write(entry.name)
            and entry.stat(follow_symlinks=False).st_size == size
        )
    return next((path for path in candidates if sha256_file(path) == sha256), None)


def _replace_reason_file(session: Session, layout: DataLayout, upload_id: str, kind: str) -> None:
    # Türetilmiş dosya (K9): bu (parti, kuyruk) çiftindeki bütün öğelerden baştan üretilir
    # (`app/storage/atomic.py`'nin `replace_file` sözleşmesi).
    rows = session.scalars(
        select(QueueItem)
        .where(QueueItem.upload_id == upload_id, QueueItem.kind == kind)
        .order_by(QueueItem.id)
    ).all()
    items = [
        {
            "plan_id": row.plan_id,
            "plan_item_id": row.plan_item_id,
            "reason": row.reason,
            **(row.payload_json or {}),
            # 08.2.1: çözülen öğe klasörden silinmez, çözüldüğü işaretlenir.
            "resolved_at": None if row.resolved_at is None else row.resolved_at.isoformat(),
            "resolved_by": row.resolved_by,
        }
        for row in rows
    ]
    content = json.dumps(
        {"upload_id": upload_id, "kind": kind, "items": items},
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8")
    replace_file(layout.queue_reason_path(kind, upload_id), content)


# --- kuyruk öğesini çalışana atama (08.2.1) ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class AssignedItem:
    """`assign_queue_item` sonucu: çözülen kuyruk kaydı, seçilen işlem ve yazılan çıktı."""

    queue_item: QueueItem
    operation: Operation
    executed: ExecutedItem


def assign_queue_item(
    session: Session,
    layout: DataLayout,
    queue_item_id: int,
    employee_id: str,
    *,
    actor: str,
    render_image_dpi: int,
    render_image_jpeg_quality: int,
) -> AssignedItem:
    """Kuyruk öğesini çalışana atar ve çıktısını yapay zekâ çağırmadan üretir (08.2.1).

    Kurallar modül açıklamasındadır. `actor` iki aşamalı onayı (K16) tamamlamış kullanıcının
    adıdır; boşsa `ValueError`. `render_image_dpi` ve `render_image_jpeg_quality` `render_image`
    işleminin ayarlarıdır (`execute_ready_item`'daki gibi).

    Kuyruk kaydı yoksa `QueueItemNotFoundError`, çalışan yoksa `AssigneeNotFoundError`; öğe
    çözülmüşse `QueueItemResolvedError`, güncel plana ait değilse `QueueItemSupersededError`, çıktı
    üretilemiyorsa `QueueItemNotAssignableError`; saklanan plan değişmişse `PlanIntegrityError`,
    kaynak partide yoksa ya da Inbox'taki içerik değişmişse (K10) `QueueItemReferenceError` /
    `QueueSourceIntegrityError`. Hepsinde hiçbir şey yazılmaz. Oturum commit edilmez.
    """
    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")
    # Aynı öğeyi eşzamanlı atayan işlem bu satırın kilidinde bekler ve öğeyi çözülmüş görür.
    queue_item = session.get(QueueItem, queue_item_id, with_for_update=True, populate_existing=True)
    if queue_item is None:
        raise QueueItemNotFoundError(f"Kuyruk öğesi bulunamadı: {queue_item_id}")
    if queue_item.resolved_at is not None:
        raise QueueItemResolvedError(f"Kuyruk öğesi {queue_item.id} zaten çözülmüş")
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise AssigneeNotFoundError(f"Çalışan bulunamadı: {employee_id}")

    plan, document, item = _queued_plan_item(session, queue_item)
    entry = _assignable_entry(session, queue_item, item)
    selected = _assigned_operation(session, layout, queue_item, plan, document, item, entry)
    if executed_document(session, plan, item) is not None:
        raise QueueItemResolvedError(f"Kuyruk öğesi {queue_item.id}'in çıktısı zaten üretilmiş")

    stem = document_stem(employee.given_names, employee.surname, entry.file_label)
    decision = ItemDecision(
        employee_id=employee.id,
        document_type_slug=entry.slug,
        operation=selected.operation,
        target_name=sequenced_filename(stem, 1, selected.target_format.value),
    )
    try:
        executed = execute_item(
            session,
            layout,
            plan,
            item,
            decision,
            render_image_dpi=render_image_dpi,
            render_image_jpeg_quality=render_image_jpeg_quality,
        )
    except EXECUTION_ERRORS as exc:
        raise _not_assignable(queue_item, str(exc)) from exc

    queue_item.resolved_at = utcnow()
    queue_item.resolved_by = actor
    session.flush()
    first = item.sources[0]
    record_event(
        session,
        EventType.MANUAL_ASSIGN,
        upload_id=plan.upload_id,
        file_id=first.file_id,
        page_index=first.pages[0] if first.pages else None,
        document_id=executed.document.id,
        employee_id=employee.id,
        actor=actor,
        data={
            "queue_item_id": queue_item.id,
            "queue": queue_item.kind,
            "plan_id": plan.id,
            "item_id": item.item_id,
            "document_type_slug": entry.slug,
            "operation": selected.operation.value,
        },
    )
    _replace_reason_file(session, layout, plan.upload_id, queue_item.kind)
    return AssignedItem(queue_item, selected.operation, executed)


def _queued_plan_item(
    session: Session, queue_item: QueueItem
) -> tuple[Plan, PlanDocument, PlanItem]:
    # Güncel plan partinin en yüksek sürümüdür (`orchestrate.current_plan`, 06.6); öğe kimlikleri
    # sürümler arasında tekrar ettiği için öğe `plan_id` + `plan_item_id` ile bulunur (K18).
    latest = session.scalar(
        select(func.max(Plan.version)).where(Plan.upload_id == queue_item.upload_id)
    )
    plan = None if queue_item.plan_id is None else session.get(Plan, queue_item.plan_id)
    if plan is None or plan.version != latest:
        raise QueueItemSupersededError(
            f"Kuyruk öğesi {queue_item.id} partinin güncel planına ait değil (eski sürüm, K18); "
            "güncel planın kuyruğundan atanır"
        )
    document = read_plan(plan)
    item = next((each for each in document.items if each.item_id == queue_item.plan_item_id), None)
    if item is None or item.route.value != queue_item.kind:
        raise QueueItemNotAssignableError(
            f"Kuyruk öğesi {queue_item.id} planın ({plan.id}) kuyruk öğesini göstermiyor"
        )
    return plan, document, item


def _assignable_entry(session: Session, queue_item: QueueItem, item: PlanItem) -> CatalogEntry:
    slug = item.document_type_slug
    if slug is None:
        raise _not_assignable(
            queue_item,
            "belge türü belirlenmedi; çıktının adı ve işlemi türden seçilir (K8, §20.3)",
        )
    entry = export_catalog(session).get(slug)
    if entry is None:
        raise _not_assignable(queue_item, "belge türü katalogda yok")
    return entry


def _assigned_operation(
    session: Session,
    layout: DataLayout,
    queue_item: QueueItem,
    plan: Plan,
    document: PlanDocument,
    item: PlanItem,
    entry: CatalogEntry,
) -> SelectedOperation:
    """Öğenin fiziksel işlemini planlayıcının kuralıyla seçer; ret gerekçesiyle atamayı keser.

    Sıra planlayıcınınkidir: kaynak doğrulayıcıları (`direct_single_source`, `file_type`; Direkt
    Belge'de §20.4.1) → §20.3 → Direkt Belge matrisi (06.3.1) → dönüşüm izni (06.4.1); ilk ret
    sonrakini keser. Olay yazılmaz: ret atamayı keser, planın kararı değişmez.
    """
    blank_pages = _blank_pages(document)
    sources = [
        operation_source(
            session.get_one(UploadFile, source.file_id),
            source,
            kind=_file_kind(resolved.path),
            blank_pages=blank_pages.get(source.file_id, frozenset()),
        )
        for source, resolved in zip(
            item.sources, _resolve_sources(session, layout, plan, item), strict=True
        )
    ]
    file_type = (
        check_direct_file_types(sources, entry=entry)
        if entry.direct
        else check_file_type(sources, entry=entry)
    )
    for refusal in (check_direct_single_source(sources, entry=entry), file_type):
        if refusal is not None:
            raise _not_assignable(queue_item, refusal.reason)
    selection = select_operation(sources, output_format=entry.output_format)
    if isinstance(selection, NoApplicableOperation):
        raise _not_assignable(queue_item, selection.reason)
    for refusal in (
        check_direct_operation(selection.operation, entry=entry),
        check_conversion(selection.operation, entry=entry),
    ):
        if refusal is not None:
            raise _not_assignable(queue_item, refusal.reason)
    return selection


def _not_assignable(queue_item: QueueItem, reason: str) -> QueueItemNotAssignableError:
    return QueueItemNotAssignableError(f"Kuyruk öğesi {queue_item.id} çalışana atanamaz: {reason}")


def _blank_pages(document: PlanDocument) -> dict[int, frozenset[int]]:
    # Planın `skip` öğeleri dosyaların boş sayfalarıdır (S8; 02.4.1 ve analizcinin boş dediği
    # sayfalar); tekrar dosyası da `skip`'tir ama bütün dosyadır (`pages: []`), sayfa katmaz.
    blank: dict[int, set[int]] = {}
    for other in document.items:
        if other.route is Route.SKIP:
            for source in other.sources:
                blank.setdefault(source.file_id, set()).update(source.pages)
    return {file_id: frozenset(pages) for file_id, pages in blank.items()}


def _file_kind(path: Path) -> FileKind | None:
    # Biçim içerikten okunur (01.2.1); tanınmayan biçim `None`.
    try:
        return detect_file_kind(path.read_bytes())
    except UnsupportedFileTypeError:
        return None
