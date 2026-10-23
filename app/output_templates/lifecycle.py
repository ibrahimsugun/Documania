"""Üretilen belgeyi arşivleme ve geri alma — PRD 15.2.2, 15.2.3 (PLAN.md §D123 d, o; K16, R11).

Sistem üretilen belgeyi silmez; günlük düzen İK'nın arşivlemesiyle yürür. Arşivleme ve geri alma
geri alınabilir olduğu için **tek adımlıdır** (§D61, K16) ve olaylıdır: `OUTPUT_ARCHIVED` /
`OUTPUT_RESTORED` kullanıcı adıyla (`generated_document_id`, `template_id`, yeni `status`; değer
yok). Dosya yerinde kalır, adı değişmez; arşivdeki belge açılıp indirilmeye devam eder.

- Etkin (`active`) ve eski sürüm (`superseded`) belge arşivlenir; `archived_at`/`archived_by`
  yazılır.
- Geri alınan belge, çalışanın aynı şablondan daha yeni (sıra numarası büyük) ve kalıcı
  silinmemiş bir belgesi varsa `superseded`, yoksa `active` olur — yeniden üretimin K18 kuralıyla
  aynı sonuç: şablon başına en çok bir etkin belge.
- Kalıcı silinmiş (`deleted`) belge arşivlenmez ve geri alınmaz (`OutputNotFoundError`).

Hiçbir fonksiyon commit etmez.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GeneratedDocument, GeneratedDocumentStatus, utcnow
from app.events import EventType, record_event


class OutputNotFoundError(LookupError):
    """Üretilen belge yok, bu çalışanın değil ya da kalıcı silinmiş."""


def get_output(session: Session, employee_id: str, generated_document_id: int) -> GeneratedDocument:
    """Çalışanın kalıcı silinmemiş üretilen belgesi; yoksa `OutputNotFoundError`."""
    document = session.scalars(
        select(GeneratedDocument).where(
            GeneratedDocument.id == generated_document_id,
            GeneratedDocument.employee_id == employee_id,
            GeneratedDocument.status != GeneratedDocumentStatus.DELETED.value,
        )
    ).first()
    if document is None:
        raise OutputNotFoundError(generated_document_id)
    return document


def _restored_status(session: Session, document: GeneratedDocument) -> str:
    newer = session.scalar(
        select(GeneratedDocument.id)
        .where(
            GeneratedDocument.employee_id == document.employee_id,
            GeneratedDocument.template_id == document.template_id,
            GeneratedDocument.id != document.id,
            GeneratedDocument.sequence_no > document.sequence_no,
            GeneratedDocument.status != GeneratedDocumentStatus.DELETED.value,
        )
        .limit(1)
    )
    if newer is not None:
        return GeneratedDocumentStatus.SUPERSEDED.value
    return GeneratedDocumentStatus.ACTIVE.value


def set_output_archived(
    session: Session, employee_id: str, generated_document_id: int, archived: bool, *, actor: str
) -> bool:
    """Üretilen belgeyi arşivler ya da geri alır (modül açıklaması); durum değiştiyse `True` ve
    olay, zaten istenen durumdaysa `False` (hiçbir şey yazılmaz)."""
    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")
    document = get_output(session, employee_id, generated_document_id)
    is_archived = document.status == GeneratedDocumentStatus.ARCHIVED.value
    if is_archived == archived:
        return False
    if archived:
        document.status = GeneratedDocumentStatus.ARCHIVED.value
        document.archived_at = utcnow()
        document.archived_by = actor
    else:
        document.status = _restored_status(session, document)
        document.archived_at = None
        document.archived_by = None
    session.flush()
    record_event(
        session,
        EventType.OUTPUT_ARCHIVED if archived else EventType.OUTPUT_RESTORED,
        employee_id=employee_id,
        actor=actor,
        data={
            "generated_document_id": document.id,
            "template_id": document.template_id,
            "status": document.status,
        },
    )
    return True
