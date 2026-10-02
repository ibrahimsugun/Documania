"""Panel şablonları ve ana menü (PRD 10.1.1).

Şablonlar paketle birlikte yüklenir (`app/web/templates/`); Jinja2 HTML'i otomatik kaçışlar.
Ana menü tek yerde tanımlıdır: `base.html` onu her panel sayfasında çizer; her bölümün
yönlendiricisi sayfasını menüdeki yolla sunar.

Arayüz dili (PRD 10.10.1, PLAN.md §D92 e): şablonlarda `jinja2.ext.i18n` — `{% trans %}` ve
`_()` isteğin dilinde çevrilir (`app.i18n.gettext`; `newstyle`: çeviri `%` biçimlemesiyle
doldurulur, otomatik kaçış korunur). Menü etiketleri `N_()` ile işaretli Türkçe msgid'lerdir,
`base.html` onları gösterirken çevirir. `html_lang` her sayfaya `<html lang>` değerini verir.

Dil seçici (PRD 10.10.2, PLAN.md §D92 c): `_language_selector.html` üst çubukta ve giriş kutusunun
altında `POST /language`'a giden üç düğmeli formdur (JavaScript'siz); `languages` dilleri seçici
sırasıyla, `language` isteğin dilini verir. Dönülecek yol `language_return_path`'tir.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import jinja2
from fastapi import Request
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.countries import country_badge, nationality_badge
from app.i18n import (
    N_,
    SUPPORTED_LANGUAGES,
    current_html_lang,
    current_language,
    gettext,
    ngettext,
)
from app.web.auth import PanelUser

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MenuEntry:
    key: str
    label: str
    path: str


PANEL_MENU = (
    MenuEntry("employees", N_("Çalışanlar"), "/employees"),
    MenuEntry("upload", N_("Yükle"), "/upload"),
    MenuEntry("document_types", N_("Belge Türleri"), "/document-types"),
    MenuEntry("document_groups", N_("Belge Grupları"), "/document-groups"),
    MenuEntry("queues", N_("Kuyruklar"), "/queues"),
    MenuEntry("uploads", N_("Yüklemeler"), "/uploads"),
    MenuEntry("training", N_("Eğitim modu"), "/training"),
    MenuEntry("users", N_("Kullanıcılar"), "/users"),
)
MENU_BY_KEY = {entry.key: entry for entry in PANEL_MENU}

# 10.10.2: dil seçicinin hedefi (`app.web.routers.auth.change_language`; `_language_selector.html`
# formun hedefini düz yazar — gönderim hedefleri denetimi şablonu okur).
LANGUAGE_PATH = "/language"


def _language_context(_request: Request) -> dict[str, Any]:
    # 10.10.1: sayfanın `<html lang>`'ı isteğin dilidir (`en`, `tr`, `sr-Latn`); 10.10.2: dil
    # seçici dilleri kendi adlarıyla gösterir, seçili olanı işaretler.
    return {
        "html_lang": current_html_lang(),
        "language": current_language(),
        "languages": tuple(SUPPORTED_LANGUAGES.values()),
    }


def language_return_path(request: Request) -> str:
    """10.10.2: dil seçildikten sonra dönülecek yol — `GET` ile açılan sayfanın kendisi (sorgu
    dizgesiyle). Form gönderiminin sonucu olan sayfa (`POST`) aynı adresle yeniden açılamayabilir,
    o zaman ana sayfaya dönülür."""
    if request.method != "GET":
        return "/"
    query = request.url.query
    return request.url.path + (f"?{query}" if query else "")


templates = Jinja2Templates(
    env=jinja2.Environment(
        loader=jinja2.PackageLoader("app.web", "templates"),
        autoescape=jinja2.select_autoescape(),
        extensions=["jinja2.ext.i18n"],
    ),
    context_processors=[_language_context],
)
# `{% trans %}` gövdesindeki satır sonu ve girinti tek boşluğa iner; çıkarıcı (`babel.cfg`) da
# aynı kuralla okur, msgid'ler eşleşir.
templates.env.policies["ext.i18n.trimmed"] = True
templates.env.install_gettext_callables(gettext, ngettext, newstyle=True)
templates.env.globals["menu"] = PANEL_MENU
# 10.1.6: alfa-2, alfa-3 ya da MRZ kodundan bayrak + Türkçe ülke adı (`app/countries`).
templates.env.globals["country_badge"] = country_badge
# 10.5.11: profildeki uyruk — bayrak + Türkçe ad + parantez içinde kod; tanınmayan kodda yalnız kod.
templates.env.globals["nationality_badge"] = nationality_badge


def code_is_stale(request: Request) -> bool:
    """13.5.3: panel açıldıktan sonra diskteki kod değiştiyse `True` (`base.html` uyarısı).

    Uyarı hesaplanamazsa gösterilmez; sayfa bu yüzden 500'e düşmez.
    """
    try:
        watch = getattr(request.app.state, "code_watch", None)
        return bool(watch is not None and watch.is_stale())
    except Exception:
        logger.warning("Eski süreç uyarısı hesaplanamadı.", exc_info=True)
        return False


templates.env.globals["code_is_stale"] = code_is_stale
templates.env.globals["language_return_path"] = language_return_path


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
