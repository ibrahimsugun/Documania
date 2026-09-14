"""Yükleme uç noktası — çoklu dosya partisi oluşturma (PRD 01.1.1, 01.1.2, 01.3.1).

Her dosya `Inbox/<upload_id>/<orijinal_ad>` altına değişmez biçimde yazılır (K10); yol yalnız
`app.storage.DataLayout` üzerinden kurulur. `context_employee_id` verilirse partiye bağlanır —
sahibi belirsiz dosyaların bu çalışana atanması, çalışan eşleştirme boru hattının (FR-MOD-05)
işidir.

Boyut ve (PDF için) sayfa sınırı (01.3.1) her dosya diske yazılmadan/partiye kaydedilmeden önce
denetlenir; sınırı aşan tek dosya olsa bile parti hiç oluşturulmaz.
"""

from __future__ import annotations

from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, status
from fastapi import UploadFile as FastAPIFile
from pydantic import BaseModel
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Employee, Upload, UploadFile, allocate_upload_id
from app.db.session import get_session
from app.events import EventType, event_context, record_event
from app.storage import DataLayout, FileKind, UnsupportedFileTypeError, detect_file_kind, write_file

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

UPLOAD_CHANNEL = "web"


class UploadCreateResponse(BaseModel):
    upload_id: str


def get_layout() -> DataLayout:
    return DataLayout(get_settings().data_dir)


def _validated_name(file: FastAPIFile) -> str:
    """Orijinal adı sözleşmeye uygun hâlde döner; yol ayracı/`..` içeriyorsa reddeder."""
    name = file.filename
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


@router.post("", response_model=UploadCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_upload(
    files: Annotated[list[FastAPIFile], File()],
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    settings: Annotated[Settings, Depends(get_settings)],
    context_employee_id: Annotated[str | None, Form()] = None,
) -> UploadCreateResponse:
    names = [_validated_name(file) for file in files]
    if len(set(names)) != len(names):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Aynı partide aynı adda birden çok dosya olamaz."
        )

    contents = [await file.read() for file in files]
    for name, content in zip(names, contents, strict=True):
        _check_size_and_page_limits(name, content, settings)

    if context_employee_id is not None and session.get(Employee, context_employee_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "context_employee_id bulunamadı.")

    upload_id = allocate_upload_id(session)
    session.add(
        Upload(id=upload_id, channel=UPLOAD_CHANNEL, context_employee_id=context_employee_id)
    )
    session.flush()

    inbox_dir = layout.upload_inbox_dir(upload_id)
    with event_context(upload_id=upload_id):
        for file, name, content in zip(files, names, contents, strict=True):
            stored = write_file(inbox_dir / name, content)
            upload_file = UploadFile(
                upload_id=upload_id,
                original_name=name,
                stored_path=stored.path.relative_to(layout.root).as_posix(),
                sha256=stored.sha256,
                mime=file.content_type or "application/octet-stream",
            )
            session.add(upload_file)
            session.flush()
            record_event(session, EventType.FILE_UPLOADED, file_id=upload_file.id, message=name)

    session.commit()
    return UploadCreateResponse(upload_id=upload_id)
