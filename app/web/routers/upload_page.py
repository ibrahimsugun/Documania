"""Yükleme sayfası, canlı ilerleme görünümü ve yükleme detayı (PRD 10.2.1, 10.2.2, 10.3.1, 10.3.2).

`GET /upload` sürükle-bırak çoklu yükleme formunu ve isteğe bağlı çalışan seçimini çizer.
`POST /upload` (HTMX) dosyaları `POST /api/uploads` ile aynı işlevle (`create_upload`) partiye
çevirir — boyut/sayfa sınırı (01.3.1), Inbox'a değişmez yazma (K10) ve tekrar tespiti (01.4.1)
orada kalır, burada kopyalanmaz. Parti oluşunca kuyruktaki işi (13.3.1) arka planda alınıp
işlenir (09.2.2; iş bu arada panelin kuyruk döngüsüne geçtiyse o işler) ve yanıt ilerleme
görünümüdür. `GET /upload/{upload_id}/progress` parti durumunu (`GET
/api/uploads/{id}`, 01.6.1) HTMX'in iki saniyede bir yenilediği parçaya çevirir; parti son
duruma (`done`, `partial`, `failed`) varınca parça yenileme öznitelikleri olmadan gelir ve
yenileme durur.

Yapay zekâ sağlayıcısı kurulamıyorsa (`AI_PROVIDER` eksik anahtar) parti yine de alınır — dosya
Inbox'ta güvende kalır, işi kuyrukta bekler — ama işlenmez; kullanıcıya bu söylenir ve yenileme
başlatılmaz.

`GET /uploads/{upload_id}` yükleme detay sayfasıdır (10.3.1): partinin sayfa küçük resimleri, güncel
planın öğeleri, çıktıları (belgeler ve kuyruğa alınanlar) ve olay zaman çizelgesi tek sayfada
görünür. Sayfa görüntüsü `GET /uploads/{upload_id}/pages/{page_id}/image`'dan gelir: analiz
kopyasıdır (`cache/pages/`), belgenin kendisi değil; küçültmeyi tarayıcı yapar, sunucu görüntüyü
işlemez (K11, K17).

`POST /uploads/{upload_id}/rerun` güncel planı yapay zekâ çağırmadan yeniden uygular (06.6.1);
`POST /uploads/{upload_id}/reanalyze` partiyi yeniden analiz edip yeni plan sürümünü açar (06.6.2,
K18). Yeniden analiz iki aşamalı onay ister (10.3.2): istemci birinci onaydan sonra
`POST .../reanalyze/prepare` ile onay belirteci alır, ikinci onaydan sonra asıl isteği bu belirteçle
gönderir; belirteçsiz, süresi geçmiş, kullanılmış ya da başka işleme ait belirteçle gelen istek 400
ile reddedilir ve hiçbir şey yapılmaz. Belirteç 10.8.1'in tek kullanımlık belirtecidir
(`app.web.confirm`); partiye ve güncel planına bağlıdır. İşlemlerin ikisi de yalnız son
durumdaki (`done`, `partial`, `failed`) ve planı olan partide yapılır: süren partinin üzerine
yazılmaz.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.ai.provider import AnalysisProvider, ProviderConfigError, create_provider
from app.catalog import export_catalog
from app.config import Settings, get_settings
from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    Event,
    Page,
    Plan,
    Upload,
    UploadFile,
    UploadStatus,
)
from app.db.session import get_session, get_session_factory
from app.pipeline.analyze import PageAnalysisStatus
from app.pipeline.orchestrate import (
    PLAN_EXECUTION_ERRORS,
    NoPlanError,
    PlanExecutor,
    current_plan,
    reanalyze_upload,
    rerun_plan,
)
from app.pipeline.plan import PlanDocument, PlanEmployee, PlanIntegrityError, Route, read_plan
from app.storage import DataLayout
from app.web.auth import PanelUser, require_panel_user
from app.web.confirm import (
    CONFIRMATION_REFUSED,
    ConfirmationRefusedError,
    Operation,
    confirm_operation,
    issue_confirmation,
)
from app.web.routers.uploads import (
    UploadFileStatusResponse,
    create_upload,
    get_layout,
    get_plan_executor,
    get_upload_status,
)
from app.web.templating import MENU_BY_KEY, render_page
from app.worker import claim_and_run

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
    Partinin kuyrukta bekleyen işini alır ve işler (13.3.1, `claim_and_run`); beklenmeyen hata
    partiyi `failed` yapar (09.2.3). İş beklemiyorsa — başka bir işleyici almış, parti işlenmiş ya
    da yok — sessizce geçilir.
    """
    try:
        provider = create_provider(settings)
    except ProviderConfigError as exc:
        return exc

    def process(upload_id: str) -> None:
        claim_and_run(session_factory, layout, upload_id, settings=settings, provider=provider)

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


# --- 10.3: yükleme detay sayfası ---------------------------------------------------------------

ROUTE_LABELS: dict[str, str] = {
    Route.READY.value: "Hazır",
    Route.UNKNOWN.value: "Unknown kuyruğu",
    Route.UNREADABLE.value: "Unreadable kuyruğu",
    Route.UNRESOLVED.value: "Unresolved kuyruğu",
    Route.SKIP.value: "Atlandı",
}
QUEUE_LABELS = {"unknown": "Unknown", "unreadable": "Unreadable", "unresolved": "Unresolved"}
EMPLOYEE_ACTION_LABELS = {
    "match": "Eşleşti",
    "create": "Yeni çalışan",
    "pending": "Onay bekleyen profil",
    "none": "Çalışan yok",
}
MATCHED_BY_LABELS = {"document_number": "belge numarası", "name_dob": "ad-soyad + doğum tarihi"}
DOCUMENT_STATUS_LABELS = {
    DocumentStatus.ACTIVE.value: "Etkin",
    DocumentStatus.SUPERSEDED.value: "Eski sürüm",
    DocumentStatus.ARCHIVED.value: "Arşivlendi",
}
PAGE_STATUS_LABELS = {
    PageAnalysisStatus.PENDING.value: "Bekliyor",
    PageAnalysisStatus.DONE.value: "Analiz edildi",
    PageAnalysisStatus.SKIPPED.value: "Atlandı",
    PageAnalysisStatus.FAILED.value: "Analiz edilemedi",
}

# Onay metinleri (10.3.2). §20.6 tablosu yalnız K16'nın beş manuel işlemini kapsar; yeniden analiz
# onları bu kalıpla tamamlar: birinci cümle ne yapılacağını, ikinci geri dönüşü olmayan sonucu
# söyler (PLAN.md §D23).
REANALYZE_FIRST_CONFIRMATION = "Bu partiyi yeniden analiz etmek üzeresiniz. Emin misiniz?"
REANALYZE_SECOND_CONFIRMATION = (
    "Bu işlem partiye yeni bir plan sürümü açacak; önceki sürümün çıktıları "
    '"eski sürüm" olarak işaretlenecektir. Son kararınız mı?'
)

UPLOAD_NOT_FOUND = "Parti bulunamadı."
PAGE_IMAGE_NOT_FOUND = "Sayfa görüntüsü bulunamadı."
BUSY_MESSAGE = "Parti hâlâ işleniyor; işlem bittikten sonra yeniden çalıştırılabilir."
NO_PLAN_MESSAGE = (
    "Partinin planı yok; yeniden çalıştırılacak ya da yeniden analiz edilecek bir sürüm bulunmuyor."
)


class ReanalysisProviderError(RuntimeError):
    """Yeniden analiz için yapay zekâ sağlayıcısı kurulamadı."""


@dataclass(frozen=True, slots=True)
class PageView:
    id: int
    number: int  # 1 tabanlı; `pages.index` 0 tabanlıdır
    status_label: str
    is_blank: bool
    has_image: bool
    item_id: str | None


@dataclass(frozen=True, slots=True)
class FileView:
    id: int
    name: str
    page_count: int | None
    is_duplicate: bool
    pages: list[PageView]


@dataclass(frozen=True, slots=True)
class ItemView:
    item_id: str
    type_slug: str | None
    sources: list[str]
    operation: str | None
    target_name: str | None
    employee: str
    route: str
    route_label: str
    reason: str | None
    validations: list[tuple[str, bool]]


@dataclass(frozen=True, slots=True)
class PlanView:
    version: int
    model: str | None
    plan_hash: str
    created_at: str
    executed_at: str | None
    items: list[ItemView]
    older_versions: int
    error: str | None


@dataclass(frozen=True, slots=True)
class OutputView:
    id: int
    employee: str
    type_slug: str
    path: str
    format: str
    sequence_no: int
    status: str
    status_label: str
    plan_version: int | None
    sources: list[str]


@dataclass(frozen=True, slots=True)
class QueueView:
    id: int
    kind_label: str
    plan_version: int | None
    item_id: str | None
    reason: str
    resolved: str | None
    current: bool


@dataclass(frozen=True, slots=True)
class EventView:
    ts: str
    ts_iso: str
    type: str
    actor: str
    place: str | None
    message: str | None


@dataclass(frozen=True, slots=True)
class DetailView:
    upload_id: str
    status: str
    label: str
    final: bool
    channel: str
    created_at: str
    context_employee: str | None
    files: list[FileView]
    plan: PlanView | None
    outputs: list[OutputView]
    queue: list[QueueView]
    events: list[EventView]
    blocked_reason: str | None


def _format_ts(moment: datetime) -> str:
    return f"{moment:%Y-%m-%d %H:%M:%S} UTC"


def _page_ranges(pages: tuple[int, ...] | list[int]) -> str:
    """0 tabanlı sayfa sıralarını insanın okuyacağı 1 tabanlı aralığa çevirir: `[0, 1, 2, 4]` →
    `s. 1–3, 5`; sayfa listesi boşsa dosya bütün olarak alınmıştır."""
    if not pages:
        return "tüm dosya"
    runs: list[list[int]] = []
    for page in sorted(pages):
        if runs and page == runs[-1][-1] + 1:
            runs[-1].append(page)
        else:
            runs.append([page])
    parts = [f"{run[0] + 1}" if len(run) == 1 else f"{run[0] + 1}–{run[-1] + 1}" for run in runs]
    return "s. " + ", ".join(parts)


def _source_text(files: dict[int, UploadFile], file_id: int, pages: list[int]) -> str:
    upload_file = files.get(file_id)
    name = upload_file.original_name if upload_file is not None else f"dosya {file_id}"
    return f"{name} · {_page_ranges(pages)}"


def _employee_label(employees: dict[str, Employee], employee_id: str) -> str:
    employee = employees.get(employee_id)
    if employee is None:
        return employee_id
    return f"{employee_id} — {employee.given_names} {employee.surname}"


def _plan_employee_text(employee: PlanEmployee, employees: dict[str, Employee]) -> str:
    text = EMPLOYEE_ACTION_LABELS[employee.action.value]
    if employee.employee_id is not None:
        text += f" · {_employee_label(employees, employee.employee_id)}"
    if employee.matched_by is not None:
        text += f" ({MATCHED_BY_LABELS[employee.matched_by.value]})"
    return text


def _plan_view(
    plan: Plan,
    upload: Upload,
    files: dict[int, UploadFile],
    employees: dict[str, Employee],
    document: PlanDocument | None,
    error: str | None,
) -> PlanView:
    items = [
        ItemView(
            item_id=item.item_id,
            type_slug=item.document_type_slug,
            sources=[
                _source_text(files, source.file_id, list(source.pages)) for source in item.sources
            ],
            operation=item.operation.value if item.operation is not None else None,
            target_name=item.target_name,
            employee=_plan_employee_text(item.employee, employees),
            route=item.route.value,
            route_label=ROUTE_LABELS[item.route.value],
            reason=item.route_reason,
            validations=[(check.name.value, check.ok) for check in item.validations],
        )
        for item in (document.items if document is not None else ())
    ]
    return PlanView(
        version=plan.version,
        model=plan.model,
        plan_hash=plan.plan_hash,
        created_at=_format_ts(plan.created_at),
        executed_at=_format_ts(plan.executed_at) if plan.executed_at is not None else None,
        items=items,
        older_versions=sum(1 for other in upload.plans if other.version < plan.version),
        error=error,
    )


def _page_items(document: PlanDocument | None) -> dict[tuple[int, int], str]:
    """`(file_id, sayfa sırası)` → sayfayı alan plan öğesinin kimliği."""
    owners: dict[tuple[int, int], str] = {}
    for item in document.items if document is not None else ():
        for source in item.sources:
            for index in source.pages:
                owners[(source.file_id, index)] = item.item_id
    return owners


def _event_place(event: Event, files: dict[int, UploadFile]) -> str | None:
    if event.file_id is None:
        return None
    upload_file = files.get(event.file_id)
    name = upload_file.original_name if upload_file is not None else f"dosya {event.file_id}"
    if event.page_index is None:
        return name
    return f"{name} · s. {event.page_index + 1}"


def _page_view(page: Page, item_id: str | None) -> PageView:
    return PageView(
        id=page.id,
        number=page.index + 1,
        status_label=PAGE_STATUS_LABELS.get(page.analysis_status, page.analysis_status),
        is_blank=page.is_blank,
        has_image=page.image_path is not None,
        item_id=item_id,
    )


def build_detail_view(session: Session, upload: Upload) -> DetailView:
    """Partinin sayfalarını, güncel planını, çıktılarını ve olaylarını tek görünüme toplar.

    Saklanan plan doğrulanamıyorsa (`PlanIntegrityError`) sayfa yine açılır: öğeler yerine nedeni
    gösterilir — uygulayıcı da bu planı yürütmez (K9).
    """
    files = {upload_file.id: upload_file for upload_file in upload.files}
    plan = current_plan(session, upload)
    document: PlanDocument | None = None
    plan_error: str | None = None
    if plan is not None:
        try:
            document = read_plan(plan)
        except PlanIntegrityError as exc:
            plan_error = str(exc)
    plan_versions = {row.id: row.version for row in upload.plans}
    outputs = list(
        session.scalars(
            select(Document).where(Document.plan_id.in_(list(plan_versions))).order_by(Document.id)
        )
    )
    events = list(
        session.scalars(
            select(Event)
            .where(
                or_(
                    Event.upload_id == upload.id,
                    Event.document_id.in_([output.id for output in outputs]),
                )
            )
            .order_by(Event.ts, Event.id)
        )
    )

    employee_ids = {output.employee_id for output in outputs}
    if upload.context_employee_id is not None:
        employee_ids.add(upload.context_employee_id)
    if document is not None:
        employee_ids.update(
            item.employee.employee_id
            for item in document.items
            if item.employee.employee_id is not None
        )
    employees = {
        employee.id: employee
        for employee in session.scalars(select(Employee).where(Employee.id.in_(employee_ids)))
    }

    owners = _page_items(document)
    current_status = UploadStatus(upload.status)
    blocked_reason = None
    if current_status not in FINAL_STATUSES:
        blocked_reason = BUSY_MESSAGE
    elif plan is None:
        blocked_reason = NO_PLAN_MESSAGE
    return DetailView(
        upload_id=upload.id,
        status=current_status.value,
        label=STATUS_LABELS[current_status],
        final=current_status in FINAL_STATUSES,
        channel=upload.channel,
        created_at=_format_ts(upload.created_at),
        context_employee=(
            _employee_label(employees, upload.context_employee_id)
            if upload.context_employee_id is not None
            else None
        ),
        files=[
            FileView(
                id=upload_file.id,
                name=upload_file.original_name,
                page_count=upload_file.page_count,
                is_duplicate=upload_file.is_duplicate_of is not None,
                pages=[
                    _page_view(page, owners.get((upload_file.id, page.index)))
                    for page in upload_file.pages
                ],
            )
            for upload_file in upload.files
        ],
        plan=(
            _plan_view(plan, upload, files, employees, document, plan_error)
            if plan is not None
            else None
        ),
        outputs=[
            OutputView(
                id=output.id,
                employee=_employee_label(employees, output.employee_id),
                type_slug=output.type_slug,
                path=output.path,
                format=output.format,
                sequence_no=output.sequence_no,
                status=output.status,
                status_label=DOCUMENT_STATUS_LABELS.get(output.status, output.status),
                plan_version=plan_versions.get(output.plan_id) if output.plan_id else None,
                sources=[
                    _source_text(files, int(ref["file_id"]), list(ref.get("pages", [])))
                    for ref in output.source_refs_json
                ],
            )
            for output in outputs
        ],
        queue=[
            QueueView(
                id=row.id,
                kind_label=QUEUE_LABELS.get(row.kind, row.kind),
                plan_version=plan_versions.get(row.plan_id) if row.plan_id else None,
                item_id=row.plan_item_id,
                reason=row.reason,
                resolved=(
                    f"{_format_ts(row.resolved_at)} · {row.resolved_by}"
                    if row.resolved_at is not None
                    else None
                ),
                current=plan is not None and row.plan_id == plan.id,
            )
            for row in upload.queue_items
        ],
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
        blocked_reason=blocked_reason,
    )


# --- 10.3.2: iki aşamalı onay belirteci --------------------------------------------------------


def reanalysis_subject(upload_id: str, plan_id: int) -> str:
    """Yeniden analiz belirtecinin bağlı olduğu hedef: parti + güncel plan (10.8.1 belirteci,
    işlem `Operation.REANALYZE`). Plan değişmişse belirteç geçmez."""
    return f"{upload_id}:{plan_id}"


def get_reanalysis_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalysisProvider | ProviderConfigError:
    """Yeniden analizin sağlayıcısı; kurulamazsa nedenini taşıyan hata (kullanıcıya gösterilir)."""
    try:
        return create_provider(settings)
    except ProviderConfigError as exc:
        return exc


ReanalysisProvider = Annotated[
    AnalysisProvider | ProviderConfigError, Depends(get_reanalysis_provider)
]


# --- 10.3: uç noktalar -------------------------------------------------------------------------


def _action_result(request: Request, status_code: int, **context: object) -> HTMLResponse:
    """`upload_action_result.html` parçası (HTMX hedefi: sayfadaki `#action-result`)."""
    return render_page(
        request, "upload_action_result.html", user=None, status_code=status_code, **context
    )


@router.get("/uploads/{upload_id}", response_class=HTMLResponse)
def upload_detail(
    upload_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    upload = session.get(Upload, upload_id)
    entry = MENU_BY_KEY["uploads"]
    if upload is None:
        return render_page(
            request,
            "upload_detail.html",
            user=user,
            active=entry.key,
            status_code=status.HTTP_404_NOT_FOUND,
            error=UPLOAD_NOT_FOUND,
        )
    view = build_detail_view(session, upload)
    # Okuma işlemi de SQLite'ta yazma kilidini tutar (`app.db.session`): sayfa çizilirken
    # arka plandaki bir işleyici beklemesin.
    session.rollback()
    return render_page(
        request,
        "upload_detail.html",
        user=user,
        active=entry.key,
        detail=view,
        first_confirmation=REANALYZE_FIRST_CONFIRMATION,
    )


@router.get("/uploads/{upload_id}/pages/{page_id}/image")
def upload_page_image(
    upload_id: str,
    page_id: int,
    layout: Annotated[DataLayout, Depends(get_layout)],
    session: Annotated[Session, Depends(get_session)],
) -> FileResponse:
    """Sayfanın analiz görüntüsü (K10: orijinal değil, `cache/pages/` kopyası). Sayfa bu partiye
    ait değilse ya da görüntüsü yoksa 404."""
    page = session.get(Page, page_id)
    image_path = page.image_path if page is not None and page.file.upload_id == upload_id else None
    session.rollback()
    if image_path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, PAGE_IMAGE_NOT_FOUND)
    try:
        path = layout.resolve(image_path)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, PAGE_IMAGE_NOT_FOUND) from None
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, PAGE_IMAGE_NOT_FOUND)
    return FileResponse(path, headers={"X-Content-Type-Options": "nosniff"})


def _actionable_upload(session: Session, upload_id: str) -> tuple[Upload, Plan]:
    """İşlem yapılabilecek partiyi ve güncel planını döner; yoksa `HTTPException`."""
    upload = session.get(Upload, upload_id)
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, UPLOAD_NOT_FOUND)
    if UploadStatus(upload.status) not in FINAL_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, BUSY_MESSAGE)
    plan = current_plan(session, upload)
    if plan is None:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_PLAN_MESSAGE)
    return upload, plan


@router.post("/uploads/{upload_id}/rerun", response_class=HTMLResponse)
def rerun_upload(
    upload_id: str,
    request: Request,
    _user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    executor: Annotated[PlanExecutor, Depends(get_plan_executor)],
) -> HTMLResponse:
    """10.3.2 — güncel planı yapay zekâ çağırmadan yeniden uygular (06.6.1)."""
    try:
        upload, _plan = _actionable_upload(session, upload_id)
        run = rerun_plan(session, layout, upload, executor=executor)
    except HTTPException as exc:
        session.rollback()
        return _action_result(request, exc.status_code, error=str(exc.detail))
    except (NoPlanError, PlanIntegrityError, *PLAN_EXECUTION_ERRORS) as exc:
        session.rollback()
        return _action_result(request, status.HTTP_409_CONFLICT, error=str(exc))
    session.commit()
    return _action_result(
        request, status.HTTP_200_OK, upload_id=upload_id, done="rerun", version=run.plan.version
    )


@router.post("/uploads/{upload_id}/reanalyze/prepare", response_class=HTMLResponse)
def prepare_reanalysis(
    upload_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """10.3.2 — birinci onaydan sonra ikinci onay formunu ve tek kullanımlık onay belirtecini
    verir (§20.6.1)."""
    try:
        _upload, plan = _actionable_upload(session, upload_id)
        issued = issue_confirmation(
            session, request, user, Operation.REANALYZE, reanalysis_subject(upload_id, plan.id)
        )
    except HTTPException as exc:
        session.rollback()
        return _action_result(request, exc.status_code, error=str(exc.detail))
    except ConfirmationRefusedError as exc:
        session.rollback()
        return _action_result(request, status.HTTP_400_BAD_REQUEST, error=str(exc))
    session.commit()
    return _action_result(
        request,
        status.HTTP_200_OK,
        upload_id=upload_id,
        second_confirmation=REANALYZE_SECOND_CONFIRMATION,
        confirmation=issued.token,
    )


@router.post("/uploads/{upload_id}/reanalyze", response_class=HTMLResponse)
def reanalyze_upload_page(
    upload_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    executor: Annotated[PlanExecutor, Depends(get_plan_executor)],
    provider: ReanalysisProvider,
    confirmation: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    """10.3.2 — partiyi yeniden analiz eder, yeni plan sürümünü açar (06.6.2, K18).

    İkinci onayın belirteci olmadan hiçbir şey yapılmaz (400). Belirteç tek kullanımlıktır ve
    partinin güncel planına bağlıdır: aynı belirteç ikinci kez geçmez.
    """
    try:
        upload, plan = _actionable_upload(session, upload_id)
        # §20.6.1: belirteç tüketilir ve `USER_CONFIRMED` (kullanıcı adı, işlem, hedef, iki onayın
        # zamanı) yazılır, ardından işlemin kendi olayı (`PLAN_REANALYZED`) düşer.
        confirm_operation(
            session,
            request,
            user,
            Operation.REANALYZE,
            reanalysis_subject(upload_id, plan.id),
            confirmation,
            event_target={"upload_id": upload.id, "plan_id": plan.id},
            upload_id=upload.id,
        )
        if isinstance(provider, ProviderConfigError):
            raise ReanalysisProviderError(str(provider))
        reanalysis = reanalyze_upload(
            session,
            layout,
            upload,
            provider=provider,
            catalog=export_catalog(session),
            executor=executor,
        )
    except HTTPException as exc:
        session.rollback()
        return _action_result(request, exc.status_code, error=str(exc.detail))
    except ConfirmationRefusedError:
        session.rollback()
        return _action_result(request, status.HTTP_400_BAD_REQUEST, error=CONFIRMATION_REFUSED)
    except ReanalysisProviderError as exc:
        session.rollback()
        return _action_result(request, status.HTTP_503_SERVICE_UNAVAILABLE, error=str(exc))
    except (NoPlanError, *PLAN_EXECUTION_ERRORS) as exc:
        session.rollback()
        return _action_result(request, status.HTTP_409_CONFLICT, error=str(exc))
    session.commit()
    return _action_result(
        request,
        status.HTTP_200_OK,
        upload_id=upload_id,
        done="reanalyze",
        version=reanalysis.plan.version,
        previous_version=reanalysis.previous_plan.version,
        superseded=len(reanalysis.superseded_document_ids),
    )
