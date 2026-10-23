"""Panel şablonları ve ana menü (PRD 10.1.1).

Şablonlar paketle birlikte yüklenir (`app/web/templates/`); Jinja2 HTML'i otomatik kaçışlar.
Ana menü tek yerde tanımlıdır: `base.html` onu her panel sayfasında çizer; her bölümün
yönlendiricisi sayfasını menüdeki yolla sunar.

Arayüz dili (PRD 10.10.1, PLAN.md §D92 e): şablonlarda `jinja2.ext.i18n` — `{% trans %}` ve
`_()` isteğin dilinde çevrilir (`app.i18n.gettext`; `newstyle`: çeviri `%` biçimlemesiyle
doldurulur, otomatik kaçış korunur). Menü etiketleri `N_()` ile işaretli Türkçe msgid'lerdir,
`base.html` onları gösterirken çevirir. `html_lang` her sayfaya `<html lang>` değerini verir.

Dil seçici (PRD 10.10.2, PLAN.md §D92 c): `_language_selector.html` üst çubuğun altındaki araç
alanında ve giriş kutusunun altında `POST /language`'a giden açılır formdur (JavaScript'siz);
`languages` dilleri seçici sırasıyla, `language` isteğin dilini verir. Dönülecek yol
`language_return_path`'tir.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from importlib import resources
from typing import Any

import jinja2
import markupsafe
from fastapi import Request
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.countries import country_badge, nationality_badge
from app.i18n import (
    N_,
    SUPPORTED_LANGUAGES,
    Translatable,
    current_html_lang,
    current_language,
    gettext,
    ngettext,
    translate,
)
from app.web.auth import PanelUser
from app.web.feedback import (
    FLASH_COOKIE,
    Toast,
    add_toasts,
    clear_flash,
    is_htmx,
    read_flash,
    render,
    status_feedback,
)

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
    MenuEntry("output_templates", N_("Hazır Şablonlar"), "/output-templates"),
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
# 10.10.3: çekirdekten gelen kaynak dildeki metin (durum adı, hata, bildirim) gösterim anında
# çevrilir (`app.i18n.translate`); veri (ad, dosya adı, tür adı) bundan geçirilmez.
templates.env.globals["translate"] = translate
# Liste öğelerini çevirmek için süzgeç olarak da (`problems|map("translate")`).
templates.env.filters["translate"] = translate


def recorded(text: object) -> str:
    """10.10.6 (§D121): kayıtlı sistem metni — kaynağı geri çağrılmışsa (`Translatable`,
    `app.i18n.recorded`) isteğin dilinde, değilse (eski Türkçe kayıt, yapay zekâ notu, insanın
    notu) olduğu gibi."""
    if isinstance(text, Translatable):
        return translate(text)
    return "" if text is None else str(text)


def recorded_attrs(text: object) -> markupsafe.Markup:
    """Kayıtlı metnin öğesine `translate="no"`: yalnız çevrilmeyen (olduğu gibi gösterilen) metin
    tarayıcı çevirisine ve kalıntı taramasına kapalıdır."""
    if isinstance(text, Translatable):
        return markupsafe.Markup("")
    return markupsafe.Markup(' translate="no"')


templates.env.globals["recorded"] = recorded
templates.env.globals["recorded_attrs"] = recorded_attrs
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


def _asset_version() -> str:
    """Her sayfanın yüklediği kendi stil ve betik dosyalarının içerik özeti (12 karakter).

    Adrese `?v=<özet>` olarak eklenir: dosya değişince adres de değişir, tarayıcı ve önündeki
    önbellek (Cloudflare gibi) eski kopyayı süresi dolana kadar sunmaz. Açılışta bir kez hesaplanır;
    dosya değişikliği zaten yeniden başlatma ister (13.5.3).
    """
    digest = hashlib.sha256()
    static = resources.files("app.web").joinpath("static")
    for name in VERSIONED_ASSETS:
        digest.update(static.joinpath(name).read_bytes())
    return digest.hexdigest()[:12]


# `base.html`in sürüm ekiyle yüklediği dosyalar.
VERSIONED_ASSETS = ("panel.css", "theme.css", "theme-init.js", "theme.js", "toast.js")
templates.env.globals["asset_version"] = _asset_version()


def render_page(
    request: Request,
    name: str,
    *,
    user: PanelUser | None,
    active: str | None = None,
    status_code: int = 200,
    feedback: Toast | None = None,
    **context: Any,
) -> HTMLResponse:
    """`name` şablonunu çizer; `user` varsa üst çubukta menü ve çıkış görünür.

    Geçici bildirim (10.11.1, PLAN.md §D120): `feedback` bu yanıtın kendi bildirimidir; verilmezse
    hata koduyla çizilen bir yazma isteği (`POST`; sayfa ya da HTMX parçası) kodun özet bildirimini
    alır. Bir önceki
    yönlendirmenin çerezdeki bildirimi (`app.web.feedback.flash`) de burada okunur ve aynı yanıtta
    silinir. Tam sayfada bildirimler `base.html`'in bildirim alanına basılır; HTMX isteğinde
    (`HX-Request`) `HX-Trigger` başlığıyla gider — `hx-select` ile seçilen parça bildirim alanını
    içermez, çift gösterim olmaz."""
    htmx = is_htmx(request)
    toasts: list[Toast] = []
    if feedback is not None:
        toasts.append(feedback)
    elif request.method == "POST":
        automatic = status_feedback(status_code)
        if automatic is not None:
            toasts.append(render(automatic))
    flashed = read_flash(request)
    response = templates.TemplateResponse(
        request,
        name,
        {"user": user, "active": active, "toasts": [] if htmx else [*flashed, *toasts], **context},
        status_code=status_code,
    )
    if FLASH_COOKIE in request.cookies:
        clear_flash(response)
    # Başlık tam sayfada da yazılır: tarayıcı yok sayar, ama HTMX hedefi olan bir parça (yalnız
    # `hx-post` taşıyan form) HTMX'siz istenirse bildirim yine yanıttadır.
    add_toasts(response, [*flashed, *toasts])
    return response
