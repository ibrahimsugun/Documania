"""İsteğin arayüz dili (PRD 10.10.1; PLAN.md §D92 b).

`use_request_language` sayfa sunan yönlendiricilere bağlanır (`app.main`): girişli istekte hesabın
dili (hesaptaki tercih 10.10.2 ile gelir; o zamana dek varsayılan), girişsiz istekte geçerli
`documania_lang` çerezi, ikisi de yoksa `Settings.panel_default_language`. Tarayıcının
`Accept-Language`'ı okunmaz. JSON API ve `/health` çevrilmez, bu bağımlılığı almaz.

Bağımlılık `async`'tir: yazdığı context değişkeni aynı istek görevinde koşan uç noktaya ve
şablona geçer. Eşzamanlı bağımlılık iş parçacığı havuzunda, bağlamın kopyasında koşardı; yazdığı
dil orada kalır, sayfa varsayılan dille çizilirdi.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.i18n import LANGUAGE_COOKIE, activate_language, resolve_language
from app.web.auth import PanelUser, get_current_user


async def use_request_language(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[PanelUser | None, Depends(get_current_user)],
) -> str:
    """İsteğin dilini çözer, bu isteğin bağlamına yazar ve döner."""
    language = resolve_language(
        signed_in=user is not None,
        user_language=None,
        cookie=request.cookies.get(LANGUAGE_COOKIE),
        default=settings.panel_default_language,
    )
    activate_language(language)
    return language
