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

Oturum commit edilmez.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Plan, QueueItem, UploadFile
from app.events import EventType, record_event
from app.pipeline.plan import PlanItem, Route
from app.storage import DataLayout, replace_file, sha256_file, write_unique
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
