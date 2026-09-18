"""Panel kimlik doğrulaması — parola, sunucu tarafı oturum ve istek bağımlılıkları (PRD 10.1.2,
10.1.3; MASTER-PROMPT §4: "sunucu tarafı oturum çerezi; parola hash `argon2`").

Parola yalnız argon2 özeti olarak saklanır. Girişte rastgele bir belirteç üretilir: çerez yalnız
bu belirteci taşır, veritabanında (`user_sessions`) belirtecin SHA-256 özeti durur. Oturum süresi
dolunca ya da çıkışta geçersizdir; kapanan oturum satırı silinmez (`revoked_at`).

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
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import User, UserRole, UserSession, utcnow
from app.db.session import get_session

SESSION_COOKIE = "belgeee_session"
LOGIN_PATH = "/login"
USERNAME_MAX_LENGTH = 150  # `users.username` sütun uzunluğu
MIN_PASSWORD_LENGTH = 8

_hasher = PasswordHasher()


@dataclass(frozen=True, slots=True)
class PanelUser:
    """Oturumu açık kullanıcı; istek boyunca veritabanı nesnesi yerine bu taşınır."""

    id: int
    username: str
    role: str


class UserCreationError(ValueError):
    """Kullanıcı açılamadı: ad geçersiz ya da kullanılıyor, parola kısa."""


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
    if len(name) > USERNAME_MAX_LENGTH:
        raise UserCreationError(f"Kullanıcı adı en çok {USERNAME_MAX_LENGTH} karakter olabilir.")
    if any(char.isspace() or not char.isprintable() for char in name):
        raise UserCreationError("Kullanıcı adında boşluk ya da denetim karakteri olamaz.")
    return name


def create_user(
    session: Session, username: str, password: str, *, role: UserRole = UserRole.ADMIN
) -> User:
    """10.1.3 — panel kullanıcısı açar; parola argon2 özetiyle saklanır. Commit çağırana aittir."""
    name = normalize_username(username)
    if len(password) < MIN_PASSWORD_LENGTH:
        raise UserCreationError(f"Parola en az {MIN_PASSWORD_LENGTH} karakter olmalı.")
    if session.scalar(select(User.id).where(User.username == name)) is not None:
        raise UserCreationError(f"'{name}' kullanıcı adı zaten kullanılıyor.")
    user = User(username=name, password_hash=hash_password(password), role=role.value)
    session.add(user)
    session.flush()
    return user


def authenticate(session: Session, username: str, password: str) -> User | None:
    """Ad ve parola doğruysa kullanıcıyı döner, değilse `None`; hangisinin yanlış olduğu söylenmez.

    Özet eski parametrelerle üretilmişse doğru parolayla yeniden özetlenir (commit çağırana aittir).
    """
    user = session.scalar(select(User).where(User.username == username.strip()))
    if user is None:
        _verify_password(_dummy_hash(), password)
        return None
    if not _verify_password(user.password_hash, password):
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
    """Belirteç açık, süresi dolmamış bir oturuma aitse kullanıcısını döner."""
    row = session.execute(
        select(User.id, User.username, User.role)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == _token_hash(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > (now or utcnow()),
        )
    ).one_or_none()
    if row is None:
        return None
    return PanelUser(id=row.id, username=row.username, role=row.role)


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
