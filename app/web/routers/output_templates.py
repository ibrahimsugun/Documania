"""Hazır Şablonlar ekranı (PRD 15.1.1, 15.1.4; PLAN.md §D123 b, f, g).

- `GET /output-templates` şablonları listeler: ilk sayfa küçük resmi, ad, açıklama, sayfa, alan
  sayısı, durum, yükleyen, zaman. Varsayılan arşivdekiler dışındakiler; `?status=draft|ready|
  archived` duruma göre süzer (15.1.4).
- `GET /output-templates/new` + `POST /output-templates` şablon yükler (ad tekil, açıklama, tek
  dosya PDF/JPEG/PNG; görüntü kayıpsız PDF'e sarılır). Kural dışı değer 422, aynı ad ya da aynı
  dosya (SHA-256) 409 ile form yeniden çizilir; tekrar dosya ayrıca uyarı bildirimi alır.
- `GET /output-templates/{id}` şablonun sayfasıdır: bilgiler, sayfa önizlemeleri, orijinali yeni
  sekmede açma ve indirme, arşivleme ve geri alma (`POST .../archive`, `.../restore`).
- Yükleme şablonu yapay zekâ incelemesine koyar (15.1.2, `app.output_templates.examine`); işçi
  haritayı yeni sürüm olarak yazar. Sağlayıcı ayarlı değilse kuyruğa girmez, sebep listede ve
  sayfada görünür. `POST .../examine` ("yeniden incele") aynı isteği tekrarlar; sonuç yeni sürümdür,
  eski sürüm silinmez. Arşivdeki şablon incelenmez (409).
- `GET .../file` (açma) ve `.../download` (indirme) dosyayı olduğu gibi sunar ve önce erişim
  logunu `template_id` ile yazar (10.9.2); `GET .../pages/{n}` önizleme görüntüsüdür, kayda
  girmez (sayfa görüntülemek dosyayı açmak sayılmaz, §D123 f kararı).

Yazma yolları İK/root'tur (10.1.8: `app.main` yönlendiriciye yazma kapısını bağlar, yalnız yazmaya
götüren `GET` sayfası `WRITER_ONLY` taşır); Kullanıcı listeyi, sayfayı ve önizlemeyi görür. Şablon
yüklemesi parti, çalışan, kuyruk öğesi ya da çıktı belgesi açmaz ve belge içeriğine dokunmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.ai.provider import ProviderConfigError, create_provider
from app.config import Settings, get_settings
from app.db.models import AccessAction, OutputTemplate, OutputTemplateStatus
from app.db.session import get_session
from app.i18n import N_
from app.output_templates import (
    DESCRIPTION_MAX_LENGTH,
    NAME_MAX_LENGTH,
    DuplicateTemplateError,
    TemplateFormError,
    TemplateNameTakenError,
    TemplateNotFoundError,
    create_template,
    field_count,
    get_template,
    list_templates,
    set_template_archived,
    status_counts,
)
from app.output_templates.examine import (
    ExamineError,
    TemplateArchivedError,
    is_examining,
    request_examination,
)
from app.storage import DataLayout
from app.web.access import record_access
from app.web.auth import WRITER_ONLY, PanelUser, require_panel_user
from app.web.feedback import (
    TEMPLATE_ARCHIVED,
    TEMPLATE_DUPLICATE,
    TEMPLATE_EXAMINE_REQUESTED,
    TEMPLATE_EXAMINE_UNAVAILABLE,
    TEMPLATE_RESTORED,
    TEMPLATE_UPLOADED,
    TEMPLATE_UPLOADED_UNEXAMINED,
    flash,
    render,
)
from app.web.routers.uploads import get_layout
from app.web.templating import MENU_BY_KEY, render_page

router = APIRouter(tags=["output-templates"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]
DbSession = Annotated[Session, Depends(get_session)]
Layout = Annotated[DataLayout, Depends(get_layout)]

LIST_PATH = "/output-templates"
ACTIVE = "output_templates"
TEMPLATE_NOT_FOUND = N_("Şablon bulunamadı")
FILE_NOT_FOUND = N_("Şablon dosyası bulunamadı")
PAGE_NOT_FOUND = N_("Sayfa görüntüsü bulunamadı")
NAME_TAKEN = N_("Bu adla bir şablon zaten var; şablon adı benzersiz olmalı.")
NAME_TAKEN_ARCHIVED = N_(
    "Bu adla arşivde bir şablon var; şablon adı benzersiz olmalı. Arşivdekini geri alabilirsiniz."
)
DUPLICATE_FILE = N_("Bu dosya zaten şablon olarak yüklenmiş.")
ARCHIVED_NOT_EXAMINED = N_("Arşivdeki şablon incelenmez; önce arşivden geri alın.")
EXAMINING_LABEL = N_("İnceleniyor")
# 15.1.2: inceleme haritası üretmediyse listede ve sayfada görünen sebep.
EXAMINE_ERROR_LABELS = {
    ExamineError.PROVIDER_UNAVAILABLE.value: N_("İncelenmedi: yapay zekâ ayarlı değil"),
    ExamineError.INVALID_RESPONSE.value: N_("İncelenemedi: yanıt alan haritası şemasına uymadı"),
    ExamineError.PROVIDER_ERROR.value: N_("İncelenemedi: yapay zekâ çağrısı tamamlanamadı"),
    ExamineError.NO_PAGES.value: N_("İncelenemedi: sayfa görüntüsü bulunamadı"),
}
EXAMINE_ERROR_FALLBACK = N_("İncelenemedi")
STATUS_LABELS = {
    OutputTemplateStatus.DRAFT.value: N_("Taslak"),
    OutputTemplateStatus.READY.value: N_("Hazır"),
    OutputTemplateStatus.ARCHIVED.value: N_("Arşivde"),
}
# Durum rozetinin sınıfı (`docs/ARAYUZ-STANDARDI.md` §3: `.status-badge` + durum sınıfı).
STATUS_BADGES = {
    OutputTemplateStatus.DRAFT.value: "status-open",
    OutputTemplateStatus.READY.value: "status-active",
    OutputTemplateStatus.ARCHIVED.value: "status-archived",
}
PDF_MEDIA_TYPE = "application/pdf"
JPEG_MEDIA_TYPE = "image/jpeg"
FILE_HEADERS = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}
FORM_TEXT_LIMIT = 1000


def provider_available(settings: Annotated[Settings, Depends(get_settings)]) -> bool:
    """İncelemenin (15.1.2) sağlayıcısı kurulabiliyor mu; çağrıyı işçi yapar, burada yalnız ayar
    denetlenir."""
    try:
        create_provider(settings)
    except ProviderConfigError:
        return False
    return True


ProviderAvailable = Annotated[bool, Depends(provider_available)]


def examine_error_label(code: str | None) -> str | None:
    """`examine_error` kodunun gösterilen sebebi; kod yoksa `None`."""
    if not code:
        return None
    return EXAMINE_ERROR_LABELS.get(code, EXAMINE_ERROR_FALLBACK)


@dataclass(frozen=True, slots=True)
class TemplateFormValues:
    """Yükleme formunda gösterilen değerler (reddedilen form girilenlerle yeniden çizilir)."""

    name: str = ""
    description: str = ""


@dataclass(frozen=True, slots=True)
class StateLink:
    """Durum süzgecinin bir sekmesi (`nav.states`)."""

    key: str
    label: str
    href: str
    count: int
    current: bool


def _template_or_404(session: Session, template_id: int) -> OutputTemplate:
    try:
        return get_template(session, template_id)
    except TemplateNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, TEMPLATE_NOT_FOUND) from None


def _template_redirect(template_id: int, key: str, **params: object) -> RedirectResponse:
    response = RedirectResponse(f"{LIST_PATH}/{template_id}", status.HTTP_303_SEE_OTHER)
    flash(response, key, **params)
    return response


def _limits() -> dict[str, int]:
    return {"name": NAME_MAX_LENGTH, "description": DESCRIPTION_MAX_LENGTH}


def _state_links(session: Session, selected: str | None) -> list[StateLink]:
    counts = status_counts(session)
    active = counts[OutputTemplateStatus.DRAFT.value] + counts[OutputTemplateStatus.READY.value]
    links = [StateLink("", N_("Etkin"), LIST_PATH, active, selected is None)]
    links += [
        StateLink(value, label, f"{LIST_PATH}?status={value}", counts[value], selected == value)
        for value, label in STATUS_LABELS.items()
    ]
    return links


def _new_page(
    request: Request,
    user: PanelUser,
    form: TemplateFormValues,
    *,
    problems: dict[str, list[str]] | None = None,
    duplicate_id: int | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    feedback = render(TEMPLATE_DUPLICATE) if duplicate_id is not None else None
    return render_page(
        request,
        "output_template.html",
        user=user,
        active=ACTIVE,
        status_code=status_code,
        feedback=feedback,
        template=None,
        form=form,
        problems=problems or {},
        duplicate_id=duplicate_id,
        limits=_limits(),
    )


@router.get(LIST_PATH, response_class=HTMLResponse)
def templates_page(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    template_status: Annotated[str | None, Query(alias="status", max_length=16)] = None,
) -> HTMLResponse:
    selected = template_status if template_status in STATUS_LABELS else None
    response = render_page(
        request,
        "output_templates.html",
        user=user,
        active=ACTIVE,
        entry=MENU_BY_KEY[ACTIVE],
        templates=list_templates(session, status=selected),
        states=_state_links(session, selected),
        selected=selected,
        status_labels=STATUS_LABELS,
        status_badges=STATUS_BADGES,
        examine_error_label=examine_error_label,
        examining_label=EXAMINING_LABEL,
    )
    # Okuma işlemi de SQLite'ta yazma kilidini tutar (`app.db.session`).
    session.rollback()
    return response


# `/output-templates/{template_id}`'dan önce kayıtlı olmalı: yol tek parçadır.
@router.get(f"{LIST_PATH}/new", response_class=HTMLResponse, dependencies=WRITER_ONLY)
def new_template_page(request: Request, user: CurrentUser) -> HTMLResponse:
    return _new_page(request, user, TemplateFormValues())


@router.post(LIST_PATH, response_class=HTMLResponse)
async def upload_template(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    settings: Annotated[Settings, Depends(get_settings)],
    available: ProviderAvailable,
) -> Response:
    # Form elle okunur: dosya seçilmeden gönderilen formda tarayıcı adı boş tek bir parça yollar,
    # Starlette onu dosya değil düz alan sayar (`app.web.routers.upload_page` ile aynı sebep).
    async with request.form() as data:
        name = str(data.get("name") or "")[:FORM_TEXT_LIMIT]
        description = str(data.get("description") or "")[:FORM_TEXT_LIMIT]
        upload = data.get("file")
        content = (
            await upload.read()
            if isinstance(upload, StarletteUploadFile) and upload.filename
            else None
        )
    form = TemplateFormValues(name=name, description=description)
    try:
        template = create_template(
            session,
            layout,
            settings,
            name=name,
            description=description,
            content=content,
            actor=user.username,
        )
        queued = request_examination(session, template, provider_available=available)
        session.commit()
    except TemplateFormError as exc:
        session.rollback()
        return _new_page(
            request,
            user,
            form,
            problems=exc.problems,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    except TemplateNameTakenError as exc:
        session.rollback()
        return _new_page(
            request,
            user,
            form,
            problems={"name": [NAME_TAKEN_ARCHIVED if exc.archived else NAME_TAKEN]},
            status_code=status.HTTP_409_CONFLICT,
        )
    except DuplicateTemplateError as exc:
        session.rollback()
        return _new_page(
            request,
            user,
            form,
            problems={"file": [DUPLICATE_FILE]},
            duplicate_id=exc.template_id,
            status_code=status.HTTP_409_CONFLICT,
        )
    key = TEMPLATE_UPLOADED if queued else TEMPLATE_UPLOADED_UNEXAMINED
    return _template_redirect(template.id, key, count=template.page_count)


@router.get(f"{LIST_PATH}/{{template_id}}", response_class=HTMLResponse)
def template_page(
    template_id: int, request: Request, user: CurrentUser, session: DbSession
) -> HTMLResponse:
    template = _template_or_404(session, template_id)
    response = render_page(
        request,
        "output_template.html",
        user=user,
        active=ACTIVE,
        template=template,
        field_count=field_count(template),
        status_labels=STATUS_LABELS,
        status_badges=STATUS_BADGES,
        pages=range(template.page_count),
        latest_map=template.maps[-1] if template.maps else None,
        examining=is_examining(template),
        examine_error=examine_error_label(template.examine_error),
    )
    session.rollback()
    return response


def _original_path(layout: DataLayout, template: OutputTemplate) -> Path | None:
    if not template.file_path:
        return None
    try:
        path = layout.resolve(template.file_path)
    except ValueError:
        return None
    return path if path.is_file() else None


def _serve_original(
    session: Session,
    layout: DataLayout,
    template_id: int,
    *,
    user: PanelUser,
    action: AccessAction,
    disposition: str,
) -> FileResponse:
    """Şablonun orijinalini olduğu gibi sunar (K10, K17); erişim logu sunmadan **önce** yazılır ve
    commit edilir — log yazılamazsa dosya gitmez (10.9.2). Dosyası yoksa 404, kayıt düşmez."""
    template = _template_or_404(session, template_id)
    path = _original_path(layout, template)
    if path is None:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, FILE_NOT_FOUND)
    filename = f"{template.file_label}.pdf"
    record_access(session, user_id=user.id, template_id=template.id, action=action)
    session.commit()
    return FileResponse(
        path,
        media_type=PDF_MEDIA_TYPE,
        filename=filename,
        content_disposition_type=disposition,
        headers=FILE_HEADERS,
    )


@router.get(f"{LIST_PATH}/{{template_id}}/file")
def open_template(
    template_id: int, user: CurrentUser, session: DbSession, layout: Layout
) -> FileResponse:
    """15.1.4 — orijinali tarayıcıda açar (sayfa bağlantıyı yeni sekmede açtırır); `view` kaydı."""
    return _serve_original(
        session, layout, template_id, user=user, action=AccessAction.VIEW, disposition="inline"
    )


@router.get(f"{LIST_PATH}/{{template_id}}/download")
def download_template(
    template_id: int, user: CurrentUser, session: DbSession, layout: Layout
) -> FileResponse:
    """15.1.4 — orijinali K8 etiketli adla indirtir; `download` kaydı."""
    return _serve_original(
        session,
        layout,
        template_id,
        user=user,
        action=AccessAction.DOWNLOAD,
        disposition="attachment",
    )


@router.get(f"{LIST_PATH}/{{template_id}}/pages/{{page_index}}")
def template_page_image(
    template_id: int, page_index: int, session: DbSession, layout: Layout
) -> FileResponse:
    """Önizleme görüntüsü (liste küçük resmi ve şablon sayfası); erişim kaydı yazılmaz."""
    template = _template_or_404(session, template_id)
    session.rollback()
    if not 0 <= page_index < template.page_count:
        raise HTTPException(status.HTTP_404_NOT_FOUND, PAGE_NOT_FOUND)
    path = layout.template_page_image_path(template.id, page_index)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, PAGE_NOT_FOUND)
    return FileResponse(path, media_type=JPEG_MEDIA_TYPE, headers=FILE_HEADERS)


def _set_archived(
    session: Session, template_id: int, archived: bool, user: PanelUser
) -> RedirectResponse:
    try:
        set_template_archived(session, template_id, archived, actor=user.username)
        session.commit()
    except TemplateNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, TEMPLATE_NOT_FOUND) from None
    return _template_redirect(template_id, TEMPLATE_ARCHIVED if archived else TEMPLATE_RESTORED)


@router.post(f"{LIST_PATH}/{{template_id}}/archive")
def archive_template(template_id: int, user: CurrentUser, session: DbSession) -> RedirectResponse:
    return _set_archived(session, template_id, True, user)


@router.post(f"{LIST_PATH}/{{template_id}}/restore")
def restore_template(template_id: int, user: CurrentUser, session: DbSession) -> RedirectResponse:
    return _set_archived(session, template_id, False, user)


@router.post(f"{LIST_PATH}/{{template_id}}/examine")
def reexamine_template(
    template_id: int, user: CurrentUser, session: DbSession, available: ProviderAvailable
) -> RedirectResponse:
    """15.1.2 — şablonu yeniden incelemeye koyar (tek adım); sonuç yeni harita sürümüdür."""
    template = _template_or_404(session, template_id)
    try:
        queued = request_examination(session, template, provider_available=available)
    except TemplateArchivedError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, ARCHIVED_NOT_EXAMINED) from None
    session.commit()
    key = TEMPLATE_EXAMINE_REQUESTED if queued else TEMPLATE_EXAMINE_UNAVAILABLE
    return _template_redirect(template_id, key)
