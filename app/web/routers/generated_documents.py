"""Profilden "Çıktıya hazırla" ve üretilen belgeleri açma/indirme (PRD 15.2.1, 15.2.2; PLAN.md
§D123 d, f, g).

- `POST /employees/{employee_id}/outputs` (form: `template_id`) hazır şablonun kopyasını
  çalışanın profil değerleriyle doldurur (`app.output_templates.generate`), `Uretilen/`'e yazar ve
  profile döner. Tek adımlıdır (§D61, K16: yeniden üretim ve arşiv geri alır). Bildirim doldurulan
  alan sayısını, eksik (profilde boş) ve taşan alanların **adlarını** söyler; değer taşımaz
  (10.11.1). Çalışan yoksa 404; pasif ya da birleştirilmişse, şablon hazır değilse (taslak, arşiv,
  onaylı harita yok) 409; şablon dosyası yoksa 404.
- `GET .../outputs/{generated_document_id}/file` (yeni sekmede açma) ve `.../download` (indirme)
  üretilen belgeyi olduğu gibi sunar ve önce erişim logunu `generated_document_id` ile yazar
  (10.9.2). Belge bu çalışanın değilse, kalıcı silinmişse ya da dosyası yoksa 404, kayıt düşmez.

Yazma yolu İK/root'tur (10.1.8: `app.main` yazma kapısını bağlar); Kullanıcı bölümleri görür,
belgeyi açar ve indirir. Kalıcı silinen çalışanın adresleri "silindi" sayfasını döner
(`employees.reject_deleted_employee`). Üretilen belge `documents`'a girmez; çalışan belgelerine ve
şablonun orijinaline dokunulmaz.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AccessAction,
    Employee,
    GeneratedDocument,
    GeneratedDocumentStatus,
    OutputTemplate,
)
from app.db.session import get_session
from app.i18n import N_
from app.output_templates.generate import (
    EmployeeNotEligibleError,
    TemplateFileMissingError,
    TemplateNotReadyError,
    generate_document,
)
from app.storage import DataLayout
from app.web.access import record_access
from app.web.auth import PanelUser, require_panel_user
from app.web.feedback import (
    OUTPUT_GENERATED,
    OUTPUT_GENERATED_MISSING,
    OUTPUT_GENERATED_MISSING_OVERFLOW,
    OUTPUT_GENERATED_OVERFLOW,
    flash,
)
from app.web.routers.uploads import get_layout

router = APIRouter(tags=["generated-documents"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]
DbSession = Annotated[Session, Depends(get_session)]
Layout = Annotated[DataLayout, Depends(get_layout)]

EMPLOYEE_NOT_FOUND = N_("Çalışan bulunamadı")
TEMPLATE_NOT_FOUND = N_("Şablon bulunamadı")
TEMPLATE_FILE_NOT_FOUND = N_("Şablon dosyası bulunamadı")
EMPLOYEE_NOT_ACTIVE = N_(
    "Yalnız etkin çalışana çıktı hazırlanır; pasif ya da birleştirilmiş kayda hazırlanmaz."
)
TEMPLATE_NOT_READY = N_(
    "Şablon hazır değil: alan haritası onaylanmamış ya da şablon arşivde. Önce şablonu hazırlayın."
)
OUTPUT_NOT_FOUND = N_("Üretilen belge bulunamadı")
OUTPUT_FILE_NOT_FOUND = N_("Üretilen belgenin dosyası bulunamadı")
PDF_MEDIA_TYPE = "application/pdf"
FILE_HEADERS = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}
# Profilde üretilen belgeler bölümünün çapası.
OUTPUTS_SECTION = "outputs"


def _redirect(employee_id: str, key: str, **params: object) -> RedirectResponse:
    response = RedirectResponse(
        f"/employees/{employee_id}#{OUTPUTS_SECTION}", status.HTTP_303_SEE_OTHER
    )
    flash(response, key, **params)
    return response


@router.post("/employees/{employee_id}/outputs")
def generate_output(
    employee_id: str,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    template_id: Annotated[int, Form()],
) -> RedirectResponse:
    """15.2.1 — "Çıktıya hazırla" (tek adım); sonuç profilin "Üretilen belgeler" bölümündedir."""
    employee = session.get(Employee, employee_id)
    template = session.get(OutputTemplate, template_id)
    if employee is None or template is None:
        session.rollback()
        detail = EMPLOYEE_NOT_FOUND if employee is None else TEMPLATE_NOT_FOUND
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail)
    try:
        result = generate_document(session, layout, template, employee, actor=user.username)
        session.commit()
    except EmployeeNotEligibleError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, EMPLOYEE_NOT_ACTIVE) from None
    except TemplateNotReadyError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, TEMPLATE_NOT_READY) from None
    except TemplateFileMissingError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, TEMPLATE_FILE_NOT_FOUND) from None
    missing = ",".join(result.missing)
    overflow = ",".join(result.truncated)
    if missing and overflow:
        return _redirect(
            employee_id, OUTPUT_GENERATED_MISSING_OVERFLOW, fields=missing, overflow=overflow
        )
    if missing:
        return _redirect(employee_id, OUTPUT_GENERATED_MISSING, fields=missing)
    if overflow:
        return _redirect(employee_id, OUTPUT_GENERATED_OVERFLOW, overflow=overflow)
    return _redirect(employee_id, OUTPUT_GENERATED, count=len(result.filled))


def _stored_output(
    session: Session,
    layout: DataLayout,
    employee_id: str,
    generated_document_id: int,
    *,
    user: PanelUser,
    action: AccessAction,
) -> Path:
    """Üretilen belgeyi erişim logunu yazarak çözer; log sunmadan **önce** commit edilir (10.9.2).
    Belge bu çalışanın değilse, kalıcı silinmişse ya da dosyası yoksa 404 ve kayıt düşmez."""
    document = session.scalars(
        select(GeneratedDocument).where(
            GeneratedDocument.id == generated_document_id,
            GeneratedDocument.employee_id == employee_id,
            GeneratedDocument.status != GeneratedDocumentStatus.DELETED.value,
        )
    ).first()
    path: Path | None = None
    if document is not None and document.path:
        try:
            path = layout.resolve(document.path)
        except ValueError:
            path = None
    if document is None or path is None or not path.is_file():
        session.rollback()
        detail = OUTPUT_NOT_FOUND if document is None else OUTPUT_FILE_NOT_FOUND
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail)
    record_access(session, user_id=user.id, generated_document_id=document.id, action=action)
    session.commit()
    return path


def _serve(path: Path, disposition: str) -> FileResponse:
    return FileResponse(
        path,
        media_type=PDF_MEDIA_TYPE,
        filename=path.name,
        content_disposition_type=disposition,
        headers=FILE_HEADERS,
    )


@router.get("/employees/{employee_id}/outputs/{generated_document_id}/file")
def open_output(
    employee_id: str,
    generated_document_id: int,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
) -> FileResponse:
    """15.2.2 — üretilen belgeyi tarayıcıda açar (bağlantı yeni sekmede); `view` kaydı."""
    path = _stored_output(
        session, layout, employee_id, generated_document_id, user=user, action=AccessAction.VIEW
    )
    return _serve(path, "inline")


@router.get("/employees/{employee_id}/outputs/{generated_document_id}/download")
def download_output(
    employee_id: str,
    generated_document_id: int,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
) -> FileResponse:
    """15.2.2 — üretilen belgeyi K8 adıyla indirtir; `download` kaydı."""
    path = _stored_output(
        session,
        layout,
        employee_id,
        generated_document_id,
        user=user,
        action=AccessAction.DOWNLOAD,
    )
    return _serve(path, "attachment")
