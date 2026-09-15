"""Plan JSON üretimi ve belirleyicilik — PRD 06.1.1, 06.1.2 (§8.5; K9, R10, R7).

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
   `unresolved`. Yapısal hükümlü aday eksik ya da parça bir belgedir: okunaklılık kapısı ona
   uygulanmaz (yalnız arka yüzden oluşan parça "okunamayan alanlar" almaz).
3. Okunaklılık kapısı (04.4) — zorunlu alan okunmuyorsa `unreadable`, kabul kriteri karşılanmıyorsa
   `unresolved`. MRZ önceliği (05.3.3) kapıdan ve kişi anahtarından önce her sayfaya uygulanır.
4. Çalışan kararı (§20.2.2).

Hiçbir hüküm yoksa rota `hazir`dır.

**Çalışan.** Her analizli adayın kişi anahtarı (05.4) kayıtlı çalışanlarla eşleştirilir (05.5).
Kararın yan etkileri yalnız belge düzeyinde kabul edilen adayda (1–3'te hükmü olmayan) yürür:
satır 1/3 eşleşmesinde yeni isim yazımı, temiz numara ve iletişim bilgisi çalışana eklenir (05.7.2,
05.8); eşleşme yoksa satır 6'da çalışan açılır (05.6), satır 7'de profil onaya önerilir (05.7.1),
satır 8 ve tablo dışı eksik kişi Unresolved'a gider. Kuyruğa giden adaydan çalışan açılmaz, profil
önerilmez, kimlik ya da iletişim bilgisi birikmez — yapısı veya okunaklılığı kabul edilmemiş
belgenin okumasına güvenilmez. Eşleştirme hükmü o adayda yalnız kişi tahmini olarak kalır
(08.1.2): satır 1/3'te `match` ve çalışan, öteki hükümlerde `none`; eşleştirme hükmü de kuyruğa
gönderiyorsa (satır 2, 4, 5, çelişkili anahtar) gerekçesi eklenir. Word/Excel ekinin sahibi partinin
bağlam çalışanıdır (`match`, `matched_by: null`); bağlam yoksa ek Unresolved'a gider (04.7.1).

**Hedef.** Yalnız `hazir` öğede dolar. `target_format` türün `output_format`'ıdır; `keep` kaynak
dosyaların içeriğinden tespit edilen biçimdir, kaynaklar farklı biçimdeyse boş kalır. `target_name`
çalışan kaydının ad-soyadı ve türün `file_label`'ıyla K8 adıdır (`Ad_Soyad-Passport.pdf`); sıra eki
(`-2`) plana girmez, yazma anında diskte seçilir (00.4.3, 07.7). `operation` bu adımda boştur —
işlem seçimi 06.2'nin (§20.3); `validations` 06.5'in.

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
from typing import Annotated

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
from app.catalog import Catalog, CatalogEntry, FileType, OutputFormat
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
    """Plan JSON `operation` (§8.5); seçimi §20.3'e göre 06.2'nindir."""

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

    `hazir` öğenin çalışanı vardır (`match`/`create`) ve gerekçesi yoktur; kuyruğa ya da atlamaya
    giden öğenin gerekçesi zorunludur, hedefi yoktur. `target_name`'in uzantısı `target_format`'tır.
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
        else:
            if self.route_reason is None:
                raise ValueError("hazir olmayan öğede route_reason zorunlu")
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
        catalog=catalog,
        today=reference_date if reference_date is not None else upload.created_at.date(),
    )
    with event_context(upload_id=upload.id):
        document = PlanDocument(
            upload_id=upload.id, version=version, model=model, items=planner.items(grouping)
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
    """Tek planlamanın durumu: katalog, referans gün ve dosya biçimi önbelleği."""

    def __init__(
        self,
        session: Session,
        layout: DataLayout,
        upload: Upload,
        *,
        catalog: Catalog,
        today: date,
    ) -> None:
        self._session = session
        self._layout = layout
        self._upload = upload
        self._catalog = catalog
        self._today = today
        self._files = {upload_file.id: upload_file for upload_file in upload.files}
        self._kinds: dict[int, FileKind | None] = {}

    def items(self, grouping: UploadGrouping) -> tuple[PlanItem, ...]:
        # Kararlar öğe sırasıyla verilir: yan etki (yeni çalışan) sonraki öğenin kararına girer.
        subjects = sorted(self._subjects(grouping), key=lambda subject: subject[0])
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
        verdicts = self._document_verdicts(candidate)
        if entry is None or verdicts:
            # Belge kabul edilmedi: eşleştirme hükmü yalnız kişi tahminidir, yan etki yok.
            guess = _verdict_of(match)
            if guess is not None:
                verdicts.append(guess)
            return self._item(item_id, candidate, entry, _employee_guess(match), verdicts)
        employee, verdict = self._decide_employee(key, match, entry, analyses, first)
        return self._item(item_id, candidate, entry, employee, [] if verdict is None else [verdict])

    def _mrz_resolved(self, page: CandidatePage) -> CandidatePage:
        return replace(page, analysis=apply_mrz_priority(page.analysis, today=self._today).analysis)

    def _entry(self, candidate: DocumentCandidate) -> CatalogEntry | None:
        slug = candidate.document_type_slug
        if candidate.unknown_type is not None or slug is None:
            return None
        return self._catalog.get(slug)

    def _document_verdicts(self, candidate: DocumentCandidate) -> list[_Verdict]:
        unknown = candidate.unknown_type
        if unknown is not None:
            return [_Verdict(unknown.queue, unknown.reason)]
        structural = [
            _Verdict(verdict.queue, verdict.reason)
            for verdict in (
                candidate.contiguity_violation,
                candidate.ambiguous_pairing,
                candidate.page_count_violation,
            )
            if verdict is not None
        ]
        if structural:
            return structural
        check = check_legibility(candidate, catalog=self._catalog)
        gates = () if check is None else (check.illegible_fields, check.unmet_criteria)
        return [_Verdict(verdict.queue, verdict.reason) for verdict in gates if verdict is not None]

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
        candidate: DocumentCandidate,
        entry: CatalogEntry | None,
        employee: PlanEmployee,
        verdicts: Sequence[_Verdict],
    ) -> PlanItem:
        file_ids = candidate.file_ids
        sources = tuple(
            PlanSource(
                file_id=file_id,
                pages=tuple(page.index for page in candidate.pages if page.file_id == file_id),
            )
            for file_id in file_ids
        )
        slug = None if entry is None else entry.slug
        if verdicts or entry is None or employee.employee_id is None:
            return _queued_item(item_id, slug, sources, employee, verdicts)
        target_format, target_name = self._target(entry, employee.employee_id, file_ids)
        return PlanItem(
            item_id=item_id,
            document_type_slug=slug,
            sources=sources,
            operation=None,
            target_format=target_format,
            target_name=target_name,
            employee=employee,
            route=Route.READY,
            route_reason=None,
            validations=(),
        )

    # --- Word/Excel eki -----------------------------------------------------------------------

    def _attachment_item(self, item_id: str, *, attachment: AttachmentFile) -> PlanItem:
        sources = (PlanSource(file_id=attachment.file_id, pages=()),)
        slug = attachment.document_type_slug
        unresolved = attachment.unresolved
        if unresolved is not None:
            # Bağlam çalışanı olmadan yüklenen ekin sahibi belirsizdir.
            verdict = _Verdict(unresolved.queue, unresolved.reason)
            return _queued_item(item_id, slug, sources, _NO_EMPLOYEE, [verdict])
        # Sahibi partinin bağlam çalışanıdır (`unresolved` boşsa doludur); belge kimliğiyle
        # eşleştirilmedi, `matched_by` boş kalır.
        owner = self._upload.context_employee_id
        employee = PlanEmployee(action=EmployeeAction.MATCH, employee_id=owner, matched_by=None)
        entry = self._catalog.get(slug)
        target_format, target_name = self._target(entry, owner, (attachment.file_id,))
        return PlanItem(
            item_id=item_id,
            document_type_slug=slug,
            sources=sources,
            operation=None,
            target_format=target_format,
            target_name=target_name,
            employee=employee,
            route=Route.READY,
            route_reason=None,
            validations=(),
        )

    # --- hedef --------------------------------------------------------------------------------

    def _target(
        self, entry: CatalogEntry, employee_id: str, file_ids: Iterable[int]
    ) -> tuple[FileType | None, str | None]:
        target_format = self._target_format(entry, file_ids)
        if target_format is None:
            return None, None
        owner = self._session.get_one(Employee, employee_id)
        stem = document_stem(owner.given_names, owner.surname, entry.file_label)
        return target_format, sequenced_filename(stem, 1, target_format.value)

    def _target_format(self, entry: CatalogEntry, file_ids: Iterable[int]) -> FileType | None:
        if entry.output_format is not OutputFormat.KEEP:
            return FileType(entry.output_format.value)
        kinds = {self._file_kind(file_id) for file_id in file_ids}
        if len(kinds) != 1:
            return None
        (kind,) = kinds
        return None if kind is None else FileType(kind.value)

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
