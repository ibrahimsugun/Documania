"""Kuyruk ekranları (PRD 10.7.1) ile kuyruk uç noktaları — kuyruk öğesini çalışana atama (PRD
08.2.1) ve belgeyi arşive taşıma (PRD 08.4.1; K16, §20.6).

**Kuyruk ekranları (10.7.1).** `GET /queues?tab=&state=&page=` üç kuyruğu (Unknown, Unreadable,
Unresolved; R7) sekme olarak gösterir; her sekmenin başlığında **bekleyen** öğe sayısı durur. Bir
öğe üç durumdan birindedir: *bekleyen* (çözülmemiş ve partinin güncel planına ait), *çözülen*
(`resolved_at` dolu) ya da *eski sürüm* (çözülmemiş ama partinin daha yeni bir planı var; K18 —
atanamaz). Liste seçilen sekmenin öğelerini seçilen durumda, 25'lik sayfalarla gösterir; durum
bağlantıları aynı sekmenin öbür durumlardaki sayısını taşır. `GET /queues/{queue_item_id}` öğenin
detayıdır: gerekçe (R7), tür ve kişi tahmini, kaynak dosyaları ile alınan sayfaların görüntüleri
(`/uploads/{id}/pages/{page_id}/image`, 10.3.1), çözülmüşse çözen kullanıcı ve çıktının geçmişi, ve
öğeyi anan olaylar. Kuyruğa alınırken dondurulan `payload_json` okunur; kaydı eksik ya da bozuk
öğe sayfayı düşürmez, o alan boş/bağlantısız yazılır. Ekranlar yalnız okur: ne belge içeriği ne
kuyruk kaydı değişir (K11, K17); atama ve onay eylemleri 10.7.2/10.7.3'tür.

`POST /api/queue/{queue_item_id}/assign` öğeyi gövdedeki çalışana atar ve çıktısını yapay zekâ
çağırmadan üretir (`app.pipeline.route.assign_queue_item`); yapay zekâ sağlayıcısı bu uç noktanın
bağımlılıkları arasında yoktur. İş tek işlemde yapılır: hata olursa hiçbir şey commit edilmez.
Kuyruk öğesi ya da çalışan yoksa 404; öğe atanamıyorsa (çözülmüş, eski sürüm, türsüz, fiziksel
kural reddi, plan ya da Inbox değişmiş) 409 ve nedeni.

`POST /api/queue/documents/{document_id}/archive` etkin belgeyi `Archive/<yyyy-mm>/`'e taşır ve
durumunu günceller (`app.storage.archive_document`, R11); belge silinmez. Belge yoksa 404, etkin
değilse (zaten arşivlenmiş ya da eski sürüm) 409.

K16: her iki işlem de iki aşamalı onay ister ve kullanıcı adıyla loglanır. Onaylanmış kullanıcının
adı `get_confirmed_actor` bağımlılığıdır; uç noktalar yalnız oturumu açık kullanıcıya açıktır
(10.1.2, `app.main`), onay belirteci (10.8.1, §20.6.1) kurulana kadar 503 döner — onaysız işlem
yapılmaz.

**Kuyruktan çalışana atama (10.7.2).** Panel akışı öğe detayında durur ve yalnız *bekleyen*, türü
belli öğede açılır (türsüz öğenin çıktısı adlandırılamaz, K8; `assign_queue_item` onu reddeder):

1. `GET /queues/{id}/assign/employees?q=` çalışanı 10.4.2'nin aramasıyla (`list_employees`) bulur;
   boş aramada liste gelmez — çalışan aranarak seçilir.
2. `GET /queues/{id}/assign/confirm?employee_id=` seçilen çalışanla **birinci** onay metnini verir.
3. `POST /queues/{id}/assign/prepare` birinci onaydan sonra **ikinci** onay metnini ve onay
   belirtecini verir (§20.6.1 adım 1–2).
4. `POST /queues/{id}/assign` ikinci onaydan sonra belirteçle gelir: belirteç doğrulanır, önce
   `USER_CONFIRMED` (kullanıcı adı, işlem, hedef, iki onayın zamanı), sonra `assign_queue_item`'ın
   `MANUAL_ASSIGN`'ı yazılır; iş tek işlemdedir, hata olursa onay olayı dahil hiçbir şey commit
   edilmez.

Onay metinleri §20.6'dan birebirdir. Belirteç 10.3.2'ninkidir (`issue_confirmation`, PLAN.md §D23):
oturuma, işleme ve hedefe (kuyruk öğesi + çalışan) bağlı, 10 dakika geçerli; belirteçsiz, süresi
geçmiş, başka öğeye, başka çalışana ya da başka oturuma ait istek 400 ve hiçbir şey yapılmaz.
Başarılı atama öğeyi çözdüğü için aynı belirteçle ikinci istek reddedilir (409; PLAN.md §D24).
Adımların hepsi öğeyi yeniden denetler: öğe yoksa 404, çözülmüş, eski sürüm ya da türsüzse 409,
çalışan yoksa 404 — yanıt `queue_assign.html` parçasıdır (HTMX hedefi).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import ColumnElement, Select, and_, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.config import Settings, get_settings
from app.db.models import (
    Employee,
    Event,
    KnownDocumentType,
    Plan,
    QueueItem,
    QueueKind,
    UploadFile,
    utcnow,
)
from app.db.session import get_session
from app.events import EventType, record_event
from app.pipeline.plan import PlanEmployee, PlanIntegrityError
from app.pipeline.route import (
    AssignedItem,
    AssigneeNotFoundError,
    QueueAssignmentError,
    QueueItemNotFoundError,
    QueueItemReferenceError,
    QueueSourceIntegrityError,
    assign_queue_item,
)
from app.storage import (
    DataLayout,
    DocumentNotArchivableError,
    DocumentNotFoundError,
    archive_document,
)
from app.web.auth import PanelUser, require_panel_user
from app.web.routers.documents import SourceView, _reference, _source_view
from app.web.routers.employees import MAX_QUERY_LENGTH, EmployeeListing, list_employees
from app.web.routers.upload_page import (
    CONFIRMATION_REFUSED,
    QUEUE_LABELS,
    ConfirmationRefusedError,
    EventView,
    _event_place,
    _format_ts,
    _plan_employee_text,
    _source_text,
    check_confirmation,
    issue_confirmation,
)
from app.web.routers.uploads import get_layout
from app.web.templating import MENU_BY_KEY, render_page

router = APIRouter(prefix="/api/queue", tags=["queue"])
pages_router = APIRouter(tags=["queue-pages"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]


class QueueAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: str


class QueueAssignmentResponse(BaseModel):
    queue_item_id: int
    upload_id: str
    plan_id: int
    plan_item_id: str
    kind: str
    employee_id: str
    document_id: int
    document_type_slug: str
    operation: str
    resolved_at: datetime
    resolved_by: str


def get_confirmed_actor() -> str:
    """K16: iki aşamalı onayı (§20.6.1) tamamlamış kullanıcının adı.

    Oturum (10.1.2) kuruldu, onay belirteci (10.8.1) henüz yok; manuel işlem onaysız yapılmaz: 503.
    10.8.1 bu bağımlılığı belirteci doğrulayıp tüketen, `USER_CONFIRMED`'ı yazan ve oturumdaki
    kullanıcının (`app.web.auth.require_api_user`) adını döndüren hâliyle bağlar.
    """
    raise HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "İki aşamalı onay mekanizması henüz kurulmadı; manuel işlem yapılamaz.",
    )


def _assign(
    session: Session,
    layout: DataLayout,
    settings: Settings,
    queue_item_id: int,
    employee_id: str,
    *,
    actor: str,
) -> AssignedItem:
    """`assign_queue_item`'ı çağırır; öğe ya da çalışan yoksa 404, atanamıyorsa 409 ve nedeni.
    Oturum commit edilmez; hata olursa hiçbir şey yazılmadı."""
    try:
        return assign_queue_item(
            session,
            layout,
            queue_item_id,
            employee_id,
            actor=actor,
            render_image_dpi=settings.render_image_dpi,
            render_image_jpeg_quality=settings.render_image_jpeg_quality,
        )
    except (QueueItemNotFoundError, AssigneeNotFoundError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except (
        QueueAssignmentError,
        PlanIntegrityError,
        QueueItemReferenceError,
        QueueSourceIntegrityError,
    ) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None


@router.post("/{queue_item_id}/assign", response_model=QueueAssignmentResponse)
def assign_queue_item_to_employee(
    queue_item_id: int,
    request: QueueAssignmentRequest,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    settings: Annotated[Settings, Depends(get_settings)],
    actor: Annotated[str, Depends(get_confirmed_actor)],
) -> QueueAssignmentResponse:
    """08.2.1 — kuyruk öğesini çalışana atar; çıktı üretilir, yapay zekâ çağrılmaz."""
    assigned = _assign(session, layout, settings, queue_item_id, request.employee_id, actor=actor)
    session.commit()
    queue_item, document = assigned.queue_item, assigned.executed.document
    assert queue_item.plan_id is not None and queue_item.plan_item_id is not None
    assert queue_item.resolved_at is not None and queue_item.resolved_by is not None
    return QueueAssignmentResponse(
        queue_item_id=queue_item.id,
        upload_id=queue_item.upload_id,
        plan_id=queue_item.plan_id,
        plan_item_id=queue_item.plan_item_id,
        kind=queue_item.kind,
        employee_id=document.employee_id,
        document_id=document.id,
        document_type_slug=document.type_slug,
        operation=assigned.operation.value,
        resolved_at=queue_item.resolved_at,
        resolved_by=queue_item.resolved_by,
    )


class DocumentArchiveResponse(BaseModel):
    document_id: int
    employee_id: str
    type_slug: str
    path: str
    status: str
    archived_by: str
    archived_at: datetime


@router.post("/documents/{document_id}/archive", response_model=DocumentArchiveResponse)
def archive_document_endpoint(
    document_id: int,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    actor: Annotated[str, Depends(get_confirmed_actor)],
) -> DocumentArchiveResponse:
    """08.4.1 — etkin belgeyi `Archive/<yyyy-mm>/`'e taşır; belge silinmez, durumu güncellenir."""
    try:
        archived = archive_document(session, layout, document_id, actor=actor)
    except DocumentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except DocumentNotArchivableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    session.commit()
    document = archived.document
    return DocumentArchiveResponse(
        document_id=document.id,
        employee_id=document.employee_id,
        type_slug=document.type_slug,
        path=document.path,
        status=document.status,
        archived_by=actor,
        archived_at=archived.event.ts,
    )


# --- 10.7.1: kuyruk ekranları -------------------------------------------------------------------

PAGE_SIZE = 25
QUEUE_ITEM_NOT_FOUND = "Kuyruk öğesi bulunamadı."
CORRUPT_SOURCE = "Bozuk kaynak kaydı"


class QueueState(enum.StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


STATE_LABELS = {
    QueueState.OPEN.value: "Bekleyen",
    QueueState.RESOLVED.value: "Çözülen",
    QueueState.SUPERSEDED.value: "Eski sürüm",
}
TAB_HINTS = {
    QueueKind.UNKNOWN.value: "Belge türü katalogda yok ya da belirlenemedi.",
    QueueKind.UNREADABLE.value: (
        "Belge türü belli, ancak zorunlu alanlardan biri okunamadı (K1); okunamayan alan gerekçede."
    ),
    QueueKind.UNRESOLVED.value: (
        "Belgenin sahibi ya da fiziksel işlemi belirlenemedi; gerekçe her öğede yazılı."
    ),
}
SUPERSEDED_NOTE = (
    "Bu öğe partinin eski bir plan sürümüne ait (K18); çözülemez. "
    "Çözülecek öğeler partinin güncel planının kuyruğundadır."
)
_RESOLVING_EVENTS = frozenset({EventType.MANUAL_ASSIGN.value, EventType.MANUAL_APPROVE.value})
_ITEM_EVENTS = (
    EventType.QUEUED_UNKNOWN.value,
    EventType.QUEUED_UNREADABLE.value,
    EventType.QUEUED_UNRESOLVED.value,
    *_RESOLVING_EVENTS,
    EventType.USER_CONFIRMED.value,
)


@dataclass(frozen=True, slots=True)
class TabView:
    kind: str
    label: str
    open_count: int
    url: str
    active: bool


@dataclass(frozen=True, slots=True)
class StateView:
    state: str
    label: str
    count: int
    url: str
    active: bool


@dataclass(frozen=True, slots=True)
class QueueRow:
    id: int
    url: str
    upload_id: str
    plan_version: int | None
    item_id: str | None
    type_name: str | None
    employee_guess: str | None
    sources: list[str]
    reason: str
    resolved: str | None


@dataclass(frozen=True, slots=True)
class QueueListing:
    kind: str
    label: str
    hint: str
    state: str
    state_label: str
    tabs: list[TabView]
    states: list[StateView]
    rows: list[QueueRow]
    total: int
    page: int
    page_count: int
    previous_url: str | None
    next_url: str | None


@dataclass(frozen=True, slots=True)
class QueueItemView:
    id: int
    kind: str
    kind_label: str
    tab_url: str
    state: str
    state_label: str
    upload_id: str
    plan_version: int | None
    item_id: str | None
    reason: str
    type_name: str | None
    employee_guess: str | None
    sources: list[SourceView]
    resolved: str | None
    document_id: int | None
    note: str | None
    events: list[EventView]
    can_assign: bool
    assign_note: str | None


def _queue_url(kind: str, state: QueueState = QueueState.OPEN, page: int = 1) -> str:
    params = {"tab": kind}
    if state is not QueueState.OPEN:
        params["state"] = state.value
    if page > 1:
        params["page"] = str(page)
    return f"/queues?{urlencode(params)}"


def _current_plan_ids() -> Select[tuple[int]]:
    """Partisinin en yüksek sürümlü (güncel) planı olan planların kimlikleri (K18)."""
    newer = aliased(Plan)
    return select(Plan.id).where(
        ~exists().where(newer.upload_id == Plan.upload_id, newer.version > Plan.version)
    )


def _state_filter(state: QueueState) -> ColumnElement[bool]:
    """Durumun tek tanımı: sayaç, liste ve detay hep bu koşuldan okur."""
    if state is QueueState.RESOLVED:
        return QueueItem.resolved_at.is_not(None)
    current = QueueItem.plan_id.in_(_current_plan_ids())
    if state is QueueState.OPEN:
        return and_(QueueItem.resolved_at.is_(None), current)
    # Planı olmayan kayıt da güncel plana ait sayılamaz (`assign_queue_item` onu da reddeder).
    return and_(QueueItem.resolved_at.is_(None), or_(QueueItem.plan_id.is_(None), ~current))


def _counts(session: Session, state: QueueState) -> dict[str, int]:
    rows = session.execute(
        select(QueueItem.kind, func.count()).where(_state_filter(state)).group_by(QueueItem.kind)
    ).all()
    return {kind: count for kind, count in rows}


def _item_state(session: Session, queue_item: QueueItem) -> QueueState:
    if queue_item.resolved_at is not None:
        return QueueState.RESOLVED
    is_open = session.scalar(
        select(exists().where(QueueItem.id == queue_item.id, _state_filter(QueueState.OPEN)))
    )
    return QueueState.OPEN if is_open else QueueState.SUPERSEDED


# `payload_json` kuyruğa alınırken donar (08.1); eski ya da elle yazılmış kayıt eksik olabilir.


def _payload_refs(payload: Any) -> list[Any]:
    sources = payload.get("sources") if isinstance(payload, dict) else None
    return sources if isinstance(sources, list) else []


def _type_slug(payload: Any) -> str | None:
    slug = payload.get("document_type_slug") if isinstance(payload, dict) else None
    return slug if isinstance(slug, str) else None


def _employee_guess(payload: Any) -> PlanEmployee | None:
    raw = payload.get("employee_guess") if isinstance(payload, dict) else None
    try:
        return PlanEmployee.model_validate(raw)
    except ValidationError:
        return None


@dataclass(frozen=True, slots=True)
class _Lookups:
    """Öğelerin gösterimi için tek seferde okunan kayıtlar (öğe başına sorgu açılmaz)."""

    files: dict[int, UploadFile]
    employees: dict[str, Employee]
    types: dict[str, KnownDocumentType]
    plan_versions: dict[int, int]

    def type_name(self, payload: Any) -> str | None:
        slug = _type_slug(payload)
        if slug is None:
            return None
        known = self.types.get(slug)
        return known.name if known is not None else slug

    def employee_guess(self, payload: Any) -> str | None:
        guess = _employee_guess(payload)
        return _plan_employee_text(guess, self.employees) if guess is not None else None

    def source_texts(self, payload: Any) -> list[str]:
        texts = []
        for ref in _payload_refs(payload):
            parsed = _reference(ref)
            texts.append(
                CORRUPT_SOURCE if parsed is None else _source_text(self.files, parsed[0], parsed[1])
            )
        return texts


def _lookups(session: Session, items: list[QueueItem]) -> _Lookups:
    file_ids: set[int] = set()
    employee_ids: set[str] = set()
    slugs: set[str] = set()
    for item in items:
        file_ids.update(
            parsed[0] for ref in _payload_refs(item.payload_json) if (parsed := _reference(ref))
        )
        guess = _employee_guess(item.payload_json)
        if guess is not None and guess.employee_id is not None:
            employee_ids.add(guess.employee_id)
        slug = _type_slug(item.payload_json)
        if slug is not None:
            slugs.add(slug)
    plan_ids = {item.plan_id for item in items if item.plan_id is not None}
    return _Lookups(
        files={
            each.id: each
            for each in session.scalars(select(UploadFile).where(UploadFile.id.in_(file_ids)))
        },
        employees={
            each.id: each
            for each in session.scalars(select(Employee).where(Employee.id.in_(employee_ids)))
        },
        types={
            each.slug: each
            for each in session.scalars(
                select(KnownDocumentType).where(KnownDocumentType.slug.in_(slugs))
            )
        },
        plan_versions={
            plan_id: version
            for plan_id, version in session.execute(
                select(Plan.id, Plan.version).where(Plan.id.in_(plan_ids))
            )
        },
    )


def _resolved_text(queue_item: QueueItem) -> str | None:
    if queue_item.resolved_at is None:
        return None
    return f"{_format_ts(queue_item.resolved_at)} · {queue_item.resolved_by}"


def list_queue(
    session: Session,
    kind: QueueKind,
    state: QueueState = QueueState.OPEN,
    page: int = 1,
) -> QueueListing:
    """10.7.1 — `kind` kuyruğunun `state` durumundaki öğelerinin `page`. sayfası.

    Sayfa sayısını aşan `page` son sayfaya indirilir. Bekleyen öğeler en eskiden yeniye (kuyruk
    sırası), çözülen ve eski sürüm öğeler en yeniden eskiye sıralanır. Yalnız okur.
    """
    counts = {each: _counts(session, each) for each in QueueState}
    total = counts[state].get(kind.value, 0)
    page_count = max(1, -(-total // PAGE_SIZE))
    page = min(max(page, 1), page_count)
    items = list(
        session.scalars(
            select(QueueItem)
            .where(QueueItem.kind == kind.value, _state_filter(state))
            .order_by(QueueItem.id if state is QueueState.OPEN else QueueItem.id.desc())
            .limit(PAGE_SIZE)
            .offset((page - 1) * PAGE_SIZE)
        )
    )
    lookups = _lookups(session, items)
    return QueueListing(
        kind=kind.value,
        label=QUEUE_LABELS[kind.value],
        hint=TAB_HINTS[kind.value],
        state=state.value,
        state_label=STATE_LABELS[state.value],
        tabs=[
            TabView(
                kind=each.value,
                label=QUEUE_LABELS[each.value],
                open_count=counts[QueueState.OPEN].get(each.value, 0),
                url=_queue_url(each.value),
                active=each is kind,
            )
            for each in QueueKind
        ],
        states=[
            StateView(
                state=each.value,
                label=STATE_LABELS[each.value],
                count=counts[each].get(kind.value, 0),
                url=_queue_url(kind.value, each),
                active=each is state,
            )
            for each in QueueState
        ],
        rows=[
            QueueRow(
                id=item.id,
                url=f"/queues/{item.id}",
                upload_id=item.upload_id,
                plan_version=lookups.plan_versions.get(item.plan_id) if item.plan_id else None,
                item_id=item.plan_item_id,
                type_name=lookups.type_name(item.payload_json),
                employee_guess=lookups.employee_guess(item.payload_json),
                sources=lookups.source_texts(item.payload_json),
                reason=item.reason,
                resolved=_resolved_text(item),
            )
            for item in items
        ],
        total=total,
        page=page,
        page_count=page_count,
        previous_url=_queue_url(kind.value, state, page - 1) if page > 1 else None,
        next_url=_queue_url(kind.value, state, page + 1) if page < page_count else None,
    )


def _mentions_item(event: Event, queue_item_id: int) -> bool:
    data = event.data_json
    if not isinstance(data, dict):
        return False
    if event.type == EventType.USER_CONFIRMED.value:
        target = data.get("target")
        return isinstance(target, dict) and target.get("queue_item_id") == queue_item_id
    return data.get("queue_item_id") == queue_item_id


def _item_events(session: Session, queue_item: QueueItem) -> list[Event]:
    """Öğeyi anan olaylar: kuyruğa alınması, onayı ve çözümü. Olayın verisi `queue_item_id`
    taşır; onay olayında (`USER_CONFIRMED`, §20.6.1) hedefin içindedir."""
    events = session.scalars(
        select(Event)
        .where(Event.upload_id == queue_item.upload_id, Event.type.in_(_ITEM_EVENTS))
        .order_by(Event.ts, Event.id)
    )
    return [event for event in events if _mentions_item(event, queue_item.id)]


def build_item_view(session: Session, queue_item_id: int) -> QueueItemView | None:
    """10.7.1 — öğenin detayı; öğe yoksa `None`. Yalnız okur, oturum commit edilmez."""
    queue_item = session.get(QueueItem, queue_item_id)
    if queue_item is None:
        return None
    lookups = _lookups(session, [queue_item])
    state = _item_state(session, queue_item)
    events = _item_events(session, queue_item)
    resolution = next(
        (
            event
            for event in reversed(events)
            if event.type in _RESOLVING_EVENTS and event.document_id is not None
        ),
        None,
    )
    return QueueItemView(
        id=queue_item.id,
        kind=queue_item.kind,
        kind_label=QUEUE_LABELS.get(queue_item.kind, queue_item.kind),
        tab_url=_queue_url(queue_item.kind, state),
        state=state.value,
        state_label=STATE_LABELS[state.value],
        upload_id=queue_item.upload_id,
        plan_version=(
            lookups.plan_versions.get(queue_item.plan_id) if queue_item.plan_id else None
        ),
        item_id=queue_item.plan_item_id,
        reason=queue_item.reason,
        type_name=lookups.type_name(queue_item.payload_json),
        employee_guess=lookups.employee_guess(queue_item.payload_json),
        sources=[_source_view(session, ref) for ref in _payload_refs(queue_item.payload_json)],
        resolved=_resolved_text(queue_item),
        document_id=resolution.document_id if resolution is not None else None,
        note=SUPERSEDED_NOTE if state is QueueState.SUPERSEDED else None,
        can_assign=_assign_refusal(session, queue_item) is None,
        assign_note=(
            TYPELESS_NOTE
            if state is QueueState.OPEN and _type_slug(queue_item.payload_json) is None
            else None
        ),
        events=[
            EventView(
                ts=_format_ts(event.ts),
                ts_iso=event.ts.isoformat(),
                type=event.type,
                actor=event.actor,
                place=_event_place(event, lookups.files),
                message=event.message,
            )
            for event in events
        ],
    )


@pages_router.get("/queues", response_class=HTMLResponse)
def queues_page(
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    tab: Annotated[QueueKind, Query()] = QueueKind.UNKNOWN,
    state: Annotated[QueueState, Query()] = QueueState.OPEN,
    page: Annotated[int, Query(ge=1)] = 1,
) -> HTMLResponse:
    listing = list_queue(session, tab, state, page)
    # Okuma işlemi de SQLite'ta yazma kilidini tutar (`app.db.session`): sayfa çizilirken
    # arka plandaki bir işleyici beklemesin.
    session.rollback()
    entry = MENU_BY_KEY["queues"]
    return render_page(
        request, "queue.html", user=user, active=entry.key, entry=entry, listing=listing
    )


@pages_router.get("/queues/{queue_item_id}", response_class=HTMLResponse)
def queue_item_page(
    queue_item_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    view = build_item_view(session, queue_item_id)
    session.rollback()
    entry = MENU_BY_KEY["queues"]
    if view is None:
        return render_page(
            request,
            "queue_item.html",
            user=user,
            active=entry.key,
            status_code=status.HTTP_404_NOT_FOUND,
            error=QUEUE_ITEM_NOT_FOUND,
        )
    return render_page(request, "queue_item.html", user=user, active=entry.key, item=view)


# --- 10.7.2: kuyruktan çalışana atama -----------------------------------------------------------

ASSIGN_OPERATION = "assign"
# §20.6: metinler birebir; `<Ad Soyad>` seçilen çalışanın adıyla doldurulur.
ASSIGN_FIRST_CONFIRMATION = "Bu belgeyi {name} çalışanına atamak üzeresiniz. Emin misiniz?"
ASSIGN_SECOND_CONFIRMATION = (
    "Bu işlem sistemdeki belge organizasyonunu değiştirecektir. Son kararınız mı?"
)
RESOLVED_NOTE = "Bu öğe zaten çözülmüş; yeniden atanamaz."
TYPELESS_NOTE = (
    "Belge türü belirlenmediği için bu öğe bir çalışana atanamaz: "
    "çıktının adı ve işlemi belge türünden seçilir (K8)."
)
ASSIGNEE_NOT_FOUND = "Çalışan bulunamadı."


@dataclass(frozen=True, slots=True)
class AssigneeView:
    id: str
    name: str


def _assign_refusal(session: Session, queue_item: QueueItem) -> str | None:
    """Öğe panelden atanamıyorsa nedeni: çözülmüş, eski sürüm (K18) ya da türsüz (K8)."""
    state = _item_state(session, queue_item)
    if state is QueueState.RESOLVED:
        return RESOLVED_NOTE
    if state is QueueState.SUPERSEDED:
        return SUPERSEDED_NOTE
    if _type_slug(queue_item.payload_json) is None:
        return TYPELESS_NOTE
    return None


def _assignable_item(session: Session, queue_item_id: int) -> QueueItem:
    """Atanabilecek (bekleyen, türü belli) kuyruk öğesi; yoksa 404, atanamıyorsa 409."""
    queue_item = session.get(QueueItem, queue_item_id)
    if queue_item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, QUEUE_ITEM_NOT_FOUND)
    refusal = _assign_refusal(session, queue_item)
    if refusal is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, refusal)
    return queue_item


def _assignee(session: Session, employee_id: str) -> AssigneeView:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ASSIGNEE_NOT_FOUND)
    return AssigneeView(id=employee.id, name=f"{employee.given_names} {employee.surname}")


def assignment_subject(queue_item_id: int, employee_id: str) -> str:
    """Atama belirtecinin bağlı olduğu işlem ve hedef: kuyruk öğesi + seçilen çalışan."""
    return f"{ASSIGN_OPERATION}:{queue_item_id}:{employee_id}"


def _assign_result(
    request: Request, status_code: int, queue_item_id: int, **context: object
) -> HTMLResponse:
    """`queue_assign.html` parçası (HTMX hedefi: öğe detayındaki `#assign-results` ya da
    `#assign-step`)."""
    return render_page(
        request,
        "queue_assign.html",
        user=None,
        status_code=status_code,
        queue_item_id=queue_item_id,
        **context,
    )


@pages_router.get("/queues/{queue_item_id}/assign/employees", response_class=HTMLResponse)
def assignment_search(
    queue_item_id: int,
    request: Request,
    _user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str, Query(max_length=MAX_QUERY_LENGTH)] = "",
) -> HTMLResponse:
    """10.7.2 — atanacak çalışanı arar (10.4.2'nin araması); boş aramada liste gelmez."""
    listing: EmployeeListing | None = None
    try:
        _assignable_item(session, queue_item_id)
        if q.strip():
            listing = list_employees(session, q)
    except HTTPException as exc:
        return _assign_result(request, exc.status_code, queue_item_id, error=str(exc.detail))
    finally:
        session.rollback()
    return _assign_result(request, status.HTTP_200_OK, queue_item_id, search=True, listing=listing)


@pages_router.get("/queues/{queue_item_id}/assign/confirm", response_class=HTMLResponse)
def assignment_first_confirmation(
    queue_item_id: int,
    request: Request,
    _user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    employee_id: Annotated[str, Query(max_length=MAX_QUERY_LENGTH)],
) -> HTMLResponse:
    """10.7.2 — seçilen çalışanla birinci onay metni (§20.6); hiçbir şey değişmez."""
    try:
        _assignable_item(session, queue_item_id)
        assignee = _assignee(session, employee_id)
    except HTTPException as exc:
        return _assign_result(request, exc.status_code, queue_item_id, error=str(exc.detail))
    finally:
        session.rollback()
    return _assign_result(
        request,
        status.HTTP_200_OK,
        queue_item_id,
        assignee=assignee,
        first_confirmation=ASSIGN_FIRST_CONFIRMATION.format(name=assignee.name),
    )


@pages_router.post("/queues/{queue_item_id}/assign/prepare", response_class=HTMLResponse)
def prepare_assignment(
    queue_item_id: int,
    request: Request,
    _user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    employee_id: Annotated[str, Form(max_length=MAX_QUERY_LENGTH)],
) -> HTMLResponse:
    """10.7.2 — birinci onaydan sonra ikinci onay metnini ve onay belirtecini verir (§20.6.1)."""
    try:
        _assignable_item(session, queue_item_id)
        assignee = _assignee(session, employee_id)
        token = issue_confirmation(request, assignment_subject(queue_item_id, assignee.id))
    except HTTPException as exc:
        return _assign_result(request, exc.status_code, queue_item_id, error=str(exc.detail))
    except ConfirmationRefusedError as exc:
        return _assign_result(request, status.HTTP_400_BAD_REQUEST, queue_item_id, error=str(exc))
    finally:
        session.rollback()
    return _assign_result(
        request,
        status.HTTP_200_OK,
        queue_item_id,
        assignee=assignee,
        second_confirmation=ASSIGN_SECOND_CONFIRMATION,
        confirmation=token,
    )


@pages_router.post("/queues/{queue_item_id}/assign", response_class=HTMLResponse)
def assign_from_queue(
    queue_item_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    settings: Annotated[Settings, Depends(get_settings)],
    employee_id: Annotated[str, Form(max_length=MAX_QUERY_LENGTH)],
    confirmation: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    """10.7.2 — ikinci onayın belirteciyle öğeyi çalışana atar (08.2.1; K16).

    Belirteç yoksa, süresi geçmişse ya da başka öğeye, çalışana veya oturuma aitse hiçbir şey
    yapılmaz (400). Onay olayı ve atama tek işlemdedir: atama düşerse onay olayı da yazılmaz.
    """
    try:
        queue_item = _assignable_item(session, queue_item_id)
        first_confirmed = check_confirmation(
            request, assignment_subject(queue_item_id, employee_id), confirmation
        )
        # §20.6.1: onay tamamlanınca `USER_CONFIRMED` (kullanıcı adı, işlem, hedef, iki onayın
        # zamanı), ardından işlemin kendi olayı (`MANUAL_ASSIGN`) düşer.
        record_event(
            session,
            EventType.USER_CONFIRMED,
            upload_id=queue_item.upload_id,
            actor=user.username,
            data={
                "operation": ASSIGN_OPERATION,
                "target": {"queue_item_id": queue_item.id, "employee_id": employee_id},
                "first_confirmed_at": first_confirmed.isoformat(),
                "second_confirmed_at": utcnow().isoformat(),
            },
        )
        assigned = _assign(
            session, layout, settings, queue_item_id, employee_id, actor=user.username
        )
        assignee = _assignee(session, employee_id)
    except HTTPException as exc:
        session.rollback()
        return _assign_result(request, exc.status_code, queue_item_id, error=str(exc.detail))
    except ConfirmationRefusedError:
        session.rollback()
        return _assign_result(
            request, status.HTTP_400_BAD_REQUEST, queue_item_id, error=CONFIRMATION_REFUSED
        )
    session.commit()
    document = assigned.executed.document
    return _assign_result(
        request,
        status.HTTP_200_OK,
        queue_item_id,
        assignee=assignee,
        done=True,
        document_id=document.id,
        file_name=PurePosixPath(document.path).name,
    )
