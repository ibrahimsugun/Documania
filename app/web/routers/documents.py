"""Belge geçmişi görünümü (PRD 10.6.1), belgeyi başka çalışana taşıma (PRD 10.8.2), arşive taşıma
ve arşivden geri alma (PRD 08.4.1, 10.5.10).

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

**Arşive taşıma ve arşivden geri alma (08.4.1, 10.5.10; K16, §D61).** Profilin belge satırından
açılır; iki akış da aynı üç adımlı kalıptadır (10.8.1) ve `document_archive_step.html` sayfasını
kullanır: `GET /documents/{id}/archive/confirm` birinci onay metni, `POST …/archive/prepare`
ikinci metin ve belgeye bağlı tek kullanımlık belirteç, `POST …/archive` belirteçle
`archive_document` (`ARCHIVED`); geri alma aynı sırayla `/documents/{id}/unarchive/*` ve
`unarchive_document` (`UNARCHIVED`, dosya `Hazir/`'a K8 adıyla döner). JSON API
(`/api/queue/documents/{id}/archive*`) yerinde kalır. Arşive yalnız etkin, geri almaya yalnız
arşivdeki belge girer (eski sürüm hiçbirine, K18); belge yoksa 404, durumu uymuyorsa, dosyası yoksa
ya da sahibi birleştirilmişse 409. Başarıdan sonra profile dönülür; paketler ve `profil.md`
servisin içinde yenilenir. Dosya yalnız taşınır ve yeniden adlandırılır (K11).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeStatus,
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
    DocumentNotArchivableError,
    DocumentNotMovableError,
    DocumentNotRestorableError,
    MovedDocument,
    archive_document,
    move_document,
    unarchive_document,
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


# --- 08.4.1, 10.5.10: arşive taşıma ve arşivden geri alma (profilden) ----------------------------

NOT_ARCHIVABLE_NOTE = "Yalnız etkin belge arşive taşınır; bu belgenin durumu: {status}."
NOT_RESTORABLE_NOTE = "Yalnız arşivdeki belge geri alınır; bu belgenin durumu: {status}."
DOCUMENT_FILE_MISSING = "Belgenin dosyası bulunamadı; taşınamaz."
OWNER_MERGED = (
    "Belgenin sahibi başka bir kayıtla birleştirildi (10.5.9); işlemi kalan kaydın profilinden "
    "yapın."
)


@dataclass(frozen=True, slots=True)
class ArchiveFlow:
    """Profilden açılan iki akıştan biri: arşive taşı (`archive`) ya da arşivden geri al
    (`unarchive`). `action` yolun parçasıdır; `notice` profil bildiriminin kodudur."""

    action: str
    operation: Operation
    required_status: str
    refusal: str
    title: str
    submit_label: str
    hint: str
    notice: str


ARCHIVE_FLOW = ArchiveFlow(
    action="archive",
    operation=Operation.ARCHIVE,
    required_status=DocumentStatus.ACTIVE.value,
    refusal=NOT_ARCHIVABLE_NOTE,
    title="Belgeyi arşive taşı",
    submit_label="Evet, arşive taşı",
    hint=(
        'Belge silinmez: Archive klasörüne taşınır, profilde "Arşivlendi" durumuyla kalır ve '
        '"Arşivden geri al" ile çalışanın Hazır klasörüne döndürülebilir. Arşivdeki belge belge '
        "paketlerinde sayılmaz."
    ),
    notice="document_archived",
)
UNARCHIVE_FLOW = ArchiveFlow(
    action="unarchive",
    operation=Operation.UNARCHIVE,
    required_status=DocumentStatus.ARCHIVED.value,
    refusal=NOT_RESTORABLE_NOTE,
    title="Belgeyi arşivden geri al",
    submit_label="Evet, geri al",
    hint=(
        "Belge çalışanın bugünkü adıyla ve türünün dosya etiketiyle adlandırılır (K8); arada aynı "
        "türden yeni belge geldiyse sıradaki sıra ekini alır. İçeriği ve kökeni değişmez."
    ),
    notice="document_unarchived",
)


@dataclass(frozen=True, slots=True)
class ArchiveStepView:
    document_id: int
    employee_id: str
    employee: str
    type_name: str
    file_name: str
    status_label: str


def document_subject(document_id: int) -> str:
    """Arşiv ve geri alma belirtecinin bağlı olduğu hedef: belge (JSON API'nin arşiv hedefiyle
    aynı biçim)."""
    return str(document_id)


def _archive_step(
    session: Session, layout: DataLayout, document_id: int, flow: ArchiveFlow
) -> ArchiveStepView:
    """Akışa girebilecek belge: yoksa 404; durumu akışın istediği değilse, dosyası yoksa ya da
    sahibi birleştirilmişse 409."""
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DOCUMENT_NOT_FOUND)
    if document.status != flow.required_status:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            flow.refusal.format(
                status=DOCUMENT_STATUS_LABELS.get(document.status, document.status)
            ),
        )
    owner = session.get_one(Employee, document.employee_id)
    if owner.status == EmployeeStatus.MERGED.value:
        raise HTTPException(status.HTTP_409_CONFLICT, OWNER_MERGED)
    if _stored_file(layout, document.path) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, DOCUMENT_FILE_MISSING)
    document_type = session.get(KnownDocumentType, document.type_slug)
    return ArchiveStepView(
        document_id=document.id,
        employee_id=owner.id,
        employee=_employee_name(owner),
        type_name=document_type.name if document_type is not None else document.type_slug,
        file_name=PurePosixPath(document.path).name,
        status_label=DOCUMENT_STATUS_LABELS.get(document.status, document.status),
    )


def _archive_page(
    request: Request,
    user: PanelUser,
    flow: ArchiveFlow,
    document_id: int,
    *,
    step: ArchiveStepView | None,
    status_code: int = status.HTTP_200_OK,
    **context: object,
) -> HTMLResponse:
    """`document_archive_step.html`: birinci onay, ikinci onay ya da hata."""
    return render_page(
        request,
        "document_archive_step.html",
        user=user,
        active=MENU_BY_KEY["employees"].key,
        status_code=status_code,
        flow=flow,
        document_id=document_id,
        step=step,
        **context,
    )


def _first_confirmation(
    request: Request,
    user: PanelUser,
    session: Session,
    layout: DataLayout,
    document_id: int,
    flow: ArchiveFlow,
) -> HTMLResponse:
    """Belge ve §20.6'nın birinci onay metni; hiçbir şey değişmez."""
    try:
        step = _archive_step(session, layout, document_id, flow)
    except HTTPException as exc:
        return _archive_page(
            request,
            user,
            flow,
            document_id,
            step=None,
            status_code=exc.status_code,
            error=exc.detail,
        )
    finally:
        session.rollback()
    return _archive_page(
        request,
        user,
        flow,
        document_id,
        step=step,
        first_confirmation=first_text(flow.operation),
    )


def _prepare(
    request: Request,
    user: PanelUser,
    session: Session,
    layout: DataLayout,
    document_id: int,
    flow: ArchiveFlow,
) -> HTMLResponse:
    """Birinci onaydan sonra ikinci onay metni ve belgeye bağlı tek kullanımlık belirteç
    (§20.6.1). Belge değişmez (S16)."""
    step: ArchiveStepView | None = None
    try:
        step = _archive_step(session, layout, document_id, flow)
        issued = issue_confirmation(
            session, request, user, flow.operation, document_subject(document_id)
        )
    except HTTPException as exc:
        session.rollback()
        return _archive_page(
            request,
            user,
            flow,
            document_id,
            step=None,
            status_code=exc.status_code,
            error=exc.detail,
        )
    except ConfirmationRefusedError as exc:  # oturum çerezi yok
        session.rollback()
        return _archive_page(
            request,
            user,
            flow,
            document_id,
            step=step,
            status_code=status.HTTP_400_BAD_REQUEST,
            error=str(exc),
        )
    session.commit()
    return _archive_page(
        request,
        user,
        flow,
        document_id,
        step=step,
        second_confirmation=second_text(flow.operation),
        confirmation=issued.token,
    )


def _complete(
    request: Request,
    user: PanelUser,
    session: Session,
    layout: DataLayout,
    document_id: int,
    flow: ArchiveFlow,
    confirmation: str | None,
) -> Response:
    """İkinci onayın belirteciyle işlemi yapar. Belirteç yoksa, süresi geçmişse, kullanılmışsa ya
    da başka belgeye, işleme veya oturuma aitse hiçbir şey yapılmaz (400). Belirtecin tüketilmesi,
    `USER_CONFIRMED` ve işlemin olayı (`ARCHIVED` / `UNARCHIVED`) tek işlemdedir; başarıdan sonra
    profilin belge bölümüne dönülür."""
    step: ArchiveStepView | None = None
    try:
        step = _archive_step(session, layout, document_id, flow)
        # §20.6.1: belirteç tüketilir ve `USER_CONFIRMED` yazılır, ardından işlemin kendi olayı
        # düşer.
        confirm_operation(
            session,
            request,
            user,
            flow.operation,
            document_subject(document_id),
            confirmation,
            event_target={"document_id": document_id},
            document_id=document_id,
            employee_id=step.employee_id,
        )
        try:
            if flow is ARCHIVE_FLOW:
                archive_document(session, layout, document_id, actor=user.username)
            else:
                unarchive_document(session, layout, document_id, actor=user.username)
        except (
            DocumentNotArchivableError,
            DocumentNotRestorableError,
            ContentMismatchError,
        ) as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except HTTPException as exc:
        session.rollback()
        return _archive_page(
            request,
            user,
            flow,
            document_id,
            step=None,
            status_code=exc.status_code,
            error=exc.detail,
        )
    except ConfirmationRefusedError:
        session.rollback()
        return _archive_page(
            request,
            user,
            flow,
            document_id,
            step=step,
            status_code=status.HTTP_400_BAD_REQUEST,
            error=CONFIRMATION_REFUSED,
            retry=True,
        )
    session.commit()
    return RedirectResponse(
        f"/employees/{step.employee_id}?notice={flow.notice}#documents",
        status.HTTP_303_SEE_OTHER,
    )


@router.get("/documents/{document_id}/archive/confirm", response_class=HTMLResponse)
def archive_first_confirmation(
    document_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
) -> HTMLResponse:
    """08.4.1 — arşive taşınacak belge ve §20.6'nın birinci onay metni; hiçbir şey değişmez."""
    return _first_confirmation(request, user, session, layout, document_id, ARCHIVE_FLOW)


@router.post("/documents/{document_id}/archive/prepare", response_class=HTMLResponse)
def prepare_archive(
    document_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
) -> HTMLResponse:
    """08.4.1 — ikinci onay metni ve tek kullanımlık belirteç (§20.6.1)."""
    return _prepare(request, user, session, layout, document_id, ARCHIVE_FLOW)


@router.post("/documents/{document_id}/archive", response_class=HTMLResponse)
def archive_from_profile(
    document_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    confirmation: Annotated[str | None, Form()] = None,
) -> Response:
    """08.4.1 — belirteçle belgeyi `Archive/<yyyy-mm>/`'e taşır (K11, K16); belge silinmez."""
    return _complete(request, user, session, layout, document_id, ARCHIVE_FLOW, confirmation)


@router.get("/documents/{document_id}/unarchive/confirm", response_class=HTMLResponse)
def unarchive_first_confirmation(
    document_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
) -> HTMLResponse:
    """10.5.10 — geri alınacak belge ve birinci onay metni (§D61 → §20.6); hiçbir şey değişmez."""
    return _first_confirmation(request, user, session, layout, document_id, UNARCHIVE_FLOW)


@router.post("/documents/{document_id}/unarchive/prepare", response_class=HTMLResponse)
def prepare_unarchive(
    document_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
) -> HTMLResponse:
    """10.5.10 — ikinci onay metni ve tek kullanımlık belirteç (§20.6.1)."""
    return _prepare(request, user, session, layout, document_id, UNARCHIVE_FLOW)


@router.post("/documents/{document_id}/unarchive", response_class=HTMLResponse)
def unarchive_from_profile(
    document_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    confirmation: Annotated[str | None, Form()] = None,
) -> Response:
    """10.5.10 — belirteçle arşivdeki belgeyi sahibinin `Hazir/`'ına K8 adıyla döndürür (K8, K11,
    K16); içerik ve köken değişmez."""
    return _complete(request, user, session, layout, document_id, UNARCHIVE_FLOW, confirmation)
