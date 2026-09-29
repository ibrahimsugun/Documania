"""Olay logu altyapısı (K15, 00.5.1) ve olay bağlamı yöneticisi (00.5.2).

Olay türleri PRD §8.3'teki sabit listedir (`EventType`). `record_event` her olayı `events`
tablosuna yazar; `event_context` içinde atılan olaylar upload/file/page alanlarını, açıkça
verilmedikçe, otomatik taşır.
"""

from __future__ import annotations

import enum
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.db.models import Event

if TYPE_CHECKING:
    from app.ai.usage import TokenUsage, UsageMeter


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


USAGE_DATA_KEY = "usage"
"""Olay verisinde token kullanımının anahtarı (PRD 13.1.1): `{"input_tokens": n, "output_tokens":
m}` (`app.ai.usage.TokenUsage.to_event_data`). Değer, olayı doğuran sayfa işinin sağlayıcıya
harcattığı toplamdır; sağlayıcı yanıt vermediyse ya da ölçüm yoksa anahtar hiç yazılmaz."""

USAGE_BY_MODEL_DATA_KEY = "usage_by_model"
"""Ön elemeli sayfada (PRD 13.2.1) `usage`'ın modellere dağılımı: `{"<model>": {"input_tokens": n,
"output_tokens": m}}`. Bir sayfa iki modele harcatmış olabilir (ucuz model ön elemesi ve ana model);
maliyet her modelin kendi fiyatıyla hesaplanır. Toplamı `usage`'a eşittir; ön eleme yapılmayan
sayfada anahtar yazılmaz, `usage` olayın `model`'ine aittir."""

CATALOG_TOKENS_DATA_KEY = "catalog_tokens"
"""Sayfa analizi olayında (PRD 11.4.3, 13.1.1) talimattaki katalog metninin tahmini token payı:
katalog metninin tahmini tokenı (`app.catalog.prompt_builder.estimate_tokens`) × talimatı taşıyan
istek sayısı (ön eleme ve ana analiz; fotoğraf kontrolü katalog taşımaz). `usage` ile birlikte
yazılır; bu alan eklenmeden önceki olaylarda yoktur."""

PRESCREEN_DATA_KEY = "prescreen"
"""Ön eleme sonucu (PRD 13.2.1): `{"model": "<ucuz model>", "accepted": true}` ya da
`{"model": ..., "accepted": false, "escalation": "<gerekçe>"}` (ucuz model hata verdiyse ayrıca
`"error": "<hata türü>"`). Ön eleme yapılmayan sayfada yazılmaz. Gerekçe kişisel değer taşımaz
(`app.pipeline.analyze.Escalation`)."""

PROVIDER_DATA_KEY = "provider"
"""Yapay zekâ çağrısı olayının sağlayıcı adı anahtarı (`usage_event_data` her zaman yazar)."""

USAGE_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.PAGE_ANALYZED,
    EventType.PAGE_ANALYSIS_FAILED,
    EventType.CANDIDATE_TYPE_EXAMINED,
    EventType.TRAINING_EXAMPLE_PLACED,
    EventType.TRAINING_ITEM_UNPLACED,
)
"""Token kullanımı taşıyabilen olay türleri: başarılı ve başarısız sayfa analizi, aday tür
incelemesi (11.5.5) ve eğitim modunun yapay zekâ incelemesi (11.9.3; ikisi de işçinin boş-zaman
işi). Başarısız sayfa da token harcamış olabilir (şemaya uymayan yanıt, fotoğraf kontrolünde hata),
bu yüzden maliyet görünümü ikisini de sayar; inceleme olayları parti kalemi değildir, toplamda ve
ayda sayılır. Yeni bir yapay zekâ çağrısının olayı (ör. işçinin boş-zaman işi, `app.worker.idle`)
kullanımını `usage_event_data` ile yazar ve türü buraya eklenir; tür yapay zekâsız adımlarca da
yazılıyorsa ayrıca `AI_STEP_EVENT_TYPES`'a."""

AI_STEP_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.TRAINING_EXAMPLE_PLACED,
    EventType.TRAINING_ITEM_UNPLACED,
)
"""Hem yapay zekâ adımının hem yapay zekâsız adımların yazdığı kullanım olayı türleri: eğitim
öğesinin yerleşme olayını mekanik tanıma (11.9.2) ve İK'nın yerleştirmesi (11.9.1) da yazar
(PRD §8.3'ün sabit listesinde sınıflandırmanın ayrı bir olayı yoktur). Bu türlerde yalnız sağlayıcı
alanını (`PROVIDER_DATA_KEY`) taşıyan olay bir yapay zekâ çağrısıdır (`is_ai_call_event`)."""


def is_ai_call_event(event_type: str, data: Mapping[str, Any] | None) -> bool:
    """`USAGE_EVENT_TYPES`'taki bir olay yapay zekâ çağrısı mı: `AI_STEP_EVENT_TYPES`'ta ise yalnız
    sağlayıcı alanını taşıyorsa; öteki türlerde her zaman (ölçülmemiş olsa da)."""
    if event_type not in AI_STEP_EVENT_TYPES:
        return True
    return isinstance(data, Mapping) and PROVIDER_DATA_KEY in data


def usage_event_data(
    *,
    provider: str,
    model: str,
    meter: UsageMeter,
    by_model: Mapping[str, TokenUsage] | None = None,
) -> dict[str, object]:
    """Yapay zekâ çağrısı olayının sağlayıcı, model ve kullanım alanları (PRD 13.1.1).

    `meter` çağrının ölçümüdür (`app.ai.usage.measure_usage`). Yanıt gelen çağrı yoksa `usage`
    yazılmaz: sıfır token, ölçülmemiş çağrıyı ölçülmüş gösterirdi. `by_model` çağrı birden çok
    modele harcattıysa dağılımdır (`USAGE_BY_MODEL_DATA_KEY`; toplamı `meter`'ınkine eşit olmalı).
    """
    data: dict[str, object] = {PROVIDER_DATA_KEY: provider, "model": model}
    if meter.calls:
        data[USAGE_DATA_KEY] = meter.usage.to_event_data()
        if by_model:
            data[USAGE_BY_MODEL_DATA_KEY] = {
                name: usage.to_event_data() for name, usage in by_model.items()
            }
    return data


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
