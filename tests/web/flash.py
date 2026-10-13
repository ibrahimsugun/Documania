"""Geçici bildirim testlerinin ortak yardımcıları (PRD 10.11.1; PLAN.md §D120).

`flashed(response)` yönlendirmenin yazdığı tek kullanımlık çerezdeki bildirimi (anahtar,
parametreler) okur; `toasts(html)` tam sayfanın bildirim alanındaki metinleri, `hx_toasts(response)`
HTMX yanıtının `HX-Trigger` başlığındaki bildirimleri döner.
"""

from __future__ import annotations

import json
import re
from html import unescape

import httpx

from app.web.feedback import FLASH_COOKIE, TOAST_EVENT, _decode

_TOAST = re.compile(
    r'<div class="toast toast-(\w+)" role="(\w+)" data-kind="\w+">'
    r'<span class="toast-icon" aria-hidden="true"></span><p class="toast-text">(.*?)</p></div>',
    re.S,
)


def flashed(response: httpx.Response) -> tuple[str, dict[str, object]] | None:
    """Yanıtın yazdığı bildirim çerezi: `(anahtar, parametreler)`; çerez yoksa `None`."""
    for header in response.headers.get_list("set-cookie"):
        name, _, rest = header.partition("=")
        if name.strip() != FLASH_COOKIE:
            continue
        value = rest.split(";", 1)[0].strip().strip('"')
        if not value:
            return None
        (item,) = _decode(value)
        return item["k"], item.get("p", {})
    return None


def toasts(html: str) -> list[str]:
    """Tam sayfanın bildirim alanındaki metinler (sırayla)."""
    return [unescape(text) for _, _, text in _TOAST.findall(html)]


def toast_items(html: str) -> list[tuple[str, str, str]]:
    """`(tür, rol, metin)` üçlüleri."""
    return [(kind, role, unescape(text)) for kind, role, text in _TOAST.findall(html)]


def hx_toasts(response: httpx.Response) -> list[dict[str, str]]:
    """HTMX yanıtının `HX-Trigger` başlığındaki `documania:toast` bildirimleri."""
    header = response.headers.get("HX-Trigger")
    if not header:
        return []
    return json.loads(header).get(TOAST_EVENT, {}).get("toasts", [])
