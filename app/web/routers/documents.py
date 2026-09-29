"""Belge geçmişi görünümü (PRD 10.6.1) ve belgeyi başka çalışana taşıma (PRD 10.8.2).

`GET /documents/{document_id}/history` bir çıktının köken izini gösterir: çıktının kendisi
(çalışan, tür, dosya, durum, plan sürümü), **kaynak dosyaları ve sayfaları** ve belgeyi anan olaylar
(K15, R13). Kaynak, çıktının yazıldığı anda `documents.source_refs_json`'a işlenen kayıttır
(07.7.1): her kayıt bir yükleme dosyası ve o dosyadan alınan 0 tabanlı sayfalardır, boş sayfa
listesi dosyanın bütününü gösterir. İz tıklanarak yürünür:

- kaynak dosyanın adı, dosyanın yükleme detay sayfasındaki bölümüne gider (`/uploads/{id}#file-N`);
- her kaynak sayfa, sayfanın görüntüsünü açar (`/uploads/{id}/pages/{page_id}/image`, 10.3.1);
- planın öğesi ve partinin kendisi yükleme detay sayfasına bağlanır;
- çıktının kendisi çalışanın profilindeki açma bağlantısıyla açılır (10.5.2).

Sayfa yalnız okur: belge içeriği, köken kaydı ya da dosya değiştirilmez, sayfa görüntüleri olduğu
gibi sunulur (K10, K11, K17). Kaynak kaydı eksik ya da bozuksa sayfa düşmez, o kayıt bağlantısız
yazılır.

**Belgeyi başka çalışana taşıma (10.8.2; K16).** Etkin belgenin geçmiş sayfasında durur; akış
10.7.2'nin atamasıyla aynı kalıptadır ve iki aşamalı onay ister (10.8.1, `app.web.confirm`):

1. `GET /documents/{id}/move/employees?q=` yeni sahibi 10.4.2'nin aramasıyla bulur; boş aramada
   liste gelmez, belgenin şimdiki sahibi seçilemez.
2. `GET /documents/{id}/move/confirm?employee_id=` §20.6'nın **birinci** onay metnini verir.
3. `POST /documents/{id}/move/prepare` birinci onaydan sonra **ikinci** metni ve tek kullanımlık
   belirteci verir (§20.6.1 adım 1–2).
4. `POST /documents/{id}/move` ikinci onaydan sonra belirteçle gelir: belirteç tüketilir, önce
   `USER_CONFIRMED`, sonra `move_document`'in `MANUAL_MOVE`'u tek işlemde yazılır; commit'ten sonra
   iki çalışanın `profil.md`'si yeniden üretilir (09.1.1). Belirteçsiz, süresi geçmiş, kullanılmış
   ya da başka belgeye, çalışana, işleme veya oturuma ait istek 400 ve hiçbir şey değişmez (S16).

Dosya yalnız yeniden adlandırılır ve taşınır, içeriği bayt bayt aynı kalır (K11). Adımların hepsi
belgeyi yeniden denetler: belge yoksa 404, etkin değilse 409; çalışan yoksa 404, belgenin zaten
sahibiyse 409 — yanıt `document_move.html` parçasıdır (HTMX hedefi).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    Event,
    KnownDocumentType,
    Page,
    Plan,
    UploadFile,
)
from app.db.session import get_session
from app.events import EventType
from app.profiles import write_profile
from app.storage import (
    ContentMismatchError,
    DataLayout,
    DocumentNotMovableError,
    MovedDocument,
    move_document,
)
from app.web.auth import PanelUser, require_panel_user
from app.web.confirm import (
    CONFIRMATION_REFUSED,
    ConfirmationRefusedError,
    Operation,
    confirm_operation,
    first_text,
    issue_confirmation,
    second_text,
)
from app.web.routers.employees import (
    MAX_QUERY_LENGTH,
    SEARCHABLE_STATUSES,
    EmployeeListing,
    _stored_file,
    list_employees,
)
from app.web.routers.upload_page import (
    DOCUMENT_STATUS_LABELS,
    EventView,
    _employee_label,
    _event_place,
    _format_ts,
    _page_ranges,
)
from app.web.routers.uploads import get_layout
from app.web.templating import MENU_BY_KEY, render_page

router = APIRouter(tags=["documents"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]

DOCUMENT_NOT_FOUND = "Belge bulunamadı."


@dataclass(frozen=True, slots=True)
class SourcePageView:
    number: int  # 1 tabanlı; köken kaydındaki sayfa sırası 0 tabanlıdır
    image_url: str | None  # sayfa satırı ve görüntüsü kayıtlıysa


@dataclass(frozen=True, slots=True)
class SourceView:
    file_name: str
    file_url: str | None
    range_text: str
    pages: list[SourcePageView]
    note: str | None


@dataclass(frozen=True, slots=True)
class HistoryView:
    document_id: int
    employee_id: str
    employee: str
    type_name: str
    file_name: str
    format: str
    sequence_no: int
    status: str
    status_label: str
    created_at: str
    plan_version: int | None
    open_url: str | None
    upload_id: str | None
    item_id: str | None
    sources: list[SourceView]
    events: list[EventView]
    can_move: bool
    move_note: str | None


def _reference(ref: Any) -> tuple[int, list[int]] | None:
    """Köken kaydındaki `(file_id, sayfa sıraları)`; kayıt bozuksa `None`."""
    if not isinstance(ref, dict):
        return None
    file_id, pages = ref.get("file_id"), ref.get("pages", [])
    if isinstance(file_id, bool) or not isinstance(file_id, int):
        return None
    if not isinstance(pages, list) or not all(
        isinstance(page, int) and not isinstance(page, bool) for page in pages
    ):
        return None
    return file_id, pages


def _source_view(session: Session, ref: Any) -> SourceView:
    parsed = _reference(ref)
    if parsed is None:
        return SourceView("Bozuk köken kaydı", None, "", [], "Kaynak dosya ve sayfa okunamadı.")
    file_id, indexes = parsed
    upload_file = session.get(UploadFile, file_id)
    if upload_file is None:
        return SourceView(
            f"dosya {file_id}", None, _page_ranges(indexes), [], "Kaynak dosya kaydı bulunamadı."
        )
    stored = {
        page.index: page
        for page in session.scalars(
            select(Page).where(Page.file_id == file_id).order_by(Page.index)
        )
    }
    # Boş sayfa listesi dosyanın bütünüdür: dosyanın bütün sayfaları izlenir.
    wanted = sorted(set(indexes)) if indexes else sorted(stored)
    pages = [
        SourcePageView(
            number=index + 1,
            image_url=(
                f"/uploads/{upload_file.upload_id}/pages/{stored[index].id}/image"
                if index in stored and stored[index].image_path is not None
                else None
            ),
        )
        for index in wanted
    ]
    return SourceView(
        file_name=upload_file.original_name,
        file_url=f"/uploads/{upload_file.upload_id}#file-{upload_file.id}",
        range_text=_page_ranges(indexes),
        pages=pages,
        note=(
            "Bu dosya daha önce yüklenmiş bir dosyanın tekrarı; sayfa görüntüsü yok."
            if upload_file.is_duplicate_of is not None and not pages
            else None
        ),
    )


def _output_item_id(events: list[Event]) -> str | None:
    """Çıktıyı yazan planın öğe kimliği: `OUTPUT_SAVED` olayının köken verisindeki `item_id`."""
    for event in events:
        if event.type == EventType.OUTPUT_SAVED.value and isinstance(event.data_json, dict):
            item_id = event.data_json.get("item_id")
            if isinstance(item_id, str):
                return item_id
    return None


def build_history(session: Session, layout: DataLayout, document_id: int) -> HistoryView | None:
    """Belgenin köken izi ve olayları; belge yoksa `None`. Yalnız okur, oturum commit edilmez."""
    document = session.get(Document, document_id)
    if document is None:
        return None
    employee = session.get(Employee, document.employee_id)
    owners = {employee.id: employee} if employee is not None else {}
    document_type = session.get(KnownDocumentType, document.type_slug)
    plan = session.get(Plan, document.plan_id) if document.plan_id is not None else None
    refs = document.source_refs_json if isinstance(document.source_refs_json, list) else []
    sources = [_source_view(session, ref) for ref in refs]

    events = list(
        session.scalars(
            select(Event).where(Event.document_id == document.id).order_by(Event.ts, Event.id)
        )
    )
    file_ids = {parsed[0] for ref in refs if (parsed := _reference(ref)) is not None}
    file_ids.update(event.file_id for event in events if event.file_id is not None)
    files = {
        upload_file.id: upload_file
        for upload_file in session.scalars(select(UploadFile).where(UploadFile.id.in_(file_ids)))
    }

    upload_id = plan.upload_id if plan is not None else None
    if upload_id is None:
        upload_id = next((files[fid].upload_id for fid in sorted(files)), None)

    return HistoryView(
        document_id=document.id,
        employee_id=document.employee_id,
        employee=_employee_label(owners, document.employee_id),
        type_name=document_type.name if document_type is not None else document.type_slug,
        file_name=PurePosixPath(document.path).name,
        format=document.format,
        sequence_no=document.sequence_no,
        status=document.status,
        status_label=DOCUMENT_STATUS_LABELS.get(document.status, document.status),
        created_at=_format_ts(document.created_at),
        plan_version=plan.version if plan is not None else None,
        open_url=(
            f"/employees/{document.employee_id}/documents/{document.id}/file"
            if _stored_file(layout, document.path) is not None
            else None
        ),
        upload_id=upload_id,
        item_id=_output_item_id(events),
        sources=sources,
        events=[
            EventView(
                ts=_format_ts(event.ts),
                ts_iso=event.ts.isoformat(),
                type=event.type,
                actor=event.actor,
                place=_event_place(event, files),
                message=event.message,
            )
            for event in events
        ],
        can_move=_move_refusal(document) is None,
        move_note=_move_refusal(document),
    )


@router.get("/documents/{document_id}/history", response_class=HTMLResponse)
def document_history(
    document_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
) -> HTMLResponse:
    history = build_history(session, layout, document_id)
    # Okuma işlemi de SQLite'ta yazma kilidini tutar (`app.db.session`): sayfa çizilirken
    # arka plandaki bir işleyici beklemesin.
    session.rollback()
    entry = MENU_BY_KEY["employees"]
    if history is None:
        return render_page(
            request,
            "history.html",
            user=user,
            active=entry.key,
            status_code=status.HTTP_404_NOT_FOUND,
            error=DOCUMENT_NOT_FOUND,
        )
    return render_page(request, "history.html", user=user, active=entry.key, history=history)


# --- 10.8.2: belgeyi başka çalışana taşıma -------------------------------------------------------

NOT_MOVABLE_NOTE = (
    "Yalnız etkin belge başka çalışana taşınabilir; bu belgenin durumu: {status}. Eski sürüm "
    "yeniden adlandırılmaz (K18), arşivlenmiş belge çalışanın klasöründe durmaz."
)
SAME_OWNER = "Belge zaten bu çalışanın; başka bir çalışan seçin."
MOVE_TARGET_NOT_FOUND = "Çalışan bulunamadı."


@dataclass(frozen=True, slots=True)
class MoveTargetView:
    id: str
    name: str


def _employee_name(employee: Employee) -> str:
    return f"{employee.given_names} {employee.surname}"


def _move_refusal(document: Document) -> str | None:
    """Belge taşınamıyorsa nedeni: yalnız etkin belge taşınır (K18, 08.4.1)."""
    if document.status == DocumentStatus.ACTIVE.value:
        return None
    return NOT_MOVABLE_NOTE.format(
        status=DOCUMENT_STATUS_LABELS.get(document.status, document.status)
    )


def _movable_document(session: Session, document_id: int) -> Document:
    """Taşınabilecek (etkin) belge; yoksa 404, etkin değilse 409."""
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DOCUMENT_NOT_FOUND)
    refusal = _move_refusal(document)
    if refusal is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, refusal)
    return document


def _move_target(session: Session, document: Document, employee_id: str) -> MoveTargetView:
    """Belgenin taşınacağı çalışan; yoksa 404, belgenin şimdiki sahibiyse 409."""
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MOVE_TARGET_NOT_FOUND)
    if employee.id == document.employee_id:
        raise HTTPException(status.HTTP_409_CONFLICT, SAME_OWNER)
    return MoveTargetView(id=employee.id, name=_employee_name(employee))


def move_subject(document_id: int, employee_id: str) -> str:
    """Taşıma belirtecinin (`Operation.MOVE`) bağlı olduğu hedef: belge + yeni sahibi."""
    return f"{document_id}:{employee_id}"


def _move_result(
    request: Request, status_code: int, document_id: int, **context: object
) -> HTMLResponse:
    """`document_move.html` parçası (HTMX hedefi: geçmiş sayfasındaki `#move-results` ya da
    `#move-step`)."""
    return render_page(
        request,
        "document_move.html",
        user=None,
        status_code=status_code,
        document_id=document_id,
        **context,
    )


@router.get("/documents/{document_id}/move/employees", response_class=HTMLResponse)
def move_search(
    document_id: int,
    request: Request,
    _user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str, Query(max_length=MAX_QUERY_LENGTH)] = "",
) -> HTMLResponse:
    """10.8.2 — yeni sahibi arar (10.4.2'nin araması); boş aramada liste gelmez."""
    listing: EmployeeListing | None = None
    try:
        owner_id = _movable_document(session, document_id).employee_id
        if q.strip():
            listing = list_employees(session, q, statuses=SEARCHABLE_STATUSES)
    except HTTPException as exc:
        return _move_result(request, exc.status_code, document_id, error=str(exc.detail))
    finally:
        session.rollback()
    return _move_result(
        request, status.HTTP_200_OK, document_id, search=True, listing=listing, owner_id=owner_id
    )


@router.get("/documents/{document_id}/move/confirm", response_class=HTMLResponse)
def move_first_confirmation(
    document_id: int,
    request: Request,
    _user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    employee_id: Annotated[str, Query(max_length=MAX_QUERY_LENGTH)],
) -> HTMLResponse:
    """10.8.2 — seçilen çalışanla birinci onay metni (§20.6); hiçbir şey değişmez."""
    try:
        target = _move_target(session, _movable_document(session, document_id), employee_id)
    except HTTPException as exc:
        return _move_result(request, exc.status_code, document_id, error=str(exc.detail))
    finally:
        session.rollback()
    return _move_result(
        request,
        status.HTTP_200_OK,
        document_id,
        target=target,
        first_confirmation=first_text(Operation.MOVE),
    )


@router.post("/documents/{document_id}/move/prepare", response_class=HTMLResponse)
def prepare_move(
    document_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    employee_id: Annotated[str, Form(max_length=MAX_QUERY_LENGTH)],
) -> HTMLResponse:
    """10.8.2 — birinci onaydan sonra ikinci onay metnini ve tek kullanımlık onay belirtecini
    verir (§20.6.1)."""
    try:
        target = _move_target(session, _movable_document(session, document_id), employee_id)
        issued = issue_confirmation(
            session, request, user, Operation.MOVE, move_subject(document_id, target.id)
        )
    except HTTPException as exc:
        session.rollback()
        return _move_result(request, exc.status_code, document_id, error=str(exc.detail))
    except ConfirmationRefusedError as exc:
        session.rollback()
        return _move_result(request, status.HTTP_400_BAD_REQUEST, document_id, error=str(exc))
    session.commit()
    return _move_result(
        request,
        status.HTTP_200_OK,
        document_id,
        target=target,
        second_confirmation=second_text(Operation.MOVE),
        confirmation=issued.token,
    )


def _move(
    session: Session, layout: DataLayout, document_id: int, employee_id: str, *, actor: str
) -> MovedDocument:
    """`move_document`'i çağırır; taşınamıyorsa 409 ve nedeni. Belge ve çalışan aynı işlemde
    önceden denetlenmiştir (silme yok, K16). Oturum commit edilmez."""
    try:
        return move_document(session, layout, document_id, employee_id, actor=actor)
    except (DocumentNotMovableError, ContentMismatchError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None


@router.post("/documents/{document_id}/move", response_class=HTMLResponse)
def move_to_employee(
    document_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    employee_id: Annotated[str, Form(max_length=MAX_QUERY_LENGTH)],
    confirmation: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    """10.8.2 — ikinci onayın belirteciyle belgeyi başka çalışana taşır (K8, K11, K16).

    Belirteç yoksa, süresi geçmişse, kullanılmışsa ya da başka belgeye, çalışana, işleme veya
    oturuma aitse hiçbir şey yapılmaz (400). Belirtecin tüketilmesi, onay olayı ve taşıma tek
    işlemdedir: taşıma düşerse onay olayı da yazılmaz, belirteç tüketilmemiş kalır. Commit'ten
    sonra iki çalışanın da `profil.md`'si güncel hâliyle yeniden üretilir (09.1.1).
    """
    try:
        target = _move_target(session, _movable_document(session, document_id), employee_id)
        # §20.6.1: belirteç tüketilir ve `USER_CONFIRMED` (kullanıcı adı, işlem, hedef, iki onayın
        # zamanı) yazılır, ardından işlemin kendi olayı (`MANUAL_MOVE`) düşer.
        confirm_operation(
            session,
            request,
            user,
            Operation.MOVE,
            move_subject(document_id, target.id),
            confirmation,
            event_target={"document_id": document_id, "employee_id": target.id},
            document_id=document_id,
            employee_id=target.id,
        )
        moved = _move(session, layout, document_id, target.id, actor=user.username)
    except HTTPException as exc:
        session.rollback()
        return _move_result(request, exc.status_code, document_id, error=str(exc.detail))
    except ConfirmationRefusedError:
        session.rollback()
        return _move_result(
            request, status.HTTP_400_BAD_REQUEST, document_id, error=CONFIRMATION_REFUSED
        )
    session.commit()
    previous = MoveTargetView(id=moved.previous_owner.id, name=_employee_name(moved.previous_owner))
    file_name = PurePosixPath(moved.document.path).name
    # 09.1.1: iki çalışanın profili de değişti; profil taşımanın commit edilmiş hâlinden üretilir.
    for employee in (moved.previous_owner, moved.new_owner):
        write_profile(session, layout, employee)
    session.rollback()
    return _move_result(
        request,
        status.HTTP_200_OK,
        document_id,
        target=target,
        previous=previous,
        done=True,
        file_name=file_name,
    )
