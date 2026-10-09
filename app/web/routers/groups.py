"""Belge Grupları ekranı (PRD 14.1.1, 14.1.2; PLAN.md §C89).

- `GET /document-groups` grupları listeler: ad, açıklama, kalem sayısı, açık paket sayısı, durum.
  Varsayılan yalnız arşivsiz gruplar; `?archived=1` arşivdekileri de gösterir.
- `GET /document-groups/new` + `POST /document-groups` grup açar (ad tekil — 00.4.2
  sadeleştirmesiyle, harf büyüklüğü yok sayılır; çakışma 409, kural dışı değer 422 ile form yeniden
  çizilir).
- `GET /document-groups/{id}` grubun sayfasıdır: ad/açıklama formu (`POST /document-groups/{id}`),
  kalem tablosu, kalem ekleme (`POST /document-groups/{id}/items`: etiket seçicisi katalogdaki
  etiketleri tür sayısıyla, tür seçicisi katalogdaki türleri listeler; zorunlu ya da isteğe bağlı;
  not ≤ 120), kalem kaldırma (`POST .../items/{item_id}/remove`), arşivleme ve geri alma
  (`POST .../archive`, `.../restore`). Sayfa kalem değişikliğinin kaç açık pakette hemen geçerli
  olacağını söyler (`open_package_count`, 14.2).
- Kalem eklenince ya da kaldırılınca grubun paketleri aynı işlemde yeniden değerlendirilir
  (`app.groups.refresh_group_packages`); ad, açıklama ya da kalem değişikliğinin commit'inden sonra
  grubun paketi olan çalışanların `profil.md`'si yeniden üretilir (09.1.1, 14.3.1).
- Hepsi tek adımlıdır (§D61-b: dosya taşımaz, eşleştirmeyi değiştirmez, geri alınabilir) ve
  `GROUP_CHANGED` olayını kullanıcı adıyla yazar. **Silme yok** (R11): grup arşivlenir, kalem
  kaldırılır ve satırı kalır. Ekran belge içeriğine dokunmaz (K17).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentGroup, DocumentGroupItem, Employee, EmployeePackage, GroupItemKind
from app.db.session import get_session
from app.groups import (
    DESCRIPTION_MAX_LENGTH,
    NAME_MAX_LENGTH,
    NOTE_MAX_LENGTH,
    DuplicateGroupItemError,
    GroupFormError,
    GroupItemNotFoundError,
    GroupNameTakenError,
    GroupNotFoundError,
    LabelChoice,
    TypeChoice,
    active_items,
    add_item,
    count_archived_groups,
    create_group,
    get_group,
    label_choices,
    list_groups,
    normalize_label,
    open_package_count,
    remove_item,
    set_group_archived,
    type_choices,
    update_group,
)
from app.i18n import N_, Translatable
from app.profiles import write_profile
from app.storage import DataLayout
from app.web.auth import WRITER_ONLY, PanelUser, require_panel_user
from app.web.routers.uploads import get_layout
from app.web.templating import MENU_BY_KEY, render_page

router = APIRouter(tags=["groups"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]
DbSession = Annotated[Session, Depends(get_session)]
Layout = Annotated[DataLayout, Depends(get_layout)]

LIST_PATH = "/document-groups"
GROUP_NOT_FOUND = N_("Belge grubu bulunamadı")
ITEM_NOT_FOUND = N_("Kalem bu grupta yok ya da zaten kaldırılmış")
NAME_TAKEN = N_("Bu adla bir grup zaten var; grup adı benzersiz olmalı.")
NAME_TAKEN_ARCHIVED = N_(
    "Bu adla arşivde bir grup var; grup adı benzersiz olmalı. Arşivdekini geri alabilirsiniz."
)
DUPLICATE_ITEM = N_("Bu kalem grupta zaten var; aynı etiket ya da tür bir grupta bir kez yer alır.")
NOTICES = {
    "created": N_("Grup oluşturuldu. Şimdi kalemlerini ekleyin."),
    "updated": N_("Grubun adı ve açıklaması güncellendi."),
    "unchanged": N_("Değişiklik yok."),
    "item_added": N_("Kalem eklendi."),
    "item_removed": N_("Kalem kaldırıldı."),
    "archived": N_("Grup arşivlendi: yeni paket tanımlanamaz, açık paketler sürer."),
    "restored": N_("Grup arşivden geri alındı."),
}
MATCH_KIND_LABELS = {
    GroupItemKind.LABEL.value: N_("Dosya etiketi"),
    GroupItemKind.TYPE.value: N_("Belge türü"),
}

# Form sınırı yalnız aşırı girdiye karşıdır; uzunluk kuralını servis alan başına mesajla bildirir.
FORM_TEXT_LIMIT = 1000
GroupName = Annotated[str, Form(max_length=FORM_TEXT_LIMIT)]
GroupDescription = Annotated[str | None, Form(max_length=FORM_TEXT_LIMIT)]


@dataclass(frozen=True, slots=True)
class GroupFormValues:
    """Grup formunda gösterilen değerler (reddedilen form girilenlerle yeniden çizilir)."""

    name: str = ""
    description: str = ""


@dataclass(frozen=True, slots=True)
class ItemFormValues:
    """Kalem ekleme formunda gösterilen değerler; `match_kind` hangi formun gönderildiğidir."""

    match_kind: str = ""
    file_label: str = ""
    type_slug: str = ""
    required: bool = True
    note: str = ""


@dataclass(frozen=True, slots=True)
class ItemView:
    """Kalem tablosunun bir satırı."""

    id: int
    position: int
    match_kind: str
    kind_label: str
    title: str
    detail: str
    required: bool
    note: str | None
    removed_at: datetime | None
    removed_by: str | None


def _notice(notice: str | None) -> str | None:
    return NOTICES.get(notice or "")


def _group_redirect(group_id: int, notice: str) -> RedirectResponse:
    return RedirectResponse(f"{LIST_PATH}/{group_id}?notice={notice}", status.HTTP_303_SEE_OTHER)


def _write_package_profiles(session: Session, layout: DataLayout, group_id: int) -> None:
    """09.1.1, 14.3.1: grubun paketi olan çalışanların `profil.md`'si grubun commit edilmiş hâlini
    (ad, kalemler, paket durumu) gösterir."""
    employees = session.scalars(
        select(Employee)
        .where(
            Employee.id.in_(
                select(EmployeePackage.employee_id).where(EmployeePackage.group_id == group_id)
            )
        )
        .order_by(Employee.id)
    )
    for employee in employees:
        write_profile(session, layout, employee)
    session.rollback()


def _group_or_404(session: Session, group_id: int) -> DocumentGroup:
    try:
        return get_group(session, group_id)
    except GroupNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GROUP_NOT_FOUND) from None


def _item_view(
    item: DocumentGroupItem,
    labels: dict[str, LabelChoice],
    types: dict[str, TypeChoice],
) -> ItemView:
    if item.match_kind == GroupItemKind.LABEL:
        choice = labels.get(normalize_label(item.file_label))
        count = choice.type_count if choice else 0
        title = item.file_label or ""
        detail = Translatable(
            N_("Ülkeden bağımsız: bu etiketli {count} türden herhangi biri karşılar"), count=count
        )
    else:
        found = types.get(item.type_slug or "")
        title = found.name if found else item.type_slug or ""
        country = f" · {found.country}" if found and found.country else ""
        detail = Translatable(
            N_("Yalnız bu tür karşılar{country} · {slug}"), country=country, slug=item.type_slug
        )
    return ItemView(
        id=item.id,
        position=item.position,
        match_kind=item.match_kind,
        kind_label=MATCH_KIND_LABELS.get(item.match_kind, item.match_kind),
        title=title,
        detail=detail,
        required=item.required,
        note=item.note,
        removed_at=item.removed_at,
        removed_by=item.removed_by,
    )


def _new_page(
    request: Request,
    user: PanelUser,
    form: GroupFormValues,
    *,
    problems: dict[str, list[str]] | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    return render_page(
        request,
        "group.html",
        user=user,
        active="document_groups",
        status_code=status_code,
        group=None,
        form=form,
        problems=problems or {},
        limits=_limits(),
    )


def _limits() -> dict[str, int]:
    return {
        "name": NAME_MAX_LENGTH,
        "description": DESCRIPTION_MAX_LENGTH,
        "note": NOTE_MAX_LENGTH,
    }


def _group_page(
    request: Request,
    user: PanelUser,
    session: Session,
    group: DocumentGroup,
    *,
    form: GroupFormValues | None = None,
    problems: dict[str, list[str]] | None = None,
    item_form: ItemFormValues | None = None,
    item_problems: dict[str, list[str]] | None = None,
    notice_text: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    labels = label_choices(session)
    types = type_choices(session)
    # Var olan kalem arşivli türe (11.1.6) bağlı olabilir: gösterim arşivlileri de bilir, seçici
    # bilmez.
    label_map = {choice.key: choice for choice in label_choices(session, include_archived=True)}
    type_map = {choice.slug: choice for choice in type_choices(session, include_archived=True)}
    items = active_items(group)
    removed = [item for item in group.items if item.removed_at is not None]
    response = render_page(
        request,
        "group.html",
        user=user,
        active="document_groups",
        status_code=status_code,
        group=group,
        form=form or GroupFormValues(name=group.name, description=group.description or ""),
        problems=problems or {},
        item_form=item_form or ItemFormValues(),
        item_problems=item_problems or {},
        items=[_item_view(item, label_map, type_map) for item in items],
        removed_items=[_item_view(item, label_map, type_map) for item in removed],
        label_choices=labels,
        type_choices=types,
        open_packages=open_package_count(session, group.id),
        notice_text=notice_text,
        limits=_limits(),
    )
    # Okuma işlemi de SQLite'ta yazma kilidini tutar (`app.db.session`).
    session.rollback()
    return response


@router.get(LIST_PATH, response_class=HTMLResponse)
def groups_page(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    archived: Annotated[str | None, Query(max_length=1)] = None,
) -> HTMLResponse:
    include_archived = archived == "1"
    groups = list_groups(session, include_archived=include_archived)
    response = render_page(
        request,
        "groups.html",
        user=user,
        active="document_groups",
        entry=MENU_BY_KEY["document_groups"],
        groups=groups,
        include_archived=include_archived,
        archived_count=count_archived_groups(session),
    )
    session.rollback()
    return response


# `/document-groups/{group_id}`'dan önce kayıtlı olmalı: yol tek parçadır.
@router.get(f"{LIST_PATH}/new", response_class=HTMLResponse, dependencies=WRITER_ONLY)
def new_group_page(request: Request, user: CurrentUser) -> HTMLResponse:
    return _new_page(request, user, GroupFormValues())


@router.post(LIST_PATH, response_class=HTMLResponse)
def create_group_endpoint(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    name: GroupName,
    description: GroupDescription = None,
) -> Response:
    form = GroupFormValues(name=name, description=description or "")
    try:
        group = create_group(session, name=name, description=description, actor=user.username)
        session.commit()
    except GroupFormError as exc:
        session.rollback()
        return _new_page(
            request,
            user,
            form,
            problems=exc.problems,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    except GroupNameTakenError as exc:
        session.rollback()
        return _new_page(
            request,
            user,
            form,
            problems={"name": [NAME_TAKEN_ARCHIVED if exc.archived else NAME_TAKEN]},
            status_code=status.HTTP_409_CONFLICT,
        )
    return _group_redirect(group.id, "created")


@router.get(f"{LIST_PATH}/{{group_id}}", response_class=HTMLResponse)
def group_page(
    group_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    notice: Annotated[str | None, Query(max_length=32)] = None,
) -> HTMLResponse:
    group = _group_or_404(session, group_id)
    return _group_page(request, user, session, group, notice_text=_notice(notice))


@router.post(f"{LIST_PATH}/{{group_id}}", response_class=HTMLResponse)
def update_group_endpoint(
    group_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    name: GroupName,
    description: GroupDescription = None,
) -> Response:
    group = _group_or_404(session, group_id)
    form = GroupFormValues(name=name, description=description or "")
    try:
        changed = update_group(
            session, group.id, name=name, description=description, actor=user.username
        )
        session.commit()
    except GroupFormError as exc:
        session.rollback()
        return _group_page(
            request,
            user,
            session,
            group,
            form=form,
            problems=exc.problems,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    except GroupNameTakenError as exc:
        session.rollback()
        return _group_page(
            request,
            user,
            session,
            group,
            form=form,
            problems={"name": [NAME_TAKEN_ARCHIVED if exc.archived else NAME_TAKEN]},
            status_code=status.HTTP_409_CONFLICT,
        )
    if changed:
        _write_package_profiles(session, layout, group_id)
    return _group_redirect(group_id, "updated" if changed else "unchanged")


@router.post(f"{LIST_PATH}/{{group_id}}/items", response_class=HTMLResponse)
def add_item_endpoint(
    group_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    match_kind: Annotated[str, Form(max_length=16)],
    file_label: Annotated[str | None, Form(max_length=255)] = None,
    type_slug: Annotated[str | None, Form(max_length=64)] = None,
    required: Annotated[bool, Form()] = False,
    note: Annotated[str | None, Form(max_length=FORM_TEXT_LIMIT)] = None,
) -> Response:
    group = _group_or_404(session, group_id)
    item_form = ItemFormValues(
        match_kind=match_kind,
        file_label=file_label or "",
        type_slug=type_slug or "",
        required=required,
        note=note or "",
    )
    problems: dict[str, list[str]]
    try:
        add_item(
            session,
            group.id,
            match_kind=match_kind,
            file_label=file_label,
            type_slug=type_slug,
            required=required,
            note=note,
            actor=user.username,
        )
        session.commit()
    except GroupFormError as exc:
        problems, status_code = exc.problems, status.HTTP_422_UNPROCESSABLE_CONTENT
    except DuplicateGroupItemError:
        field_name = "file_label" if match_kind == GroupItemKind.LABEL else "type_slug"
        problems, status_code = {field_name: [DUPLICATE_ITEM]}, status.HTTP_409_CONFLICT
    else:
        _write_package_profiles(session, layout, group_id)
        return _group_redirect(group_id, "item_added")
    session.rollback()
    return _group_page(
        request,
        user,
        session,
        group,
        item_form=item_form,
        item_problems=problems,
        status_code=status_code,
    )


@router.post(f"{LIST_PATH}/{{group_id}}/items/{{item_id}}/remove")
def remove_item_endpoint(
    group_id: int, item_id: int, user: CurrentUser, session: DbSession, layout: Layout
) -> RedirectResponse:
    try:
        remove_item(session, group_id, item_id, actor=user.username)
        session.commit()
    except GroupNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, GROUP_NOT_FOUND) from None
    except GroupItemNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, ITEM_NOT_FOUND) from None
    _write_package_profiles(session, layout, group_id)
    return _group_redirect(group_id, "item_removed")


def _set_archived(
    session: Session, group_id: int, archived: bool, user: PanelUser
) -> RedirectResponse:
    try:
        set_group_archived(session, group_id, archived, actor=user.username)
        session.commit()
    except GroupNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, GROUP_NOT_FOUND) from None
    return _group_redirect(group_id, "archived" if archived else "restored")


@router.post(f"{LIST_PATH}/{{group_id}}/archive")
def archive_group(group_id: int, user: CurrentUser, session: DbSession) -> RedirectResponse:
    return _set_archived(session, group_id, True, user)


@router.post(f"{LIST_PATH}/{{group_id}}/restore")
def restore_group(group_id: int, user: CurrentUser, session: DbSession) -> RedirectResponse:
    return _set_archived(session, group_id, False, user)
