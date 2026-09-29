"""Panel şablonları ve ana menü (PRD 10.1.1).

Şablonlar paketle birlikte yüklenir (`app/web/templates/`); Jinja2 HTML'i otomatik kaçışlar.
Ana menü tek yerde tanımlıdır: `base.html` onu her panel sayfasında çizer; her bölümün
yönlendiricisi sayfasını menüdeki yolla sunar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jinja2
from fastapi import Request
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.web.auth import PanelUser


@dataclass(frozen=True, slots=True)
class MenuEntry:
    key: str
    label: str
    path: str


PANEL_MENU = (
    MenuEntry("upload", "Yükle", "/upload"),
    MenuEntry("employees", "Çalışanlar", "/employees"),
    MenuEntry("queues", "Kuyruklar", "/queues"),
    MenuEntry("document_types", "Belge Türleri", "/document-types"),
    MenuEntry("document_groups", "Belge Grupları", "/document-groups"),
    MenuEntry("uploads", "Yüklemeler", "/uploads"),
    MenuEntry("training", "Eğitim modu", "/training"),
    MenuEntry("users", "Kullanıcılar", "/users"),
)
MENU_BY_KEY = {entry.key: entry for entry in PANEL_MENU}

templates = Jinja2Templates(
    env=jinja2.Environment(
        loader=jinja2.PackageLoader("app.web", "templates"),
        autoescape=jinja2.select_autoescape(),
    )
)
templates.env.globals["menu"] = PANEL_MENU


def render_page(
    request: Request,
    name: str,
    *,
    user: PanelUser | None,
    active: str | None = None,
    status_code: int = 200,
    **context: Any,
) -> HTMLResponse:
    """`name` şablonunu çizer; `user` varsa üst çubukta menü ve çıkış görünür."""
    return templates.TemplateResponse(
        request,
        name,
        {"user": user, "active": active, **context},
        status_code=status_code,
    )
