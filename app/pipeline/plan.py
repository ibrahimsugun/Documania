"""Plan JSON üretimi, belirleyicilik, işlem seçimi, Direkt Belge kuralı ve dönüşüm izni — PRD
06.1.1, 06.1.2, 06.2.1, 06.3.1, 06.3.2, 06.4.1 (§8.5, §20.3, §20.4; K3, K9, K11, K12, R5, R10, R7).

Karar motorunun bir parti için verdiği bütün kararlar tek bir **Plan JSON**'da dondurulur (K9):
uygulayıcı (07.x) ve kuyruk (08.1) planı yürütür, yapay zekâya ya da eşleştirmeye yeniden sormaz.
`create_plan` partiyi gruplar (04.1–04.7), her öğenin kararını verir, planı `plans` tablosuna
hash'iyle yazar ve `PLAN_CREATED` olayını atar.

**Öğeler.** Plan partinin her dosyasını ve tekrar olmayan dosyaların her sayfasını tam bir öğeye
bağlar; hiçbir sayfa sessizce düşmez (R7):

- Her belge adayı (dosya içi ve dosyalar arası) bir öğedir. `sources` adayın sayfalarını dosya
  başına, belgedeki sırasıyla taşır — dosyalar arası adayda önce ön yüzün dosyası.
- Word/Excel eki (04.7.1) bir öğedir; dosya bütün olarak alınır (`pages: []`).
- Dosyanın boş sayfaları (02.4.1 ve analizcinin boş dediği sayfalar) tek bir `skip` öğesidir (S8).
- Dosyanın analizi yapılamamış sayfaları tek bir `unresolved` öğesidir: içerikleri bilinmez.
- Sayfası olmayan ve Word/Excel eki olarak tanınmayan dosya `unresolved` öğesidir.
- Tekrar yüklenen dosya (01.4.1) `skip` öğesidir; yeniden işlenmez (S2).

Öğeler dosya (`upload_files.id`) ve ilk sayfa sırasıyla dizilir; `item_id` bu sırayla `i1`, `i2`…
verilir ve kararlar da bu sırayla alınır: aynı partide açılan çalışan sonraki öğede bulunur.

**Rota.** Belge adayının hükümleri şu öncelikle okunur; ilk hüküm rotayı verir, kuyruğa gönderen
bütün hükümlerin gerekçeleri (`route_reason`) aynı sırayla birleşir:

1. Bilinmeyen tür (04.6.1) → `unknown`.
2. Yapısal hüküm — ardışıklık (04.2.1), belirsiz eşleştirme (04.3.2), sayfa sayısı (04.5.1) →
   `unresolved`. Yapısal hükümlü aday eksik ya da parça bir belgedir: okunaklılık kapısı ve işlem
   seçimi ona uygulanmaz (yalnız arka yüzden oluşan parça "okunamayan alanlar" almaz).
3. Okunaklılık kapısı (04.4) — zorunlu alan okunmuyorsa `unreadable`, kabul kriteri karşılanmıyorsa
   `unresolved`. MRZ önceliği (05.3.3) kapıdan ve kişi anahtarından önce her sayfaya uygulanır.
4. İşlem — Direkt Belge format kontrolü (06.3.2), işlem seçimi (06.2.1), Direkt Belge matrisi
   (06.3.1) ve dönüşüm izni (06.4.1): format tutmuyorsa, §20.3'te uyan satır yoksa (satır 7), matris
   işlemi yasaklıyorsa ya da dönüşüm türün `allowed_conversions`'ında değilse `unresolved`.
5. Çalışan kararı (§20.2.2).

Hiçbir hüküm yoksa rota `hazir`dır.

**İşlem (06.2.1).** `select_operation` belge adayının ve Word/Excel ekinin fiziksel işlemini §20.3
karar tablosuyla seçer; satırlar sırayla denenir, ilk uyan kazanır:

1. Tek dosya, dosyanın tüm sayfaları, hedef biçim kaynağınki → `passthrough` (Word/Excel eki dahil).
2. Tek PDF, sayfalarının ardışık alt kümesi, hedef PDF → `extract`.
3. Birden çok dosya, hedef PDF → `merge`.
4. Tek JPEG/PNG, tek sayfa, hedef PDF → `wrap_image`.
5. Tek PDF, tek sayfa, hedef JPEG, sayfa tek tam sayfa gömülü görüntü (02.5.1) → `extract_image`.
6. Tek PDF, tek sayfa, hedef JPEG, gömülü tek görüntü yok → `render_image`.
7. Hiçbiri → işlem yok, `unresolved`; gerekçe kaynakları, kapsamayı ve hedef biçimi yazar.

Kaynak biçimi içerikten tespit edilir (01.2.1); istemcinin bildirdiği `mime`'a güvenilmez. Hedef
biçim türün `output_format`'ıdır; `keep` kaynakların ortak biçimidir — kaynaklar farklı biçimdeyse
ya da biçimi tanınmıyorsa hedef yoktur ve hiçbir satır uymaz. Kapsama dosyanın sayfa satırlarıyla
ve `page_count`'uyla ölçülür: dosyanın adayda olmayan tek bir sayfası (boş sayfa dahil) adayı alt
küme yapar, boş sayfa çıktıya girmez (S8). Ardışıklık K5'tir: alınan sayfaların arasında boş sayfa
dışında sayfa yoksa ardışıktır. Seçim okunaklılık kapısından sonra, çalışan kararından önce yapılır:
işlemi olmayan belgeden çalışan açılmaz, kimlik birikmez. İşlem ve hedef yalnız `hazir` öğede plana
girer; kuyruğa giden öğenin işlemi yoktur (§20.4: reddedilen işlem uygulanmaz).

**Direkt Belge (06.3.1, 06.3.2).** `direct: true` türün (K3) işlemi §20.4'ten geçer; belge adayı
da Word/Excel eki de. Önce format kontrolü (§20.4.1): kaynaklardan birinin içerikten tespit edilen
biçimi türün `expected_file_types`'ında yoksa — tanınmayan biçim de yoktur — işlem seçilmez ve belge
"Uygun formatta yeniden gönderin." gerekçesiyle Unresolved'a gider; dönüştürülerek kurtarılmaz (S6).
Format tutarsa §20.3 işlemi seçer ve izin matrisi uygulanır: Direkt Belge'de yalnız `passthrough` ve
`extract` (tek kaynağın sayfaları olduğu gibi) izinlidir; `merge`, `wrap_image`, `extract_image` ve
`render_image` yasaktır, işlem plana girmez, belge Unresolved'a gider. İlk ret sonraki adımı keser:
format tutmayan belgede işlem seçilmez, uyan satırı olmayan belgede matris denenmez. Ret gerekçesi
okunaklılık gerekçelerinin ardından gelir ve `DIRECT_DOC_CHECK` olayına adayın ilk sayfasıyla (ekte
dosyayla) yazılır; izinli işlem olay atmaz, planda durur. `direct: false` sütununun "dönüşüm
izinliyse" şartı (`allowed_conversions`) 06.4.1'indir.

**Dönüşüm izni (06.4.1).** §20.3 satır 3–6'nın işlemleri — `merge`, `wrap_image`, `extract_image`,
`render_image` — dönüşümdür (K12) ve türün `allowed_conversions` listesinde bulunmak zorundadır;
`passthrough` ve `extract` dönüşüm değildir, her türde izinlidir. Kontrol matristen sonra yapılır
(Direkt Belge'nin listesi boştur ve matris dönüşümü zaten reddeder). Listede olmayan dönüşüm plana
girmez, başka bir satıra düşülmez — gömülü tek görüntülü sayfada izinsiz `extract_image` yerine
`render_image` denenmez (K12) — ve belge dönüştürülmeden gerekçesiyle Unresolved'a gider. Gerekçe
okunaklılık gerekçelerinin ardından gelir. Olay atılmaz: §8.3'te dönüşüm izni için tür yoktur, ret
planın gerekçesinde durur.

**Çalışan.** Her analizli adayın kişi anahtarı (05.4) kayıtlı çalışanlarla eşleştirilir (05.5).
Kararın yan etkileri yalnız belge düzeyinde kabul edilen adayda (1–4'te hükmü olmayan) yürür:
satır 1/3 eşleşmesinde yeni isim yazımı, temiz numara ve iletişim bilgisi çalışana eklenir (05.7.2,
05.8); eşleşme yoksa satır 6'da çalışan açılır (05.6), satır 7'de profil onaya önerilir (05.7.1),
satır 8 ve tablo dışı eksik kişi Unresolved'a gider. Kuyruğa giden adaydan çalışan açılmaz, profil
önerilmez, kimlik ya da iletişim bilgisi birikmez — yapısı veya okunaklılığı kabul edilmemiş
belgenin okumasına güvenilmez. Eşleştirme hükmü o adayda yalnız kişi tahmini olarak kalır
(08.1.2): satır 1/3'te `match` ve çalışan, öteki hükümlerde `none`; eşleştirme hükmü de kuyruğa
gönderiyorsa (satır 2, 4, 5, çelişkili anahtar) gerekçesi eklenir. Word/Excel ekinin sahibi partinin
bağlam çalışanıdır (`match`, `matched_by: null`); bağlam yoksa ek Unresolved'a gider (04.7.1).
İşlemi olmayan ekte işlem gerekçesi sahiplik gerekçesinden önce gelir; bağlam çalışanı kişi tahmini
kalır.

**Hedef.** Yalnız `hazir` öğede dolar ve orada zorunludur. `target_format` seçilen işlemin hedef
biçimidir (yukarıda). `target_name` çalışan kaydının ad-soyadı ve türün `file_label`'ıyla K8 adıdır
(`Ad_Soyad-Passport.pdf`); sıra eki (`-2`) plana girmez, yazma anında diskte seçilir (00.4.3, 07.7).
`validations` 06.5'indir.

**Belirleyicilik (06.1.2).** Plan yalnız kalıcı girdilerin işlevidir: saklanan sayfa analizleri,
güncel katalog, planlama anındaki çalışan kayıtları ve parti (bağlam çalışanı, dosyalar). Zaman
damgası, rastgele değer ve sözlük sırası plana girmez; MRZ doğum tarihinin yüzyılı (§20.1.6) saat
değil partinin alındığı gün ile seçilir. `plan_hash` planın kanonik JSON'unun (anahtarlar sıralı,
boşluksuz, UTF-8) SHA-256'sıdır: aynı analiz sonuçlarından iki kez üretilen plan aynı baytları ve
aynı hash'i verir. Planın kendi yan etkisi (açılan çalışan) sonraki bir planlamanın girdisini
değiştirir; bu yüzden mevcut plan yeniden üretilmez, yeniden çalıştırılır (06.6.1). Aynı partinin
yeni planı bir sonraki sürüm numarasını alır (K18, 06.6.2).
"""

from __future__ import annotations

import enum
import json
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, replace
from datetime import date
from functools import partial
from itertools import pairwise
from typing import Annotated, ClassVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    ValidationError,
    model_validator,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.schemas import PageAnalysis
from app.catalog import Catalog, CatalogEntry, Conversion, FileType, OutputFormat
from app.catalog.schema import FieldName, Slug, Text
from app.db.models import Employee, Plan, QueueKind, Upload, UploadFile
from app.events import EventType, event_context, record_event
from app.matching.contacts import accumulate_contacts
from app.matching.match import (
    EmployeeAction,
    EmployeeMatch,
    MatchedBy,
    MatchRule,
    PersonKey,
    UnmatchedResolution,
    UnmatchedRule,
    accumulate_identity,
    build_person_key,
    create_employee,
    match_employee,
    propose_pending_profile,
    resolve_unmatched,
)
from app.matching.mrz import apply_mrz_priority
from app.pipeline.group import (
    AttachmentFile,
    CandidatePage,
    DocumentCandidate,
    FileGrouping,
    UploadGrouping,
    group_upload,
)
from app.pipeline.legibility import check_legibility
from app.storage import (
    DataLayout,
    FileKind,
    UnsupportedFileTypeError,
    detect_file_kind,
    document_stem,
    sequenced_filename,
    sha256_bytes,
)

# --- sözleşme (§8.5) ---------------------------------------------------------------------------


class Operation(enum.StrEnum):
    """Plan JSON `operation` (§8.5): K11'in izin verdiği fiziksel işlemler; seçimi §20.3."""

    PASSTHROUGH = "passthrough"
    EXTRACT = "extract"
    MERGE = "merge"
    WRAP_IMAGE = "wrap_image"
    EXTRACT_IMAGE = "extract_image"
    RENDER_IMAGE = "render_image"


class Route(enum.StrEnum):
    """Plan JSON `route` (§8.5): çalışanın `Hazir/` klasörü, üç kuyruk (`QueueKind`) ya da atla."""

    READY = "hazir"
    UNKNOWN = "unknown"
    UNREADABLE = "unreadable"
    UNRESOLVED = "unresolved"
    SKIP = "skip"


ItemId = Annotated[str, StringConstraints(strict=True, pattern=r"^i[1-9][0-9]*$")]
EmployeeId = Annotated[str, StringConstraints(strict=True, pattern=r"^E[0-9]{4,}$")]
# `uploads.id` (32 karakter) ve veri dizini yol parçası kümesi (`app/storage/layout.py`).
UploadId = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
]
ModelName = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]
FileId = Annotated[StrictInt, Field(ge=1)]
PageIndex = Annotated[StrictInt, Field(ge=0)]
# K8 çıktı adı: sıra eksiz gövde ve küçük harfli uzantı (`app/storage/naming.py`).
TargetName = Annotated[
    str,
    StringConstraints(
        strict=True, max_length=255, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*\.[a-z0-9]{1,10}$"
    ),
]


class PlanSource(BaseModel):
    """Öğenin tek kaynak dosyası: `upload_files.id` ve alınan sayfalar (`pages.index`).

    Sayfalar artan sıradadır. Sayfası olmayan dosyada (Word/Excel, K2) ya da bütün olarak ele alınan
    dosyada (tekrar yükleme) liste boştur: dosya bütün olarak alınır.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    file_id: FileId
    pages: tuple[PageIndex, ...]

    @model_validator(mode="after")
    def _increasing_pages(self) -> PlanSource:
        if any(first >= second for first, second in pairwise(self.pages)):
            raise ValueError("pages artan sırada ve tekrarsız olmalı")
        return self


class PlanEmployee(BaseModel):
    """Plan JSON `employee` (§8.5, §20.2.2).

    `employee_id` yalnız `match` ve `create` kararında doludur ve orada zorunludur; `matched_by`
    yalnız `match`'te dolabilir (bağlam çalışanına verilen Word/Excel ekinde boştur).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: EmployeeAction
    employee_id: EmployeeId | None
    matched_by: MatchedBy | None

    @model_validator(mode="after")
    def _consistent(self) -> PlanEmployee:
        owned = self.action in (EmployeeAction.MATCH, EmployeeAction.CREATE)
        if owned != (self.employee_id is not None):
            raise ValueError("employee_id yalnız match ve create kararında dolar ve orada zorunlu")
        if self.matched_by is not None and self.action is not EmployeeAction.MATCH:
            raise ValueError("matched_by yalnız match kararında dolar")
        return self


class PlanValidation(BaseModel):
    """Plan JSON `validations` satırı (§8.5); doğrulayıcılar 06.5'indir."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: FieldName
    ok: StrictBool


class PlanItem(BaseModel):
    """Planın tek öğesi (§8.5): kaynak, işlem, hedef, çalışan ve rota.

    `hazir` öğenin çalışanı (`match`/`create`), işlemi ve hedefi vardır, gerekçesi yoktur; kuyruğa
    ya da atlamaya giden öğenin gerekçesi zorunludur, işlemi ve hedefi yoktur — uygulanmayacak işlem
    plana girmez. `target_name`'in uzantısı `target_format`'tır.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: ItemId
    document_type_slug: Slug | None
    sources: Annotated[tuple[PlanSource, ...], Field(min_length=1)]
    operation: Operation | None
    target_format: FileType | None
    target_name: TargetName | None
    employee: PlanEmployee
    route: Route
    route_reason: Text | None
    validations: tuple[PlanValidation, ...]

    @model_validator(mode="after")
    def _consistent(self) -> PlanItem:
        file_ids = [source.file_id for source in self.sources]
        if len(set(file_ids)) != len(file_ids):
            raise ValueError("bir dosya sources'ta bir kez geçer")
        if self.route is Route.READY:
            if self.route_reason is not None:
                raise ValueError("hazir öğede route_reason boş olmalı")
            if self.employee.employee_id is None:
                raise ValueError("hazir öğenin çalışanı olmalı (match veya create, R7)")
            if self.operation is None:
                raise ValueError("hazir öğede operation zorunlu (06.2.1)")
            if self.target_name is None:
                raise ValueError("hazir öğede target_format ve target_name zorunlu")
        else:
            if self.route_reason is None:
                raise ValueError("hazir olmayan öğede route_reason zorunlu")
            if self.operation is not None:
                raise ValueError("operation yalnız hazir öğede dolar")
            if self.target_format is not None or self.target_name is not None:
                raise ValueError("hedef yalnız hazir öğede dolar")
        if self.target_name is not None and (
            self.target_format is None
            or not self.target_name.endswith(f".{self.target_format.value}")
        ):
            raise ValueError("target_name'in uzantısı target_format olmalı")
        return self


class PlanDocument(BaseModel):
    """Partinin dondurulmuş planı (§8.5, K9).

    Öğe kimlikleri tekildir; bir sayfa en fazla bir öğeye aittir, bütün olarak alınan dosyanın
    başka öğesi olmaz. `plan_hash` kanonik JSON'un SHA-256'sıdır (06.1.2).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    upload_id: UploadId
    version: Annotated[StrictInt, Field(ge=1)]
    model: ModelName | None
    items: tuple[PlanItem, ...]

    @model_validator(mode="after")
    def _items_do_not_overlap(self) -> PlanDocument:
        item_ids = [item.item_id for item in self.items]
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("item_id plan içinde tekil olmalı")
        claimed: set[tuple[int, int]] = set()
        whole: set[int] = set()
        touched: set[int] = set()
        for item in self.items:
            for source in item.sources:
                if source.file_id in whole or (not source.pages and source.file_id in touched):
                    raise ValueError("bütün olarak alınan dosyanın başka öğesi olamaz")
                if not source.pages:
                    whole.add(source.file_id)
                for page in source.pages:
                    if (source.file_id, page) in claimed:
                        raise ValueError("bir sayfa birden fazla öğeye ait olamaz")
                    claimed.add((source.file_id, page))
                touched.add(source.file_id)
        return self

    def canonical_json(self) -> bytes:
        """Hash'in girdisi: anahtarları sıralı, ayırıcıları boşluksuz, UTF-8 JSON."""
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @property
    def plan_hash(self) -> str:
        return sha256_bytes(self.canonical_json())


class PlanIntegrityError(ValueError):
    """Saklanan plan §8.5 sözleşmesine ya da kaydının kimliğine/hash'ine uymuyor.

    Mesaj yalnız alan konumunu ve kuralı taşır; plan değerleri (hedef adı kişi adı taşır) tekrar
    edilmez (CONVENTIONS §6).
    """


def read_plan(row: Plan) -> PlanDocument:
    """`plans` kaydındaki JSON'u sözleşmeyle okur ve kaydın hash'iyle doğrular.

    Dondurulduktan sonra değişmiş, sözleşmeye uymayan ya da başka parti/sürüm/modeli gösteren plan
    `PlanIntegrityError` verir — uygulayıcı değişmiş planı yürütmez (K9).
    """
    try:
        document = PlanDocument.model_validate(row.json)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'plan'}: {error['msg']}"
            for error in exc.errors(include_url=False, include_input=False, include_context=False)
        )
        raise PlanIntegrityError(
            f"Saklanan plan §8.5 sözleşmesine uymuyor (plan {row.id}): {problems}"
        ) from None
    if (document.upload_id, document.version, document.model) != (
        row.upload_id,
        row.version,
        row.model,
    ):
        raise PlanIntegrityError(
            f"Saklanan planın parti, sürüm ya da modeli kaydıyla uyuşmuyor (plan {row.id})"
        )
    if document.plan_hash != row.plan_hash:
        raise PlanIntegrityError(
            f"Saklanan planın hash'i kaydıyla uyuşmuyor (plan {row.id}): plan dondurulduktan "
            "sonra değişmiş"
        )
    return document


# --- işlem seçimi (06.2.1, §20.3) --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OperationSource:
    """İşlem seçiminin okuduğu tek kaynak dosya (§20.3 girdileri).

    `kind` içerikten tespit edilen biçimdir (01.2.1); tanınmıyorsa `None`. `pages` öğenin bu
    dosyadan aldığı sayfalardır (`pages.index`); boşsa dosya bütün olarak alınır (Word/Excel, K2).
    `file_pages` dosyanın bütün sayfaları, `blank_pages` boş sayfaları (02.4.1 ve analizcinin boş
    dediği; başka belgeye ait sayılmaz), `single_image_pages` tek tam sayfa gömülü görüntüden oluşan
    sayfalarıdır (02.5.1).
    """

    file_id: int
    kind: FileKind | None
    pages: tuple[int, ...] = ()
    file_pages: frozenset[int] = frozenset()
    blank_pages: frozenset[int] = frozenset()
    single_image_pages: frozenset[int] = frozenset()

    @property
    def whole(self) -> bool:
        """Kapsama: dosyanın bütün sayfaları mı alınıyor; alınmayan tek sayfa alt küme yapar."""
        return not self.pages or frozenset(self.pages) == self.file_pages

    @property
    def contiguous(self) -> bool:
        """Ardışıklık (K5): alınan sayfaların arasında yalnız boş sayfa olabilir."""
        taken = frozenset(self.pages)
        if not taken:
            return True
        return taken.union(self.blank_pages).issuperset(range(min(taken), max(taken) + 1))


@dataclass(frozen=True, slots=True)
class SelectedOperation:
    """§20.3 satır 1–6'nın seçtiği işlem ve çıktının biçimi."""

    operation: Operation
    target_format: FileType


@dataclass(frozen=True, slots=True)
class NoApplicableOperation:
    """§20.3 satır 7: kaynak, kapsama ve biçim için tabloda uyan işlem yok; belge dönüştürülmez.

    Belge gerekçesiyle Unresolved'a gider. `sources` öğenin kaynaklarıdır; `target_format` türün
    hedef biçimidir (`keep`'te kaynakların ortak biçimi yoksa `None`). Gerekçe dosya kimliği, 1'den
    başlayan sayfa numarası ve biçim taşır; kişisel değer taşımaz.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED

    sources: tuple[OperationSource, ...]
    target_format: FileType | None

    @property
    def reason(self) -> str:
        label = "Kaynak" if len(self.sources) == 1 else "Kaynaklar"
        described = "; ".join(_operation_source_text(source) for source in self.sources)
        if self.target_format is not None:
            target = self.target_format.value
        elif any(source.kind is None for source in self.sources):
            target = "belirlenemedi (output_format: keep, kaynak biçimi tanınmadı)"
        else:
            target = "belirlenemedi (output_format: keep, kaynaklar farklı biçimde)"
        return (
            f"İşlem seçilemedi (06.2.1): {label}: {described}. Hedef biçim: {target}. §20.3'te bu "
            "kaynak, kapsama ve biçim için uyan fiziksel işlem yok; belge dönüştürülmez."
        )


def select_operation(
    sources: Sequence[OperationSource], *, output_format: OutputFormat
) -> SelectedOperation | NoApplicableOperation:
    """Öğenin fiziksel işlemini §20.3 karar tablosuyla seçer (06.2.1); kurallar modül açıklamasında.

    `sources` öğenin en az bir kaynak dosyasıdır (plandaki `sources` sırasıyla); `output_format`
    türün çıktı biçimidir. Saf işlevdir. Direkt Belge kuralı (06.3: `check_direct_file_types` önce,
    `check_direct_operation` sonra) ve dönüşüm izni (06.4.1: `check_conversion`) planlayıcıda
    uygulanır; bu işlev onlara bakmaz.
    """
    target = _target_format(sources, output_format)
    operation = _table_operation(sources, target)
    if operation is None or target is None:
        return NoApplicableOperation(tuple(sources), target)
    return SelectedOperation(operation, target)


def _target_format(
    sources: Sequence[OperationSource], output_format: OutputFormat
) -> FileType | None:
    # Hedef biçim türün `output_format`'ıdır; `keep` kaynakların ortak biçimidir.
    if output_format is not OutputFormat.KEEP:
        return FileType(output_format.value)
    kinds = {source.kind for source in sources}
    if len(kinds) != 1:
        return None
    (kind,) = kinds
    return None if kind is None else FileType(kind.value)


def _table_operation(
    sources: Sequence[OperationSource], target: FileType | None
) -> Operation | None:
    # §20.3 satırları sırayla, ilk uyan kazanır. Satır 3 dışındaki satırlar tek dosya ister; satır
    # 3'ün yeri sonucu değiştirmez.
    if len(sources) > 1:
        return Operation.MERGE if target is FileType.PDF else None  # satır 3
    (source,) = sources
    kind = None if source.kind is None else FileType(source.kind.value)
    single_page = len(source.pages) == 1
    if kind is not None and kind is target and source.whole:
        return Operation.PASSTHROUGH  # satır 1
    if kind is FileType.PDF and target is FileType.PDF and not source.whole and source.contiguous:
        return Operation.EXTRACT  # satır 2
    if kind in (FileType.JPEG, FileType.PNG) and single_page and target is FileType.PDF:
        return Operation.WRAP_IMAGE  # satır 4
    if kind is FileType.PDF and single_page and target is FileType.JPEG:
        if source.pages[0] in source.single_image_pages:
            return Operation.EXTRACT_IMAGE  # satır 5
        return Operation.RENDER_IMAGE  # satır 6
    return None  # satır 7


def _operation_source_text(source: OperationSource) -> str:
    kind = "biçimi tanınmadı" if source.kind is None else source.kind.value
    if not source.pages:
        return f"dosya {source.file_id} ({kind}, bütün dosya)"
    if source.whole:
        coverage = "dosyanın tüm sayfaları"
    elif source.contiguous:
        coverage = "dosyanın ardışık alt kümesi"
    else:
        coverage = "dosyanın ardışık olmayan alt kümesi"
    return f"{_pages_text(source.file_id, source.pages)} ({kind}, {coverage})"


# --- Direkt Belge (06.3.1, 06.3.2, §20.4) ------------------------------------------------------

# §20.4 `direct: true` sütunu: yalnız tek kaynağın sayfaları olduğu gibi alınır (K3).
DIRECT_OPERATIONS = frozenset({Operation.PASSTHROUGH, Operation.EXTRACT})


@dataclass(frozen=True, slots=True)
class DirectFileTypeMismatch:
    """§20.4.1 (06.3.2): Direkt Belge kaynağının biçimi türün `expected_file_types`'ında yok.

    İşlem seçilmez ve uygulanmaz; belge dönüştürülerek kurtarılmaz (K3), gerekçesiyle Unresolved'a
    gider. `received` beklenmeyen kaynakların biçimleridir (tanınmayan biçim `None`), kaynak
    sırasıyla ve tekrarsız. Gerekçe kişisel değer taşımaz.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED
    check: ClassVar[str] = "file_type"

    expected_file_types: tuple[FileType, ...]
    received: tuple[FileType | None, ...]

    @property
    def reason(self) -> str:
        expected = "/".join(file_type.value for file_type in self.expected_file_types)
        received = "/".join(
            "tanınmayan biçim" if file_type is None else file_type.value
            for file_type in self.received
        )
        return (
            f"Direkt Belge: beklenen dosya türü {expected}, gelen {received}. Uygun formatta "
            "yeniden gönderin."
        )


@dataclass(frozen=True, slots=True)
class DirectOperationForbidden:
    """§20.4 (06.3.1): seçilen işlem Direkt Belge türünde yasak.

    Birleştirme, sarma, gömülü görüntü çıkarma ve render belgeyi başka kaynaklardan kurar ya da
    biçimini değiştirir (K3); işlem uygulanmaz, belge gerekçesiyle Unresolved'a gider.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED
    check: ClassVar[str] = "operation"

    operation: Operation

    @property
    def reason(self) -> str:
        return f"Direkt Belge: {self.operation.value} bu tür için yapılamaz."


def check_direct_file_types(
    sources: Sequence[OperationSource], *, entry: CatalogEntry
) -> DirectFileTypeMismatch | None:
    """Direkt Belge format kontrolü (06.3.2, §20.4.1); işlem seçiminden önce yapılır.

    `direct: false` türde ya da her kaynağın içerikten tespit edilen biçimi (01.2.1) türün
    `expected_file_types`'ında olduğunda `None`. Tanınmayan biçim beklenen türlerden değildir. Saf
    işlevdir.
    """
    if not entry.direct:
        return None
    received: dict[FileType | None, None] = {}
    for source in sources:
        kind = None if source.kind is None else FileType(source.kind.value)
        if kind not in entry.expected_file_types:
            received[kind] = None
    if not received:
        return None
    return DirectFileTypeMismatch(entry.expected_file_types, tuple(received))


def check_direct_operation(
    operation: Operation, *, entry: CatalogEntry
) -> DirectOperationForbidden | None:
    """Direkt Belge izin matrisi (06.3.1, §20.4); §20.3'ün seçtiği işleme uygulanır.

    `direct: true` türde yalnız `passthrough` ve `extract` izinlidir. `direct: false` türde matris
    her işleme izin verir; dönüşümün türün `allowed_conversions`'ında olması 06.4.1'in kontrolüdür
    (`check_conversion`). Saf işlevdir.
    """
    if not entry.direct or operation in DIRECT_OPERATIONS:
        return None
    return DirectOperationForbidden(operation)


# --- dönüşüm izni (06.4.1, §20.3) --------------------------------------------------------------

# §20.3 satır 3–6'nın işlemleri; adları katalogdaki `Conversion` değerleridir (K12, D5).
CONVERSION_OPERATIONS = frozenset(
    {Operation.MERGE, Operation.WRAP_IMAGE, Operation.EXTRACT_IMAGE, Operation.RENDER_IMAGE}
)


@dataclass(frozen=True, slots=True)
class ConversionNotAllowed:
    """§20.3 (06.4.1): seçilen dönüşüm türün `allowed_conversions`'ında yok (K12).

    İşlem uygulanmaz ve başka bir satıra düşülmez; belge dönüştürülmez, gerekçesiyle Unresolved'a
    gider. `allowed_conversions` türün listesidir (boş olabilir). Gerekçe kişisel değer taşımaz.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED

    operation: Operation
    allowed_conversions: tuple[Conversion, ...]

    @property
    def reason(self) -> str:
        allowed = "/".join(conversion.value for conversion in self.allowed_conversions) or "boş"
        return (
            f"Dönüşüm izni yok (06.4.1): {self.operation.value} bu türün izinli dönüşümleri "
            f"arasında değil (allowed_conversions: {allowed}). Belge dönüştürülmez."
        )


def check_conversion(operation: Operation, *, entry: CatalogEntry) -> ConversionNotAllowed | None:
    """Dönüşüm izni kontrolü (06.4.1, §20.3); Direkt Belge matrisinden sonra uygulanır.

    `passthrough` ve `extract` dönüşüm değildir, her türde `None`. Satır 3–6'nın işlemi türün
    `allowed_conversions`'ında değilse ret. Saf işlevdir.
    """
    if operation not in CONVERSION_OPERATIONS:
        return None
    if Conversion(operation.value) in entry.allowed_conversions:
        return None
    return ConversionNotAllowed(operation, entry.allowed_conversions)


# --- plan üretimi (06.1.1) ---------------------------------------------------------------------


def create_plan(
    session: Session,
    layout: DataLayout,
    upload: Upload,
    *,
    catalog: Catalog,
    model: str | None = None,
    reference_date: date | None = None,
) -> Plan:
    """Partinin planını üretir, `plans` tablosuna dondurur ve `PLAN_CREATED` yazar (06.1.1).

    Kurallar modül açıklamasındadır. `catalog` güncel katalogdur (`export_catalog(session)`).
    `model` analizi yapan yapay zekâ modelidir (§8.5 `model`); plan üretimi yapay zekâ çağırmaz.
    `reference_date` MRZ doğum tarihinin yüzyılını seçer (§20.1.6); verilmezse partinin alındığı
    gündür (`uploads.created_at`, UTC) — saat plana girmez. Sürüm partinin son planının bir
    fazlasıdır (ilk plan 1). Olaylar (gruplama, eşleştirme, çalışan açma, `PLAN_CREATED`) partinin
    bağlamında yazılır; olay verisi kişisel değer taşımaz. Oturum commit edilmez.
    """
    session.flush()
    latest = session.scalar(select(func.max(Plan.version)).where(Plan.upload_id == upload.id))
    version = (latest or 0) + 1
    grouping = group_upload(session, upload, catalog=catalog, layout=layout)
    planner = _Planner(
        session,
        layout,
        upload,
        grouping,
        catalog=catalog,
        today=reference_date if reference_date is not None else upload.created_at.date(),
    )
    with event_context(upload_id=upload.id):
        document = PlanDocument(
            upload_id=upload.id, version=version, model=model, items=planner.items()
        )
        row = Plan(
            upload_id=upload.id,
            version=version,
            json=document.model_dump(mode="json"),
            model=model,
            plan_hash=document.plan_hash,
        )
        session.add(row)
        session.flush()
        routes = Counter(item.route.value for item in document.items)
        record_event(
            session,
            EventType.PLAN_CREATED,
            data={
                "plan_id": row.id,
                "version": version,
                "plan_hash": row.plan_hash,
                "model": model,
                "items": len(document.items),
                "routes": dict(sorted(routes.items())),
            },
        )
    return row


@dataclass(frozen=True, slots=True)
class _Verdict:
    """Öğeyi kuyruğa gönderen hüküm ve kişisel değer taşımayan gerekçesi."""

    queue: QueueKind
    reason: str


_NO_EMPLOYEE = PlanEmployee(action=EmployeeAction.NONE, employee_id=None, matched_by=None)
# Öğenin partideki yeri — (dosya, ilk sayfa); bütün dosyayı alan öğe -1'dedir — ve kurucusu.
_Subject = tuple[tuple[int, int], Callable[[str], PlanItem]]


class _Planner:
    """Tek planlamanın durumu: gruplama, katalog, referans gün ve dosya biçimi önbelleği."""

    def __init__(
        self,
        session: Session,
        layout: DataLayout,
        upload: Upload,
        grouping: UploadGrouping,
        *,
        catalog: Catalog,
        today: date,
    ) -> None:
        self._session = session
        self._layout = layout
        self._upload = upload
        self._grouping = grouping
        self._catalog = catalog
        self._today = today
        self._files = {upload_file.id: upload_file for upload_file in upload.files}
        self._blank_pages = {
            file_grouping.file_id: frozenset(file_grouping.blank_pages)
            for file_grouping in grouping.files
        }
        self._kinds: dict[int, FileKind | None] = {}

    def items(self) -> tuple[PlanItem, ...]:
        # Kararlar öğe sırasıyla verilir: yan etki (yeni çalışan) sonraki öğenin kararına girer.
        subjects = sorted(self._subjects(self._grouping), key=lambda subject: subject[0])
        return tuple(build(f"i{number}") for number, (_, build) in enumerate(subjects, start=1))

    def _subjects(self, grouping: UploadGrouping) -> Iterator[_Subject]:
        for candidate in grouping.candidates:
            first = candidate.pages[0]
            yield (first.file_id, first.index), partial(self._candidate_item, candidate=candidate)
        for file_grouping in grouping.files:
            yield from _page_subjects(file_grouping)
        attached = {attachment.file_id for attachment in grouping.attachments}
        for attachment in grouping.attachments:
            yield (attachment.file_id, -1), partial(self._attachment_item, attachment=attachment)
        for upload_file in self._upload.files:
            duplicate = upload_file.is_duplicate_of is not None
            if duplicate or (not upload_file.pages and upload_file.id not in attached):
                yield (upload_file.id, -1), partial(_file_item, upload_file=upload_file)

    # --- belge adayı --------------------------------------------------------------------------

    def _candidate_item(self, item_id: str, *, candidate: DocumentCandidate) -> PlanItem:
        # MRZ önce (K6, 05.3.3): okunaklılık kapısı ve kişi anahtarı MRZ'nin çözdüğü okumayı görür.
        candidate = replace(
            candidate, pages=tuple(self._mrz_resolved(page) for page in candidate.pages)
        )
        analyses = [page.analysis for page in candidate.pages]
        first = candidate.pages[0]
        key = build_person_key(analyses, today=self._today)
        match = match_employee(self._session, key, file_id=first.file_id, page_index=first.index)
        entry = self._entry(candidate)
        sources = tuple(
            PlanSource(
                file_id=file_id,
                pages=tuple(page.index for page in candidate.pages if page.file_id == file_id),
            )
            for file_id in candidate.file_ids
        )
        verdicts, selected = self._document_verdicts(candidate, entry, sources)
        if entry is None or verdicts:
            # Belge kabul edilmedi: eşleştirme hükmü yalnız kişi tahminidir, yan etki yok.
            guess = _verdict_of(match)
            if guess is not None:
                verdicts.append(guess)
            return self._item(item_id, sources, entry, _employee_guess(match), verdicts, None)
        employee, verdict = self._decide_employee(key, match, entry, analyses, first)
        verdicts = [] if verdict is None else [verdict]
        return self._item(item_id, sources, entry, employee, verdicts, selected)

    def _mrz_resolved(self, page: CandidatePage) -> CandidatePage:
        return replace(page, analysis=apply_mrz_priority(page.analysis, today=self._today).analysis)

    def _entry(self, candidate: DocumentCandidate) -> CatalogEntry | None:
        slug = candidate.document_type_slug
        if candidate.unknown_type is not None or slug is None:
            return None
        return self._catalog.get(slug)

    def _document_verdicts(
        self,
        candidate: DocumentCandidate,
        entry: CatalogEntry | None,
        sources: Sequence[PlanSource],
    ) -> tuple[list[_Verdict], SelectedOperation | None]:
        # Belge düzeyindeki hükümler (çalışan kararından önce) ve kabul edilen belgenin işlemi.
        unknown = candidate.unknown_type
        if unknown is not None:
            return [_Verdict(unknown.queue, unknown.reason)], None
        structural = [
            _Verdict(verdict.queue, verdict.reason)
            for verdict in (
                candidate.contiguity_violation,
                candidate.ambiguous_pairing,
                candidate.page_count_violation,
            )
            if verdict is not None
        ]
        if structural or entry is None:
            return structural, None
        check = check_legibility(candidate, catalog=self._catalog)
        gates = () if check is None else (check.illegible_fields, check.unmet_criteria)
        verdicts = [
            _Verdict(verdict.queue, verdict.reason) for verdict in gates if verdict is not None
        ]
        selected, refusal = self._operation(entry, sources)
        return [*verdicts, *refusal], selected

    def _decide_employee(
        self,
        key: PersonKey,
        match: EmployeeMatch,
        entry: CatalogEntry,
        analyses: Sequence[PageAnalysis],
        first: CandidatePage,
    ) -> tuple[PlanEmployee, _Verdict | None]:
        session = self._session
        if match.employee_id is not None:
            # §20.2.2 satır 1/3: yeni yazım, temiz numara ve iletişim bilgisi birikir.
            accumulate_identity(session, key, entry=entry)
            accumulate_contacts(session, match.employee_id, analyses)
            employee = PlanEmployee(
                action=EmployeeAction.MATCH,
                employee_id=match.employee_id,
                matched_by=match.matched_by,
            )
            return employee, None
        if match.rule is not MatchRule.NO_MATCH:
            # Çelişkili anahtar, belirsiz eşleşme, yalnız isim (satır 2, 4, 5).
            return _NO_EMPLOYEE, _verdict_of(match)
        resolution = resolve_unmatched(key, match, entry=entry)
        if resolution.rule is UnmatchedRule.CREATE:
            created = create_employee(
                session,
                self._layout,
                key,
                entry=entry,
                file_id=first.file_id,
                page_index=first.index,
            )
            accumulate_contacts(session, created.id, analyses)
            employee = PlanEmployee(
                action=EmployeeAction.CREATE, employee_id=created.id, matched_by=None
            )
            return employee, None
        if resolution.rule is UnmatchedRule.PENDING_PROFILE:
            propose_pending_profile(
                session, key, entry=entry, file_id=first.file_id, page_index=first.index
            )
        employee = PlanEmployee(action=resolution.action, employee_id=None, matched_by=None)
        return employee, _verdict_of(resolution)

    def _item(
        self,
        item_id: str,
        sources: tuple[PlanSource, ...],
        entry: CatalogEntry | None,
        employee: PlanEmployee,
        verdicts: Sequence[_Verdict],
        selected: SelectedOperation | None,
    ) -> PlanItem:
        slug = None if entry is None else entry.slug
        if verdicts or entry is None or selected is None or employee.employee_id is None:
            return _queued_item(item_id, slug, sources, employee, verdicts)
        owner = self._session.get_one(Employee, employee.employee_id)
        stem = document_stem(owner.given_names, owner.surname, entry.file_label)
        return PlanItem(
            item_id=item_id,
            document_type_slug=slug,
            sources=sources,
            operation=selected.operation,
            target_format=selected.target_format,
            target_name=sequenced_filename(stem, 1, selected.target_format.value),
            employee=employee,
            route=Route.READY,
            route_reason=None,
            validations=(),
        )

    # --- Word/Excel eki -----------------------------------------------------------------------

    def _attachment_item(self, item_id: str, *, attachment: AttachmentFile) -> PlanItem:
        sources = (PlanSource(file_id=attachment.file_id, pages=()),)
        entry = self._catalog.get(attachment.document_type_slug)
        selected, verdicts = self._operation(entry, sources)
        unresolved = attachment.unresolved
        if unresolved is not None:
            # Bağlam çalışanı olmadan yüklenen ekin sahibi belirsizdir.
            verdicts.append(_Verdict(unresolved.queue, unresolved.reason))
            return self._item(item_id, sources, entry, _NO_EMPLOYEE, verdicts, selected)
        # Sahibi partinin bağlam çalışanıdır (`unresolved` boşsa doludur); belge kimliğiyle
        # eşleştirilmedi, `matched_by` boş kalır.
        owner = self._upload.context_employee_id
        employee = PlanEmployee(action=EmployeeAction.MATCH, employee_id=owner, matched_by=None)
        return self._item(item_id, sources, entry, employee, verdicts, selected)

    # --- işlem --------------------------------------------------------------------------------

    def _operation(
        self, entry: CatalogEntry, sources: Sequence[PlanSource]
    ) -> tuple[SelectedOperation | None, list[_Verdict]]:
        # Direkt Belge format kontrolü (06.3.2) → §20.3 → Direkt Belge matrisi (06.3.1) → dönüşüm
        # izni (06.4.1). İlk ret sonraki adımı keser: işlem yok ve belgeyi Unresolved'a gönderen
        # tek hüküm.
        operation_sources = [self._operation_source(source) for source in sources]
        mismatch = check_direct_file_types(operation_sources, entry=entry)
        if mismatch is not None:
            self._record_direct_refusal(entry, operation_sources, mismatch, operation=None)
            return None, [_Verdict(mismatch.queue, mismatch.reason)]
        selection = select_operation(operation_sources, output_format=entry.output_format)
        if isinstance(selection, NoApplicableOperation):
            return None, [_Verdict(selection.queue, selection.reason)]
        forbidden = check_direct_operation(selection.operation, entry=entry)
        if forbidden is not None:
            self._record_direct_refusal(
                entry, operation_sources, forbidden, operation=selection.operation
            )
            return None, [_Verdict(forbidden.queue, forbidden.reason)]
        not_allowed = check_conversion(selection.operation, entry=entry)
        if not_allowed is not None:
            return None, [_Verdict(not_allowed.queue, not_allowed.reason)]
        return selection, []

    def _record_direct_refusal(
        self,
        entry: CatalogEntry,
        sources: Sequence[OperationSource],
        refusal: DirectFileTypeMismatch | DirectOperationForbidden,
        *,
        operation: Operation | None,
    ) -> None:
        # §20.4: ret `DIRECT_DOC_CHECK`'e adayın ilk sayfasıyla (ekte dosyayla) yazılır.
        first = sources[0]
        record_event(
            self._session,
            EventType.DIRECT_DOC_CHECK,
            file_id=first.file_id,
            page_index=first.pages[0] if first.pages else None,
            message=refusal.reason,
            data={
                "document_type_slug": entry.slug,
                "check": refusal.check,
                "operation": None if operation is None else operation.value,
                "expected_file_types": [file_type.value for file_type in entry.expected_file_types],
                "file_types": [
                    None if source.kind is None else source.kind.value for source in sources
                ],
                "queue": refusal.queue.value,
            },
        )

    def _operation_source(self, source: PlanSource) -> OperationSource:
        upload_file = self._files[source.file_id]
        pages = upload_file.pages
        return OperationSource(
            file_id=source.file_id,
            kind=self._file_kind(source.file_id),
            pages=source.pages,
            # Satırı açılmamış sayfa da dosyanındır: kapsamayı alt kümeye çevirir.
            file_pages=frozenset(page.index for page in pages).union(
                range(upload_file.page_count or 0)
            ),
            blank_pages=self._blank_pages.get(source.file_id, frozenset()),
            single_image_pages=frozenset(
                page.index for page in pages if page.has_single_embedded_image
            ),
        )

    def _file_kind(self, file_id: int) -> FileKind | None:
        # Biçim içerikten okunur (01.2.1); istemcinin bildirdiği `mime`'a güvenilmez.
        if file_id not in self._kinds:
            upload_file = self._files[file_id]
            content = self._layout.resolve(upload_file.stored_path).read_bytes()
            try:
                self._kinds[file_id] = detect_file_kind(content)
            except UnsupportedFileTypeError:
                self._kinds[file_id] = None
        return self._kinds[file_id]


def _verdict_of(decision: EmployeeMatch | UnmatchedResolution) -> _Verdict | None:
    # Çalışan kararı belgeyi kuyruğa gönderiyorsa hüküm; Hazir'a giden kararda `None`.
    if decision.queue is None or decision.reason is None:
        return None
    return _Verdict(decision.queue, decision.reason)


def _employee_guess(match: EmployeeMatch) -> PlanEmployee:
    # Kuyruğa giden belgenin kişi tahmini (08.1.2): yalnız satır 1/3'ün çalışanı.
    if match.employee_id is None:
        return _NO_EMPLOYEE
    return PlanEmployee(
        action=EmployeeAction.MATCH, employee_id=match.employee_id, matched_by=match.matched_by
    )


def _queued_item(
    item_id: str,
    slug: str | None,
    sources: tuple[PlanSource, ...],
    employee: PlanEmployee,
    verdicts: Sequence[_Verdict],
) -> PlanItem:
    return PlanItem(
        item_id=item_id,
        document_type_slug=slug,
        sources=sources,
        operation=None,
        target_format=None,
        target_name=None,
        employee=employee,
        route=Route(verdicts[0].queue.value),
        route_reason=" ".join(verdict.reason for verdict in verdicts),
        validations=(),
    )


_BLANK_PAGES_REASON = "Boş sayfa ({pages}): atlanır; çıktıya ve kuyruğa girmez, hata sayılmaz."
_UNANALYZED_PAGES_REASON = (
    "Analizi yapılamamış sayfa ({pages}): içeriği bilinmediği için hiçbir belgeye katılmaz ve "
    "çıktı üretmez (R7); yeniden analizle değerlendirilir."
)


def _page_subjects(grouping: FileGrouping) -> Iterator[_Subject]:
    # Adaya girmeyen sayfalar: boş sayfa atlanır (S8), analizi olmayan sayfa kuyruğa gider (R7).
    file_id = grouping.file_id
    for pages, route, reason in (
        (grouping.blank_pages, Route.SKIP, _BLANK_PAGES_REASON),
        (grouping.unanalyzed_pages, Route.UNRESOLVED, _UNANALYZED_PAGES_REASON),
    ):
        if pages:
            ordered = tuple(sorted(pages))
            build = partial(
                _unowned_item,
                file_id=file_id,
                pages=ordered,
                route=route,
                reason=reason.format(pages=_pages_text(file_id, ordered)),
            )
            yield (file_id, ordered[0]), build


def _file_item(item_id: str, *, upload_file: UploadFile) -> PlanItem:
    # Bütün olarak ele alınan dosya: tekrar yükleme ya da sayfası üretilmemiş, tanınmayan dosya.
    if upload_file.is_duplicate_of is not None:
        route = Route.SKIP
        reason = (
            f"Tekrar yükleme (01.4.1): dosya {upload_file.id}, daha önce yüklenen dosya "
            f"{upload_file.is_duplicate_of} ile aynı içerikte; yeniden işlenmez, çıktı üretmez."
        )
    else:
        route = Route.UNRESOLVED
        reason = (
            f"İşlenemeyen dosya (dosya {upload_file.id}): sayfası üretilmemiş ve Word/Excel eki "
            "olarak tanınmadı; çıktı üretmez (R7)."
        )
    return _unowned_item(item_id, file_id=upload_file.id, pages=(), route=route, reason=reason)


def _unowned_item(
    item_id: str, *, file_id: int, pages: tuple[int, ...], route: Route, reason: str
) -> PlanItem:
    return PlanItem(
        item_id=item_id,
        document_type_slug=None,
        sources=(PlanSource(file_id=file_id, pages=pages),),
        operation=None,
        target_format=None,
        target_name=None,
        employee=_NO_EMPLOYEE,
        route=route,
        route_reason=reason,
        validations=(),
    )


def _pages_text(file_id: int, pages: Iterable[int]) -> str:
    # Sayfa numarası kullanıcının gördüğü gibi 1'den başlar.
    return f"dosya {file_id}, sayfa " + ", ".join(str(index + 1) for index in pages)
