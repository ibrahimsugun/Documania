"""Kuyruğa yönlendirme, gerekçe dosyası, kuyruk öğesini çalışana atama ve onay bekleyen profili
onaylama — PRD 08.1.1, 08.1.2, 08.2.1, 08.3.1 (§8.2, §8.3, §20.2.2; K7, K9, K10, K15, K16, R7).

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

**Önerilen profil payload'da yok.** Onay bekleyen profilin tam içeriği (§20.2.2 satır 7,
`ProposedProfile.payload()`) kuyruk kaydına yazılmaz; `employee_guess` plan öğesinin taşıdığı
`action`/`employee_id`/`matched_by` üçlüsüdür (PLAN.md §D20). Onay (08.3.1) profili saklanan sayfa
analizlerinden yeniden kurar (PLAN.md §C42).

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

**Onay bekleyen profili onaylama (08.3.1; K7, K16).** `approve_queued_profile` İK'nın onayıyla
satır 7'nin önerdiği çalışanı açar ve belgeyi ona bağlar; atamanın bütün kuralları geçerlidir, sahip
insanın seçtiği kayıtlı çalışan değil onayla açılan çalışandır:

- Yalnız güncel planın `employee.action: pending` öğesi onaylanır; öteki kuyruk öğesinin kişisi
  onayla açılmaz, belge kayıtlı çalışana atanır (08.2.1).
- Tür, işlem ve çıktı denetimleri çalışan açılmadan önce yapılır: fiziksel kural reddi çalışan
  açtırmaz.
- Profil planlayıcının saf adımlarıyla yeniden kurulur (PLAN.md §C29, §C42): öğenin sayfalarının
  saklanan analizleri (belgedeki sırasıyla) → `build_person_key` (MRZ yüzyılı partinin alındığı
  gün, `create_plan`'in varsayılanı). Yapay zekâ çağrılmaz, plan ve analizler değişmez (K9).
- Çalışanı `approve_pending_profile` (`app/matching/match.py`) açar: satır 7 onay anında yeniden
  değerlendirilir; kişi öneriden sonra kayıtlı bir çalışanla eşleşiyorsa (aynı kişinin öteki
  belgesi onaylandı) ikinci çalışan açılmaz, öğe onaylanmaz — o çalışana atanır.
- Çıktı atamadaki gibi yazılır; belgedeki iletişim bilgisi yeni çalışana eklenir (05.8, satır 6
  gibi; `source_document_id` çıktının satırı). Kuyruk kaydı çözülür, `MANUAL_APPROVE` kullanıcı
  adıyla yazılır.
- İK önerilen profili onaydan önce düzeltebilir (10.7.3, `ProfileFields`): düzeltme çalışan
  kaydına ve çıktının K8 adına gider; belge içeriği, sayfa okumaları ve plan değişmez (K9, K17).
  Panel öneriyi onaydan önce `review_queued_profile` ile yazmadan gösterir.

**Paketler ve profil (14.2.2, 09.1.1).** Atama ve onay çıktıyı çalışana yazar; ikisi önce
çalışanın belge paketlerini aynı işlemde yeniler (`refresh_employee_packages`, geçiş olayları
kullanıcı adıyla), son adım olarak çalışanın `profil.md`'sini `write_profile` ile yeniden üretir
(atamada çıktının sahibi, onayda açılan çalışan — belgeden eklenen iletişim bilgisi dahil): çıktı,
olay ve iletişim satırları yazıldıktan sonra, hata verebilecek başka adım kalmadan. Profil yalnız
veritabanından üretilir (K17); dosya atomik yazılır (`replace_file`) ama oturum commit edilmediği
için çağıran commit'ten önce işlemi geri alırsa `profil.md` bir sonraki yeniden üretime kadar bayat
kalır (PLAN.md §D31).

İki aşamalı onay (K16, §20.6.1) ve `USER_CONFIRMED` onay mekanizmasınındır (10.8.1): bu işlevler
onaylanmış kullanıcının adını (`actor`) alır. Aynı öğeyi eşzamanlı çözen ikinci işlem kuyruk
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

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.schemas import PageAnalysis
from app.catalog import CatalogEntry, export_catalog
from app.db.models import (
    Employee,
    EmployeeStatus,
    Page,
    Plan,
    QueueItem,
    Upload,
    UploadFile,
    utcnow,
)
from app.events import EventType, event_context, record_event
from app.groups import refresh_employee_packages
from app.matching.contacts import accumulate_contacts
from app.matching.match import (
    EmployeeAction,
    PersonKey,
    ProfileApprovalRefusedError,
    ProfileFields,
    ProposedProfile,
    approve_pending_profile,
    build_person_key,
    review_pending_profile,
)
from app.pipeline.analyze import PageAnalysisStatus
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
from app.profiles import write_profile
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
    """08.2.1, 08.3.1: kuyruk öğesi bir çalışana — insanın seçtiğine ya da onayla açılana —
    bağlanamıyor; hiçbir şey yazılmadı.

    Mesaj nedeni söyler (dosya kimliği, sayfa, kural); kişisel değer taşımaz (CONVENTIONS §6).
    """


class QueueItemResolvedError(QueueAssignmentError):
    """08.2.1, 08.3.1: öğe zaten çözülmüş — atanmış ya da onaylanmış (`resolved_at`) veya çıktısı
    üretilmiş."""


class QueueItemSupersededError(QueueAssignmentError):
    """08.2.1, 08.3.1 (K18): öğe partinin güncel planına ait değil; eski sürümün öğesi çözülmez."""


class QueueItemNotAssignableError(QueueAssignmentError):
    """08.2.1, 08.3.1: öğeden çıktı üretilemiyor — türü yok, fiziksel kurallardan biri (K3, K5,
    K11, K12) işlemi reddediyor ya da işlem belgeyi üretemedi."""


class QueueItemNotApprovableError(QueueAssignmentError):
    """08.3.1: öğenin profili onaylanamıyor — öğe onay bekleyen profil değil, sayfa analizleri
    okunamıyor ya da §20.2.2 satır 7 onay anında artık uymuyor (kişi kayıtlı bir çalışanla
    eşleşiyor, hüküm değişti)."""


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
    `QueueSourceIntegrityError`. Hepsinde hiçbir şey yazılmaz. Başarıdan sonra atanan çalışanın
    `profil.md`'si yeniden üretilir (09.1.1). Oturum commit edilmez.
    """
    _require_actor(actor)
    queue_item = _unresolved_queue_item(session, queue_item_id)
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise AssigneeNotFoundError(f"Çalışan bulunamadı: {employee_id}")
    if employee.status == EmployeeStatus.MERGED.value:
        raise QueueAssignmentError(
            f"Çalışan {employee.id} başka bir kayıtla birleştirildi; öğe kalan kayda atanır "
            "(10.5.9)"
        )

    plan, document, item = _queued_plan_item(session, queue_item)
    entry, selected = _item_output(session, layout, queue_item, plan, document, item)
    executed = _resolve_with_output(
        session,
        layout,
        queue_item,
        plan,
        item,
        entry,
        selected,
        employee,
        actor=actor,
        event_type=EventType.MANUAL_ASSIGN,
        render_image_dpi=render_image_dpi,
        render_image_jpeg_quality=render_image_jpeg_quality,
    )
    # 14.2.2: yeni çıktı çalışanın paket kalemini karşılayabilir; aynı işlemde yenilenir.
    refresh_employee_packages(session, employee.id, actor=actor)
    # 09.1.1: çalışanın profili yeni çıktıyı gösterir; son adım, sonrasında hata verecek iş yok.
    write_profile(session, layout, employee)
    return AssignedItem(queue_item, selected.operation, executed)


# --- onay bekleyen profili onaylama (08.3.1) --------------------------------------------------


@dataclass(frozen=True, slots=True)
class ApprovedProfile:
    """`approve_queued_profile` sonucu: çözülen kuyruk kaydı, onayla açılan çalışan, seçilen işlem
    ve yazılan çıktı."""

    queue_item: QueueItem
    employee: Employee
    operation: Operation
    executed: ExecutedItem


def review_queued_profile(
    session: Session, queue_item_id: int, *, fields: ProfileFields | None = None
) -> ProposedProfile:
    """Kuyruk öğesinin onaya sunulan profili (10.7.3): onayın okuyacağı öneri, hiçbir şey
    yazılmadan.

    Onayın ön denetimleri — öğe güncel planın çözülmemiş, `employee.action: pending` öğesi, türü
    katalogda, sayfa analizleri okunuyor, satır 7 hâlâ uyuyor ve `fields` (İK'nın düzeltmesi)
    geçerli ve kayıtlı bir çalışana uymuyor — aynı hatalarla yapılır (`approve_queued_profile`);
    fiziksel işlem ve Inbox denetimleri onayın kendisindedir. Profil onaydaki gibi saklanan
    analizlerden kurulur, yapay zekâ çağrılmaz (K9). Kuyruk satırı kilitlenmez; oturum commit
    edilmez.
    """
    queue_item = _unresolved_queue_item(session, queue_item_id, lock=False)
    plan, _, item = _queued_plan_item(session, queue_item)
    _require_pending(queue_item, item)
    entry = _assignable_entry(session, queue_item, item)
    _, key = _profile_key(session, queue_item, plan, item)
    try:
        return review_pending_profile(session, key, entry=entry, fields=fields)
    except ProfileApprovalRefusedError as exc:
        raise _not_approvable(queue_item, str(exc)) from exc


def approve_queued_profile(
    session: Session,
    layout: DataLayout,
    queue_item_id: int,
    *,
    actor: str,
    render_image_dpi: int,
    render_image_jpeg_quality: int,
    fields: ProfileFields | None = None,
) -> ApprovedProfile:
    """Onay bekleyen profili onaylar: çalışan açılır ve belge ona bağlanır (08.3.1, 10.7.3).

    Kurallar modül açıklamasındadır. `actor` iki aşamalı onayı (K16) tamamlamış kullanıcının
    adıdır; boşsa `ValueError`. `render_image_dpi` ve `render_image_jpeg_quality` `render_image`
    işleminin ayarlarıdır. `fields` İK'nın düzelttiği profildir (`approve_pending_profile`);
    verilmezse öneri olduğu gibi yazılır. Düzeltme yalnız çalışan kaydını ve çıktının K8 adını
    değiştirir: çıktı yine kaynak sayfalardan planın işlemiyle üretilir (K11, K17).

    Kuyruk kaydı yoksa `QueueItemNotFoundError`; öğe çözülmüşse `QueueItemResolvedError`, güncel
    plana ait değilse `QueueItemSupersededError`, onay bekleyen profil değilse, sayfa analizleri
    okunamıyorsa, satır 7 artık uymuyorsa ya da onaylanan alanlar geçersizse veya kayıtlı bir
    çalışana uyuyorsa `QueueItemNotApprovableError`, çıktı üretilemiyorsa
    `QueueItemNotAssignableError`; saklanan plan değişmişse `PlanIntegrityError`, kaynak partide
    yoksa ya da Inbox'taki içerik değişmişse (K10) `QueueItemReferenceError` /
    `QueueSourceIntegrityError`. Hepsinde çağıran işlemi geri alır; işlem çalışan açıldıktan sonra
    düşerse (`QueueItemNotAssignableError`) boş çalışan klasörü diskte kalır. Başarıdan sonra açılan
    çalışanın `profil.md`'si yazılır (09.1.1). Oturum commit edilmez.
    """
    _require_actor(actor)
    queue_item = _unresolved_queue_item(session, queue_item_id)
    plan, document, item = _queued_plan_item(session, queue_item)
    _require_pending(queue_item, item)
    entry, selected = _item_output(session, layout, queue_item, plan, document, item)
    analyses, key = _profile_key(session, queue_item, plan, item)
    first = item.sources[0]
    try:
        with event_context(upload_id=plan.upload_id):
            employee = approve_pending_profile(
                session,
                layout,
                key,
                entry=entry,
                actor=actor,
                fields=fields,
                file_id=first.file_id,
                page_index=first.pages[0] if first.pages else None,
            )
    except ProfileApprovalRefusedError as exc:
        raise _not_approvable(queue_item, str(exc)) from exc

    executed = _resolve_with_output(
        session,
        layout,
        queue_item,
        plan,
        item,
        entry,
        selected,
        employee,
        actor=actor,
        event_type=EventType.MANUAL_APPROVE,
        render_image_dpi=render_image_dpi,
        render_image_jpeg_quality=render_image_jpeg_quality,
    )
    # Satır 6'da açılan çalışan gibi (05.8): belgede açıkça yazılı iletişim bilgisi eklenir.
    accumulate_contacts(session, employee.id, analyses, source_document_id=executed.document.id)
    # 14.2.2: onayla yeni açılan çalışanın paketi olmaz; yenileme her belge yazma noktasında aynı
    # tek giriş noktasından geçsin diye yine çağrılır.
    refresh_employee_packages(session, employee.id, actor=actor)
    # 09.1.1: yeni çalışanın profili çıktıyı ve eklenen iletişim bilgisini gösterir; son adım.
    write_profile(session, layout, employee)
    return ApprovedProfile(queue_item, employee, selected.operation, executed)


def _not_approvable(queue_item: QueueItem, reason: str) -> QueueItemNotApprovableError:
    return QueueItemNotApprovableError(f"Kuyruk öğesi {queue_item.id} onaylanamaz: {reason}")


def _require_pending(queue_item: QueueItem, item: PlanItem) -> None:
    if item.employee.action is not EmployeeAction.PENDING:
        raise _not_approvable(
            queue_item,
            "öğe onay bekleyen profil değil (§20.2.2 satır 7); belge kayıtlı çalışana atanır",
        )


def _profile_key(
    session: Session, queue_item: QueueItem, plan: Plan, item: PlanItem
) -> tuple[list[PageAnalysis], PersonKey]:
    # Planlayıcının anahtarı: MRZ doğum tarihinin yüzyılı partinin alındığı günle seçilir (§20.1.6).
    analyses = _item_analyses(session, queue_item, item)
    upload = session.get_one(Upload, plan.upload_id)
    return analyses, build_person_key(analyses, today=upload.created_at.date())


def _item_analyses(session: Session, queue_item: QueueItem, item: PlanItem) -> list[PageAnalysis]:
    # Planlayıcının kişi anahtarına verdiği okumalar: öğenin sayfaları belgedeki sırasıyla
    # (`sources` adayın sırasıyla, dosya başına), saklanan analizleriyle — katalogsuz okunur (C12).
    analyses: list[PageAnalysis] = []
    for source in item.sources:
        for index in source.pages:
            where = f"dosya {source.file_id}, sayfa {index}"
            page = session.scalar(
                select(Page).where(Page.file_id == source.file_id, Page.index == index)
            )
            if (
                page is None
                or page.analysis_status != PageAnalysisStatus.DONE
                or page.analysis_json is None
            ):
                raise _not_approvable(queue_item, f"saklanan sayfa analizi yok ({where})")
            try:
                analyses.append(PageAnalysis.model_validate(page.analysis_json))
            except ValidationError:
                # Gelen değer mesaja konmaz (CONVENTIONS §6).
                raise _not_approvable(
                    queue_item, f"saklanan sayfa analizi §8.4 şemasına uymuyor ({where})"
                ) from None
    return analyses


# --- atama ve onayın ortak adımları -----------------------------------------------------------


def _require_actor(actor: str) -> None:
    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")


def _unresolved_queue_item(session: Session, queue_item_id: int, *, lock: bool = True) -> QueueItem:
    # Aynı öğeyi eşzamanlı çözen işlem bu satırın kilidinde bekler ve öğeyi çözülmüş görür; yalnız
    # okuyan önizleme (`review_queued_profile`) kilitlemez.
    queue_item = session.get(QueueItem, queue_item_id, with_for_update=lock, populate_existing=lock)
    if queue_item is None:
        raise QueueItemNotFoundError(f"Kuyruk öğesi bulunamadı: {queue_item_id}")
    if queue_item.resolved_at is not None:
        raise QueueItemResolvedError(f"Kuyruk öğesi {queue_item.id} zaten çözülmüş")
    return queue_item


def _item_output(
    session: Session,
    layout: DataLayout,
    queue_item: QueueItem,
    plan: Plan,
    document: PlanDocument,
    item: PlanItem,
) -> tuple[CatalogEntry, SelectedOperation]:
    # Çıktının türü ve fiziksel işlemi; öğenin bu planla çıktısı varsa (07.8.1) ikinci çıktı ya da
    # başka sahip yazılmaz.
    entry = _assignable_entry(session, queue_item, item)
    selected = _assigned_operation(session, layout, queue_item, plan, document, item, entry)
    if executed_document(session, plan, item) is not None:
        raise QueueItemResolvedError(f"Kuyruk öğesi {queue_item.id}'in çıktısı zaten üretilmiş")
    return entry, selected


def _resolve_with_output(
    session: Session,
    layout: DataLayout,
    queue_item: QueueItem,
    plan: Plan,
    item: PlanItem,
    entry: CatalogEntry,
    selected: SelectedOperation,
    employee: Employee,
    *,
    actor: str,
    event_type: EventType,
    render_image_dpi: int,
    render_image_jpeg_quality: int,
) -> ExecutedItem:
    """Öğenin çıktısını `employee`'ye yazar, kuyruk kaydını çözer ve manuel işlemin olayını
    (`MANUAL_ASSIGN`, `MANUAL_APPROVE`) kullanıcı adıyla atar."""
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
        event_type,
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
    return executed


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
