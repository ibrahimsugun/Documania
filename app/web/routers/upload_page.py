"""Yükleme sayfası, canlı ilerleme görünümü ve yükleme detayı (PRD 10.2.1, 10.2.2, 10.3.1, 10.3.2,
10.3.4, 10.3.5, 10.3.6, 10.3.7, 10.5.5, 05.5.4).

`GET /upload` sürükle-bırak çoklu yükleme formunu ve isteğe bağlı çalışan seçimini çizer.
`POST /upload` (HTMX) dosyaları `POST /api/uploads` ile aynı işlevle (`create_upload`) partiye
çevirir — boyut/sayfa sınırı (01.3.1), Inbox'a değişmez yazma (K10) ve tekrar tespiti (01.4.1)
orada kalır, burada kopyalanmaz. Parti ve kuyruğa işi tek işlemde eklenir; HTTP uygulaması işi
almaz. Ayrı `worker` servisi kuyruğu tüketir. Yanıt ilerleme görünümüdür; worker bitirene kadar
HTMX iki saniyede bir yeniler.

Yapay zekâ sağlayıcısı HTTP uygulamasında kurulmaz: API yalnızca dosyayı güvenle alıp kuyruğa yazar.
Worker ayarları eksikse iş kuyrukta kalır; servis hatası worker loglarında görünür.


`GET /uploads/{upload_id}` yükleme detay sayfasıdır (10.3.1): partinin sayfa küçük resimleri, güncel
planın öğeleri, çıktıları (belgeler ve kuyruğa alınanlar) ve olay zaman çizelgesi tek sayfada
görünür. Sayfa görüntüsü `GET /uploads/{upload_id}/pages/{page_id}/image`'dan gelir: analiz
kopyasıdır (`cache/pages/`), belgenin kendisi değil; küçültmeyi tarayıcı yapar, sunucu görüntüyü
işlemez (K11, K17). Planın yalnız isimle eşleştirdiği öğe (§20.2.2 satır 5a, `matched_by: name`)
ve o öğenin çıktısı (`name_matched_documents`) "Yalnız isimle eşleşti" etiketi taşır (05.5.4):
yanlışsa İK belgeyi başka çalışana taşır (10.8.1).

`POST /uploads/{upload_id}/rerun` güncel planı yapay zekâ çağırmadan yeniden uygular (06.6.1);
`POST /uploads/{upload_id}/reanalyze` partiyi yeniden analiz edip yeni plan sürümünü açar (06.6.2,
K18). Yeniden analiz iki aşamalı onay ister (10.3.2): istemci birinci onaydan sonra
`POST .../reanalyze/prepare` ile onay belirteci alır, ikinci onaydan sonra asıl isteği bu belirteçle
gönderir; belirteçsiz, süresi geçmiş, kullanılmış ya da başka işleme ait belirteçle gelen istek 400
ile reddedilir ve hiçbir şey yapılmaz. Belirteç 10.8.1'in tek kullanımlık belirtecidir
(`app.web.confirm`); partiye ve güncel planına bağlıdır. İşlemlerin ikisi de yalnız son
durumdaki (`done`, `partial`, `failed`), planı olan ve yoksayılmamış partide yapılır: süren partinin
üzerine yazılmaz.

**Taramayı yoksay (10.3.4; K16, §20.6).** Son durumdaki, yoksayılmamış partide — planı olmasa da —
üçüncü düğmedir. Birinci onaydan sonra `POST .../dismiss/prepare` §20.6'nın ikinci metnini
(kapanacak <N> kuyruk öğesi, yerinde kalacak <M> etkin belge) ve partiye + güncel planına bağlı tek
kullanımlık belirteci verir; `POST .../dismiss` belirteçle gelir: belirtecin tüketilmesi,
`USER_CONFIRMED`, yoksayma ve `UPLOAD_DISMISSED` tek işlemdedir (`app.pipeline.dismiss`). Belirteç
önce denetlenir: belirteçsiz, kullanılmış, süresi geçmiş ya da başka partiye ait istek 400;
partinin durumu buna uymuyorsa (yoksayılmış, süren) 409 ve belirteç tüketilmez. Yoksayılan
partinin detay sayfası adresle açılır, üstte kimin ne zaman yoksaydığını söyler ve işlem düğmesi
göstermez; yeniden çalıştırma ve yeniden analiz de 409'dur — yoksayılan partinin kuyruk öğeleri geri
gelmesin.

**Yoksaymayı geri alma (10.3.5; §D61).** Yoksayılan partinin bildiriminin yanında "Yoksaymayı geri
al" düğmesi durur: `POST .../undismiss` tek adımdır (salt durum çevirir) ve kullanıcı adıyla
`UPLOAD_RESTORED` yazar (`app.pipeline.dismiss.restore_upload`). Parti listeye döner; yalnız
yoksaymayla kapanan kuyruk öğeleri yeniden açılır, arada başka yolla (atama, onay, kapatma) çözülmüş
öğe açılmaz. Yoksayılmamış partide 409.

**Süren partiyi iptal et (10.3.6; K16, §20.6; PLAN.md §D114).** Süren (`received` … `executing`)
partinin İşlemler bölümünde "Partiyi iptal et" vardır; yeniden çalıştırma ve yeniden analiz o sırada
kapalıdır. Birinci onaydan sonra `POST .../cancel/prepare` §20.6'nın ikinci metnini ve partiye bağlı
tek kullanımlık belirteci verir; `POST .../cancel` belirteçle gelir: belirtecin tüketilmesi,
`USER_CONFIRMED`, iptal ve `UPLOAD_CANCELLED` tek işlemdedir (`app.pipeline.cancel`). Belirteçsiz ya
da geçersiz istek 400; parti bu arada son duruma vardıysa 409 ve belirteç tüketilmez. İptal edilen
partinin detayında kimin ne zaman iptal ettiği (ya da 10 dakikada tamamlanamadığı için otomatik
iptal edildiği) yazar. İptal edilen parti yeniden çalıştırılmaz ve yeniden analiz edilmez (409,
planı olsa da): iptal partiyi yeniden başlatmanın yolu değildir, dosyalar yeniden yüklenir —
tekrar sayılmaz (§D114 g). Yoksayılabilir (10.3.4).

**Otomatik iptal (10.3.7).** Yükleme listesi ve parti detayı tam sayfa olarak açılırken alındığından
beri `UPLOAD_TIMEOUT_SECONDS` (600) geçmiş bitmemiş partiler iptal edilir ve commit edilir
(`expire_stale_uploads`): işleyici kapalıyken de takılan parti böyle yakalanır. Bu iki `GET` bilerek
yazar; HTMX ilerleme parçası yazmaz. Saat `get_clock` bağımlılığıdır (testte enjekte edilir).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.ai.provider import AnalysisProvider, ProviderConfigError, create_provider
from app.catalog import export_catalog
from app.config import Settings, get_settings
from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeStatus,
    Event,
    Page,
    Plan,
    QueueItem,
    QueueResolution,
    Upload,
    UploadFile,
    UploadStatus,
    utcnow,
)
from app.db.session import get_session
from app.i18n import N_, Translatable
from app.matching.match import MatchedBy
from app.pipeline.analyze import PageAnalysisStatus
from app.pipeline.cancel import (
    CancelReason,
    UploadNotCancellableError,
    cancel_stale_uploads,
    cancel_upload,
    is_cancellable,
    last_cancellation,
)
from app.pipeline.dismiss import (
    UploadNotDismissableError,
    UploadNotRestorableError,
    dismiss_upload,
    is_dismissed,
    preview_dismissal,
    restore_upload,
)
from app.pipeline.orchestrate import (
    PLAN_EXECUTION_ERRORS,
    NoPlanError,
    PlanExecutor,
    current_plan,
    reanalyze_upload,
    rerun_plan,
)
from app.pipeline.plan import (
    PlanDocument,
    PlanEmployee,
    PlanIntegrityError,
    Route,
    name_matched_documents,
    read_plan,
)
from app.pipeline.queue_close import close_reason_label
from app.storage import DataLayout
from app.web.auth import WRITER_ONLY, PanelUser, require_panel_user
from app.web.confirm import (
    CONFIRMATION_REFUSED,
    ConfirmationRefusedError,
    Operation,
    confirm_operation,
    first_text,
    issue_confirmation,
    second_text,
)
from app.web.context_person import ForeignDocumentsWarning, upload_warning
from app.web.routers.uploads import (
    CANCELLED_MESSAGE,
    DISMISSED_MESSAGE,
    UploadFileStatusResponse,
    create_upload,
    get_layout,
    get_plan_executor,
    get_upload_status,
)
from app.web.templating import MENU_BY_KEY, render_page

router = APIRouter(tags=["upload-page"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]

# Yenileme aralığı `upload_result.html`'dedir (`hx-trigger="every 2s"`).
PIPELINE_STAGES: tuple[tuple[UploadStatus, str], ...] = (
    (UploadStatus.RECEIVED, N_("Alındı")),
    (UploadStatus.RENDERING, N_("Sayfalar hazırlanıyor")),
    (UploadStatus.ANALYZING, N_("Analiz ediliyor")),
    (UploadStatus.PLANNING, N_("Plan hazırlanıyor")),
    (UploadStatus.EXECUTING, N_("Plan uygulanıyor")),
)
STATUS_LABELS: dict[UploadStatus, str] = {
    **dict(PIPELINE_STAGES),
    UploadStatus.DONE: N_("Tamamlandı"),
    UploadStatus.PARTIAL: N_("Kısmen tamamlandı — bazı sayfalar analiz edilemedi"),
    UploadStatus.FAILED: N_("İşlenemedi"),
    UploadStatus.CANCELLED: N_("İptal edildi"),
}
FINAL_STATUSES = frozenset(
    {UploadStatus.DONE, UploadStatus.PARTIAL, UploadStatus.FAILED, UploadStatus.CANCELLED}
)
# Adım çizelgesinde hiçbir adımı "tamam" göstermeyen son durumlar: parti sona varmadan durdu.
_STOPPED_STATUSES = frozenset({UploadStatus.FAILED, UploadStatus.CANCELLED})

NO_FILE_MESSAGE = N_("Yüklenecek dosya seçilmedi.")


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
    # 10.5.5: son durumdaki bağlamlı partinin bu çalışana ait görünmeyen belgeleri.
    warning: ForeignDocumentsWarning | None = None


def build_progress_view(session: Session, upload_id: str) -> ProgressView:
    """01.6.1 yanıtını (`get_upload_status`) sayfanın gösterdiği biçime çevirir; parti yoksa 404.

    Parti son durumdaysa kişi denetiminin uyarısı da hazırlanır (10.5.5); süren partinin planı
    henüz uygulanmadığı için uyarı son durumu bekler.
    """
    report = get_upload_status(upload_id, session)
    current = UploadStatus(report.status)
    final = current in FINAL_STATUSES
    steps: list[Step] = []
    reached = False
    for stage, label in PIPELINE_STAGES:
        if final:
            state = "todo" if current in _STOPPED_STATUSES else "done"
        elif stage is current:
            state, reached = "current", True
        else:
            state = "todo" if reached else "done"
        steps.append(Step(label, state))
    upload = session.get(Upload, report.upload_id) if final else None
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
        warning=None if upload is None else upload_warning(session, upload),
    )


def _employee_options(session: Session) -> list[Employee]:
    # 10.5.7: pasif çalışana yükleme yapılmaz (409); seçimde yalnız etkin çalışanlar durur.
    return list(
        session.scalars(
            select(Employee)
            .where(Employee.status == EmployeeStatus.ACTIVE.value)
            .order_by(Employee.folder_name)
        )
    )


def _result(request: Request, status_code: int = 200, **context: object) -> HTMLResponse:
    """`upload_result.html` parçasını çizer (HTMX hedefi: sayfadaki `#upload-result`)."""
    return render_page(request, "upload_result.html", user=None, status_code=status_code, **context)


@router.get("/upload", response_class=HTMLResponse, dependencies=WRITER_ONLY)
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
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    settings: Annotated[Settings, Depends(get_settings)],
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
            return _result(request, exc.status_code, error=exc.detail)

    view = build_progress_view(session, created.upload_id)
    # İş kuyrukta atomik olarak hazır; bu HTTP oturumu SQLite kilidini worker'a bırakır.
    session.rollback()
    return _result(
        request,
        status.HTTP_201_CREATED,
        progress=view,
        poll=not view.final,
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
        return _result(request, exc.status_code, error=exc.detail)
    return _result(request, progress=view, poll=not view.final)


# --- 10.3: yükleme detay sayfası ---------------------------------------------------------------

ROUTE_LABELS: dict[str, str] = {
    Route.READY.value: N_("Hazır"),
    Route.UNKNOWN.value: N_("Tür bilinmiyor kuyruğu"),
    Route.UNREADABLE.value: N_("Okunamadı kuyruğu"),
    Route.UNRESOLVED.value: N_("Sahibi belirsiz kuyruğu"),
    Route.SKIP.value: N_("Atlandı"),
}
# Ekranda görünen ad Türkçedir (İngilizce ve Sırpça panelde klasör adıyla: Unknown, Unreadable,
# Unresolved — §D92 f); enum değeri, URL ve diskteki kuyruk klasörü adı (PRD 08.1.1) İngilizce
# kalır. Klasörle eşleştirmek için İngilizce karşılık `QUEUE_FOLDERS`tadır.
QUEUE_LABELS = {
    "unknown": N_("Tür bilinmiyor"),
    "unreadable": N_("Okunamadı"),
    "unresolved": N_("Sahibi belirsiz"),
}
QUEUE_FOLDERS = {"unknown": "Unknown", "unreadable": "Unreadable", "unresolved": "Unresolved"}
EMPLOYEE_ACTION_LABELS = {
    "match": N_("Eşleşti"),
    "create": N_("Yeni çalışan"),
    "pending": N_("Onay bekleyen profil"),
    "none": N_("Çalışan yok"),
}
MATCHED_BY_LABELS = {
    "document_number": N_("belge numarası"),
    "name_dob": N_("ad-soyad + doğum tarihi"),
    "name": N_("yalnız ad-soyad"),
}
DOCUMENT_STATUS_LABELS = {
    DocumentStatus.ACTIVE.value: N_("Etkin"),
    DocumentStatus.SUPERSEDED.value: N_("Eski sürüm"),
    DocumentStatus.ARCHIVED.value: N_("Arşivlendi"),
    DocumentStatus.DELETED.value: N_("Silindi"),
}
PAGE_STATUS_LABELS = {
    PageAnalysisStatus.PENDING.value: N_("Bekliyor"),
    PageAnalysisStatus.DONE.value: N_("Analiz edildi"),
    PageAnalysisStatus.SKIPPED.value: N_("Atlandı"),
    PageAnalysisStatus.FAILED.value: N_("Analiz edilemedi"),
}

# Onay metinleri (10.3.2). §20.6 tablosu yalnız K16'nın beş manuel işlemini kapsar; yeniden analiz
# onları bu kalıpla tamamlar: birinci cümle ne yapılacağını, ikinci geri dönüşü olmayan sonucu
# söyler (PLAN.md §D23).
REANALYZE_FIRST_CONFIRMATION = N_("Bu partiyi yeniden analiz etmek üzeresiniz. Emin misiniz?")
REANALYZE_SECOND_CONFIRMATION = N_(
    "Bu işlem partiye yeni bir plan sürümü açacak; önceki sürümün çıktıları "
    '"eski sürüm" olarak işaretlenecektir. Son kararınız mı?'
)

UPLOAD_NOT_FOUND = N_("Parti bulunamadı.")
# 10.3.4 — yoksayılan partinin detay bildirimi (PLAN.md §C80) ve işlem reddi.
DISMISSED_NOTICE = N_("Bu tarama {when} tarihinde {user} tarafından yoksayıldı.")
DISMISS_BUSY_MESSAGE = N_("Parti hâlâ işleniyor; süren tarama yoksayılamaz.")
DISMISSED_RESOLUTION = N_("tarama yoksayıldı")
# 10.3.5 — geri alınacak yoksayma yok.
NOT_DISMISSED_MESSAGE = N_("Bu tarama yoksayılmamış; geri alınacak bir yoksayma yok.")
# 10.7.4 — gerekçeyle kapatılan kuyruk öğesinin çözümü.
CLOSED_RESOLUTION = N_("kapatıldı")
PAGE_IMAGE_NOT_FOUND = N_("Sayfa görüntüsü bulunamadı.")
BUSY_MESSAGE = N_("Parti hâlâ işleniyor; işlem bittikten sonra yeniden çalıştırılabilir.")
NO_PLAN_MESSAGE = N_(
    "Partinin planı yok; yeniden çalıştırılacak ya da yeniden analiz edilecek bir sürüm bulunmuyor."
)
# 10.3.6, 10.3.7 — iptal edilen partinin bildirimi (PLAN.md §D114 f), işlem reddi ve iptal reddi.
CANCELLED_NOTICE = N_("Bu parti {when} tarihinde {user} tarafından iptal edildi.")
TIMEOUT_CANCELLED_NOTICE = N_(
    "Bu parti 10 dakikada tamamlanamadığı için {when} tarihinde otomatik iptal edildi."
)
NOT_CANCELLABLE_MESSAGE = N_("Parti son durumda; iptal edilecek süren bir işlem yok.")


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
    # 05.5.4: çalışan yalnız isimle eşleşti (§20.2.2 satır 5a).
    name_only: bool = False


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
    path: str | None  # kalıcı silinen belgede boş (10.5.12)
    format: str
    sequence_no: int
    status: str
    status_label: str
    plan_version: int | None
    sources: list[str]
    # 05.5.4: planın yalnız isimle yerleştirdiği belge.
    name_only: bool = False


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
    # 10.5.5: bağlam çalışanına ait görünmeyen belgeler.
    context_warning: ForeignDocumentsWarning | None = None
    # 10.3.4: yoksayılan partinin bildirimi; yoksayma düğmesi yalnız `can_dismiss` iken.
    dismissed_notice: str | None = None
    can_dismiss: bool = False
    # 10.3.6, 10.3.7: iptal edilen partinin bildirimi; iptal düğmesi yalnız `can_cancel` iken.
    cancelled_notice: str | None = None
    can_cancel: bool = False


def _format_ts(moment: datetime) -> str:
    return f"{moment:%Y-%m-%d %H:%M:%S} UTC"


def _page_ranges(pages: tuple[int, ...] | list[int]) -> Translatable:
    """0 tabanlı sayfa sıralarını insanın okuyacağı 1 tabanlı aralığa çevirir: `[0, 1, 2, 4]` →
    `s. 1–3, 5`; sayfa listesi boşsa dosya bütün olarak alınmıştır."""
    if not pages:
        return Translatable(N_("tüm dosya"))
    runs: list[list[int]] = []
    for page in sorted(pages):
        if runs and page == runs[-1][-1] + 1:
            runs[-1].append(page)
        else:
            runs.append([page])
    parts = [f"{run[0] + 1}" if len(run) == 1 else f"{run[0] + 1}–{run[-1] + 1}" for run in runs]
    return Translatable(N_("s. {pages}"), pages=", ".join(parts))


def _source_text(files: dict[int, UploadFile], file_id: int, pages: list[int]) -> Translatable:
    upload_file = files.get(file_id)
    name = (
        upload_file.original_name
        if upload_file is not None
        else Translatable(N_("dosya {id}"), id=file_id)
    )
    return Translatable("{name} · {pages}", name=name, pages=_page_ranges(pages))


def _employee_label(employees: dict[str, Employee], employee_id: str) -> str:
    employee = employees.get(employee_id)
    # 10.5.13: kalıcı silinen çalışanın adı yoktur; yalnız E numarası görünür.
    if employee is None or employee.status == EmployeeStatus.DELETED.value:
        return employee_id
    return f"{employee_id} — {employee.given_names} {employee.surname}"


def _plan_employee_text(employee: PlanEmployee, employees: dict[str, Employee]) -> Translatable:
    template = "{action}"
    values: dict[str, object] = {
        "action": Translatable(EMPLOYEE_ACTION_LABELS[employee.action.value])
    }
    if employee.employee_id is not None:
        template += " · {employee}"
        values["employee"] = _employee_label(employees, employee.employee_id)
    if employee.matched_by is not None:
        template += " ({matched_by})"
        values["matched_by"] = Translatable(MATCHED_BY_LABELS[employee.matched_by.value])
    return Translatable(template, **values)


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
            name_only=item.employee.matched_by is MatchedBy.NAME,
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


def _event_place(event: Event, files: dict[int, UploadFile]) -> str | Translatable | None:
    if event.file_id is None:
        return None
    upload_file = files.get(event.file_id)
    name = (
        upload_file.original_name
        if upload_file is not None
        else Translatable(N_("dosya {id}"), id=event.file_id)
    )
    if event.page_index is None:
        return name
    page = Translatable(N_("s. {pages}"), pages=event.page_index + 1)
    return Translatable("{name} · {page}", name=name, page=page)


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

    by_name = name_matched_documents(outputs)
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
    if is_dismissed(upload):
        blocked_reason = DISMISSED_MESSAGE
    elif current_status is UploadStatus.CANCELLED:
        blocked_reason = CANCELLED_MESSAGE
    elif current_status not in FINAL_STATUSES:
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
                name_only=output.id in by_name,
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
                resolved=resolution_text(row),
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
        context_warning=upload_warning(session, upload),
        dismissed_notice=dismissed_notice(upload),
        can_dismiss=not is_dismissed(upload) and current_status in FINAL_STATUSES,
        cancelled_notice=cancelled_notice(session, upload),
        can_cancel=is_cancellable(upload),
    )


def cancelled_notice(session: Session, upload: Upload) -> Translatable | None:
    """10.3.6, 10.3.7 — elle: "Bu parti <tarih> tarihinde <kullanıcı> tarafından iptal edildi";
    otomatik: "… 10 dakikada tamamlanamadığı için … otomatik iptal edildi". İptal edilmemiş partide
    `None`."""
    if upload.status != UploadStatus.CANCELLED.value:
        return None
    found = last_cancellation(session, upload.id)
    if found is None:
        return Translatable(CANCELLED_NOTICE, when="—", user="—")
    when, actor, reason = found
    if reason == CancelReason.TIMEOUT.value:
        return Translatable(TIMEOUT_CANCELLED_NOTICE, when=_format_ts(when))
    return Translatable(CANCELLED_NOTICE, when=_format_ts(when), user=actor)


def dismissed_notice(upload: Upload) -> str | None:
    """10.3.4 — "Bu tarama <tarih> tarihinde <kullanıcı> tarafından yoksayıldı"; yoksayılmamış
    partide `None`."""
    if upload.dismissed_at is None:
        return None
    return Translatable(
        DISMISSED_NOTICE, when=_format_ts(upload.dismissed_at), user=upload.dismissed_by or "—"
    )


def resolution_text(queue_item: QueueItem) -> Translatable | None:
    """Kuyruk öğesinin çözümü: an ve kullanıcı; partisi yoksayılınca kapanan öğede nedeni de
    (10.3.4), gerekçeyle kapatılan öğede gerekçenin Türkçesi ve notu (10.7.4). Çözülmemiş öğede
    `None`."""
    if queue_item.resolved_at is None:
        return None
    template = "{when} · {user}"
    values: dict[str, object] = {
        "when": _format_ts(queue_item.resolved_at),
        "user": queue_item.resolved_by,
    }
    if queue_item.resolution == QueueResolution.DISMISSED.value:
        template += " · {resolution}"
        values["resolution"] = Translatable(DISMISSED_RESOLUTION)
    elif queue_item.resolution == QueueResolution.CLOSED.value:
        template += " · {resolution}: {reason}"
        values["resolution"] = Translatable(CLOSED_RESOLUTION)
        values["reason"] = close_reason_label(queue_item.resolution_reason) or "—"
        if queue_item.resolution_note:
            template += " — {note}"
            values["note"] = queue_item.resolution_note
    return Translatable(template, **values)


# --- 10.3.2: iki aşamalı onay belirteci --------------------------------------------------------


def reanalysis_subject(upload_id: str, plan_id: int) -> str:
    """Yeniden analiz belirtecinin bağlı olduğu hedef: parti + güncel plan (10.8.1 belirteci,
    işlem `Operation.REANALYZE`). Plan değişmişse belirteç geçmez."""
    return f"{upload_id}:{plan_id}"


def dismissal_subject(upload_id: str, plan_id: int | None) -> str:
    """Yoksayma belirtecinin bağlı olduğu hedef: parti + güncel plan (10.8.1 belirteci, işlem
    `Operation.DISMISS`); planı olmayan partide `none`. Plan değişmişse belirteç geçmez."""
    return f"{upload_id}:{plan_id if plan_id is not None else 'none'}"


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


def get_clock() -> datetime:
    """Otomatik iptalin saati (10.3.7): şimdiki UTC an; testte bağımlılık olarak değiştirilir."""
    return utcnow()


Clock = Annotated[datetime, Depends(get_clock)]


def expire_stale_uploads(session: Session, settings: Settings, now: datetime) -> list[str]:
    """10.3.7 — süresi dolan bitmemiş partileri `system` adına iptal eder ve commit eder; iptal
    edilenlerin kimliklerini döner. Yükleme listesi ve parti detayı açılırken çağrılır (modül
    açıklaması): işleyici kapalıyken de takılan parti yakalanır. İptal edilecek parti yoksa tek
    sorgudur, commit edilmez."""
    cancelled = cancel_stale_uploads(
        session, timeout_seconds=settings.upload_timeout_seconds, now=now
    )
    if cancelled:
        session.commit()
    return cancelled


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
    settings: Annotated[Settings, Depends(get_settings)],
    now: Clock,
) -> HTMLResponse:
    # 10.3.7: bu GET bilerek yazar — süresi dolan partiler iptal edilir (modül açıklaması).
    expire_stale_uploads(session, settings, now)
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
        dismiss_first_confirmation=first_text(Operation.DISMISS),
        cancel_first_confirmation=first_text(Operation.CANCEL_UPLOAD),
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
    if is_dismissed(upload):
        raise HTTPException(status.HTTP_409_CONFLICT, DISMISSED_MESSAGE)
    if upload.status == UploadStatus.CANCELLED.value:
        raise HTTPException(status.HTTP_409_CONFLICT, CANCELLED_MESSAGE)
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
        return _action_result(request, exc.status_code, error=exc.detail)
    except (NoPlanError, PlanIntegrityError, *PLAN_EXECUTION_ERRORS) as exc:
        session.rollback()
        return _action_result(request, status.HTTP_409_CONFLICT, error=exc)
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
        return _action_result(request, exc.status_code, error=exc.detail)
    except ConfirmationRefusedError as exc:
        session.rollback()
        return _action_result(request, status.HTTP_400_BAD_REQUEST, error=exc)
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
    settings: Annotated[Settings, Depends(get_settings)],
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
            catalog_token_budget=settings.catalog_token_budget,
        )
    except HTTPException as exc:
        session.rollback()
        return _action_result(request, exc.status_code, error=exc.detail)
    except ConfirmationRefusedError:
        session.rollback()
        return _action_result(request, status.HTTP_400_BAD_REQUEST, error=CONFIRMATION_REFUSED)
    except ReanalysisProviderError as exc:
        session.rollback()
        return _action_result(request, status.HTTP_503_SERVICE_UNAVAILABLE, error=exc)
    except (NoPlanError, *PLAN_EXECUTION_ERRORS) as exc:
        session.rollback()
        return _action_result(request, status.HTTP_409_CONFLICT, error=exc)
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


# --- 10.3.4: taramayı yoksay -------------------------------------------------------------------


def _dismissal_target(session: Session, upload_id: str) -> tuple[Upload, Plan | None]:
    """Yoksayılacak parti ve güncel planı (yoksa `None`); parti yoksa 404."""
    upload = session.get(Upload, upload_id)
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, UPLOAD_NOT_FOUND)
    return upload, current_plan(session, upload)


def _check_dismissable(upload: Upload) -> None:
    """Parti yoksayılamıyorsa nedenini taşıyan 409."""
    if is_dismissed(upload):
        raise HTTPException(status.HTTP_409_CONFLICT, DISMISSED_MESSAGE)
    if UploadStatus(upload.status) not in FINAL_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, DISMISS_BUSY_MESSAGE)


@router.post("/uploads/{upload_id}/dismiss/prepare", response_class=HTMLResponse)
def prepare_dismissal(
    upload_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """10.3.4 — birinci onaydan sonra §20.6'nın ikinci metnini (<N> kuyruk öğesi, <M> etkin belge)
    ve tek kullanımlık onay belirtecini verir; hiçbir şeyi değiştirmez (S16)."""
    try:
        upload, plan = _dismissal_target(session, upload_id)
        _check_dismissable(upload)
        preview = preview_dismissal(session, upload)
        issued = issue_confirmation(
            session,
            request,
            user,
            Operation.DISMISS,
            dismissal_subject(upload.id, plan.id if plan is not None else None),
        )
    except HTTPException as exc:
        session.rollback()
        return _action_result(request, exc.status_code, error=exc.detail)
    except ConfirmationRefusedError as exc:
        session.rollback()
        return _action_result(request, status.HTTP_400_BAD_REQUEST, error=exc)
    session.commit()
    return _action_result(
        request,
        status.HTTP_200_OK,
        upload_id=upload_id,
        confirm_action="dismiss",
        second_confirmation=second_text(
            Operation.DISMISS,
            queue_items=preview.queue_items,
            documents=preview.active_documents,
        ),
        confirmation=issued.token,
    )


@router.post("/uploads/{upload_id}/dismiss", response_class=HTMLResponse)
def dismiss_upload_page(
    upload_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    confirmation: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    """10.3.4 — ikinci onayın belirteciyle partiyi yoksayar (`app.pipeline.dismiss`).

    Belirteçsiz, kullanılmış, süresi geçmiş ya da başka partiye/plana ait istek 400; parti
    yoksayılamıyorsa 409 — ikisinde de hiçbir şey değişmez ve belirteç tüketilmez.
    """
    try:
        upload, plan = _dismissal_target(session, upload_id)
        plan_id = plan.id if plan is not None else None
        # §20.6.1: belirteç tüketilir ve `USER_CONFIRMED` (kullanıcı adı, işlem, hedef, iki onayın
        # zamanı) yazılır, ardından işlemin kendi olayı (`UPLOAD_DISMISSED`) düşer.
        confirm_operation(
            session,
            request,
            user,
            Operation.DISMISS,
            dismissal_subject(upload.id, plan_id),
            confirmation,
            event_target={"upload_id": upload.id, "plan_id": plan_id},
            upload_id=upload.id,
        )
        _check_dismissable(upload)
        dismissal = dismiss_upload(session, upload, actor=user.username)
    except HTTPException as exc:
        session.rollback()
        return _action_result(request, exc.status_code, error=exc.detail)
    except ConfirmationRefusedError:
        session.rollback()
        return _action_result(request, status.HTTP_400_BAD_REQUEST, error=CONFIRMATION_REFUSED)
    except UploadNotDismissableError:
        # Aynı anda gelen öteki istek partiyi yoksaydı ya da parti yeniden işlenmeye başladı.
        session.rollback()
        return _action_result(request, status.HTTP_409_CONFLICT, error=DISMISSED_MESSAGE)
    session.commit()
    return _action_result(
        request,
        status.HTTP_200_OK,
        upload_id=upload_id,
        done="dismiss",
        closed=len(dismissal.queue_item_ids),
        kept=len(dismissal.active_document_ids),
    )


# --- 10.3.5: yoksaymayı geri al ------------------------------------------------------------------


@router.post("/uploads/{upload_id}/undismiss", response_class=HTMLResponse)
def undismiss_upload(
    upload_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """10.3.5 — yoksayılan partiyi tek adımda geri alır (§D61): parti listeye döner, yoksaymayla
    kapanan kuyruk öğeleri yeniden açılır; `UPLOAD_RESTORED` kullanıcı adıyla yazılır. Parti yoksa
    404, yoksayılmamışsa 409 ve hiçbir şey değişmez."""
    upload = session.get(Upload, upload_id)
    if upload is None:
        session.rollback()
        return _action_result(request, status.HTTP_404_NOT_FOUND, error=UPLOAD_NOT_FOUND)
    try:
        restoration = restore_upload(session, upload, actor=user.username)
    except UploadNotRestorableError:
        session.rollback()
        return _action_result(request, status.HTTP_409_CONFLICT, error=NOT_DISMISSED_MESSAGE)
    session.commit()
    return _action_result(
        request,
        status.HTTP_200_OK,
        upload_id=upload_id,
        done="undismiss",
        reopened=len(restoration.queue_item_ids),
    )


# --- 10.3.6: süren partiyi iptal et --------------------------------------------------------------


def cancellation_subject(upload_id: str) -> str:
    """İptal belirtecinin bağlı olduğu hedef: parti (10.8.1 belirteci, işlem
    `Operation.CANCEL_UPLOAD`)."""
    return upload_id


@router.post("/uploads/{upload_id}/cancel/prepare", response_class=HTMLResponse)
def prepare_cancellation(
    upload_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """10.3.6 — birinci onaydan sonra §20.6'nın ikinci metnini ve tek kullanımlık onay belirtecini
    verir; hiçbir şeyi değiştirmez (S16). Parti yoksa 404, son durumdaysa 409."""
    upload = session.get(Upload, upload_id)
    if upload is None:
        session.rollback()
        return _action_result(request, status.HTTP_404_NOT_FOUND, error=UPLOAD_NOT_FOUND)
    if not is_cancellable(upload):
        session.rollback()
        return _action_result(request, status.HTTP_409_CONFLICT, error=NOT_CANCELLABLE_MESSAGE)
    try:
        issued = issue_confirmation(
            session, request, user, Operation.CANCEL_UPLOAD, cancellation_subject(upload.id)
        )
    except ConfirmationRefusedError as exc:
        session.rollback()
        return _action_result(request, status.HTTP_400_BAD_REQUEST, error=exc)
    session.commit()
    return _action_result(
        request,
        status.HTTP_200_OK,
        upload_id=upload_id,
        confirm_action="cancel",
        second_confirmation=second_text(Operation.CANCEL_UPLOAD),
        confirmation=issued.token,
    )


@router.post("/uploads/{upload_id}/cancel", response_class=HTMLResponse)
def cancel_upload_page(
    upload_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    confirmation: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    """10.3.6 — ikinci onayın belirteciyle süren partiyi iptal eder (`app.pipeline.cancel`).

    Belirteçsiz, kullanılmış, süresi geçmiş ya da başka partiye ait istek 400; parti bu arada son
    duruma vardıysa 409 — ikisinde de hiçbir şey değişmez ve belirteç tüketilmez.
    """
    upload = session.get(Upload, upload_id)
    if upload is None:
        session.rollback()
        return _action_result(request, status.HTTP_404_NOT_FOUND, error=UPLOAD_NOT_FOUND)
    try:
        # §20.6.1: belirteç tüketilir ve `USER_CONFIRMED` (kullanıcı adı, işlem, hedef, iki onayın
        # zamanı) yazılır, ardından işlemin kendi olayı (`UPLOAD_CANCELLED`) düşer.
        confirm_operation(
            session,
            request,
            user,
            Operation.CANCEL_UPLOAD,
            cancellation_subject(upload.id),
            confirmation,
            event_target={"upload_id": upload.id},
            upload_id=upload.id,
        )
        cancellation = cancel_upload(
            session, upload, actor=user.username, reason=CancelReason.MANUAL
        )
    except ConfirmationRefusedError:
        session.rollback()
        return _action_result(request, status.HTTP_400_BAD_REQUEST, error=CONFIRMATION_REFUSED)
    except UploadNotCancellableError:
        # Parti bu arada bitti, işlenemedi ya da başka istekle (ya da süre aşımıyla) iptal edildi.
        session.rollback()
        return _action_result(request, status.HTTP_409_CONFLICT, error=NOT_CANCELLABLE_MESSAGE)
    session.commit()
    return _action_result(
        request,
        status.HTTP_200_OK,
        upload_id=upload_id,
        done="cancel",
        stage=STATUS_LABELS[cancellation.stage],
    )
