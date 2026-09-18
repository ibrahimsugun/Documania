"""Panel girişi ve çıkışı (PRD 10.1.2).

`GET /login` formu gösterir; oturum zaten açıksa istenen sayfaya geçer. `POST /login` ad ve
parolayı doğrular, yeni oturum açar, belirteci çereze yazar ve istenen sayfaya (`next`, yalnız bu
sitedeki yol) yönlendirir; hatalı girişte hangi alanın yanlış olduğu söylenmez (401). `POST
/logout` oturumu kapatır ve çerezi siler. Bu üç yol ve `/health` oturumsuz açılabilen tek
yollardır (`app.main`).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_session
from app.web.auth import (
    LOGIN_PATH,
    SESSION_COOKIE,
    PanelUser,
    authenticate,
    clear_session_cookie,
    close_session,
    get_current_user,
    open_session,
    safe_next_path,
    set_session_cookie,
)
from app.web.templating import render_page

router = APIRouter(tags=["auth"])

LOGIN_FAILED = "Kullanıcı adı veya parola hatalı."


@router.get(LOGIN_PATH, response_class=HTMLResponse)
def login_form(
    request: Request,
    user: Annotated[PanelUser | None, Depends(get_current_user)],
    next_path: Annotated[str | None, Query(alias="next")] = None,
) -> Response:
    target = safe_next_path(next_path)
    if user is not None:
        return RedirectResponse(target, status.HTTP_303_SEE_OTHER)
    return render_page(request, "login.html", user=None, next=target, username="", error=None)


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
    user = authenticate(session, username, password)
    if user is None:
        return render_page(
            request,
            "login.html",
            user=None,
            next=target,
            username=username.strip(),
            error=LOGIN_FAILED,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    # Tarayıcıda kalmış önceki oturum kapanır; her girişte yeni belirteç verilir.
    previous = request.cookies.get(SESSION_COOKIE)
    if previous:
        close_session(session, previous)
    token = open_session(session, user, max_age_seconds=settings.session_max_age_seconds)
    session.commit()
    response = RedirectResponse(target, status.HTTP_303_SEE_OTHER)
    set_session_cookie(response, token, settings)
    return response


@router.post("/logout")
def logout(request: Request, session: Annotated[Session, Depends(get_session)]) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token and close_session(session, token):
        session.commit()
    response = RedirectResponse(LOGIN_PATH, status.HTTP_303_SEE_OTHER)
    clear_session_cookie(response)
    return response
