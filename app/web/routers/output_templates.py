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
- Şablon sayfası alan haritasını önizler (15.1.3): her sayfa görüntüsünün üstünde haritanın kutuları
  (SVG; koordinat normalize kutudan, sayfa görüntüsünün ölçüsüyle) ve kutu başına bir satır. İK son
  sürümde `text`/`date` kutusunun bağlı alanını açılır listeden seçer ya da "boş bırak" yapar;
  imza/kaşe/logo/fotoğraf/çerçeve kutusu seçimsizdir. `POST .../maps/{version}/approve` atamaları
  doğrular (`app.output_templates.approve`: bilinmeyen atama 422; bağlı kutu yoksa 422 ve sayfa
  seçimlerle yeniden çizilir; arada yeni sürüm gelmişse ya da şablon arşivdeyse 409), gerekirse yeni
  sürüm yazar ve şablonu hazır yapar. Tek adımlıdır (§D61); JavaScript'siz düz form gönderimidir.
  Kullanıcı yalnız onaylı haritayı salt okunur görür.

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
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.ai.provider import ProviderConfigError, create_provider
from app.ai.schemas import FILLABLE_KINDS, TemplateFieldMapError
from app.config import Settings, get_settings
from app.db.models import AccessAction, OutputTemplate, OutputTemplateMap, OutputTemplateStatus
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
from app.output_templates.approve import (
    UNASSIGNED,
    MapAssignmentError,
    MapNotFoundError,
    NothingBoundError,
    StaleMapError,
    approve_map,
    approved_map,
    field_map_of,
)
from app.output_templates.examine import (
    ExamineError,
    TemplateArchivedError,
    is_examining,
    request_examination,
)
from app.output_templates.labels import FIELD_LABELS
from app.storage import DataLayout
from app.web.access import record_access
from app.web.ai_runtime import ActiveAiSettings
from app.web.auth import WRITER_ONLY, PanelUser, require_panel_user
from app.web.feedback import (
    TEMPLATE_ARCHIVED,
    TEMPLATE_DUPLICATE,
    TEMPLATE_EXAMINE_REQUESTED,
    TEMPLATE_EXAMINE_UNAVAILABLE,
    TEMPLATE_MAP_APPROVED,
    TEMPLATE_MAP_APPROVED_EDITED,
    TEMPLATE_MAP_NOTHING_BOUND,
    TEMPLATE_MAP_UNCHANGED,
    TEMPLATE_RESTORED,
    TEMPLATE_UPLOADED,
    TEMPLATE_UPLOADED_UNEXAMINED,
    Toast,
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
# 15.1.3: kutu başına atamanın form alanı `source-<field_id>`.
SOURCE_PREFIX = "source-"
MAP_NOT_FOUND = N_("Alan haritasının bu sürümü yok.")
MAP_STALE = N_("Harita bu arada yeni bir sürüm aldı; son sürümü gözden geçirip yeniden onaylayın.")
ARCHIVED_NOT_APPROVED = N_("Arşivdeki şablonun haritası onaylanmaz; önce arşivden geri alın.")
MAP_ASSIGNMENT_INVALID = N_("Atama geçersiz: her doldurulacak kutu listedeki bir alana bağlanır.")
# §8.7 `source` seçenekleri (`app.output_templates.labels`); açılır listenin sırası budur.
SOURCE_LABELS = FIELD_LABELS
KIND_LABELS = {
    "text": N_("Metin"),
    "date": N_("Tarih"),
    "signature": N_("İmza"),
    "stamp": N_("Kaşe / mühür"),
    "logo": N_("Logo"),
    "photo": N_("Fotoğraf"),
    "decoration": N_("Çerçeve"),
}
# Sayfa görüntüsü okunamazsa kutular A4 oranlı bir tuvale çizilir.
FALLBACK_PAGE_SIZE = (1000, 1414)


def provider_available(settings: ActiveAiSettings) -> bool:
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


@dataclass(frozen=True, slots=True)
class MapBox:
    """Önizlemede bir kutu ve satırı (15.1.3). Koordinatlar sayfa görüntüsünün pikselidir."""

    number: int
    field_id: str
    kind: str
    label_text: str | None
    source: str | None
    x: float
    y: float
    width: float
    height: float

    @property
    def fillable(self) -> bool:
        return self.kind in FILLABLE_KINDS

    @property
    def state(self) -> str:
        """Kutunun görünüm sınıfı: bağlı, boş bırakılmış ya da doldurulamaz."""
        if not self.fillable:
            return "map-box-locked"
        return "map-box-unassigned" if self.source == UNASSIGNED else "map-box-bound"


@dataclass(frozen=True, slots=True)
class MapPage:
    """Kutusu olan bir sayfa; `width`/`height` önizleme görüntüsünün ölçüsü (SVG `viewBox`)."""

    index: int
    width: int
    height: int
    boxes: list[MapBox]

    @property
    def label_size(self) -> float:
        return round(max(self.width, self.height) * 0.018, 1)


@dataclass(frozen=True, slots=True)
class MapView:
    """Önizlenen sürüm: sayfalar ve düzenlenebilir mi."""

    row: OutputTemplateMap
    pages: list[MapPage]
    editable: bool

    @property
    def boxes(self) -> list[MapBox]:
        return [box for page in self.pages for box in page.boxes]

    @property
    def fillable_count(self) -> int:
        return sum(1 for box in self.boxes if box.fillable)

    @property
    def bound_count(self) -> int:
        return sum(1 for box in self.boxes if box.state == "map-box-bound")


def _page_size(layout: DataLayout, template_id: int, index: int) -> tuple[int, int]:
    # Pillow yalnız ölçer (MASTER-PROMPT §4); görüntü değişmez.
    try:
        with Image.open(layout.template_page_image_path(template_id, index)) as image:
            return image.size
    except (OSError, UnidentifiedImageError, ValueError):
        return FALLBACK_PAGE_SIZE


def _map_view(
    layout: DataLayout,
    template: OutputTemplate,
    row: OutputTemplateMap | None,
    *,
    editable: bool,
    assignments: dict[str, str] | None = None,
) -> MapView | None:
    """Sürümün önizlemesi; `assignments` reddedilen formun seçimleridir (yeniden çizim). Kutu
    koordinatları haritadan değişmeden gelir, yalnız sayfa ölçüsüyle çarpılır."""
    if row is None:
        return None
    try:
        fields = field_map_of(row, page_count=template.page_count).fields
    except TemplateFieldMapError:
        return None
    chosen = assignments or {}
    pages: list[MapPage] = []
    for index in range(template.page_count):
        on_page = [(n, item) for n, item in enumerate(fields, start=1) if item.page == index]
        if not on_page:
            continue
        width, height = _page_size(layout, template.id, index)
        boxes = [
            MapBox(
                number=number,
                field_id=item.field_id,
                kind=item.kind,
                label_text=item.label_text,
                source=chosen.get(item.field_id, item.source) if item.source else None,
                x=round(item.box[0] * width, 1),
                y=round(item.box[1] * height, 1),
                width=round((item.box[2] - item.box[0]) * width, 1),
                height=round((item.box[3] - item.box[1]) * height, 1),
            )
            for number, item in on_page
        ]
        pages.append(MapPage(index, width, height, boxes))
    return MapView(row, pages, editable)


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


def _template_response(
    request: Request,
    user: PanelUser,
    template: OutputTemplate,
    layout: DataLayout,
    *,
    assignments: dict[str, str] | None = None,
    feedback: Toast | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    latest = template.maps[-1] if template.maps else None
    approved = approved_map(template)
    # İK son sürümü düzenler (arşivde salt okunur görür); Kullanıcı yalnız onaylı haritayı görür.
    if user.can_write:
        editable = template.status != OutputTemplateStatus.ARCHIVED.value
        preview = _map_view(layout, template, latest, editable=editable, assignments=assignments)
    else:
        preview = _map_view(layout, template, approved, editable=False)
    return render_page(
        request,
        "output_template.html",
        user=user,
        active=ACTIVE,
        status_code=status_code,
        feedback=feedback,
        template=template,
        field_count=field_count(template),
        status_labels=STATUS_LABELS,
        status_badges=STATUS_BADGES,
        pages=range(template.page_count),
        latest_map=latest,
        approved_map=approved,
        preview=preview,
        source_labels=SOURCE_LABELS,
        kind_labels=KIND_LABELS,
        examining=is_examining(template),
        examine_error=examine_error_label(template.examine_error),
    )


@router.get(f"{LIST_PATH}/{{template_id}}", response_class=HTMLResponse)
def template_page(
    template_id: int, request: Request, user: CurrentUser, session: DbSession, layout: Layout
) -> HTMLResponse:
    template = _template_or_404(session, template_id)
    response = _template_response(request, user, template, layout)
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


@router.post(f"{LIST_PATH}/{{template_id}}/maps/{{version}}/approve", response_class=HTMLResponse)
async def approve_template_map(
    template_id: int,
    version: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
) -> Response:
    """15.1.3 — son sürümü formdaki atamalarla onaylar (tek adım); şablon hazır olur."""
    async with request.form() as data:
        assignments = {
            key.removeprefix(SOURCE_PREFIX): value[:FORM_TEXT_LIMIT]
            for key, value in data.multi_items()
            if key.startswith(SOURCE_PREFIX) and isinstance(value, str)
        }
    template = _template_or_404(session, template_id)
    try:
        approval = approve_map(session, template, version, assignments, actor=user.username)
    except MapNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, MAP_NOT_FOUND) from None
    except TemplateArchivedError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, ARCHIVED_NOT_APPROVED) from None
    except StaleMapError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, MAP_STALE) from None
    except MapAssignmentError:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, MAP_ASSIGNMENT_INVALID) from None
    except NothingBoundError:
        session.rollback()
        template = _template_or_404(session, template_id)
        response = _template_response(
            request,
            user,
            template,
            layout,
            assignments=assignments,
            feedback=render(TEMPLATE_MAP_NOTHING_BOUND),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
        session.rollback()
        return response
    session.commit()
    if approval.already_approved:
        return _template_redirect(template_id, TEMPLATE_MAP_UNCHANGED)
    if approval.created:
        return _template_redirect(
            template_id,
            TEMPLATE_MAP_APPROVED_EDITED,
            count=approval.changed_count,
            version=approval.map.version,
        )
    return _template_redirect(template_id, TEMPLATE_MAP_APPROVED, version=approval.map.version)
