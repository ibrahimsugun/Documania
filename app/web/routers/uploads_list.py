"""Yükleme listesi (PRD 10.3.3, 10.3.6, 10.3.7): Yüklemeler menüsü partileri en yeni üstte
listeler.

`GET /uploads` her partiyi tek satırda gösterir: alındığı an, kanal, yükleyen, bağlam çalışanı
(profiline bağlantı), dosya ve sayfa sayısı, durum ve **çözülmemiş** kuyruk öğelerinin sayısı
(Unknown, Unreadable, Unresolved ayrı sütunlarda; sıfırsa boş). Parti kimliği partinin detay
sayfasına (10.3.1) gider. Durumlar kendi adlarıyla görünür: işlemdeki beş durum "işleniyor"
altında toplanmaz, `partial` ile `failed` da `done`'dan ayrıdır. Zamanlar panelin öbür
sayfalarındaki gibi UTC'dir; listede dakikaya kadar yazılır (`2026-10-08 12:07`), saniye ve "UTC"
eki detay sayfasında kalır.

**Süzme (GET).** `status` (`processing` | `done` | `partial` | `failed` | `cancelled`;
`processing` işlemdeki beş durumun hepsidir, `cancelled` iptal edilen partilerdir — 10.3.6),
`from` / `to` (`YYYY-MM-DD`, ikisi de dahil gün, UTC) ve `dismissed`
(10.3.4). Yoksayılan parti varsayılan olarak listelenmez; `dismissed=only` yalnız yoksayılanları,
`dismissed=include` hepsini gösterir — yoksayılan parti bulunamaz hâle gelmez, satırında
"Yoksayıldı" yazar. Geçersiz değer
400 olmaz: o süzgeç yok sayılır ve formun üstünde uyarı çıkar; geçerli süzgeçler uygulanmaya devam
eder. Başlangıç günü bitiş gününden sonraysa tarih süzgeci bütünüyle yok sayılır. Sayfalama
`PAGE_SIZE` (50) satırlıktır; aralığın ötesindeki sayfa numarası son sayfayı, sayı olmayan ya da
1'den küçük numara ilk sayfayı verir. Sayfa bağlantıları geçerli süzgeçleri taşır.

**Sayılar tek sorguyla gelir.** Dosya, sayfa ve kuyruk sayıları sayfadaki her satır için bağıntılı
skaler alt sorgudur; liste, satır sayısından bağımsız olarak sabit sayıda sorguyla çizilir (N+1
yok).

Sayfa partileri okur; toplu işlem, silme ya da canlı yenileme sunmaz. Tek yazdığı otomatik
iptaldir (10.3.7): sayfa açılırken alındığından beri `UPLOAD_TIMEOUT_SECONDS` (600) geçmiş bitmemiş
partiler `system` adına iptal edilir ve `UPLOAD_CANCELLED` yazılır
(`app.web.routers.upload_page.expire_stale_uploads`) — işleyici kapalıyken de takılan parti
yakalanır. Dosya adı ve belge
içeriği ya da kişisel alan gösterilmez — dosya adı kişi adı taşıyabilir, bu yüzden yalnız sayılar
görünür (K11, K17).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import ColumnElement, ScalarSelect, func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Employee, Page, QueueItem, QueueKind, Upload, UploadFile, UploadStatus
from app.db.session import get_session
from app.i18n import N_
from app.web.auth import PanelUser, require_panel_user
from app.web.routers.upload_page import QUEUE_LABELS, Clock, expire_stale_uploads
from app.web.routers.uploads import UPLOAD_CHANNEL
from app.web.templating import render_page

router = APIRouter(tags=["uploads-list"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]

PAGE_SIZE = 50
ACTIVE_KEY = "uploads"
PROCESSING_FILTER = "processing"

# Bot (`app.telegram.handlers`) kanalı "telegram" yazar; öbür kanal panelin kendisidir.
CHANNEL_LABELS = {UPLOAD_CHANNEL: N_("Panel"), "telegram": N_("Telegram")}
STATUS_LABELS: dict[str, str] = {
    UploadStatus.RECEIVED.value: N_("Alındı"),
    UploadStatus.RENDERING.value: N_("Sayfalar hazırlanıyor"),
    UploadStatus.ANALYZING.value: N_("Analiz ediliyor"),
    UploadStatus.PLANNING.value: N_("Plan hazırlanıyor"),
    UploadStatus.EXECUTING.value: N_("Plan uygulanıyor"),
    UploadStatus.DONE.value: N_("Tamamlandı"),
    UploadStatus.PARTIAL.value: N_("Kısmen tamamlandı"),
    UploadStatus.FAILED.value: N_("İşlenemedi"),
    UploadStatus.CANCELLED.value: N_("İptal edildi"),
}
PROCESSING_STATUSES = (
    UploadStatus.RECEIVED,
    UploadStatus.RENDERING,
    UploadStatus.ANALYZING,
    UploadStatus.PLANNING,
    UploadStatus.EXECUTING,
)
# Süzgeç değeri → (formdaki ad, o süzgeçle listelenen durumlar).
STATUS_FILTERS: dict[str, tuple[str, tuple[UploadStatus, ...]]] = {
    PROCESSING_FILTER: (N_("İşleniyor"), PROCESSING_STATUSES),
    UploadStatus.DONE.value: (N_("Tamamlandı"), (UploadStatus.DONE,)),
    UploadStatus.PARTIAL.value: (N_("Kısmi"), (UploadStatus.PARTIAL,)),
    UploadStatus.FAILED.value: (N_("Hata"), (UploadStatus.FAILED,)),
    UploadStatus.CANCELLED.value: (N_("İptal"), (UploadStatus.CANCELLED,)),
}

# 10.3.4 — süzgeç değeri → formdaki ad; değer yoksa yoksayılan parti listelenmez.
DISMISSED_ONLY = "only"
DISMISSED_INCLUDE = "include"
DISMISSED_FILTERS: dict[str, str] = {
    DISMISSED_ONLY: N_("Yalnız yoksayılanlar"),
    DISMISSED_INCLUDE: N_("Yoksayılanlar dahil"),
}

INVALID_STATUS_WARNING = N_("Durum süzgeci tanınmadı; yok sayıldı.")
INVALID_FROM_WARNING = N_("Başlangıç günü geçerli bir tarih değil (YYYY-AA-GG); yok sayıldı.")
INVALID_TO_WARNING = N_("Bitiş günü geçerli bir tarih değil (YYYY-AA-GG); yok sayıldı.")
REVERSED_RANGE_WARNING = N_("Başlangıç günü bitiş gününden sonra; tarih süzgeci yok sayıldı.")
INVALID_DISMISSED_WARNING = N_("Yoksayılanlar süzgeci tanınmadı; yok sayıldı.")


@dataclass(frozen=True, slots=True)
class QueueCount:
    """Bir kuyruk türündeki çözülmemiş öğe sayısı; sıfır boş hücredir (`shown` yanlış)."""

    kind: str
    label: str
    count: int

    @property
    def shown(self) -> bool:
        return self.count > 0


@dataclass(frozen=True, slots=True)
class UploadRow:
    """Bir parti: sayılar ve etiketler gösterime hazırdır. Dosya adı bilerek yoktur."""

    id: str
    url: str
    created_at: str
    channel: str
    uploaded_by: str | None
    context_employee_id: str | None
    context_employee_name: str | None
    context_employee_url: str | None
    file_count: int
    page_count: int
    status: str
    status_label: str
    queue_counts: list[QueueCount]
    dismissed: bool = False


@dataclass(frozen=True, slots=True)
class UploadFilter:
    """Uygulanan (geçerli) süzgeçler; uyarılar yok sayılan değerleri anlatır."""

    status: str | None
    date_from: date | None
    date_to: date | None
    warnings: list[str]
    dismissed: str | None = None  # `DISMISSED_FILTERS` anahtarı; yoksa yoksayılan gizli

    @property
    def active(self) -> bool:
        return (
            self.status is not None
            or self.date_from is not None
            or self.date_to is not None
            or self.dismissed is not None
        )

    def params(self) -> dict[str, str]:
        """Sayfa bağlantılarının taşıdığı süzgeçler (yalnız geçerli olanlar)."""
        params: dict[str, str] = {}
        if self.status is not None:
            params["status"] = self.status
        if self.date_from is not None:
            params["from"] = self.date_from.isoformat()
        if self.date_to is not None:
            params["to"] = self.date_to.isoformat()
        if self.dismissed is not None:
            params["dismissed"] = self.dismissed
        return params


@dataclass(frozen=True, slots=True)
class UploadListing:
    filter: UploadFilter
    rows: list[UploadRow]
    total: int
    page: int
    page_count: int
    previous_url: str | None
    next_url: str | None
    queue_headers: list[str]


def _format_minute(moment: datetime) -> str:
    """Listenin tarih hücresi: UTC, dakikaya kadar (`2026-10-08 12:07`)."""
    return f"{moment:%Y-%m-%d %H:%M}"


def _parse_day(value: str | None) -> tuple[date | None, bool]:
    """`YYYY-MM-DD` gününü çözer; (gün, geçersiz mi). Boş değer süzgeç yok demektir."""
    if value is None or not value.strip():
        return None, False
    try:
        return date.fromisoformat(value.strip()), False
    except ValueError:
        return None, True


def parse_filter(
    status: str | None,
    date_from: str | None,
    date_to: str | None,
    dismissed: str | None = None,
) -> UploadFilter:
    """İstek değerlerini süzgece çevirir; geçersiz değeri atar ve uyarıya yazar."""
    warnings: list[str] = []
    status_value = status.strip() if status is not None else ""
    if status_value and status_value not in STATUS_FILTERS:
        warnings.append(INVALID_STATUS_WARNING)
    dismissed_value = dismissed.strip() if dismissed is not None else ""
    if dismissed_value and dismissed_value not in DISMISSED_FILTERS:
        warnings.append(INVALID_DISMISSED_WARNING)
    start, start_invalid = _parse_day(date_from)
    end, end_invalid = _parse_day(date_to)
    if start_invalid:
        warnings.append(INVALID_FROM_WARNING)
    if end_invalid:
        warnings.append(INVALID_TO_WARNING)
    if start is not None and end is not None and start > end:
        warnings.append(REVERSED_RANGE_WARNING)
        start = end = None
    return UploadFilter(
        status=status_value if status_value in STATUS_FILTERS else None,
        date_from=start,
        date_to=end,
        warnings=warnings,
        dismissed=dismissed_value if dismissed_value in DISMISSED_FILTERS else None,
    )


def _parse_page(value: str | None) -> int:
    """Sayfa numarası; sayı olmayan ya da 1'den küçük değer ilk sayfadır."""
    try:
        return max(1, int(value)) if value is not None else 1
    except ValueError:
        return 1


def _conditions(applied: UploadFilter) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if applied.status is not None:
        statuses = [each.value for each in STATUS_FILTERS[applied.status][1]]
        conditions.append(Upload.status.in_(statuses))
    if applied.date_from is not None:
        conditions.append(Upload.created_at >= _day_start(applied.date_from))
    if applied.date_to is not None:
        conditions.append(Upload.created_at < _day_start(applied.date_to + timedelta(days=1)))
    if applied.dismissed is None:
        conditions.append(Upload.dismissed_at.is_(None))
    elif applied.dismissed == DISMISSED_ONLY:
        conditions.append(Upload.dismissed_at.is_not(None))
    return conditions


def _day_start(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _file_count() -> ScalarSelect[int]:
    return (
        select(func.count(UploadFile.id)).where(UploadFile.upload_id == Upload.id).scalar_subquery()
    )


def _page_count() -> ScalarSelect[int]:
    return (
        select(func.count(Page.id))
        .join(UploadFile, UploadFile.id == Page.file_id)
        .where(UploadFile.upload_id == Upload.id)
        .scalar_subquery()
    )


def _open_queue_count(kind: QueueKind) -> ScalarSelect[int]:
    return (
        select(func.count(QueueItem.id))
        .where(
            QueueItem.upload_id == Upload.id,
            QueueItem.kind == kind.value,
            QueueItem.resolved_at.is_(None),
        )
        .scalar_subquery()
    )


def _page_url(applied: UploadFilter, page: int) -> str:
    params = applied.params()
    if page > 1:
        params["page"] = str(page)
    return f"/uploads?{urlencode(params)}" if params else "/uploads"


def build_listing(
    session: Session,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: str | None = None,
    dismissed: str | None = None,
) -> UploadListing:
    """Partileri en yeni üstte listeler; süzgeç ve sayfa numarası yumuşak çözülür. Yoksayılan parti
    yalnız `dismissed` süzgeciyle listelenir (10.3.4)."""
    applied = parse_filter(status, date_from, date_to, dismissed)
    conditions = _conditions(applied)
    total = session.scalar(select(func.count(Upload.id)).where(*conditions)) or 0
    page_count = max(1, -(-total // PAGE_SIZE))
    number = min(_parse_page(page), page_count)
    kinds = tuple(QueueKind)
    counts = [_open_queue_count(kind) for kind in kinds]
    statement = (
        select(
            Upload,
            Employee.given_names,
            Employee.surname,
            _file_count(),
            _page_count(),
            *counts,
        )
        .outerjoin(Employee, Employee.id == Upload.context_employee_id)
        .where(*conditions)
        .order_by(Upload.created_at.desc(), Upload.id.desc())
        .limit(PAGE_SIZE)
        .offset((number - 1) * PAGE_SIZE)
    )
    rows = []
    for upload, given_names, surname, file_count, pages, *open_counts in session.execute(statement):
        has_context = upload.context_employee_id is not None
        rows.append(
            UploadRow(
                id=upload.id,
                url=f"/uploads/{upload.id}",
                created_at=_format_minute(upload.created_at),
                channel=CHANNEL_LABELS.get(upload.channel, upload.channel),
                uploaded_by=upload.uploaded_by or None,
                context_employee_id=upload.context_employee_id,
                # Bağlam çalışanı silinemez (FK), ama adı boşsa E numarası okunur kalır.
                context_employee_name=(
                    f"{given_names} {surname}".strip() or upload.context_employee_id
                    if has_context
                    else None
                ),
                context_employee_url=(
                    f"/employees/{upload.context_employee_id}" if has_context else None
                ),
                file_count=file_count,
                page_count=pages,
                status=upload.status,
                status_label=STATUS_LABELS.get(upload.status, upload.status),
                queue_counts=[
                    QueueCount(kind=kind.value, label=QUEUE_LABELS[kind.value], count=count)
                    for kind, count in zip(kinds, open_counts, strict=True)
                ],
                dismissed=upload.dismissed_at is not None,
            )
        )
    return UploadListing(
        filter=applied,
        rows=rows,
        total=total,
        page=number,
        page_count=page_count,
        previous_url=_page_url(applied, number - 1) if number > 1 else None,
        next_url=_page_url(applied, number + 1) if number < page_count else None,
        queue_headers=[QUEUE_LABELS[kind.value] for kind in kinds],
    )


@router.get("/uploads", response_class=HTMLResponse)
def uploads_list_page(
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    now: Clock,
    status: str | None = None,
    date_from: Annotated[str | None, Query(alias="from")] = None,
    date_to: Annotated[str | None, Query(alias="to")] = None,
    page: str | None = None,
    dismissed: str | None = None,
) -> HTMLResponse:
    # 10.3.7: bu GET bilerek yazar — süresi dolan partiler önce iptal edilir (modül açıklaması).
    expire_stale_uploads(session, settings, now)
    listing = build_listing(session, status, date_from, date_to, page, dismissed)
    # Okuma işlemi de SQLite'ta yazma kilidini tutar (`app.db.session`): sayfa çizilirken
    # arka plandaki bir işleyici beklemesin.
    session.rollback()
    return render_page(
        request,
        "uploads_list.html",
        user=user,
        active=ACTIVE_KEY,
        listing=listing,
        status_filters=[(value, name) for value, (name, _) in STATUS_FILTERS.items()],
        dismissed_filters=list(DISMISSED_FILTERS.items()),
    )
