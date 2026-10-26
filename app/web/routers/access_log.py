"""Erişim logu görünümü (PRD 13.4.1): çalışan bazında kim, ne zaman baktı.

Kaynak `access_log` tablosudur (10.9.2, 12.3.3): panelden belge açma/indirme ve bot üzerinden
gönderilen her belge kullanıcı, zaman, eylem ve kanalla yazılır. Bu görünüm yalnız okur; hiçbir
kayıt ve belge değişmez, günlükte silme ya da düzeltme yolu yoktur.

Yalnız root açar (10.1.9, PLAN.md §D115 e): `require_root` yönlendiricinin bütün yollarındadır; İK
ve Kullanıcı için adres yokmuş gibi 404 döner, bağlantı da görünmez. Kayıt tutma her rolde sürer.

- `GET /access-log` belgelerine bakılmış çalışanları listeler: erişim sayısı, kaç farklı kullanıcı
  baktığı ve son erişim; en son bakılan çalışan üstte. Hiç bakılmamış çalışan listede yoktur.
- `GET /access-log/employees/{employee_id}` bir çalışanın dökümüdür: kullanıcı bazında özet
  (kim, kaç kez açtı/indirdi, en son ne zaman) ve erişimlerin kendisi, en yeni üstte.
- `GET /access-log/logins` "Girişler" sekmesidir (10.1.11, PLAN.md §D125 f): `login_log`
  satırları en yeni üstte, sonuca (`outcome`) ve kullanıcıya (`user`: kimlik ya da `unknown`) göre
  süzülür; üstte kullanıcı bazında son başarılı giriş ve son 24 saatteki başarısız deneme sayısı,
  bilinmeyen adlar tek satırda. Süzgeç düz `GET` formudur (JavaScript gerekmez).

**Çalışan belgenin güncel sahibidir.** `access_log` erişim anındaki sahibi saklamaz; satır belgeye
bağlıdır. Belge başka çalışana taşınırsa (K16) geçmiş erişimleri de yeni sahibinin dökümünde görünür
(PLAN.md §C73). Zamanlar UTC'dir. Kullanıcı satırı silinmez (`access_log.user_id` zorunlu), bu
yüzden adı hep bilinir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AccessAction,
    AccessChannel,
    AccessLog,
    Document,
    Employee,
    KnownDocumentType,
    LoginFailure,
    LoginLog,
    LoginOutcome,
    User,
    utcnow,
)
from app.db.session import get_session
from app.i18n import N_
from app.web.auth import PanelUser, require_panel_user, require_root
from app.web.templating import render_page

router = APIRouter(tags=["access-log"], dependencies=[Depends(require_root)])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]

PAGE_SIZE = 50
EMPLOYEE_NOT_FOUND = N_("Çalışan bulunamadı.")
ACTIVE_KEY = "access_log"

ACTION_LABELS = {AccessAction.VIEW.value: N_("Açtı"), AccessAction.DOWNLOAD.value: N_("İndirdi")}
CHANNEL_LABELS = {
    AccessChannel.WEB.value: N_("Panel"),
    AccessChannel.TELEGRAM.value: N_("Telegram"),
}
TIME_FORMAT = "%d.%m.%Y %H:%M:%S"

LOGINS_PATH = "/access-log/logins"
OUTCOME_LABELS = {
    LoginOutcome.SUCCESS.value: N_("Başarılı"),
    LoginOutcome.FAILED.value: N_("Başarısız"),
    LoginOutcome.LOGOUT.value: N_("Çıkış"),
}
REASON_LABELS = {
    LoginFailure.UNKNOWN_USER.value: N_("Bilinmeyen kullanıcı adı"),
    LoginFailure.WRONG_PASSWORD.value: N_("Yanlış parola"),
    LoginFailure.INACTIVE.value: N_("Pasif kullanıcı"),
}
UNKNOWN_USERS = "unknown"  # kullanıcı süzgecinde bilinmeyen adlar
FAILED_WINDOW = timedelta(hours=24)
AGENT_SHOWN = 60  # tarayıcı bilgisinin tabloda görünen kısmı; tamamı title özniteliğinde


@dataclass(frozen=True, slots=True)
class EmployeeAccessRow:
    """Belgelerine bakılmış bir çalışan: sayılar gösterime hazırdır."""

    employee_id: str
    name: str
    accesses: int
    viewers: int
    last_access: str
    url: str


@dataclass(frozen=True, slots=True)
class AccessOverview:
    rows: list[EmployeeAccessRow]
    total: int
    page: int
    page_count: int
    previous_url: str | None
    next_url: str | None


@dataclass(frozen=True, slots=True)
class ViewerRow:
    """Bir çalışanın belgelerine bakan kullanıcı ve bakışlarının özeti."""

    username: str
    views: int
    downloads: int
    last_access: str


@dataclass(frozen=True, slots=True)
class AccessEntry:
    """Tek bir erişim: kim, ne zaman, hangi belgeyi, nasıl ve hangi kanaldan."""

    ts: str
    username: str
    type_name: str
    file_name: str | None  # belge kalıcı silindiyse boş; satır kalır (10.5.12)
    action: str
    channel: str


@dataclass(frozen=True, slots=True)
class EmployeeAccessLog:
    employee_id: str
    name: str
    total: int
    viewers: list[ViewerRow]
    entries: list[AccessEntry]
    page: int
    page_count: int
    previous_url: str | None
    next_url: str | None


def _stamp(ts: datetime) -> str:
    return f"{ts.strftime(TIME_FORMAT)} UTC"


def _page_count(total: int) -> int:
    return max(1, -(-total // PAGE_SIZE))


def _page_url(path: str, page: int) -> str:
    return f"{path}?{urlencode({'page': page})}" if page > 1 else path


def _neighbours(path: str, page: int, page_count: int) -> tuple[str | None, str | None]:
    previous_url = _page_url(path, page - 1) if page > 1 else None
    next_url = _page_url(path, page + 1) if page < page_count else None
    return previous_url, next_url


def build_overview(session: Session, page: int = 1) -> AccessOverview:
    """Belgelerine bakılmış çalışanlar, son erişimi en yeni olan üstte (eşitlikte E numarası)."""
    total = (
        session.scalar(
            select(func.count(func.distinct(Document.employee_id)))
            .select_from(AccessLog)
            .join(Document, Document.id == AccessLog.document_id)
        )
        or 0
    )
    page_count = _page_count(total)
    page = min(max(page, 1), page_count)
    last_access = func.max(AccessLog.ts)
    grouped = (
        select(
            Document.employee_id,
            func.count(AccessLog.id),
            func.count(func.distinct(AccessLog.user_id)),
            last_access,
        )
        .join(Document, Document.id == AccessLog.document_id)
        .group_by(Document.employee_id)
        .order_by(last_access.desc(), Document.employee_id)
        .limit(PAGE_SIZE)
        .offset((page - 1) * PAGE_SIZE)
    )
    stats = session.execute(grouped).all()
    employees = {
        employee.id: employee
        for employee in session.scalars(
            select(Employee).where(Employee.id.in_([row[0] for row in stats]))
        )
    }
    rows = [
        EmployeeAccessRow(
            employee_id=employee_id,
            name=f"{employees[employee_id].given_names} {employees[employee_id].surname}",
            accesses=accesses,
            viewers=viewers,
            last_access=_stamp(last),
            url=f"/access-log/employees/{employee_id}",
        )
        for employee_id, accesses, viewers, last in stats
    ]
    previous_url, next_url = _neighbours("/access-log", page, page_count)
    return AccessOverview(
        rows=rows,
        total=total,
        page=page,
        page_count=page_count,
        previous_url=previous_url,
        next_url=next_url,
    )


def build_employee_log(
    session: Session, employee_id: str, page: int = 1
) -> EmployeeAccessLog | None:
    """Çalışanın belgelerine yapılmış erişimler; çalışan yoksa `None`."""
    employee = session.get(Employee, employee_id)
    if employee is None:
        return None
    of_employee = Document.employee_id == employee_id
    total = (
        session.scalar(
            select(func.count(AccessLog.id))
            .join(Document, Document.id == AccessLog.document_id)
            .where(of_employee)
        )
        or 0
    )
    is_view = case((AccessLog.action == AccessAction.VIEW.value, 1), else_=0)
    is_download = case((AccessLog.action == AccessAction.DOWNLOAD.value, 1), else_=0)
    last_access = func.max(AccessLog.ts)
    viewers = [
        ViewerRow(username=username, views=views, downloads=downloads, last_access=_stamp(last))
        for username, views, downloads, last in session.execute(
            select(User.username, func.sum(is_view), func.sum(is_download), last_access)
            .join(User, User.id == AccessLog.user_id)
            .join(Document, Document.id == AccessLog.document_id)
            .where(of_employee)
            .group_by(User.id, User.username)
            .order_by(last_access.desc(), User.username)
        )
    ]
    page_count = _page_count(total)
    page = min(max(page, 1), page_count)
    entries = [
        AccessEntry(
            ts=_stamp(access.ts),
            username=username,
            type_name=type_name,
            # 10.5.12: kalıcı silinen belgenin satırı kalır, dosya adı kalmaz.
            file_name=PurePosixPath(document.path).name if document.path is not None else None,
            action=ACTION_LABELS.get(access.action, access.action),
            channel=CHANNEL_LABELS.get(access.channel, access.channel),
        )
        for access, document, username, type_name in session.execute(
            select(AccessLog, Document, User.username, KnownDocumentType.name)
            .join(Document, Document.id == AccessLog.document_id)
            .join(User, User.id == AccessLog.user_id)
            .join(KnownDocumentType, KnownDocumentType.slug == Document.type_slug)
            .where(of_employee)
            .order_by(AccessLog.ts.desc(), AccessLog.id.desc())
            .limit(PAGE_SIZE)
            .offset((page - 1) * PAGE_SIZE)
        )
    ]
    previous_url, next_url = _neighbours(f"/access-log/employees/{employee_id}", page, page_count)
    return EmployeeAccessLog(
        employee_id=employee.id,
        name=f"{employee.given_names} {employee.surname}",
        total=total,
        viewers=viewers,
        entries=entries,
        page=page,
        page_count=page_count,
        previous_url=previous_url,
        next_url=next_url,
    )


@dataclass(frozen=True, slots=True)
class LoginEntry:
    """Tek bir giriş kaydı: zaman, denenen ad, sonuç, neden, IP, tarayıcı."""

    ts: str
    username: str
    known: bool  # ad bir kullanıcıya ait mi (bilinmeyende rozet)
    outcome: str
    outcome_label: str
    reason_label: str | None
    ip: str | None
    agent: str | None  # kısaltılmış
    agent_full: str | None


@dataclass(frozen=True, slots=True)
class LoginSummaryRow:
    """Kullanıcı bazında özet; `username` boşsa bilinmeyen adların toplu satırıdır."""

    username: str | None
    last_success: str | None
    failed_recent: int


@dataclass(frozen=True, slots=True)
class FilterLink:
    label: str
    url: str
    active: bool


@dataclass(frozen=True, slots=True)
class UserOption:
    value: str
    label: str | None  # boşsa "Tüm kullanıcılar" ya da "Bilinmeyen adlar" (şablon çevirir)
    selected: bool


@dataclass(frozen=True, slots=True)
class LoginOverview:
    entries: list[LoginEntry]
    summary: list[LoginSummaryRow]
    states: list[FilterLink]
    users: list[UserOption]
    outcome: str
    user_filter: str
    total: int
    page: int
    page_count: int
    previous_url: str | None
    next_url: str | None


def _logins_url(outcome: str, user_filter: str, page: int = 1) -> str:
    query = {
        key: value
        for key, value in (("outcome", outcome), ("user", user_filter), ("page", page))
        if value and value != 1
    }
    return f"{LOGINS_PATH}?{urlencode(query)}" if query else LOGINS_PATH


def _login_summary(session: Session, now: datetime) -> list[LoginSummaryRow]:
    last_success = func.max(
        case((LoginLog.outcome == LoginOutcome.SUCCESS.value, LoginLog.ts), else_=None)
    )
    recent_failed = func.sum(
        case(
            (
                (LoginLog.outcome == LoginOutcome.FAILED.value)
                & (LoginLog.ts >= now - FAILED_WINDOW),
                1,
            ),
            else_=0,
        )
    )
    rows = [
        LoginSummaryRow(
            username=username,
            last_success=_stamp(last) if last is not None else None,
            failed_recent=failed or 0,
        )
        for username, last, failed in session.execute(
            select(User.username, last_success, recent_failed)
            .join(User, User.id == LoginLog.user_id)
            .group_by(User.id, User.username)
            .order_by(User.username)
        )
    ]
    attempts, failed = session.execute(
        select(func.count(LoginLog.id), recent_failed).where(LoginLog.user_id.is_(None))
    ).one()
    if attempts:
        rows.append(LoginSummaryRow(username=None, last_success=None, failed_recent=failed or 0))
    return rows


def build_logins(
    session: Session,
    *,
    outcome: str = "",
    user_filter: str = "",
    page: int = 1,
    now: datetime | None = None,
) -> LoginOverview:
    """10.1.11 — giriş kaydı, en yeni üstte; tanınmayan süzgeç değeri "tümü" sayılır."""
    if outcome not in OUTCOME_LABELS:
        outcome = ""
    known_users = session.execute(
        select(User.id, User.username)
        .where(User.id.in_(select(LoginLog.user_id).where(LoginLog.user_id.is_not(None))))
        .order_by(User.username)
    ).all()
    has_unknown = (
        session.scalar(select(LoginLog.id).where(LoginLog.user_id.is_(None)).limit(1)) is not None
    )
    by_id = {str(user_id): user_id for user_id, _ in known_users}
    if user_filter not in by_id and not (user_filter == UNKNOWN_USERS and has_unknown):
        user_filter = ""

    conditions = []
    if outcome:
        conditions.append(LoginLog.outcome == outcome)
    if user_filter == UNKNOWN_USERS:
        conditions.append(LoginLog.user_id.is_(None))
    elif user_filter:
        conditions.append(LoginLog.user_id == by_id[user_filter])
    total = session.scalar(select(func.count(LoginLog.id)).where(*conditions)) or 0
    page_count = _page_count(total)
    page = min(max(page, 1), page_count)
    entries = []
    for row in session.scalars(
        select(LoginLog)
        .where(*conditions)
        .order_by(LoginLog.ts.desc(), LoginLog.id.desc())
        .limit(PAGE_SIZE)
        .offset((page - 1) * PAGE_SIZE)
    ):
        agent = row.user_agent
        short = agent if agent is None or len(agent) <= AGENT_SHOWN else agent[:AGENT_SHOWN] + "…"
        entries.append(
            LoginEntry(
                ts=_stamp(row.ts),
                username=row.username,
                known=row.user_id is not None,
                outcome=row.outcome,
                outcome_label=OUTCOME_LABELS.get(row.outcome, row.outcome),
                reason_label=REASON_LABELS.get(row.reason, row.reason) if row.reason else None,
                ip=row.ip,
                agent=short,
                agent_full=agent,
            )
        )
    states = [
        FilterLink(label=label, url=_logins_url(value, user_filter), active=value == outcome)
        for value, label in (("", N_("Tümü")), *OUTCOME_LABELS.items())
    ]
    users = [UserOption(value="", label=None, selected=not user_filter)]
    users += [
        UserOption(value=str(user_id), label=username, selected=str(user_id) == user_filter)
        for user_id, username in known_users
    ]
    if has_unknown:
        users.append(
            UserOption(value=UNKNOWN_USERS, label=None, selected=user_filter == UNKNOWN_USERS)
        )
    previous_url = _logins_url(outcome, user_filter, page - 1) if page > 1 else None
    next_url = _logins_url(outcome, user_filter, page + 1) if page < page_count else None
    return LoginOverview(
        entries=entries,
        summary=_login_summary(session, now or utcnow()),
        states=states,
        users=users,
        outcome=outcome,
        user_filter=user_filter,
        total=total,
        page=page,
        page_count=page_count,
        previous_url=previous_url,
        next_url=next_url,
    )


@router.get("/access-log", response_class=HTMLResponse)
def access_log_page(
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
) -> HTMLResponse:
    overview = build_overview(session, page)
    # Okuma işlemi de SQLite'ta yazma kilidini tutar (`app.db.session`): sayfa çizilirken
    # arka plandaki bir işleyici beklemesin.
    session.rollback()
    return render_page(request, "access_log.html", user=user, active=ACTIVE_KEY, overview=overview)


@router.get("/access-log/employees/{employee_id}", response_class=HTMLResponse)
def employee_access_log_page(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
) -> HTMLResponse:
    log = build_employee_log(session, employee_id, page)
    session.rollback()
    if log is None:
        return render_page(
            request,
            "access_log_employee.html",
            user=user,
            active=ACTIVE_KEY,
            status_code=status.HTTP_404_NOT_FOUND,
            error=EMPLOYEE_NOT_FOUND,
        )
    return render_page(request, "access_log_employee.html", user=user, active=ACTIVE_KEY, log=log)


@router.get(LOGINS_PATH, response_class=HTMLResponse)
def logins_page(
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    outcome: Annotated[str, Query(max_length=16)] = "",
    user_filter: Annotated[str, Query(alias="user", max_length=16)] = "",
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
) -> HTMLResponse:
    logins = build_logins(session, outcome=outcome, user_filter=user_filter, page=page)
    session.rollback()
    return render_page(
        request, "access_log_logins.html", user=user, active=ACTIVE_KEY, logins=logins
    )
