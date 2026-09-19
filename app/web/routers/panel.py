"""Panel sayfaları ve ana menü (PRD 10.1.1): Yükle, Çalışanlar, Kuyruklar, Belge Türleri,
Yüklemeler.

Her sayfa oturum ister (10.1.2): yönlendirici `app.main`'de `require_panel_user` ile bağlanır,
oturumsuz istek giriş sayfasına gider. Bölümlerin içeriği kendi gereksinimlerinindir (10.2
yükleme — `upload_page.py`, 10.3 yükleme ayrıntısı, 10.4 çalışan listesi — `employees.py`, 10.7
kuyruklar — `queue.py`, 11.1 katalog); içeriği gelmemiş bölümde sayfa yalnız bölümün adını gösterir.
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


@router.get("/uploads", response_class=HTMLResponse)
def uploads_page(request: Request, user: CurrentUser) -> HTMLResponse:
    return _section(request, user, "uploads")
