"""Katalog yönetim ekranı (PRD 11.1.1, 11.1.2, 11.1.3): Belge Türleri.

- `GET /document-types` bütün türleri (pasifler dahil) listeler; her satırdan düzenlenir,
  pasifleştirilir ya da yeniden etkinleştirilir. `GET /document-types/new` + `POST
  /document-types` tür oluşturur; `GET /document-types/{slug}` (form) + `POST
  /document-types/{slug}` düzenler (`slug` değişmez); `POST /document-types/{slug}/deactivate`
  ve `.../activate` pasifleştirir/etkinleştirir (`TYPE_DEACTIVATED`/`TYPE_ACTIVATED`, kullanıcı
  adıyla). **Silme yok** (K16, R11).
- **Arşiv (11.1.6, PLAN.md §C92-a).** Tür iki aşamalı onayla arşivlenir (K16 dışı, §D61-d;
  metinler bu modülde, §20.6'ya girmez): `GET /document-types/{slug}/archive/confirm` birinci
  metni, `POST .../archive/prepare` ikinci metni ve türe bağlı tek kullanımlık belirteci verir,
  `POST .../archive` belirteci tüketip türü arşivler (`USER_CONFIRMED` + `TYPE_ARCHIVED`).
  Arşivli tür listeden, analiz talimatından ve seçicilerden kalkar; `GET
  /document-types?archived=1` "Arşivlenen türler"dir ve `POST /document-types/{slug}/restore` tek
  adımda geri alır (`TYPE_RESTORED`). Korunan türler (`PROTECTED_SLUGS`) arşivlenemez (409).
- **Toplu seçim (11.1.6).** Tablo satırlarının onay kutuları `POST /document-types/bulk`'a (`action`
  ∈ activate|deactivate|archive, `slugs`, süzgeç `country`) gider. Pasifleştirme ve etkinleştirme
  tek adımdır (tür başına olay, `bulk: true`). Arşiv iki aşamalıdır: belirteçsiz istek birinci metni
  verir, `POST /document-types/bulk/prepare` sıralı slug kümesinin SHA-256'sına bağlı belirteci,
  belirteçli istek arşivler; korunan türler atlanır ve sayılır. Seçim en çok `BULK_LIMIT` türdür.
- Form katalog sözleşmesinden geçer (`app.catalog.form`, 11.1.2): Direkt türde dönüşüm listesi
  boş, `front_back` türde en az bir kabul edilen düzen seçili ve sayfa aralığı düzenlerden
  hesaplanır (ayrı sayfalar 2, tek sayfa 1), tek yüzlü türde düzen yok, analiz edilmeyen türde
  zorunlu alan yok. Reddedilen form 422 ile, girilen değerler ve alan başına mesajla yeniden
  çizilir; hiçbir şey yazılmaz.
- `acceptance_criteria` (11.1.3) formda madde madde düzenlenir: HTMX'li `POST
  /document-types/criteria/add` ve `.../remove` yalnız madde listesi parçasını yeniler
  (kaydetmez); JavaScript kapalıyken formun sonundaki boş madde alanı ve boşaltılan maddenin
  kaydedilmemesi aynı işi görür. Kayıt her analizde veritabanından baştan okunur
  (`export_catalog`): değişiklik **bir sonraki analizde** geçerli olur — süren analiz ve donmuş
  plan (K9) etkilenmez.
- Bu ekran belge içeriğine dokunmaz (K17); kaynak `known_document_types`'tır, `catalog.yaml`
  yazılmaz.
- **Katalog bütçesi (11.4.3).** Listenin üstünde analiz talimatına giren (etkin ve analiz edilen)
  tür sayısı, katalog metninin tahmini token sayısı ve etkin bütçe (`effective_token_budget`:
  `CATALOG_TOKEN_BUDGET` ayarı ya da tür sayısıyla ölçekli) gösterilir; tanımı kısaltılan tür
  varsa uyarı kutusu onları türün sayfasına bağlar. Değer her istekte analizle aynı derleyiciyle
  (`compile_catalog`, uyarı logu olmadan) hesaplanır; önbellek yoktur (400 türde ölçüm PLAN.md
  §D'de).

**Örnek belgeler (11.2.1).** Türün düzenleme sayfasında (`GET /document-types/{slug}`) o türün
örnekleri listelenir ve `POST /document-types/{slug}/examples` ile (çok dosyalı `files`) yenisi
yüklenir; örnek `GET /document-types/{slug}/examples/{ad}` ile açılır. Örnekler
`data/KnownDocuments/examples/<slug>/` altında dosya olarak durur (`app.storage.examples`):
çalışan verisinden ayrıdır — yükleme, belge, olay kaydı açılmaz, `Inbox/` ve `Employees/`'a girmez —
bu yüzden çalışan/belge aramasında görünmez ve gerçek bir yüklemeyi "tekrar" saymaz. Yükleme
hep-ya-hiçtir: bir dosya reddedilirse (tür PDF/JPEG/PNG dışı, bozuk, boş, boyut sınırını aşan)
hiçbiri yazılmaz ve hata dosya başına bildirilir (422). Aynı içerik bu türde zaten örnekse (etkin
kaydı ya da klasördeki dosyası) ya da aynı yüklemede iki kez geliyorsa yine hiçbiri yazılmaz (409,
11.9.2). Yazılan her örnek `example_files` kaydı alır (11.9.6: yöntem elle, etiket doğrulanmış,
öğesiz, not "tür sayfasından yüklendi"); olay yazılmaz (§D58 e, `app.training.cleanup`). Örnek
listesinde kaydı olan örnek eğitim sekmesinin 11.9.4 akışına bağlanır ("Başka türe taşı",
"Örneklerden çıkar": `/training/examples/{id}/move|remove/confirm`, iki aşamalı); kaydı olmayan
eski dosya "kayıtsız" notuyla durur (`python -m app.catalog register-examples` kaydeder). Örnekten
çıkarılmış kaydın adı dosya uç noktasında 404'tür. Silme ve düzenleme yolu yok.

**Tür açıklaması (11.3.1).** Düzenleme sayfasındaki formun "Örneklerden açıklama üret" düğmesi formu
`POST /document-types/{slug}/description`'a gönderir: türün örnek sayfaları (en çok
`MAX_DESCRIPTION_PAGES`) yapay zekâya verilir, yapılandırılmış açıklama (düzen, başlıklar, dil ve
alfabe, alanların yeri, MRZ, ön/arka yüz farkı) üretilir ve metni formun "Analizci için açıklama"
(`prompt_description`) alanına yazılarak form yeniden çizilir; yapılandırılmış hâli ve kullanılan
sayfalar formun üstünde gösterilir. **Kaydedilmez:** İK metni düzenleyip "Kaydet" ile türü
kaydeder (yukarıdaki düzenleme yolu, 11.1.1). Formdaki kaydedilmemiş değerler korunur; açıklama
formdaki tür bilgileriyle (ad, ülke, yüzler, zorunlu alanlar) istenir, bu yüzden form önce
doğrulanır (geçersizse 422, istek gitmez). Örnek yoksa 422, sağlayıcı kurulamıyorsa 503, sağlayıcı
yanıt vermez ya da yanıt şemaya uymazsa 502; hiçbirinde bir şey yazılmaz.

**Kabul edilen fotoğraflar (11.8.1).** Fotoğraf türünün düzenleme sayfasında "Kabul edilen
fotoğraflar" bölümü, açık kuralların hepsinden `pass` almış ve Hazir'da duran (`active`)
fotoğrafları örnek olarak işaretli gösterir (`app.catalog.describe.accepted_photos`; sayı + en yeni
`MAX_DESCRIPTION_PAGES` tanesi belgenin köken sayfasına bağlantıyla). "Örneklerden açıklama üret"
düğmesi türün yüklenmiş örneği olmasa da kabul edilen fotoğraf varken çıkar ve bu fotoğrafları örnek
sayfalarla birlikte yapay zekâya verir; üretilen metne şirketin kabul ettiği fotoğrafın tanımı
girer. İşaret ayrı bir kayıt değildir, her istekte kural setine göre yeniden çıkarılır; fotoğraf
dosyası değişmez, kopyalanmaz.

**Fotoğraf kuralları (11.6.1).** Profile Picture türünün düzenleme sayfasında
(`app.catalog.photo_rules.PHOTO_RULE_TYPES`) "Fotoğraf kuralları" bölümü kural setini gösterir:
her kural bir işaret kutusudur (yüz görünür, tek kişi, nötr ifade, sade arka plan, asgari
çözünürlük, güneş gözlüğü yok, baş örtüsü yok — sonuncusu şirket kararıdır, açılana kadar kapalı)
ve çözünürlük kuralı asgari genişlik/yüksekliği piksel olarak taşır. `POST
/document-types/{slug}/photo-rules` bütün seti tek işlemde kaydeder
(`known_document_types.photo_rules`): işaretli kural açık, işaretsiz kapalı olur; geçersiz piksel
sayısı ya da tanımsız kural 422 ile alan başına bildirilir ve hiçbir şey yazılmaz. Tür formunun
kendisi (`POST /document-types/{slug}`) kuralları değiştirmez. Kurallar yalnız saklanır; fotoğrafın
kurallara göre değerlendirilmesi 11.7'nindir.

**Aday türler (11.5).** Analizcinin önerdiği katalog dışı türler (04.6.1) `GET
/document-types/candidate-types`'ta listelenir (11.5.1): bekleyen adaylar adı, görülme sayısı, örnek
sayfaları (analiz kopyası, `/uploads/{id}/pages/{page_id}/image`) ve bekleyen Unknown öğe sayısıyla;
onaylanmış ama ilişkili Unknown öğesi hâlâ bekleyen adaylar ayrıca. Yol parçasındaki tire hiçbir
slug'la çakışmaz (slug `[a-z][a-z0-9_]*`). `GET /document-types/candidate-types/{id}` adayın
detayıdır: örnek sayfalar, ilişkili bekleyen Unknown öğeleri (ilk kaynak sayfası adayın örnek
sayfalarından biri olan, partisinin güncel planındaki çözülmemiş öğe — `app.web.routers.queue`'nun
durum tanımı) ve karar:

- **Onay (11.5.2, K16).** Tür formu sistemin incelemesinin taslağıyla (11.5.5) bütün alanlarıyla
  dolu açılır (11.5.6, `app.catalog.prefill.suggested_form`; taslak yoksa adayın adıyla); üstündeki
  bant taslağın durumunu (örnek sayfa sayısı ve tarih), doğrulamadan geçmeyip boş kalan alanları,
  katalogdaki olası aynı türü ve hazır önerilen tür kaydından seçilen slug'ın doğrulanmamış "AI
  kararı" örneklerini söyler. `POST .../examine` ("Yeniden incele") taslağı eşzamanlı yeniler
  (sağlayıcı kurulamıyorsa 503, hata verirse 502; ikisinde de taslak değişmez). İK düzeltir ve
  tamamlar. `POST .../approve/confirm` formu
  11.1.2 doğrulamasından geçirir ve §20.6'nın birinci metnini (`<Tür adı>` = formdaki ad) eklenecek
  kaydın özetiyle verir → `POST .../approve/prepare` ikinci metni ve kayda bağlı tek kullanımlık
  belirteci (10.8.1; hedef aday + kaydın SHA-256 özeti) verir → `POST .../approve` belirteci
  tüketir; `USER_CONFIRMED`, türün kataloğa eklenmesi ve `TYPE_APPROVED` tek işlemdedir. Her adım
  adayı ve kaydı yeniden denetler: karara bağlanmış aday 409, geçersiz form 422, katalogda olan slug
  409.
- **Ret (11.5.4).** `POST .../reject` adayı reddeder (`TYPE_REJECTED`, kullanıcı adıyla); K16'nın
  onaylı işlemleri arasında olmadığı için tek adımdır (pasifleştirme gibi). Reddedilen aday listeye
  kendiliğinden geri düşmez.
- **Retten geri alma (11.5.7).** `GET /document-types/candidate-types?status=rejected`
  reddedilenleri ayrı görünümde listeler; `POST .../restore` adayı tek adımda yeniden bekleyen yapar
  (`CANDIDATE_TYPE_RESTORED`, kullanıcı adıyla).
- **Toplu yeniden analiz (11.5.3).** Onaylanmış adayın ilişkili Unknown öğelerinin partileri
  yeniden analiz edilir (06.6.2, K18: her partide yeni plan sürümü, eski çıktılar "eski sürüm").
  Yeniden analiz iki aşamalı onay ister (10.3.2): `POST .../reanalyze/prepare` ikinci metni ve
  partilere + güncel planlarına bağlı belirteci verir, `POST .../reanalyze` hepsini tek işlemde
  yapar — biri düşerse hiçbiri kalmaz. Metinler yeniden analizinkilerin (D23) çoğuludur.

Bu adımlar yalnız katalog ve aday kaydını değiştirir; belge içeriği değişmez (K11, K17).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Annotated, Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.ai.provider import AnalysisProvider, ProviderConfigError, ProviderError, create_provider
from app.ai.type_description import TypeDescriptionError
from app.ai.type_proposal import TypeProposalError
from app.catalog import (
    DETAIL_SAMPLE_LIMIT,
    LIST_SAMPLE_LIMIT,
    PHOTO_RULE_TYPES,
    PROTECTED_SLUGS,
    CandidateDecidedError,
    CandidateNotFoundError,
    CandidateNotRejectedError,
    CatalogEntry,
    CatalogError,
    CompiledCatalog,
    Conversion,
    FileType,
    FrontBackLayout,
    OutputFormat,
    PhotoRulesError,
    PhotoRulesForm,
    Sides,
    TypeExistsError,
    TypeForm,
    TypeFormError,
    TypeNotFoundError,
    TypeProtectedError,
    TypeSummary,
    approve_candidate_type,
    approved_type_slug,
    archive_type,
    build_entry,
    build_photo_rules,
    check_archivable,
    compile_catalog,
    count_pending_candidate_types,
    create_type,
    effective_token_budget,
    export_catalog,
    list_candidate_types,
    list_types,
    load_candidate_type,
    load_record,
    read_photo_rules,
    record_problems,
    reject_candidate_type,
    restore_candidate_type,
    restore_type,
    sample_page_refs,
    set_photo_rules,
    set_type_active,
    summarize_candidates,
    update_type,
)
from app.catalog.describe import (
    MAX_DESCRIPTION_PAGES,
    SCRIPT_LABELS,
    AcceptedPhoto,
    GeneratedDescription,
    NoExamplePagesError,
    TypeNotAnalyzedError,
    accepted_photos,
    describe_type,
    unverified_ai_examples,
)
from app.catalog.prefill import (
    SuggestedForm,
    suggested_form,
    suggested_type,
    unverified_example_count,
)
from app.catalog.propose import (
    CANDIDATE_EXAMINATIONS,
    examine,
    load_proposal,
    read_examination,
    store_error,
    store_examination,
)
from app.config import Settings, get_settings
from app.countries import lookup, turkish_sort_key
from app.db.models import (
    CandidateDocumentType,
    CandidateProposalStatus,
    CandidateTypeStatus,
    ExampleFileRecord,
    ExampleLabel,
    KnownDocumentType,
    Plan,
    QueueItem,
    QueueKind,
    Upload,
    UploadFile,
    UploadStatus,
)
from app.db.session import get_session
from app.pipeline.orchestrate import (
    PLAN_EXECUTION_ERRORS,
    PlanExecutor,
    current_plan,
    reanalyze_upload,
)
from app.storage import DataLayout, sha256_bytes
from app.storage.examples import (
    ExampleRejectedError,
    StoredExample,
    check_example,
    example_path,
    list_examples,
    store_example,
)
from app.training.cleanup import listed_hashes, record_uploaded_example, same_type_example
from app.training.known_types import KnownTypes, load_known_types
from app.web.auth import PanelUser, require_panel_user
from app.web.confirm import (
    CONFIRMATION_REFUSED,
    ConfirmationRefusedError,
    Operation,
    confirm_operation,
    fill,
    first_text,
    issue_confirmation,
    second_text,
)
from app.web.routers.documents import _reference
from app.web.routers.queue import QueueState, _payload_refs, _state_filter
from app.web.routers.training import LABEL_TEXTS, MANUAL_CHECK_TEXT
from app.web.routers.upload_page import (
    BUSY_MESSAGE,
    FINAL_STATUSES,
    ReanalysisProvider,
    ReanalysisProviderError,
    _page_ranges,
)
from app.web.routers.uploads import get_layout, get_plan_executor
from app.web.templating import MENU_BY_KEY, render_page

router = APIRouter(tags=["catalog"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]
DbSession = Annotated[Session, Depends(get_session)]
Layout = Annotated[DataLayout, Depends(get_layout)]
AppSettings = Annotated[Settings, Depends(get_settings)]

LIST_PATH = "/document-types"
TYPE_NOT_FOUND = "Belge türü bulunamadı"
SLUG_TAKEN = "Bu slug'la bir tür zaten var; slug benzersiz olmalı ve sonradan değişmez"

FILE_TYPE_LABELS = {
    FileType.PDF: "PDF",
    FileType.JPEG: "JPEG",
    FileType.PNG: "PNG",
    FileType.DOC: "Word (doc)",
    FileType.DOCX: "Word (docx)",
    FileType.XLS: "Excel (xls)",
    FileType.XLSX: "Excel (xlsx)",
}
SIDES_LABELS = {Sides.SINGLE: "Tek yüz", Sides.FRONT_BACK: "Ön ve arka yüz"}
LAYOUT_LABELS = {
    FrontBackLayout.SEPARATE: "Ön ve arka ayrı sayfalarda",
    FrontBackLayout.COMBINED: "İki yüz tek sayfada",
}
CONVERSION_LABELS = {
    Conversion.MERGE: "Sayfaları birleştir",
    Conversion.WRAP_IMAGE: "Görüntüyü PDF'e sar",
    Conversion.EXTRACT_IMAGE: "Gömülü görüntüyü çıkar",
    Conversion.RENDER_IMAGE: "Sayfayı görüntüye çevir",
}
OUTPUT_FORMAT_LABELS = {
    OutputFormat.KEEP: "Kaynağın biçimini koru",
    OutputFormat.PDF: "PDF",
    OutputFormat.JPEG: "JPEG",
}
NOTICES = {
    "created": "Tür oluşturuldu.",
    "updated": "Tür güncellendi. Değişiklik bir sonraki analizden itibaren geçerlidir.",
    "deactivated": "Tür pasifleştirildi: yeni belgelere atanmaz.",
    "activated": "Tür yeniden etkinleştirildi.",
    "archived": "Tür arşivlendi: listeden, analiz talimatından ve tür seçicilerden kalktı; var "
    "olan belgeleri yerinde.",
    "restored": "Tür arşivden geri alındı; bir sonraki analizden itibaren yeniden geçerlidir.",
    "none_selected": "Tür seçilmedi: önce tablodan en az bir türü işaretleyin.",
}

# --- 11.1.6: arşiv ve toplu seçim -----------------------------------------------------------------

BULK_PATH = f"{LIST_PATH}/bulk"
BULK_LIMIT = 500
BULK_ACTIONS = ("activate", "deactivate", "archive")
BULK_NOTICES = {
    "bulk_deactivated": "{count} tür pasifleştirildi: yeni belgelere atanmaz.",
    "bulk_activated": "{count} tür yeniden etkinleştirildi.",
    "bulk_archived": "{count} tür arşivlendi.",
}
BULK_ARCHIVED_SKIPPED = "{count} tür arşivlendi, {skipped} korunan tür atlandı."
BULK_UNKNOWN_ACTION = "Tanınmayan toplu işlem."
BULK_TOO_MANY = f"Tek seferde en çok {BULK_LIMIT} tür seçilebilir."
BULK_NOTHING_TO_ARCHIVE = (
    "Seçilen türlerin hiçbiri arşivlenemez: hepsi korunan tür ya da zaten arşivde."
)
TYPE_PROTECTED = "Bu tür boru hattının adıyla kullandığı korunan bir türdür; arşivlenemez."
TYPE_ALREADY_ARCHIVED = "Bu tür zaten arşivde."
# §20.6 dışı (K16 dışı, PLAN.md §C92-a, §D61-d; §D58'in eğitim emsali): metinler BİREBİR §C92'den.
ARCHIVE_SECOND = (
    "Tür analiz talimatından ve listelerden kalkacak, var olan belgeler yerinde kalacaktır. Son "
    "kararınız mı?"
)
_ARCHIVE_TEXTS: dict[Operation, tuple[str, str]] = {
    Operation.TYPE_ARCHIVE: (
        "<Tür adı> belge türünü arşivlemek üzeresiniz. Emin misiniz?",
        ARCHIVE_SECOND,
    ),
    Operation.TYPE_ARCHIVE_BULK: (
        "<N> belge türünü arşivlemek üzeresiniz. Emin misiniz?",
        ARCHIVE_SECOND,
    ),
}

TYPE_PAGE_NOTICES = {"photo_rules": "Fotoğraf kuralları kaydedildi."}

# --- 11.4.3: katalog bütçesi ---------------------------------------------------------------------

BUDGET_UNAVAILABLE = (
    "Katalog metni ölçülemedi: katalogda tutarsız kayıt var (satırdaki «Tutarsız kayıt» "
    "rozetine bakın). Analiz bu kayıt düzeltilene kadar katalogu okuyamaz."
)


@dataclass(frozen=True, slots=True)
class CatalogBudgetView:
    """Belge Türleri sayfasının bütçe satırı (11.4.3): talimattaki tür sayısı, katalog metninin
    tahmini tokenı, etkin bütçe ve kaynağı; `shortened` tanımı kısaltılan türler (slug, ad)."""

    active_types: int
    estimated_tokens: int
    token_budget: int
    configured: bool
    shortened: tuple[tuple[str, str], ...]
    over_budget: bool

    @property
    def tokens_text(self) -> str:
        return _thousands(self.estimated_tokens)

    @property
    def budget_text(self) -> str:
        return _thousands(self.token_budget)


def _thousands(value: int) -> str:
    """Binlik ayraçlı sayı (Türkçe yazım: 12.345)."""
    return f"{value:,}".replace(",", ".")


# --- 11.1.5: ülke süzgeci -------------------------------------------------------------------------

COUNTRY_CODE_RE = re.compile(r"^[A-Z]{2}$")


def _normalize_country(value: str | None) -> str:
    """Süzgeç değerini geçerli bir biçime indirger: `all` (varsayılan), `general`, ISO2 büyük harf;
    başka değer (uzunluk sınırı `Query`/`Form` ile ayrı denetlenir) `all`'a döner. Küçük harf ülke
    kodu büyütülür (TUZAKLAR)."""
    if value is None:
        return "all"
    lowered = value.strip().lower()
    if lowered in ("", "all"):
        return "all"
    if lowered == "general":
        return "general"
    upper = value.strip().upper()
    return upper if COUNTRY_CODE_RE.match(upper) else "all"


def _is_general(country: str | None) -> bool:
    """`country` sütunu `None` ve boş dize ikisi de "genel" sayılır (TUZAKLAR, `form.py:149` yeni
    kayıtta boşu `None` yapar ama eski kayıt boş dize taşıyabilir)."""
    return not (country or "").strip()


@dataclass(frozen=True, slots=True)
class CountryOption:
    """Ülke süzgecinin bir seçeneği: değer (`all`/`general`/ISO2), tür sayısıyla etiket ve ülkenin
    bayrağı (11.1.7; özel seçeneklerde, bayraksız ve tanınmayan ülkede `None`)."""

    value: str
    label: str
    flag_url: str | None = None


def _code_option(code: str, count: int) -> tuple[tuple[int, Any], CountryOption]:
    """Kataloğun bir ülke kodunun seçeneği ve sıralama anahtarı (11.1.7): tanınan ISO2 kod Türkçe
    adla ve bayrağıyla, Türkçe harf sırasında; tanınmayan kod (ISO2 olmayan eski kayıt dahil)
    koduyla, tanınanlardan sonra kod sırasında."""
    country = lookup(code) if COUNTRY_CODE_RE.match(code) else None
    if country is None:
        return (1, code), CountryOption(code, f"{code} ({count})")
    option = CountryOption(code, f"{country.name_tr} ({count})", country.flag_url)
    return (0, turkish_sort_key(country.name_tr)), option


def _country_options(types: list[TypeSummary]) -> tuple[CountryOption, ...]:
    """Süzgecin seçenekleri: "Hepsi", "Genel — ülkesiz", sonra kataloğun ülkeleri Türkçe adlarıyla
    ve Türkçe harf sırasıyla, tanınmayan kodlar sonda; hepsi tür sayısıyla (11.1.5, 11.1.7). Her
    zaman süzülmemiş listeden üretilir: seçim değiştikçe seçeneklerin sayıları değişmez."""
    codes = Counter(item.country.strip().upper() for item in types if not _is_general(item.country))
    general_count = sum(1 for item in types if _is_general(item.country))
    options = [
        CountryOption("all", f"Hepsi ({len(types)})"),
        CountryOption("general", f"Genel — ülkesiz ({general_count})"),
    ]
    ranked = sorted(
        (_code_option(code, count) for code, count in codes.items()), key=lambda pair: pair[0]
    )
    options.extend(option for _, option in ranked)
    return tuple(options)


def _filter_types(types: list[TypeSummary], country: str) -> list[TypeSummary]:
    """Süzgeç kuralı (11.1.5): `general` yalnız ülkesiz türleri, bir ISO2 kod o ülkenin türlerini
    **ve** ülkeden bağımsız türleri, `all` tümünü listeler."""
    if country == "all":
        return types
    if country == "general":
        return [item for item in types if _is_general(item.country)]
    return [
        item
        for item in types
        if _is_general(item.country) or item.country.strip().upper() == country
    ]


def _country_suffix(country: str) -> str:
    """Satır bağlantılarının süzgeci taşıyan sorgu dizesi (11.1.5); `all` için boş."""
    return "" if country == "all" else f"?{urlencode({'country': country})}"


# Tür sayfası listenin süzgecini adresten (`?country=`) alır; tür formunda `country` türün kendi
# alanı olduğundan süzgeç formda gizli `list_country` alanıyla taşınır (11.1.5).
ListCountryQuery = Annotated[str | None, Query(alias="country", max_length=8)]
ListCountryField = Annotated[str | None, Form(max_length=8)]


def catalog_budget_view(session: Session, settings: Settings) -> CatalogBudgetView | None:
    """Analiz talimatının katalog metni bugünkü katalogla nasıl derlenir; katalog tutarsızsa
    (analiz de okuyamaz) `None`. Yalnız okur, uyarı loglamaz."""
    try:
        catalog = export_catalog(session)
    except CatalogError:
        return None
    configured = settings.catalog_token_budget
    compiled: CompiledCatalog = compile_catalog(
        catalog, token_budget=effective_token_budget(catalog, configured), warn=False
    )
    names = {entry.slug: entry.name for entry in catalog}
    return CatalogBudgetView(
        active_types=len(compiled.known_slugs),
        estimated_tokens=compiled.estimated_tokens,
        token_budget=compiled.token_budget,
        configured=configured is not None,
        shortened=tuple((slug, names[slug]) for slug in compiled.shortened_slugs),
        over_budget=compiled.over_budget,
    )


# --- 11.6: fotoğraf kuralları --------------------------------------------------------------------

NO_PHOTO_RULES = "Bu türün fotoğraf kuralı yok"

# --- 11.2: örnek belgeler ------------------------------------------------------------------------

EXAMPLE_NOT_FOUND = "Örnek belge bulunamadı"
NO_EXAMPLE_FILE = "Dosya seçilmedi."
EXAMPLE_DUPLICATE = "'{file}' bu türde zaten örnek (aynı içerik: {existing}); yüklenmedi."
EXAMPLE_REPEATED = "'{file}' aynı yüklemede '{first}' ile aynı içerikte; yüklenmedi."
EXAMPLE_RECORD_CLASH = (
    "Örnek dosyası yazıldı ama kaydı tutulamadı: bu adla etkin bir örnek kaydı var. "
    "python -m app.catalog register-examples ile kaydedin."
)

# --- 11.3: tür açıklaması -----------------------------------------------------------------------

DESCRIPTION_INVALID_FORM = "Açıklama üretilmedi: önce alanların altındaki uyarıları düzeltin."
DESCRIPTION_NOT_ANALYZED = (
    "Açıklama üretilmedi: analiz edilmeyen türün açıklaması analizde kullanılmaz."
)
DESCRIPTION_NO_EXAMPLES = (
    "Açıklama üretilmedi: bu türün açılabilen örneği yok. Önce örnek belge yükleyin."
)
DESCRIPTION_PROVIDER_UNAVAILABLE = (
    "Açıklama üretilmedi: yapay zekâ sağlayıcısı kurulamadı. {detail}"
)
DESCRIPTION_PROVIDER_FAILED = (
    "Açıklama üretilmedi: yapay zekâ sağlayıcısı yanıt vermedi ({detail}). Biraz sonra yeniden "
    "deneyin."
)
DESCRIPTION_REJECTED = (
    "Açıklama üretilmedi: yapay zekânın yanıtı tür açıklaması şemasına uymadı. Yeniden deneyin."
)

# --- 11.5: aday türler ---------------------------------------------------------------------------

CANDIDATES_PATH = f"{LIST_PATH}/candidate-types"
CANDIDATE_NOT_FOUND = "Aday tür bulunamadı."
CANDIDATE_STATUS_LABELS = {
    CandidateTypeStatus.PENDING.value: "Onay bekliyor",
    CandidateTypeStatus.APPROVED.value: "Onaylandı",
    CandidateTypeStatus.REJECTED.value: "Reddedildi",
}
DECIDED_NOTES = {
    CandidateTypeStatus.APPROVED.value: "Bu aday tür onaylanmış; yeniden karara bağlanamaz.",
    CandidateTypeStatus.REJECTED.value: "Bu aday tür reddedilmiş; yeniden karara bağlanamaz.",
}
DECIDED_NOTE = "Bu aday tür karara bağlanmış; yeniden karara bağlanamaz."
CANDIDATE_NOTICES = {
    "approved": "Aday tür standart türler arasına eklendi; tür bir sonraki analizden itibaren "
    "geçerlidir. İlişkili Unknown öğeleri aşağıdan toplu yeniden analiz edilebilir.",
    "rejected": "Aday tür reddedildi; bir daha listeye düşmez.",
    "restored": "Aday tür retten geri alındı; yeniden onay bekliyor.",
}
NOT_REJECTED_NOTE = "Bu aday tür reddedilmiş değil; geri alınacak bir ret yok."
CANDIDATE_VIEWS = ("pending", "rejected")
# 11.5.6: taslakla dolu onay formunun bandı ve "Yeniden incele".
PREFILL_FILLED = (
    "Alanlar sistemin incelemesiyle dolduruldu ({pages} örnek sayfa, {date}). Kaydetmeden önce "
    "kontrol edin."
)
PREFILL_UNFILLED = "Şu alanlar önerilemedi, elle doldurun: {fields}"
PREFILL_STATUS = {
    None: "Sistem bu adayı henüz incelemedi; örnek sayfalar işçinin boş zamanında incelenir. "
    "Form adayın adıyla açıldı.",
    CandidateProposalStatus.FAILED.value: "Sistemin incelemesi taslak üretmedi: {reason}. "
    "Form adayın adıyla açıldı.",
    CandidateProposalStatus.NO_SAMPLES.value: "Sistemin incelemesi yapılamadı: {reason}. "
    "Form adayın adıyla açıldı.",
}
EXAMINED_NOTICE = "Aday yeniden incelendi."
EXAMINE_PROVIDER_UNAVAILABLE = "Yeniden incelenmedi: yapay zekâ sağlayıcısı kurulamadı. {detail}"
EXAMINE_PROVIDER_FAILED = (
    "Yeniden incelenmedi: yapay zekâ sağlayıcısı yanıt vermedi ({detail}). Biraz sonra yeniden "
    "deneyin."
)
EXAMINE_REJECTED = (
    "Yeniden incelenmedi: yapay zekânın yanıtı tür taslağı şemasına uymadı. Yeniden deneyin."
)
NOT_APPROVED_NOTE = "Toplu yeniden analiz yalnız onaylanmış aday türde yapılır."
NO_RELATED_NOTE = (
    "Bu aday türle ilişkili bekleyen Unknown öğesi yok; yeniden analiz edilecek parti bulunmuyor."
)
# §20.6 dışı (PLAN.md §D30): yeniden analizin onay metinlerinin (D23) çoğulu.
BATCH_REANALYZE_FIRST = "Bu {count} partiyi yeniden analiz etmek üzeresiniz. Emin misiniz?"
BATCH_REANALYZE_SECOND = (
    "Bu işlem her partiye yeni bir plan sürümü açacak; önceki sürümlerin çıktıları "
    '"eski sürüm" olarak işaretlenecektir. Son kararınız mı?'
)


def type_form(
    # Alan adı `slug`; yol parametresiyle (`/document-types/{slug}`) karışmasın diye takma adla.
    type_slug: Annotated[str, Form(alias="slug")] = "",
    name: Annotated[str, Form()] = "",
    file_label: Annotated[str, Form()] = "",
    country: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    expected_file_types: Annotated[list[str] | None, Form()] = None,
    pages_min: Annotated[str, Form()] = "",
    pages_max: Annotated[str, Form()] = "",
    sides: Annotated[str, Form()] = "",
    front_back_layouts: Annotated[list[str] | None, Form()] = None,
    direct: Annotated[str | None, Form()] = None,
    analyze: Annotated[str | None, Form()] = None,
    required_fields: Annotated[str, Form()] = "",
    allowed_conversions: Annotated[list[str] | None, Form()] = None,
    output_format: Annotated[str, Form()] = "",
    acceptance_criteria: Annotated[list[str] | None, Form()] = None,
    prompt_description: Annotated[str, Form()] = "",
) -> TypeForm:
    """Formun kayıt alanları. Başka form alanı okunmaz: `active` ve `photo_rules` bu formdan
    değişmez. İşaret kutusu (`direct`, `analyze`) gönderilmişse işaretlidir."""
    return TypeForm(
        slug=type_slug,
        name=name,
        file_label=file_label,
        country=country,
        description=description,
        expected_file_types=tuple(expected_file_types or ()),
        pages_min=pages_min,
        pages_max=pages_max,
        sides=sides,
        front_back_layouts=tuple(front_back_layouts or ()),
        direct=direct is not None,
        analyze=analyze is not None,
        required_fields=required_fields,
        allowed_conversions=tuple(allowed_conversions or ()),
        output_format=output_format,
        acceptance_criteria=tuple(acceptance_criteria or ()),
        prompt_description=prompt_description,
    )


SubmittedForm = Annotated[TypeForm, Depends(type_form)]


def _form_page(
    request: Request,
    user: PanelUser,
    form: TypeForm,
    *,
    slug: str | None,
    problems: dict[str, list[str]] | None = None,
    current_problems: tuple[str, ...] = (),
    status_code: int = status.HTTP_200_OK,
    examples: dict[str, Any] | None = None,
    photo: dict[str, Any] | None = None,
    generated: GeneratedDescription | None = None,
    description_error: str | None = None,
    notice_text: str | None = None,
    list_country: str | None = None,
) -> HTMLResponse:
    """Tür formunu çizer. `slug` düzenlenen türdür (yeni türde `None`); `examples` düzenleme
    sayfasının örnek belge bölümünün bağlamıdır (`_examples_context`), `photo` fotoğraf kuralları
    bölümünün (`_photo_context`, yalnız fotoğraf türlerinde dolu); `generated` örneklerden üretilen
    (kaydedilmemiş) tür açıklaması, `description_error` üretilemediyse nedeni; `list_country`
    listenin ülke süzgeci — geri bağlantıları ve kaydetme yönlendirmesi ona döner (11.1.5)."""
    selected_country = _normalize_country(list_country)
    return render_page(
        request,
        "catalog_form.html",
        user=user,
        active="document_types",
        status_code=status_code,
        slug=slug,
        current_problems=current_problems,
        **_fields_context(form, problems),
        **(examples or {}),
        **(photo or {}),
        generated=generated,
        description_error=description_error,
        notice_text=notice_text,
        script_labels=SCRIPT_LABELS,
        max_description_pages=MAX_DESCRIPTION_PAGES,
        is_new=slug is None,
        list_country=selected_country,
        list_query=_country_suffix(selected_country),
    )


def _size_label(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{max(1, round(size / 1024))} KB"


def _example_records(session: Session, slug: str) -> dict[str, ExampleFileRecord]:
    """Türün etkin örnek kayıtları (ad → kayıt; 11.9, 11.9.6). Okuma SQLite'ta yazma kilidini
    tutar: işlem hemen bırakılır (çağıranın bekleyen yazması olmamalı)."""
    try:
        records = session.scalars(
            select(ExampleFileRecord).where(
                ExampleFileRecord.type_slug == slug, ExampleFileRecord.removed_at.is_(None)
            )
        )
        return {record.name: record for record in records}
    finally:
        session.rollback()


def _move_targets(session: Session, slug: str) -> list[tuple[str, str]]:
    """ "Başka türe taşı"nın seçenekleri: bilinen türler (katalog ∪ önerilen, 11.9) bu tür hariç;
    kayıtlı katalog okunamazsa boş (form yine gönderilir, hedef onay adımında denetlenir)."""
    try:
        known = _known_types(session)
    finally:
        session.rollback()
    if known is None:
        return []
    return [(item.slug, item.name) for item in known if item.slug != slug]


def _examples_context(
    session: Session,
    layout: DataLayout,
    slug: str,
    *,
    stored: list[StoredExample] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    """Düzenleme sayfasındaki örnek belge bölümünün bağlamı: türün örnekleri (dosya sistemi), bu
    yüklemenin sonucu ve hataları. Kaydı olan örnek (`example_files`) etiketini taşır; "AI kararı"
    etiketli örnek elle kontrol ikonuyla görünür ve eğitim sekmesindeki tür sayfasına bağlanır
    (doğrula orada, 11.9.4). Kaydı olan her örnek kaydın kimliğiyle (`record_id`) "Başka türe taşı"
    ve "Örneklerden çıkar" akışına bağlanır (11.9.6); kaydı olmayan dosyada `record_id` boştur."""
    records = _example_records(session, slug)
    examples = []
    for item in list_examples(layout, slug):
        record = records.get(item.name)
        label = record.label if record is not None else None
        examples.append(
            {
                "name": item.name,
                "size_label": _size_label(item.size),
                "label_text": LABEL_TEXTS.get(label or ""),
                "manual_check": label == ExampleLabel.AI_DECISION,
                "record_id": record.id if record is not None else None,
            }
        )
    registered = any(example["record_id"] is not None for example in examples)
    return {
        "examples": examples,
        "example_stored": stored or [],
        "example_errors": errors or [],
        "manual_check_text": MANUAL_CHECK_TEXT,
        "training_type_url": f"/training/known/{quote(slug)}",
        "move_targets": _move_targets(session, slug) if registered else [],
    }


def _accepted_photos(
    session: Session, slug: str, stored: dict[str, Any] | None
) -> tuple[AcceptedPhoto, ...]:
    """Türün örnek işaretlenen kabul edilmiş fotoğrafları (11.8.1). Okuma SQLite'ta yazma kilidini
    tutar: işlem hemen bırakılır (çağıranın bekleyen yazması olmamalı)."""
    try:
        return accepted_photos(session, slug, stored)
    finally:
        session.rollback()


def _photo_context(
    session: Session,
    slug: str,
    stored: dict[str, Any] | None,
    *,
    form: PhotoRulesForm | None = None,
    problems: dict[str, list[str]] | None = None,
    accepted: tuple[AcceptedPhoto, ...] | None = None,
) -> dict[str, Any]:
    """Düzenleme sayfasının fotoğraf kuralları ve kabul edilen fotoğraflar (11.8.1) bölümlerinin
    bağlamı; türün kuralı yoksa boş. `stored` kayıtlı `photo_rules`, `form` reddedilen formun
    girilen değerleridir (kayıtlıyı gölgeler); `accepted` önceden okunmuş kabul edilen fotoğraflar
    (verilmezse okunur)."""
    if slug not in PHOTO_RULE_TYPES:
        return {}
    settings = read_photo_rules(stored)
    shown = form or PhotoRulesForm.from_settings(settings)
    if accepted is None:
        accepted = _accepted_photos(session, slug, stored)
    return {
        "accepted_photos": {
            "count": len(accepted),
            "listed": [
                {"document_id": photo.document_id, "date": f"{photo.created_at:%Y-%m-%d}"}
                for photo in accepted[:MAX_DESCRIPTION_PAGES]
            ],
            "more": max(0, len(accepted) - MAX_DESCRIPTION_PAGES),
        },
        "photo_rules": {
            "rules": [
                {
                    "id": setting.id,
                    "label": setting.label,
                    "description": setting.spec.description,
                    "company_decision": setting.spec.company_decision,
                    "enabled": setting.id in shown.enabled,
                }
                for setting in settings
            ],
            "min_width_px": shown.min_width_px,
            "min_height_px": shown.min_height_px,
            "problems": problems or {},
        },
    }


def _fields_context(form: TypeForm, problems: dict[str, list[str]] | None) -> dict[str, Any]:
    """`catalog_type_fields.html`'in bağlamı (`is_new` hariç); madde listesinin sonuna
    JavaScript'siz ekleme için boş bir alan konur."""
    return {
        "form": form,
        "problems": problems or {},
        "criteria": [*form.acceptance_criteria, ""],
        "file_types": FILE_TYPE_LABELS,
        "sides_options": SIDES_LABELS,
        "layouts": LAYOUT_LABELS,
        "conversions": CONVERSION_LABELS,
        "output_formats": OUTPUT_FORMAT_LABELS,
    }


def _list_url(*, country: str | None = None, archived: bool = False, **params: str | int) -> str:
    """Belge Türleri listesinin adresi: arşiv görünümü (`archived=1`), bildirim parametreleri ve
    süzgeç (11.1.5; `all` yazılmaz)."""
    query: dict[str, str | int] = {"archived": 1} if archived else {}
    query.update(params)
    normalized = _normalize_country(country)
    if normalized != "all":
        query["country"] = normalized
    return f"{LIST_PATH}?{urlencode(query)}" if query else LIST_PATH


def _redirect(
    notice: str, slug: str | None = None, *, country: str | None = None, **counts: int
) -> RedirectResponse:
    params: dict[str, str | int] = {"notice": notice}
    if slug is not None:
        params["slug"] = slug
    params.update(counts)
    return RedirectResponse(_list_url(country=country, **params), status.HTTP_303_SEE_OTHER)


def _notice_text(
    notice: str | None,
    slug: str | None,
    named: dict[str, str],
    count: int | None,
    skipped: int | None,
) -> str | None:
    """Liste bildiriminin metni; tanınmayan bildirim yok sayılır. Tekil bildirim türün adını taşır,
    toplu bildirim sayıları (11.1.6)."""
    key = notice or ""
    if key in BULK_NOTICES:
        if count is None:
            return None
        if key == "bulk_archived" and skipped:
            return BULK_ARCHIVED_SKIPPED.format(count=count, skipped=skipped)
        return BULK_NOTICES[key].format(count=count)
    text = NOTICES.get(key)
    if text and slug in named:
        text = f"{named[slug]}: {text}"
    return text


@router.get(LIST_PATH, response_class=HTMLResponse)
def catalog_page(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
    notice: Annotated[str | None, Query(max_length=32)] = None,
    slug: Annotated[str | None, Query(max_length=64)] = None,
    country: Annotated[str | None, Query(max_length=8)] = None,
    archived: Annotated[str | None, Query(max_length=1)] = None,
    count: Annotated[int | None, Query(ge=0, le=BULK_LIMIT)] = None,
    skipped: Annotated[int | None, Query(ge=0, le=BULK_LIMIT)] = None,
) -> HTMLResponse:
    """Belge Türleri (11.1.1): arşivsiz türler; `archived=1` "Arşivlenen türler" görünümüdür
    (11.1.6). Ülke süzgeci (11.1.5) iki görünümde de görünümün kendi türlerinden üretilir."""
    every_type = list_types(session, include_archived=True)
    show_archived = archived == "1"
    types = [item for item in every_type if (item.archived_at is not None) == show_archived]
    named = {item.slug: item.name for item in every_type}
    selected_country = _normalize_country(country)
    return render_page(
        request,
        "catalog.html",
        user=user,
        active="document_types",
        entry=MENU_BY_KEY["document_types"],
        types=_filter_types(types, selected_country),
        total_types=len(types),
        show_archived=show_archived,
        archived_total=sum(1 for item in every_type if item.archived_at is not None),
        archived_url=_list_url(country=selected_country, archived=True),
        list_url=_list_url(country=selected_country),
        bulk_limit=BULK_LIMIT,
        country_options=_country_options(types),
        selected_country=selected_country,
        country_query=_country_suffix(selected_country),
        notice_text=_notice_text(notice, slug, named, count, skipped),
        sides_labels=SIDES_LABELS,
        pending_candidates=count_pending_candidate_types(session),
        budget=catalog_budget_view(session, settings),
        budget_unavailable=BUDGET_UNAVAILABLE,
    )


@router.get(f"{LIST_PATH}/new", response_class=HTMLResponse)
def new_type_page(
    request: Request, user: CurrentUser, list_country: ListCountryQuery = None
) -> HTMLResponse:
    return _form_page(request, user, TypeForm(), slug=None, list_country=list_country)


# `/document-types/{slug}`'dan önce kayıtlı olmalı: yol tek parçadır.
@router.get(CANDIDATES_PATH, response_class=HTMLResponse)
def candidate_types_page(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    notice: Annotated[str | None, Query(max_length=32)] = None,
    view: Annotated[str | None, Query(alias="status", max_length=16)] = None,
) -> HTMLResponse:
    """11.5.1 — bekleyen aday türler adı, görülme sayısı ve örnek sayfalarıyla; onaylanmış ama
    ilişkili Unknown öğesi bekleyen adaylar ayrıca (toplu yeniden analiz için, 11.5.3).
    `status=rejected` reddedilenleri "Geri al" düğmesiyle listeler (11.5.7)."""
    shown = view if view in CANDIDATE_VIEWS else "pending"
    rejected = list_candidate_types(
        session,
        CandidateTypeStatus.REJECTED,
        sample_limit=LIST_SAMPLE_LIMIT if shown == "rejected" else 0,
    )
    pending = list_candidate_types(
        session, sample_limit=LIST_SAMPLE_LIMIT if shown == "pending" else 0
    )
    approved = list_candidate_types(session, CandidateTypeStatus.APPROVED, sample_limit=0)
    related = _related_by_candidate(session, [item.id for item in (*pending, *approved)])
    response = render_page(
        request,
        "catalog_candidates.html",
        user=user,
        active="document_types",
        view=shown,
        pending=pending,
        rejected=rejected,
        approved=[item for item in approved if related[item.id]],
        related_counts={key: len(items) for key, items in related.items()},
        notice_text=CANDIDATE_NOTICES.get(notice or ""),
    )
    # Okuma işlemi de SQLite'ta yazma kilidini tutar (`app.db.session`).
    session.rollback()
    return response


@router.post(LIST_PATH, response_class=HTMLResponse)
def create_type_endpoint(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    form: SubmittedForm,
    list_country: ListCountryField = None,
) -> Response:
    try:
        entry = build_entry(form)
    except TypeFormError as exc:
        return _form_page(
            request,
            user,
            form,
            slug=None,
            problems=exc.problems,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            list_country=list_country,
        )
    try:
        create_type(session, entry)
        session.commit()
    except TypeExistsError:
        session.rollback()
        return _form_page(
            request,
            user,
            form,
            slug=None,
            problems={"slug": [SLUG_TAKEN]},
            status_code=status.HTTP_409_CONFLICT,
            list_country=list_country,
        )
    return _redirect("created", entry.slug, country=list_country)


# --- 11.1.6: toplu seçim ------------------------------------------------------------------------
# `POST /document-types/{slug}`'dan önce kayıtlı olmalı; `bulk` slug olamaz (`RESERVED_SLUGS`).

CountryField = Annotated[str | None, Form(max_length=8)]
BulkSlugs = Annotated[list[str] | None, Form()]


@dataclass(frozen=True, slots=True)
class _BulkArchive:
    """Toplu arşivin planı: seçilen slug'lar (sıralı, tekil), arşivlenecek ve atlanacak korunan
    türler."""

    selected: tuple[str, ...]
    archivable: tuple[KnownDocumentType, ...]
    protected: tuple[KnownDocumentType, ...]


def _bulk_selection(
    session: Session, slugs: list[str] | None
) -> tuple[tuple[str, ...], dict[str, KnownDocumentType]]:
    """Seçimin denetimi: en çok `BULK_LIMIT` (422), her slug katalogda (404). Sıralı ve tekil."""
    if len(slugs or ()) > BULK_LIMIT:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, BULK_TOO_MANY)
    selected = tuple(sorted({slug.strip() for slug in slugs or () if slug.strip()}))
    rows = {
        row.slug: row
        for row in session.scalars(
            select(KnownDocumentType).where(KnownDocumentType.slug.in_(selected))
        )
    }
    if len(rows) != len(selected):
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND)
    return selected, rows


def _bulk_archive(session: Session, slugs: list[str] | None) -> _BulkArchive:
    """Toplu arşivin ortak denetimi (her adımda yeniden): seçim, en az bir arşivlenebilir tür
    (409). Zaten arşivli tür sessizce dışarıda kalır, korunan tür atlanır ve sayılır."""
    selected, rows = _bulk_selection(session, slugs)
    chosen = [rows[slug] for slug in selected]
    protected = tuple(row for row in chosen if row.slug in PROTECTED_SLUGS)
    archivable = tuple(
        row for row in chosen if row.slug not in PROTECTED_SLUGS and row.archived_at is None
    )
    if not archivable:
        raise HTTPException(status.HTTP_409_CONFLICT, BULK_NOTHING_TO_ARCHIVE)
    return _BulkArchive(selected, archivable, protected)


def bulk_archive_subject(selected: tuple[str, ...]) -> str:
    """Toplu arşiv belirtecinin (`Operation.TYPE_ARCHIVE_BULK`) hedefi: sıralı slug kümesinin
    SHA-256 özeti. Hazırlıktan sonra seçim değişirse belirteç geçmez."""
    return f"document-types:bulk:{_digest(chr(10).join(selected))}"


def archive_subject(slug: str) -> str:
    """Tekil arşiv belirtecinin (`Operation.TYPE_ARCHIVE`) hedefi."""
    return f"document-types:{slug}"


def _archive_text(operation: Operation, second: bool, **values: Any) -> str:
    first_text_, second_text_ = _ARCHIVE_TEXTS[operation]
    return fill(second_text_ if second else first_text_, **values)


def _archive_page(
    request: Request,
    user: PanelUser,
    status_code: int,
    *,
    country: str | None,
    slug: str | None = None,
    type_name: str | None = None,
    plan: _BulkArchive | None = None,
    confirm_text: str | None = None,
    confirmation: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    """Arşiv adımının sayfası (`catalog_archive_step.html`): tekil (`slug`) ya da toplu (`plan`)
    birinci onay (belirteçsiz), ikinci onay (belirteçle) ya da ret."""
    selected_country = _normalize_country(country)
    return render_page(
        request,
        "catalog_archive_step.html",
        user=user,
        active="document_types",
        status_code=status_code,
        entry=MENU_BY_KEY["document_types"],
        bulk=slug is None,
        slug=slug,
        type_name=type_name,
        selected=plan.selected if plan else (),
        archivable=[row.name for row in plan.archivable] if plan else [],
        protected=[row.name for row in plan.protected] if plan else [],
        selected_country=selected_country,
        back_url=_list_url(country=selected_country),
        confirm_text=confirm_text,
        confirmation=confirmation,
        error=error,
    )


def _archive_refused(
    request: Request,
    user: PanelUser,
    session: Session,
    exc: Exception,
    country: str | None,
    *,
    detail: bool = False,
) -> HTMLResponse:
    """Arşiv ya da toplu adımın reddi → hata sayfası; hiçbir şey yazılmadı. Belirteç reddi istemciye
    tek genel metinle gider; hazırlıkta (`detail`) üretim hatasının nedeni yazılır."""
    session.rollback()
    if isinstance(exc, HTTPException):
        code, message = exc.status_code, str(exc.detail)
    else:  # ConfirmationRefusedError
        code = status.HTTP_400_BAD_REQUEST
        message = str(exc) if detail else CONFIRMATION_REFUSED
    return _archive_page(request, user, code, country=country, error=message)


@router.post(BULK_PATH, response_class=HTMLResponse)
def bulk_types(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    action: Annotated[str, Form(max_length=16)] = "",
    slugs: BulkSlugs = None,
    country: CountryField = None,
    confirmation: Annotated[str | None, Form()] = None,
) -> Response:
    """11.1.6 — seçilen türleri topluca pasifleştirir, etkinleştirir ya da arşivler.

    Pasifleştirme ve etkinleştirme tek adımdır: durumu değişen her tür için olay (`bulk: true`).
    Arşiv iki aşamalıdır: belirteçsiz istek birinci metni verir (hiçbir şey değişmez),
    `bulk/prepare` belirteci verir, belirteçli istek belirteci tüketir ve arşivler; korunan türler
    atlanır. Belirtecin tüketilmesi, `USER_CONFIRMED` ve bütün arşiv olayları tek işlemdedir."""
    if action not in BULK_ACTIONS:
        return _archive_refused(
            request,
            user,
            session,
            HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, BULK_UNKNOWN_ACTION),
            country,
        )
    if not any(slug.strip() for slug in slugs or ()):
        return _redirect("none_selected", country=country)
    if action == "archive" and confirmation is None:
        try:
            plan = _bulk_archive(session, slugs)
        except HTTPException as exc:
            return _archive_refused(request, user, session, exc, country)
        response = _archive_page(
            request,
            user,
            status.HTTP_200_OK,
            country=country,
            plan=plan,
            confirm_text=_archive_text(
                Operation.TYPE_ARCHIVE_BULK, False, count=len(plan.archivable)
            ),
        )
        session.rollback()
        return response
    try:
        if action == "archive":
            plan = _bulk_archive(session, slugs)
            confirm_operation(
                session,
                request,
                user,
                Operation.TYPE_ARCHIVE_BULK,
                bulk_archive_subject(plan.selected),
                confirmation,
                event_target={
                    "slugs": [row.slug for row in plan.archivable],
                    "skipped": [row.slug for row in plan.protected],
                },
            )
            archived = sum(
                archive_type(session, row.slug, actor=user.username, bulk=True)
                for row in plan.archivable
            )
            session.commit()
            return _redirect(
                "bulk_archived", country=country, count=archived, skipped=len(plan.protected)
            )
        selected, _ = _bulk_selection(session, slugs)
        active = action == "activate"
        changed = sum(
            set_type_active(session, slug, active, actor=user.username, bulk=True)
            for slug in selected
        )
    except (HTTPException, ConfirmationRefusedError) as exc:
        return _archive_refused(request, user, session, exc, country)
    session.commit()
    return _redirect(f"bulk_{action}d", country=country, count=changed)


@router.post(f"{BULK_PATH}/prepare", response_class=HTMLResponse)
def prepare_bulk_archive(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    slugs: BulkSlugs = None,
    country: CountryField = None,
) -> HTMLResponse:
    """11.1.6 — toplu arşivin birinci onayından sonra ikinci metni ve sıralı slug kümesine bağlı tek
    kullanımlık belirteci verir (10.8.1)."""
    try:
        plan = _bulk_archive(session, slugs)
        issued = issue_confirmation(
            session,
            request,
            user,
            Operation.TYPE_ARCHIVE_BULK,
            bulk_archive_subject(plan.selected),
        )
    except (HTTPException, ConfirmationRefusedError) as exc:
        return _archive_refused(request, user, session, exc, country, detail=True)
    response = _archive_page(
        request,
        user,
        status.HTTP_200_OK,
        country=country,
        plan=plan,
        confirm_text=_archive_text(Operation.TYPE_ARCHIVE_BULK, True),
        confirmation=issued.token,
    )
    session.commit()
    return response


@router.get(f"{LIST_PATH}/{{slug}}", response_class=HTMLResponse)
def type_page(
    slug: str,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    notice: Annotated[str | None, Query(max_length=32)] = None,
    list_country: ListCountryQuery = None,
) -> HTMLResponse:
    try:
        record = load_record(session, slug)
    except TypeNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    # Kayıtlı tür §8.6'ya uymuyorsa (elle değiştirilmiş satır) form yine açılır; kaydetmek
    # onu düzeltir.
    return _form_page(
        request,
        user,
        TypeForm.from_record(record),
        slug=slug,
        current_problems=record_problems(record),
        examples=_examples_context(session, layout, slug),
        photo=_photo_context(session, slug, record["photo_rules"]),
        notice_text=TYPE_PAGE_NOTICES.get(notice or ""),
        list_country=list_country,
    )


@router.post(f"{LIST_PATH}/{{slug}}", response_class=HTMLResponse)
def update_type_endpoint(
    slug: str,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    form: SubmittedForm,
    list_country: ListCountryField = None,
) -> Response:
    # Slug adresten gelir, formdan değil: değişmez (belgeler ve çıktı adları ona bağlı).
    form = replace(form, slug=slug)
    try:
        record = load_record(session, slug)
    except TypeNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    try:
        entry = build_entry(form)
    except TypeFormError as exc:
        return _form_page(
            request,
            user,
            form,
            slug=slug,
            problems=exc.problems,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            examples=_examples_context(session, layout, slug),
            photo=_photo_context(session, slug, record["photo_rules"]),
            list_country=list_country,
        )
    try:
        update_type(session, entry)
        session.commit()
    except TypeNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    return _redirect("updated", slug, country=list_country)


def _set_active(
    session: Session, user: PanelUser, slug: str, active: bool, *, country: str | None
) -> RedirectResponse:
    """Tekil pasifleştirme/etkinleştirme: durum değiştiyse `TYPE_DEACTIVATED`/`TYPE_ACTIVATED`
    kullanıcı adıyla yazılır (11.1.6)."""
    try:
        set_type_active(session, slug, active, actor=user.username)
        session.commit()
    except TypeNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    return _redirect("activated" if active else "deactivated", slug, country=country)


@router.post(f"{LIST_PATH}/{{slug}}/deactivate")
def deactivate_type(
    slug: str, user: CurrentUser, session: DbSession, country: CountryField = None
) -> RedirectResponse:
    return _set_active(session, user, slug, False, country=country)


@router.post(f"{LIST_PATH}/{{slug}}/activate")
def activate_type(
    slug: str, user: CurrentUser, session: DbSession, country: CountryField = None
) -> RedirectResponse:
    return _set_active(session, user, slug, True, country=country)


# --- 11.1.6: tekil arşiv ve geri alma ------------------------------------------------------------


def _archivable(session: Session, slug: str) -> KnownDocumentType:
    """Tekil arşivin ortak denetimi (her adımda yeniden): tür (404), korunan değil (409), arşivde
    değil (409). Yazmaz."""
    try:
        row = check_archivable(session, slug)
    except TypeNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    except TypeProtectedError:
        raise HTTPException(status.HTTP_409_CONFLICT, TYPE_PROTECTED) from None
    if row.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, TYPE_ALREADY_ARCHIVED)
    return row


@router.get(f"{LIST_PATH}/{{slug}}/archive/confirm", response_class=HTMLResponse)
def archive_first_confirmation(
    slug: str,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    list_country: ListCountryQuery = None,
) -> HTMLResponse:
    """11.1.6 "Arşivle" — türü denetler ve §C92'nin birinci onay metnini verir; hiçbir şey
    değişmez."""
    try:
        row = _archivable(session, slug)
    except HTTPException as exc:
        return _archive_refused(request, user, session, exc, list_country)
    response = _archive_page(
        request,
        user,
        status.HTTP_200_OK,
        country=list_country,
        slug=slug,
        type_name=row.name,
        confirm_text=_archive_text(Operation.TYPE_ARCHIVE, False, type_name=row.name),
    )
    session.rollback()
    return response


@router.post(f"{LIST_PATH}/{{slug}}/archive/prepare", response_class=HTMLResponse)
def prepare_archive(
    slug: str,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    country: CountryField = None,
) -> HTMLResponse:
    """11.1.6 — birinci onaydan sonra ikinci onay metnini ve türe bağlı tek kullanımlık belirteci
    verir (10.8.1)."""
    try:
        row = _archivable(session, slug)
        issued = issue_confirmation(
            session, request, user, Operation.TYPE_ARCHIVE, archive_subject(slug)
        )
    except (HTTPException, ConfirmationRefusedError) as exc:
        return _archive_refused(request, user, session, exc, country, detail=True)
    response = _archive_page(
        request,
        user,
        status.HTTP_200_OK,
        country=country,
        slug=slug,
        type_name=row.name,
        confirm_text=_archive_text(Operation.TYPE_ARCHIVE, True),
        confirmation=issued.token,
    )
    session.commit()
    return response


@router.post(f"{LIST_PATH}/{{slug}}/archive", response_class=HTMLResponse)
def archive_selected_type(
    slug: str,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    country: CountryField = None,
    confirmation: Annotated[str | None, Form()] = None,
) -> Response:
    """11.1.6 — ikinci onayın belirteciyle türü arşivler. Belirteçsiz ya da geçersiz belirteçte
    hiçbir şey yapılmaz (400). Belirtecin tüketilmesi, `USER_CONFIRMED` ve `TYPE_ARCHIVED` tek
    işlemdedir. Tür kaydı ve belgeleri yerinde kalır (R11)."""
    try:
        _archivable(session, slug)
        confirm_operation(
            session,
            request,
            user,
            Operation.TYPE_ARCHIVE,
            archive_subject(slug),
            confirmation,
            event_target={"slug": slug},
        )
        archive_type(session, slug, actor=user.username)
    except (HTTPException, ConfirmationRefusedError) as exc:
        return _archive_refused(request, user, session, exc, country)
    session.commit()
    return _redirect("archived", slug, country=country)


@router.post(f"{LIST_PATH}/{{slug}}/restore")
def restore_archived_type(
    slug: str, user: CurrentUser, session: DbSession, country: CountryField = None
) -> RedirectResponse:
    """11.1.6 — arşivli türü tek adımda geri alır (§D61-b: salt durum çevirir); `TYPE_RESTORED`
    kullanıcı adıyla. Arşivde olmayan türde hiçbir şey yazılmaz."""
    try:
        restore_type(session, slug, actor=user.username)
        session.commit()
    except TypeNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    return _redirect("restored", slug, country=country)


@router.post(f"{LIST_PATH}/{{slug}}/photo-rules", response_class=HTMLResponse)
def save_photo_rules(
    slug: str,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    enabled: Annotated[list[str] | None, Form()] = None,
    min_width_px: Annotated[str, Form()] = "",
    min_height_px: Annotated[str, Form()] = "",
) -> Response:
    """11.6.1 — türün fotoğraf kural setini kaydeder: işaretli kural açık, işaretsiz kapalı olur;
    asgari çözünürlük piksel olarak yazılır. Geçersiz değer 422 ile alan başına bildirilir ve hiçbir
    şey yazılmaz. Tür formunu ve belge içeriğini değiştirmez (K17)."""
    record = _known_type(session, slug)
    if slug not in PHOTO_RULE_TYPES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_PHOTO_RULES)
    submitted = PhotoRulesForm(
        enabled=tuple(enabled or ()), min_width_px=min_width_px, min_height_px=min_height_px
    )
    try:
        rules = build_photo_rules(submitted)
    except PhotoRulesError as exc:
        return _form_page(
            request,
            user,
            TypeForm.from_record(record),
            slug=slug,
            current_problems=record_problems(record),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            examples=_examples_context(session, layout, slug),
            photo=_photo_context(
                session, slug, record["photo_rules"], form=submitted, problems=exc.problems
            ),
        )
    set_photo_rules(session, slug, rules)
    session.commit()
    return RedirectResponse(
        f"{LIST_PATH}/{quote(slug)}?notice=photo_rules#photo-rules", status.HTTP_303_SEE_OTHER
    )


def _known_type(session: Session, slug: str) -> dict[str, Any]:
    """Türün ham kaydı; katalogda yoksa 404. Örnek uçları yalnız katalogdaki türlerindir. Okuma
    SQLite'ta yazma kilidini tutar (`app.db.session`): işlem hemen bırakılır."""
    try:
        return load_record(session, slug)
    except TypeNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    finally:
        session.rollback()


@router.post(f"{LIST_PATH}/{{slug}}/examples", response_class=HTMLResponse)
async def upload_examples(
    slug: str,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    settings: AppSettings,
) -> HTMLResponse:
    """11.2.1 — türe bir ya da birkaç örnek belge yükler. Dosyalar diske yazılmadan önce hep
    birlikte denetlenir: biri reddedilirse (422) ya da içeriği bu türde zaten örnekse ya da aynı
    yüklemede tekrar ediyorsa (409, 11.9.2) hiçbiri yazılmaz. Yazılan her örnek `example_files`
    kaydı alır (`manual`, `verified`; 11.9.6); olay yazılmaz, çalışan verisine dokunulmaz."""
    record = _known_type(session, slug)
    # Form elle okunur: tarayıcı dosya seçilmemişken adı boş tek bir parça gönderir (bkz.
    # `submit_upload`). Her dosya sınırın bir baytı ötesine kadar okunur: devasa dosya belleğe
    # tümüyle alınmaz, sınır aşımı yine yakalanır.
    limit = settings.max_upload_file_size_bytes
    async with request.form() as submitted:
        chosen = [
            (file.filename, await file.read(limit + 1))
            for file in submitted.getlist("files")
            if isinstance(file, StarletteUploadFile) and file.filename
        ]

    errors: list[str] = []
    checked = []
    for name, content in chosen:
        try:
            checked.append((name, content, check_example(name, content, max_bytes=limit)))
        except ExampleRejectedError as exc:
            errors.append(str(exc))
    if not chosen:
        errors.append(NO_EXAMPLE_FILE)
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT if chosen else status.HTTP_400_BAD_REQUEST
    if not errors:
        errors = _duplicate_examples(session, layout, slug, checked)
        status_code = status.HTTP_409_CONFLICT
    if errors:
        return _form_page(
            request,
            user,
            TypeForm.from_record(record),
            slug=slug,
            current_problems=record_problems(record),
            status_code=status_code,
            examples=_examples_context(session, layout, slug, errors=errors),
            photo=_photo_context(session, slug, record["photo_rules"]),
        )
    stored = [store_example(layout, slug, name, content, kind) for name, content, kind in checked]
    try:
        for example in stored:
            if not example.duplicate:  # ön denetimden sonra başka bir yükleme yazdıysa
                record_uploaded_example(session, slug, example)
        session.commit()
    except IntegrityError:
        session.rollback()
        return _form_page(
            request,
            user,
            TypeForm.from_record(record),
            slug=slug,
            current_problems=record_problems(record),
            status_code=status.HTTP_409_CONFLICT,
            examples=_examples_context(session, layout, slug, errors=[EXAMPLE_RECORD_CLASH]),
            photo=_photo_context(session, slug, record["photo_rules"]),
        )
    return _form_page(
        request,
        user,
        TypeForm.from_record(record),
        slug=slug,
        current_problems=record_problems(record),
        examples=_examples_context(session, layout, slug, stored=stored),
        photo=_photo_context(session, slug, record["photo_rules"]),
    )


def _duplicate_examples(
    session: Session, layout: DataLayout, slug: str, checked: list[tuple[str, bytes, Any]]
) -> list[str]:
    """Aynı içerik bu türde zaten örnekse (etkin kaydı ya da klasördeki kayıtsız dosyası) ya da
    aynı yüklemede tekrar ediyorsa dosya başına ret metni (11.9.2); hiçbir şey yazmaz."""
    listed = listed_hashes(layout, slug)
    seen: dict[str, str] = {}
    problems: list[str] = []
    try:
        for name, content, _kind in checked:
            label = PurePosixPath(name.replace("\\", "/")).name
            sha256 = sha256_bytes(content)
            existing = same_type_example(session, slug, sha256, listed)
            if existing is not None:
                problems.append(EXAMPLE_DUPLICATE.format(file=label, existing=existing))
            elif sha256 in seen:
                problems.append(EXAMPLE_REPEATED.format(file=label, first=seen[sha256]))
            seen.setdefault(sha256, label)
    finally:
        session.rollback()
    return problems


def _removed_only(session: Session, slug: str, name: str) -> bool:
    """Bu adın kaydı var ve hepsi örneklerden çıkarılmış mı (11.9.4 → 11.9.6: dosya uç noktası
    404). Kaydı olmayan (kayıtsız eski) dosya çıkarılmış sayılmaz."""
    try:
        removed = session.execute(
            select(ExampleFileRecord.removed_at).where(
                ExampleFileRecord.type_slug == slug, ExampleFileRecord.name == name
            )
        ).scalars()
        states = [value is not None for value in removed]
    finally:
        session.rollback()
    return bool(states) and all(states)


@router.get(f"{LIST_PATH}/{{slug}}/examples/{{name}}")
def example_file(slug: str, name: str, session: DbSession, layout: Layout) -> FileResponse:
    """Türün örnek dosyası (yüklendiği baytlar). Tür katalogda ya da dosya türün örnek dizininde
    yoksa ya da adın kaydı örneklerden çıkarılmışsa (11.9.6) 404."""
    _known_type(session, slug)
    path = example_path(layout, slug, name)
    if path is None or _removed_only(session, slug, name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, EXAMPLE_NOT_FOUND)
    return FileResponse(path, headers={"X-Content-Type-Options": "nosniff"})


def get_description_provider(settings: AppSettings) -> AnalysisProvider | ProviderConfigError:
    """Tür açıklamasının (11.3.1) sağlayıcısı; kurulamazsa nedenini taşıyan hata (kullanıcıya
    gösterilir)."""
    try:
        return create_provider(settings)
    except ProviderConfigError as exc:
        return exc


DescriptionProvider = Annotated[
    AnalysisProvider | ProviderConfigError, Depends(get_description_provider)
]


@router.post(f"{LIST_PATH}/{{slug}}/description", response_class=HTMLResponse)
def generate_description(
    slug: str,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    settings: AppSettings,
    form: SubmittedForm,
    provider: DescriptionProvider,
    list_country: ListCountryField = None,
) -> HTMLResponse:
    """11.3.1 — türün örneklerinden (fotoğraf türünde ayrıca kabul edilen fotoğraflardan, 11.8.1)
    yapılandırılmış açıklama üretir ve metnini formun `prompt_description` alanına yazarak formu
    yeniden çizer. **Kaydetmez:** İK düzenleyip kaydeder.

    Formdaki (kaydedilmemiş) değerler korunur ve açıklama onlarla istenir; kabul edilen fotoğraflar
    türün kayıtlı kurallarıyla seçilir. Veritabanı işlemi sağlayıcı çağrısından önce bırakılır
    (`_known_type`, `_accepted_photos`): uzun süren çağrı yazma kilidi tutmaz.
    """
    form = replace(form, slug=slug)
    record = _known_type(session, slug)
    photos = _accepted_photos(session, slug, record["photo_rules"])
    # 11.9.4: doğrulanmamış "AI kararı" örneği açıklama üretimine girmez.
    try:
        exclude = unverified_ai_examples(session, slug)
    finally:
        session.rollback()

    def page(
        status_code: int,
        *,
        problems: dict[str, list[str]] | None = None,
        generated: GeneratedDescription | None = None,
        error: str | None = None,
    ) -> HTMLResponse:
        shown = form if generated is None else replace(form, prompt_description=generated.text)
        return _form_page(
            request,
            user,
            shown,
            slug=slug,
            problems=problems,
            current_problems=record_problems(record),
            status_code=status_code,
            examples=_examples_context(session, layout, slug),
            photo=_photo_context(session, slug, record["photo_rules"], accepted=photos),
            generated=generated,
            description_error=error,
            list_country=list_country,
        )

    try:
        entry = build_entry(form)
    except TypeFormError as exc:
        return page(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            problems=exc.problems,
            error=DESCRIPTION_INVALID_FORM,
        )
    if isinstance(provider, ProviderConfigError):
        return page(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            error=DESCRIPTION_PROVIDER_UNAVAILABLE.format(detail=provider),
        )
    try:
        generated = describe_type(entry, layout, settings, provider, photos=photos, exclude=exclude)
    except TypeNotAnalyzedError:
        return page(status.HTTP_422_UNPROCESSABLE_CONTENT, error=DESCRIPTION_NOT_ANALYZED)
    except NoExamplePagesError as exc:
        error = " ".join((DESCRIPTION_NO_EXAMPLES, *exc.skipped))
        return page(status.HTTP_422_UNPROCESSABLE_CONTENT, error=error)
    except ProviderError as exc:
        return page(
            status.HTTP_502_BAD_GATEWAY, error=DESCRIPTION_PROVIDER_FAILED.format(detail=exc)
        )
    except TypeDescriptionError:
        return page(status.HTTP_502_BAD_GATEWAY, error=DESCRIPTION_REJECTED)
    return page(status.HTTP_200_OK, generated=generated)


def _criteria_fragment(request: Request, user: PanelUser, items: list[str]) -> HTMLResponse:
    return render_page(request, "catalog_criteria.html", user=user, criteria=items)


@router.post(f"{LIST_PATH}/criteria/add", response_class=HTMLResponse)
def add_criterion(
    request: Request,
    user: CurrentUser,
    acceptance_criteria: Annotated[list[str] | None, Form()] = None,
) -> HTMLResponse:
    """Madde listesine boş bir madde ekler; kaydetmez (formun geri kalanı yerinde durur)."""
    return _criteria_fragment(request, user, [*(acceptance_criteria or ()), ""])


@router.post(f"{LIST_PATH}/criteria/remove", response_class=HTMLResponse)
def remove_criterion(
    request: Request,
    user: CurrentUser,
    index: Annotated[int, Form(ge=0)],
    acceptance_criteria: Annotated[list[str] | None, Form()] = None,
) -> HTMLResponse:
    """`index`teki maddeyi listeden çıkarır; kaydetmez."""
    items = list(acceptance_criteria or ())
    if index < len(items):
        del items[index]
    return _criteria_fragment(request, user, items)


# --- 11.5: aday türler ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RelatedItemView:
    """Aday türle ilişkili bekleyen Unknown öğesi (kuyruk öğesi detayına bağlanır)."""

    id: int
    upload_id: str
    source: str


@dataclass(frozen=True, slots=True)
class ReanalysisTargetView:
    """Toplu yeniden analizde yeniden analiz edilecek parti ve onun güncel plan sürümü."""

    upload_id: str
    version: int
    item_count: int


@dataclass(frozen=True, slots=True)
class ReanalyzedView:
    """Toplu yeniden analizin bir partideki sonucu."""

    upload_id: str
    previous_version: int
    version: int
    superseded: int


def _first_page(item: QueueItem) -> tuple[int, int] | None:
    """Öğenin ilk kaynak sayfası `(dosya kimliği, 0 tabanlı sıra)`; kayıt bozuk ya da sayfasızsa
    `None` (öğe hiçbir adayla ilişkilendirilmez)."""
    refs = _payload_refs(item.payload_json)
    parsed = _reference(refs[0]) if refs else None
    if parsed is None or not parsed[1]:
        return None
    return parsed[0], parsed[1][0]


def _related_by_candidate(session: Session, candidate_ids: list[int]) -> dict[int, list[QueueItem]]:
    """11.5.3 — her adayın ilişkili bekleyen Unknown öğeleri (kuyruk sırasıyla). Bekleyen öğe
    kuyruk ekranlarının tanımıdır (`_state_filter`): çözülmemiş ve partisinin güncel planında."""
    if not candidate_ids:
        return {}
    unknown = session.scalars(
        select(QueueItem)
        .where(QueueItem.kind == QueueKind.UNKNOWN.value, _state_filter(QueueState.OPEN))
        .order_by(QueueItem.id)
    ).all()
    firsts = [(item, _first_page(item)) for item in unknown]
    related: dict[int, list[QueueItem]] = {}
    for candidate_id in candidate_ids:
        refs = sample_page_refs(session, session.get_one(CandidateDocumentType, candidate_id))
        related[candidate_id] = [item for item, first in firsts if first in refs]
    return related


def _related_view(session: Session, item: QueueItem) -> RelatedItemView:
    refs = _payload_refs(item.payload_json)
    parsed = _reference(refs[0]) if refs else None
    assert parsed is not None  # `_first_page` ile ilişkilendirilmiş öğe
    file_id, pages = parsed
    # İlk sayfa adayın örnek sayfalarından biridir: dosyası vardır.
    name = session.get_one(UploadFile, file_id).original_name
    return RelatedItemView(item.id, item.upload_id, f"{name} · {_page_ranges(pages)}")


def _reanalysis_targets(session: Session, items: list[QueueItem]) -> list[tuple[Upload, Plan, int]]:
    """İlişkili öğelerin partileri (kimlik sırasıyla), güncel planları ve partideki öğe sayısı.
    Süren partide yeniden analiz yapılmaz (10.3.2): biri sürüyorsa 409 ve hiçbiri."""
    counts = Counter(item.upload_id for item in items)
    targets = []
    for upload_id in sorted(counts):
        upload = session.get_one(Upload, upload_id)
        if UploadStatus(upload.status) not in FINAL_STATUSES:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{upload_id}: {BUSY_MESSAGE}")
        plan = current_plan(session, upload)
        assert plan is not None  # bekleyen öğe partinin güncel planındadır
        targets.append((upload, plan, counts[upload_id]))
    return targets


def _target_views(targets: list[tuple[Upload, Plan, int]]) -> list[ReanalysisTargetView]:
    return [ReanalysisTargetView(upload.id, plan.version, count) for upload, plan, count in targets]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def approval_subject(candidate_id: int, entry: CatalogEntry) -> str:
    """Tür onayı belirtecinin (`Operation.APPROVE_TYPE`) bağlı olduğu hedef: aday + eklenecek
    kaydın özeti. İkinci onaydan sonra kayıtta bir alan değişirse belirteç geçmez."""
    canonical = json.dumps(entry.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    return f"{candidate_id}:{_digest(canonical)}"


def batch_reanalysis_subject(candidate_id: int, targets: list[tuple[Upload, Plan, int]]) -> str:
    """Toplu yeniden analiz belirtecinin (`Operation.REANALYZE`) hedefi: aday + partiler ve güncel
    planları. Parti kümesi ya da bir partinin planı değişmişse belirteç geçmez."""
    plans = ";".join(f"{upload.id}:{plan.id}" for upload, plan, _ in targets)
    return f"candidate-types:{candidate_id}:{_digest(plans)}"


def _decided_note(candidate_status: str) -> str:
    return DECIDED_NOTES.get(candidate_status, DECIDED_NOTE)


def _candidate_or_404(session: Session, candidate_id: int) -> CandidateDocumentType:
    try:
        return load_candidate_type(session, candidate_id)
    except CandidateNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CANDIDATE_NOT_FOUND) from None


def _candidate_page(
    request: Request,
    user: PanelUser,
    session: Session,
    candidate: CandidateDocumentType,
    *,
    form: TypeForm | None = None,
    problems: dict[str, list[str]] | None = None,
    notice: str | None = None,
    examine_error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Aday türün detayı: örnek sayfalar, ilişkili bekleyen Unknown öğeleri ve durumuna göre onay
    formu + ret (bekleyen), toplu yeniden analiz (onaylanmış) ya da ret notu. Bekleyen adayın formu
    taslakla dolu açılır (11.5.6, `suggested_form`); `form` verilirse (reddedilen gönderim) o
    çizilir, bant yine sistemin incelemesini anlatır. `examine_error` "Yeniden incele"nin
    hatasıdır."""
    (summary,) = summarize_candidates(session, [candidate], sample_limit=DETAIL_SAMPLE_LIMIT)
    related = _related_by_candidate(session, [candidate.id])[candidate.id]
    pending = candidate.status == CandidateTypeStatus.PENDING.value
    approved = candidate.status == CandidateTypeStatus.APPROVED.value
    targets: list[ReanalysisTargetView] = []
    blocked = None
    if approved and related:
        try:
            targets = _target_views(_reanalysis_targets(session, related))
        except HTTPException as exc:
            blocked = str(exc.detail)
    context: dict[str, Any] = {}
    if pending:
        prefill = suggested_form(candidate, known=_known_types(session))
        context = _fields_context(form or prefill.form, problems) | _prefill_context(
            session, prefill
        )
    return render_page(
        request,
        "catalog_candidate.html",
        user=user,
        active="document_types",
        status_code=status_code,
        candidate=summary,
        status=candidate.status,
        status_label=CANDIDATE_STATUS_LABELS.get(candidate.status, candidate.status),
        approved_slug=approved_type_slug(session, candidate.id) if approved else None,
        related=[_related_view(session, item) for item in related],
        targets=targets,
        reanalysis_blocked=blocked,
        reanalysis_first=BATCH_REANALYZE_FIRST.format(count=len(targets)),
        notice_text=notice,
        examine_error=examine_error,
        is_new=True,
        **context,
    )


def _known_types(session: Session) -> KnownTypes | None:
    """Bilinen türler (katalog ∪ önerilen tür kaydı, §C86); kayıtlı katalog okunamazsa `None` — form
    önerilen kayıt ve çakışma uyarısı olmadan açılır, onay yine slug'ı denetler."""
    try:
        return load_known_types(session)
    except CatalogError:
        return None


def _prefill_context(session: Session, prefill: SuggestedForm) -> dict[str, Any]:
    """Onay formunun üstündeki bant (11.5.6): taslağın durumu, doldurulamayan alanlar, katalog
    çakışması ve önerilen slug'ın doğrulanmamış "AI kararı" örnekleri."""
    if prefill.filled:
        generated = prefill.proposal_generated_at
        state = PREFILL_FILLED.format(
            pages=prefill.proposal_pages,
            date="—" if generated is None else f"{generated:%Y-%m-%d}",
        )
    else:
        template = PREFILL_STATUS.get(prefill.proposal_status, PREFILL_STATUS[None])
        state = template.format(reason=(prefill.proposal_reason or "gerekçe yok").rstrip("."))
    slug = prefill.suggested_slug
    return {
        "prefill": prefill,
        "prefill_state": state,
        "prefill_unfilled": (
            PREFILL_UNFILLED.format(fields=", ".join(prefill.unfilled))
            if prefill.unfilled
            else None
        ),
        "unverified_examples": None if slug is None else unverified_example_count(session, slug),
    }


def _step_page(
    request: Request, user: PanelUser, candidate_id: int, status_code: int, **context: object
) -> HTMLResponse:
    """Onay ve yeniden analiz adımlarının sayfası (`catalog_candidate_step.html`): onay metni,
    sonuç ya da hata."""
    return render_page(
        request,
        "catalog_candidate_step.html",
        user=user,
        active="document_types",
        status_code=status_code,
        candidate_id=candidate_id,
        **context,
    )


@router.get(f"{CANDIDATES_PATH}/{{candidate_id}}", response_class=HTMLResponse)
def candidate_type_page(
    candidate_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    notice: Annotated[str | None, Query(max_length=32)] = None,
) -> HTMLResponse:
    candidate = _candidate_or_404(session, candidate_id)
    response = _candidate_page(
        request, user, session, candidate, notice=CANDIDATE_NOTICES.get(notice or "")
    )
    session.rollback()
    return response


# --- 11.5.2: onay -------------------------------------------------------------------------------


def _entry_rows(entry: CatalogEntry) -> list[tuple[str, str]]:
    """Onay adımlarında gösterilen, kataloğa eklenecek kayıt."""
    pages = entry.expected_pages
    return [
        ("Slug", entry.slug),
        ("Ad", entry.name),
        ("Dosya etiketi", entry.file_label),
        ("Ülke", entry.country or "—"),
        ("Açıklama", entry.description or "—"),
        (
            "Beklenen dosya türleri",
            ", ".join(FILE_TYPE_LABELS[t] for t in entry.expected_file_types),
        ),
        ("Beklenen sayfa sayısı", "—" if pages is None else f"{pages.min} – {pages.max}"),
        ("Yüz yapısı", SIDES_LABELS[entry.sides]),
        (
            "Kabul edilen düzenler",
            ", ".join(LAYOUT_LABELS[layout] for layout in entry.front_back_layouts) or "—",
        ),
        ("Direkt Belge", "Evet" if entry.direct else "Hayır"),
        ("Analiz", "Evet" if entry.analyze else "Hayır"),
        ("Zorunlu alanlar", ", ".join(entry.required_fields) or "—"),
        (
            "İzinli dönüşümler",
            ", ".join(CONVERSION_LABELS[c] for c in entry.allowed_conversions) or "—",
        ),
        ("Çıktı biçimi", OUTPUT_FORMAT_LABELS[entry.output_format]),
        ("Kabul kriterleri", " · ".join(entry.acceptance_criteria) or "—"),
        ("Analizci için açıklama", entry.prompt_description or "—"),
    ]


def _approval(
    session: Session, candidate_id: int, form: TypeForm
) -> tuple[CandidateDocumentType, CatalogEntry]:
    """Onay adımlarının ortak denetimi: aday (404), bekliyor mu (409), form (`TypeFormError`) ve
    slug katalogda boş mu (`TypeExistsError`)."""
    candidate = _candidate_or_404(session, candidate_id)
    if candidate.status != CandidateTypeStatus.PENDING.value:
        raise HTTPException(status.HTTP_409_CONFLICT, _decided_note(candidate.status))
    entry = build_entry(form)
    if session.get(KnownDocumentType, entry.slug) is not None:
        raise TypeExistsError(entry.slug)
    return candidate, entry


def _approval_refused(
    request: Request,
    user: PanelUser,
    session: Session,
    candidate_id: int,
    form: TypeForm,
    exc: Exception,
) -> HTMLResponse:
    """Onay adımının reddi: aday yok/karara bağlanmış → hata sayfası; form ya da slug → detay
    sayfası, form girilen değerlerle ve alan başına mesajla (hiçbir şey yazılmadı)."""
    if isinstance(exc, HTTPException):
        return _step_page(request, user, candidate_id, exc.status_code, error=str(exc.detail))
    if isinstance(exc, TypeFormError):
        problems, code = exc.problems, status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        problems, code = {"slug": [SLUG_TAKEN]}, status.HTTP_409_CONFLICT
    candidate = session.get_one(CandidateDocumentType, candidate_id)
    return _candidate_page(
        request, user, session, candidate, form=form, problems=problems, status_code=code
    )


def _approval_step(candidate: CandidateDocumentType, entry: CatalogEntry) -> dict[str, object]:
    # Onay adımlarının ortak içeriği: eklenecek kayıt ve bir sonraki adıma taşınan (doğrulanmış)
    # form değerleri.
    return {
        "step": "approve",
        "candidate_name": candidate.proposed_name,
        "rows": _entry_rows(entry),
        "form": TypeForm.from_record(entry.model_dump(mode="json")),
    }


@router.post(f"{CANDIDATES_PATH}/{{candidate_id}}/approve/confirm", response_class=HTMLResponse)
def approval_first_confirmation(
    candidate_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    form: SubmittedForm,
) -> HTMLResponse:
    """11.5.2 — formu doğrular ve §20.6'nın birinci onay metnini verir; hiçbir şey değişmez."""
    try:
        candidate, entry = _approval(session, candidate_id, form)
        response = _step_page(
            request,
            user,
            candidate_id,
            status.HTTP_200_OK,
            first_confirmation=first_text(Operation.APPROVE_TYPE, type_name=entry.name),
            **_approval_step(candidate, entry),
        )
    except (HTTPException, TypeFormError, TypeExistsError) as exc:
        response = _approval_refused(request, user, session, candidate_id, form, exc)
    session.rollback()
    return response


@router.post(f"{CANDIDATES_PATH}/{{candidate_id}}/approve/prepare", response_class=HTMLResponse)
def prepare_approval(
    candidate_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    form: SubmittedForm,
) -> HTMLResponse:
    """11.5.2 — birinci onaydan sonra ikinci onay metnini ve kayda bağlı tek kullanımlık onay
    belirtecini verir (§20.6.1)."""
    try:
        candidate, entry = _approval(session, candidate_id, form)
        issued = issue_confirmation(
            session, request, user, Operation.APPROVE_TYPE, approval_subject(candidate_id, entry)
        )
    except (HTTPException, TypeFormError, TypeExistsError) as exc:
        session.rollback()
        response = _approval_refused(request, user, session, candidate_id, form, exc)
        session.rollback()
        return response
    except ConfirmationRefusedError as exc:
        session.rollback()
        return _step_page(request, user, candidate_id, status.HTTP_400_BAD_REQUEST, error=str(exc))
    session.commit()
    return _step_page(
        request,
        user,
        candidate_id,
        status.HTTP_200_OK,
        second_confirmation=second_text(Operation.APPROVE_TYPE),
        confirmation=issued.token,
        **_approval_step(candidate, entry),
    )


@router.post(f"{CANDIDATES_PATH}/{{candidate_id}}/approve", response_class=HTMLResponse)
def approve_candidate(
    candidate_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    form: SubmittedForm,
    confirmation: Annotated[str | None, Form()] = None,
) -> Response:
    """11.5.2 — ikinci onayın belirteciyle türü kataloğa ekler ve adayı onaylar (K16).

    Belirteç yoksa, süresi geçmişse, kullanılmışsa ya da başka adaya, başka kayda, işleme veya
    oturuma aitse hiçbir şey yapılmaz (400). Belirtecin tüketilmesi, `USER_CONFIRMED`, türün
    eklenmesi ve `TYPE_APPROVED` tek işlemdedir: biri düşerse hiçbiri yazılmaz.
    """
    try:
        candidate, entry = _approval(session, candidate_id, form)
        # §20.6.1: belirteç tüketilir ve `USER_CONFIRMED` (kullanıcı adı, işlem, hedef, iki onayın
        # zamanı) yazılır, ardından işlemin kendi olayı (`TYPE_APPROVED`) düşer.
        confirm_operation(
            session,
            request,
            user,
            Operation.APPROVE_TYPE,
            approval_subject(candidate_id, entry),
            confirmation,
            event_target={"candidate_type_id": candidate.id, "document_type_slug": entry.slug},
        )
        approve_candidate_type(session, candidate_id, entry, actor=user.username)
    except (HTTPException, TypeFormError, TypeExistsError) as exc:
        session.rollback()
        response = _approval_refused(request, user, session, candidate_id, form, exc)
        session.rollback()
        return response
    except ConfirmationRefusedError:
        session.rollback()
        return _step_page(
            request, user, candidate_id, status.HTTP_400_BAD_REQUEST, error=CONFIRMATION_REFUSED
        )
    except CandidateDecidedError as exc:
        session.rollback()
        return _step_page(
            request, user, candidate_id, status.HTTP_409_CONFLICT, error=_decided_note(exc.status)
        )
    session.commit()
    return RedirectResponse(
        f"{CANDIDATES_PATH}/{candidate_id}?notice=approved", status.HTTP_303_SEE_OTHER
    )


# --- 11.5.4: ret --------------------------------------------------------------------------------


@router.post(f"{CANDIDATES_PATH}/{{candidate_id}}/reject", response_class=HTMLResponse)
def reject_candidate(
    candidate_id: int, request: Request, user: CurrentUser, session: DbSession
) -> Response:
    """11.5.4 — adayı reddeder (`TYPE_REJECTED`, kullanıcı adıyla); reddedilen aday bir daha
    listeye düşmez. Katalog ve belgeler değişmez."""
    try:
        reject_candidate_type(session, candidate_id, actor=user.username)
    except CandidateNotFoundError:
        session.rollback()
        return _step_page(
            request, user, candidate_id, status.HTTP_404_NOT_FOUND, error=CANDIDATE_NOT_FOUND
        )
    except CandidateDecidedError as exc:
        session.rollback()
        return _step_page(
            request, user, candidate_id, status.HTTP_409_CONFLICT, error=_decided_note(exc.status)
        )
    session.commit()
    return RedirectResponse(f"{CANDIDATES_PATH}?notice=rejected", status.HTTP_303_SEE_OTHER)


@router.post(f"{CANDIDATES_PATH}/{{candidate_id}}/restore", response_class=HTMLResponse)
def restore_candidate(
    candidate_id: int, request: Request, user: CurrentUser, session: DbSession
) -> Response:
    """11.5.7 — reddedilen adayı tek adımda yeniden bekleyen yapar (`CANDIDATE_TYPE_RESTORED`,
    kullanıcı adıyla). Katalog ve belgeler değişmez."""
    try:
        restore_candidate_type(session, candidate_id, actor=user.username)
    except CandidateNotFoundError:
        session.rollback()
        return _step_page(
            request, user, candidate_id, status.HTTP_404_NOT_FOUND, error=CANDIDATE_NOT_FOUND
        )
    except CandidateNotRejectedError:
        session.rollback()
        return _step_page(
            request, user, candidate_id, status.HTTP_409_CONFLICT, error=NOT_REJECTED_NOTE
        )
    session.commit()
    return RedirectResponse(f"{CANDIDATES_PATH}?notice=restored", status.HTTP_303_SEE_OTHER)


# --- 11.5.6: yeniden incele ---------------------------------------------------------------------


@router.post(f"{CANDIDATES_PATH}/{{candidate_id}}/examine", response_class=HTMLResponse)
def reexamine_candidate(
    candidate_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    provider: DescriptionProvider,
) -> HTMLResponse:
    """11.5.6 — bekleyen adayı hemen yeniden inceler (11.5.5'in `read_examination` → `examine` →
    `store_examination` üçlüsü, işçinin boş-zaman işiyle aynı) ve sayfayı yeni taslakla dolu formla
    yeniden çizer. Önerilen tür kaydının eşleşen satırı isteğe girer (`suggested_type`).

    Tür açıklaması (`POST /document-types/{slug}/description`) gibi eşzamanlıdır: veritabanı
    işlemi sağlayıcı çağrısından önce bırakılır, sonuç yeni işlemde yazılır. Başarıda deneme sayacı
    sıfırlanır ve işçinin sahiplenmesi kaldırılır (süren bir boş-zaman birimi sonucunu yazmaz).
    Sağlayıcı kurulamıyorsa 503, yanıt vermez ya da yanıt şemaya uymazsa 502: taslak değişmez, hata
    bantta yazar; yapılmış çağrının kullanımı olayla (`CANDIDATE_TYPE_EXAMINED`, sonuç `error`)
    sayılır. Karara bağlanmış aday 409. Kaydetmez ve onaylamaz: onay iki aşamalıdır (K16).
    """
    candidate = _candidate_or_404(session, candidate_id)

    def page(
        status_code: int, *, notice: str | None = None, error: str | None = None
    ) -> HTMLResponse:
        current = session.get_one(CandidateDocumentType, candidate_id)
        response = _candidate_page(
            request,
            user,
            session,
            current,
            notice=notice,
            examine_error=error,
            status_code=status_code,
        )
        session.rollback()
        return response

    if candidate.status != CandidateTypeStatus.PENDING.value:
        note = _decided_note(candidate.status)
        session.rollback()
        return _step_page(request, user, candidate_id, status.HTTP_409_CONFLICT, error=note)
    if isinstance(provider, ProviderConfigError):
        return page(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            error=EXAMINE_PROVIDER_UNAVAILABLE.format(detail=provider),
        )
    known = _known_types(session)
    suggested = None
    if known is not None:
        suggested = suggested_type(known, candidate, load_proposal(candidate))
    source = read_examination(session, candidate, suggested=suggested)
    session.rollback()  # Uzun süren çağrı yazma kilidi tutmasın.
    error = None
    try:
        examination = examine(source, layout, provider)
    except ProviderError as exc:
        error = (EXAMINE_PROVIDER_FAILED.format(detail=exc), exc)
    except TypeProposalError as exc:
        error = (EXAMINE_REJECTED, exc)
    candidate = session.get_one(CandidateDocumentType, candidate_id)
    if candidate.status != CandidateTypeStatus.PENDING.value:
        # İstek sürerken karara bağlandı: sonuç yazılmaz.
        note = _decided_note(candidate.status)
        session.rollback()
        return _step_page(request, user, candidate_id, status.HTTP_409_CONFLICT, error=note)
    if error is not None:
        text, exc = error
        store_error(
            session,
            candidate,
            error=type(exc).__name__,
            final=False,
            provider=provider,
        )
        session.commit()
        return page(status.HTTP_502_BAD_GATEWAY, error=text)
    store_examination(session, candidate, examination, provider=provider)
    candidate.idle_attempts = 0
    CANDIDATE_EXAMINATIONS.clear(candidate)
    session.commit()
    return page(status.HTTP_200_OK, notice=EXAMINED_NOTICE)


# --- 11.5.3: toplu yeniden analiz ---------------------------------------------------------------


def _reanalysis(
    session: Session, candidate_id: int
) -> tuple[CandidateDocumentType, list[tuple[Upload, Plan, int]]]:
    """Toplu yeniden analizin ortak denetimi: aday (404), onaylanmış mı (409), ilişkili bekleyen
    Unknown öğesi var mı (409) ve partilerin hiçbiri sürmüyor mu (409)."""
    candidate = _candidate_or_404(session, candidate_id)
    if candidate.status != CandidateTypeStatus.APPROVED.value:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_APPROVED_NOTE)
    related = _related_by_candidate(session, [candidate.id])[candidate.id]
    if not related:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_RELATED_NOTE)
    return candidate, _reanalysis_targets(session, related)


@router.post(f"{CANDIDATES_PATH}/{{candidate_id}}/reanalyze/prepare", response_class=HTMLResponse)
def prepare_batch_reanalysis(
    candidate_id: int, request: Request, user: CurrentUser, session: DbSession
) -> HTMLResponse:
    """11.5.3 — birinci onaydan sonra ikinci onay metnini ve partilere bağlı tek kullanımlık
    belirteci verir (10.3.2, §20.6.1)."""
    try:
        candidate, targets = _reanalysis(session, candidate_id)
        issued = issue_confirmation(
            session,
            request,
            user,
            Operation.REANALYZE,
            batch_reanalysis_subject(candidate_id, targets),
        )
    except HTTPException as exc:
        session.rollback()
        return _step_page(request, user, candidate_id, exc.status_code, error=str(exc.detail))
    except ConfirmationRefusedError as exc:
        session.rollback()
        return _step_page(request, user, candidate_id, status.HTTP_400_BAD_REQUEST, error=str(exc))
    session.commit()
    return _step_page(
        request,
        user,
        candidate_id,
        status.HTTP_200_OK,
        step="reanalyze",
        candidate_name=candidate.proposed_name,
        targets=_target_views(targets),
        second_confirmation=BATCH_REANALYZE_SECOND,
        confirmation=issued.token,
    )


@router.post(f"{CANDIDATES_PATH}/{{candidate_id}}/reanalyze", response_class=HTMLResponse)
def batch_reanalyze(
    candidate_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Annotated[DataLayout, Depends(get_layout)],
    executor: Annotated[PlanExecutor, Depends(get_plan_executor)],
    provider: ReanalysisProvider,
    settings: AppSettings,
    confirmation: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    """11.5.3 — ikinci onayın belirteciyle ilişkili Unknown öğelerinin partilerini güncel katalogla
    yeniden analiz eder (06.6.2, K18).

    Belirteçsiz ya da geçersiz belirteçle hiçbir şey yapılmaz (400). Belirtecin tüketilmesi,
    `USER_CONFIRMED` ve bütün partilerin yeniden analizi tek işlemdedir: biri düşerse hiçbiri
    kalmaz.
    """
    try:
        candidate, targets = _reanalysis(session, candidate_id)
        confirm_operation(
            session,
            request,
            user,
            Operation.REANALYZE,
            batch_reanalysis_subject(candidate_id, targets),
            confirmation,
            event_target={
                "candidate_type_id": candidate.id,
                "uploads": [
                    {"upload_id": upload.id, "plan_id": plan.id} for upload, plan, _ in targets
                ],
            },
        )
        if isinstance(provider, ProviderConfigError):
            raise ReanalysisProviderError(str(provider))
        catalog = export_catalog(session)
        results = []
        for upload, _, _ in targets:
            reanalysis = reanalyze_upload(
                session,
                layout,
                upload,
                provider=provider,
                catalog=catalog,
                executor=executor,
                catalog_token_budget=settings.catalog_token_budget,
            )
            results.append(
                ReanalyzedView(
                    upload.id,
                    reanalysis.previous_plan.version,
                    reanalysis.plan.version,
                    len(reanalysis.superseded_document_ids),
                )
            )
    except HTTPException as exc:
        session.rollback()
        return _step_page(request, user, candidate_id, exc.status_code, error=str(exc.detail))
    except ConfirmationRefusedError:
        session.rollback()
        return _step_page(
            request, user, candidate_id, status.HTTP_400_BAD_REQUEST, error=CONFIRMATION_REFUSED
        )
    except ReanalysisProviderError as exc:
        session.rollback()
        return _step_page(
            request, user, candidate_id, status.HTTP_503_SERVICE_UNAVAILABLE, error=str(exc)
        )
    except PLAN_EXECUTION_ERRORS as exc:
        session.rollback()
        return _step_page(request, user, candidate_id, status.HTTP_409_CONFLICT, error=str(exc))
    session.commit()
    remaining = len(_related_by_candidate(session, [candidate_id])[candidate_id])
    session.rollback()
    return _step_page(
        request,
        user,
        candidate_id,
        status.HTTP_200_OK,
        step="reanalyzed",
        candidate_name=candidate.proposed_name,
        results=results,
        remaining=remaining,
    )
