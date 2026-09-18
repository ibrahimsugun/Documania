"""Panel sayfaları ve ana menü (PRD 10.1.1): Yükle, Çalışanlar, Kuyruklar, Belge Türleri,
Yüklemeler.

Her sayfa oturum ister (10.1.2): yönlendirici `app.main`'de `require_panel_user` ile bağlanır,
oturumsuz istek giriş sayfasına gider. Bölümlerin içeriği kendi gereksinimlerinindir (10.2
yükleme, 10.3 yükleme ayrıntısı, 10.4 çalışan listesi, 10.7 kuyruklar, 11.1 katalog); o işler
gelene kadar sayfa bölümün adını gösterir.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.web.auth import PanelUser, require_panel_user
from app.web.templating import MENU_BY_KEY, PANEL_MENU, render_page

router = APIRouter(tags=["panel"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]


def _section(request: Request, user: PanelUser, key: str) -> HTMLResponse:
    entry = MENU_BY_KEY[key]
    return render_page(request, "section.html", user=user, active=entry.key, entry=entry)


@router.get("/")
def home(_user: CurrentUser) -> RedirectResponse:
    """Panelin girişi menünün ilk bölümüdür."""
    return RedirectResponse(PANEL_MENU[0].path, status.HTTP_303_SEE_OTHER)


@router.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request, user: CurrentUser) -> HTMLResponse:
    return _section(request, user, "upload")


@router.get("/employees", response_class=HTMLResponse)
def employees_page(request: Request, user: CurrentUser) -> HTMLResponse:
    return _section(request, user, "employees")


@router.get("/queues", response_class=HTMLResponse)
def queues_page(request: Request, user: CurrentUser) -> HTMLResponse:
    return _section(request, user, "queues")


@router.get("/document-types", response_class=HTMLResponse)
def document_types_page(request: Request, user: CurrentUser) -> HTMLResponse:
    return _section(request, user, "document_types")


@router.get("/uploads", response_class=HTMLResponse)
def uploads_page(request: Request, user: CurrentUser) -> HTMLResponse:
    return _section(request, user, "uploads")
