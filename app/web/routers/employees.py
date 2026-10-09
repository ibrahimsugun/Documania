"""Çalışan listesi, arama ve çalışan profili (PRD 10.4.1, 10.4.2, 10.5.1-10.5.9).

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
Belge listesi çalışanın **tüm** belgelerini (etkin, eski sürüm, arşivlenmiş) gösterir — kalıcı
silinen belge (10.5.12) listede yoktur, dosya adresi 404 döner; her belge yeni sekmede açılır
(`.../file`) ve indirilir (`.../download`), ikisi de yalnız `GET`'tir — panelde belge içeriğini
değiştiren yol yoktur (10.5.2, K17). Planın yalnız isimle yerleştirdiği belge
(§20.2.2 satır 5a, `matched_by: name`; `app.pipeline.plan.name_matched_documents`) listede "Yalnız
isimle eşleşti" etiketi taşır (05.5.4); yanlışsa İK belgeyi taşır (10.8.1). Fotoğraf ayrı bir
adresten (`.../photo`)
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

**Profili düzenleme (10.5.6; PLAN.md §C90-a, §D61).** Profil sayfasındaki "Profili düzenle"
bağlantısı (birleştirilmiş çalışanda yok) `GET /employees/{id}/fields` formunu açar: ad, soyad,
diğer isimler, orijinal yazım, doğum tarihi, uyruk — başka alan yoktur, belge içeriği bu formla
değişmez (K17). Form §20.6'nın **birinci** onay metnini taşır; gönderim `POST .../fields/prepare`'e
gider: alanlar denetlenir (`app.web.profile_form`; geçersizse ya da hiçbir alan değişmediyse 422 ve
form hatası), değişikliklerin özeti, **ikinci** metin (`<N>` = dosyası yeniden adlandırılacak belge
sayısı, ad değişmiyorsa 0) ve form değerlerine bağlı tek kullanımlık belirteç döner (belirteç hedefi
çalışan + değerlerin SHA-256 özeti: hazırlıktan sonra değişen değer belirteçten geçmez). `POST
.../fields` belirteçle gelir: belirteç tüketilir, önce `USER_CONFIRMED`, sonra
`update_employee_fields`'in `EMPLOYEE_EDITED`'i tek işlemde yazılır; ad değiştiyse klasör ve etkin
belge dosyaları K8 adına yeniden adlandırılır (`app.matching.edit`). Commit'ten sonra `profil.md`
yeniden üretilir ve profil sayfasına bildirimle dönülür. Belirteçsiz, süresi geçmiş, kullanılmış ya
da başka değerlere, çalışana, işleme veya oturuma ait istek 400; yeniden adlandırma yarıda kalırsa
409 — ikisinde de hiçbir şey değişmez (S16). Elle girilen alanın kaynağı kartta "elle" olarak
görünür; o düzenlemeden önceki belge gözlemleri uyarıdan düşer (değer artık İK'nın kararıdır),
sonrakiler kaynak ya da uyarı olur.

**Pasife alma ve yeniden etkinleştirme (10.5.7; PLAN.md §C90-b, §D61).** Liste `?status=` süzgecini
taşır: `active` (varsayılan), `inactive`, `all` — birleştirilmiş çalışan (10.5.9) yalnız `all`'da;
seçenekler aramaya uyan çalışan sayısıyla çizilir, süzgeç sayfalama bağlantılarında korunur. Atama
ve taşıma aramaları (`statuses=SEARCHABLE_STATUSES`) pasif çalışanı da bulur. Profildeki "Pasife al"
(pasif çalışanda bildirimdeki "Yeniden etkinleştir") `GET /employees/{id}/status/confirm?to=` ile
§20.6'nın birinci metnini ve isteğe bağlı notu (≤ 200) gösterir; `POST .../status/prepare` ikinci
metni ve hedef duruma + notun özetine bağlı tek kullanımlık belirteci verir; `POST .../status`
belirteçle gelir: belirteç tüketilir, `USER_CONFIRMED` ve
`EMPLOYEE_DEACTIVATED`/`EMPLOYEE_REACTIVATED` tek işlemde yazılır (`app.matching.status`),
commit'ten sonra `profil.md` yeniden üretilir. Klasör, belgeler ve olaylar yerinde kalır (R11).
Pasif profilde üstte bildirim (kim, ne zaman, not) durur ve yükleme formu yoktur — bağlam yüklemesi
zaten 409'dur (`app.web.routers.uploads`). Birleştirilmiş ya da zaten o durumdaki çalışan 409,
geçersiz hedef 422, belirteç reddi 400; hiçbirinde bir şey değişmez.

**Profil alt kayıtları (10.5.8; PLAN.md §C90-c, §D61, §D68).** Profilin "Profil kayıtları" bölümü
görülen isim yazımlarını (katlanmış; yazım ve alfabe), belge numaralarını (tür, numara, kaynak
belge) ve iletişim bilgilerini (tür, değer, kaynak ya da "elle", güncel/geçmiş) listeler; her etkin
satırda "Kaldır" vardır. Kaldırma iki aşamalıdır: `GET .../records/{kind}/{rid}/remove/confirm`
§20.6'nın birinci metnini, `POST .../remove/prepare` ikinci metni ve `kind:rid`'e bağlı tek
kullanımlık belirteci verir, `POST .../remove` belirteçle gelir; belirteç tüketilir,
`USER_CONFIRMED` ve `PROFILE_RECORD_REMOVED` tek işlemde yazılır (`app.matching.records`). Kayıt
silinmez; "Kaldırılanlar" altında kim ve ne zaman bilgisiyle durur, `POST .../restore` tek adımda
geri alır (`PROFILE_RECORD_RESTORED`). Kaldırılmış kayıt eşleştirmede, aramada, kartta ve
`profil.md`'de kullanılmaz; belgeden yeniden gelirse bölümün üstünde "Belgede görülen <tür>
kaldırılmış bir kayda uyuyor" uyarısı durur. `POST /employees/{id}/contacts` iletişim bilgisini elle
ekler (tek adım, `CONTACT_ADDED`): yeni değer güncel olur, aynı türün öncekileri geçmişte kalır.
Olaylar kayıt türünü ve kimliğini taşır, değeri taşımaz. Her işlemden sonra `profil.md` yeniden
üretilir. `kind` `alias|identifier|contact` dışındaysa ya da kayıt bu çalışanın değilse 404;
birleştirilmiş çalışan, zaten kaldırılmış (ya da geri alınacak şeyi olmayan) kayıt 409; iletişim
kuralı 422; belirteç reddi 400 — hiçbirinde bir şey değişmez.

**İki çalışanı birleştirme (10.5.9; PLAN.md §C90-d, §D61, §D69).** Profildeki "Başka kayıtla
birleştir" (birleştirilmiş çalışanda yok) `GET /employees/{id}/merge/employees` sayfasını açar:
ikinci çalışan 10.4.2'nin aramasıyla bulunur (etkin ve pasif; birleştirilmiş çalışan bulunmaz,
kaydın kendisi seçilemez; HTMX isteği yalnız sonuç parçasını alır). `GET
.../merge/confirm?other=&keep=` iki kaydın alanlarını yan yana, belge sayılarını ve birleştirmenin
alan sonucunu (dolacak, farklı) gösterir; kalacak kayıt radyoyla seçilir (varsayılan profildeki
kayıt) ve §20.6'nın birinci metni seçime göre dolar. `POST .../merge/prepare` ikinci metni (`<N>`
kalana bağlanacak belge sayısı, "geri alınamaz") ve `kalan:birleşen` çiftine bağlı tek kullanımlık
belirteci verir; `POST .../merge` belirteçle gelir: belirteç tüketilir, `USER_CONFIRMED` ve
`EMPLOYEE_MERGED` tek işlemde yazılır (`app.matching.merge`), belgeler, alt kayıtlar, alan
kaynakları ve paketler kalana bağlanır, dosyalar K8 adıyla taşınır. Commit'ten sonra iki `profil.md`
yeniden üretilir ve kalan profile dönülür. Birleştirilmiş kaydın profili 200 döner: üstte kalan
kayda bağlantılı bildirim durur; düzenleme, durum, alt kayıt, paket, yükleme ve birleştirme
işlemleri yoktur. Çalışan ya da seçilen kayıt yoksa 404; aynı kayıt ya da biri zaten
birleştirilmişse 409; kalan ikisinden biri değilse 422; belirteç reddi 400; dosya taşıması düşerse
409 — hiçbirinde bir şey değişmez.

**Pasif çalışanı kalıcı silme (10.5.13; K16, R11, PLAN.md §D110, §D116).** Yalnız pasif profilin
bildiriminde "Çalışanı kalıcı sil" (tehlike görünümü) vardır. Aynı üç adımlı kalıptır: `GET
/employees/{id}/delete/confirm` §20.6'nın birinci metnini çalışanın adıyla, `POST
.../delete/prepare` ikinci metni (`<N>` silinecek belge sayısı,
`app.storage.plan_employee_deletion`) ve çalışana ve bu sayıya bağlı tek kullanımlık belirteci
verir; `POST .../delete` belirteci ve sayıyı taşır: belirteç tüketilir, `USER_CONFIRMED` ve
`delete_employee`'nin `EMPLOYEE_DELETED`'i tek işlemde yazılır, commit'ten sonra dosyalar ve klasör
diskten kalkar (`remove_employee_files`). Etkin ya da birleştirilmiş çalışan 409, belirteç reddi
400, belge sayısı onaydan sonra değiştiyse 409 — hiçbirinde bir şey değişmez. Silinen çalışanın
bütün `/employees/{id}…` adresleri yönlendiricinin bağımlılığıyla (`reject_deleted_employee`) "Bu
çalışan <tarih> tarihinde <kullanıcı> tarafından kalıcı olarak silindi" sayfasını (410) döner;
listede (`?status=all` dahil), aramada, atama, taşıma ve birleştirme aramalarında görünmez.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy import ColumnElement, and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.ai.schemas import Script
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
    EmployeeStatus,
    FieldOutcome,
    FieldSource,
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
from app.i18n import N_, Translatable
from app.matching.edit import (
    MERGED_STATUS,
    EmployeeEditRefusedError,
    NoFieldChangesError,
    current_profile_fields,
    preview_employee_edit,
    update_employee_fields,
)
from app.matching.match import (
    PROFILE_FIELDS,
    ProfileFields,
    ProfileFieldsError,
    normalize_document_number,
)
from app.matching.merge import (
    EmployeeMergeRefusedError,
    merge_document_count,
    merge_employees,
    merge_field_preview,
)
from app.matching.names import EmptyNameError, normalize_name
from app.matching.records import (
    ACTIVE_ALIAS,
    ACTIVE_CONTACT,
    ACTIVE_IDENTIFIER,
    CONTACT_VALUE_MAX_LENGTH,
    SEEN_AFTER_REMOVAL_WARNING,
    ContactFormError,
    EmployeeRecords,
    ProfileRecord,
    ProfileRecordStateError,
    RecordKind,
    add_contact,
    employee_records,
    find_record,
    record_kind,
    record_label,
    record_value,
    remove_record,
    restore_record,
    seen_after_removal_warning,
)
from app.matching.status import (
    REASON_MAX_LENGTH,
    EmployeeStatusError,
    StatusReasonError,
    change_employee_status,
    check_status_change,
    last_deactivation,
    normalized_reason,
    status_label,
    status_target,
)
from app.pipeline.plan import name_matched_documents
from app.profiles import write_profile
from app.profiles.latin_names import needs_latin_repair
from app.profiles.render import calculate_age
from app.storage import (
    DataLayout,
    EmployeeDeletionChangedError,
    EmployeeMergeError,
    EmployeeNotDeletableError,
    EmployeeRenameError,
    check_employee_deletable,
    delete_employee,
    plan_employee_deletion,
    remove_employee_files,
)
from app.web.access import record_access
from app.web.auth import PanelUser, require_panel_user
from app.web.confirm import (
    CONFIRMATION_REFUSED,
    ConfirmationRefusedError,
    Operation,
    confirm_operation,
    first_text,
    issue_confirmation,
    second_text,
)
from app.web.context_person import ForeignDocumentsWarning, profile_warning
from app.web.profile_form import (
    INVALID_PROFILE,
    PROFILE_LABELS,
    ProfileFormError,
    ProfileValues,
    parse_profile,
    profile_digest,
    profile_form_fields,
    profile_text,
    profile_values,
)
from app.web.routers.upload_page import DOCUMENT_STATUS_LABELS
from app.web.routers.uploads import get_layout
from app.web.templating import MENU_BY_KEY, render_page

router = APIRouter(tags=["employees"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]

PAGE_SIZE = 25
MAX_QUERY_LENGTH = 100
# Her terim birkaç EXISTS alt sorgusu açar; uzun bir metin sorguyu gereksiz büyütmesin.
MAX_TERMS = 6

# 10.5.7: listenin durum süzgeci (`?status=`); varsayılan etkin çalışanlar, tanınmayan değer
# varsayılana döner. Birleştirilmiş çalışan (10.5.9) yalnız "Hepsi"nde görünür.
ALL_STATUSES = "all"
STATUS_FILTERS: dict[str, frozenset[str] | None] = {
    EmployeeStatus.ACTIVE.value: frozenset({EmployeeStatus.ACTIVE.value}),
    EmployeeStatus.INACTIVE.value: frozenset({EmployeeStatus.INACTIVE.value}),
    # Hepsi: etkin, pasif ve birleştirilmiş; kalıcı silinen (10.5.13) hiçbir süzgeçte yoktur.
    ALL_STATUSES: frozenset(
        {
            EmployeeStatus.ACTIVE.value,
            EmployeeStatus.INACTIVE.value,
            EmployeeStatus.MERGED.value,
        }
    ),
}
STATUS_FILTER_LABELS = {
    EmployeeStatus.ACTIVE.value: N_("Aktif"),
    EmployeeStatus.INACTIVE.value: N_("Pasif"),
    ALL_STATUSES: N_("Hepsi"),
}
DEFAULT_STATUS = EmployeeStatus.ACTIVE.value
# Atama (10.7.2) ve taşıma (10.8.2) aramaları pasif çalışanı da bulur ("(pasif)" ekiyle).
SEARCHABLE_STATUSES = frozenset({EmployeeStatus.ACTIVE.value, EmployeeStatus.INACTIVE.value})
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
class StatusOption:
    """Durum süzgecinin seçeneği: değer, etiket, aramaya uyan çalışan sayısı ve seçili mi."""

    value: str
    label: str
    count: int
    url: str
    selected: bool


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
    status: str = DEFAULT_STATUS
    status_options: list[StatusOption] = field(default_factory=list)


def package_cell(counts: PackageCounts | None) -> str:
    """14.3.1 — listenin "Paket" hücresi: "2 açık · 3 eksik"; açık paket yoksa "—"."""
    if counts is None or not counts.open:
        return NO_PACKAGES
    return Translatable(
        N_("{open} açık · {missing} eksik"), open=counts.open, missing=counts.missing
    )


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
    # İK'nın profilden kaldırdığı yazım ve numara (10.5.8) aramada kullanılmaz.
    predicates = [
        *name_fields,
        exists().where(EmployeeAlias.employee_id == Employee.id, ACTIVE_ALIAS, alias_match),
    ]
    number = normalize_document_number(term)
    if number:
        predicates.append(
            exists().where(
                EmployeeIdentifier.employee_id == Employee.id,
                ACTIVE_IDENTIFIER,
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


def _page_url(
    query: str, page: int, packages: str = "", status_filter: str = DEFAULT_STATUS
) -> str:
    params = {"q": query} if query else {}
    if packages:
        params["packages"] = packages
    if status_filter != DEFAULT_STATUS:
        params["status"] = status_filter
    if page > 1:
        params["page"] = str(page)
    return "/employees" + (f"?{urlencode(params)}" if params else "")


def normalize_status_filter(value: str) -> str:
    """10.5.7 — `?status=` değeri; tanınmayan değer varsayılan (`active`)."""
    return value if value in STATUS_FILTERS else DEFAULT_STATUS


def list_employees(
    session: Session,
    query: str = "",
    page: int = 1,
    packages: str = "",
    *,
    status_filter: str = DEFAULT_STATUS,
    statuses: frozenset[str] | None = None,
) -> EmployeeListing:
    """10.4.1/10.4.2/14.3.1/10.5.7 — çalışanların `page`. sayfası; `query` boşsa hepsi, doluysa
    uyanlar. `packages="missing"` yalnız en az bir açık (zorunlu kalemi eksik) paketi olanları
    bırakır. `status_filter` listenin durum süzgecidir (`active` varsayılan, `inactive`, `all`);
    `statuses` verilirse süzgecin yerine yalnız o durumlar aranır ve süzgeç seçenekleri
    hesaplanmaz (atama ve taşıma aramaları).

    Sayfa sayısını aşan `page` son sayfaya indirilir. Sıra soyad, ad, çalışan numarasıdır.
    """
    query = " ".join(query.split())
    packages = packages if packages == MISSING_PACKAGES else ""
    status_filter = normalize_status_filter(status_filter)
    base = [_term_matches(session, term) for term in search_terms(query)]
    if packages:
        base.append(Employee.id.in_(sorted(employees_with_missing_packages(session))))
    wanted = statuses if statuses is not None else STATUS_FILTERS[status_filter]
    filters = base if wanted is None else [*base, Employee.status.in_(sorted(wanted))]
    options = (
        []
        if statuses is not None
        else _status_options(session, base, query, packages, status_filter)
    )
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
            status_label=status_label(employee.status),
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
        previous_url=(_page_url(query, page - 1, packages, status_filter) if page > 1 else None),
        next_url=(
            _page_url(query, page + 1, packages, status_filter) if page < page_count else None
        ),
        packages=packages,
        status=status_filter,
        status_options=options,
    )


def _status_options(
    session: Session,
    base: list[ColumnElement[bool]],
    query: str,
    packages: str,
    selected: str,
) -> list[StatusOption]:
    # Sayaçlar aramaya ve paket süzgecine uyan çalışanlardır (durumdan bağımsız); tek sorgu.
    by_status: dict[str, int] = {
        status_value: count
        for status_value, count in session.execute(
            select(Employee.status, func.count()).where(*base).group_by(Employee.status)
        )
    }
    return [
        StatusOption(
            value=value,
            label=STATUS_FILTER_LABELS[value],
            count=sum(
                count
                for status_value, count in by_status.items()
                if wanted is None or status_value in wanted
            ),
            url=_page_url(query, 1, packages, value),
            selected=value == selected,
        )
        for value, wanted in STATUS_FILTERS.items()
    ]


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
    status_filter: Annotated[str, Query(alias="status", max_length=16)] = DEFAULT_STATUS,
) -> HTMLResponse:
    listing = list_employees(session, q, page, packages, status_filter=status_filter)
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
EMPLOYEE_NOT_FOUND = N_("Çalışan bulunamadı.")
DOCUMENT_NOT_FOUND = N_("Belge bulunamadı.")
FILE_NOT_FOUND = N_("Belge dosyası bulunamadı.")

CONTACT_LABELS = {
    ContactKind.PHONE.value: N_("Telefon"),
    ContactKind.EMAIL.value: N_("E-posta"),
    ContactKind.ADDRESS.value: N_("Adres"),
}
# Kartın alan etiketleri (05.7.3 uyarısı "<alan>: belgede farklı değer okundu").
FIELD_LABELS = {
    ProfileField.GIVEN_NAMES: N_("Ad"),
    ProfileField.SURNAME: N_("Soyad"),
    ProfileField.OTHER_NAMES: N_("Diğer isimler"),
    ProfileField.ORIGINAL_SCRIPT_NAME: N_("Orijinal yazım"),
    ProfileField.NATIONALITY: N_("Vatandaşlık"),
    ProfileField.DATE_OF_BIRTH: N_("Doğum tarihi"),
}
FIELD_CONFLICT_WARNING = N_("{label}: belgede farklı değer okundu")
# 10.5.6: elle girilen alanın kaynağı; 10.5.9: birleştirmede birleşen kayıttan dolan alanınki.
MANUAL_SOURCE = N_("elle ({actor}, {day})")
MERGE_SOURCE = N_("birleştirme ({actor}, {day})")
# Kaynağı belge olmayan alan gözlemlerinin etiketi (bağlantısız).
_USER_SOURCES = {FieldSource.MANUAL.value: MANUAL_SOURCE, FieldSource.MERGE.value: MERGE_SOURCE}
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
    # 05.5.4: planın yalnız isimle yerleştirdiği belge.
    name_only: bool = False


@dataclass(frozen=True, slots=True)
class SourceLink:
    """Alan kaynağının bağlantısı; elle girilen alanın (10.5.6) bağlantısı yoktur (`url` boş)."""

    label: str
    url: str | None
    new_tab: bool = False


@dataclass(frozen=True, slots=True)
class FieldSources:
    """Bir profil alanının belge kaynakları (05.7.3): `source` alanı dolduran ya da aynı değeri
    okuyan belge, `conflicts` farklı değer okuyan belgeler; `warning` çakışma uyarısının metni."""

    source: SourceLink | None
    conflicts: list[SourceLink]
    warning: str


@dataclass(frozen=True, slots=True)
class MergedIntoView:
    """10.5.9: birleştirilmiş kaydın bildirimi — kalan kayıt (numara ve ad; yoksa yalnız numara)."""

    id: str
    name: str | None


@dataclass(frozen=True, slots=True)
class DeactivationView:
    """Pasif çalışanın bildirimi: pasife alan kullanıcı, zaman ve (varsa) notu."""

    actor: str | None
    at: datetime
    reason: str | None


# 10.5.8: kaynağı belge olan ama belge kimliği tutulmamış kayıt (05.7.2, 05.8.1 — birikim çıktı
# belgesinden önce yapılır); elle eklenen iletişim bilgisi `MANUAL_SOURCE`'u taşır.
FROM_DOCUMENT = N_("belgeden")
RECORD_KIND_LABELS = {
    RecordKind.ALIAS.value: N_("İsim yazımı"),
    RecordKind.IDENTIFIER.value: N_("Belge numarası"),
}
ALIAS_SCRIPT_LABELS = {
    Script.LATIN.value: N_("Latin"),
    Script.CYRILLIC.value: N_("Kiril"),
    Script.ARABIC.value: N_("Arap"),
    Script.OTHER.value: N_("diğer"),
}
NO_SCRIPT = "—"


@dataclass(frozen=True, slots=True)
class RecordRow:
    """10.5.8 — profil alt kaydının satırı. `label` isim yazımında alfabe, numarada belge türü,
    iletişimde "Telefon"/"E-posta"/"Adres"; `kind_label` kaldırılanlar listesindeki tür adı.
    Kaldırılmış kayıt kim ve ne zaman kaldırıldığını ve (belgede yeniden görüldüyse) uyarıyı
    taşır."""

    kind: str
    id: int
    kind_label: str
    label: str
    value: str
    source: SourceLink | None = None
    current: bool = False
    removed_by: str | None = None
    removed_at: datetime | None = None
    warning: str | None = None


@dataclass(frozen=True, slots=True)
class RecordSections:
    """10.5.8 — profilin alt kayıt bölümü: etkin yazımlar, numaralar ve iletişim bilgileri,
    kaldırılanlar (en son kaldırılan önce) ve belgede yeniden görülen kaldırılmış kayıt
    uyarıları."""

    aliases: list[RecordRow] = field(default_factory=list)
    numbers: list[RecordRow] = field(default_factory=list)
    contacts: list[RecordRow] = field(default_factory=list)
    removed: list[RecordRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


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
    # 10.5.6: "Profili düzenle" bağlantısı; birleştirilmiş çalışanda yok.
    editable: bool = True
    # 10.5.7: durum, "Pasife al"/"Yeniden etkinleştir" bağlantısının hedefi (birleştirilmişte yok)
    # ve pasif çalışanın bildirimi (son pasife alma olayı).
    status: str = EmployeeStatus.ACTIVE.value
    status_action: str | None = EmployeeStatus.INACTIVE.value
    deactivation: DeactivationView | None = None
    # 10.5.8: alt kayıtlar; "Kaldır", "Geri al" ve ekleme formu birleştirilmişte (`editable`) yok.
    records: RecordSections = field(default_factory=RecordSections)
    # 10.5.9: birleştirilmiş kaydın kalan kaydı (bildirim ve bağlantı); "Başka kayıtla birleştir"
    # bağlantısı birleştirilmişte yok.
    merged_into: MergedIntoView | None = None

    @property
    def merged(self) -> bool:
        return self.status == EmployeeStatus.MERGED.value

    @property
    def inactive(self) -> bool:
        return self.status == EmployeeStatus.INACTIVE.value

    @property
    def can_upload(self) -> bool:
        # 10.5.3: profilden yükleme yalnız etkin çalışana (pasife 409).
        return self.status == EmployeeStatus.ACTIVE.value

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


def _stored_file(layout: DataLayout, relative_path: str | None) -> Path | None:
    """Belgenin diskteki dosyası; yolu boşsa (kalıcı silinmiş belge, 10.5.12), veri dizininden
    kaçıyorsa ya da dosya yoksa `None`."""
    if relative_path is None:
        return None
    try:
        path = layout.resolve(relative_path)
    except ValueError:
        return None
    return path if path.is_file() else None


def _stored_document(layout: DataLayout, document: Document) -> StoredDocument | None:
    path = _stored_file(layout, document.path)
    if path is None or document.path is None:
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

    # 10.5.8: kart yalnız etkin (kaldırılmamış) numarayı ve güncel iletişim bilgisini gösterir.
    identifiers = session.scalars(
        select(EmployeeIdentifier)
        .where(EmployeeIdentifier.employee_id == employee_id, ACTIVE_IDENTIFIER)
        .order_by(EmployeeIdentifier.id)
    ).all()
    records = employee_records(session, employee_id)
    # Numaranın türü belge türü slug'ıdır; kişiye okunur ad için katalogdan çevrilir.
    type_names = {
        slug: name
        for slug, name in session.execute(
            select(KnownDocumentType.slug, KnownDocumentType.name).where(
                KnownDocumentType.slug.in_({identifier.kind for identifier in records.identifiers})
            )
        )
    }
    current_contacts = session.scalars(
        select(EmployeeContact)
        .where(
            EmployeeContact.employee_id == employee_id,
            EmployeeContact.is_current.is_(True),
            ACTIVE_CONTACT,
        )
        .order_by(EmployeeContact.id)
    ).all()
    documents = session.execute(
        select(Document, KnownDocumentType.name)
        .join(KnownDocumentType, KnownDocumentType.slug == Document.type_slug)
        .where(
            Document.employee_id == employee_id,
            # 10.5.12: kalıcı silinen belge listeden kalkar (iskeleti geçmiş sayfasında görünür).
            Document.status != DocumentStatus.DELETED.value,
        )
        .order_by(Document.created_at.desc(), Document.id.desc())
    ).all()

    by_name = name_matched_documents(document for document, _ in documents)
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
            name_only=document.id in by_name,
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
        status_label=status_label(employee.status),
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
        editable=employee.status != MERGED_STATUS,
        status=employee.status,
        status_action=_status_action(employee),
        deactivation=_deactivation(session, employee),
        records=_record_sections(employee_id, records, type_names, rows),
        merged_into=_merged_into(session, employee),
    )


def _status_action(employee: Employee) -> str | None:
    try:
        return status_target(employee).value
    except EmployeeStatusError:
        return None


def _merged_into(session: Session, employee: Employee) -> MergedIntoView | None:
    if employee.status != MERGED_STATUS or employee.merged_into_id is None:
        return None
    kept = session.get(Employee, employee.merged_into_id)
    name = None if kept is None else f"{kept.given_names} {kept.surname}"
    return MergedIntoView(id=employee.merged_into_id, name=name)


def _deactivation(session: Session, employee: Employee) -> DeactivationView | None:
    if employee.status != EmployeeStatus.INACTIVE.value:
        return None
    event = last_deactivation(session, employee.id)
    if event is None:  # olaysız (elle yazılmış) kayıt: bildirim yine çıkar, ayrıntısız
        return None
    data = event.data_json if isinstance(event.data_json, dict) else {}
    reason = data.get("reason")
    return DeactivationView(
        actor=event.actor, at=event.ts, reason=reason if isinstance(reason, str) else None
    )


def _removal_warning(kind: RecordKind, record: ProfileRecord) -> str | None:
    """`seen_after_removal_warning`'in isteğin dilindeki hâli (10.10.3): kayıt türü de çevrilir."""
    if seen_after_removal_warning(kind, record) is None:
        return None
    return Translatable(SEEN_AFTER_REMOVAL_WARNING, label=Translatable(record_label(kind, record)))


def _record_sections(
    employee_id: str,
    records: EmployeeRecords,
    type_names: dict[str, str],
    documents: list[DocumentRow],
) -> RecordSections:
    """10.5.8 — alt kayıtların profil satırları; değer olduğu gibi gösterilir (K17)."""
    by_id = {row.id: row for row in documents}

    def document_source(document_id: int | None) -> SourceLink:
        if document_id is None:
            return SourceLink(label=FROM_DOCUMENT, url=None)
        row = by_id.get(document_id)
        if row is None:  # belge artık bu çalışanda değil (taşındı): geçmişi açılır
            label = Translatable(N_("Belge {id}"), id=document_id)
            return SourceLink(label=label, url=f"/documents/{document_id}/history")
        if row.available:
            url = f"/employees/{employee_id}/documents/{row.id}/file"
            return SourceLink(label=row.file_name, url=url, new_tab=True)
        return SourceLink(label=row.file_name, url=f"/documents/{row.id}/history")

    def record_row(kind: RecordKind, record: ProfileRecord) -> RecordRow:
        removal = {
            "removed_by": record.removed_by,
            "removed_at": record.removed_at,
            "warning": _removal_warning(kind, record),
        }
        if isinstance(record, EmployeeAlias):
            return RecordRow(
                kind.value,
                record.id,
                RECORD_KIND_LABELS[kind.value],
                ALIAS_SCRIPT_LABELS.get(record.script or "", NO_SCRIPT),
                record.raw_name,
                **removal,
            )
        if isinstance(record, EmployeeIdentifier):
            return RecordRow(
                kind.value,
                record.id,
                RECORD_KIND_LABELS[kind.value],
                type_names.get(record.kind, record.kind),
                record.value,
                source=document_source(record.source_document_id),
                **removal,
            )
        label = CONTACT_LABELS.get(record.kind, record.kind)
        if record.added_by:
            day = record.first_seen_at.strftime("%d.%m.%Y")
            manual = Translatable(MANUAL_SOURCE, actor=record.added_by, day=day)
            source = SourceLink(label=manual, url=None)
        else:
            source = document_source(record.source_document_id)
        return RecordRow(
            kind.value,
            record.id,
            label,
            label,
            record_value(record),
            source=source,
            current=record.is_current,
            **removal,
        )

    removed = [record_row(kind, record) for kind, record in records.removed]
    return RecordSections(
        aliases=[
            record_row(RecordKind.ALIAS, each)
            for each in records.aliases
            if each.removed_at is None
        ],
        numbers=[
            record_row(RecordKind.IDENTIFIER, each)
            for each in records.identifiers
            if each.removed_at is None
        ],
        contacts=[
            record_row(RecordKind.CONTACT, each)
            for each in records.contacts
            if each.removed_at is None
        ],
        removed=removed,
        warnings=list(dict.fromkeys(each.warning for each in removed if each.warning)),
    )


def _field_sources(
    session: Session,
    employee_id: str,
    documents: list[Document],
    rows: list[DocumentRow],
) -> dict[str, FieldSources]:
    """05.7.3 — alan başına kaynak ve çakışma bağlantıları (gözlem sırasıyla); gözlemi olmayan
    alan sözlükte yoktur. Değer gösterilmez: kart alanın kendi değerini zaten gösterir.

    Alan elle düzenlendiyse (10.5.6, `source=manual`) kaynak son düzenlemedir ("elle", kullanıcı ve
    gün) — ondan sonra alanı dolduran belge yoksa. O düzenlemeden önceki gözlemler (kaynak ve
    çakışma) eski değerle karşılaştırıldığı için düşer, sonrakiler kalır."""
    observations = session.execute(
        select(EmployeeFieldObservation, UploadFile.upload_id)
        .outerjoin(UploadFile, UploadFile.id == EmployeeFieldObservation.file_id)
        .where(EmployeeFieldObservation.employee_id == employee_id)
        .order_by(EmployeeFieldObservation.observed_at, EmployeeFieldObservation.id)
    ).all()
    if not observations:
        return {}
    by_source = _documents_by_source(documents)
    available = {row.id: row.available for row in rows}

    def link(observation: EmployeeFieldObservation, upload_id: str | None) -> SourceLink:
        if observation.source in _USER_SOURCES:
            day = observation.observed_at.strftime("%d.%m.%Y")
            label = Translatable(
                _USER_SOURCES[observation.source], actor=observation.actor, day=day
            )
            return SourceLink(label=label, url=None)
        document = by_source.get((observation.file_id, observation.page_index))
        if document is None:
            label = Translatable(N_("Parti {id}"), id=upload_id)
            return SourceLink(label=label, url=f"/uploads/{upload_id}")
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
        manual = [
            index
            for index, (observation, _) in enumerate(seen)
            if observation.source == FieldSource.MANUAL.value
        ]
        edited = seen[manual[-1]] if manual else None
        if manual:
            seen = seen[manual[-1] + 1 :]
        by_outcome = {
            outcome: [(obs, upload) for obs, upload in seen if obs.outcome == outcome.value]
            for outcome in FieldOutcome
        }
        # Kaynak: alanı dolduran belge; yoksa son elle düzenleme; o da yoksa (alan belgeden önce
        # doluydu) aynı değeri okuyan ilk belge.
        origin = [
            *by_outcome[FieldOutcome.FILLED],
            *([edited] if edited is not None else by_outcome[FieldOutcome.SAME]),
        ]
        conflicts = list(
            dict.fromkeys(link(obs, upload) for obs, upload in by_outcome[FieldOutcome.CONFLICT])
        )
        sources[profile_field.value] = FieldSources(
            source=link(*origin[0]) if origin else None,
            conflicts=conflicts,
            warning=Translatable(FIELD_CONFLICT_WARNING, label=Translatable(label)),
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
    "package_assigned": N_("Paket tanımlandı."),
    "package_cancelled": N_("Paket iptal edildi."),
    "package_reopened": N_("Paket yeniden açıldı."),
}
# 10.5.6: düzenlemeden sonra profil sayfasının bildirimi.
PROFILE_NOTICES = {
    "fields_changed": N_("Profil bilgileri değiştirildi."),
    "fields_renamed": (
        N_(
            "Profil bilgileri değiştirildi; klasör ve belge dosyaları yeni adla yeniden "
            "adlandırıldı."
        )
    ),
    # 10.5.7
    "status_inactive": N_("Çalışan pasife alındı; yeni belgeleri otomatik yerleşmeyecek."),
    "status_active": N_("Çalışan yeniden etkinleştirildi."),
    # 10.5.9
    "merged": (
        N_(
            "Kayıtlar birleştirildi; birleşen kaydın belgeleri, numaraları, isim yazımları, "
            "iletişim bilgileri ve belge paketleri bu profile taşındı."
        )
    ),
}
# 10.5.8: alt kayıt işlemlerinden sonra "Profil kayıtları" bölümünün bildirimi.
RECORD_NOTICES = {
    "record_removed": N_("Kayıt kaldırıldı; eşleştirmede ve aramada kullanılmayacak."),
    "record_restored": N_("Kayıt geri alındı; yeniden eşleştirmede ve aramada kullanılacak."),
    "contact_added": N_("İletişim bilgisi eklendi."),
}
# 08.4.1, 10.5.10, 10.5.12: profilden arşive taşıma, arşivden geri alma ve kalıcı silmeden sonra
# "Belgeler" bölümünün bildirimi.
DOCUMENT_NOTICES = {
    "document_archived": N_("Belge arşive taşındı; çalışanın Hazır klasöründen çıktı."),
    "document_unarchived": N_("Belge arşivden geri alındı; çalışanın Hazır klasörüne döndü."),
    "document_deleted": N_("Belge kalıcı olarak silindi; dosyaları diskten kaldırıldı."),
    "document_deleted_partial": N_(
        "Belge kalıcı olarak silindi, ancak bazı dosyaları diskten kaldırılamadı (açık ya da "
        "kilitli olabilir); sayısı olay logunda. Sistem yöneticisine bildirin."
    ),
}
PACKAGE_NOT_FOUND = N_("Paket bulunamadı.")
GROUP_NOT_FOUND = N_("Belge grubu bulunamadı.")
DUPLICATE_PACKAGE = N_(
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
    record_problems: list[str] | None = None,
    contact_form: ContactFormValues | None = None,
    contact_problems: dict[str, list[str]] | None = None,
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
        profile_notice=PROFILE_NOTICES.get(notice or ""),
        note_limit=NOTE_MAX_LENGTH,
        records_notice=RECORD_NOTICES.get(notice or ""),
        documents_notice=DOCUMENT_NOTICES.get(notice or ""),
        record_problems=record_problems or [],
        contact_form=contact_form or ContactFormValues(),
        contact_problems=contact_problems or {},
        contact_kinds=CONTACT_LABELS,
        contact_limit=CONTACT_VALUE_MAX_LENGTH,
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
    except (GroupArchivedError, PackageStateError) as exc:
        # Arşivdeki grup ya da birleştirilmiş çalışan (10.5.9).
        problems, status_code = {"group_id": [exc]}, status.HTTP_409_CONFLICT
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
            cancel_problems={package_id: [exc]},
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
            cancel_problems={package_id: [exc]},
            status_code=status.HTTP_409_CONFLICT,
        )
    session.commit()
    _rewrite_profile(session, layout, employee_id)
    return _package_redirect(employee_id, "package_reopened")


# --- 10.5.6: çalışan profilini düzenleme -------------------------------------------------------

# §20.6 "Çalışan profilini düzenle": metinler birebir `app.web.confirm`'dadır; `<N>` dosyası
# yeniden adlandırılacak belge sayısıyla dolar.
NOT_EDITABLE = N_(
    "Bu çalışan başka bir kayıtla birleştirildi; profili düzenlenmez, kalan kaydı düzenleyin."
)
NO_FIELD_CHANGES = N_("Hiçbir alan değişmedi; değiştirmek istediğiniz alanı düzenleyin.")


@dataclass(frozen=True, slots=True)
class EditTarget:
    """Düzenlenen çalışan: sayfa başlığı için."""

    id: str
    name: str


@dataclass(frozen=True, slots=True)
class FieldChangeView:
    """İkinci onay adımındaki özet satırı: alanın şimdiki ve yeni değeri."""

    label: str
    before: str
    after: str
    changed: bool


def fields_subject(employee_id: str, fields: ProfileFields) -> str:
    """Düzenleme belirtecinin (`Operation.EDIT_EMPLOYEE`) bağlı olduğu hedef: çalışan + form
    değerlerinin özeti. Hazırlıktan sonra bir alan değişirse belirteç geçmez; değerler belirtece
    girmez."""
    return f"{employee_id}:{profile_digest(fields)}"


def _editable_employee(session: Session, employee_id: str) -> Employee:
    """Düzenlenecek çalışan (satır kilitli); yoksa 404, birleştirilmişse 409."""
    employee = session.get(Employee, employee_id, with_for_update=True)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, EMPLOYEE_NOT_FOUND)
    if employee.status == MERGED_STATUS:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_EDITABLE)
    return employee


def _edit_target(employee: Employee) -> EditTarget:
    return EditTarget(id=employee.id, name=f"{employee.given_names} {employee.surname}")


def _field_changes(employee: Employee, fields: ProfileFields) -> list[FieldChangeView]:
    before, after = profile_values(current_profile_fields(employee)), profile_values(fields)
    return [
        FieldChangeView(
            label=PROFILE_LABELS[name],
            before=profile_text(name, before[name]),
            after=profile_text(name, after[name]),
            changed=before[name] != after[name],
        )
        for name in PROFILE_FIELDS
    ]


def _fields_page(
    request: Request,
    user: PanelUser,
    employee_id: str,
    *,
    target: EditTarget | None,
    status_code: int = status.HTTP_200_OK,
    **context: object,
) -> HTMLResponse:
    """`employee_fields.html`: düzenleme formu, ikinci onay adımı ya da hata."""
    return render_page(
        request,
        "employee_fields.html",
        user=user,
        active=MENU_BY_KEY["employees"].key,
        status_code=status_code,
        employee_id=employee_id,
        target=target,
        first_confirmation=first_text(Operation.EDIT_EMPLOYEE),
        **context,
    )


def _refused_fields(
    request: Request,
    user: PanelUser,
    employee_id: str,
    target: EditTarget | None,
    values: dict[str, str],
    exc: Exception,
) -> HTMLResponse:
    """Reddedilen düzenleme: çalışan yoksa ya da birleştirilmişse yalnız hata; geçersiz ya da
    değişmemiş alanlar (422) ve tamamlanamayan yeniden adlandırma (409) girilen değerlerle formu
    yeniden çizer; belirteç reddi (400) formu yeniden açma bağlantısı verir."""
    if isinstance(exc, HTTPException):
        return _fields_page(
            request, user, employee_id, target=None, status_code=exc.status_code, error=exc.detail
        )
    if isinstance(exc, ConfirmationRefusedError):
        return _fields_page(
            request,
            user,
            employee_id,
            target=target,
            status_code=status.HTTP_400_BAD_REQUEST,
            error=CONFIRMATION_REFUSED,
            retry=True,
        )
    status_code, error, field_errors = status.HTTP_422_UNPROCESSABLE_CONTENT, INVALID_PROFILE, []
    if isinstance(exc, ProfileFormError):
        field_errors = exc.field_errors()
    elif isinstance(exc, ProfileFieldsError):
        field_errors = ProfileFormError(exc.errors).field_errors()
    elif isinstance(exc, NoFieldChangesError):
        error = NO_FIELD_CHANGES
    else:  # birleştirilmiş çalışan, yeniden adlandırma
        status_code, error = status.HTTP_409_CONFLICT, str(exc)
    return _fields_page(
        request,
        user,
        employee_id,
        target=target,
        status_code=status_code,
        error=error,
        field_errors=field_errors,
        form=profile_form_fields(values),
    )


# `_refused_fields`'in çizdiği reddedilen düzenlemeler; hepsinde oturum geri alınır.
_FIELDS_REFUSALS = (
    HTTPException,
    ProfileFormError,
    ProfileFieldsError,
    EmployeeEditRefusedError,
    EmployeeRenameError,
)


@router.get("/employees/{employee_id}/fields", response_class=HTMLResponse)
def employee_fields_form(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """10.5.6 — çalışanın alanlarıyla dolu düzenleme formu ve birinci onay metni; hiçbir şey
    değişmez."""
    try:
        employee = _editable_employee(session, employee_id)
        target = _edit_target(employee)
        values = profile_values(current_profile_fields(employee))
    except HTTPException as exc:
        return _refused_fields(request, user, employee_id, None, {}, exc)
    finally:
        session.rollback()
    return _fields_page(request, user, employee_id, target=target, form=profile_form_fields(values))


@router.post("/employees/{employee_id}/fields/prepare", response_class=HTMLResponse)
def prepare_employee_fields(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    values: ProfileValues,
) -> HTMLResponse:
    """10.5.6 — birinci onaydan sonra alanları denetler; değişikliklerin özetini, ikinci onay
    metnini ve form değerlerine bağlı tek kullanımlık onay belirtecini verir (§20.6.1). Hiçbir alanı
    değiştirmez (S16)."""
    target: EditTarget | None = None
    try:
        employee = _editable_employee(session, employee_id)
        target = _edit_target(employee)
        fields = parse_profile(values)
        preview = preview_employee_edit(session, layout, employee, fields)
        changes = _field_changes(employee, fields)
        issued = issue_confirmation(
            session, request, user, Operation.EDIT_EMPLOYEE, fields_subject(employee.id, fields)
        )
    except (*_FIELDS_REFUSALS, ConfirmationRefusedError) as exc:
        session.rollback()
        if isinstance(exc, ConfirmationRefusedError):  # oturum çerezi yok
            return _fields_page(
                request,
                user,
                employee_id,
                target=target,
                status_code=status.HTTP_400_BAD_REQUEST,
                error=exc,
            )
        return _refused_fields(request, user, employee_id, target, values, exc)
    session.commit()
    return _fields_page(
        request,
        user,
        employee_id,
        target=target,
        changes=changes,
        second_confirmation=second_text(Operation.EDIT_EMPLOYEE, count=preview.documents),
        hidden=profile_values(fields),
        confirmation=issued.token,
    )


@router.post("/employees/{employee_id}/fields", response_class=HTMLResponse)
def change_employee_fields(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    values: ProfileValues,
    confirmation: Annotated[str | None, Form()] = None,
) -> Response:
    """10.5.6 — ikinci onayın belirteciyle alanları değiştirir; ad değiştiyse klasör ve etkin belge
    dosyaları K8 adına yeniden adlandırılır (K8, K11, K16).

    Belirteç yoksa, süresi geçmişse, kullanılmışsa ya da başka değerlere, çalışana, işleme veya
    oturuma aitse hiçbir şey yapılmaz (400). Belirtecin tüketilmesi, onay olayı ve düzenleme tek
    işlemdedir: yeniden adlandırma yarıda kalırsa dosyalar geri alınır, onay olayı yazılmaz,
    belirteç tüketilmemiş kalır (409). Commit'ten sonra `profil.md` yeniden üretilir (09.1.1) ve
    profil sayfasına dönülür.
    """
    target: EditTarget | None = None
    try:
        employee = _editable_employee(session, employee_id)
        target = _edit_target(employee)
        fields = parse_profile(values)
        # §20.6.1: belirteç tüketilir ve `USER_CONFIRMED` (kullanıcı adı, işlem, hedef, iki onayın
        # zamanı) yazılır, ardından işlemin kendi olayı (`EMPLOYEE_EDITED`) düşer. Alan değerleri
        # olaya girmez (CONVENTIONS §6).
        confirm_operation(
            session,
            request,
            user,
            Operation.EDIT_EMPLOYEE,
            fields_subject(employee.id, fields),
            confirmation,
            event_target={"employee_id": employee.id},
            employee_id=employee.id,
        )
        edited = update_employee_fields(session, layout, employee, fields, actor=user.username)
    except (*_FIELDS_REFUSALS, ConfirmationRefusedError) as exc:
        session.rollback()
        return _refused_fields(request, user, employee_id, target, values, exc)
    session.commit()
    notice = "fields_renamed" if edited.renamed else "fields_changed"
    _rewrite_profile(session, layout, employee_id)
    return RedirectResponse(f"/employees/{employee_id}?notice={notice}", status.HTTP_303_SEE_OTHER)


# --- 10.5.7: çalışanı pasife alma ve yeniden etkinleştirme -------------------------------------

# §20.6 "Çalışanı pasife al" / "Çalışanı yeniden etkinleştir": metinler birebir
# `app.web.confirm`'dadır; `<Ad Soyad>` çalışanın adıyla dolar.
STATUS_OPERATIONS = {
    EmployeeStatus.INACTIVE: Operation.DEACTIVATE_EMPLOYEE,
    EmployeeStatus.ACTIVE: Operation.REACTIVATE_EMPLOYEE,
}
STATUS_TITLES = {
    EmployeeStatus.INACTIVE: N_("Çalışanı pasife al"),
    EmployeeStatus.ACTIVE: N_("Çalışanı yeniden etkinleştir"),
}
BAD_STATUS_TARGET = N_("Hedef durum yalnız pasif (inactive) ya da aktif (active) olabilir.")
STATUS_NOT_CHANGEABLE = N_("Bu çalışan başka bir kayıtla birleştirildi; durumu değiştirilmez.")
STATUS_ALREADY = {
    EmployeeStatus.INACTIVE: N_("Çalışan zaten pasif."),
    EmployeeStatus.ACTIVE: N_("Çalışan zaten etkin."),
}
# Form sınırı yalnız aşırı girdiye karşıdır; not kuralını (≤ 200) servis mesajla bildirir.
STATUS_FORM_LIMIT = 1000
StatusTo = Annotated[str, Form(max_length=16)]
StatusReason = Annotated[str | None, Form(max_length=STATUS_FORM_LIMIT)]


def status_subject(employee_id: str, target: EmployeeStatus, reason: str | None) -> str:
    """Durum belirtecinin (`Operation.DEACTIVATE_EMPLOYEE`/`REACTIVATE_EMPLOYEE`) bağlı olduğu
    hedef: çalışan + hedef durum + notun özeti. Hazırlıktan sonra not değişirse belirteç geçmez;
    not belirtece girmez."""
    digest = hashlib.sha256((reason or "").encode("utf-8")).hexdigest()[:16]
    return f"{employee_id}:{target.value}:{digest}"


def _status_value(value: str) -> EmployeeStatus:
    """`to` alanı: yalnız `inactive` ya da `active`; başkası 422."""
    target = next((each for each in STATUS_OPERATIONS if each.value == value), None)
    if target is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, BAD_STATUS_TARGET)
    return target


def _status_employee(session: Session, employee_id: str, target: EmployeeStatus) -> Employee:
    """Durumu değişecek çalışan (satır kilitli); yoksa 404, birleştirilmişse ya da zaten o
    durumdaysa 409."""
    employee = session.get(Employee, employee_id, with_for_update=True)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, EMPLOYEE_NOT_FOUND)
    if employee.status == MERGED_STATUS:
        raise HTTPException(status.HTTP_409_CONFLICT, STATUS_NOT_CHANGEABLE)
    try:
        check_status_change(employee, target)
    except EmployeeStatusError:
        raise HTTPException(status.HTTP_409_CONFLICT, STATUS_ALREADY[target]) from None
    return employee


def _status_page(
    request: Request,
    user: PanelUser,
    employee_id: str,
    *,
    target: EditTarget | None,
    to: EmployeeStatus | None,
    status_code: int = status.HTTP_200_OK,
    **context: object,
) -> HTMLResponse:
    """`employee_status_step.html`: birinci onay (not alanıyla), ikinci onay ya da hata."""
    return render_page(
        request,
        "employee_status_step.html",
        user=user,
        active=MENU_BY_KEY["employees"].key,
        status_code=status_code,
        employee_id=employee_id,
        target=target,
        to=to.value if to is not None else None,
        title=STATUS_TITLES[to] if to is not None else N_("Çalışanın durumu"),
        reason_limit=REASON_MAX_LENGTH,
        **context,
    )


@router.get("/employees/{employee_id}/status/confirm", response_class=HTMLResponse)
def employee_status_first_confirmation(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    to: Annotated[str, Query(max_length=16)],
) -> HTMLResponse:
    """10.5.7 — birinci onay metni (§20.6) ve isteğe bağlı not alanı; hiçbir şey değişmez."""
    target: EditTarget | None = None
    wanted: EmployeeStatus | None = None
    try:
        wanted = _status_value(to)
        employee = _status_employee(session, employee_id, wanted)
        target = _edit_target(employee)
    except HTTPException as exc:
        return _status_page(
            request,
            user,
            employee_id,
            target=None,
            to=wanted,
            status_code=exc.status_code,
            error=exc.detail,
        )
    finally:
        session.rollback()
    return _status_page(
        request,
        user,
        employee_id,
        target=target,
        to=wanted,
        first_confirmation=first_text(STATUS_OPERATIONS[wanted], name=target.name),
        reason="",
    )


@router.post("/employees/{employee_id}/status/prepare", response_class=HTMLResponse)
def prepare_employee_status(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    to: StatusTo,
    reason: StatusReason = None,
) -> HTMLResponse:
    """10.5.7 — birinci onaydan sonra ikinci onay metnini ve hedef duruma + nota bağlı tek
    kullanımlık belirteci verir (§20.6.1). Durumu değiştirmez (S16)."""
    wanted: EmployeeStatus | None = None
    try:
        wanted = _status_value(to)
        employee = _status_employee(session, employee_id, wanted)
    except HTTPException as exc:
        session.rollback()
        return _status_page(
            request,
            user,
            employee_id,
            target=None,
            to=wanted,
            status_code=exc.status_code,
            error=exc.detail,
        )
    target = _edit_target(employee)
    try:
        note = normalized_reason(reason)
    except StatusReasonError as exc:
        session.rollback()
        return _status_page(
            request,
            user,
            employee_id,
            target=target,
            to=wanted,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            error=exc,
            first_confirmation=first_text(STATUS_OPERATIONS[wanted], name=target.name),
            reason=reason or "",
        )
    try:
        issued = issue_confirmation(
            session,
            request,
            user,
            STATUS_OPERATIONS[wanted],
            status_subject(employee.id, wanted, note),
        )
    except ConfirmationRefusedError as exc:  # oturum çerezi yok
        session.rollback()
        return _status_page(
            request,
            user,
            employee_id,
            target=target,
            to=wanted,
            status_code=status.HTTP_400_BAD_REQUEST,
            error=exc,
        )
    session.commit()
    return _status_page(
        request,
        user,
        employee_id,
        target=target,
        to=wanted,
        second_confirmation=second_text(STATUS_OPERATIONS[wanted]),
        reason=note or "",
        confirmation=issued.token,
    )


@router.post("/employees/{employee_id}/status", response_class=HTMLResponse)
def change_employee_status_endpoint(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    to: StatusTo,
    reason: StatusReason = None,
    confirmation: Annotated[str | None, Form()] = None,
) -> Response:
    """10.5.7 — ikinci onayın belirteciyle çalışanı pasife alır ya da yeniden etkinleştirir
    (K16, R11).

    Belirteç yoksa, süresi geçmişse, kullanılmışsa ya da başka çalışana, hedefe, nota, işleme veya
    oturuma aitse hiçbir şey yapılmaz (400). Belirtecin tüketilmesi, `USER_CONFIRMED` ve
    `EMPLOYEE_DEACTIVATED`/`EMPLOYEE_REACTIVATED` tek işlemdedir. Klasör ve belgeler yerinde kalır;
    commit'ten sonra `profil.md` yeniden üretilir (09.1.1) ve profil sayfasına dönülür.
    """
    target: EditTarget | None = None
    wanted: EmployeeStatus | None = None
    try:
        wanted = _status_value(to)
        employee = _status_employee(session, employee_id, wanted)
        target = _edit_target(employee)
        # Hazırlıkta denetlenen not; kurala uymayan not hiçbir belirtece bağlanmamıştır (400).
        note = normalized_reason(reason)
        # §20.6.1: belirteç tüketilir ve `USER_CONFIRMED` yazılır, ardından işlemin kendi olayı
        # düşer. Not olaya işlemin verisinde girer, onay hedefine girmez.
        confirm_operation(
            session,
            request,
            user,
            STATUS_OPERATIONS[wanted],
            status_subject(employee.id, wanted, note),
            confirmation,
            event_target={"employee_id": employee.id, "status": wanted.value},
            employee_id=employee.id,
        )
        change_employee_status(session, employee, wanted, actor=user.username, reason=note)
    except HTTPException as exc:
        session.rollback()
        return _status_page(
            request,
            user,
            employee_id,
            target=None,
            to=wanted,
            status_code=exc.status_code,
            error=exc.detail,
        )
    except (ConfirmationRefusedError, StatusReasonError):
        session.rollback()
        return _status_page(
            request,
            user,
            employee_id,
            target=target,
            to=wanted,
            status_code=status.HTTP_400_BAD_REQUEST,
            error=CONFIRMATION_REFUSED,
            retry=True,
        )
    session.commit()
    _rewrite_profile(session, layout, employee_id)
    return RedirectResponse(
        f"/employees/{employee_id}?notice=status_{wanted.value}", status.HTTP_303_SEE_OTHER
    )


# --- 10.5.13: pasif çalışanı kalıcı silme ------------------------------------------------------

# §20.6 "Çalışanı kalıcı sil": metinler birebir `app.web.confirm`'dadır; `<Ad Soyad>` çalışanın
# adıyla, `<N>` silinecek belge sayısıyla dolar.
DELETE_EMPLOYEE_TITLE = N_("Çalışanı kalıcı sil")
DELETE_EMPLOYEE_SUBMIT = N_("Evet, çalışanı kalıcı olarak sil")
DELETE_EMPLOYEE_HINT = N_(
    "Kalıcı silme geri alınamaz. Çalışanın klasörü (Hazir, Alinan, profil.md), bütün belgeleri "
    "(etkin, arşivdeki, eski sürüm), isim yazımları, belge numaraları, iletişim bilgileri ve "
    "paketleri silinir; yalnız bu çalışana ait yüklemelerin orijinali ve sayfa görüntüleri de "
    "gider. Başka bir çalışana ya da açık kuyruk öğesine kaynak olan dosyalar yerinde kalır. Olay "
    "ve erişim logu satırları kalır, kişisel değerleri temizlenir."
)
EMPLOYEE_NOT_DELETABLE = N_(
    "Yalnız pasif çalışan kalıcı silinir; önce çalışanı pasife alın. Bu çalışanın durumu: {status}."
)
EMPLOYEE_DELETION_CHANGED = N_(
    "Silinecek belge sayısı onaydan sonra değişti; hiçbir şey silinmedi. Onayı yeniden başlatın."
)
# Silme yönlendirmesinden sonra "silindi" sayfasının bildirimi.
EMPLOYEE_DELETED_NOTICES = {
    "employee_deleted": N_(
        "Çalışan kalıcı olarak silindi; klasörü ve belgeleri diskten kaldırıldı."
    ),
    "employee_deleted_partial": N_(
        "Çalışan kalıcı olarak silindi, ancak bazı dosyaları diskten kaldırılamadı (açık ya da "
        "kilitli olabilir); sayısı olay logunda. Sistem yöneticisine bildirin."
    ),
}


@dataclass(frozen=True, slots=True)
class EmployeeDeleteStepView:
    id: str
    name: str
    status_label: str
    documents: int


def employee_deletion_subject(employee_id: str, documents: int) -> str:
    """Silme belirtecinin bağlı olduğu hedef: çalışan ve ikinci onayda gösterilen belge sayısı —
    kullanıcı hangi sayıyı onayladıysa belirteç yalnız onunla tüketilir."""
    return f"{employee_id}:{documents}"


def _deletable_employee(session: Session, employee_id: str) -> Employee:
    """Silinebilecek çalışan: yoksa 404; pasif değilse (etkin, birleştirilmiş) 409."""
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, EMPLOYEE_NOT_FOUND)
    try:
        check_employee_deletable(employee)
    except EmployeeNotDeletableError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            Translatable(
                EMPLOYEE_NOT_DELETABLE, status=Translatable(status_label(employee.status))
            ),
        ) from None
    return employee


def _employee_delete_step(
    session: Session, layout: DataLayout, employee_id: str
) -> EmployeeDeleteStepView:
    employee = _deletable_employee(session, employee_id)
    plan = plan_employee_deletion(session, layout, employee)
    return EmployeeDeleteStepView(
        id=employee.id,
        name=f"{employee.given_names} {employee.surname}",
        status_label=status_label(employee.status),
        documents=plan.document_count,
    )


def _employee_delete_page(
    request: Request,
    user: PanelUser,
    employee_id: str,
    *,
    step: EmployeeDeleteStepView | None,
    status_code: int = status.HTTP_200_OK,
    **context: object,
) -> HTMLResponse:
    """`employee_delete_step.html`: birinci onay, ikinci onay ya da hata."""
    return render_page(
        request,
        "employee_delete_step.html",
        user=user,
        active=MENU_BY_KEY["employees"].key,
        status_code=status_code,
        employee_id=employee_id,
        step=step,
        title=DELETE_EMPLOYEE_TITLE,
        hint=DELETE_EMPLOYEE_HINT,
        submit_label=DELETE_EMPLOYEE_SUBMIT,
        **context,
    )


@router.get("/employees/{employee_id}/delete/confirm", response_class=HTMLResponse)
def employee_delete_first_confirmation(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
) -> HTMLResponse:
    """10.5.13 — silinecek çalışan, belge sayısı ve §20.6'nın birinci onay metni; hiçbir şey
    değişmez."""
    try:
        step = _employee_delete_step(session, layout, employee_id)
    except HTTPException as exc:
        return _employee_delete_page(
            request, user, employee_id, step=None, status_code=exc.status_code, error=exc.detail
        )
    finally:
        session.rollback()
    return _employee_delete_page(
        request,
        user,
        employee_id,
        step=step,
        first_confirmation=first_text(Operation.DELETE_EMPLOYEE, name=step.name),
    )


@router.post("/employees/{employee_id}/delete/prepare", response_class=HTMLResponse)
def prepare_employee_delete(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
) -> HTMLResponse:
    """10.5.13 — ikinci onay metni (`<N>` silme planından) ve çalışana ve bu sayıya bağlı tek
    kullanımlık belirteç (§20.6.1). Hiçbir şey değişmez (S16)."""
    step: EmployeeDeleteStepView | None = None
    try:
        step = _employee_delete_step(session, layout, employee_id)
        issued = issue_confirmation(
            session,
            request,
            user,
            Operation.DELETE_EMPLOYEE,
            employee_deletion_subject(employee_id, step.documents),
        )
    except HTTPException as exc:
        session.rollback()
        return _employee_delete_page(
            request, user, employee_id, step=None, status_code=exc.status_code, error=exc.detail
        )
    except ConfirmationRefusedError as exc:  # oturum çerezi yok
        session.rollback()
        return _employee_delete_page(
            request,
            user,
            employee_id,
            step=step,
            status_code=status.HTTP_400_BAD_REQUEST,
            error=str(exc),
        )
    session.commit()
    return _employee_delete_page(
        request,
        user,
        employee_id,
        step=step,
        second_confirmation=second_text(Operation.DELETE_EMPLOYEE, count=step.documents),
        confirmation=issued.token,
    )


@router.post("/employees/{employee_id}/delete", response_class=HTMLResponse)
def delete_employee_endpoint(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    confirmation: Annotated[str | None, Form()] = None,
    documents: Annotated[int | None, Form(ge=0)] = None,
) -> Response:
    """10.5.13 — belirteçle pasif çalışanı kalıcı siler (K16, R11): önce veritabanı (iskelet, alt
    kayıtlar, planlar, olay temizliği, `USER_CONFIRMED`, `EMPLOYEE_DELETED`) tek işlemde commit
    edilir, sonra dosyalar ve klasör diskten kalkar. Belirteç yoksa, süresi geçmişse, kullanılmışsa
    ya da başka çalışana, sayıya, işleme veya oturuma aitse 400; çalışan pasif değilse ya da belge
    sayısı onaydan sonra değiştiyse 409 — hiçbirinde bir şey değişmez."""
    try:
        _deletable_employee(session, employee_id)
        if documents is None:
            raise ConfirmationRefusedError("İkinci onayın sayısı yok.")
        confirm_operation(
            session,
            request,
            user,
            Operation.DELETE_EMPLOYEE,
            employee_deletion_subject(employee_id, documents),
            confirmation,
            event_target={"employee_id": employee_id},
            employee_id=employee_id,
        )
        try:
            deleted = delete_employee(
                session, layout, employee_id, actor=user.username, expected_documents=documents
            )
        except EmployeeDeletionChangedError:
            raise HTTPException(status.HTTP_409_CONFLICT, EMPLOYEE_DELETION_CHANGED) from None
    except HTTPException as exc:
        session.rollback()
        return _employee_delete_page(
            request,
            user,
            employee_id,
            step=None,
            status_code=exc.status_code,
            error=exc.detail,
            retry=exc.detail == EMPLOYEE_DELETION_CHANGED,
        )
    except ConfirmationRefusedError:
        session.rollback()
        return _employee_delete_page(
            request,
            user,
            employee_id,
            step=None,
            status_code=status.HTTP_400_BAD_REQUEST,
            error=CONFIRMATION_REFUSED,
            retry=True,
        )
    # §D110 b: önce veritabanı; dosyalar ancak silme kalıcılaştıktan sonra diskten kalkar.
    session.commit()
    failed = remove_employee_files(session, deleted)
    if failed:
        session.commit()
    notice = "employee_deleted_partial" if failed else "employee_deleted"
    return RedirectResponse(f"/employees/{employee_id}?notice={notice}", status.HTTP_303_SEE_OTHER)


class EmployeeDeletedError(Exception):
    """10.5.13: istenen çalışan kalıcı silinmiş; `/employees/{id}` altındaki her adres "silindi"
    sayfasını (410) döner (`employee_deleted_page`)."""

    def __init__(self, employee: Employee, user: PanelUser) -> None:
        super().__init__(employee.id)
        self.employee_id = employee.id
        self.deleted_at = employee.deleted_at
        self.deleted_by = employee.deleted_by
        self.user = user


def reject_deleted_employee(
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Yönlendiricinin bağımlılığı: yolda `employee_id` varsa ve çalışan kalıcı silinmişse
    `EmployeeDeletedError` — profil, düzenleme, durum, alt kayıt, birleştirme, paket, silme ve belge
    dosyası adresleri silinen kaydı göstermez, değiştirmez."""
    employee_id = request.path_params.get("employee_id")
    if not isinstance(employee_id, str):
        return
    employee = session.get(Employee, employee_id)
    if employee is not None and employee.status == EmployeeStatus.DELETED.value:
        session.rollback()
        raise EmployeeDeletedError(employee, user)


def employee_deleted_page(request: Request, exc: Exception) -> Response:
    """`EmployeeDeletedError` → "Bu çalışan <tarih> tarihinde <kullanıcı> tarafından silindi"
    (410); kişisel değer yoktur, yalnız E numarası (10.5.13)."""
    assert isinstance(exc, EmployeeDeletedError)
    notice = EMPLOYEE_DELETED_NOTICES.get(request.query_params.get("notice", ""))
    return render_page(
        request,
        "employee_deleted.html",
        user=exc.user,
        active=MENU_BY_KEY["employees"].key,
        status_code=status.HTTP_410_GONE,
        employee_id=exc.employee_id,
        deleted_at=(
            exc.deleted_at.strftime("%d.%m.%Y %H:%M") if exc.deleted_at is not None else "—"
        ),
        deleted_by=exc.deleted_by,
        notice=notice,
    )


# --- 10.5.8: profil alt kayıtları -----------------------------------------------------------------

# §20.6 "Profil alt kaydını kaldır": metinler birebir `app.web.confirm`'dadır.
RECORD_NOT_FOUND = N_("Kayıt bulunamadı.")
RECORDS_LOCKED = N_(
    "Bu çalışan başka bir kayıtla birleştirildi; kayıtları kalan kayıtta yönetilir."
)
RECORD_ALREADY_REMOVED = N_(
    "Kayıt zaten kaldırılmış; profildeki “Kaldırılanlar” altından geri alınır."
)
RECORD_NOT_REMOVED = N_("Kayıt kaldırılmamış; geri alınacak bir şey yok.")
# Form sınırı yalnız aşırı girdiye karşıdır; değer kuralını (≤ 500) servis mesajla bildirir.
CONTACT_FORM_LIMIT = 2000


@dataclass(frozen=True, slots=True)
class ContactFormValues:
    """İletişim ekleme formunun değerleri (reddedilen form girilenlerle yeniden çizilir)."""

    kind: str = ContactKind.PHONE.value
    value: str = ""


@dataclass(frozen=True, slots=True)
class RecordStepView:
    """Kaldırma onayı sayfasındaki kayıt: tür adı ve değer (İK neyi kaldırdığını görür)."""

    kind: str
    id: int
    kind_label: str
    value: str


def record_subject(kind: RecordKind, record_id: int) -> str:
    """Kaldırma belirtecinin (`Operation.REMOVE_PROFILE_RECORD`) bağlı olduğu hedef: `kind:rid`."""
    return f"{kind.value}:{record_id}"


def _record_target(
    session: Session, employee_id: str, kind: str, record_id: int
) -> tuple[Employee, RecordKind, ProfileRecord]:
    """İşlem görecek kayıt ve çalışanı (satır kilitli); çalışan, tür ya da bu çalışanın kaydı yoksa
    404, çalışan birleştirilmişse 409."""
    employee = session.get(Employee, employee_id, with_for_update=True)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, EMPLOYEE_NOT_FOUND)
    wanted = record_kind(kind)
    record = None if wanted is None else find_record(session, employee_id, wanted, record_id)
    if wanted is None or record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, RECORD_NOT_FOUND)
    if employee.status == MERGED_STATUS:
        raise HTTPException(status.HTTP_409_CONFLICT, RECORDS_LOCKED)
    return employee, wanted, record


def _removable_record(
    session: Session, employee_id: str, kind: str, record_id: int
) -> tuple[Employee, RecordKind, ProfileRecord]:
    """Kaldırılacak kayıt: `_record_target` ve zaten kaldırılmışsa 409."""
    employee, wanted, record = _record_target(session, employee_id, kind, record_id)
    if record.removed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, RECORD_ALREADY_REMOVED)
    return employee, wanted, record


def _record_step_view(kind: RecordKind, record: ProfileRecord) -> RecordStepView:
    if isinstance(record, EmployeeContact):
        label = CONTACT_LABELS.get(record.kind, record.kind)
    else:
        label = RECORD_KIND_LABELS[kind.value]
    return RecordStepView(kind.value, record.id, label, record_value(record))


def _record_page(
    request: Request,
    user: PanelUser,
    employee_id: str,
    kind: str,
    record_id: int,
    *,
    target: EditTarget | None,
    record: RecordStepView | None,
    status_code: int = status.HTTP_200_OK,
    **context: object,
) -> HTMLResponse:
    """`profile_record_step.html`: birinci onay, ikinci onay ya da hata."""
    return render_page(
        request,
        "profile_record_step.html",
        user=user,
        active=MENU_BY_KEY["employees"].key,
        status_code=status_code,
        employee_id=employee_id,
        kind=kind,
        record_id=record_id,
        target=target,
        record=record,
        **context,
    )


def _records_redirect(employee_id: str, notice: str) -> RedirectResponse:
    return RedirectResponse(
        f"/employees/{employee_id}?notice={notice}#records", status.HTTP_303_SEE_OTHER
    )


@router.get(
    "/employees/{employee_id}/records/{kind}/{record_id}/remove/confirm",
    response_class=HTMLResponse,
)
def record_removal_first_confirmation(
    employee_id: str,
    kind: str,
    record_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """10.5.8 — kaldırılacak kayıt ve §20.6'nın birinci onay metni; hiçbir şey değişmez."""
    try:
        employee, wanted, record = _removable_record(session, employee_id, kind, record_id)
        target, view = _edit_target(employee), _record_step_view(wanted, record)
    except HTTPException as exc:
        return _record_page(
            request,
            user,
            employee_id,
            kind,
            record_id,
            target=None,
            record=None,
            status_code=exc.status_code,
            error=exc.detail,
        )
    finally:
        session.rollback()
    return _record_page(
        request,
        user,
        employee_id,
        kind,
        record_id,
        target=target,
        record=view,
        first_confirmation=first_text(Operation.REMOVE_PROFILE_RECORD),
    )


@router.post(
    "/employees/{employee_id}/records/{kind}/{record_id}/remove/prepare",
    response_class=HTMLResponse,
)
def prepare_record_removal(
    employee_id: str,
    kind: str,
    record_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """10.5.8 — birinci onaydan sonra ikinci onay metnini ve `kind:rid`'e bağlı tek kullanımlık
    belirteci verir (§20.6.1). Kaydı değiştirmez (S16)."""
    target: EditTarget | None = None
    view: RecordStepView | None = None
    try:
        employee, wanted, record = _removable_record(session, employee_id, kind, record_id)
        target, view = _edit_target(employee), _record_step_view(wanted, record)
        issued = issue_confirmation(
            session,
            request,
            user,
            Operation.REMOVE_PROFILE_RECORD,
            record_subject(wanted, record.id),
        )
    except (HTTPException, ConfirmationRefusedError) as exc:
        session.rollback()
        refused = isinstance(exc, ConfirmationRefusedError)  # oturum çerezi yok
        return _record_page(
            request,
            user,
            employee_id,
            kind,
            record_id,
            target=target if refused else None,
            record=view if refused else None,
            status_code=status.HTTP_400_BAD_REQUEST if refused else exc.status_code,
            error=exc if refused else exc.detail,
        )
    session.commit()
    return _record_page(
        request,
        user,
        employee_id,
        kind,
        record_id,
        target=target,
        record=view,
        second_confirmation=second_text(Operation.REMOVE_PROFILE_RECORD),
        confirmation=issued.token,
    )


@router.post(
    "/employees/{employee_id}/records/{kind}/{record_id}/remove", response_class=HTMLResponse
)
def remove_record_endpoint(
    employee_id: str,
    kind: str,
    record_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    confirmation: Annotated[str | None, Form()] = None,
) -> Response:
    """10.5.8 — ikinci onayın belirteciyle kaydı kaldırır (K16, R11): kayıt silinmez, kaldırılmış
    işaretlenir ve eşleştirmeye, aramaya girmez.

    Belirteç yoksa, süresi geçmişse, kullanılmışsa ya da başka kayda, işleme veya oturuma aitse
    hiçbir şey yapılmaz (400). Belirtecin tüketilmesi, `USER_CONFIRMED` ve
    `PROFILE_RECORD_REMOVED` tek işlemdedir; commit'ten sonra `profil.md` yeniden üretilir (09.1.1)
    ve profilin kayıt bölümüne dönülür.
    """
    target: EditTarget | None = None
    view: RecordStepView | None = None
    try:
        employee, wanted, record = _removable_record(session, employee_id, kind, record_id)
        target, view = _edit_target(employee), _record_step_view(wanted, record)
        # §20.6.1: belirteç tüketilir ve `USER_CONFIRMED` yazılır, ardından işlemin kendi olayı
        # düşer. Kaydın değeri hiçbir olaya girmez (CONVENTIONS §6).
        confirm_operation(
            session,
            request,
            user,
            Operation.REMOVE_PROFILE_RECORD,
            record_subject(wanted, record.id),
            confirmation,
            event_target={"employee_id": employee.id, "kind": wanted.value, "record_id": record.id},
            employee_id=employee.id,
        )
        remove_record(session, employee, wanted, record, actor=user.username)
    except HTTPException as exc:
        session.rollback()
        return _record_page(
            request,
            user,
            employee_id,
            kind,
            record_id,
            target=None,
            record=None,
            status_code=exc.status_code,
            error=exc.detail,
        )
    except ConfirmationRefusedError:
        session.rollback()
        return _record_page(
            request,
            user,
            employee_id,
            kind,
            record_id,
            target=target,
            record=view,
            status_code=status.HTTP_400_BAD_REQUEST,
            error=CONFIRMATION_REFUSED,
            retry=True,
        )
    session.commit()
    _rewrite_profile(session, layout, employee_id)
    return _records_redirect(employee_id, "record_removed")


@router.post(
    "/employees/{employee_id}/records/{kind}/{record_id}/restore", response_class=HTMLResponse
)
def restore_record_endpoint(
    employee_id: str,
    kind: str,
    record_id: int,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
) -> Response:
    """10.5.8 — kaldırılmış kaydı tek adımda geri alır (§D61-b) ve `PROFILE_RECORD_RESTORED`'ı
    kullanıcı adıyla yazar. Çalışan, tür ya da kayıt yoksa 404; kayıt kaldırılmamışsa ya da
    çalışan birleştirilmişse 409 — hiçbir şey değişmez."""
    try:
        employee, wanted, record = _record_target(session, employee_id, kind, record_id)
        restore_record(session, employee, wanted, record, actor=user.username)
    except HTTPException as exc:
        session.rollback()
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            raise
        problem = str(exc.detail)
    except ProfileRecordStateError:
        session.rollback()
        problem = RECORD_NOT_REMOVED
    else:
        session.commit()
        _rewrite_profile(session, layout, employee_id)
        return _records_redirect(employee_id, "record_restored")
    return _profile_page(
        request,
        user,
        session,
        layout,
        employee_id,
        record_problems=[problem],
        status_code=status.HTTP_409_CONFLICT,
    )


@router.post("/employees/{employee_id}/contacts", response_class=HTMLResponse)
def add_contact_endpoint(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    kind: Annotated[str, Form(max_length=16)] = "",
    value: Annotated[str | None, Form(max_length=CONTACT_FORM_LIMIT)] = None,
) -> Response:
    """10.5.8 — iletişim bilgisini elle ekler (tek adım): yeni değer güncel olur, aynı türün
    öncekileri geçmişte kalır (05.8.2); kaynak "elle" ve ekleyen kullanıcıdır, `CONTACT_ADDED`
    yazılır. Tür ya da değer kurala uymazsa 422, çalışan birleştirilmişse 409; ikisinde de form
    girilenlerle yeniden çizilir ve hiçbir şey değişmez."""
    employee = session.get(Employee, employee_id, with_for_update=True)
    if employee is None:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, EMPLOYEE_NOT_FOUND)
    problems: dict[str, list[str]]
    try:
        add_contact(session, employee, kind, value, actor=user.username)
    except ContactFormError as exc:
        problems, status_code = exc.problems, status.HTTP_422_UNPROCESSABLE_CONTENT
    except ProfileRecordStateError:
        problems, status_code = {"kind": [RECORDS_LOCKED]}, status.HTTP_409_CONFLICT
    else:
        session.commit()
        _rewrite_profile(session, layout, employee_id)
        return _records_redirect(employee_id, "contact_added")
    session.rollback()
    return _profile_page(
        request,
        user,
        session,
        layout,
        employee_id,
        contact_form=ContactFormValues(kind=kind, value=value or ""),
        contact_problems=problems,
        status_code=status_code,
    )


# --- 10.5.9: iki çalışanı birleştirme -----------------------------------------------------------

# §20.6 "İki çalışanı birleştir": metinler birebir `app.web.confirm`'dadır; `<Birleşen Ad Soyad>`,
# `<Kalan Ad Soyad>` ve `<N>` (kalana bağlanacak belge sayısı) çalışma zamanında dolar.
MERGE_SAME = N_("Bir kayıt kendisiyle birleştirilmez; başka bir çalışan seçin.")
MERGE_CLOSED = N_(
    "Bu kayıt başka bir kayıtla zaten birleştirildi; birleştirme geri alınmaz, kalan kaydı "
    "kullanın."
)
MERGE_OTHER_CLOSED = N_(
    "Seçilen çalışan başka bir kayıtla zaten birleştirildi; kalan kaydını seçin."
)
MERGE_OTHER_NOT_FOUND = N_("Birleştirilecek çalışan bulunamadı.")
MERGE_BAD_KEEP = N_("Kalacak kayıt birleştirilen iki çalışandan biri olmalı.")
MERGE_FILES_FAILED = N_(
    "Belge dosyaları taşınamadı; birleştirme yapılmadı, hiçbir şey değişmedi. Dosyaların açık "
    "olmadığından emin olup yeniden deneyin."
)
# Özet tablosunda alanın sonucu (`merge_field_preview`).
MERGE_FIELD_NOTES = {
    "filled": N_("kalanın boş alanı bu değerle dolacak"),
    "different": N_("farklı — kalanın değeri geçerli kalır, profilde uyarı olur"),
}
MergeOther = Annotated[str, Form(max_length=MAX_QUERY_LENGTH)]
MergeKeep = Annotated[str, Form(max_length=MAX_QUERY_LENGTH)]


@dataclass(frozen=True, slots=True)
class MergeSideView:
    """Birleştirme özetinde bir kayıt: numara, ad, durum ve bağlı belge sayısı."""

    id: str
    name: str
    status_label: str
    documents: int


@dataclass(frozen=True, slots=True)
class MergeFieldRow:
    """Özet satırı: alanın iki kayıttaki değeri ve birleştirmedeki sonucu."""

    label: str
    keep: str
    merge: str
    note: str | None


@dataclass(frozen=True, slots=True)
class MergeView:
    """Birleştirme onayının özeti: kalan ve birleşen kayıt, alanlar yan yana, `<N>`."""

    keep: MergeSideView
    merge: MergeSideView
    rows: list[MergeFieldRow]

    @property
    def documents(self) -> int:
        return self.merge.documents


def merge_subject(keep_id: str, merge_id: str) -> str:
    """Birleştirme belirtecinin (`Operation.MERGE_EMPLOYEES`) bağlı olduğu hedef: `kalan:birleşen`.
    Kalan seçimi değişirse (ya da iki kayıttan biri) belirteç geçmez."""
    return f"{keep_id}:{merge_id}"


def _merge_pair(
    session: Session, employee_id: str, other_id: str, keep_id: str | None, *, lock: bool = False
) -> tuple[Employee, Employee]:
    """(kalan, birleşen). Profil ya da seçilen çalışan yoksa (ya da kalıcı silinmişse) 404; aynı
    kayıtsa ya da biri zaten birleştirilmişse 409; kalan ikisinden biri değilse 422. `lock` iki
    satırı kilitler."""
    employee = session.get(Employee, employee_id, with_for_update=lock)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, EMPLOYEE_NOT_FOUND)
    if employee.status == MERGED_STATUS:
        raise HTTPException(status.HTTP_409_CONFLICT, MERGE_CLOSED)
    other = session.get(Employee, other_id, with_for_update=lock)
    # 10.5.13: kalıcı silinen kayıt seçilemez; bulunamamış sayılır.
    if other is None or other.status == EmployeeStatus.DELETED.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MERGE_OTHER_NOT_FOUND)
    if other.id == employee.id:
        raise HTTPException(status.HTTP_409_CONFLICT, MERGE_SAME)
    if other.status == MERGED_STATUS:
        raise HTTPException(status.HTTP_409_CONFLICT, MERGE_OTHER_CLOSED)
    wanted = keep_id or employee.id
    if wanted not in (employee.id, other.id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, MERGE_BAD_KEEP)
    return (employee, other) if wanted == employee.id else (other, employee)


def _merge_side(session: Session, employee: Employee) -> MergeSideView:
    return MergeSideView(
        id=employee.id,
        name=f"{employee.given_names} {employee.surname}",
        status_label=status_label(employee.status),
        documents=merge_document_count(session, employee.id),
    )


def _merge_view(session: Session, keep: Employee, merge: Employee) -> MergeView:
    kept = profile_values(current_profile_fields(keep))
    merged = profile_values(current_profile_fields(merge))
    outcomes = merge_field_preview(keep, merge)
    return MergeView(
        keep=_merge_side(session, keep),
        merge=_merge_side(session, merge),
        rows=[
            MergeFieldRow(
                label=PROFILE_LABELS[name],
                keep=profile_text(name, kept[name]),
                merge=profile_text(name, merged[name]),
                note=MERGE_FIELD_NOTES.get(outcomes[name]),
            )
            for name in PROFILE_FIELDS
        ],
    )


def _merge_first_text(view: MergeView) -> str:
    return first_text(
        Operation.MERGE_EMPLOYEES, merged_name=view.merge.name, kept_name=view.keep.name
    )


def _merge_page(
    request: Request,
    user: PanelUser,
    template: str,
    employee_id: str,
    *,
    status_code: int = status.HTTP_200_OK,
    **context: object,
) -> HTMLResponse:
    """`employee_merge.html` (arama sayfası), `employee_merge_results.html` (HTMX arama sonucu) ya
    da `employee_merge_step.html` (onay adımları ve hata)."""
    return render_page(
        request,
        template,
        user=user,
        active=MENU_BY_KEY["employees"].key,
        status_code=status_code,
        employee_id=employee_id,
        **context,
    )


@router.get("/employees/{employee_id}/merge/employees", response_class=HTMLResponse)
def merge_search(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str, Query(max_length=MAX_QUERY_LENGTH)] = "",
) -> HTMLResponse:
    """10.5.9 — birleştirilecek ikinci çalışanı 10.4.2'nin aramasıyla bulur: etkin ve pasif
    çalışanlar; birleştirilmiş olan bulunmaz, kaydın kendisi seçilemez; boş aramada liste gelmez.
    HTMX isteği yalnız sonuç parçasını alır."""
    template = "employee_merge_results.html" if _wants_fragment(request) else "employee_merge.html"
    target: EditTarget | None = None
    listing: EmployeeListing | None = None
    try:
        employee = session.get(Employee, employee_id)
        if employee is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, EMPLOYEE_NOT_FOUND)
        if employee.status == MERGED_STATUS:
            raise HTTPException(status.HTTP_409_CONFLICT, MERGE_CLOSED)
        target = _edit_target(employee)
        if q.strip():
            listing = list_employees(session, q, statuses=SEARCHABLE_STATUSES)
    except HTTPException as exc:
        return _merge_page(
            request, user, template, employee_id, status_code=exc.status_code, error=exc.detail
        )
    finally:
        session.rollback()
    response = _merge_page(
        request, user, template, employee_id, target=target, listing=listing, query=q.strip()
    )
    response.headers["Vary"] = "HX-Request"
    return response


@router.get("/employees/{employee_id}/merge/confirm", response_class=HTMLResponse)
def merge_first_confirmation(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    other: Annotated[str, Query(max_length=MAX_QUERY_LENGTH)],
    keep: Annotated[str | None, Query(max_length=MAX_QUERY_LENGTH)] = None,
) -> HTMLResponse:
    """10.5.9 — iki kaydın özeti (alanlar yan yana, belge sayıları), kalacak kaydın seçimi
    (varsayılan: profildeki kayıt) ve §20.6'nın birinci onay metni; hiçbir şey değişmez."""
    try:
        kept, merged = _merge_pair(session, employee_id, other, keep)
        view = _merge_view(session, kept, merged)
    except HTTPException as exc:
        return _merge_page(
            request,
            user,
            "employee_merge_step.html",
            employee_id,
            status_code=exc.status_code,
            error=exc.detail,
        )
    finally:
        session.rollback()
    return _merge_page(
        request,
        user,
        "employee_merge_step.html",
        employee_id,
        other=other,
        view=view,
        first_confirmation=_merge_first_text(view),
    )


@router.post("/employees/{employee_id}/merge/prepare", response_class=HTMLResponse)
def prepare_merge(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    other: MergeOther,
    keep: MergeKeep,
) -> HTMLResponse:
    """10.5.9 — birinci onaydan sonra ikinci onay metnini (`<N>` kalana bağlanacak belge sayısı,
    "geri alınamaz") ve `kalan:birleşen` çiftine bağlı tek kullanımlık belirteci verir (§20.6.1).
    Hiçbir kaydı değiştirmez (S16)."""
    try:
        kept, merged = _merge_pair(session, employee_id, other, keep)
        view = _merge_view(session, kept, merged)
        issued = issue_confirmation(
            session, request, user, Operation.MERGE_EMPLOYEES, merge_subject(kept.id, merged.id)
        )
    except HTTPException as exc:
        session.rollback()
        return _merge_page(
            request,
            user,
            "employee_merge_step.html",
            employee_id,
            status_code=exc.status_code,
            error=exc.detail,
        )
    except ConfirmationRefusedError as exc:  # oturum çerezi yok
        session.rollback()
        return _merge_page(
            request,
            user,
            "employee_merge_step.html",
            employee_id,
            status_code=status.HTTP_400_BAD_REQUEST,
            error=exc,
        )
    session.commit()
    return _merge_page(
        request,
        user,
        "employee_merge_step.html",
        employee_id,
        other=other,
        view=view,
        second_confirmation=second_text(Operation.MERGE_EMPLOYEES, count=view.documents),
        confirmation=issued.token,
    )


@router.post("/employees/{employee_id}/merge", response_class=HTMLResponse)
def merge_employees_endpoint(
    employee_id: str,
    request: Request,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    other: MergeOther,
    keep: MergeKeep,
    confirmation: Annotated[str | None, Form()] = None,
) -> Response:
    """10.5.9 — ikinci onayın belirteciyle iki kaydı birleştirir (K8, K16, R11); geri alınamaz.

    Belirteç yoksa, süresi geçmişse, kullanılmışsa ya da başka kayıt çiftine, kalan seçimine,
    işleme veya oturuma aitse hiçbir şey yapılmaz (400). Belirtecin tüketilmesi, `USER_CONFIRMED`
    ve `EMPLOYEE_MERGED` (ardından dolan alanların ve paketlerin olayları) tek işlemdedir; dosya
    taşıması yarıda kalırsa taşınanlar geri alınır ve 409 — hiçbir şey değişmez. Commit'ten sonra
    iki kaydın `profil.md`'si yeniden üretilir (birleşeninki yönlendirme notu) ve kalan kaydın
    profiline dönülür.
    """
    try:
        kept, merged = _merge_pair(session, employee_id, other, keep, lock=True)
        # §20.6.1: belirteç tüketilir ve `USER_CONFIRMED` yazılır, ardından işlemin kendi olayı
        # (`EMPLOYEE_MERGED`) düşer.
        confirm_operation(
            session,
            request,
            user,
            Operation.MERGE_EMPLOYEES,
            merge_subject(kept.id, merged.id),
            confirmation,
            event_target={"kept": kept.id, "merged": merged.id},
            employee_id=kept.id,
        )
        result = merge_employees(session, layout, kept, merged, actor=user.username)
    except HTTPException as exc:
        session.rollback()
        return _merge_page(
            request,
            user,
            "employee_merge_step.html",
            employee_id,
            status_code=exc.status_code,
            error=exc.detail,
        )
    except ConfirmationRefusedError:
        session.rollback()
        return _merge_page(
            request,
            user,
            "employee_merge_step.html",
            employee_id,
            status_code=status.HTTP_400_BAD_REQUEST,
            error=CONFIRMATION_REFUSED,
            other=other,
            keep=keep,
            retry=True,
        )
    except (EmployeeMergeRefusedError, EmployeeMergeError) as exc:
        session.rollback()
        detail = MERGE_FILES_FAILED if isinstance(exc, EmployeeMergeError) else str(exc)
        return _merge_page(
            request,
            user,
            "employee_merge_step.html",
            employee_id,
            status_code=status.HTTP_409_CONFLICT,
            error=detail,
        )
    session.commit()
    kept_id, merged_id = result.keep.id, result.merge.id
    # 09.1.1: iki profil de değişti; birleştirmenin commit edilmiş hâlinden üretilir.
    _rewrite_profile(session, layout, merged_id)
    _rewrite_profile(session, layout, kept_id)
    return RedirectResponse(f"/employees/{kept_id}?notice=merged", status.HTTP_303_SEE_OTHER)


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
    dosyası yoksa ya da kalıcı silinmişse (10.5.12) 404 ve log yazılmaz.

    Satır sunmadan **önce** yazılır ve commit edilir: log yazılamazsa istek düşer, belge gitmez.
    """
    document = session.scalars(
        select(Document).where(
            Document.id == document_id,
            Document.employee_id == employee_id,
            Document.status != DocumentStatus.DELETED.value,
        )
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
