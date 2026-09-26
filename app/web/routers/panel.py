"""Panel sayfaları ve ana menü (PRD 10.1.1): Yükle, Çalışanlar, Kuyruklar, Belge Türleri,
Yüklemeler, Eğitim modu.

Her sayfa oturum ister (10.1.2): yönlendirici `app.main`'de `require_panel_user` ile bağlanır,
oturumsuz istek giriş sayfasına gider. Bölümlerin içeriği kendi gereksinimlerinindir (10.2
yükleme — `upload_page.py`, 10.3 yükleme listesi — `uploads_list.py` ve ayrıntısı —
`upload_page.py`, 10.4 çalışan listesi — `employees.py`, 10.7 kuyruklar — `queue.py`, 11.1
katalog, 11.9.1 eğitim modu — `training.py`); bu dosyada yalnız panelin giriş yönlendirmesi kalır.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import RedirectResponse

from app.web.auth import PanelUser, require_panel_user
from app.web.templating import PANEL_MENU

router = APIRouter(tags=["panel"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]


@router.get("/")
def home(_user: CurrentUser) -> RedirectResponse:
    """Panelin girişi menünün ilk bölümüdür."""
    return RedirectResponse(PANEL_MENU[0].path, status.HTTP_303_SEE_OTHER)
