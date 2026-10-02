"""Olay logu altyapısı (K15, 00.5.1) ve olay bağlamı yöneticisi (00.5.2).

Olay türleri PRD §8.3'teki sabit listedir (`EventType`). `record_event` her olayı `events`
tablosuna yazar; `event_context` içinde atılan olaylar upload/file/page alanlarını, açıkça
verilmedikçe, otomatik taşır.
"""

from __future__ import annotations

import enum
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Event


class EventType(enum.StrEnum):
    """PRD §8.3'teki sabit olay türü listesi."""

    FILE_UPLOADED = "FILE_UPLOADED"
    FILE_DUPLICATE = "FILE_DUPLICATE"
    PAGE_RENDERED = "PAGE_RENDERED"
    PAGE_BLANK = "PAGE_BLANK"
    PAGE_ANALYZED = "PAGE_ANALYZED"
    PAGE_ANALYSIS_FAILED = "PAGE_ANALYSIS_FAILED"
    PAGE_UNREADABLE = "PAGE_UNREADABLE"
    DOC_TYPE_DETERMINED = "DOC_TYPE_DETERMINED"
    DOC_TYPE_UNKNOWN = "DOC_TYPE_UNKNOWN"
    CANDIDATE_TYPE_PROPOSED = "CANDIDATE_TYPE_PROPOSED"
    PERSON_IDENTIFIED = "PERSON_IDENTIFIED"
    PERSON_MATCHED = "PERSON_MATCHED"
    PERSON_NOT_MATCHED = "PERSON_NOT_MATCHED"
    PERSON_AMBIGUOUS = "PERSON_AMBIGUOUS"
    EMPLOYEE_CREATED = "EMPLOYEE_CREATED"
    EMPLOYEE_PENDING = "EMPLOYEE_PENDING"
    EMPLOYEE_FIELD_FILLED = "EMPLOYEE_FIELD_FILLED"
    PLAN_CREATED = "PLAN_CREATED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    DIRECT_DOC_CHECK = "DIRECT_DOC_CHECK"
    PAGE_EXTRACTED = "PAGE_EXTRACTED"
    PAGES_MERGED = "PAGES_MERGED"
    IMAGE_WRAPPED = "IMAGE_WRAPPED"
    IMAGE_EXTRACTED = "IMAGE_EXTRACTED"
    IMAGE_RENDERED = "IMAGE_RENDERED"
    OUTPUT_SAVED = "OUTPUT_SAVED"
    OUTPUT_SKIPPED = "OUTPUT_SKIPPED"
    QUEUED_UNKNOWN = "QUEUED_UNKNOWN"
    QUEUED_UNREADABLE = "QUEUED_UNREADABLE"
    QUEUED_UNRESOLVED = "QUEUED_UNRESOLVED"
    MANUAL_MOVE = "MANUAL_MOVE"
    MANUAL_ASSIGN = "MANUAL_ASSIGN"
    MANUAL_APPROVE = "MANUAL_APPROVE"
    TYPE_APPROVED = "TYPE_APPROVED"
    TYPE_REJECTED = "TYPE_REJECTED"
    USER_CONFIRMED = "USER_CONFIRMED"
    PLAN_RERUN = "PLAN_RERUN"
    PLAN_REANALYZED = "PLAN_REANALYZED"
    ARCHIVED = "ARCHIVED"
    UPLOAD_DISMISSED = "UPLOAD_DISMISSED"
    PIPELINE_FAILED = "PIPELINE_FAILED"
    CANDIDATE_TYPE_EXAMINED = "CANDIDATE_TYPE_EXAMINED"
    TRAINING_EXAMPLE_PLACED = "TRAINING_EXAMPLE_PLACED"
    TRAINING_ITEM_UNPLACED = "TRAINING_ITEM_UNPLACED"
    TRAINING_LABEL_VERIFIED = "TRAINING_LABEL_VERIFIED"
    TRAINING_EXAMPLE_MOVED = "TRAINING_EXAMPLE_MOVED"
    TRAINING_EXAMPLE_REMOVED = "TRAINING_EXAMPLE_REMOVED"
    TRAINING_MAP_STARTED = "TRAINING_MAP_STARTED"
    GROUP_CHANGED = "GROUP_CHANGED"
    PACKAGE_ASSIGNED = "PACKAGE_ASSIGNED"
    PACKAGE_COMPLETED = "PACKAGE_COMPLETED"
    PACKAGE_REOPENED = "PACKAGE_REOPENED"
    PACKAGE_CANCELLED = "PACKAGE_CANCELLED"
    EMPLOYEE_EDITED = "EMPLOYEE_EDITED"
    EMPLOYEE_DEACTIVATED = "EMPLOYEE_DEACTIVATED"
    EMPLOYEE_REACTIVATED = "EMPLOYEE_REACTIVATED"
    EMPLOYEE_MERGED = "EMPLOYEE_MERGED"
    PROFILE_RECORD_REMOVED = "PROFILE_RECORD_REMOVED"
    PROFILE_RECORD_RESTORED = "PROFILE_RECORD_RESTORED"
    CONTACT_ADDED = "CONTACT_ADDED"
    UNARCHIVED = "UNARCHIVED"
    QUEUE_ITEM_CLOSED = "QUEUE_ITEM_CLOSED"
    QUEUE_ITEM_REOPENED = "QUEUE_ITEM_REOPENED"
    UPLOAD_RESTORED = "UPLOAD_RESTORED"
    TYPE_ACTIVATED = "TYPE_ACTIVATED"
    TYPE_DEACTIVATED = "TYPE_DEACTIVATED"
    TYPE_ARCHIVED = "TYPE_ARCHIVED"
    TYPE_RESTORED = "TYPE_RESTORED"
    CANDIDATE_TYPE_RESTORED = "CANDIDATE_TYPE_RESTORED"
    TRAINING_ITEM_DISMISSED = "TRAINING_ITEM_DISMISSED"
    TRAINING_ITEM_RESTORED = "TRAINING_ITEM_RESTORED"
    TRAINING_RUN_ARCHIVED = "TRAINING_RUN_ARCHIVED"
    USER_CREATED = "USER_CREATED"
    USER_DEACTIVATED = "USER_DEACTIVATED"
    USER_REACTIVATED = "USER_REACTIVATED"
    USER_PASSWORD_CHANGED = "USER_PASSWORD_CHANGED"
    USER_LANGUAGE_CHANGED = "USER_LANGUAGE_CHANGED"
    TELEGRAM_USER_CHANGED = "TELEGRAM_USER_CHANGED"
    TELEGRAM_LINK_CREATED = "TELEGRAM_LINK_CREATED"


PRESCREEN_DATA_KEY = "prescreen"
"""Ön eleme sonucu (PRD 13.2.1): `{"model": "<ucuz model>", "accepted": true}` ya da
`{"model": ..., "accepted": false, "escalation": "<gerekçe>"}` (ucuz model hata verdiyse ayrıca
`"error": "<hata türü>"`). Ön eleme yapılmayan sayfada yazılmaz. Gerekçe kişisel değer taşımaz
(`app.pipeline.analyze.Escalation`)."""

PROVIDER_DATA_KEY = "provider"
"""Yapay zekâ çağrısı olayının sağlayıcı adı anahtarı (`ai_call_event_data` her zaman yazar)."""


def ai_call_event_data(*, provider: str, model: str) -> dict[str, object]:
    """Yapay zekâ çağrısı olayının sağlayıcı ve model alanları (denetim için).

    Token sayısı ve maliyet tutulmaz (PLAN §D84): olay yalnız hangi sağlayıcının hangi modelle
    çağrıldığını söyler.
    """
    return {PROVIDER_DATA_KEY: provider, "model": model}


@dataclass(frozen=True, slots=True)
class EventContext:
    """`event_context` bloğunda etkin olan, olaylara otomatik taşınacak alanlar."""

    upload_id: str | None = None
    file_id: int | None = None
    page_index: int | None = None


_EMPTY_CONTEXT = EventContext()
_current_context: ContextVar[EventContext] = ContextVar(
    "belgeee_event_context", default=_EMPTY_CONTEXT
)


@contextmanager
def event_context(
    *,
    upload_id: str | None = None,
    file_id: int | None = None,
    page_index: int | None = None,
) -> Iterator[EventContext]:
    """Blok içinde `record_event`e verilmeyen upload/file/page alanlarını otomatik uygular.

    İç içe kullanımda yalnız burada verilen alanlar üzerine yazılır; belirtilmeyenler dıştaki
    bağlamdan miras kalır.
    """
    parent = _current_context.get()
    merged = EventContext(
        upload_id=upload_id if upload_id is not None else parent.upload_id,
        file_id=file_id if file_id is not None else parent.file_id,
        page_index=page_index if page_index is not None else parent.page_index,
    )
    token = _current_context.set(merged)
    try:
        yield merged
    finally:
        _current_context.reset(token)


def record_event(
    session: Session,
    event_type: EventType,
    *,
    upload_id: str | None = None,
    file_id: int | None = None,
    page_index: int | None = None,
    document_id: int | None = None,
    employee_id: str | None = None,
    actor: str = "system",
    message: str | None = None,
    data: dict[str, Any] | None = None,
) -> Event:
    """Bir olayı `events` tablosuna yazar (K15).

    upload_id/file_id/page_index açıkça verilmezse etkin `event_context`ten alınır.
    """
    ctx = _current_context.get()
    row = Event(
        upload_id=upload_id if upload_id is not None else ctx.upload_id,
        file_id=file_id if file_id is not None else ctx.file_id,
        page_index=page_index if page_index is not None else ctx.page_index,
        document_id=document_id,
        employee_id=employee_id,
        actor=actor,
        type=event_type.value,
        message=message,
        data_json=data,
    )
    session.add(row)
    session.flush()
    return row
