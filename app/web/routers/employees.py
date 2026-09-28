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
(`archived`, K16) belge çalışanın klasöründe durmadığı için sayılmaz. "Paket" sütunu (14.3.1)
çalışanın açık belge paketi sayısını ve o paketlerdeki eksik zorunlu kalem sayısını ("2 açık · 3
eksik") gösterir, açık paketi yoksa "—"; `packages=missing` listeyi en az bir açık (zorunlu kalemi
eksik) paketi olan çalışanlarla daraltır ve aramayla birleşir. Sayılar profil sayfasıyla aynı
hesaptır (`app.groups.package_counts`). Sayfa yalnız okur: belge içeriği ya da çalışan kaydı
değiştirilmez (K11, K17).

HTMX isteği (`HX-Request`) yalnız sonuç parçasını (`employees_results.html`) alır, tarayıcı isteği
tam sayfayı; ikisi de aynı adrestedir, bu yüzden yanıt `Vary: HX-Request` taşır. Sayfalama düz
bağlantıdır; JavaScript kapalıyken de arama form gönderimiyle çalışır.

`GET /employees/{employee_id}` çalışanın profil sayfasıdır (10.5.1): CV benzeri kart profil
fotoğrafını, adı, soyadı, diğer isimleri, orijinal yazımı, vatandaşlığı, doğum tarihi ve yaşı,
iletişim bilgilerini ve belge numaralarını gösterir; bilinmeyen alan gizlenmez, "—" görünür.
Çalışanın etkin bir `profile_picture` belgesi yoksa kart yer tutucu çizer ve belgeyi eksik olarak
işaretler (10.5.4). Ad, soyad ve diğer isimler Latin yazımdır, Latin olmayan yazım "Orijinal
yazım"da durur (05.2.2); bu alanlardan biri hâlâ Latin olmayan harf taşıyorsa (onarımın Latin
yazım bulamadığı eski kayıt, `python -m app.profiles repair-latin-names`) kart "Latin yazım eksik"
uyarısı gösterir. Ad, soyad, diğer isimler, orijinal yazım, vatandaşlık ve doğum tarihinin
yanında kaynağı durur (05.7.3, `employee_field_observations`): alanı dolduran belge, yoksa aynı
değeri okuyan ilk belge. Belgede farklı değer okunduysa alan değişmez; altında "<alan>: belgede
farklı değer okundu" uyarısı ve belgelere bağlantı çıkar. Kaynak, çalışanın kökeni o sayfayla
başlayan belgesine (etkin olan, sonra en yeni) bağlanır — dosyası varsa yeni sekmede açılır, yoksa
geçmişine; belge bu çalışanda yoksa (henüz yürütülmedi, başka çalışana taşındı) parti sayfasına.
Belge listesi çalışanın **tüm** belgelerini (etkin, eski sürüm, arşivlenmiş) gösterir; her belge
yeni sekmede açılır (`.../file`) ve indirilir (`.../download`), ikisi de yalnız `GET`'tir — panelde
belge içeriğini değiştiren yol yoktur (10.5.2, K17). Fotoğraf ayrı bir adresten (`.../photo`)
sunulur: profil sayfasını çizmek belgeyi "açmak" sayılmasın (10.9.2 açma ve indirmeyi loglar, sayfa
görüntülemeyi değil): `.../file` `view`, `.../download` `download` olarak `access_log`'a kullanıcı
ve zamanla yazılır (`app.web.access`), satır sunmadan önce commit edilir.
Profil sayfası bağlam çalışanıyla yükleme formu taşır (10.5.3): form `POST /upload`'a çalışan
kimliğini gizli alanla gönderir. Profilden yüklenip bu çalışana ait görünmeyen (kişi denetimi,
10.5.5) ve kuyrukta çözülmemiş belge varsa sayfanın üstünde büyük kırmızı uyarı kutusu durur;
kuyruk öğesi çözülünce kalkar (`app.web.context_person`).

**Belge paketleri (14.2.1–14.2.3; PLAN.md §C89).** Profilin "Belge paketleri" bölümü açık ve
tamamlanmış paketleri kart hâlinde gösterir: grup adı, tanımlayan ve zaman, kalem listesi (✓/○,
zorunlu/isteğe bağlı, karşılayan belgenin bağlantısı) ve durum rozeti ("Açık — k/n zorunlu kalem"
ya da "Tamamlandı — başvuru başlatılabilir"); iptal edilenler katlanmış listededir. Tikler her
görüntülemede belgelerden hesaplanır, GET hiçbir şey yazmaz (`app.groups.employee_packages`).
`POST /employees/{id}/packages` arşivlenmemiş bir grubu pakete çevirir (not ≤ 120); aynı grubun
iptal edilmemiş paketi varsa ilk gönderim uyarıyla döner (409) ve ancak `confirm_duplicate=1`'li
ikinci gönderim paketi açar. `POST .../packages/{pkg}/cancel` paketi nedeniyle iptal eder,
`POST .../packages/{pkg}/reopen` açığa döndürür. Üçü tek adımdır (§D61-b: dosya taşımaz,
eşleştirmeyi değiştirmez, geri alınabilir), `PACKAGE_*` olayını kullanıcı adıyla yazar (K15) ve
commit'ten sonra çalışanın `profil.md`'sini yeniden üretir (09.1.1, 14.3.1). Paket silinmez (R11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
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
    EmployeeFieldObservation,
    EmployeeIdentifier,
    FieldOutcome,
    KnownDocumentType,
    ProfileField,
    UploadFile,
)
from app.db.session import get_session
from app.groups import (
    NOTE_MAX_LENGTH,
    GroupArchivedError,
    GroupNotFoundError,
    GroupSummary,
    PackageCounts,
    PackageEmployeeNotFoundError,
    PackageFormError,
    PackageNotFoundError,
    PackageStateError,
    PackageView,
    assign_package,
    cancel_package,
    employee_packages,
    employees_with_missing_packages,
    list_groups,
    package_counts,
    reopen_package,
)
from app.matching.match import normalize_document_number
from app.matching.names import EmptyNameError, normalize_name
from app.profiles import write_profile
from app.profiles.latin_names import needs_latin_repair
from app.profiles.render import calculate_age
from app.storage import DataLayout
from app.web.access import record_access
from app.web.auth import PanelUser, require_panel_user
from app.web.context_person import ForeignDocumentsWarning, profile_warning
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
# 14.3.1: listenin paket süzgeci; tanınmayan değer süzmez.
MISSING_PACKAGES = "missing"
NO_PACKAGES = "—"


@dataclass(frozen=True, slots=True)
class EmployeeRow:
    id: str
    name: str
    original_script_name: str | None
    nationality: str | None
    document_count: int
    status: str
    status_label: str
    packages: str = NO_PACKAGES


@dataclass(frozen=True, slots=True)
class EmployeeListing:
    query: str
    rows: list[EmployeeRow]
    total: int
    page: int
    page_count: int
    previous_url: str | None
    next_url: str | None
    packages: str = ""


def package_cell(counts: PackageCounts | None) -> str:
    """14.3.1 — listenin "Paket" hücresi: "2 açık · 3 eksik"; açık paket yoksa "—"."""
    if counts is None or not counts.open:
        return NO_PACKAGES
    return f"{counts.open} açık · {counts.missing} eksik"


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


def _page_url(query: str, page: int, packages: str = "") -> str:
    params = {"q": query} if query else {}
    if packages:
        params["packages"] = packages
    if page > 1:
        params["page"] = str(page)
    return "/employees" + (f"?{urlencode(params)}" if params else "")


def list_employees(
    session: Session, query: str = "", page: int = 1, packages: str = ""
) -> EmployeeListing:
    """10.4.1/10.4.2/14.3.1 — çalışanların `page`. sayfası; `query` boşsa hepsi, doluysa uyanlar.
    `packages="missing"` yalnız en az bir açık (zorunlu kalemi eksik) paketi olanları bırakır.

    Sayfa sayısını aşan `page` son sayfaya indirilir. Sıra soyad, ad, çalışan numarasıdır.
    """
    query = " ".join(query.split())
    packages = packages if packages == MISSING_PACKAGES else ""
    filters = [_term_matches(session, term) for term in search_terms(query)]
    if packages:
        filters.append(Employee.id.in_(sorted(employees_with_missing_packages(session))))
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
    counts = package_counts(session, [employee.id for employee, _ in found])
    rows = [
        EmployeeRow(
            id=employee.id,
            name=f"{employee.given_names} {employee.surname}",
            original_script_name=employee.original_script_name,
            nationality=employee.nationality,
            document_count=count,
            status=employee.status,
            status_label=STATUS_LABELS.get(employee.status, employee.status),
            packages=package_cell(counts.get(employee.id)),
        )
        for employee, count in found
    ]
    return EmployeeListing(
        query=query,
        rows=rows,
        total=total,
        page=page,
        page_count=page_count,
        previous_url=_page_url(query, page - 1, packages) if page > 1 else None,
        next_url=_page_url(query, page + 1, packages) if page < page_count else None,
        packages=packages,
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
    packages: Annotated[str, Query(max_length=16)] = "",
) -> HTMLResponse:
    listing = list_employees(session, q, page, packages)
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
# Kartın alan etiketleri (05.7.3 uyarısı "<alan>: belgede farklı değer okundu").
FIELD_LABELS = {
    ProfileField.GIVEN_NAMES: "Ad",
    ProfileField.SURNAME: "Soyad",
    ProfileField.OTHER_NAMES: "Diğer isimler",
    ProfileField.ORIGINAL_SCRIPT_NAME: "Orijinal yazım",
    ProfileField.NATIONALITY: "Vatandaşlık",
    ProfileField.DATE_OF_BIRTH: "Doğum tarihi",
}
FIELD_CONFLICT_WARNING = "{label}: belgede farklı değer okundu"
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
class SourceLink:
    label: str
    url: str
    new_tab: bool = False


@dataclass(frozen=True, slots=True)
class FieldSources:
    """Bir profil alanının belge kaynakları (05.7.3): `source` alanı dolduran ya da aynı değeri
    okuyan belge, `conflicts` farklı değer okuyan belgeler; `warning` çakışma uyarısının metni."""

    source: SourceLink | None
    conflicts: list[SourceLink]
    warning: str


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
    latin_missing: bool = False
    field_sources: dict[str, FieldSources] = field(default_factory=dict)
    # 10.5.5: profilden yüklenip bu çalışana ait görünmeyen, kuyrukta çözülmemiş belgeler.
    context_warning: ForeignDocumentsWarning | None = None
    # 14.2: çalışanın belge paketleri (iptal edilenler dahil) ve dosyası yerinde olan belgeler
    # (kalemi karşılayan belgenin bağlantısı dosyayı ya da geçmişini açar).
    packages: list[PackageView] = field(default_factory=list)
    available_document_ids: frozenset[int] = frozenset()

    @property
    def live_packages(self) -> list[PackageView]:
        return [package for package in self.packages if not package.cancelled]

    @property
    def cancelled_packages(self) -> list[PackageView]:
        return [package for package in self.packages if package.cancelled]


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

    field_sources = _field_sources(
        session, employee_id, [document for document, _ in documents], rows
    )
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
        latin_missing=needs_latin_repair(employee),
        field_sources=field_sources,
        context_warning=profile_warning(session, employee_id),
        packages=employee_packages(session, employee_id),
        available_document_ids=frozenset(row.id for row in rows if row.available),
    )


def _field_sources(
    session: Session,
    employee_id: str,
    documents: list[Document],
    rows: list[DocumentRow],
) -> dict[str, FieldSources]:
    """05.7.3 — alan başına kaynak ve çakışma bağlantıları (gözlem sırasıyla); gözlemi olmayan
    alan sözlükte yoktur. Değer gösterilmez: kart alanın kendi değerini zaten gösterir."""
    observations = session.execute(
        select(EmployeeFieldObservation, UploadFile.upload_id)
        .join(UploadFile, UploadFile.id == EmployeeFieldObservation.file_id)
        .where(EmployeeFieldObservation.employee_id == employee_id)
        .order_by(EmployeeFieldObservation.observed_at, EmployeeFieldObservation.id)
    ).all()
    if not observations:
        return {}
    by_source = _documents_by_source(documents)
    available = {row.id: row.available for row in rows}

    def link(observation: EmployeeFieldObservation, upload_id: str) -> SourceLink:
        document = by_source.get((observation.file_id, observation.page_index))
        if document is None:
            return SourceLink(label=f"Parti {upload_id}", url=f"/uploads/{upload_id}")
        name = PurePosixPath(document.path).name
        if available.get(document.id, False):
            url = f"/employees/{employee_id}/documents/{document.id}/file"
            return SourceLink(label=name, url=url, new_tab=True)
        return SourceLink(label=name, url=f"/documents/{document.id}/history")

    sources: dict[str, FieldSources] = {}
    for profile_field, label in FIELD_LABELS.items():
        seen = [
            (observation, upload_id)
            for observation, upload_id in observations
            if observation.field == profile_field.value
        ]
        if not seen:
            continue
        by_outcome = {
            outcome: [(obs, upload) for obs, upload in seen if obs.outcome == outcome.value]
            for outcome in FieldOutcome
        }
        # Kaynak: alanı dolduran belge; yoksa (alan belgeden önce doluydu) aynı değeri okuyan ilk.
        origin = [*by_outcome[FieldOutcome.FILLED], *by_outcome[FieldOutcome.SAME]]
        conflicts = list(
            dict.fromkeys(link(obs, upload) for obs, upload in by_outcome[FieldOutcome.CONFLICT])
        )
        sources[profile_field.value] = FieldSources(
            source=link(*origin[0]) if origin else None,
            conflicts=conflicts,
            warning=FIELD_CONFLICT_WARNING.format(label=label),
        )
    return sources


def _documents_by_source(documents: list[Document]) -> dict[tuple[int, int], Document]:
    # Belge, kökeninin ilk sayfasıyla (gözlemin kaynağı, 05.7.3). Aynı kaynaktan birden çok çıktı
    # varsa (yeniden analiz, K18) etkin olan, sonra en yeni.
    chosen: dict[tuple[int, int], Document] = {}
    ranked = sorted(
        documents,
        key=lambda each: (each.status == DocumentStatus.ACTIVE.value, each.created_at, each.id),
    )
    for document in ranked:
        source = _first_source_page(document.source_refs_json)
        if source is not None:
            chosen[source] = document
    return chosen


def _first_source_page(source_refs: Any) -> tuple[int, int] | None:
    # `documents.source_refs_json`: `[{"file_id": 4, "pages": [0, 1]}]`; bozuk kayıt atlanır.
    if not isinstance(source_refs, list) or not source_refs:
        return None
    first = source_refs[0]
    if not isinstance(first, dict):
        return None
    file_id, pages = first.get("file_id"), first.get("pages")
    if not isinstance(file_id, int) or not isinstance(pages, list) or not pages:
        return None
    return (file_id, pages[0]) if isinstance(pages[0], int) else None


@dataclass(frozen=True, slots=True)
class PackageFormValues:
    """Paket tanımlama formunun değerleri (reddedilen form girilenlerle yeniden çizilir);
    `duplicate` aynı grubun paketi varken ilk gönderimin uyarısıdır."""

    group_id: int | None = None
    note: str = ""
    duplicate: bool = False


PACKAGE_NOTICES = {
    "package_assigned": "Paket tanımlandı.",
    "package_cancelled": "Paket iptal edildi.",
    "package_reopened": "Paket yeniden açıldı.",
}
PACKAGE_NOT_FOUND = "Paket bulunamadı."
GROUP_NOT_FOUND = "Belge grubu bulunamadı."
DUPLICATE_PACKAGE = (
    "Bu çalışanda aynı gruptan iptal edilmemiş bir paket zaten var. Yine de ikinci paket "
    "tanımlamak için onaylayın."
)
# Form sınırı yalnız aşırı girdiye karşıdır; uzunluk kuralını servis mesajla bildirir.
PACKAGE_FORM_LIMIT = 1000
PackageNote = Annotated[str | None, Form(max_length=PACKAGE_FORM_LIMIT)]


def _profile_page(
    request: Request,
    user: PanelUser,
    session: Session,
    layout: DataLayout,
    employee_id: str,
    *,
    notice: str | None = None,
    package_form: PackageFormValues | None = None,
    package_problems: dict[str, list[str]] | None = None,
    cancel_problems: dict[int, list[str]] | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    profile = build_profile(session, layout, employee_id)
    groups: list[GroupSummary] = list_groups(session) if profile is not None else []
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
    return render_page(
        request,
        "profile.html",
        user=user,
        active=entry.key,
        status_code=status_code,
        profile=profile,
        group_choices=groups,
        package_form=package_form or PackageFormValues(),
        package_problems=package_problems or {},
        cancel_problems=cancel_problems or {},
        package_notice=PACKAGE_NOTICES.get(notice or ""),
        note_limit=NOTE_MAX_LENGTH,
    )


@router.get("/employees/{employee_id}", response_class=HTMLResponse)
def employee_profile(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    notice: Annotated[str | None, Query(max_length=32)] = None,
) -> HTMLResponse:
    return _profile_page(request, user, session, layout, employee_id, notice=notice)


def _package_redirect(employee_id: str, notice: str) -> RedirectResponse:
    return RedirectResponse(
        f"/employees/{employee_id}?notice={notice}#packages", status.HTTP_303_SEE_OTHER
    )


def _rewrite_profile(session: Session, layout: DataLayout, employee_id: str) -> None:
    # 09.1.1, 14.3.1: profil.md paketlerin commit edilmiş hâlini gösterir.
    employee = session.get(Employee, employee_id)
    if employee is not None:
        write_profile(session, layout, employee)
    session.rollback()


@router.post("/employees/{employee_id}/packages", response_class=HTMLResponse)
def assign_package_endpoint(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    group_id: Annotated[int, Form()],
    note: PackageNote = None,
    confirm_duplicate: Annotated[str | None, Form(max_length=1)] = None,
) -> Response:
    """14.2.1 — grubu çalışana paket olarak tanımlar (tek adım). Arşivdeki grup 409, not kuralı
    422; aynı grubun iptal edilmemiş paketi varsa ilk gönderim uyarıyla 409 döner, onaylı ikinci
    gönderim (`confirm_duplicate=1`) paketi açar."""
    form = PackageFormValues(group_id=group_id, note=note or "")
    problems: dict[str, list[str]]
    try:
        result = assign_package(
            session,
            employee_id,
            group_id,
            actor=user.username,
            note=note,
            confirm_duplicate=confirm_duplicate == "1",
        )
    except PackageEmployeeNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, EMPLOYEE_NOT_FOUND) from None
    except GroupNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, GROUP_NOT_FOUND) from None
    except GroupArchivedError as exc:
        problems, status_code = {"group_id": [str(exc)]}, status.HTTP_409_CONFLICT
    except PackageFormError as exc:
        problems, status_code = exc.problems, status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        if result.warn:
            session.rollback()
            return _profile_page(
                request,
                user,
                session,
                layout,
                employee_id,
                package_form=PackageFormValues(group_id=group_id, note=note or "", duplicate=True),
                package_problems={"group_id": [DUPLICATE_PACKAGE]},
                status_code=status.HTTP_409_CONFLICT,
            )
        session.commit()
        _rewrite_profile(session, layout, employee_id)
        return _package_redirect(employee_id, "package_assigned")
    session.rollback()
    return _profile_page(
        request,
        user,
        session,
        layout,
        employee_id,
        package_form=form,
        package_problems=problems,
        status_code=status_code,
    )


@router.post("/employees/{employee_id}/packages/{package_id}/cancel", response_class=HTMLResponse)
def cancel_package_endpoint(
    employee_id: str,
    package_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    note: PackageNote = None,
) -> Response:
    """14.2.3 — paketi nedeniyle tek adımda iptal eder; paket silinmez. Neden boşsa ya da uzunsa
    422, paket zaten iptal edilmişse 409."""
    try:
        cancel_package(session, employee_id, package_id, actor=user.username, note=note)
    except PackageNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, PACKAGE_NOT_FOUND) from None
    except (PackageFormError, PackageStateError) as exc:
        session.rollback()
        conflict = isinstance(exc, PackageStateError)
        return _profile_page(
            request,
            user,
            session,
            layout,
            employee_id,
            cancel_problems={package_id: [str(exc)]},
            status_code=(
                status.HTTP_409_CONFLICT if conflict else status.HTTP_422_UNPROCESSABLE_CONTENT
            ),
        )
    session.commit()
    _rewrite_profile(session, layout, employee_id)
    return _package_redirect(employee_id, "package_cancelled")


@router.post("/employees/{employee_id}/packages/{package_id}/reopen", response_class=HTMLResponse)
def reopen_package_endpoint(
    employee_id: str,
    package_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
) -> Response:
    """14.2.3 — iptal edilmiş paketi tek adımda açığa döndürür ve yeniden değerlendirir; paket
    iptal edilmemişse 409."""
    try:
        reopen_package(session, employee_id, package_id, actor=user.username)
    except PackageNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, PACKAGE_NOT_FOUND) from None
    except PackageStateError as exc:
        session.rollback()
        return _profile_page(
            request,
            user,
            session,
            layout,
            employee_id,
            cancel_problems={package_id: [str(exc)]},
            status_code=status.HTTP_409_CONFLICT,
        )
    session.commit()
    _rewrite_profile(session, layout, employee_id)
    return _package_redirect(employee_id, "package_reopened")


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
