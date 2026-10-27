"""Panel girişi, çıkışı ve arayüz dili seçimi (PRD 10.1.2, 10.10.2).

`GET /login` formu gösterir; oturum zaten açıksa istenen sayfaya geçer. `POST /login` ad ve
parolayı doğrular, yeni oturum açar, belirteci çereze yazar ve istenen sayfaya (`next`, yalnız bu
sitedeki yol) yönlendirir; hatalı girişte hangi alanın yanlış olduğu söylenmez (401). `POST
/logout` oturumu kapatır ve çerezi siler. `POST /language` dil seçicinin hedefidir (PLAN.md §D92
c): dil çerezini, girişliyse hesabın tercihini yazar ve aynı sayfaya döner. Bu dört yol ve
`/health` oturumsuz açılabilen tek yollardır (`app.main`).

Girişte dil (§D92 d): hesabın tercihi boşsa ve çerez geçerli bir dil taşıyorsa (giriş sayfasında
seçilmiş) hesaba yazılır; hesabın tercihi doluysa çerez hesabın diliyle yenilenir — çıkıştan sonra
giriş sayfası kullanıcının dilinde açılır, tercih cihazdan bağımsızdır.

Giriş kaydı (10.1.11, PLAN.md §D125): başarılı giriş ve açık oturumun çıkışı aynı işlemde,
başarısız deneme (nedeniyle) ayrı commit'le `login_log`'a yazılır; kayıt yazılamazsa giriş ve çıkış
yine sonuçlanır. Giriş sayfasının hata metni ve 401'i nedenden bağımsızdır.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import LoginOutcome, User
from app.db.session import get_session
from app.i18n import LANGUAGE_COOKIE, N_, gettext, is_supported
from app.i18n.request import set_language_cookie
from app.web.auth import (
    LANGUAGE_VIA_LOGIN,
    LANGUAGE_VIA_SELECTOR,
    LOGIN_PATH,
    SESSION_COOKIE,
    PanelUser,
    check_login,
    clear_session_cookie,
    close_session,
    get_current_user,
    login_url,
    open_session,
    record_login,
    safe_next_path,
    session_owner,
    set_session_cookie,
    set_user_language,
)
from app.web.templating import LANGUAGE_PATH, render_page

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])

# 10.10.1: giriş sayfası isteğin dilindedir; mesaj gösterim anında çevrilir.
LOGIN_FAILED = N_("Kullanıcı adı veya parola hatalı.")
UNSUPPORTED_LANGUAGE = N_("Desteklenmeyen dil.")


@router.get(LOGIN_PATH, response_class=HTMLResponse)
def login_form(
    request: Request,
    user: Annotated[PanelUser | None, Depends(get_current_user)],
    next_path: Annotated[str | None, Query(alias="next")] = None,
) -> Response:
    target = safe_next_path(next_path)
    if user is not None:
        return RedirectResponse(target, status.HTTP_303_SEE_OTHER)
    return render_page(
        request,
        "login.html",
        user=None,
        next=target,
        username="",
        error=None,
        language_next=login_url(target),
    )


@router.post(LOGIN_PATH, response_class=HTMLResponse)
def login(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    next_path: Annotated[str, Form(alias="next")] = "/",
) -> Response:
    target = safe_next_path(next_path)
    attempt = check_login(session, username, password)
    user = attempt.user
    if user is None:
        # Başarısız yolda `check_login` hiçbir şey değiştirmez: commit yalnız kaydı yazar.
        record_login(
            session,
            request,
            settings,
            username=username,
            outcome=LoginOutcome.FAILED,
            user_id=attempt.account.id if attempt.account is not None else None,
            reason=attempt.reason,
        )
        _commit_quietly(session)
        return render_page(
            request,
            "login.html",
            user=None,
            next=target,
            username=username.strip(),
            error=gettext(LOGIN_FAILED),
            language_next=login_url(target),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    # Tarayıcıda kalmış önceki oturum kapanır; her girişte yeni belirteç verilir.
    previous = request.cookies.get(SESSION_COOKIE)
    if previous:
        close_session(session, previous)
    # 10.10.2: giriş sayfasında seçilmiş dil, tercihi olmayan hesaba kaydedilir.
    cookie_language = request.cookies.get(LANGUAGE_COOKIE)
    if user.language is None and is_supported(cookie_language):
        set_user_language(session, user, cookie_language, via=LANGUAGE_VIA_LOGIN)
    token = open_session(session, user, max_age_seconds=settings.session_max_age_seconds)
    record_login(
        session,
        request,
        settings,
        username=user.username,
        outcome=LoginOutcome.SUCCESS,
        user_id=user.id,
    )
    language = user.language
    session.commit()
    response = RedirectResponse(target, status.HTTP_303_SEE_OTHER)
    set_session_cookie(response, token, settings)
    if language is not None:
        set_language_cookie(response, language, settings)
    return response


@router.post("/logout")
def logout(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    owner = session_owner(session, token) if token else None
    if token and close_session(session, token):
        if owner is not None:
            record_login(
                session,
                request,
                settings,
                username=owner.username,
                outcome=LoginOutcome.LOGOUT,
                user_id=owner.id,
            )
        session.commit()
    response = RedirectResponse(LOGIN_PATH, status.HTTP_303_SEE_OTHER)
    clear_session_cookie(response)
    # 11.9.8 (PLAN.md §D131 f4): ortak bilgisayarda çıkıştan sonra önbellekte belge görüntüsü
    # (ön yüklenen önizlemeler, sayfa görüntüleri) kalmaz.
    response.headers["Clear-Site-Data"] = '"cache"'
    return response


def _commit_quietly(session: Session) -> None:
    """Başarısız denemenin kaydını commit'ler; commit hata verirse 401 yine döner (§D125 h)."""
    try:
        session.commit()
    except Exception:  # noqa: BLE001 — giriş, günlüğe bağımlı kilitlenmez (10.1.11)
        session.rollback()
        logger.warning("başarısız giriş kaydı commit'lenemedi", exc_info=True)


@router.post(LANGUAGE_PATH)
def change_language(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[PanelUser | None, Depends(get_current_user)],
    language: Annotated[str, Form()] = "",
    next_path: Annotated[str, Form(alias="next")] = "/",
) -> Response:
    """10.10.2 — dil seçici: çerez her durumda, girişliyse kullanıcının kendi tercihi de yazılır
    (`USER_LANGUAGE_CHANGED` via `selector`; dil aynıysa olay yok). Geçersiz dil 422, hiçbir şey
    değişmez. Dönüş yalnız bu sitedeki yola (açık yönlendirme yok)."""
    if not is_supported(language):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, gettext(UNSUPPORTED_LANGUAGE))
    if user is not None:
        account = session.get(User, user.id)
        if account is not None:
            set_user_language(session, account, language, via=LANGUAGE_VIA_SELECTOR)
            session.commit()
    response = RedirectResponse(safe_next_path(next_path), status.HTTP_303_SEE_OTHER)
    set_language_cookie(response, language, settings)
    return response
