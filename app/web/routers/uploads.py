"""Yükleme uç noktası — çoklu dosya partisi oluşturma (PRD 01.1.1, 01.1.2, 01.3.1), planı yeniden
çalıştırma ve yeniden analiz (06.6.1, 06.6.2).

Her dosya `Inbox/<upload_id>/<orijinal_ad>` altına değişmez biçimde yazılır (K10); yol yalnız
`app.storage.DataLayout` üzerinden kurulur. `context_employee_id` verilirse partiye bağlanır —
sahibi belirsiz dosyaların bu çalışana atanması, çalışan eşleştirme boru hattının (FR-MOD-05)
işidir.

Boyut ve (PDF için) sayfa sınırı (01.3.1) her dosya diske yazılmadan/partiye kaydedilmeden önce
denetlenir; sınırı aşan tek dosya olsa bile parti hiç oluşturulmaz.

Partiyi kuran çekirdek `store_upload`'dır (eşzamanlı, HTTP'den bağımsız): web uç noktası ve Telegram
botu (12.2.1) aynı doğrulamadan, aynı Inbox yazımından ve aynı tekrar tespitinden geçer; yalnız
`channel`/`uploaded_by` değişir. Hata `HTTPException` olarak yükselir, `detail` kullanıcıya
gösterilecek Türkçe iletidir.

`POST /{upload_id}/rerun` güncel planı yeniden uygular; yapay zekâ sağlayıcısı bu uç noktanın
bağımlılıkları arasında yoktur. `POST /{upload_id}/reanalyze` partiyi yeniden analiz eder ve yeni
plan sürümünü açar (`app.pipeline.orchestrate`). İkisi de işi tek işlemde yapar: hata olursa
hiçbir şey commit edilmez. Planı uygulayan adım `get_plan_executor` bağımlılığıdır — uygulamanın
uygulayıcısı (`plan_executor`: çıktılar 07.x, kuyruk 08.1, profil 09.1; 09.2 bağlar). Plan öğesini
yürütemeyen hata (kayıt, Inbox bütünlüğü K10, işlem) 409 döner.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, status
from fastapi import UploadFile as FastAPIFile
from pydantic import BaseModel
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy.orm import Session

from app.ai.provider import AnalysisProvider, ProviderConfigError, create_provider
from app.catalog import export_catalog
from app.config import Settings, get_settings
from app.db.models import Employee, Upload, UploadFile, allocate_upload_id
from app.db.session import get_session
from app.events import EventType, event_context, record_event
from app.pipeline.orchestrate import (
    PLAN_EXECUTION_ERRORS,
    NoPlanError,
    PlanExecutor,
    plan_executor,
    reanalyze_upload,
    rerun_plan,
)
from app.pipeline.plan import PlanIntegrityError
from app.storage import (
    DataLayout,
    FileKind,
    UnsupportedFileTypeError,
    detect_file_kind,
    find_original_by_sha256,
    write_to_inbox,
)

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

UPLOAD_CHANNEL = "web"


@dataclass(frozen=True, slots=True)
class IncomingFile:
    """Partiye girecek dosya: adı, baytları ve istemcinin bildirdiği içerik türü."""

    name: str
    content: bytes
    content_type: str | None


class UploadCreateResponse(BaseModel):
    upload_id: str


class UploadFileStatusResponse(BaseModel):
    id: int
    original_name: str
    mime: str
    sha256: str
    page_count: int | None
    is_duplicate: bool


class UploadProgressResponse(BaseModel):
    total_files: int
    rendered_files: int


class UploadStatusResponse(BaseModel):
    upload_id: str
    status: str
    files: list[UploadFileStatusResponse]
    progress: UploadProgressResponse


class PlanRunResponse(BaseModel):
    upload_id: str
    plan_id: int
    version: int
    plan_hash: str


class ReanalysisResponse(PlanRunResponse):
    previous_plan_id: int
    previous_version: int
    superseded_document_ids: list[int]


def get_layout() -> DataLayout:
    return DataLayout(get_settings().data_dir)


def get_plan_executor(settings: Annotated[Settings, Depends(get_settings)]) -> PlanExecutor:
    """Planı uygulayan adım (06.6): uygulamanın uygulayıcısı, `render_image` ayarları `.env`'den."""
    return plan_executor(settings)


def get_analysis_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalysisProvider:
    """`.env`'deki `AI_PROVIDER` sağlayıcısı (03.2.1); kurulamıyorsa 503."""
    try:
        return create_provider(settings)
    except ProviderConfigError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None


def _get_upload(session: Session, upload_id: str) -> Upload:
    upload = session.get(Upload, upload_id)
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Parti bulunamadı.")
    return upload


def _validated_name(name: str) -> str:
    """Orijinal adı sözleşmeye uygun hâlde döner; yol ayracı/`..` içeriyorsa reddeder."""
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Geçersiz dosya adı.")
    return name


def _pdf_page_count(content: bytes) -> int | None:
    """PDF sayfa sayısını döner; içerik PDF değilse veya çözülemezse `None` (denetim atlanır)."""
    try:
        if detect_file_kind(content) is not FileKind.PDF:
            return None
    except UnsupportedFileTypeError:
        return None
    try:
        return len(PdfReader(BytesIO(content)).pages)
    except PdfReadError:
        return None


def _check_size_and_page_limits(name: str, content: bytes, settings: Settings) -> None:
    """01.3.1 — sınırı aşan dosyayı reddeder ve kullanıcıya bölmesini söyler."""
    if len(content) > settings.max_upload_file_size_bytes:
        limit_mb = settings.max_upload_file_size_bytes / (1024 * 1024)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"'{name}' dosyası {limit_mb:.0f} MB sınırını aşıyor. "
            "Lütfen dosyayı bölüp tekrar yükleyin.",
        )
    page_count = _pdf_page_count(content)
    if page_count is not None and page_count > settings.max_upload_pdf_pages:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"'{name}' dosyası {settings.max_upload_pdf_pages} sayfa sınırını aşıyor "
            f"({page_count} sayfa). Lütfen dosyayı bölüp tekrar yükleyin.",
        )


def store_upload(
    session: Session,
    layout: DataLayout,
    settings: Settings,
    files: Sequence[IncomingFile],
    *,
    channel: str,
    uploaded_by: str | None = None,
    context_employee_id: str | None = None,
) -> str:
    """Dosyaları tek parti olarak Inbox'a yazar, kaydeder ve commit eder; `upload_id` döner.

    Ad, boyut/sayfa sınırı (01.3.1) ve bağlam çalışanı doğrulanır; biri tutmazsa `HTTPException`
    ve hiçbir şey yazılmaz. Tekrar (01.4.1) yalnız işaretlenir, dosya yine Inbox'a yazılır (K10).
    """
    names = [_validated_name(file.name) for file in files]
    if len(set(names)) != len(names):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Aynı partide aynı adda birden çok dosya olamaz."
        )
    for name, file in zip(names, files, strict=True):
        _check_size_and_page_limits(name, file.content, settings)

    if context_employee_id is not None and session.get(Employee, context_employee_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "context_employee_id bulunamadı.")

    upload_id = allocate_upload_id(session)
    session.add(
        Upload(
            id=upload_id,
            channel=channel,
            uploaded_by=uploaded_by,
            context_employee_id=context_employee_id,
        )
    )
    session.flush()

    with event_context(upload_id=upload_id):
        for name, file in zip(names, files, strict=True):
            stored = write_to_inbox(layout, upload_id, name, file.content)
            # K10: içerik hâlâ değişmez biçimde Inbox'a yazılır; tekrar yalnız işaretlenir,
            # dosya reddedilmez. Analiz adımı (henüz yok) `is_duplicate_of` alanına bakarak
            # bu satırı atlayacak.
            original = find_original_by_sha256(session, stored.sha256)
            upload_file = UploadFile(
                upload_id=upload_id,
                original_name=name,
                stored_path=stored.path.relative_to(layout.root).as_posix(),
                sha256=stored.sha256,
                mime=file.content_type or "application/octet-stream",
                is_duplicate_of=original.id if original is not None else None,
            )
            session.add(upload_file)
            session.flush()
            if original is not None:
                record_event(
                    session,
                    EventType.FILE_DUPLICATE,
                    file_id=upload_file.id,
                    message=name,
                    data={"duplicate_of_file_id": original.id},
                )
            else:
                record_event(session, EventType.FILE_UPLOADED, file_id=upload_file.id, message=name)

    session.commit()
    return upload_id


@router.post("", response_model=UploadCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_upload(
    files: Annotated[list[FastAPIFile], File()],
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    settings: Annotated[Settings, Depends(get_settings)],
    context_employee_id: Annotated[str | None, Form()] = None,
) -> UploadCreateResponse:
    incoming = [
        IncomingFile(file.filename or "", await file.read(), file.content_type) for file in files
    ]
    upload_id = store_upload(
        session,
        layout,
        settings,
        incoming,
        channel=UPLOAD_CHANNEL,
        context_employee_id=context_employee_id,
    )
    return UploadCreateResponse(upload_id=upload_id)


@router.get("/{upload_id}", response_model=UploadStatusResponse)
def get_upload_status(
    upload_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> UploadStatusResponse:
    """01.6.1 — parti durumu, dosyaları ve dosya başına sayfa üretim ilerlemesini döner."""
    upload = _get_upload(session, upload_id)

    files = [
        UploadFileStatusResponse(
            id=file.id,
            original_name=file.original_name,
            mime=file.mime,
            sha256=file.sha256,
            page_count=file.page_count,
            is_duplicate=file.is_duplicate_of is not None,
        )
        for file in upload.files
    ]
    rendered_files = sum(1 for file in upload.files if len(file.pages) > 0)

    return UploadStatusResponse(
        upload_id=upload.id,
        status=upload.status,
        files=files,
        progress=UploadProgressResponse(total_files=len(files), rendered_files=rendered_files),
    )


@router.post("/{upload_id}/rerun", response_model=PlanRunResponse)
def rerun_upload_plan(
    upload_id: str,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    executor: Annotated[PlanExecutor, Depends(get_plan_executor)],
) -> PlanRunResponse:
    """06.6.1 — güncel planı yapay zekâ çağırmadan yeniden uygular; plan yok/değişmiş/öğe
    yürütülemiyor: 409."""
    upload = _get_upload(session, upload_id)
    try:
        run = rerun_plan(session, layout, upload, executor=executor)
    except (NoPlanError, PlanIntegrityError, *PLAN_EXECUTION_ERRORS) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    session.commit()
    return PlanRunResponse(
        upload_id=upload.id,
        plan_id=run.plan.id,
        version=run.plan.version,
        plan_hash=run.plan.plan_hash,
    )


@router.post("/{upload_id}/reanalyze", response_model=ReanalysisResponse)
def reanalyze_upload_plan(
    upload_id: str,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    executor: Annotated[PlanExecutor, Depends(get_plan_executor)],
    provider: Annotated[AnalysisProvider, Depends(get_analysis_provider)],
) -> ReanalysisResponse:
    """06.6.2 — partiyi yeniden analiz eder, yeni plan sürümünü açar; plan yok/öğe yürütülemiyor:
    409."""
    upload = _get_upload(session, upload_id)
    try:
        reanalysis = reanalyze_upload(
            session,
            layout,
            upload,
            provider=provider,
            catalog=export_catalog(session),
            executor=executor,
        )
    except (NoPlanError, *PLAN_EXECUTION_ERRORS) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    session.commit()
    return ReanalysisResponse(
        upload_id=upload.id,
        plan_id=reanalysis.plan.id,
        version=reanalysis.plan.version,
        plan_hash=reanalysis.plan.plan_hash,
        previous_plan_id=reanalysis.previous_plan.id,
        previous_version=reanalysis.previous_plan.version,
        superseded_document_ids=list(reanalysis.superseded_document_ids),
    )
