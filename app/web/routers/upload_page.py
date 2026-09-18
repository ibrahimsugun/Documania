"""Yükleme sayfası ve canlı ilerleme görünümü (PRD 10.2.1, 10.2.2).

`GET /upload` sürükle-bırak çoklu yükleme formunu ve isteğe bağlı çalışan seçimini çizer.
`POST /upload` (HTMX) dosyaları `POST /api/uploads` ile aynı işlevle (`create_upload`) partiye
çevirir — boyut/sayfa sınırı (01.3.1), Inbox'a değişmez yazma (K10) ve tekrar tespiti (01.4.1)
orada kalır, burada kopyalanmaz. Parti oluşunca `process_upload` (09.2.2) arka planda başlar ve
yanıt ilerleme görünümüdür. `GET /upload/{upload_id}/progress` parti durumunu (`GET
/api/uploads/{id}`, 01.6.1) HTMX'in iki saniyede bir yenilediği parçaya çevirir; parti son
duruma (`done`, `partial`, `failed`) varınca parça yenileme öznitelikleri olmadan gelir ve
yenileme durur.

Yapay zekâ sağlayıcısı kurulamıyorsa (`AI_PROVIDER` eksik anahtar) parti yine de alınır — dosya
Inbox'ta güvende kalır — ama işlenmez; kullanıcıya bu söylenir ve yenileme başlatılmaz.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.ai.provider import ProviderConfigError, create_provider
from app.config import Settings, get_settings
from app.db.models import Employee, Upload, UploadStatus
from app.db.session import get_session, get_session_factory
from app.pipeline.orchestrate import UploadTransitionError, process_upload
from app.storage import DataLayout
from app.web.auth import PanelUser, require_panel_user
from app.web.routers.uploads import (
    UploadFileStatusResponse,
    create_upload,
    get_layout,
    get_upload_status,
)
from app.web.templating import MENU_BY_KEY, render_page

router = APIRouter(tags=["upload-page"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]

# Yenileme aralığı `upload_result.html`'dedir (`hx-trigger="every 2s"`).
PIPELINE_STAGES: tuple[tuple[UploadStatus, str], ...] = (
    (UploadStatus.RECEIVED, "Alındı"),
    (UploadStatus.RENDERING, "Sayfalar hazırlanıyor"),
    (UploadStatus.ANALYZING, "Analiz ediliyor"),
    (UploadStatus.PLANNING, "Plan hazırlanıyor"),
    (UploadStatus.EXECUTING, "Plan uygulanıyor"),
)
STATUS_LABELS: dict[UploadStatus, str] = {
    **dict(PIPELINE_STAGES),
    UploadStatus.DONE: "Tamamlandı",
    UploadStatus.PARTIAL: "Kısmen tamamlandı — bazı sayfalar analiz edilemedi",
    UploadStatus.FAILED: "İşlenemedi",
}
FINAL_STATUSES = frozenset({UploadStatus.DONE, UploadStatus.PARTIAL, UploadStatus.FAILED})

NO_FILE_MESSAGE = "Yüklenecek dosya seçilmedi."
UNPROCESSED_NOTICE = (
    "Yapay zekâ sağlayıcısı kurulamadığı için parti işlenmiyor; dosyalar alındı ve "
    "'Alındı' durumunda bekliyor. {reason}"
)

UploadProcessor = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class Step:
    label: str
    state: str  # "done" | "current" | "todo"


@dataclass(frozen=True, slots=True)
class ProgressView:
    upload_id: str
    status: str
    label: str
    final: bool
    steps: list[Step]
    files: list[UploadFileStatusResponse]
    rendered_files: int
    total_files: int


def build_progress_view(session: Session, upload_id: str) -> ProgressView:
    """01.6.1 yanıtını (`get_upload_status`) sayfanın gösterdiği biçime çevirir; parti yoksa 404."""
    report = get_upload_status(upload_id, session)
    current = UploadStatus(report.status)
    final = current in FINAL_STATUSES
    steps: list[Step] = []
    reached = False
    for stage, label in PIPELINE_STAGES:
        if final:
            state = "todo" if current is UploadStatus.FAILED else "done"
        elif stage is current:
            state, reached = "current", True
        else:
            state = "todo" if reached else "done"
        steps.append(Step(label, state))
    return ProgressView(
        upload_id=report.upload_id,
        status=current.value,
        label=STATUS_LABELS[current],
        final=final,
        steps=steps,
        files=report.files,
        rendered_files=report.progress.rendered_files,
        # Tekrar dosyası (01.4.1) hiç işlenmez; sayaç işlenecek dosyaları sayar.
        total_files=sum(1 for file in report.files if not file.is_duplicate),
    )


def get_upload_processor(
    settings: Annotated[Settings, Depends(get_settings)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> UploadProcessor | ProviderConfigError:
    """Partiyi arka planda işleyen adım; sağlayıcı kurulamazsa nedenini taşıyan hata döner.

    İşleyici isteğin oturumunu kullanmaz: yanıt gittikten sonra çalışır, kendi oturumunu açar.
    `process_upload` beklenmeyen hatayı partiyi `failed` yaparak kaydeder (09.2.3); yalnızca
    partiyi başka bir işleyicinin almış olması sessizce geçilir.
    """
    try:
        provider = create_provider(settings)
    except ProviderConfigError as exc:
        return exc

    def process(upload_id: str) -> None:
        with session_factory() as session:
            upload = session.get(Upload, upload_id)
            if upload is None:
                return
            try:
                process_upload(session, layout, upload, settings=settings, provider=provider)
            except UploadTransitionError:
                return

    return process


Processor = Annotated[UploadProcessor | ProviderConfigError, Depends(get_upload_processor)]


def _employee_options(session: Session) -> list[Employee]:
    return list(session.scalars(select(Employee).order_by(Employee.folder_name)))


def _result(request: Request, status_code: int = 200, **context: object) -> HTMLResponse:
    """`upload_result.html` parçasını çizer (HTMX hedefi: sayfadaki `#upload-result`)."""
    return render_page(request, "upload_result.html", user=None, status_code=status_code, **context)


@router.get("/upload", response_class=HTMLResponse)
def upload_page(
    request: Request, user: CurrentUser, session: Annotated[Session, Depends(get_session)]
) -> HTMLResponse:
    return render_page(
        request,
        "upload.html",
        user=user,
        active=MENU_BY_KEY["upload"].key,
        entry=MENU_BY_KEY["upload"],
        employees=_employee_options(session),
    )


@router.post("/upload", response_class=HTMLResponse)
async def submit_upload(
    request: Request,
    _user: CurrentUser,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    settings: Annotated[Settings, Depends(get_settings)],
    processor: Processor,
) -> HTMLResponse:
    # Form elle okunur: tarayıcı dosya seçilmemişken adı boş tek bir parça gönderir ve Starlette
    # onu dosya değil düz alan sayar; bildirimli `list[UploadFile]` bunu 422 ile reddederdi.
    async with request.form() as form:
        chosen = [
            file
            for file in form.getlist("files")
            if isinstance(file, StarletteUploadFile) and file.filename
        ]
        if not chosen:
            return _result(request, status.HTTP_400_BAD_REQUEST, error=NO_FILE_MESSAGE)
        employee_id = form.get("context_employee_id")
        try:
            created = await create_upload(
                files=chosen,
                session=session,
                layout=layout,
                settings=settings,
                # Seçim yapılmamışsa form boş dize gönderir: bağlam çalışanı yok demektir.
                context_employee_id=(employee_id or None) if isinstance(employee_id, str) else None,
            )
        except HTTPException as exc:
            return _result(request, exc.status_code, error=str(exc.detail))

    notice = None
    if isinstance(processor, ProviderConfigError):
        notice = UNPROCESSED_NOTICE.format(reason=processor)
    else:
        background_tasks.add_task(processor, created.upload_id)
    view = build_progress_view(session, created.upload_id)
    # Okuma işlemi de SQLite'ta yazma kilidini tutar (`app.db.session`): arka plan işleyicisi
    # bu oturum kapanana kadar beklemesin.
    session.rollback()
    return _result(
        request,
        status.HTTP_201_CREATED,
        progress=view,
        poll=notice is None and not view.final,
        notice=notice,
    )


@router.get("/upload/{upload_id}/progress", response_class=HTMLResponse)
def upload_progress(
    upload_id: str,
    request: Request,
    _user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    try:
        view = build_progress_view(session, upload_id)
    except HTTPException as exc:
        return _result(request, exc.status_code, error=str(exc.detail))
    return _result(request, progress=view, poll=not view.final)
