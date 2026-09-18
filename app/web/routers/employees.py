"""Çalışan listesi, arama ve çalışan profili (PRD 10.4.1, 10.4.2, 10.5.1-10.5.4).

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

`GET /employees/{employee_id}` çalışanın profil sayfasıdır (10.5.1): CV benzeri kart profil
fotoğrafını, adı, soyadı, diğer isimleri, orijinal yazımı, vatandaşlığı, doğum tarihi ve yaşı,
iletişim bilgilerini ve belge numaralarını gösterir; bilinmeyen alan gizlenmez, "—" görünür.
Çalışanın etkin bir `profile_picture` belgesi yoksa kart yer tutucu çizer ve belgeyi eksik olarak
işaretler (10.5.4). Belge listesi çalışanın **tüm** belgelerini (etkin, eski sürüm, arşivlenmiş)
gösterir; her belge yeni sekmede açılır (`.../file`) ve indirilir (`.../download`), ikisi de
yalnız `GET`'tir — panelde belge içeriğini değiştiren yol yoktur (10.5.2, K17). Fotoğraf ayrı bir
adresten (`.../photo`) sunulur: profil sayfasını çizmek belgeyi "açmak" sayılmasın (10.9.2 açma ve
indirmeyi loglar, sayfa görüntülemeyi değil): `.../file` `view`, `.../download` `download` olarak
`access_log`'a kullanıcı ve zamanla yazılır (`app.web.access`), satır sunmadan önce commit edilir.
Profil sayfası bağlam çalışanıyla yükleme formu taşır (10.5.3): form `POST /upload`'a çalışan
kimliğini gizli alanla gönderir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import ColumnElement, and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    AccessAction,
    ContactKind,
    Document,
    DocumentStatus,
    Employee,
    EmployeeAlias,
    EmployeeContact,
    EmployeeIdentifier,
    KnownDocumentType,
)
from app.db.session import get_session
from app.matching.match import normalize_document_number
from app.matching.names import EmptyNameError, normalize_name
from app.profiles.render import calculate_age
from app.storage import DataLayout
from app.web.access import record_access
from app.web.auth import PanelUser, require_panel_user
from app.web.routers.upload_page import DOCUMENT_STATUS_LABELS
from app.web.routers.uploads import get_layout
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


# --- 10.5: çalışan profili ---------------------------------------------------------------------

PROFILE_PICTURE_SLUG = "profile_picture"
EMPLOYEE_NOT_FOUND = "Çalışan bulunamadı."
DOCUMENT_NOT_FOUND = "Belge bulunamadı."
FILE_NOT_FOUND = "Belge dosyası bulunamadı."

CONTACT_LABELS = {
    ContactKind.PHONE.value: "Telefon",
    ContactKind.EMAIL.value: "E-posta",
    ContactKind.ADDRESS.value: "Adres",
}
# Tarayıcının kendi görüntüleyicisiyle açabildiği çıktı biçimleri; başka biçim (Word/Excel, K2)
# olduğu gibi indirilir. Ortam türü dosya içeriğinden değil, bu tablodan gelir.
MEDIA_TYPES = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}
IMAGE_FORMATS = frozenset({"jpg", "jpeg", "png"})
DOWNLOAD_MEDIA_TYPE = "application/octet-stream"
# Kimlik belgeleri paylaşımlı önbelleğe ve tarayıcı geçmişine girmesin.
FILE_HEADERS = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}


@dataclass(frozen=True, slots=True)
class ContactGroup:
    label: str
    values: list[str]


@dataclass(frozen=True, slots=True)
class IdentifierRow:
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class DocumentRow:
    id: int
    type_name: str
    file_name: str
    format: str
    status: str
    status_label: str
    created_on: date
    available: bool


@dataclass(frozen=True, slots=True)
class ProfileView:
    id: str
    name: str
    status_label: str
    given_names: str
    surname: str
    other_names: str | None
    original_script_name: str | None
    nationality: str | None
    date_of_birth: date | None
    age: int | None
    contacts: list[ContactGroup]
    identifiers: list[IdentifierRow]
    photo_url: str | None
    photo_missing: bool
    documents: list[DocumentRow]


@dataclass(frozen=True, slots=True)
class StoredDocument:
    path: Path
    name: str
    format: str


def _stored_file(layout: DataLayout, relative_path: str) -> Path | None:
    """Belgenin diskteki dosyası; yolu veri dizininden kaçıyorsa ya da dosya yoksa `None`."""
    try:
        path = layout.resolve(relative_path)
    except ValueError:
        return None
    return path if path.is_file() else None


def _stored_document(layout: DataLayout, document: Document) -> StoredDocument | None:
    path = _stored_file(layout, document.path)
    if path is None:
        return None
    return StoredDocument(
        path=path, name=PurePosixPath(document.path).name, format=document.format.lower()
    )


def _active_photo_document(session: Session, employee_id: str) -> Document | None:
    """Çalışanın güncel profil fotoğrafı: en yeni **etkin** `profile_picture` belgesi (10.5.4)."""
    return session.scalars(
        select(Document)
        .where(
            Document.employee_id == employee_id,
            Document.type_slug == PROFILE_PICTURE_SLUG,
            Document.status == DocumentStatus.ACTIVE.value,
        )
        .order_by(Document.created_at.desc(), Document.id.desc())
        .limit(1)
    ).first()


def build_profile(
    session: Session, layout: DataLayout, employee_id: str, *, today: date | None = None
) -> ProfileView | None:
    """10.5.1-10.5.4 — çalışanın profil kartı ve belge listesi; çalışan yoksa `None`.

    `today` yaş hesabının referans günüdür (verilmezse bugün). Sayfa yalnız var olan kayıtları
    gösterir: hiçbir alan üretilmez ya da düzeltilmez (K11, K17).
    """
    employee = session.get(Employee, employee_id)
    if employee is None:
        return None
    reference_date = today if today is not None else date.today()

    identifiers = session.scalars(
        select(EmployeeIdentifier)
        .where(EmployeeIdentifier.employee_id == employee_id)
        .order_by(EmployeeIdentifier.id)
    ).all()
    # Numaranın türü belge türü slug'ıdır; kişiye okunur ad için katalogdan çevrilir.
    type_names = {
        slug: name
        for slug, name in session.execute(
            select(KnownDocumentType.slug, KnownDocumentType.name).where(
                KnownDocumentType.slug.in_({identifier.kind for identifier in identifiers})
            )
        )
    }
    current_contacts = session.scalars(
        select(EmployeeContact)
        .where(EmployeeContact.employee_id == employee_id, EmployeeContact.is_current.is_(True))
        .order_by(EmployeeContact.id)
    ).all()
    documents = session.execute(
        select(Document, KnownDocumentType.name)
        .join(KnownDocumentType, KnownDocumentType.slug == Document.type_slug)
        .where(Document.employee_id == employee_id)
        .order_by(Document.created_at.desc(), Document.id.desc())
    ).all()

    rows = [
        DocumentRow(
            id=document.id,
            type_name=type_name,
            file_name=PurePosixPath(document.path).name,
            format=document.format,
            status=document.status,
            status_label=DOCUMENT_STATUS_LABELS.get(document.status, document.status),
            created_on=document.created_at.date(),
            available=_stored_file(layout, document.path) is not None,
        )
        for document, type_name in documents
    ]

    photo = _active_photo_document(session, employee_id)
    photo_stored = _stored_document(layout, photo) if photo is not None else None
    photo_shown = photo_stored is not None and photo_stored.format in IMAGE_FORMATS
    return ProfileView(
        id=employee.id,
        name=f"{employee.given_names} {employee.surname}",
        status_label=STATUS_LABELS.get(employee.status, employee.status),
        given_names=employee.given_names,
        surname=employee.surname,
        other_names=employee.other_names,
        original_script_name=employee.original_script_name,
        nationality=employee.nationality,
        date_of_birth=employee.date_of_birth,
        age=(
            calculate_age(employee.date_of_birth, today=reference_date)
            if employee.date_of_birth is not None
            else None
        ),
        contacts=[
            ContactGroup(
                label=label,
                values=[contact.value for contact in current_contacts if contact.kind == kind],
            )
            for kind, label in CONTACT_LABELS.items()
        ],
        identifiers=[
            IdentifierRow(label=type_names.get(item.kind, item.kind), value=item.value)
            for item in identifiers
        ],
        photo_url=f"/employees/{employee.id}/photo" if photo_shown else None,
        photo_missing=photo is None,
        documents=rows,
    )


@router.get("/employees/{employee_id}", response_class=HTMLResponse)
def employee_profile(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
) -> HTMLResponse:
    profile = build_profile(session, layout, employee_id)
    # Okuma işlemi de SQLite'ta yazma kilidini tutar (`app.db.session`): sayfa çizilirken
    # arka plandaki bir işleyici beklemesin.
    session.rollback()
    entry = MENU_BY_KEY["employees"]
    if profile is None:
        return render_page(
            request,
            "profile.html",
            user=user,
            active=entry.key,
            status_code=status.HTTP_404_NOT_FOUND,
            error=EMPLOYEE_NOT_FOUND,
        )
    return render_page(request, "profile.html", user=user, active=entry.key, profile=profile)


def _file_response(stored: StoredDocument, *, disposition: str) -> FileResponse:
    """Belgeyi olduğu gibi sunar (K10, K17): bayt bayt dosyadır, sunucu içeriğe dokunmaz.

    Tarayıcıda açılamayan biçim (Word/Excel) her koşulda indirme olarak gider.
    """
    media_type = MEDIA_TYPES.get(stored.format)
    if media_type is None:
        media_type, disposition = DOWNLOAD_MEDIA_TYPE, "attachment"
    return FileResponse(
        stored.path,
        media_type=media_type,
        filename=stored.name,
        content_disposition_type=disposition,
        headers=FILE_HEADERS,
    )


def _employee_document(
    session: Session,
    layout: DataLayout,
    employee_id: str,
    document_id: int,
    *,
    user: PanelUser,
    action: AccessAction,
) -> StoredDocument:
    """Belgeyi erişim logunu yazarak çözer (10.9.2); belge bu çalışana ait değilse, kaydı ya da
    dosyası yoksa 404 ve log yazılmaz.

    Satır sunmadan **önce** yazılır ve commit edilir: log yazılamazsa istek düşer, belge gitmez.
    """
    document = session.scalars(
        select(Document).where(Document.id == document_id, Document.employee_id == employee_id)
    ).first()
    stored = _stored_document(layout, document) if document is not None else None
    if document is None or stored is None:
        session.rollback()
        detail = DOCUMENT_NOT_FOUND if document is None else FILE_NOT_FOUND
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail)
    record_access(session, user_id=user.id, document_id=document.id, action=action)
    session.commit()
    return stored


@router.get("/employees/{employee_id}/documents/{document_id}/file")
def open_document(
    employee_id: str,
    document_id: int,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
) -> FileResponse:
    """10.5.2 — belgeyi tarayıcıda açar (profil sayfası bağlantıyı yeni sekmede açtırır).

    Açış `access_log`'a `view` olarak yazılır (10.9.2).
    """
    stored = _employee_document(
        session, layout, employee_id, document_id, user=user, action=AccessAction.VIEW
    )
    return _file_response(stored, disposition="inline")


@router.get("/employees/{employee_id}/documents/{document_id}/download")
def download_document(
    employee_id: str,
    document_id: int,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
) -> FileResponse:
    """10.5.2 — belgeyi dosya adıyla indirtir.

    İndirme `access_log`'a `download` olarak yazılır (10.9.2).
    """
    stored = _employee_document(
        session, layout, employee_id, document_id, user=user, action=AccessAction.DOWNLOAD
    )
    return _file_response(stored, disposition="attachment")


@router.get("/employees/{employee_id}/photo")
def employee_photo(
    employee_id: str,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
) -> FileResponse:
    """10.5.1 — profil kartındaki fotoğraf: güncel `profile_picture` belgesinin görüntüsü.

    Etkin fotoğraf belgesi yoksa, görüntü biçiminde değilse ya da dosyası yoksa 404.
    """
    document = _active_photo_document(session, employee_id)
    stored = _stored_document(layout, document) if document is not None else None
    session.rollback()
    if stored is None or stored.format not in IMAGE_FORMATS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DOCUMENT_NOT_FOUND)
    return _file_response(stored, disposition="inline")
