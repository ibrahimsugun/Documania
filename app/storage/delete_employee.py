"""Pasif çalışanı kalıcı silme — PRD 10.5.13 (R11, K8, K9, K10, K15, K16; PLAN.md §D110, §D116).

İşten ayrılan, pasife alınmış (10.5.7) çalışanı İK iki aşamalı onayla (K16, §20.6 "Çalışanı kalıcı
sil") bütün belgeleriyle siler. Sistem kendiliğinden silmez (R11); etkin, birleştirilmiş ve zaten
silinmiş kayıt silinmez (`EmployeeNotDeletableError`). Geri alma yoktur. Belge silmenin (10.5.12,
`app.storage.delete`) iki adımı aynıdır:

1. `delete_employee` yalnız veritabanını değiştirir, commit etmez:

   - **Belgeler** (etkin, arşivdeki, eski sürüm) `deleted` iskeletine döner; hangi dosyanın gidip
     hangisinin kalacağı belge silmenin ölçütleridir, ama belgeler **birlikte** planlanır
     (`plan_documents_files`): çalışanın kendi belgeleri birbirinin orijinalini tutmaz. Başka
     çalışana ya da açık kuyruk öğesine kaynak olan orijinal ve sayfa kalır (K10, ortak yükleme).
     Orijinali giden dosyanın bütün sayfaları (belgeye girmeyen boş sayfa dahil) boşalır.
   - **Alt kayıtlar** (`employee_aliases`, `employee_identifiers`, `employee_contacts`,
     `employee_field_observations`, `employee_packages`) satır olarak silinir.
   - **Planlar (K9):** bu çalışana yerleştirilmiş plan öğelerinin hedef adı (K8 adı kişi adı taşır)
     `deleted-<öğe>.<biçim>` olur ve planın hash'i yeniden hesaplanır — saklanan plan okunmaya
     (`read_plan`) devam eder; silinen belgeye dayanan öğe yeniden çalıştırmada üretilmez
     (`OUTPUT_SKIPPED`, `reason: deleted`; 10.5.12).
   - **Olaylar (K15):** satır silinmez. Bu çalışanın olaylarının mesajı "<tür> — silinmiş çalışan"
     olur; verisinden `PERSONAL_DATA_KEYS` anahtarları her derinlikte çıkar. Ayrıca bu çalışanın,
     belgelerinin, kaynak dosyalarının ve partilerinin olaylarında kişinin değerlerini (ad, soyad,
     yazımları, klasör adı, doğum tarihi, belge numaraları, iletişim bilgileri) taşıyan dizgeler
     atılır, böyle bir mesaj genel metne çevrilir.
   - **Çalışan satırı** `deleted` iskeletine döner: E numarası, oluşturma anı, `deleted_at`,
     `deleted_by` kalır; ad, soyad, diğer isimler, orijinal yazım, doğum tarihi, uyruk boşalır,
     klasör adı `deleted_<E>` olur. E numarası yeniden verilmez: `allocate_employee_number` en büyük
     numarayı iskelet dahil sayar (K8).
   - Bu çalışana `merged_into_id` ile bağlı birleştirilmiş kayıtlar (10.5.9) aynı kişidir:
     klasörleri ve `profil.md`'leri de kişinin adını taşır; birlikte silinir (PLAN.md §D116 b).
   - `EMPLOYEE_DELETED` kullanıcı adıyla ve yalnız sayılarla yazılır (§8.3).

2. Çağıran commit eder, sonra `remove_employee_files` planlanan dosyaları ve çalışan klasörlerini
   (`Hazir`, `Alinan`, `profil.md`) diskten kaldırır. Kaldırılamayan dosya geri sarmaz: sayısı
   olayın verisine `files_failed` olarak eklenir, logda yol yazılmaz (yol kişi adı taşır).

Erişim logu satırları (10.9.2), yüklemenin bağlam çalışanı ve belge iskeletleri kalır: hepsi yalnız
kimlik taşır. Kabul edilmiş fotoğraf örnekleri (11.8.1) saklanmaz, her okumada etkin belgelerden
çıkarılır; belgeler silinince kendiliğinden kalkar.
"""

from __future__ import annotations

import logging
import re
import shutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeAlias,
    EmployeeContact,
    EmployeeFieldObservation,
    EmployeeIdentifier,
    EmployeePackage,
    EmployeeStatus,
    Event,
    Page,
    Plan,
    UploadFile,
    utcnow,
)
from app.events import PERSONAL_DATA_KEYS, EventType, record_event
from app.storage.delete import (
    FileRole,
    PlannedFile,
    PlannedPage,
    _refs,
    plan_documents_files,
)
from app.storage.layout import DataLayout

logger = logging.getLogger(__name__)

# Silinen çalışanın iskelet klasör adı: benzersiz kalır, kişi adı taşımaz (§D110 a).
DELETED_FOLDER_PREFIX = "deleted_"
# Bu çalışanın olaylarının yeni mesajı (§D110 d); kaynak dildedir, olay verisi gibi çevrilmez.
DELETED_EMPLOYEE_MESSAGE = "{type} — silinmiş çalışan"
# Plan öğesinin temizlenmiş hedef adı; `TargetName` desenine uyar.
DELETED_TARGET_NAME = "deleted-{item_id}.{format}"
# Kişinin değerini dizgede ararken tek başına kullanılmayacak kadar kısa sözcükler.
_MIN_TOKEN_LENGTH = 3
_WORDS = re.compile(r"[\s_\-,./()]+")


class EmployeeNotFoundError(LookupError):
    """10.5.13: çalışan yok; hiçbir şey değişmedi."""


class EmployeeNotDeletableError(ValueError):
    """10.5.13: yalnız pasif çalışan kalıcı silinir; etkin, birleştirilmiş ya da zaten silinmiş
    kayıt silinmez. Hiçbir şey değişmedi."""


class EmployeeDeletionChangedError(ValueError):
    """10.5.13: ikinci onaydan sonra silinecek belge sayısı değişti; hiçbir şey değişmedi, onay
    yeniden istenir."""

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"Silinecek belge sayısı onaydan sonra değişti: {expected} → {actual}")
        self.expected = expected
        self.actual = actual


@dataclass(frozen=True, slots=True)
class EmployeeDeletionPlan:
    """`plan_employee_deletion` sonucu: silinecek kayıtlar, belgeler, dosyalar ve klasörler."""

    employee_id: str
    # Çalışan ve ona birleştirilmiş kayıtlar (10.5.9), E numarası sırasıyla.
    people: tuple[str, ...]
    documents: tuple[int, ...]
    remove: tuple[PlannedFile, ...]
    keep: tuple[PlannedFile, ...]
    pages: tuple[PlannedPage, ...]
    folders: tuple[Path, ...]

    @property
    def document_count(self) -> int:
        """İkinci onay metninin `<N>`'si: silinecek belge sayısı."""
        return len(self.documents)


@dataclass(frozen=True, slots=True)
class DeletedEmployee:
    """`delete_employee` sonucu: iskelete dönen satır, uygulanan plan ve olay."""

    employee: Employee
    plan: EmployeeDeletionPlan
    event: Event


def check_employee_deletable(employee: Employee) -> None:
    """Yalnız pasif (`inactive`) çalışan silinir; aksi `EmployeeNotDeletableError`."""
    if employee.status != EmployeeStatus.INACTIVE.value:
        raise EmployeeNotDeletableError(
            f"Çalışan {employee.id} kalıcı silinmez: durum {employee.status!r} "
            "(yalnız pasif çalışan silinir)"
        )


def plan_employee_deletion(
    session: Session, layout: DataLayout, employee: Employee
) -> EmployeeDeletionPlan:
    """Çalışanı silmek neyi kaldırır, neyi bırakır (modül açıklaması). Hiçbir şey yazmaz; durum
    denetimi `check_employee_deletable`'dadır."""
    people = _people(session, employee)
    ids = [person.id for person in people]
    documents = list(
        session.scalars(
            select(Document)
            .where(
                Document.employee_id.in_(ids),
                Document.status != DocumentStatus.DELETED.value,
            )
            .order_by(Document.id)
        )
    )
    remove, keep, pages = plan_documents_files(session, layout, documents, clear_gone_files=True)
    folders = tuple(
        folder
        for folder in (_employee_dir(layout, person.folder_name) for person in people)
        if folder is not None
    )
    return EmployeeDeletionPlan(
        employee_id=employee.id,
        people=tuple(ids),
        documents=tuple(document.id for document in documents),
        remove=remove,
        keep=keep,
        pages=pages,
        folders=folders,
    )


def delete_employee(
    session: Session,
    layout: DataLayout,
    employee_id: str,
    *,
    actor: str,
    expected_documents: int | None = None,
    now: datetime | None = None,
) -> DeletedEmployee:
    """Pasif çalışanı kalıcı siler — veritabanı adımı (modül açıklaması, adım 1); commit etmez.

    `actor` iki aşamalı onayı tamamlamış kullanıcının adıdır; boşsa `ValueError`. Çalışan yoksa
    `EmployeeNotFoundError`, pasif değilse `EmployeeNotDeletableError`; `expected_documents` ikinci
    onayda gösterilen `<N>`'dir ve işlem anındaki plan başka sayı veriyorsa
    `EmployeeDeletionChangedError`. Üçünde de hiçbir şey yazılmaz. Dosyalar commit'ten sonra
    `remove_employee_files` ile kaldırılır.
    """
    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")
    employee = session.get(Employee, employee_id, with_for_update=True, populate_existing=True)
    if employee is None:
        raise EmployeeNotFoundError(f"Çalışan bulunamadı: {employee_id}")
    check_employee_deletable(employee)
    plan = plan_employee_deletion(session, layout, employee)
    if expected_documents is not None and expected_documents != plan.document_count:
        raise EmployeeDeletionChangedError(expected_documents, plan.document_count)

    deleted_at = now or utcnow()
    people = [session.get_one(Employee, person_id) for person_id in plan.people]
    pattern = _person_pattern(session, people)

    events_cleaned = _clean_events(session, plan, pattern)
    plans_cleaned = _clean_plans(session, plan)

    for document_id in plan.documents:
        document = session.get_one(Document, document_id)
        document.status = DocumentStatus.DELETED.value
        document.path = None
        document.deleted_at = deleted_at
        document.deleted_by = actor
    for planned in plan.pages:
        page = session.get_one(Page, planned.page_id)
        page.image_path = None
        page.analysis_json = None
        page.text_layer = None

    records = 0
    for model in (
        EmployeeAlias,
        EmployeeIdentifier,
        EmployeeContact,
        EmployeeFieldObservation,
    ):
        records += _delete_rows(session, model, plan.people)
    packages = _delete_rows(session, EmployeePackage, plan.people)

    for person in people:
        person.status = EmployeeStatus.DELETED.value
        person.given_names = ""
        person.surname = ""
        person.other_names = None
        person.original_script_name = None
        person.date_of_birth = None
        person.nationality = None
        person.folder_name = f"{DELETED_FOLDER_PREFIX}{person.id}"
        person.deleted_at = deleted_at
        person.deleted_by = actor
    session.flush()

    event = record_event(
        session,
        EventType.EMPLOYEE_DELETED,
        employee_id=employee.id,
        actor=actor,
        data={
            "documents": len(plan.documents),
            "files_deleted": len(plan.remove),
            "files_kept": len(plan.keep),
            "pages_cleared": len(plan.pages),
            "records": records,
            "packages": packages,
            "merged_records": len(plan.people) - 1,
            "plans_cleaned": plans_cleaned,
            "events_cleaned": events_cleaned,
        },
    )
    return DeletedEmployee(employee, plan, event)


def remove_employee_files(session: Session, deleted: DeletedEmployee) -> int:
    """Commit edilmiş silmenin dosyalarını ve çalışan klasörlerini diskten kaldırır (modül
    açıklaması, adım 2). Kaldırılamayan dosya sayılır, loglanır ve olayın verisine `files_failed`
    olarak eklenir; hiçbir şey geri sarılmaz. Kaldırılamayan dosya sayısını döndürür; olay
    değiştiyse çağıran commit eder."""
    planned = [
        *deleted.plan.remove,
        *(
            PlannedFile(FileRole.PAGE_IMAGE, page.image)
            for page in deleted.plan.pages
            if page.image is not None
        ),
    ]
    failed = 0
    for target in planned:
        try:
            target.path.unlink(missing_ok=True)
        except OSError as exc:
            failed += 1
            _log_failure(deleted, target.role.value, exc)
    errors: list[BaseException] = []
    for folder in deleted.plan.folders:
        shutil.rmtree(folder, onexc=lambda _func, _path, exc: errors.append(exc))
    failed += len(errors)
    for exc in errors:
        _log_failure(deleted, "employee_folder", exc)
    if failed:
        event = deleted.event
        event.data_json = {**(event.data_json or {}), "files_failed": failed}
        session.flush()
    return failed


# --- yardımcılar --------------------------------------------------------------------------------


def _log_failure(deleted: DeletedEmployee, role: str, exc: BaseException) -> None:
    logger.warning(
        "Çalışan %s kalıcı silindi ama bir %s dosyası diskten kaldırılamadı (%s)",
        deleted.plan.employee_id,
        role,
        type(exc).__name__,
    )


def _people(session: Session, employee: Employee) -> list[Employee]:
    """Çalışan ve ona (dolaylı da olsa) birleştirilmiş kayıtlar, E numarası sırasıyla."""
    found = {employee.id: employee}
    frontier = [employee.id]
    while frontier:
        merged = session.scalars(
            select(Employee).where(
                Employee.merged_into_id.in_(frontier), Employee.id.not_in(list(found))
            )
        ).all()
        frontier = [person.id for person in merged]
        found.update((person.id, person) for person in merged)
    return [found[person_id] for person_id in sorted(found)]


def _employee_dir(layout: DataLayout, folder_name: str) -> Path | None:
    try:
        folder = layout.employee_dir(folder_name)
    except ValueError:
        return None
    return folder if folder.is_dir() else None


def _delete_rows(session: Session, model: Any, people: Sequence[str]) -> int:
    result = session.execute(delete(model).where(model.employee_id.in_(list(people))))
    return int(getattr(result, "rowcount", 0) or 0)


def _person_pattern(session: Session, people: Sequence[Employee]) -> re.Pattern[str] | None:
    """Kişinin değerlerini (bütün olarak ve ad sözcükleri) dizgede bulan desen; sınır harf ya da
    rakam değildir (`Employees/Ad_Soyad_E0001/...` içinde ad da bulunur). E numarası değer
    sayılmaz — iskelette kalır."""
    ids = [person.id for person in people]
    names: list[str] = []
    values: set[str] = set()
    for person in people:
        names.extend(
            text
            for text in (
                person.given_names,
                person.surname,
                person.other_names,
                person.original_script_name,
            )
            if text
        )
        values.add(person.folder_name)
        names.extend(word for word in _WORDS.split(person.folder_name) if word != person.id)
        if person.date_of_birth is not None:
            born = person.date_of_birth
            values.update({born.isoformat(), born.strftime("%d.%m.%Y"), born.strftime("%d/%m/%Y")})
    names.extend(
        session.scalars(select(EmployeeAlias.raw_name).where(EmployeeAlias.employee_id.in_(ids)))
    )
    values.update(
        session.scalars(
            select(EmployeeIdentifier.value).where(EmployeeIdentifier.employee_id.in_(ids))
        )
    )
    values.update(
        session.scalars(select(EmployeeContact.value).where(EmployeeContact.employee_id.in_(ids)))
    )
    for name in names:
        values.add(name)
        values.update(_WORDS.split(name))
    tokens = sorted(
        {
            value.strip()
            for value in values
            if len(value.strip()) >= _MIN_TOKEN_LENGTH and value.strip() not in ids
        },
        key=lambda token: (-len(token), token),
    )
    if not tokens:
        return None
    alternatives = "|".join(re.escape(token) for token in tokens)
    return re.compile(rf"(?<![^\W_])(?:{alternatives})(?![^\W_])", re.IGNORECASE)


class _Drop:
    """Temizlenen dizge: kapsayan sözlükten ya da listeden çıkar."""


_DROP = _Drop()


def _scrub(value: Any, pattern: re.Pattern[str] | None, keys: frozenset[str]) -> Any:
    if isinstance(value, Mapping):
        cleaned = {}
        for key, item in value.items():
            if key in keys:
                continue
            item = _scrub(item, pattern, keys)
            if item is not _DROP:
                cleaned[key] = item
        return cleaned
    if isinstance(value, list):
        items = (_scrub(each, pattern, keys) for each in value)
        return [item for item in items if item is not _DROP]
    if isinstance(value, str) and pattern is not None and pattern.search(value):
        return _DROP
    return value


def _related_events(session: Session, plan: EmployeeDeletionPlan) -> Iterable[Event]:
    """Kişinin değerini taşıyabilecek olaylar: bu kayıtların, belgelerinin (önceden silinenler
    dahil), belgelerin kaynak dosyalarının ve o dosyaların partilerinin olayları."""
    document_rows = session.execute(
        select(Document.id, Document.source_refs_json).where(
            Document.employee_id.in_(list(plan.people))
        )
    ).all()
    document_ids = [document_id for document_id, _ in document_rows]
    file_ids = {file_id for _, refs in document_rows for file_id, _pages in _refs(refs)}
    upload_ids = set(
        session.scalars(select(UploadFile.upload_id).where(UploadFile.id.in_(file_ids)))
    )
    upload_ids.update(
        upload_id
        for upload_id in session.scalars(
            select(Event.upload_id).where(Event.employee_id.in_(list(plan.people)))
        )
        if upload_id is not None
    )
    return session.scalars(
        select(Event)
        .where(
            or_(
                Event.employee_id.in_(list(plan.people)),
                Event.document_id.in_(document_ids),
                Event.file_id.in_(file_ids),
                Event.upload_id.in_(upload_ids),
            )
        )
        .order_by(Event.id)
    )


def _clean_events(
    session: Session, plan: EmployeeDeletionPlan, pattern: re.Pattern[str] | None
) -> int:
    """Olay satırları kalır; kişisel değerleri temizlenir (modül açıklaması). Değişen olay
    sayısını döndürür."""
    people = set(plan.people)
    cleaned = 0
    for event in _related_events(session, plan):
        own = event.employee_id in people
        keys = PERSONAL_DATA_KEYS if own else frozenset()
        message = event.message
        if message is not None and (own or (pattern is not None and pattern.search(message))):
            message = DELETED_EMPLOYEE_MESSAGE.format(type=event.type)
        data = event.data_json
        if isinstance(data, Mapping):
            scrubbed = _scrub(data, pattern, keys)
            data = scrubbed if scrubbed != data else event.data_json
        if message != event.message or data is not event.data_json:
            event.message = message
            event.data_json = data
            cleaned += 1
    session.flush()
    return cleaned


def _clean_plans(session: Session, plan: EmployeeDeletionPlan) -> int:
    """K9: bu kayıtlara yerleştirilmiş öğelerin hedef adı temizlenir, hash yeniden hesaplanır.
    Değişen plan sayısı."""
    # Döngüsel içe aktarmayı önlemek için: `app.pipeline` `app.storage`'ı içe aktarır.
    from app.pipeline.plan_models import PlanDocument

    people = set(plan.people)
    upload_ids = select(Event.upload_id).where(
        Event.employee_id.in_(list(people)), Event.upload_id.is_not(None)
    )
    plan_ids = select(Document.plan_id).where(Document.employee_id.in_(list(people)))
    cleaned = 0
    for row in session.scalars(
        select(Plan)
        .where(or_(Plan.upload_id.in_(upload_ids), Plan.id.in_(plan_ids)))
        .order_by(Plan.id)
    ):
        content = row.json
        items = content.get("items") if isinstance(content, Mapping) else None
        if not isinstance(items, list):
            continue
        changed = False
        new_items = []
        for item in items:
            if _placed_on(item, people) and item.get("target_name") is not None:
                item = {
                    **item,
                    "target_name": DELETED_TARGET_NAME.format(
                        item_id=item.get("item_id"), format=item.get("target_format")
                    ),
                }
                changed = True
            new_items.append(item)
        if not changed:
            continue
        new_content = {**content, "items": new_items}
        row.json = new_content
        try:
            row.plan_hash = PlanDocument.model_validate(new_content).plan_hash
        except ValidationError:
            # Sözleşmeye zaten uymayan saklı plan okunamıyordu; hash'i dokunulmadan kalır.
            pass
        cleaned += 1
    session.flush()
    return cleaned


def _placed_on(item: Any, people: set[str]) -> bool:
    if not isinstance(item, Mapping):
        return False
    employee = item.get("employee")
    return isinstance(employee, Mapping) and employee.get("employee_id") in people


__all__ = [
    "DELETED_EMPLOYEE_MESSAGE",
    "DELETED_FOLDER_PREFIX",
    "DeletedEmployee",
    "EmployeeDeletionChangedError",
    "EmployeeDeletionPlan",
    "EmployeeNotDeletableError",
    "EmployeeNotFoundError",
    "check_employee_deletable",
    "delete_employee",
    "plan_employee_deletion",
    "remove_employee_files",
]
