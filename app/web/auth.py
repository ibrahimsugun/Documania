"""Panel kimlik doğrulaması — parola, sunucu tarafı oturum ve istek bağımlılıkları (PRD 10.1.2,
10.1.3, 10.1.4; MASTER-PROMPT §4: "sunucu tarafı oturum çerezi; parola hash `argon2`").

Parola yalnız argon2 özeti olarak saklanır. Girişte rastgele bir belirteç üretilir: çerez yalnız
bu belirteci taşır, veritabanında (`user_sessions`) belirtecin SHA-256 özeti durur. Oturum süresi
dolunca ya da çıkışta geçersizdir; kapanan oturum satırı silinmez (`revoked_at`).

Kullanıcı yönetimi (10.1.4, PLAN.md §C92-d): kullanıcı silinmez, pasife alınır (`users.active`).
Pasif kullanıcı giriş yapamaz (hata metni yanlış parolanınkiyle aynı) ve açık oturumları kapanır;
oturum denetimi her istekte `users.active`'i okur (önbellek yok). Kullanıcı kendini pasife alamaz,
son etkin yönetici pasife alınamaz. Parola değişince kullanıcının diğer oturumları kapanır. Her
işlem kullanıcı adıyla olaya yazılır; parola hiçbir olaya girmez (K15).

10.1.2 "girişsiz hiçbir panel yolu açılmaz": panel sayfaları `require_panel_user` ile girişe
yönlendirir (303), API uç noktaları `require_api_user` ile 401 döner. İkisi de oturumu
`get_current_user`'dan okur; bağlama `app.main.create_app`'te yönlendirici düzeyindedir, açık
yollar yalnız giriş/çıkış, sağlık denetimi ve stil dosyasıdır.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Annotated
from urllib.parse import urlencode

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, aliased

from app.config import Settings
from app.db.models import User, UserRole, UserSession, utcnow
from app.db.session import get_session
from app.events import EventType, record_event
from app.i18n import is_supported

SESSION_COOKIE = "belgeee_session"
LOGIN_PATH = "/login"
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 150  # `users.username` sütun uzunluğu
MIN_PASSWORD_LENGTH = 12  # komut satırı ve panel aynı kuralı kullanır (§C92-d)

_hasher = PasswordHasher()


@dataclass(frozen=True, slots=True)
class PanelUser:
    """Oturumu açık kullanıcı; istek boyunca veritabanı nesnesi yerine bu taşınır."""

    id: int
    username: str
    role: str
    # 10.10.2: hesabın arayüz dili tercihi (`en`/`tr`/`sr`); `None` = tercih yok.
    language: str | None = None


class UserCreationError(ValueError):
    """Kullanıcı açılamadı ya da parola değişmedi: ad geçersiz ya da kullanılıyor, parola kısa."""


class UsernameTakenError(UserCreationError):
    """Kullanıcı adı başka bir kullanıcıda (panelde 409)."""


class WrongPasswordError(ValueError):
    """Kendi parolasını değiştirirken verilen eski parola yanlış (panelde 400)."""


class UserStatusError(ValueError):
    """Kullanıcı işlemi kuralla reddedildi: kendini pasife alma, son etkin yönetici, zaten o
    durumda olma, kendi parolasını sıfırlama (panelde 409)."""


class LoginRequiredError(Exception):
    """Panel yolu oturumsuz istendi; `app.main` bunu giriş sayfasına yönlendirmeye çevirir."""

    def __init__(self, next_path: str) -> None:
        super().__init__(next_path)
        self.next_path = next_path


# --- parola -----------------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def _verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    # Bilinmeyen kullanıcı adında da bir doğrulama yapılır: yanıt süresi adın var olup
    # olmadığını ele vermesin.
    return _hasher.hash(secrets.token_urlsafe(16))


def normalize_username(username: str) -> str:
    """Baştaki/sondaki boşluk atılır; boş, çok uzun, boşluklu ya da denetim karakterli ad
    reddedilir."""
    name = username.strip()
    if not name:
        raise UserCreationError("Kullanıcı adı boş olamaz.")
    if len(name) < USERNAME_MIN_LENGTH:
        raise UserCreationError(f"Kullanıcı adı en az {USERNAME_MIN_LENGTH} karakter olmalı.")
    if len(name) > USERNAME_MAX_LENGTH:
        raise UserCreationError(f"Kullanıcı adı en çok {USERNAME_MAX_LENGTH} karakter olabilir.")
    if any(char.isspace() or not char.isprintable() for char in name):
        raise UserCreationError("Kullanıcı adında boşluk ya da denetim karakteri olamaz.")
    return name


def check_password(password: str) -> None:
    """Yeni parolanın kuralı: en az `MIN_PASSWORD_LENGTH` karakter."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise UserCreationError(f"Parola en az {MIN_PASSWORD_LENGTH} karakter olmalı.")


def create_user(
    session: Session,
    username: str,
    password: str,
    *,
    role: UserRole = UserRole.ADMIN,
    actor: str | None = None,
) -> User:
    """10.1.3, 10.1.4 — panel kullanıcısı açar; parola argon2 özetiyle saklanır. Paneldeki açılış
    (`actor` verilir) `USER_CREATED` yazar; komut satırının ilk yöneticisi olay yazmaz. Commit
    çağırana aittir."""
    name = normalize_username(username)
    check_password(password)
    if session.scalar(select(User.id).where(User.username == name)) is not None:
        raise UsernameTakenError(f"'{name}' kullanıcı adı zaten kullanılıyor.")
    user = User(username=name, password_hash=hash_password(password), role=role.value, active=True)
    session.add(user)
    session.flush()
    if actor is not None:
        record_event(
            session,
            EventType.USER_CREATED,
            actor=actor,
            data={"target_user_id": user.id, "role": user.role},
        )
    return user


def authenticate(session: Session, username: str, password: str) -> User | None:
    """Ad ve parola doğruysa ve kullanıcı etkinse kullanıcıyı döner, değilse `None`; hangisinin
    yanlış olduğu, kullanıcının pasif olduğu söylenmez (10.1.4: pasif kullanıcı giriş yapamaz).

    Özet eski parametrelerle üretilmişse doğru parolayla yeniden özetlenir (commit çağırana aittir).
    """
    user = session.scalar(select(User).where(User.username == username.strip()))
    if user is None:
        _verify_password(_dummy_hash(), password)
        return None
    # Pasif kullanıcıda da parola doğrulanır: yanıt süresi durumu ele vermesin.
    if not _verify_password(user.password_hash, password) or not user.active:
        return None
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    return user


# --- oturum -----------------------------------------------------------------------------------


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def open_session(
    session: Session, user: User, *, max_age_seconds: int, now: datetime | None = None
) -> str:
    """Kullanıcıya yeni oturum açar ve çereze yazılacak belirteci döner (yalnız özeti saklanır)."""
    started = now or utcnow()
    token = secrets.token_urlsafe(32)
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            created_at=started,
            expires_at=started + timedelta(seconds=max_age_seconds),
        )
    )
    session.flush()
    return token


def resolve_session(
    session: Session, token: str, *, now: datetime | None = None
) -> PanelUser | None:
    """Belirteç açık, süresi dolmamış bir oturuma aitse ve kullanıcı etkinse kullanıcısını döner.

    `users.active` her istekte buradan okunur (10.1.4): pasife alınan kullanıcının kapanmamış bir
    oturumu kalsa bile geçersizdir.
    """
    row = session.execute(
        select(User.id, User.username, User.role, User.language)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == _token_hash(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > (now or utcnow()),
            User.active.is_(True),
        )
    ).one_or_none()
    if row is None:
        return None
    return PanelUser(id=row.id, username=row.username, role=row.role, language=row.language)


def close_session(session: Session, token: str, *, now: datetime | None = None) -> bool:
    """Belirtecin açık oturumunu kapatır; kapatacak oturum yoksa `False`."""
    user_session = session.scalar(
        select(UserSession).where(
            UserSession.token_hash == _token_hash(token), UserSession.revoked_at.is_(None)
        )
    )
    if user_session is None:
        return False
    user_session.revoked_at = now or utcnow()
    return True


def close_user_sessions(
    session: Session, user_id: int, *, keep_token: str | None = None, now: datetime | None = None
) -> int:
    """Kullanıcının açık oturumlarını kapatır (`revoked_at`); `keep_token`'ın oturumu açık kalır.
    Kapatılan oturum sayısını döner."""
    conditions = [UserSession.user_id == user_id, UserSession.revoked_at.is_(None)]
    if keep_token is not None:
        conditions.append(UserSession.token_hash != _token_hash(keep_token))
    result = session.execute(
        update(UserSession)
        .where(*conditions)
        .values(revoked_at=now or utcnow())
        .execution_options(synchronize_session=False)
    )
    return result.rowcount


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    # HttpOnly: betik okuyamaz; SameSite=Lax: başka siteden gelen POST çerezi taşımaz;
    # üretimde (HTTPS, Caddy) yalnız güvenli bağlantıda gönderilir.
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_max_age_seconds,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")


# --- kullanıcı yönetimi (10.1.4) -------------------------------------------------------------


def _record_password_change(session: Session, target: User, *, actor: str, own: bool) -> None:
    record_event(
        session,
        EventType.USER_PASSWORD_CHANGED,
        actor=actor,
        data={"target_user_id": target.id, "self": own},
    )


def change_own_password(
    session: Session,
    user: User,
    current_password: str,
    new_password: str,
    *,
    keep_token: str | None,
) -> None:
    """Kullanıcı kendi parolasını değiştirir: eski parola doğru olmalı. Bu oturum (`keep_token`)
    açık kalır, diğer oturumları kapanır; `USER_PASSWORD_CHANGED` (`self: true`). Commit çağırana
    aittir."""
    if not _verify_password(user.password_hash, current_password):
        raise WrongPasswordError("Şu anki parola hatalı.")
    check_password(new_password)
    user.password_hash = hash_password(new_password)
    close_user_sessions(session, user.id, keep_token=keep_token)
    _record_password_change(session, user, actor=user.username, own=True)


def reset_password(session: Session, target: User, new_password: str, *, actor: PanelUser) -> None:
    """Yönetici başka bir kullanıcının parolasını sıfırlar; hedefin bütün oturumları kapanır,
    `USER_PASSWORD_CHANGED` (`self: false`). Kendi parolası eski parolayla değişir (409). Commit
    çağırana aittir."""
    if target.id == actor.id:
        raise UserStatusError("Kendi parolanızı «Parolamı değiştir» sayfasından değiştirin.")
    check_password(new_password)
    target.password_hash = hash_password(new_password)
    close_user_sessions(session, target.id)
    _record_password_change(session, target, actor=actor.username, own=False)


def set_user_active(session: Session, target: User, active: bool, *, actor: PanelUser) -> None:
    """Kullanıcıyı pasife alır ya da yeniden etkinleştirir; kullanıcı silinmez (R11).

    Pasife alma kendini (409) ve son etkin yöneticiyi (409) reddeder; koşullu güncellemeyle yapılır
    (arada başka bir istek son diğer yöneticiyi pasife aldıysa satır değişmez), hedefin açık
    oturumları kapanır, `USER_DEACTIVATED`. Etkinleştirme `USER_REACTIVATED`. Zaten o durumdaki
    kullanıcı 409. Commit çağırana aittir.
    """
    if target.active == active:
        state = "etkin" if active else "pasif"
        raise UserStatusError(f"'{target.username}' zaten {state}.")
    if active:
        target.active = True
        session.flush()
        record_event(
            session,
            EventType.USER_REACTIVATED,
            actor=actor.username,
            data={"target_user_id": target.id},
        )
        return
    if target.id == actor.id:
        raise UserStatusError("Kendi hesabınızı pasife alamazsınız.")
    other = aliased(User)
    other_active_admins = (
        select(func.count(other.id))
        .where(other.active.is_(True), other.role == UserRole.ADMIN.value, other.id != target.id)
        .scalar_subquery()
    )
    conditions = [User.id == target.id, User.active.is_(True)]
    if target.role == UserRole.ADMIN.value:
        conditions.append(other_active_admins > 0)
    result = session.execute(
        update(User)
        .where(*conditions)
        .values(active=False)
        .execution_options(synchronize_session=False)
    )
    session.refresh(target)
    if result.rowcount != 1:
        raise UserStatusError("Son etkin yönetici pasife alınamaz.")
    close_user_sessions(session, target.id)
    record_event(
        session,
        EventType.USER_DEACTIVATED,
        actor=actor.username,
        data={"target_user_id": target.id},
    )


# --- arayüz dili tercihi (10.10.2) ----------------------------------------------------------

# `USER_LANGUAGE_CHANGED` verisindeki `via`: dil seçici ya da giriş sayfasında seçilmiş dilin
# tercihi olmayan hesaba girişte kaydı (PRD §8.3, PLAN.md §D92 c, d).
LANGUAGE_VIA_SELECTOR = "selector"
LANGUAGE_VIA_LOGIN = "login"


def set_user_language(session: Session, user: User, language: str, *, via: str) -> bool:
    """Kullanıcının kendi arayüz dili tercihini yazar; `USER_LANGUAGE_CHANGED` kullanıcının kendi
    adıyla düşer. Dil zaten buysa hiçbir şey yazılmaz, `False` döner. Başkasının dili buradan
    ayarlanmaz: çağıran yalnız oturumun kendi kullanıcısını verir. Commit çağırana aittir."""
    if not is_supported(language):
        raise ValueError(f"desteklenmeyen dil: {language!r}")
    if via not in (LANGUAGE_VIA_SELECTOR, LANGUAGE_VIA_LOGIN):
        raise ValueError(f"bilinmeyen dil değişikliği kaynağı: {via!r}")
    if user.language == language:
        return False
    user.language = language
    session.flush()
    record_event(
        session,
        EventType.USER_LANGUAGE_CHANGED,
        actor=user.username,
        data={"target_user_id": user.id, "language": language, "via": via},
    )
    return True


# --- yönlendirme ------------------------------------------------------------------------------


def safe_next_path(value: str | None) -> str:
    """Girişten sonra dönülecek yol: yalnız bu sitedeki mutlak yol, aksi halde kök (açık
    yönlendirme olmasın: `//site`, `/\\site`, şema ya da denetim karakteri reddedilir)."""
    if (
        not value
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(not char.isprintable() for char in value)
    ):
        return "/"
    return value


def login_url(next_path: str) -> str:
    target = safe_next_path(next_path)
    return LOGIN_PATH if target == "/" else f"{LOGIN_PATH}?{urlencode({'next': target})}"


# --- istek bağımlılıkları ---------------------------------------------------------------------


def get_current_user(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> PanelUser | None:
    """İsteğin çerezindeki oturumun kullanıcısı; oturum yok, kapalı ya da süresi dolmuşsa `None`."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    user = resolve_session(session, token)
    # Okuma işlemi burada biter: SQLite'ta her işlem yazma kilidini baştan alır (PLAN.md §C4);
    # uç nokta aynı oturumu kendi işi için yeniden açar.
    session.commit()
    return user


def require_panel_user(
    request: Request, user: Annotated[PanelUser | None, Depends(get_current_user)]
) -> PanelUser:
    """Panel sayfası: oturum yoksa giriş sayfasına yönlendirir, dönüşte istenen sayfa açılır."""
    if user is None:
        query = request.url.query
        raise LoginRequiredError(request.url.path + (f"?{query}" if query else ""))
    return user


def require_api_user(user: Annotated[PanelUser | None, Depends(get_current_user)]) -> PanelUser:
    """API uç noktası: oturum yoksa 401."""
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Oturum açılmamış; önce giriş yapın.")
    return user
