"""Taramayı (partiyi) yoksayma ve yoksaymayı geri alma — PRD 10.3.4, 10.3.5 (K16'nın altıncı manuel
işlemi; K10, K15, PLAN.md §C80, §C91, §D50, §D61).

İK son durumdaki (`done`, `partial`, `failed`, `cancelled`) bir partiyi yoksayar: parti yükleme
listesinden, partinin kuyruk öğeleri kuyruklardan kalkar. İşlem **silme değildir** ve yalnız
veritabanına yazar:

- Partiye `dismissed_at` (UTC) ve `dismissed_by` yazılır; `uploads.status` değişmez (durum makinesi
  09.2.1 bozulmaz).
- Partinin çözülmemiş bütün kuyruk öğeleri — güncel planınki de eski sürümünki de — `resolved_at`,
  `resolved_by` ve `resolution = dismissed` alır. Çözülmüş öğe olduğu gibi kalır.
- `UPLOAD_DISMISSED` kullanıcı adıyla yazılır: kapanan kuyruk öğelerinin ve yerinde kalan etkin
  belgelerin kimlikleri (kişisel değer yok).

Dokunulmayanlar: Inbox dosyaları (K10), sayfa görüntüleri, planlar, olaylar (K15), üretilmiş
belgeler (çalışanın Hazır klasöründe kalır; kaldırmak arşivin, 08.4.1'in işidir) ve kuyruk
klasörlerindeki kaynak kopyaları ile `reason.json` — dosya sistemine hiçbir şey yazılmaz. SHA-256
tekrar tespiti (01.4.1) yoksayılan partinin dosyasını da görmeye devam eder (iptal edilen
partininkini görmez, `app.storage.hashing`).

İki aşamalı onay (§20.6 "Taramayı yoksay", 10.8.1) çağıranın işidir — panel `app.web.confirm` ile
yapar; bu modül `USER_CONFIRMED` yazmaz. Hiçbir fonksiyon commit etmez; hata olursa çağıran geri
alır. Süren parti yoksayılmaz (kapsam dışı: toplu yoksayma).

**Yoksaymayı geri alma (10.3.5)** `restore_upload` ile tek adımdır (§D61: salt durum çevirir) ama
kullanıcı adıyla olaylıdır: partinin `dismissed_at`/`dismissed_by`'ı temizlenir, parti listeye ve
kuyruklara döner. Yalnız yoksaymayla kapanan öğeler — `resolution = dismissed` ve `resolved_at >=
dismissed_at` — yeniden açılır; yoksaymadan önce atanmış, onaylanmış (`resolution` boş) ya da
kapatılmış (`closed`, 10.7.4) öğe çözülmüş kalır. Açılan öğenin planı değişmez: partinin güncel
planına aitse bekleyen, değilse eski sürüm olur. `UPLOAD_RESTORED` açılan kuyruk öğelerinin
kimliklerini taşır. Dosya sistemine yine hiçbir şey yazılmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentStatus,
    Plan,
    QueueItem,
    QueueResolution,
    Upload,
    UploadStatus,
    utcnow,
)
from app.events import EventType, record_event

# Süren parti yoksayılmaz; son durumdaki her parti — iptal edilen de (10.3.6, PLAN.md §D114 b) —
# yoksayılabilir.
DISMISSABLE_STATUSES = frozenset(
    {UploadStatus.DONE, UploadStatus.PARTIAL, UploadStatus.FAILED, UploadStatus.CANCELLED}
)


class UploadNotDismissableError(ValueError):
    """Parti yoksayılamaz: hâlâ işleniyor ya da zaten yoksayılmış."""


class UploadNotRestorableError(ValueError):
    """Yoksayma geri alınamaz: parti yoksayılmamış."""


@dataclass(frozen=True, slots=True)
class DismissalPreview:
    """İkinci onay metninin sayıları (§20.6): kapanacak kuyruk öğeleri (`<N>`) ve yerinde kalacak
    etkin belgeler (`<M>`)."""

    queue_items: int
    active_documents: int


@dataclass(frozen=True, slots=True)
class Dismissal:
    upload_id: str
    dismissed_at: datetime
    dismissed_by: str
    queue_item_ids: tuple[int, ...]
    active_document_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Restoration:
    upload_id: str
    restored_by: str
    queue_item_ids: tuple[int, ...]


def is_dismissed(upload: Upload) -> bool:
    return upload.dismissed_at is not None


def check_dismissable(upload: Upload) -> None:
    """Parti yoksayılabilir değilse `UploadNotDismissableError`."""
    if is_dismissed(upload):
        raise UploadNotDismissableError(f"Parti {upload.id} zaten yoksayılmış")
    if UploadStatus(upload.status) not in DISMISSABLE_STATUSES:
        raise UploadNotDismissableError(f"Parti {upload.id} hâlâ işleniyor")


def _unresolved(upload_id: str) -> tuple[ColumnElement[bool], ...]:
    return (QueueItem.upload_id == upload_id, QueueItem.resolved_at.is_(None))


def _active_documents(upload_id: str) -> tuple[ColumnElement[bool], ...]:
    plans = select(Plan.id).where(Plan.upload_id == upload_id)
    return (Document.plan_id.in_(plans), Document.status == DocumentStatus.ACTIVE.value)


def preview_dismissal(session: Session, upload: Upload) -> DismissalPreview:
    """Yoksayma yapılsaydı kapanacak kuyruk öğesi ve yerinde kalacak etkin belge sayısı. Yalnız
    okur."""
    queue_items = session.scalar(
        select(func.count()).select_from(QueueItem).where(*_unresolved(upload.id))
    )
    documents = session.scalar(
        select(func.count()).select_from(Document).where(*_active_documents(upload.id))
    )
    return DismissalPreview(queue_items=queue_items or 0, active_documents=documents or 0)


def dismiss_upload(session: Session, upload: Upload, *, actor: str) -> Dismissal:
    """Partiyi `actor` adına yoksayar (modül açıklaması); commit etmez.

    Parti süren ya da zaten yoksayılmışsa `UploadNotDismissableError` ve hiçbir şey yazılmaz. Parti
    koşullu güncellemeyle işaretlenir (`dismissed_at IS NULL`): aynı partiyi aynı anda yoksayan iki
    işlemden yalnız biri geçer. Kuyruk öğeleri kilitlenerek okunur; aynı anda atanan (08.2.1) öğe
    çözülmüş görülür ve yeniden kapatılmaz.
    """
    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")
    check_dismissable(upload)
    now = utcnow()
    marked = session.execute(
        update(Upload)
        .where(
            Upload.id == upload.id,
            Upload.dismissed_at.is_(None),
            Upload.status.in_([status.value for status in DISMISSABLE_STATUSES]),
        )
        .values(dismissed_at=now, dismissed_by=actor)
        .execution_options(synchronize_session=False)
    )
    session.refresh(upload)
    if marked.rowcount != 1:
        check_dismissable(upload)  # aynı anda gelen öteki işlem geçti ya da parti yeniden işleniyor
        raise UploadNotDismissableError(f"Parti {upload.id} yoksayılamadı")

    queue_items = session.scalars(
        select(QueueItem)
        .where(*_unresolved(upload.id))
        .order_by(QueueItem.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    for queue_item in queue_items:
        queue_item.resolved_at = now
        queue_item.resolved_by = actor
        queue_item.resolution = QueueResolution.DISMISSED.value
    document_ids = tuple(
        session.scalars(
            select(Document.id).where(*_active_documents(upload.id)).order_by(Document.id)
        )
    )
    session.flush()

    dismissal = Dismissal(
        upload_id=upload.id,
        dismissed_at=now,
        dismissed_by=actor,
        queue_item_ids=tuple(queue_item.id for queue_item in queue_items),
        active_document_ids=document_ids,
    )
    record_event(
        session,
        EventType.UPLOAD_DISMISSED,
        upload_id=upload.id,
        actor=actor,
        data={
            "queue_item_ids": list(dismissal.queue_item_ids),
            "active_document_ids": list(dismissal.active_document_ids),
        },
    )
    return dismissal


def restore_upload(session: Session, upload: Upload, *, actor: str) -> Restoration:
    """Partinin yoksaymasını `actor` adına geri alır (modül açıklaması, 10.3.5); commit etmez.

    Parti yoksayılmamışsa `UploadNotRestorableError` ve hiçbir şey yazılmaz. Parti koşullu
    güncellemeyle işaretlenir (`dismissed_at IS NOT NULL`): aynı anda gelen iki geri almadan yalnız
    biri geçer. Öğeler kilitlenerek okunur.
    """
    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")
    dismissed_at = upload.dismissed_at
    if dismissed_at is None:
        raise UploadNotRestorableError(f"Parti {upload.id} yoksayılmamış")
    marked = session.execute(
        update(Upload)
        .where(Upload.id == upload.id, Upload.dismissed_at.is_not(None))
        .values(dismissed_at=None, dismissed_by=None)
        .execution_options(synchronize_session=False)
    )
    session.refresh(upload)
    if marked.rowcount != 1:
        raise UploadNotRestorableError(f"Parti {upload.id} yoksayılmamış")

    queue_items = session.scalars(
        select(QueueItem)
        .where(
            QueueItem.upload_id == upload.id,
            QueueItem.resolution == QueueResolution.DISMISSED.value,
            QueueItem.resolved_at >= dismissed_at,
        )
        .order_by(QueueItem.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    for queue_item in queue_items:
        queue_item.resolved_at = None
        queue_item.resolved_by = None
        queue_item.resolution = None
        queue_item.resolution_reason = None
        queue_item.resolution_note = None
    session.flush()

    restoration = Restoration(
        upload_id=upload.id,
        restored_by=actor,
        queue_item_ids=tuple(queue_item.id for queue_item in queue_items),
    )
    record_event(
        session,
        EventType.UPLOAD_RESTORED,
        upload_id=upload.id,
        actor=actor,
        data={"queue_item_ids": list(restoration.queue_item_ids)},
    )
    return restoration
