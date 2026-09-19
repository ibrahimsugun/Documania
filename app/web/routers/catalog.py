"""Katalog yönetim ekranı (PRD 11.1.1, 11.1.2, 11.1.3): Belge Türleri.

- `GET /document-types` bütün türleri (pasifler dahil) listeler; her satırdan düzenlenir,
  pasifleştirilir ya da yeniden etkinleştirilir. `GET /document-types/new` + `POST
  /document-types` tür oluşturur; `GET /document-types/{slug}` (form) + `POST
  /document-types/{slug}` düzenler (`slug` değişmez); `POST /document-types/{slug}/deactivate`
  ve `.../activate` pasifleştirir/etkinleştirir. **Silme yok** (K16).
- Form katalog sözleşmesinden geçer (`app.catalog.form`, 11.1.2): Direkt türde dönüşüm listesi
  boş, `front_back` türde sayfa aralığı 2, analiz edilmeyen türde zorunlu alan yok. Reddedilen
  form 422 ile, girilen değerler ve alan başına mesajla yeniden çizilir; hiçbir şey yazılmaz.
- `acceptance_criteria` (11.1.3) formda madde madde düzenlenir: HTMX'li `POST
  /document-types/criteria/add` ve `.../remove` yalnız madde listesi parçasını yeniler
  (kaydetmez); JavaScript kapalıyken formun sonundaki boş madde alanı ve boşaltılan maddenin
  kaydedilmemesi aynı işi görür. Kayıt her analizde veritabanından baştan okunur
  (`export_catalog`): değişiklik **bir sonraki analizde** geçerli olur — süren analiz ve donmuş
  plan (K9) etkilenmez.
- Bu ekran belge içeriğine dokunmaz (K17); kaynak `known_document_types`'tır, `catalog.yaml`
  yazılmaz.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.catalog import (
    Conversion,
    FileType,
    OutputFormat,
    Sides,
    TypeExistsError,
    TypeForm,
    TypeFormError,
    TypeNotFoundError,
    build_entry,
    create_type,
    list_types,
    load_record,
    record_problems,
    set_type_active,
    update_type,
)
from app.db.session import get_session
from app.web.auth import PanelUser, require_panel_user
from app.web.templating import MENU_BY_KEY, render_page

router = APIRouter(tags=["catalog"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]
DbSession = Annotated[Session, Depends(get_session)]

LIST_PATH = "/document-types"
TYPE_NOT_FOUND = "Belge türü bulunamadı"
SLUG_TAKEN = "Bu slug'la bir tür zaten var; slug benzersiz olmalı ve sonradan değişmez"

FILE_TYPE_LABELS = {
    FileType.PDF: "PDF",
    FileType.JPEG: "JPEG",
    FileType.PNG: "PNG",
    FileType.DOC: "Word (doc)",
    FileType.DOCX: "Word (docx)",
    FileType.XLS: "Excel (xls)",
    FileType.XLSX: "Excel (xlsx)",
}
SIDES_LABELS = {Sides.SINGLE: "Tek yüz", Sides.FRONT_BACK: "Ön ve arka yüz"}
CONVERSION_LABELS = {
    Conversion.MERGE: "Sayfaları birleştir",
    Conversion.WRAP_IMAGE: "Görüntüyü PDF'e sar",
    Conversion.EXTRACT_IMAGE: "Gömülü görüntüyü çıkar",
    Conversion.RENDER_IMAGE: "Sayfayı görüntüye çevir",
}
OUTPUT_FORMAT_LABELS = {
    OutputFormat.KEEP: "Kaynağın biçimini koru",
    OutputFormat.PDF: "PDF",
    OutputFormat.JPEG: "JPEG",
}
NOTICES = {
    "created": "Tür oluşturuldu.",
    "updated": "Tür güncellendi. Değişiklik bir sonraki analizden itibaren geçerlidir.",
    "deactivated": "Tür pasifleştirildi: yeni belgelere atanmaz.",
    "activated": "Tür yeniden etkinleştirildi.",
}


def type_form(
    # Alan adı `slug`; yol parametresiyle (`/document-types/{slug}`) karışmasın diye takma adla.
    type_slug: Annotated[str, Form(alias="slug")] = "",
    name: Annotated[str, Form()] = "",
    file_label: Annotated[str, Form()] = "",
    country: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    expected_file_types: Annotated[list[str] | None, Form()] = None,
    pages_min: Annotated[str, Form()] = "",
    pages_max: Annotated[str, Form()] = "",
    sides: Annotated[str, Form()] = "",
    direct: Annotated[str | None, Form()] = None,
    analyze: Annotated[str | None, Form()] = None,
    required_fields: Annotated[str, Form()] = "",
    allowed_conversions: Annotated[list[str] | None, Form()] = None,
    output_format: Annotated[str, Form()] = "",
    acceptance_criteria: Annotated[list[str] | None, Form()] = None,
    prompt_description: Annotated[str, Form()] = "",
) -> TypeForm:
    """Formun kayıt alanları. Başka form alanı okunmaz: `active` ve `photo_rules` bu formdan
    değişmez. İşaret kutusu (`direct`, `analyze`) gönderilmişse işaretlidir."""
    return TypeForm(
        slug=type_slug,
        name=name,
        file_label=file_label,
        country=country,
        description=description,
        expected_file_types=tuple(expected_file_types or ()),
        pages_min=pages_min,
        pages_max=pages_max,
        sides=sides,
        direct=direct is not None,
        analyze=analyze is not None,
        required_fields=required_fields,
        allowed_conversions=tuple(allowed_conversions or ()),
        output_format=output_format,
        acceptance_criteria=tuple(acceptance_criteria or ()),
        prompt_description=prompt_description,
    )


SubmittedForm = Annotated[TypeForm, Depends(type_form)]


def _form_page(
    request: Request,
    user: PanelUser,
    form: TypeForm,
    *,
    slug: str | None,
    problems: dict[str, list[str]] | None = None,
    current_problems: tuple[str, ...] = (),
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Tür formunu çizer. `slug` düzenlenen türdür (yeni türde `None`); madde listesinin sonuna
    JavaScript'siz ekleme için boş bir alan konur."""
    return render_page(
        request,
        "catalog_form.html",
        user=user,
        active="document_types",
        status_code=status_code,
        form=form,
        is_new=slug is None,
        slug=slug,
        problems=problems or {},
        current_problems=current_problems,
        criteria=[*form.acceptance_criteria, ""],
        file_types=FILE_TYPE_LABELS,
        sides_options=SIDES_LABELS,
        conversions=CONVERSION_LABELS,
        output_formats=OUTPUT_FORMAT_LABELS,
    )


def _redirect(notice: str, slug: str) -> RedirectResponse:
    return RedirectResponse(
        f"{LIST_PATH}?{urlencode({'notice': notice, 'slug': slug})}", status.HTTP_303_SEE_OTHER
    )


@router.get(LIST_PATH, response_class=HTMLResponse)
def catalog_page(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    notice: Annotated[str | None, Query(max_length=32)] = None,
    slug: Annotated[str | None, Query(max_length=64)] = None,
) -> HTMLResponse:
    types = list_types(session)
    named = {item.slug: item.name for item in types}
    notice_text = NOTICES.get(notice or "")
    if notice_text and slug in named:
        notice_text = f"{named[slug]}: {notice_text}"
    return render_page(
        request,
        "catalog.html",
        user=user,
        active="document_types",
        entry=MENU_BY_KEY["document_types"],
        types=types,
        notice_text=notice_text,
        sides_labels=SIDES_LABELS,
    )


@router.get(f"{LIST_PATH}/new", response_class=HTMLResponse)
def new_type_page(request: Request, user: CurrentUser) -> HTMLResponse:
    return _form_page(request, user, TypeForm(), slug=None)


@router.post(LIST_PATH, response_class=HTMLResponse)
def create_type_endpoint(
    request: Request, user: CurrentUser, session: DbSession, form: SubmittedForm
) -> Response:
    try:
        entry = build_entry(form)
    except TypeFormError as exc:
        return _form_page(
            request,
            user,
            form,
            slug=None,
            problems=exc.problems,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    try:
        create_type(session, entry)
        session.commit()
    except TypeExistsError:
        session.rollback()
        return _form_page(
            request,
            user,
            form,
            slug=None,
            problems={"slug": [SLUG_TAKEN]},
            status_code=status.HTTP_409_CONFLICT,
        )
    return _redirect("created", entry.slug)


@router.get(f"{LIST_PATH}/{{slug}}", response_class=HTMLResponse)
def type_page(slug: str, request: Request, user: CurrentUser, session: DbSession) -> HTMLResponse:
    try:
        record = load_record(session, slug)
    except TypeNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    # Kayıtlı tür §8.6'ya uymuyorsa (elle değiştirilmiş satır) form yine açılır; kaydetmek
    # onu düzeltir.
    return _form_page(
        request,
        user,
        TypeForm.from_record(record),
        slug=slug,
        current_problems=record_problems(record),
    )


@router.post(f"{LIST_PATH}/{{slug}}", response_class=HTMLResponse)
def update_type_endpoint(
    slug: str, request: Request, user: CurrentUser, session: DbSession, form: SubmittedForm
) -> Response:
    # Slug adresten gelir, formdan değil: değişmez (belgeler ve çıktı adları ona bağlı).
    form = replace(form, slug=slug)
    try:
        load_record(session, slug)
    except TypeNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    try:
        entry = build_entry(form)
    except TypeFormError as exc:
        return _form_page(
            request,
            user,
            form,
            slug=slug,
            problems=exc.problems,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    try:
        update_type(session, entry)
        session.commit()
    except TypeNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    return _redirect("updated", slug)


def _set_active(session: Session, slug: str, active: bool) -> RedirectResponse:
    try:
        set_type_active(session, slug, active)
        session.commit()
    except TypeNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    return _redirect("activated" if active else "deactivated", slug)


@router.post(f"{LIST_PATH}/{{slug}}/deactivate")
def deactivate_type(slug: str, session: DbSession) -> RedirectResponse:
    return _set_active(session, slug, False)


@router.post(f"{LIST_PATH}/{{slug}}/activate")
def activate_type(slug: str, session: DbSession) -> RedirectResponse:
    return _set_active(session, slug, True)


def _criteria_fragment(request: Request, user: PanelUser, items: list[str]) -> HTMLResponse:
    return render_page(request, "catalog_criteria.html", user=user, criteria=items)


@router.post(f"{LIST_PATH}/criteria/add", response_class=HTMLResponse)
def add_criterion(
    request: Request,
    user: CurrentUser,
    acceptance_criteria: Annotated[list[str] | None, Form()] = None,
) -> HTMLResponse:
    """Madde listesine boş bir madde ekler; kaydetmez (formun geri kalanı yerinde durur)."""
    return _criteria_fragment(request, user, [*(acceptance_criteria or ()), ""])


@router.post(f"{LIST_PATH}/criteria/remove", response_class=HTMLResponse)
def remove_criterion(
    request: Request,
    user: CurrentUser,
    index: Annotated[int, Form(ge=0)],
    acceptance_criteria: Annotated[list[str] | None, Form()] = None,
) -> HTMLResponse:
    """`index`teki maddeyi listeden çıkarır; kaydetmez."""
    items = list(acceptance_criteria or ())
    if index < len(items):
        del items[index]
    return _criteria_fragment(request, user, items)
