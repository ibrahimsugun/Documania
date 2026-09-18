"""Çalışan listesi ve arama (PRD 10.4.1, 10.4.2).

`GET /employees` çalışanları ad, orijinal yazım, uyruk, belge sayısı ve durumla listeler (10.4.1).
`q` verilirse liste aranan metne uyanlarla daralır (10.4.2): metin boşlukla terimlere ayrılır, her
terim çalışanın **en az bir** alanında geçmelidir (terimler arası "ve", alanlar arası "veya");
böylece `ivan petrov` de `petrov ivan` da aynı kişiyi bulur, `ivan pasaport` pasaportu olan Ivan'ı.
Aranan alanlar:

- ad: `given_names`, `surname`, `other_names`;
- alias (`employee_aliases`) ve orijinal yazım: alias'ın ham yazımının yanında normalize anahtarı
  da (`app.matching.names.normalize_name`) aranır — harf büyüklüğü, aksan ve yazı sistemi
  (Kiril ↔ Latin) farkı aramayı bozmaz; orijinal yazım hem çalışan kaydında hem alias olarak aranır;
- belge numarası (`employee_identifiers.value`): numara saklanırken normalize edilir (§20.2.1),
  aranan metin de aynı biçime indirilir — boşluk, tire ve nokta farkı yok sayılır;
- belge türü: katalogdaki tür adı, dosya etiketi ve `slug`; çalışanın **etkin** bir belgesi o
  türdeyse çalışan uyar.

"Belge sayısı" çalışanın etkin belgeleridir: eski sürüm (`superseded`, K18) ve arşive taşınmış
(`archived`, K16) belge çalışanın klasöründe durmadığı için sayılmaz. Sayfa yalnız okur: belge
içeriği ya da çalışan kaydı değiştirilmez (K11, K17).

HTMX isteği (`HX-Request`) yalnız sonuç parçasını (`employees_results.html`) alır, tarayıcı isteği
tam sayfayı; ikisi de aynı adrestedir, bu yüzden yanıt `Vary: HX-Request` taşır. Sayfalama düz
bağlantıdır; JavaScript kapalıyken de arama form gönderimiyle çalışır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import ColumnElement, and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeAlias,
    EmployeeIdentifier,
    KnownDocumentType,
)
from app.db.session import get_session
from app.matching.match import normalize_document_number
from app.matching.names import EmptyNameError, normalize_name
from app.web.auth import PanelUser, require_panel_user
from app.web.templating import MENU_BY_KEY, render_page

router = APIRouter(tags=["employees"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]

PAGE_SIZE = 25
MAX_QUERY_LENGTH = 100
# Her terim birkaç EXISTS alt sorgusu açar; uzun bir metin sorguyu gereksiz büyütmesin.
MAX_TERMS = 6

STATUS_LABELS = {"active": "Aktif"}


@dataclass(frozen=True, slots=True)
class EmployeeRow:
    id: str
    name: str
    original_script_name: str | None
    nationality: str | None
    document_count: int
    status: str
    status_label: str


@dataclass(frozen=True, slots=True)
class EmployeeListing:
    query: str
    rows: list[EmployeeRow]
    total: int
    page: int
    page_count: int
    previous_url: str | None
    next_url: str | None


def search_terms(query: str) -> list[str]:
    """Aranan metni boşlukla terimlere böler; en çok `MAX_TERMS` terim alınır."""
    return query.split()[:MAX_TERMS]


def _matching_type_slugs(session: Session, term: str) -> list[str]:
    """Adı, dosya etiketi ya da slug'ı terimi içeren katalog türleri.

    Katalog küçüktür ve Türkçe büyük/küçük harf (`İkamet`) SQLite'ta SQL ile karşılaştırılamaz;
    eşleşme Python'da, isim eşleştirmeyle aynı katlamayla yapılır.
    """
    try:
        folded_term = normalize_name(term)
    except EmptyNameError:
        return []
    slugs = []
    for entry in session.scalars(select(KnownDocumentType)):
        for text in (entry.name, entry.file_label, entry.slug):
            try:
                if folded_term in normalize_name(text):
                    slugs.append(entry.slug)
                    break
            except EmptyNameError:
                continue
    return slugs


def _term_matches(session: Session, term: str) -> ColumnElement[bool]:
    """Çalışanın bu terimi taşıdığı alanlardan herhangi biri — bkz. modül açıklaması."""
    name_fields: list[ColumnElement[bool]] = [
        Employee.given_names.icontains(term, autoescape=True),
        Employee.surname.icontains(term, autoescape=True),
        Employee.other_names.icontains(term, autoescape=True),
        Employee.original_script_name.icontains(term, autoescape=True),
    ]
    alias_match: ColumnElement[bool] = EmployeeAlias.raw_name.icontains(term, autoescape=True)
    try:
        folded_words = normalize_name(term).split()
    except EmptyNameError:
        folded_words = []
    if folded_words:
        alias_match = or_(
            alias_match,
            and_(
                *(
                    EmployeeAlias.normalized_name.contains(word, autoescape=True)
                    for word in folded_words
                )
            ),
        )
    predicates = [
        *name_fields,
        exists().where(EmployeeAlias.employee_id == Employee.id, alias_match),
    ]
    number = normalize_document_number(term)
    if number:
        predicates.append(
            exists().where(
                EmployeeIdentifier.employee_id == Employee.id,
                EmployeeIdentifier.value.contains(number, autoescape=True),
            )
        )
    type_slugs = _matching_type_slugs(session, term)
    if type_slugs:
        predicates.append(
            exists().where(
                Document.employee_id == Employee.id,
                Document.status == DocumentStatus.ACTIVE.value,
                Document.type_slug.in_(type_slugs),
            )
        )
    return or_(*predicates)


def _page_url(query: str, page: int) -> str:
    params = {"q": query} if query else {}
    if page > 1:
        params["page"] = str(page)
    return "/employees" + (f"?{urlencode(params)}" if params else "")


def list_employees(session: Session, query: str = "", page: int = 1) -> EmployeeListing:
    """10.4.1/10.4.2 — çalışanların `page`. sayfası; `query` boşsa hepsi, doluysa uyanlar.

    Sayfa sayısını aşan `page` son sayfaya indirilir. Sıra soyad, ad, çalışan numarasıdır.
    """
    query = " ".join(query.split())
    filters = [_term_matches(session, term) for term in search_terms(query)]
    total = session.scalar(select(func.count()).select_from(Employee).where(*filters)) or 0
    page_count = max(1, -(-total // PAGE_SIZE))
    page = min(max(page, 1), page_count)
    document_count = (
        select(func.count(Document.id))
        .where(
            Document.employee_id == Employee.id,
            Document.status == DocumentStatus.ACTIVE.value,
        )
        .correlate(Employee)
        .scalar_subquery()
    )
    found = session.execute(
        select(Employee, document_count)
        .where(*filters)
        .order_by(func.lower(Employee.surname), func.lower(Employee.given_names), Employee.id)
        .limit(PAGE_SIZE)
        .offset((page - 1) * PAGE_SIZE)
    ).all()
    rows = [
        EmployeeRow(
            id=employee.id,
            name=f"{employee.given_names} {employee.surname}",
            original_script_name=employee.original_script_name,
            nationality=employee.nationality,
            document_count=count,
            status=employee.status,
            status_label=STATUS_LABELS.get(employee.status, employee.status),
        )
        for employee, count in found
    ]
    return EmployeeListing(
        query=query,
        rows=rows,
        total=total,
        page=page,
        page_count=page_count,
        previous_url=_page_url(query, page - 1) if page > 1 else None,
        next_url=_page_url(query, page + 1) if page < page_count else None,
    )


def _wants_fragment(request: Request) -> bool:
    # Geçmiş geri yüklemesi (önbellek boşsa) HTMX'in `HX-Request`'iyle gelir ama tam sayfa bekler.
    return (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )


@router.get("/employees", response_class=HTMLResponse)
def employees_page(
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str, Query(max_length=MAX_QUERY_LENGTH)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
) -> HTMLResponse:
    listing = list_employees(session, q, page)
    entry = MENU_BY_KEY["employees"]
    if _wants_fragment(request):
        response = render_page(request, "employees_results.html", user=None, listing=listing)
    else:
        response = render_page(
            request,
            "employees.html",
            user=user,
            active=entry.key,
            entry=entry,
            listing=listing,
        )
    response.headers["Vary"] = "HX-Request"
    return response
