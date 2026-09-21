"""Kuyruk ekranları (PRD 10.7.1–10.7.3) ile kuyruk uç noktaları — kuyruk öğesini çalışana atama
(PRD 08.2.1) ve belgeyi arşive taşıma (PRD 08.4.1; K16, §20.6).

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

K16: her iki işlem de iki aşamalı onay ister ve kullanıcı adıyla loglanır (10.8.1,
`app.web.confirm`). Uç noktalar yalnız oturumu açık kullanıcıya açıktır (10.1.2, `app.main`).
İstemci birinci onaydan sonra hazırlık isteği gönderir — `POST /api/queue/{id}/assign/prepare`
(gövde `employee_id`) ya da `POST /api/queue/documents/{id}/archive/prepare` — ve §20.6'nın iki
metnini, tek kullanımlık belirteci ve son geçerlilik anını alır; asıl istek belirteci
`X-Confirmation-Token` başlığında taşır. Belirteçsiz, süresi geçmiş, kullanılmış ya da başka
işleme, hedefe veya oturuma ait belirteçle gelen istek 400 ve hiçbir şey yapılmaz; başarılı istek
önce `USER_CONFIRMED`, sonra işlemin kendi olayını (`MANUAL_ASSIGN`, `ARCHIVED`) tek işlemde yazar.

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

Onay metinleri §20.6'dan birebirdir (`app.web.confirm`). Belirteç 10.8.1'in tek kullanımlık
belirtecidir: oturuma, işleme ve hedefe (kuyruk öğesi + çalışan) bağlı, 10 dakika geçerli;
belirteçsiz, süresi geçmiş, kullanılmış, başka öğeye, başka çalışana ya da başka oturuma ait istek
400 ve hiçbir şey yapılmaz. Başarılı atama öğeyi çözdüğü için aynı belirteçle ikinci istek öğe
denetiminde 409 ile reddedilir.
Adımların hepsi öğeyi yeniden denetler: öğe yoksa 404, çözülmüş, eski sürüm ya da türsüzse 409,
çalışan yoksa 404 — yanıt `queue_assign.html` parçasıdır (HTMX hedefi).

**Kuyruktan profil oluşturma (10.7.3).** Onay bekleyen profil (§20.2.2 satır 7, K7) öğesinin
detayında önerilen profil düzenlenebilir bir formla gelir: öneri onaydaki gibi saklanan sayfa
analizlerinden kurulur (`review_queued_profile`; yapay zekâ çağrılmaz, K9). Form yalnız çalışan
kaydının altı alanını taşır (ad, soyad, diğer isimler, orijinal yazım, doğum tarihi, vatandaşlık);
belge içeriği — sayfalar, tür, sayfa okumaları — formda yoktur ve düzenlenemez (K17), başka form
alanı okunmaz. Çıktı yine kaynak sayfalardan planın işlemiyle üretilir; düzeltme yalnız çalışan
kaydına ve çıktının K8 adına gider.

1. `POST /queues/{id}/profile/confirm` düzenlenen alanlarla **birinci** onay metnini (§20.6,
   `<Ad Soyad>` onaylanan ad-soyad) ve öneriden farklı alanları gösterir; alan geçersizse 422 ve
   alan alan sorunlar.
2. `POST /queues/{id}/profile/prepare` **ikinci** onay metnini ve belirteci verir.
3. `POST /queues/{id}/profile` belirteçle gelir: önce `USER_CONFIRMED` (işlem `approve_profile`,
   hedef öğe; profil değerleri olaya girmez), sonra `approve_queued_profile`'ın `EMPLOYEE_CREATED`
   (düzeltilen alanların adları) ve `MANUAL_APPROVE`'u tek işlemde yazılır.

Belirteç atamanınkiyle aynı mekanizmadır; hedefi kuyruk öğesi + onaylanan alanların özetidir
(`profile_subject`): ikinci onaydan sonra değiştirilen alan, başka öğe, işlem ya da oturum 400.
Her adım öğeyi ve düzeltilen profili onayın hükmüyle yeniden denetler: öğe yoksa 404; çözülmüş,
eski sürüm, onay bekleyen profil değil, satır 7 artık uymuyor ya da düzeltilen ad/doğum tarihi
kayıtlı bir çalışana uyuyorsa (ikinci çalışan açılmaz; belge o çalışana atanır) 409 — yanıt
`queue_new_profile.html` parçasıdır.
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import PurePosixPath
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import ColumnElement, Select, and_, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.config import Settings, get_settings
from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    Event,
    KnownDocumentType,
    Plan,
    QueueItem,
    QueueKind,
    UploadFile,
)
from app.db.session import get_session
from app.events import EventType
from app.matching.match import (
    DATE_OF_BIRTH,
    GIVEN_NAMES,
    NATIONALITY,
    ORIGINAL_SCRIPT_NAME,
    OTHER_NAMES,
    PROFILE_FIELDS,
    PROFILE_TEXT_MAX_LENGTH,
    SURNAME,
    EmployeeAction,
    ProfileFields,
    ProposedProfile,
    check_profile_fields,
    edited_profile_fields,
)
from app.pipeline.plan import PlanEmployee, PlanIntegrityError
from app.pipeline.route import (
    ApprovedProfile,
    AssignedItem,
    AssigneeNotFoundError,
    QueueAssignmentError,
    QueueItemNotFoundError,
    QueueItemReferenceError,
    QueueSourceIntegrityError,
    approve_queued_profile,
    assign_queue_item,
    review_queued_profile,
)
from app.storage import (
    DataLayout,
    DocumentNotArchivableError,
    archive_document,
)
from app.web.auth import PanelUser, require_api_user, require_panel_user
from app.web.confirm import (
    CONFIRMATION_HEADER,
    CONFIRMATION_REFUSED,
    ConfirmationRefusedError,
    Operation,
    confirm_operation,
    first_text,
    issue_confirmation,
    second_text,
)
from app.web.routers.documents import SourceView, _reference, _source_view
from app.web.routers.employees import MAX_QUERY_LENGTH, EmployeeListing, list_employees
from app.web.routers.upload_page import (
    QUEUE_LABELS,
    EventView,
    _event_place,
    _format_ts,
    _plan_employee_text,
    _source_text,
)
from app.web.routers.uploads import get_layout
from app.web.templating import MENU_BY_KEY, render_page

router = APIRouter(prefix="/api/queue", tags=["queue"])
pages_router = APIRouter(tags=["queue-pages"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]
ApiUser = Annotated[PanelUser, Depends(require_api_user)]
ConfirmationHeader = Annotated[str | None, Header(alias=CONFIRMATION_HEADER)]


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


class ConfirmationResponse(BaseModel):
    """Hazırlık isteğinin yanıtı (§20.6.1 adım 2): §20.6'nın iki onay metni, tek kullanımlık
    belirteç (asıl istekte `X-Confirmation-Token` başlığı) ve son geçerlilik anı."""

    operation: str
    first_confirmation: str
    second_confirmation: str
    confirmation: str
    expires_at: datetime


def _confirm_api(
    session: Session,
    request: Request,
    user: PanelUser,
    operation: Operation,
    target: str,
    token: str | None,
    **event: Any,
) -> None:
    """API isteğinin belirtecini tüketir ve `USER_CONFIRMED`'ı yazar; geçersizse 400 (hiçbir şey
    yazılmaz, oturum geri alınır)."""
    try:
        confirm_operation(session, request, user, operation, target, token, **event)
    except ConfirmationRefusedError:
        session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, CONFIRMATION_REFUSED) from None


def _issued(
    session: Session,
    request: Request,
    user: PanelUser,
    operation: Operation,
    target: str,
    **texts: str,
) -> ConfirmationResponse:
    """Hazırlık isteği: belirteci üretir ve commit eder; oturum çerezi yoksa 400."""
    try:
        issued = issue_confirmation(session, request, user, operation, target)
    except ConfirmationRefusedError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    session.commit()
    return ConfirmationResponse(
        operation=operation.value,
        first_confirmation=first_text(operation, **texts),
        second_confirmation=second_text(operation, **texts),
        confirmation=issued.token,
        expires_at=issued.expires_at,
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


@router.post("/{queue_item_id}/assign/prepare", response_model=ConfirmationResponse)
def prepare_queue_assignment(
    queue_item_id: int,
    body: QueueAssignmentRequest,
    request: Request,
    user: ApiUser,
    session: Annotated[Session, Depends(get_session)],
) -> ConfirmationResponse:
    """08.2.1 / 10.8.1 — atamanın hazırlığı: onay metinleri ve tek kullanımlık belirteç. Öğe ya
    da çalışan yoksa 404, öğe atanamıyorsa 409; hiçbir şey atanmaz."""
    try:
        _assignable_item(session, queue_item_id)
        assignee = _assignee(session, body.employee_id)
    except HTTPException:
        session.rollback()
        raise
    return _issued(
        session,
        request,
        user,
        Operation.ASSIGN,
        assignment_subject(queue_item_id, assignee.id),
        name=assignee.name,
    )


@router.post("/{queue_item_id}/assign", response_model=QueueAssignmentResponse)
def assign_queue_item_to_employee(
    queue_item_id: int,
    body: QueueAssignmentRequest,
    request: Request,
    user: ApiUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    settings: Annotated[Settings, Depends(get_settings)],
    token: ConfirmationHeader = None,
) -> QueueAssignmentResponse:
    """08.2.1 — kuyruk öğesini çalışana atar; çıktı üretilir, yapay zekâ çağrılmaz. İkinci onayın
    belirteci olmadan hiçbir şey yapılmaz (400); onay olayı ve atama tek işlemdedir."""
    queue_item = session.get(QueueItem, queue_item_id)
    if queue_item is None:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, QUEUE_ITEM_NOT_FOUND)
    _confirm_api(
        session,
        request,
        user,
        Operation.ASSIGN,
        assignment_subject(queue_item_id, body.employee_id),
        token,
        event_target={"queue_item_id": queue_item_id, "employee_id": body.employee_id},
        upload_id=queue_item.upload_id,
    )
    try:
        assigned = _assign(
            session, layout, settings, queue_item_id, body.employee_id, actor=user.username
        )
    except HTTPException:
        session.rollback()
        raise
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


def _archivable_document(session: Session, document_id: int) -> Document:
    """Arşivlenebilecek (etkin) belge; yoksa 404, etkin değilse 409."""
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Belge bulunamadı: {document_id}")
    if document.status != DocumentStatus.ACTIVE.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Belge {document.id} arşivlenemez: durum {document.status!r} "
            "(yalnız etkin belge arşivlenir)",
        )
    return document


def archive_subject(document_id: int) -> str:
    """Arşiv belirtecinin bağlı olduğu hedef: belge."""
    return str(document_id)


@router.post("/documents/{document_id}/archive/prepare", response_model=ConfirmationResponse)
def prepare_document_archive(
    document_id: int,
    request: Request,
    user: ApiUser,
    session: Annotated[Session, Depends(get_session)],
) -> ConfirmationResponse:
    """08.4.1 / 10.8.1 — arşivin hazırlığı: onay metinleri ve tek kullanımlık belirteç. Belge
    yoksa 404, etkin değilse 409; hiçbir şey taşınmaz."""
    try:
        _archivable_document(session, document_id)
    except HTTPException:
        session.rollback()
        raise
    return _issued(session, request, user, Operation.ARCHIVE, archive_subject(document_id))


@router.post("/documents/{document_id}/archive", response_model=DocumentArchiveResponse)
def archive_document_endpoint(
    document_id: int,
    request: Request,
    user: ApiUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    token: ConfirmationHeader = None,
) -> DocumentArchiveResponse:
    """08.4.1 — etkin belgeyi `Archive/<yyyy-mm>/`'e taşır; belge silinmez, durumu güncellenir.
    İkinci onayın belirteci olmadan hiçbir şey yapılmaz (400); onay olayı ve arşiv tek işlemde."""
    document = session.get(Document, document_id)
    if document is None:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Belge bulunamadı: {document_id}")
    _confirm_api(
        session,
        request,
        user,
        Operation.ARCHIVE,
        archive_subject(document_id),
        token,
        event_target={"document_id": document_id},
        document_id=document_id,
        employee_id=document.employee_id,
    )
    try:
        archived = archive_document(session, layout, document_id, actor=user.username)
    except DocumentNotArchivableError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    session.commit()
    document = archived.document
    return DocumentArchiveResponse(
        document_id=document.id,
        employee_id=document.employee_id,
        type_slug=document.type_slug,
        path=document.path,
        status=document.status,
        archived_by=user.username,
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
    profile_form: list[ProfileFieldView] | None
    profile_note: str | None


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
    profile_form, profile_note = _profile_section(session, queue_item, state)
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
        profile_form=profile_form,
        profile_note=profile_note,
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

# §20.6: metinler birebir `app.web.confirm`'dadır; `<Ad Soyad>` seçilen çalışanın adıyla dolar.
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
    """Atama belirtecinin (`Operation.ASSIGN`) bağlı olduğu hedef: kuyruk öğesi + seçilen
    çalışan."""
    return f"{queue_item_id}:{employee_id}"


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
        first_confirmation=first_text(Operation.ASSIGN, name=assignee.name),
    )


@pages_router.post("/queues/{queue_item_id}/assign/prepare", response_class=HTMLResponse)
def prepare_assignment(
    queue_item_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    employee_id: Annotated[str, Form(max_length=MAX_QUERY_LENGTH)],
) -> HTMLResponse:
    """10.7.2 — birinci onaydan sonra ikinci onay metnini ve tek kullanımlık onay belirtecini
    verir (§20.6.1)."""
    try:
        _assignable_item(session, queue_item_id)
        assignee = _assignee(session, employee_id)
        issued = issue_confirmation(
            session, request, user, Operation.ASSIGN, assignment_subject(queue_item_id, assignee.id)
        )
    except HTTPException as exc:
        session.rollback()
        return _assign_result(request, exc.status_code, queue_item_id, error=str(exc.detail))
    except ConfirmationRefusedError as exc:
        session.rollback()
        return _assign_result(request, status.HTTP_400_BAD_REQUEST, queue_item_id, error=str(exc))
    session.commit()
    return _assign_result(
        request,
        status.HTTP_200_OK,
        queue_item_id,
        assignee=assignee,
        second_confirmation=second_text(Operation.ASSIGN),
        confirmation=issued.token,
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

    Belirteç yoksa, süresi geçmişse, kullanılmışsa ya da başka öğeye, çalışana veya oturuma
    aitse hiçbir şey yapılmaz (400). Belirtecin tüketilmesi, onay olayı ve atama tek işlemdedir:
    atama düşerse onay olayı da yazılmaz, belirteç tüketilmemiş kalır.
    """
    try:
        queue_item = _assignable_item(session, queue_item_id)
        # §20.6.1: belirteç tüketilir ve `USER_CONFIRMED` (kullanıcı adı, işlem, hedef, iki onayın
        # zamanı) yazılır, ardından işlemin kendi olayı (`MANUAL_ASSIGN`) düşer.
        confirm_operation(
            session,
            request,
            user,
            Operation.ASSIGN,
            assignment_subject(queue_item_id, employee_id),
            confirmation,
            event_target={"queue_item_id": queue_item.id, "employee_id": employee_id},
            upload_id=queue_item.upload_id,
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


# --- 10.7.3: kuyruktan profil oluşturma ---------------------------------------------------------

# §20.6 "Onay bekleyen profili onayla": metinler birebir `app.web.confirm`'dadır; `<Ad Soyad>`
# onaylanan ad-soyadla dolar.
PROFILE_RESOLVED_NOTE = "Bu öğe zaten çözülmüş; profil oluşturulamaz."
NOT_PENDING_NOTE = (
    "Bu öğe onay bekleyen profil değil (§20.2.2 satır 7): kişisi yeni çalışan olarak açılmaz, "
    "belge kayıtlı bir çalışana atanır."
)
INVALID_PROFILE = "Profil alanları geçersiz; düzeltip yeniden gönderin."
BAD_DATE = "YYYY-AA-GG biçiminde bir tarih olmalı"
PROFILE_LABELS = {
    GIVEN_NAMES: "Ad",
    SURNAME: "Soyad",
    OTHER_NAMES: "Diğer isimler",
    ORIGINAL_SCRIPT_NAME: "Orijinal yazım",
    DATE_OF_BIRTH: "Doğum tarihi",
    NATIONALITY: "Vatandaşlık",
}
# 05.2.2: ad, soyad ve diğer isimler yalnız Latin harfi taşır; Latin yazımı belgede olmayan
# öneride ad ve soyad boş gelir, İK yazar.
_LATIN_HINT = "Latin harfleriyle (belgedeki Latin yazım ya da MRZ; aksanlı harf olur)"
_PROFILE_HINTS = {
    GIVEN_NAMES: _LATIN_HINT,
    SURNAME: _LATIN_HINT,
    OTHER_NAMES: _LATIN_HINT,
    ORIGINAL_SCRIPT_NAME: "Belgedeki Latin olmayan yazım (ör. Kiril)",
    NATIONALITY: "ICAO kodu (ör. RUS, SRB, D)",
}
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


@dataclass(frozen=True, slots=True)
class ProfileFieldView:
    """Düzenleme formunun bir alanı. Form yalnız çalışan kaydının altı alanını taşır; belgenin
    içeriği (sayfalar, tür, okumalar) formda yoktur (K17)."""

    name: str
    label: str
    value: str
    input_type: str
    required: bool
    maxlength: int
    hint: str | None


@dataclass(frozen=True, slots=True)
class ProfileRowView:
    """Onay adımlarında gösterilen alan: onaylanacak değer ve öneriden farklı olup olmadığı."""

    label: str
    value: str
    edited: bool


class _ProfileFormError(Exception):
    """Formun alanları geçersiz: alan adı → sorun (kişisel değer yok)."""

    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__(INVALID_PROFILE)
        self.errors = errors


def profile_form(
    given_names: Annotated[str, Form()] = "",
    surname: Annotated[str, Form()] = "",
    other_names: Annotated[str, Form()] = "",
    original_script_name: Annotated[str, Form()] = "",
    date_of_birth: Annotated[str, Form()] = "",
    nationality: Annotated[str, Form()] = "",
) -> dict[str, str]:
    """Formun profil alanları, kırpılmış (`PROFILE_FIELDS` anahtarlı). Başka form alanı okunmaz:
    tür, sayfa ya da belge içeriği bu akışla gönderilemez (K17)."""
    return {
        GIVEN_NAMES: given_names.strip(),
        SURNAME: surname.strip(),
        OTHER_NAMES: other_names.strip(),
        ORIGINAL_SCRIPT_NAME: original_script_name.strip(),
        DATE_OF_BIRTH: date_of_birth.strip(),
        NATIONALITY: nationality.strip().upper(),
    }


ProfileValues = Annotated[dict[str, str], Depends(profile_form)]


def _parse_profile(values: dict[str, str]) -> ProfileFields:
    """Formun değerlerinden onaylanacak profil; geçersizse `_ProfileFormError`
    (`check_profile_fields` + tarih biçimi). Boş isteğe bağlı alan `None`'dır."""
    errors: dict[str, str] = {}
    born: date | None = None
    text = values[DATE_OF_BIRTH]
    if text:
        try:
            if not _ISO_DATE.fullmatch(text):
                raise ValueError(text)
            born = date.fromisoformat(text)
        except ValueError:
            errors[DATE_OF_BIRTH] = BAD_DATE
    fields = ProfileFields(
        given_names=values[GIVEN_NAMES],
        surname=values[SURNAME],
        other_names=values[OTHER_NAMES] or None,
        original_script_name=values[ORIGINAL_SCRIPT_NAME] or None,
        date_of_birth=born,
        nationality=values[NATIONALITY] or None,
    )
    errors = {**check_profile_fields(fields), **errors}
    if errors:
        raise _ProfileFormError(errors)
    return fields


def _profile_values(fields: ProfileFields) -> dict[str, str]:
    return {name: value or "" for name, value in fields.values().items()}


def profile_subject(queue_item_id: int, fields: ProfileFields) -> str:
    """Profil onayı belirtecinin (`Operation.APPROVE_PROFILE`) bağlı olduğu hedef: kuyruk öğesi +
    onaylanan alanların özeti. İkinci onaydan sonra bir alan değişirse belirteç geçmez; değerler
    belirtece girmez."""
    canonical = json.dumps(fields.values(), ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{queue_item_id}:{digest}"


def _proposes_profile(payload: Any) -> bool:
    guess = _employee_guess(payload)
    return guess is not None and guess.action is EmployeeAction.PENDING


def _profile_refusal(session: Session, queue_item: QueueItem) -> str | None:
    """Öğeden profil oluşturulamıyorsa nedeni: çözülmüş, eski sürüm (K18) ya da onay bekleyen
    profil değil (§20.2.2 satır 7)."""
    state = _item_state(session, queue_item)
    if state is QueueState.RESOLVED:
        return PROFILE_RESOLVED_NOTE
    if state is QueueState.SUPERSEDED:
        return SUPERSEDED_NOTE
    if not _proposes_profile(queue_item.payload_json):
        return NOT_PENDING_NOTE
    return None


def _reviewed_profile(
    session: Session, queue_item_id: int, fields: ProfileFields | None = None
) -> ProposedProfile:
    """Onayın okuyacağı öneri (`review_queued_profile`): öğe yoksa 404, onaylanamıyorsa (satır 7
    artık uymuyor, düzeltilen profil kayıtlı çalışana uyuyor…) 409 ve nedeni."""
    try:
        return review_queued_profile(session, queue_item_id, fields=fields)
    except QueueItemNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, QUEUE_ITEM_NOT_FOUND) from None
    except (QueueAssignmentError, PlanIntegrityError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None


def _confirmed_profile(
    session: Session, queue_item_id: int, values: dict[str, str]
) -> tuple[QueueItem, ProfileFields, ProposedProfile]:
    """Adımların ortak denetimi: öğe (404/409), formun alanları (`_ProfileFormError`) ve onayın
    hükmü düzeltilen profille (409)."""
    queue_item = session.get(QueueItem, queue_item_id)
    if queue_item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, QUEUE_ITEM_NOT_FOUND)
    refusal = _profile_refusal(session, queue_item)
    if refusal is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, refusal)
    fields = _parse_profile(values)
    return queue_item, fields, _reviewed_profile(session, queue_item_id, fields)


def _profile_section(
    session: Session, queue_item: QueueItem, state: QueueState
) -> tuple[list[ProfileFieldView] | None, str | None]:
    """Öğe detayındaki profil bölümü: bekleyen onay bekleyen profil öğesinde öneriyle dolu form ya
    da neden onaylanamadığı; öteki öğelerde bölüm yok (`None, None`)."""
    if state is not QueueState.OPEN or not _proposes_profile(queue_item.payload_json):
        return None, None
    try:
        proposal = _reviewed_profile(session, queue_item.id)
    except HTTPException as exc:
        return None, str(exc.detail)
    return _profile_form_fields(_profile_values(proposal.fields())), None


def _profile_form_fields(values: dict[str, str]) -> list[ProfileFieldView]:
    return [
        ProfileFieldView(
            name=name,
            label=PROFILE_LABELS[name],
            value=values[name],
            input_type="date" if name == DATE_OF_BIRTH else "text",
            required=name in (GIVEN_NAMES, SURNAME),
            maxlength=3 if name == NATIONALITY else PROFILE_TEXT_MAX_LENGTH,
            hint=_PROFILE_HINTS.get(name),
        )
        for name in PROFILE_FIELDS
    ]


def _profile_rows(proposal: ProposedProfile, fields: ProfileFields) -> list[ProfileRowView]:
    edited = edited_profile_fields(proposal, fields)
    return [
        ProfileRowView(
            label=PROFILE_LABELS[name],
            value=_profile_text(name, value),
            edited=name in edited,
        )
        for name, value in fields.values().items()
    ]


def _profile_text(name: str, value: str | None) -> str:
    if value is None:
        return "—"
    if name == DATE_OF_BIRTH:
        return date.fromisoformat(value).strftime("%d.%m.%Y")
    return value


def _profile_result(
    request: Request, status_code: int, queue_item_id: int, **context: object
) -> HTMLResponse:
    """`queue_new_profile.html` parçası (HTMX hedefi: öğe detayındaki `#profile-step`)."""
    return render_page(
        request,
        "queue_new_profile.html",
        user=None,
        status_code=status_code,
        queue_item_id=queue_item_id,
        **context,
    )


def _invalid_profile(request: Request, queue_item_id: int, errors: dict[str, str]) -> HTMLResponse:
    return _profile_result(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        queue_item_id,
        error=INVALID_PROFILE,
        field_errors=[
            (PROFILE_LABELS[name], errors[name]) for name in PROFILE_FIELDS if name in errors
        ],
    )


def _steps_context(fields: ProfileFields, proposal: ProposedProfile) -> dict[str, object]:
    # Onay adımlarının ortak içeriği: onaylanacak değerler ve bir sonraki adıma taşınan alanlar.
    return {"rows": _profile_rows(proposal, fields), "hidden": _profile_values(fields)}


@pages_router.post("/queues/{queue_item_id}/profile/confirm", response_class=HTMLResponse)
def profile_first_confirmation(
    queue_item_id: int,
    request: Request,
    _user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    values: ProfileValues,
) -> HTMLResponse:
    """10.7.3 — düzenlenen profille birinci onay metni (§20.6); hiçbir şey değişmez."""
    try:
        _, fields, proposal = _confirmed_profile(session, queue_item_id, values)
    except HTTPException as exc:
        return _profile_result(request, exc.status_code, queue_item_id, error=str(exc.detail))
    except _ProfileFormError as exc:
        return _invalid_profile(request, queue_item_id, exc.errors)
    finally:
        session.rollback()
    return _profile_result(
        request,
        status.HTTP_200_OK,
        queue_item_id,
        first_confirmation=first_text(
            Operation.APPROVE_PROFILE, name=f"{fields.given_names} {fields.surname}"
        ),
        **_steps_context(fields, proposal),
    )


@pages_router.post("/queues/{queue_item_id}/profile/prepare", response_class=HTMLResponse)
def prepare_profile(
    queue_item_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    values: ProfileValues,
) -> HTMLResponse:
    """10.7.3 — birinci onaydan sonra ikinci onay metnini ve onaylanan alanlara bağlı tek
    kullanımlık onay belirtecini verir (§20.6.1)."""
    try:
        _, fields, proposal = _confirmed_profile(session, queue_item_id, values)
        issued = issue_confirmation(
            session,
            request,
            user,
            Operation.APPROVE_PROFILE,
            profile_subject(queue_item_id, fields),
        )
    except HTTPException as exc:
        session.rollback()
        return _profile_result(request, exc.status_code, queue_item_id, error=str(exc.detail))
    except _ProfileFormError as exc:
        session.rollback()
        return _invalid_profile(request, queue_item_id, exc.errors)
    except ConfirmationRefusedError as exc:
        session.rollback()
        return _profile_result(request, status.HTTP_400_BAD_REQUEST, queue_item_id, error=str(exc))
    session.commit()
    return _profile_result(
        request,
        status.HTTP_200_OK,
        queue_item_id,
        second_confirmation=second_text(Operation.APPROVE_PROFILE),
        confirmation=issued.token,
        **_steps_context(fields, proposal),
    )


def _approve_profile(
    session: Session,
    layout: DataLayout,
    settings: Settings,
    queue_item_id: int,
    fields: ProfileFields,
    *,
    actor: str,
) -> ApprovedProfile:
    """`approve_queued_profile`'ı çağırır; öğe yoksa 404, onaylanamıyorsa 409 ve nedeni. Oturum
    commit edilmez; hata olursa hiçbir şey yazılmadı."""
    try:
        return approve_queued_profile(
            session,
            layout,
            queue_item_id,
            actor=actor,
            render_image_dpi=settings.render_image_dpi,
            render_image_jpeg_quality=settings.render_image_jpeg_quality,
            fields=fields,
        )
    except QueueItemNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except (
        QueueAssignmentError,
        PlanIntegrityError,
        QueueItemReferenceError,
        QueueSourceIntegrityError,
    ) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None


@pages_router.post("/queues/{queue_item_id}/profile", response_class=HTMLResponse)
def create_profile_from_queue(
    queue_item_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    settings: Annotated[Settings, Depends(get_settings)],
    values: ProfileValues,
    confirmation: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    """10.7.3 — ikinci onayın belirteciyle önerilen (düzenlenmiş olabilir) profili onaylar:
    çalışan açılır, belge ona bağlanır (08.3.1; K7, K16).

    Belirteç yoksa, süresi geçmişse, kullanılmışsa ya da başka öğeye, başka alan değerlerine,
    başka işleme veya oturuma aitse hiçbir şey yapılmaz (400). Belirtecin tüketilmesi, onay olayı ve
    onay tek işlemdedir: onay düşerse onay olayı da yazılmaz. Belge içeriği değişmez: çıktı kaynak
    sayfalardan planın işlemiyle üretilir.
    """
    try:
        queue_item, fields, _ = _confirmed_profile(session, queue_item_id, values)
        # §20.6.1: belirteç tüketilir ve `USER_CONFIRMED` (kullanıcı adı, işlem, hedef, iki onayın
        # zamanı) yazılır, ardından işlemin kendi olayı (`MANUAL_APPROVE`) düşer. Profil değerleri
        # olaya girmez (CONVENTIONS §6).
        confirm_operation(
            session,
            request,
            user,
            Operation.APPROVE_PROFILE,
            profile_subject(queue_item_id, fields),
            confirmation,
            event_target={"queue_item_id": queue_item.id},
            upload_id=queue_item.upload_id,
        )
        approved = _approve_profile(
            session, layout, settings, queue_item_id, fields, actor=user.username
        )
    except HTTPException as exc:
        session.rollback()
        return _profile_result(request, exc.status_code, queue_item_id, error=str(exc.detail))
    except _ProfileFormError as exc:
        session.rollback()
        return _invalid_profile(request, queue_item_id, exc.errors)
    except ConfirmationRefusedError:
        session.rollback()
        return _profile_result(
            request, status.HTTP_400_BAD_REQUEST, queue_item_id, error=CONFIRMATION_REFUSED
        )
    session.commit()
    employee, document = approved.employee, approved.executed.document
    return _profile_result(
        request,
        status.HTTP_200_OK,
        queue_item_id,
        done=True,
        employee=AssigneeView(id=employee.id, name=f"{employee.given_names} {employee.surname}"),
        document_id=document.id,
        file_name=PurePosixPath(document.path).name,
    )
