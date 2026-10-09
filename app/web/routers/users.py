"""Kullanıcılar ekranı ve Hesabım (PRD 10.1.4, 10.1.8, 12.1.3, 12.1.8; PLAN.md §C92-d, §C92-e,
§D97, §D115).

- `GET /users` panel kullanıcılarını listeler: kullanıcı adı, rol, durum, izinli Telegram kimliği
  sayısı; "Yeni kullanıcı" formu ve her başka kullanıcı için rol, parola sıfırlama ve pasife alma /
  yeniden etkinleştirme. Her kullanıcı satırının altında — kendi satırı dahil — bağlı Telegram
  kimlikleri izin durumlarıyla durur; yönetici izni kapatıp açabilir (kaybolan telefon), ama
  başkası adına kimlik ekleyemez ve bağlantı üretemez (12.1.8, §D97 d).
- `POST /users` kullanıcı açar (ad 3–150, parola ≥ 12, rol `hr` | `user`); kural dışı değer (root
  dahil) 422, kullanılan ad 409 ile sayfa yeniden çizilir.
- `POST /users/{id}/role` (`role` = `hr` | `user`, 10.1.8): `USER_ROLE_CHANGED` {target_user_id,
  from, to}; kendi rolü, aynı rol ve son etkin İK'yı düşürme 409, root ya da bilinmeyen rol 422.
- `POST /users/{id}/password` yöneticinin sıfırlamasıdır; hedefin açık oturumları kapanır. Kendi
  parolası buradan değişmez (409).
- `POST /users/{id}/status` (`active` | `inactive`): kendini pasife alma ve son etkin İK'yı pasife
  alma 409; pasife alınanın açık oturumları kapanır.
- `GET /account/password` + `POST /account/password` kullanıcının kendi parolasıdır: eski parola
  yanlışsa 400; bu oturum açık kalır, diğerleri kapanır.
- `POST /users/{id}/telegram/{tid}/status` (`allowed` = `true` | `false`) izni açar ya da kapatır;
  aynı duruma geçiş 409, kimlik o kullanıcıya bağlı değilse 404. Bot yalnız izinli ve etkin
  kullanıcıya bağlı kimliğe yanıt verir (`app.telegram.whitelist`). Olay `TELEGRAM_USER_CHANGED`.
- `POST /users/{id}/telegram/{tid}/delete` kaydı siler (12.1.10, §D107): numara serbest kalır ve
  aynı ya da başka bir hesaba yeniden bağlanabilir; kimlik o kullanıcıya bağlı değilse 404. Olay
  `TELEGRAM_USER_CHANGED` {…, removed: true}.

**Hesabım → Telegram (12.1.8, §D97 c).** Telegram'ı yalnız hesabın sahibi bağlar. Yolların
hiçbirinde kullanıcı kimliği yoktur: hedef her zaman oturumdaki kullanıcıdır (`user.id`).

- `GET /account/telegram` kendi kimlikleri izin durumlarıyla; her girişli kullanıcıya açık.
- `POST /account/telegram/link` "Telegram'ı bağla" (12.1.4, §D87): kendisi için tek kullanımlık,
  10 dakika geçerli bot bağlantısı (`https://t.me/<bot>?start=<kod>`) üretir ve sayfayla birlikte
  bir kez gösterir (yönlendirme yok: kod adres çubuğuna, geçmişe ve loga girmez; yanıt
  `Cache-Control: no-store`). Kişi bağlantıyı açıp «Başlat»a basınca bot kimliğini kendisi bağlar
  (`app.telegram.link`). Bot bu veri dizininde hiç çalışmadıysa (`telegram/bot.json` yok) düğme
  kapalıdır ve istek 409 döner. Olay `TELEGRAM_LINK_CREATED` kişinin kendi adıyla.
- `POST /account/telegram` (`telegram_id`) elle ekleme: pozitif tam sayı değilse 422, kimlik zaten
  bir kullanıcıya bağlıysa 409; olay `TELEGRAM_USER_CHANGED` {…, via: "account"}.
- `POST /account/telegram/{tid}/status` kendi kimliğinin izni; kimlik kendisinin değilse 404, aynı
  duruma geçiş 409.
- `POST /account/telegram/{tid}/delete` kendi kimliğinin kaydını siler (12.1.10); kimlik kendisinin
  değilse 404; olay {…, removed: true, via: "account"}.

**Yetki (10.1.8, §D115).** Kullanıcılar sayfasını her rol açar; yazma işlemleri (`router`) İK ve
root'undur — `app.main`'deki kapı Kullanıcı'nın her `POST`'una 403 döner, şablon
Kullanıcı'ya formları göstermez. Hesabım yolları (`account_router`: kendi parolası ve Telegram'ı)
her role açıktır.
**Root gizlidir:** root satırı kullanıcı ve Telegram tablolarından süzülür (root'un kendi ekranında
da), rol seçiminde yoktur ve `/users/{root_id}/…` her rol için "kullanıcı bulunamadı" (404) döner.

Hepsi tek adımlıdır (§D61-b: dosyaya ve belgeye dokunmaz, geri alınabilir) ve kullanıcı adıyla olay
yazar (`USER_*`).
Parola hiçbir olaya, loga ya da sayfaya yazılmaz; reddedilen formda parola alanı boş gelir.
Kullanıcı silinmez (R11); silinebilen tek kayıt Telegram kimliğidir (12.1.10, §D107).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Path, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import TelegramUser, User, UserRole
from app.db.session import get_session
from app.i18n import N_
from app.storage import DataLayout
from app.telegram.link import (
    LINK_CODE_TTL,
    LinkTargetInactiveError,
    create_link_code,
    link_url,
    read_bot_info,
)
from app.telegram.whitelist import (
    TELEGRAM_ID_MAX,
    USERINFOBOT_URL,
    TelegramIdError,
    TelegramIdTakenError,
    TelegramStatusError,
    add_telegram_id,
    parse_telegram_id,
    remove_telegram_id,
    set_telegram_allowed,
)
from app.web.auth import (
    ASSIGNABLE_ROLES,
    MIN_PASSWORD_LENGTH,
    SESSION_COOKIE,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
    PanelUser,
    UserCreationError,
    UsernameTakenError,
    UserStatusError,
    WrongPasswordError,
    change_own_password,
    create_user,
    require_panel_user,
    reset_password,
    set_user_active,
    set_user_role,
)
from app.web.routers.uploads import get_layout
from app.web.templating import MENU_BY_KEY, render_page

router = APIRouter(tags=["users"])
# Kişinin kendi hesabı (parola, Telegram): yazma kapısının dışında, her role açık (10.1.8).
account_router = APIRouter(tags=["account"])

USERS_PATH = "/users"
ACCOUNT_PASSWORD_PATH = "/account/password"
ACCOUNT_TELEGRAM_PATH = "/account/telegram"
ACCOUNT_VIA = "account"
"""`TELEGRAM_USER_CHANGED` olayında kimliği kişinin kendi hesap sayfasından eklediğini söyler."""
USER_NOT_FOUND = N_("Kullanıcı bulunamadı")
TELEGRAM_NOT_FOUND = N_("Bu kullanıcıya bağlı böyle bir Telegram kimliği yok")
OWN_TELEGRAM_NOT_FOUND = N_("Hesabınıza bağlı böyle bir Telegram kimliği yok")
UNKNOWN_ALLOWED = N_("İzin 'true' ya da 'false' olmalı.")
PASSWORDS_DIFFER = N_("Yeni parola ile tekrarı eşleşmiyor.")
UNKNOWN_ROLE = N_("Bilinmeyen rol.")
UNKNOWN_STATUS = N_("Durum 'active' ya da 'inactive' olmalı.")
BOT_NEVER_RAN = N_(
    "Telegram botu bu kurulumda hiç çalışmadı: .env'e TELEGRAM_BOT_TOKEN ekleyip botu başlatın "
    "(baslat.bat). Bot ilk açılışta adını kaydeder; sonra bağlantı üretilebilir."
)
# 10.1.8: tablolarda root satırı yoktur; "Root" etiketi yalnız root'un kendi ekranındadır
# (`base.html`, Hesabım).
ROLE_LABELS = {UserRole.HR.value: N_("İK"), UserRole.USER.value: N_("Kullanıcı")}
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
NOTICES = {
    "created": N_("Kullanıcı oluşturuldu."),
    "password_reset": N_("Parola sıfırlandı; kullanıcının açık oturumları kapatıldı."),
    "deactivated": N_("Kullanıcı pasife alındı; açık oturumları kapatıldı."),
    "reactivated": N_("Kullanıcı yeniden etkinleştirildi."),
    "role_changed": N_("Kullanıcının rolü değişti; bir sonraki isteğinde geçerli olur."),
    "own_password": N_("Parolanız değiştirildi; diğer oturumlarınız kapatıldı."),
    "telegram_allowed": N_("Telegram kimliğinin izni açıldı."),
    "telegram_blocked": N_("Telegram kimliğinin izni kapatıldı; bot bu kimliğe yanıt vermeyecek."),
    "telegram_removed": N_(
        "Telegram kaydı silindi. Bu numara artık yeniden bağlanabilir; bot ona yanıt vermeyecek."
    ),
}
ACCOUNT_NOTICES = {
    "telegram_added": N_("Telegram kimliği eklendi ve izni açıldı."),
    "telegram_allowed": NOTICES["telegram_allowed"],
    "telegram_blocked": NOTICES["telegram_blocked"],
    "telegram_removed": NOTICES["telegram_removed"],
}
ALLOWED_TRUE = "true"
ALLOWED_FALSE = "false"

# Form sınırı yalnız aşırı girdiye karşıdır; uzunluk kuralını `app.web.auth` mesajla bildirir.
FORM_TEXT_LIMIT = 1000
TextField = Annotated[str, Form(max_length=FORM_TEXT_LIMIT)]


# Yazma yolları yalnız İK ve root'a açıktır: kapı `app.main`'de yönlendirici düzeyindedir
# (`panel_write_gate`); burada yalnız oturumdaki kullanıcı okunur.
CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]
DbSession = Annotated[Session, Depends(get_session)]
Layout = Annotated[DataLayout, Depends(get_layout)]


@dataclass(frozen=True, slots=True)
class TelegramRow:
    telegram_id: int
    allowed: bool


@dataclass(frozen=True, slots=True)
class UserRow:
    id: int
    username: str
    role: str
    role_label: str
    active: bool
    telegram_count: int
    is_self: bool
    telegram: tuple[TelegramRow, ...] = ()


@dataclass(frozen=True, slots=True)
class IssuedLink:
    """Az önce üretilen bot bağlantısı: yalnız bu yanıtta gösterilir (12.1.4)."""

    url: str
    expires_at: datetime
    minutes: int


@dataclass(frozen=True, slots=True)
class NewUserValues:
    """Reddedilen "Yeni kullanıcı" formunda yeniden gösterilen değerler (parola hiç gösterilmez)."""

    username: str = ""
    role: str = UserRole.USER.value


def _rows(session: Session, user: PanelUser) -> list[UserRow]:
    telegram = (
        select(TelegramUser.user_id, func.count().label("allowed"))
        .where(TelegramUser.allowed.is_(True))
        .group_by(TelegramUser.user_id)
        .subquery()
    )
    # 10.1.8: root hiçbir tabloda listelenmez — root'un kendi ekranında da.
    rows = session.execute(
        select(User.id, User.username, User.role, User.active, telegram.c.allowed)
        .outerjoin(telegram, telegram.c.user_id == User.id)
        .where(User.role != UserRole.ROOT.value)
        .order_by(User.id)
    ).all()
    accounts: dict[int, list[TelegramRow]] = {}
    for account in session.execute(
        select(TelegramUser.user_id, TelegramUser.telegram_id, TelegramUser.allowed)
        .join(User, User.id == TelegramUser.user_id)
        .where(User.role != UserRole.ROOT.value)
        .order_by(TelegramUser.user_id, TelegramUser.telegram_id)
    ):
        accounts.setdefault(account.user_id, []).append(
            TelegramRow(telegram_id=account.telegram_id, allowed=account.allowed)
        )
    return [
        UserRow(
            id=row.id,
            username=row.username,
            role=row.role,
            role_label=ROLE_LABELS.get(row.role, row.role),
            active=row.active,
            telegram_count=row.allowed or 0,
            is_self=row.id == user.id,
            telegram=tuple(accounts.get(row.id, ())),
        )
        for row in rows
    ]


def _users_page(
    request: Request,
    user: PanelUser,
    session: Session,
    layout: DataLayout,
    *,
    status_code: int = status.HTTP_200_OK,
    notice: str | None = None,
    error: str | None = None,
    error_user_id: int | None = None,
    form: NewUserValues | None = None,
) -> HTMLResponse:
    response = render_page(
        request,
        "users.html",
        user=user,
        active="users",
        entry=MENU_BY_KEY["users"],
        users=_rows(session, user),
        roles=[(role.value, ROLE_LABELS[role.value]) for role in ASSIGNABLE_ROLES],
        notice=NOTICES.get(notice or ""),
        error=error,
        error_user_id=error_user_id,
        form=form or NewUserValues(),
        min_password_length=MIN_PASSWORD_LENGTH,
        username_min_length=USERNAME_MIN_LENGTH,
        username_max_length=USERNAME_MAX_LENGTH,
        status_code=status_code,
    )
    session.rollback()
    return response


def _redirect(notice: str) -> RedirectResponse:
    return RedirectResponse(f"{USERS_PATH}?notice={notice}", status.HTTP_303_SEE_OTHER)


def _user_or_404(session: Session, user_id: int) -> User:
    """`/users/{id}/…` hedefi. 10.1.8: root yokmuş gibidir — her rol için aynı 404 ve aynı metin."""
    target = session.get(User, user_id)
    if target is None or target.role == UserRole.ROOT.value:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    return target


def _own_user(session: Session, user: PanelUser) -> User:
    """Hesabım yollarının hedefi: her zaman oturumdaki kullanıcı (root dahil)."""
    own = session.get(User, user.id)
    if own is None:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    return own


def _assignable_role(value: str) -> UserRole | None:
    """Formdaki rol: yalnız `hr` ya da `user`; root ve bilinmeyen değer `None` (aynı 422 metni)."""
    return next((role for role in ASSIGNABLE_ROLES if role.value == value), None)


@router.get(USERS_PATH, response_class=HTMLResponse)
def users_page(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    notice: Annotated[str | None, Query(max_length=32)] = None,
) -> HTMLResponse:
    return _users_page(request, user, session, layout, notice=notice)


@router.post(USERS_PATH, response_class=HTMLResponse)
def create_user_endpoint(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    username: TextField = "",
    password: TextField = "",
    role: TextField = UserRole.USER.value,
) -> Response:
    """10.1.4, 10.1.8 "yeni kullanıcı" — `USER_CREATED` {target_user_id, role} kullanıcı adıyla.
    Rol `hr` ya da `user`; root ve bilinmeyen rol aynı metinle 422 (root ele verilmez)."""
    form = NewUserValues(username=username.strip(), role=role)
    chosen = _assignable_role(role)
    if chosen is None:
        return _users_page(
            request,
            user,
            session,
            layout,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            error=UNKNOWN_ROLE,
            form=form,
        )
    try:
        create_user(session, username, password, role=chosen, actor=user.username)
    except UserCreationError as exc:
        session.rollback()
        code = (
            status.HTTP_409_CONFLICT
            if isinstance(exc, UsernameTakenError)
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        return _users_page(request, user, session, layout, status_code=code, error=exc, form=form)
    session.commit()
    return _redirect("created")


@router.post(f"{USERS_PATH}/{{user_id}}/role", response_class=HTMLResponse)
def set_role_endpoint(
    user_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    role: Annotated[str, Form(max_length=16)] = "",
) -> Response:
    """10.1.8 rol değiştirme (İK ↔ Kullanıcı) — `USER_ROLE_CHANGED` {target_user_id, from, to}.
    Root hedefi 404; root ya da bilinmeyen rol 422; kendi rolü, aynı rol ve son etkin İK 409. Açık
    oturumlar kapanmaz: yeni rol hedefin bir sonraki isteğinde geçerlidir."""
    target = _user_or_404(session, user_id)
    chosen = _assignable_role(role)
    if chosen is None:
        return _users_page(
            request,
            user,
            session,
            layout,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            error=UNKNOWN_ROLE,
            error_user_id=user_id,
        )
    try:
        set_user_role(session, target, chosen, actor=user)
    except UserStatusError as exc:
        session.rollback()
        return _users_page(
            request,
            user,
            session,
            layout,
            status_code=status.HTTP_409_CONFLICT,
            error=exc,
            error_user_id=user_id,
        )
    session.commit()
    return _redirect("role_changed")


@router.post(f"{USERS_PATH}/{{user_id}}/password", response_class=HTMLResponse)
def reset_password_endpoint(
    user_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    password: TextField = "",
) -> Response:
    """10.1.4 "başka kullanıcının parolasını sıfırlama" — hedefin oturumları kapanır,
    `USER_PASSWORD_CHANGED` {target_user_id, self: false}. Kendi parolası 409, kısa parola 422."""
    target = _user_or_404(session, user_id)
    try:
        reset_password(session, target, password, actor=user)
    except (UserCreationError, UserStatusError) as exc:
        session.rollback()
        code = (
            status.HTTP_409_CONFLICT
            if isinstance(exc, UserStatusError)
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        return _users_page(
            request,
            user,
            session,
            layout,
            status_code=code,
            error=exc,
            error_user_id=user_id,
        )
    session.commit()
    return _redirect("password_reset")


@router.post(f"{USERS_PATH}/{{user_id}}/status", response_class=HTMLResponse)
def set_status_endpoint(
    user_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    status_value: Annotated[str, Form(alias="status", max_length=16)] = "",
) -> Response:
    """10.1.4 pasife alma ve yeniden etkinleştirme — `USER_DEACTIVATED`/`USER_REACTIVATED`
    {target_user_id}. Kendini ya da son etkin İK'yı pasife alma, aynı duruma geçiş 409."""
    if status_value not in (STATUS_ACTIVE, STATUS_INACTIVE):
        return _users_page(
            request,
            user,
            session,
            layout,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            error=UNKNOWN_STATUS,
            error_user_id=user_id,
        )
    target = _user_or_404(session, user_id)
    active = status_value == STATUS_ACTIVE
    try:
        set_user_active(session, target, active, actor=user)
    except UserStatusError as exc:
        session.rollback()
        return _users_page(
            request,
            user,
            session,
            layout,
            status_code=status.HTTP_409_CONFLICT,
            error=exc,
            error_user_id=user_id,
        )
    session.commit()
    return _redirect("reactivated" if active else "deactivated")


@router.post(
    f"{USERS_PATH}/{{user_id}}/telegram/{{telegram_id}}/status", response_class=HTMLResponse
)
def set_telegram_status_endpoint(
    user_id: int,
    telegram_id: Annotated[int, Path(ge=1, le=TELEGRAM_ID_MAX)],
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    allowed_value: Annotated[str, Form(alias="allowed", max_length=8)] = "",
) -> Response:
    """12.1.3 izni kapatma ve açma — kayıt silinmez; `TELEGRAM_USER_CHANGED` {target_user_id,
    telegram_id, allowed, added: false}. Aynı duruma geçiş 409, kimlik bu kullanıcıya bağlı değilse
    404."""
    if allowed_value not in (ALLOWED_TRUE, ALLOWED_FALSE):
        return _users_page(
            request,
            user,
            session,
            layout,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            error=UNKNOWN_ALLOWED,
            error_user_id=user_id,
        )
    target = _user_or_404(session, user_id)
    account = session.get(TelegramUser, telegram_id)
    if account is None or account.user_id != target.id:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, TELEGRAM_NOT_FOUND)
    allowed = allowed_value == ALLOWED_TRUE
    try:
        set_telegram_allowed(session, account, allowed, actor=user.username)
    except TelegramStatusError as exc:
        session.rollback()
        return _users_page(
            request,
            user,
            session,
            layout,
            status_code=status.HTTP_409_CONFLICT,
            error=exc,
            error_user_id=user_id,
        )
    session.commit()
    return _redirect("telegram_allowed" if allowed else "telegram_blocked")


@router.post(
    f"{USERS_PATH}/{{user_id}}/telegram/{{telegram_id}}/delete", response_class=HTMLResponse
)
def delete_telegram_endpoint(
    user_id: int,
    telegram_id: Annotated[int, Path(ge=1, le=TELEGRAM_ID_MAX)],
    user: CurrentUser,
    session: DbSession,
) -> Response:
    """12.1.10 kaydı silme (§D107) — `TELEGRAM_USER_CHANGED` {target_user_id, telegram_id, allowed,
    added: false, removed: true}. Kimlik bu kullanıcıya bağlı değilse 404."""
    target = _user_or_404(session, user_id)
    try:
        remove_telegram_id(session, target.id, telegram_id, actor=user.username)
    except LookupError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, TELEGRAM_NOT_FOUND) from None
    session.commit()
    return _redirect("telegram_removed")


def _account_page(
    request: Request,
    user: PanelUser,
    *,
    status_code: int = status.HTTP_200_OK,
    error: str | None = None,
) -> HTMLResponse:
    return render_page(
        request,
        "account_password.html",
        user=user,
        active="users",
        error=error,
        min_password_length=MIN_PASSWORD_LENGTH,
        status_code=status_code,
    )


@account_router.get(ACCOUNT_PASSWORD_PATH, response_class=HTMLResponse)
def account_password_page(request: Request, user: CurrentUser) -> HTMLResponse:
    return _account_page(request, user)


@account_router.post(ACCOUNT_PASSWORD_PATH, response_class=HTMLResponse)
def change_own_password_endpoint(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    current_password: TextField = "",
    new_password: TextField = "",
    new_password_repeat: TextField = "",
) -> Response:
    """10.1.4 "kendi parolasını değiştirme" — eski parola yanlışsa 400, yeni parola kısa ya da
    tekrarı farklıysa 422; bu oturum açık kalır, diğerleri kapanır; `USER_PASSWORD_CHANGED`
    {target_user_id, self: true}."""
    own = _own_user(session, user)
    if new_password != new_password_repeat:
        session.rollback()
        return _account_page(
            request, user, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, error=PASSWORDS_DIFFER
        )
    try:
        change_own_password(
            session,
            own,
            current_password,
            new_password,
            keep_token=request.cookies.get(SESSION_COOKIE),
        )
    except (WrongPasswordError, UserCreationError) as exc:
        session.rollback()
        code = (
            status.HTTP_400_BAD_REQUEST
            if isinstance(exc, WrongPasswordError)
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        return _account_page(request, user, status_code=code, error=exc)
    session.commit()
    return _redirect("own_password")


# --- Hesabım → Telegram (12.1.8, §D97 c) ------------------------------------------------------


def _own_accounts(session: Session, user: PanelUser) -> list[TelegramRow]:
    return [
        TelegramRow(telegram_id=row.telegram_id, allowed=row.allowed)
        for row in session.execute(
            select(TelegramUser.telegram_id, TelegramUser.allowed)
            .where(TelegramUser.user_id == user.id)
            .order_by(TelegramUser.telegram_id)
        )
    ]


def _account_telegram_page(
    request: Request,
    user: PanelUser,
    session: Session,
    layout: DataLayout,
    *,
    status_code: int = status.HTTP_200_OK,
    notice: str | None = None,
    error: str | None = None,
    telegram_value: str = "",
    link: IssuedLink | None = None,
) -> HTMLResponse:
    bot = read_bot_info(layout)
    response = render_page(
        request,
        "account_telegram.html",
        user=user,
        active="users",
        accounts=_own_accounts(session, user),
        notice=ACCOUNT_NOTICES.get(notice or ""),
        error=error,
        telegram_value=telegram_value,
        userinfobot_url=USERINFOBOT_URL,
        bot_username=bot.username if bot is not None else None,
        bot_never_ran=BOT_NEVER_RAN,
        link=link,
        status_code=status_code,
    )
    session.rollback()
    return response


def _account_redirect(notice: str) -> RedirectResponse:
    return RedirectResponse(f"{ACCOUNT_TELEGRAM_PATH}?notice={notice}", status.HTTP_303_SEE_OTHER)


@account_router.get(ACCOUNT_TELEGRAM_PATH, response_class=HTMLResponse)
def account_telegram_page(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    notice: Annotated[str | None, Query(max_length=32)] = None,
) -> HTMLResponse:
    """12.1.8 Hesabım → Telegram: yalnız oturumdaki kullanıcının kimlikleri."""
    return _account_telegram_page(request, user, session, layout, notice=notice)


@account_router.post(ACCOUNT_TELEGRAM_PATH, response_class=HTMLResponse)
def add_own_telegram_endpoint(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    telegram_id: Annotated[str, Form(max_length=64)] = "",
) -> Response:
    """12.1.8 kendi Telegram kimliğini elle ekleme — izin açık gelir; `TELEGRAM_USER_CHANGED`
    {target_user_id = kendi, telegram_id, allowed: true, added: true, via: "account"}. Pozitif tam
    sayı değilse 422, kimlik zaten bir kullanıcıya bağlıysa 409."""
    own = _own_user(session, user)
    try:
        add_telegram_id(
            session, own, parse_telegram_id(telegram_id), actor=user.username, via=ACCOUNT_VIA
        )
    except (TelegramIdError, TelegramIdTakenError) as exc:
        session.rollback()
        code = (
            status.HTTP_409_CONFLICT
            if isinstance(exc, TelegramIdTakenError)
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        return _account_telegram_page(
            request,
            user,
            session,
            layout,
            status_code=code,
            error=exc,
            telegram_value=telegram_id.strip(),
        )
    session.commit()
    return _account_redirect("telegram_added")


@account_router.post(f"{ACCOUNT_TELEGRAM_PATH}/{{telegram_id}}/status", response_class=HTMLResponse)
def set_own_telegram_status_endpoint(
    telegram_id: Annotated[int, Path(ge=1, le=TELEGRAM_ID_MAX)],
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    allowed_value: Annotated[str, Form(alias="allowed", max_length=8)] = "",
) -> Response:
    """12.1.8 kendi kimliğinin iznini kapatma ve açma — `TELEGRAM_USER_CHANGED` {…, added: false}.
    Kimlik oturumdaki kullanıcının değilse 404, aynı duruma geçiş 409."""
    if allowed_value not in (ALLOWED_TRUE, ALLOWED_FALSE):
        return _account_telegram_page(
            request,
            user,
            session,
            layout,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            error=UNKNOWN_ALLOWED,
        )
    account = session.get(TelegramUser, telegram_id)
    if account is None or account.user_id != user.id:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, OWN_TELEGRAM_NOT_FOUND)
    allowed = allowed_value == ALLOWED_TRUE
    try:
        set_telegram_allowed(session, account, allowed, actor=user.username)
    except TelegramStatusError as exc:
        session.rollback()
        return _account_telegram_page(
            request, user, session, layout, status_code=status.HTTP_409_CONFLICT, error=exc
        )
    session.commit()
    return _account_redirect("telegram_allowed" if allowed else "telegram_blocked")


@account_router.post(f"{ACCOUNT_TELEGRAM_PATH}/{{telegram_id}}/delete", response_class=HTMLResponse)
def delete_own_telegram_endpoint(
    telegram_id: Annotated[int, Path(ge=1, le=TELEGRAM_ID_MAX)],
    user: CurrentUser,
    session: DbSession,
) -> Response:
    """12.1.10 kendi kimliğinin kaydını silme — `TELEGRAM_USER_CHANGED` {…, removed: true,
    via: "account"}. Hedef her zaman oturumdaki kullanıcıdır; kimlik onun değilse 404."""
    try:
        remove_telegram_id(session, user.id, telegram_id, actor=user.username, via=ACCOUNT_VIA)
    except LookupError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, OWN_TELEGRAM_NOT_FOUND) from None
    session.commit()
    return _account_redirect("telegram_removed")


@account_router.post(f"{ACCOUNT_TELEGRAM_PATH}/link", response_class=HTMLResponse)
def create_own_telegram_link_endpoint(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
) -> Response:
    """12.1.4, 12.1.8 "Telegram'ı bağla" — kendisi için tek kullanımlık bot bağlantısı;
    `TELEGRAM_LINK_CREATED` {target_user_id = kendi, expires_at} kendi adıyla. Önceki kullanılmamış
    bağlantı geçersiz olur. Bot hiç çalışmamışken 409. Bağlantı yalnız bu yanıtta görünür."""
    own = _own_user(session, user)
    bot = read_bot_info(layout)
    if bot is None:
        session.rollback()
        return _account_telegram_page(
            request,
            user,
            session,
            layout,
            status_code=status.HTTP_409_CONFLICT,
            error=BOT_NEVER_RAN,
        )
    try:
        issued = create_link_code(session, own, actor=user.username)
    except LinkTargetInactiveError as exc:  # pasif kullanıcı giriş yapamaz; yarış için
        session.rollback()
        return _account_telegram_page(
            request, user, session, layout, status_code=status.HTTP_409_CONFLICT, error=exc
        )
    session.commit()
    response = _account_telegram_page(
        request,
        user,
        session,
        layout,
        link=IssuedLink(
            url=link_url(bot.username, issued.code),
            expires_at=issued.expires_at,
            minutes=int(LINK_CODE_TTL.total_seconds() // 60),
        ),
    )
    response.headers["Cache-Control"] = "no-store"
    return response
