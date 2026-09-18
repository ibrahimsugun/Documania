"""Belge geçmişi görünümü (PRD 10.6.1).

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
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    Employee,
    Event,
    KnownDocumentType,
    Page,
    Plan,
    UploadFile,
)
from app.db.session import get_session
from app.events import EventType
from app.storage import DataLayout
from app.web.auth import PanelUser, require_panel_user
from app.web.routers.employees import _stored_file
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
