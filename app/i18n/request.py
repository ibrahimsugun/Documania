"""İsteğin arayüz dili (PRD 10.10.1; PLAN.md §D92 b).

`use_request_language` sayfa sunan yönlendiricilere bağlanır (`app.main`): girişli istekte hesabın
dil tercihi (`users.language`, 10.10.2; oturumla aynı sorguda okunur), girişsiz istekte geçerli
`documania_lang` çerezi, ikisi de yoksa `Settings.panel_default_language`. Tarayıcının
`Accept-Language`'ı okunmaz. JSON API ve `/health` çevrilmez, bu bağımlılığı almaz.

Çerezi dil seçici (`POST /language`) ve giriş yazar (`set_language_cookie`, §D92 c, d).

Bağımlılık `async`'tir: yazdığı context değişkeni aynı istek görevinde koşan uç noktaya ve
şablona geçer. Eşzamanlı bağımlılık iş parçacığı havuzunda, bağlamın kopyasında koşardı; yazdığı
dil orada kalır, sayfa varsayılan dille çizilirdi.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request, Response

from app.config import Settings, get_settings
from app.i18n import LANGUAGE_COOKIE, activate_language, is_supported, resolve_language
from app.web.auth import PanelUser, get_current_user


async def use_request_language(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[PanelUser | None, Depends(get_current_user)],
) -> str:
    """İsteğin dilini çözer, bu isteğin bağlamına yazar ve döner."""
    language = resolve_language(
        signed_in=user is not None,
        user_language=user.language if user is not None else None,
        cookie=request.cookies.get(LANGUAGE_COOKIE),
        default=settings.panel_default_language,
    )
    activate_language(language)
    return language


# Dil çerezi bir yıl yaşar; çıkıştan sonra giriş sayfası kullanıcının dilinde açılsın diye.
LANGUAGE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60


def set_language_cookie(response: Response, language: str, settings: Settings) -> None:
    """`documania_lang` çerezini yazar (§D92 c): HttpOnly, SameSite=Lax; `Secure` kuralı oturum
    çereziyle aynı (üretimde yalnız güvenli bağlantı)."""
    if not is_supported(language):
        raise ValueError(f"desteklenmeyen dil: {language!r}")
    response.set_cookie(
        LANGUAGE_COOKIE,
        language,
        max_age=LANGUAGE_COOKIE_MAX_AGE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
    )
