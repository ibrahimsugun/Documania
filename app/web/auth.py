"""Panel kimlik doğrulaması — parola, sunucu tarafı oturum ve istek bağımlılıkları (PRD 10.1.2,
10.1.3, 10.1.4; MASTER-PROMPT §4: "sunucu tarafı oturum çerezi; parola hash `argon2`").

Parola yalnız argon2 özeti olarak saklanır. Girişte rastgele bir belirteç üretilir: çerez yalnız
bu belirteci taşır, veritabanında (`user_sessions`) belirtecin SHA-256 özeti durur. Oturum süresi
dolunca ya da çıkışta geçersizdir; kapanan oturum satırı silinmez (`revoked_at`).

Kullanıcı yönetimi (10.1.4, PLAN.md §C92-d): kullanıcı silinmez, pasife alınır (`users.active`).
Pasif kullanıcı giriş yapamaz (hata metni yanlış parolanınkiyle aynı) ve açık oturumları kapanır;
oturum denetimi her istekte `users.active`'i okur (önbellek yok). Kullanıcı kendini pasife alamaz,
son etkin İK pasife alınamaz. Parola değişince kullanıcının diğer oturumları kapanır. Her
işlem kullanıcı adıyla olaya yazılır; parola hiçbir olaya girmez (K15).

Yetki seviyeleri (10.1.8, 10.1.9; PLAN.md §D115): `hr` (İK) ve `root` yazar, `user` (Kullanıcı)
salt okunur gezer. Rol, `users.active` gibi her istekte veritabanından okunur: rol değişikliği açık
oturumda bir sonraki istekte geçerlidir. Yazma kapısı sunucudadır: `app.main` her yönlendiriciye
`panel_write_gate`/`api_write_gate` bağlar — güvenli olmayan her yöntem `require_writer`'ın
kuralından geçer (Kullanıcı'ya 403, hiçbir şey yazılmaz); yalnız giriş/çıkış, dil seçici ve kendi
hesabının yolları (`/account/...`) bu kapının dışındadır. `require_root` erişim logunu root'a
ayırır, ötekine 404 döner. Root gizlidir ve tektir: panel root üretmez ve atamaz (`create_root`
yalnız komut satırı), son etkin İK kuralı root'u saymaz ve hata metni onu anmaz.

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
from typing import Annotated, Any
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
from app.i18n import N_, Translatable, is_supported

SESSION_COOKIE = "belgeee_session"
LOGIN_PATH = "/login"
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 150  # `users.username` sütun uzunluğu
MIN_PASSWORD_LENGTH = 12  # komut satırı ve panel aynı kuralı kullanır (§C92-d)
# 10.1.8: yazan roller; panelde (ve `create-user`'da) atanabilen roller — root yalnız
# `create-root`'la verilir.
WRITER_ROLES = frozenset({UserRole.HR.value, UserRole.ROOT.value})
ASSIGNABLE_ROLES = (UserRole.HR, UserRole.USER)
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
READ_ONLY = N_("Hesabınız salt okunur: bu işlemi yapamazsınız.")
LAST_ACTIVE_HR = N_("Son etkin İK pasife alınamaz ve rolü düşürülemez.")

_hasher = PasswordHasher()


@dataclass(frozen=True, slots=True)
class PanelUser:
    """Oturumu açık kullanıcı; istek boyunca veritabanı nesnesi yerine bu taşınır."""

    id: int
    username: str
    role: str
    # 10.10.2: hesabın arayüz dili tercihi (`en`/`tr`/`sr`); `None` = tercih yok.
    language: str | None = None

    @property
    def can_write(self) -> bool:
        """10.1.8: İK ve root yazar; Kullanıcı salt okunurdur (şablon yazma düğmelerini gizler)."""
        return self.role in WRITER_ROLES

    @property
    def is_root(self) -> bool:
        """10.1.8, 10.1.9: root'un kendi ekranındaki etiket ve erişim logu."""
        return self.role == UserRole.ROOT.value


class UserCreationError(ValueError):
    """Kullanıcı açılamadı ya da parola değişmedi: ad geçersiz ya da kullanılıyor, parola kısa."""


class UsernameTakenError(UserCreationError):
    """Kullanıcı adı başka bir kullanıcıda (panelde 409)."""


class WrongPasswordError(ValueError):
    """Kendi parolasını değiştirirken verilen eski parola yanlış (panelde 400)."""


class UserStatusError(ValueError):
    """Kullanıcı işlemi kuralla reddedildi: kendini pasife alma, son etkin İK, zaten o durumda ya da
    rolde olma, kendi parolasını sıfırlama, kendi rolünü değiştirme (panelde 409)."""


class RootExistsError(UserCreationError):
    """İkinci root açılamaz (10.1.8): komut satırı reddeder, veritabanı indeksi de reddeder."""


class RootTargetError(LookupError):
    """Panelden root'a yönelik işlem (10.1.8): panel bunu "kullanıcı bulunamadı" (404) sayar."""


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
        raise UserCreationError(N_("Kullanıcı adı boş olamaz."))
    if len(name) < USERNAME_MIN_LENGTH:
        raise UserCreationError(
            Translatable(
                N_("Kullanıcı adı en az {limit} karakter olmalı."), limit=USERNAME_MIN_LENGTH
            )
        )
    if len(name) > USERNAME_MAX_LENGTH:
        raise UserCreationError(
            Translatable(
                N_("Kullanıcı adı en çok {limit} karakter olabilir."), limit=USERNAME_MAX_LENGTH
            )
        )
    if any(char.isspace() or not char.isprintable() for char in name):
        raise UserCreationError(N_("Kullanıcı adında boşluk ya da denetim karakteri olamaz."))
    return name


def check_password(password: str) -> None:
    """Yeni parolanın kuralı: en az `MIN_PASSWORD_LENGTH` karakter."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise UserCreationError(
            Translatable(N_("Parola en az {limit} karakter olmalı."), limit=MIN_PASSWORD_LENGTH)
        )


def create_user(
    session: Session,
    username: str,
    password: str,
    *,
    role: UserRole = UserRole.HR,
    actor: str | None = None,
) -> User:
    """10.1.3, 10.1.4, 10.1.8 — İK ya da Kullanıcı açar; parola argon2 özetiyle saklanır. Root
    buradan açılmaz (`create_root`). Paneldeki açılış (`actor` verilir) `USER_CREATED` yazar; komut
    satırının açtığı kullanıcı olay yazmaz. Commit çağırana aittir."""
    if role not in ASSIGNABLE_ROLES:
        raise ValueError(f"create_user root açmaz: {role!r}")
    return _new_user(session, username, password, role=role, actor=actor)


def create_root(session: Session, username: str, password: str) -> User:
    """10.1.8 — tek root'u açar; yalnız komut satırı çağırır (`python -m app.web create-root`).
    Root zaten varsa `RootExistsError`; aynı anda iki açılışı `uq_users_single_root` indeksi
    reddeder. Olay yazmaz (komut satırının açtığı kullanıcı gibi). Commit çağırana aittir."""
    if session.scalar(select(User.id).where(User.role == UserRole.ROOT.value)) is not None:
        raise RootExistsError(N_("Sistemde zaten bir root var; ikinci root açılamaz."))
    return _new_user(session, username, password, role=UserRole.ROOT, actor=None)


def _new_user(
    session: Session, username: str, password: str, *, role: UserRole, actor: str | None
) -> User:
    name = normalize_username(username)
    check_password(password)
    if session.scalar(select(User.id).where(User.username == name)) is not None:
        raise UsernameTakenError(
            Translatable(N_("'{name}' kullanıcı adı zaten kullanılıyor."), name=name)
        )
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
        raise WrongPasswordError(N_("Şu anki parola hatalı."))
    check_password(new_password)
    user.password_hash = hash_password(new_password)
    close_user_sessions(session, user.id, keep_token=keep_token)
    _record_password_change(session, user, actor=user.username, own=True)


def reset_password(session: Session, target: User, new_password: str, *, actor: PanelUser) -> None:
    """İK başka bir kullanıcının parolasını sıfırlar; hedefin bütün oturumları kapanır,
    `USER_PASSWORD_CHANGED` (`self: false`). Kendi parolası eski parolayla değişir (409). Commit
    çağırana aittir."""
    _refuse_root_target(target)
    if target.id == actor.id:
        raise UserStatusError(N_("Kendi parolanızı «Parolamı değiştir» sayfasından değiştirin."))
    check_password(new_password)
    target.password_hash = hash_password(new_password)
    close_user_sessions(session, target.id)
    _record_password_change(session, target, actor=actor.username, own=False)


def _refuse_root_target(target: User) -> None:
    """10.1.8: panel root'a yönelik hiçbir işlem yapmaz (yönlendirici bunu 404'e çevirir)."""
    if target.role == UserRole.ROOT.value:
        raise RootTargetError(target.id)


def _other_active_hr(target: User) -> Any:
    """`target` dışındaki etkin İK sayısı (alt sorgu). Root sayılmaz (10.1.8): gizlidir; İK kalmazsa
    panel yazan görünür kişiyi kaybeder."""
    other = aliased(User)
    return (
        select(func.count(other.id))
        .where(other.active.is_(True), other.role == UserRole.HR.value, other.id != target.id)
        .scalar_subquery()
    )


def set_user_active(session: Session, target: User, active: bool, *, actor: PanelUser) -> None:
    """Kullanıcıyı pasife alır ya da yeniden etkinleştirir; kullanıcı silinmez (R11).

    Pasife alma kendini (409) ve son etkin İK'yı (409; root sayılmaz, metin root'u anmaz) reddeder;
    koşullu güncellemeyle yapılır (arada başka bir istek son diğer İK'yı pasife aldıysa ya da
    düşürdüyse satır değişmez), hedefin açık oturumları kapanır, `USER_DEACTIVATED`. Etkinleştirme
    `USER_REACTIVATED`. Zaten o durumdaki kullanıcı 409. Root hedefi `RootTargetError`. Commit
    çağırana aittir.
    """
    _refuse_root_target(target)
    if target.active == active:
        template = N_("'{name}' zaten etkin.") if active else N_("'{name}' zaten pasif.")
        raise UserStatusError(Translatable(template, name=target.username))
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
        raise UserStatusError(N_("Kendi hesabınızı pasife alamazsınız."))
    result = session.execute(
        update(User)
        .where(
            User.id == target.id,
            User.active.is_(True),
            (User.role != UserRole.HR.value) | (_other_active_hr(target) > 0),
        )
        .values(active=False)
        .execution_options(synchronize_session=False)
    )
    session.refresh(target)
    if result.rowcount != 1:
        raise UserStatusError(LAST_ACTIVE_HR)
    close_user_sessions(session, target.id)
    record_event(
        session,
        EventType.USER_DEACTIVATED,
        actor=actor.username,
        data={"target_user_id": target.id},
    )


def set_user_role(session: Session, target: User, role: UserRole, *, actor: PanelUser) -> None:
    """10.1.8 — İK ile Kullanıcı arasında rol değiştirir; `USER_ROLE_CHANGED` {target_user_id, from,
    to} kullanıcı adıyla. Root ne hedeftir (`RootTargetError`) ne de seçenek (`ValueError`). Kendi
    rolü, aynı role geçiş ve son etkin İK'yı Kullanıcı'ya düşürme 409 (`UserStatusError`; koşullu
    güncelleme, `set_user_active` gibi). Açık oturumlar kapanmaz: rol her istekte okunur, değişiklik
    bir sonraki istekte geçerlidir. Commit çağırana aittir."""
    if role not in ASSIGNABLE_ROLES:
        raise ValueError(f"panelden atanamayan rol: {role!r}")
    _refuse_root_target(target)
    if target.id == actor.id:
        raise UserStatusError(N_("Kendi rolünüzü değiştiremezsiniz."))
    previous = target.role
    if previous == role.value:
        raise UserStatusError(Translatable(N_("'{name}' zaten bu rolde."), name=target.username))
    result = session.execute(
        update(User)
        .where(
            User.id == target.id,
            User.role == previous,
            (User.role != UserRole.HR.value)
            | User.active.is_(False)
            | (_other_active_hr(target) > 0),
        )
        .values(role=role.value)
        .execution_options(synchronize_session=False)
    )
    session.refresh(target)
    if result.rowcount != 1:
        raise UserStatusError(LAST_ACTIVE_HR)
    record_event(
        session,
        EventType.USER_ROLE_CHANGED,
        actor=actor.username,
        data={"target_user_id": target.id, "from": previous, "to": role.value},
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


# --- yetki (10.1.8, 10.1.9; PLAN.md §D115) ----------------------------------------------------


def _writer(user: PanelUser) -> PanelUser:
    if not user.can_write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, READ_ONLY)
    return user


def require_writer(user: Annotated[PanelUser, Depends(require_panel_user)]) -> PanelUser:
    """Yalnız yazmaya götüren panel sayfası (form, onay adımı) ve yazan yol: İK ve root;
    Kullanıcı'ya 403. Kapı sunucudadır — şablonun düğmeyi gizlemesi güvenlik değildir."""
    return _writer(user)


# Yalnız yazmaya götüren `GET` sayfalarının (yükleme ve düzenleme formu, taşıma, atama ve
# birleştirme araması, iki aşamalı onayın ilk adımı) yol bağımlılığı:
# `@router.get(..., dependencies=WRITER_ONLY)`.
WRITER_ONLY = [Depends(require_writer)]


def require_root(user: Annotated[PanelUser, Depends(require_panel_user)]) -> PanelUser:
    """10.1.9 erişim logu: yalnız root; İK ve Kullanıcı için yol yokmuş gibi 404."""
    if not user.is_root:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return user


def panel_write_gate(
    request: Request, user: Annotated[PanelUser, Depends(require_panel_user)]
) -> None:
    """Yönlendirici düzeyinde (`app.main`): güvenli olmayan her yöntem `require_writer`'ın
    kuralından geçer; yeni eklenen her yazan yol kendiliğinden kapıdadır
    (`tests/web/test_roles.py` tarar)."""
    if request.method not in SAFE_METHODS:
        _writer(user)


def api_write_gate(request: Request, user: Annotated[PanelUser, Depends(require_api_user)]) -> None:
    """`panel_write_gate`'in JSON API karşılığı: oturum yoksa 401, Kullanıcı yazarsa 403."""
    if request.method not in SAFE_METHODS:
        _writer(user)
