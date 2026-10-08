"""Validated JSON contracts and immutable plan data models (PRD §8.5)."""

from __future__ import annotations

import enum
import json
from collections.abc import Iterable
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

from app.catalog import FileType
from app.catalog.schema import Slug, Text
from app.db.models import Document, Plan
from app.matching.match import EmployeeAction, MatchedBy
from app.pipeline.validate import ValidationName
from app.storage import sha256_bytes


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

UploadId = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
]

ModelName = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]

FileId = Annotated[StrictInt, Field(ge=1)]

PageIndex = Annotated[StrictInt, Field(ge=0)]

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
    yalnız `match`'te dolabilir (bağlam çalışanına verilen Word/Excel ekinde ve sahibini aynı
    dosyadan alan kişisiz belgede — D29 — boştur).
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
    """Plan JSON `validations` satırı (§8.5): doğrulayıcının adı (06.5.1) ve sonucu."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: ValidationName
    ok: StrictBool


_VALIDATION_ORDER = tuple(ValidationName)


class PlanItem(BaseModel):
    """Planın tek öğesi (§8.5): kaynak, işlem, hedef, çalışan, rota ve doğrulamalar.

    `hazir` öğenin çalışanı (`match`/`create`), işlemi ve hedefi vardır, gerekçesi yoktur ve
    doğrulanmıştır (`validations` dolu, hepsi `ok` — 06.5.2); kuyruğa ya da atlamaya giden öğenin
    gerekçesi zorunludur, işlemi ve hedefi yoktur — uygulanmayacak işlem plana girmez.
    `target_name`'in uzantısı `target_format`'tır. Doğrulamalar tekrarsız ve 06.5.1 sırasıyladır.
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
        names = [validation.name for validation in self.validations]
        if names != sorted(set(names), key=_VALIDATION_ORDER.index):
            raise ValueError("validations tekrarsız ve 06.5.1 sırasıyla olmalı")
        if self.route is Route.READY:
            if self.route_reason is not None:
                raise ValueError("hazir öğede route_reason boş olmalı")
            if self.employee.employee_id is None:
                raise ValueError("hazir öğenin çalışanı olmalı (match veya create, R7)")
            if self.operation is None:
                raise ValueError("hazir öğede operation zorunlu (06.2.1)")
            if self.target_name is None:
                raise ValueError("hazir öğede target_format ve target_name zorunlu")
            if not self.validations or not all(validation.ok for validation in self.validations):
                raise ValueError(
                    "hazir öğe doğrulanmış olmalı: validations dolu ve hepsi ok (06.5.2)"
                )
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


def name_matched_documents(documents: Iterable[Document]) -> frozenset[int]:
    """Belgelerden planın satır 5a isim eşleşmesiyle (`matched_by: name`, 05.5.4) bugünkü sahibinin
    Hazir'ına yerleştirdiklerinin kimlikleri.

    Belgenin öğesi planı (`documents.plan_id`) ve kökeniyle (`source_refs_json` öğenin `sources`'u,
    `app.pipeline.execute.executed_document` gibi) bulunur. Öğe Hazir'a gitmiş, `matched_by: name`
    taşıyor ve çalışanı belgenin bugünkü sahibi olmalıdır: kuyruktan atanan (kişi tahmini isimle
    olsa da), İK'nın başka çalışana taşıdığı ya da birleştirmeyle kalan kayda geçen belge isimle
    yerleşmiş sayılmaz — sahibini İK belirledi. Planı olmayan ya da sözleşmeye uymayan (K9) belge
    sayılmaz. Her plan bir kez okunur; veritabanına yazılmaz.
    """
    plans: dict[int, PlanDocument | None] = {}
    matched: set[int] = set()
    for document in documents:
        plan_id = document.plan_id
        if plan_id is None:
            continue
        if plan_id not in plans:
            try:
                plans[plan_id] = None if document.plan is None else read_plan(document.plan)
            except PlanIntegrityError:
                plans[plan_id] = None
        plan = plans[plan_id]
        if plan is not None and any(_placed_by_name(item, document) for item in plan.items):
            matched.add(document.id)
    return frozenset(matched)


def _placed_by_name(item: PlanItem, document: Document) -> bool:
    employee = item.employee
    return (
        item.route is Route.READY
        and employee.matched_by is MatchedBy.NAME
        and employee.employee_id == document.employee_id
        and [source.model_dump(mode="json") for source in item.sources] == document.source_refs_json
    )
