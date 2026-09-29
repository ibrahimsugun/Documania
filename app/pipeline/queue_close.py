"""Kuyruk öğesini kapatma ve yeniden açma — PRD 10.7.4 (K16, §D61; K15, R7, R11, PLAN.md §C91).

Çöp sayfa, mükerrer belge gibi atanacak ya da profil açılacak bir sahibi olmayan kuyruk öğesini İK
gerekçeyle kapatır. Kapatmak **silme değildir** ve yalnız veritabanına yazar:

- Öğeye `resolved_at` (UTC), `resolved_by`, `resolution = closed`, gerekçe kodu
  (`resolution_reason`: `not_a_document`, `already_exists`, `other`) ve isteğe bağlı not
  (`resolution_note`, en çok 200 karakter; "Diğer" gerekçesinde zorunlu) yazılır. Öğe çözülmüş
  sayılır: kuyruk sayaçlarından düşer, "Çözülen" görünümünde gerekçesiyle durur.
- `QUEUE_ITEM_CLOSED` kullanıcı adıyla yazılır: öğenin kimliği ve gerekçe kodu (not ve kişisel değer
  olaya girmez, CONVENTIONS §6).

Dokunulmayanlar: kuyruk klasöründeki kaynak kopyası ve `reason.json` (R7, R11 — dosya sistemine
hiçbir şey yazılmaz), öğenin planı ve kaydı (`payload_json`, K9), aday tür görülmeleri ve örnek
sayfaları (§C80; 10.3.4 ile aynı kural — öğrenilen silinmez).

Yalnız çözülmemiş öğe kapatılır — bekleyen de, partinin eski plan sürümüne ait olan da (K18) —;
partisi yoksayılmış öğe kapatılmaz. İşaretleme koşullu güncellemedir (`resolved_at IS NULL`): aynı
öğeyi aynı anda atayan ya da kapatan iki işlemden yalnız biri geçer.

**Yeniden açma** tek adımdır (§D61: salt durum çevirir, geri alınabilir) ama yine olaylıdır: yalnız
`closed` öğe açılır, çözüm alanlarının hepsi temizlenir ve `QUEUE_ITEM_REOPENED` (öğe, geri alınan
gerekçe kodu) kullanıcı adıyla yazılır. Partisi yoksayılmış öğe açılmaz; önce yoksayma geri alınır
(10.3.5, `app.pipeline.dismiss.restore_upload`). Açılan öğenin planı değişmez: partinin güncel
planına aitse yeniden bekleyen, değilse eski sürüm olur.

İki aşamalı onay (§20.6 "Kuyruk öğesini kapat", 10.8.1) çağıranın işidir — panel `app.web.confirm`
ile yapar; bu modül `USER_CONFIRMED` yazmaz. Hiçbir fonksiyon commit etmez; hata olursa çağıran geri
alır.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, select, update
from sqlalchemy.orm import Session

from app.db.models import QueueCloseReason, QueueItem, QueueResolution, Upload, utcnow
from app.events import EventType, record_event
from app.pipeline.route import QueueItemNotFoundError

NOTE_MAX_LENGTH = 200  # `queue_items.resolution_note`
CLOSE_REASON_LABELS: dict[str, str] = {
    QueueCloseReason.NOT_A_DOCUMENT.value: "Belge değil / çöp sayfa",
    QueueCloseReason.ALREADY_EXISTS.value: "Zaten var",
    QueueCloseReason.OTHER.value: "Diğer",
}

ALREADY_RESOLVED = "Bu öğe zaten çözülmüş; kapatılamaz."
BATCH_DISMISSED = "Öğenin partisi yoksayılmış; önce yoksaymayı geri alın."
NOT_CLOSED = "Yalnız kapatılan öğe yeniden açılır; bu öğe kapatılmadı."
NOTE_TOO_LONG = f"Not en çok {NOTE_MAX_LENGTH} karakter olabilir."
NOTE_REQUIRED = '"Diğer" gerekçesinde kısa bir not yazın.'


class QueueItemNotClosableError(ValueError):
    """Öğe kapatılamıyor: çözülmüş ya da partisi yoksayılmış; hiçbir şey yazılmadı."""


class QueueItemNotReopenableError(ValueError):
    """Öğe yeniden açılamıyor: kapatılmamış ya da partisi yoksayılmış; hiçbir şey yazılmadı."""


class CloseNoteError(ValueError):
    """Kapatma notu geçersiz: çok uzun ya da "Diğer" gerekçesinde boş."""


def close_reason_label(reason: str | None) -> str | None:
    """Gerekçe kodunun Türkçesi; tanınmayan kod olduğu gibi, kod yoksa `None`."""
    if reason is None:
        return None
    return CLOSE_REASON_LABELS.get(reason, reason)


def clean_close_note(reason: QueueCloseReason, note: str | None) -> str | None:
    """Notun saklanacak biçimi: baştaki ve sondaki boşluk atılır, boş not `None`. Çok uzun not ya da
    notsuz "Diğer" `CloseNoteError`."""
    text = (note or "").strip()
    if len(text) > NOTE_MAX_LENGTH:
        raise CloseNoteError(NOTE_TOO_LONG)
    if not text and reason is QueueCloseReason.OTHER:
        raise CloseNoteError(NOTE_REQUIRED)
    return text or None


def _dismissed_uploads() -> ColumnElement[bool]:
    return QueueItem.upload_id.in_(select(Upload.id).where(Upload.dismissed_at.is_not(None)))


def _batch_dismissed(session: Session, queue_item: QueueItem) -> bool:
    return session.get_one(Upload, queue_item.upload_id).dismissed_at is not None


def closing_refusal(session: Session, queue_item: QueueItem) -> str | None:
    """Öğe kapatılamıyorsa nedeni: çözülmüş ya da partisi yoksayılmış."""
    if queue_item.resolved_at is not None:
        return ALREADY_RESOLVED
    if _batch_dismissed(session, queue_item):
        return BATCH_DISMISSED
    return None


def reopening_refusal(session: Session, queue_item: QueueItem) -> str | None:
    """Öğe yeniden açılamıyorsa nedeni: kapatılmamış ya da partisi yoksayılmış."""
    if queue_item.resolution != QueueResolution.CLOSED.value:
        return NOT_CLOSED
    if _batch_dismissed(session, queue_item):
        return BATCH_DISMISSED
    return None


def _queue_item(session: Session, queue_item_id: int) -> QueueItem:
    queue_item = session.get(QueueItem, queue_item_id)
    if queue_item is None:
        raise QueueItemNotFoundError(f"Kuyruk kaydı yok: {queue_item_id}")
    return queue_item


def _check_actor(actor: str) -> None:
    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")


def close_queue_item(
    session: Session,
    queue_item_id: int,
    *,
    reason: QueueCloseReason,
    note: str | None,
    actor: str,
) -> QueueItem:
    """Öğeyi `actor` adına `reason` gerekçesiyle kapatır (modül açıklaması); commit etmez.

    Öğe yoksa `QueueItemNotFoundError`, not geçersizse `CloseNoteError`, öğe kapatılamıyorsa
    `QueueItemNotClosableError` — üçünde de hiçbir şey yazılmaz.
    """
    _check_actor(actor)
    cleaned = clean_close_note(reason, note)
    queue_item = _queue_item(session, queue_item_id)
    refusal = closing_refusal(session, queue_item)
    if refusal is not None:
        raise QueueItemNotClosableError(refusal)
    closed = session.execute(
        update(QueueItem)
        .where(
            QueueItem.id == queue_item_id,
            QueueItem.resolved_at.is_(None),
            ~_dismissed_uploads(),
        )
        .values(
            resolved_at=utcnow(),
            resolved_by=actor,
            resolution=QueueResolution.CLOSED.value,
            resolution_reason=reason.value,
            resolution_note=cleaned,
        )
        .execution_options(synchronize_session=False)
    )
    session.refresh(queue_item)
    if closed.rowcount != 1:
        # Aynı anda gelen öteki işlem öğeyi çözdü ya da partiyi yoksaydı.
        raise QueueItemNotClosableError(closing_refusal(session, queue_item) or ALREADY_RESOLVED)
    record_event(
        session,
        EventType.QUEUE_ITEM_CLOSED,
        upload_id=queue_item.upload_id,
        actor=actor,
        data={"queue_item_id": queue_item.id, "reason": reason.value},
    )
    return queue_item


def reopen_queue_item(session: Session, queue_item_id: int, *, actor: str) -> QueueItem:
    """Kapatılan öğeyi `actor` adına yeniden açar (modül açıklaması); commit etmez.

    Öğe yoksa `QueueItemNotFoundError`, açılamıyorsa `QueueItemNotReopenableError` — ikisinde de
    hiçbir şey yazılmaz.
    """
    _check_actor(actor)
    queue_item = _queue_item(session, queue_item_id)
    refusal = reopening_refusal(session, queue_item)
    if refusal is not None:
        raise QueueItemNotReopenableError(refusal)
    reason = queue_item.resolution_reason
    reopened = session.execute(
        update(QueueItem)
        .where(
            QueueItem.id == queue_item_id,
            QueueItem.resolution == QueueResolution.CLOSED.value,
            ~_dismissed_uploads(),
        )
        .values(
            resolved_at=None,
            resolved_by=None,
            resolution=None,
            resolution_reason=None,
            resolution_note=None,
        )
        .execution_options(synchronize_session=False)
    )
    session.refresh(queue_item)
    if reopened.rowcount != 1:
        raise QueueItemNotReopenableError(reopening_refusal(session, queue_item) or NOT_CLOSED)
    record_event(
        session,
        EventType.QUEUE_ITEM_REOPENED,
        upload_id=queue_item.upload_id,
        actor=actor,
        data={"queue_item_id": queue_item.id, "reason": reason},
    )
    return queue_item
