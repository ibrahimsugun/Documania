"""İki çalışanı birleştirme — PRD 10.5.9 (PLAN.md §C90-d, §D61, §D69; K8, K10, K11, K16, K18,
R11, R13).

Otomatik açılışın (05.6) aynı kişi için açtığı ikinci kaydın tek çözüm yoludur. İK iki kaydı seçer
ve hangisinin kalacağına (`keep`) karar verir; öteki (`merge`) birleşir. İşlem iki aşamalı onaydan
(K16, §20.6 "İki çalışanı birleştir") sonra `merge_employees` ile tek işlemde yapılır ve **geri
alınamaz**; hiçbir şey silinmez (R11):

- **Belgeler** kalan kayda bağlanır (`documents.employee_id`); köken kaydı (`plan_id`,
  `source_refs_json`) değişmez (R13). Etkin belgenin dosyası kalanın `Hazir/`'ına K8 adıyla ve ilk
  boş sıra ekiyle taşınır (10.8.2'nin fiziksel kuralı), eski sürüm adını korur (K18), arşivdeki
  belge `Archive/` altında kalır; `Alinan/` kopyaları kalanın `Alinan/`'ına taşınır
  (`app.storage.merge`). Belge başına `MANUAL_MOVE` yazılmaz.
- **Alt kayıtlar** (isim yazımları, belge numaraları, iletişim bilgileri) kalan kayda bağlanır; aynı
  değer tek kalır: kalanda aynı `(kind, value)` — isim yazımında aynı ham yazım ya da normalize
  anahtar — varsa birleşenin satırı birleşende kalır ve `removed_at`/`removed_by` alır (silinmez).
  Aynı iletişim değerinin görülme zamanları kalandaki satıra katlanır; türde en çok bir güncel
  satır kalır — en son görülen (05.8.2).
- **Alan kaynakları** (`employee_field_observations`) kalan kayda bağlanır. Kalanın boş alanı
  birleşenin dolu alanıyla dolar (05.7.3'ün kuralı: dolu alan değişmez): `source=merge` gözlemi ve
  `EMPLOYEE_FIELD_FILLED` (`source: merge`) yazılır. İki kayıtta farklı değer taşıyan alanda
  birleşenin belge gözlemi kalanın değeriyle çelişir, sonucu `conflict` olur (profil uyarısı);
  kalanda aynı kaynaktan gözlem varsa birleşeninki birleşende kalır. Elle ve birleştirmeyle yazılmış
  gözlem yalnız değeri kalana geçen alanda taşınır.
- **Belge paketleri** kalan kayda bağlanır; kalanda aynı grubun iptal edilmemiş paketi varsa
  birleşenden gelen iptal edilir (nedeni `DUPLICATE_PACKAGE_NOTE`, yeniden açılabilir). Kalanın
  paketleri aynı işlemde yenilenir (14.2.2).
- **Birleşen kayıt** `merged` olur ve kalanın numarasını `merged_into_id`'de taşır; alanları,
  klasörü ve olayları yerinde kalır. Eşleştirme, aramalar, atama, taşıma, bağlam yüklemesi ve paket
  tanımlama onu bulmaz ya da 409'la reddeder; kaydı geri açılmaz.

Tek `EMPLOYEE_MERGED` olayı kullanıcı adıyla yazılır: `kept`, `merged` (iki numara), `documents`
(bağlanan belge kimlikleri) ve sayılar; kişisel değer yazılmaz (PRD §8.3, D51). Erişim logu,
kuyruk öğelerinin verisi ve geçmiş olaylar değişmez.

Satırlar önce yazılıp `flush` edilir, dosyalar en son taşınır; taşıma yarıda kalırsa dosyalar geri
alınır ve `EmployeeMergeError` yükselir — çağıran oturumu geri alır, hiçbir şey değişmemiş olur.
İki kaydın `profil.md`'si commit'ten sonra çağıranca yeniden üretilir (09.1.1,
`app.profiles.write_profile`: birleşeninki yalnız yönlendirme notudur). Oturum commit edilmez.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    Employee,
    EmployeeAlias,
    EmployeeContact,
    EmployeeFieldObservation,
    EmployeeIdentifier,
    EmployeePackage,
    EmployeeStatus,
    Event,
    FieldOutcome,
    FieldSource,
    PackageStatus,
    ProfileField,
    utcnow,
)
from app.events import EventType, record_event
from app.groups import cancel_package, refresh_employee_packages
from app.matching.fields import _is_empty, _same
from app.storage import (
    DataLayout,
    RelocatedDocument,
    plan_employee_merge,
    relocate_merged_files,
)

MERGED_STATUS = EmployeeStatus.MERGED.value
MERGE_RULE = "10.5.9"
MERGE_SOURCE = FieldSource.MERGE.value
# Kalanda aynı grubun paketi varken birleşenden gelen paketin iptal nedeni (≤ 120, 14.2.3).
DUPLICATE_PACKAGE_NOTE = "Birleştirme: kalan kayıtta aynı grubun paketi var."

_LIVE_PACKAGES = (PackageStatus.OPEN.value, PackageStatus.COMPLETED.value)


class EmployeeMergeRefusedError(ValueError):
    """Birleştirme yapılmaz; hiçbir şey yazılmadı. Mesaj kişisel değer taşımaz."""


class SameEmployeeError(EmployeeMergeRefusedError):
    """Kalan ve birleşen aynı kayıt."""


class EmployeeAlreadyMergedError(EmployeeMergeRefusedError):
    """Kayıtlardan biri zaten birleştirilmiş; birleştirme geri alınmaz, kalan kayıt kullanılır."""


class _Relation(enum.Enum):
    """Bir profil alanında birleşenin değeri kalanınkine göre."""

    NONE = "none"  # birleşende değer yok
    FILLED = "filled"  # kalanda boş: birleşenin değeriyle dolar
    SAME = "same"
    DIFFERENT = "different"


@dataclass(frozen=True, slots=True)
class RecordCounts:
    """Alt kayıtların sonucu: kalana bağlanan ve aynı değer kalanda olduğu için birleşende
    kapanan (`removed_at` alan) satır sayısı."""

    moved: int = 0
    closed: int = 0

    def __add__(self, other: RecordCounts) -> RecordCounts:
        return RecordCounts(self.moved + other.moved, self.closed + other.closed)


@dataclass(frozen=True, slots=True)
class MergedEmployees:
    """`merge_employees` sonucu: iki kayıt, kalana bağlanan belgeler (dosyası taşınanlar
    `relocated`), taşınan `Alinan/` dosyası sayısı, alt kayıt sayıları, dolan alanlar, bağlanan ve
    iptal edilen paketler ve `EMPLOYEE_MERGED` olayı."""

    keep: Employee
    merge: Employee
    documents: tuple[int, ...]
    relocated: tuple[int, ...]
    received: int
    records: RecordCounts
    fields: tuple[str, ...]
    packages: tuple[int, ...]
    cancelled_packages: tuple[int, ...]
    event: Event


def check_merge(keep: Employee, merge: Employee) -> None:
    """Birleştirmenin denetimi; hiçbir şey yazmaz. Aynı kayıt `SameEmployeeError`, kayıtlardan
    biri birleştirilmişse `EmployeeAlreadyMergedError`."""
    if keep.id == merge.id:
        raise SameEmployeeError(f"Çalışan {keep.id} kendisiyle birleştirilmez")
    for employee in (keep, merge):
        if employee.status == MERGED_STATUS:
            raise EmployeeAlreadyMergedError(
                f"Çalışan {employee.id} zaten birleştirilmiş; birleştirme geri alınmaz (10.5.9)"
            )


def merge_field_preview(keep: Employee, merge: Employee) -> dict[str, str]:
    """Onay özetinde alan başına sonuç (`ProfileField` sırasıyla): `filled` (kalanın boş alanı
    birleşenin değeriyle dolacak), `same`, `different` (kalanın değeri geçerli kalır, birleşenin
    belgeleri profilde uyarı olur) ya da `none` (birleşende değer yok). Hiçbir şey yazmaz."""
    return {field.value: _relation(field, keep, merge).value for field in ProfileField}


def merge_document_count(session: Session, employee_id: str) -> int:
    """Birleşenden kalana bağlanacak belge sayısı (ikinci onay metninin `<N>`'i): etkin, eski
    sürüm ve arşivdeki belgelerin hepsi."""
    return (
        session.scalar(select(func.count(Document.id)).where(Document.employee_id == employee_id))
        or 0
    )


def merge_employees(
    session: Session,
    layout: DataLayout,
    keep: Employee,
    merge: Employee,
    *,
    actor: str,
) -> MergedEmployees:
    """10.5.9 — `merge`'ü `keep`'e birleştirir; kurallar modül açıklamasındadır.

    `actor` iki aşamalı onayı (K16, §20.6.1) tamamlamış kullanıcının adıdır; boşsa `ValueError`.
    Denetim hataları `check_merge`'inkilerdir; dosya taşıması yarıda kalırsa `EmployeeMergeError`
    (dosyalar geri alındı, oturumu geri almak çağıranın). Oturum commit edilmez.
    """
    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")
    check_merge(keep, merge)
    now = utcnow()
    plan = plan_employee_merge(session, layout, keep, merge)

    documents = _merge_documents(session, keep, merge, plan.documents)
    records = (
        _merge_aliases(session, keep, merge, now=now, actor=actor)
        + _merge_identifiers(session, keep, merge, now=now, actor=actor)
        + _merge_contacts(session, keep, merge, now=now, actor=actor)
    )
    filled = _merge_fields(session, keep, merge, actor=actor)
    packages, duplicates = _merge_packages(session, keep, merge)
    merge.status = MERGED_STATUS
    merge.merged_into_id = keep.id

    relocated = tuple(document.document_id for document in plan.documents)
    event = record_event(
        session,
        EventType.EMPLOYEE_MERGED,
        employee_id=keep.id,
        actor=actor,
        data={
            "kept": keep.id,
            "merged": merge.id,
            "documents": list(documents),
            "relocated": list(relocated),
            "received": len(plan.received),
            "records": {"moved": records.moved, "closed": records.closed},
            "fields": list(filled),
            "packages": list(packages),
            "cancelled_packages": list(duplicates),
        },
    )
    for field_name in filled:
        record_event(
            session,
            EventType.EMPLOYEE_FIELD_FILLED,
            employee_id=keep.id,
            actor=actor,
            data={
                "field": field_name,
                "source": MERGE_SOURCE,
                "rule": MERGE_RULE,
                "from_employee_id": merge.id,
            },
        )
    session.flush()
    for package_id in duplicates:
        cancel_package(session, keep.id, package_id, actor=actor, note=DUPLICATE_PACKAGE_NOTE)
    # 14.2.2: birleşenden gelen belgeler kalanın paket kalemlerini karşılayabilir.
    refresh_employee_packages(session, keep.id, actor=actor)
    session.flush()
    # Dosyalar en son: bundan sonra düşecek iş yok, düşerse dosyalar geri alınmış olur.
    relocate_merged_files(layout, plan)
    return MergedEmployees(
        keep=keep,
        merge=merge,
        documents=documents,
        relocated=relocated,
        received=len(plan.received),
        records=records,
        fields=filled,
        packages=packages,
        cancelled_packages=duplicates,
        event=event,
    )


# --- belgeler -----------------------------------------------------------------------------------


def _merge_documents(
    session: Session, keep: Employee, merge: Employee, relocations: Sequence[RelocatedDocument]
) -> tuple[int, ...]:
    by_id = {relocation.document_id: relocation for relocation in relocations}
    documents = session.scalars(
        select(Document).where(Document.employee_id == merge.id).order_by(Document.id)
    ).all()
    for document in documents:
        document.employee_id = keep.id
        relocation = by_id.get(document.id)
        if relocation is not None:
            document.path = relocation.path
            document.sequence_no = relocation.sequence_no
    return tuple(document.id for document in documents)


# --- alt kayıtlar -------------------------------------------------------------------------------


def _close(
    record: EmployeeAlias | EmployeeIdentifier | EmployeeContact, now: datetime, actor: str
) -> int:
    """Kalanda aynı değeri olan birleşen satırı birleşende kapanır (silinmez); zaten kaldırılmışsa
    dokunulmaz. Yeni kapanan satır sayısı (0 ya da 1)."""
    if record.removed_at is not None:
        return 0
    record.removed_at = now
    record.removed_by = actor
    return 1


def _merge_aliases(
    session: Session, keep: Employee, merge: Employee, *, now: datetime, actor: str
) -> RecordCounts:
    kept = session.scalars(select(EmployeeAlias).where(EmployeeAlias.employee_id == keep.id)).all()
    raw_names = {alias.raw_name for alias in kept}
    keys = {alias.normalized_name for alias in kept}
    moved = closed = 0
    for alias in session.scalars(
        select(EmployeeAlias)
        .where(EmployeeAlias.employee_id == merge.id)
        .order_by(EmployeeAlias.id)
    ).all():
        if alias.raw_name in raw_names or alias.normalized_name in keys:
            closed += _close(alias, now, actor)
            continue
        alias.employee_id = keep.id
        moved += 1
    return RecordCounts(moved, closed)


def _merge_identifiers(
    session: Session, keep: Employee, merge: Employee, *, now: datetime, actor: str
) -> RecordCounts:
    kept = {
        (identifier.kind, identifier.value)
        for identifier in session.scalars(
            select(EmployeeIdentifier).where(EmployeeIdentifier.employee_id == keep.id)
        )
    }
    moved = closed = 0
    for identifier in session.scalars(
        select(EmployeeIdentifier)
        .where(EmployeeIdentifier.employee_id == merge.id)
        .order_by(EmployeeIdentifier.id)
    ).all():
        if (identifier.kind, identifier.value) in kept:
            closed += _close(identifier, now, actor)
            continue
        identifier.employee_id = keep.id
        moved += 1
    return RecordCounts(moved, closed)


def _merge_contacts(
    session: Session, keep: Employee, merge: Employee, *, now: datetime, actor: str
) -> RecordCounts:
    kept = list(
        session.scalars(
            select(EmployeeContact)
            .where(EmployeeContact.employee_id == keep.id)
            .order_by(EmployeeContact.id)
        )
    )
    by_value: dict[tuple[str, str], EmployeeContact] = {}
    for contact in kept:
        by_value.setdefault((contact.kind, contact.value), contact)
    moved: list[EmployeeContact] = []
    closed = 0
    for contact in session.scalars(
        select(EmployeeContact)
        .where(EmployeeContact.employee_id == merge.id)
        .order_by(EmployeeContact.id)
    ).all():
        twin = by_value.get((contact.kind, contact.value))
        if twin is None:
            contact.employee_id = keep.id
            moved.append(contact)
            continue
        # Aynı değer tek kalır: görülme zamanları kalandaki satıra katlanır (05.8.2).
        twin.first_seen_at = min(twin.first_seen_at, contact.first_seen_at)
        twin.last_seen_at = max(twin.last_seen_at, contact.last_seen_at)
        twin.is_current = twin.is_current or contact.is_current
        contact.is_current = False
        closed += _close(contact, now, actor)
    _single_current(kept + moved)
    return RecordCounts(len(moved), closed)


def _single_current(contacts: Sequence[EmployeeContact]) -> None:
    """Türde en çok bir güncel satır (§D68-c): birden çok güncel satır varsa en son görülen kalır
    (05.8.2; eşitlikte son eklenen), ötekiler geçmiş olur. Kaldırılmış satır da sayılır — kazanırsa
    kart o türde "—" gösterir, geri alınınca yeniden güncel olur."""
    for kind in {contact.kind for contact in contacts}:
        current = [contact for contact in contacts if contact.kind == kind and contact.is_current]
        if len(current) < 2:
            continue
        winner = max(current, key=lambda contact: (contact.last_seen_at, contact.id))
        for contact in current:
            if contact is not winner:
                contact.is_current = False


# --- alan kaynakları ------------------------------------------------------------------------------


def _relation(field: ProfileField, keep: Employee, merge: Employee) -> _Relation:
    kept, merged = getattr(keep, field.value), getattr(merge, field.value)
    if _is_empty(merged):
        return _Relation.NONE
    if _is_empty(kept):
        return _Relation.FILLED
    return _Relation.SAME if _same(field, kept, merged) else _Relation.DIFFERENT


def _merge_fields(
    session: Session, keep: Employee, merge: Employee, *, actor: str
) -> tuple[str, ...]:
    relations = {field.value: _relation(field, keep, merge) for field in ProfileField}
    kept_sources = set(
        session.execute(
            select(
                EmployeeFieldObservation.field,
                EmployeeFieldObservation.file_id,
                EmployeeFieldObservation.page_index,
            ).where(
                EmployeeFieldObservation.employee_id == keep.id,
                EmployeeFieldObservation.source == FieldSource.DOCUMENT.value,
            )
        ).tuples()
    )
    for observation in session.scalars(
        select(EmployeeFieldObservation)
        .where(EmployeeFieldObservation.employee_id == merge.id)
        .order_by(EmployeeFieldObservation.id)
    ).all():
        relation = relations[observation.field]
        if observation.source != FieldSource.DOCUMENT.value:
            # Elle ya da birleştirmeyle yazılmış gözlem birleşenin değerini anlatır: yalnız değer
            # kalana geçiyorsa onunla gider.
            if relation is _Relation.FILLED:
                observation.employee_id = keep.id
            continue
        source = (observation.field, observation.file_id, observation.page_index)
        if source in kept_sources:
            continue  # aynı kaynak kalanda zaten gözlendi (tekil anahtar)
        kept_sources.add(source)
        observation.employee_id = keep.id
        if relation is _Relation.DIFFERENT and observation.outcome != FieldOutcome.CONFLICT.value:
            # Belge birleşenin değerini okudu; kalanın değeri farklı → profil uyarısı.
            observation.outcome = FieldOutcome.CONFLICT.value

    filled = tuple(name for name, relation in relations.items() if relation is _Relation.FILLED)
    for name in filled:
        setattr(keep, name, getattr(merge, name))
        session.add(
            EmployeeFieldObservation(
                employee_id=keep.id,
                field=name,
                outcome=FieldOutcome.FILLED.value,
                source=MERGE_SOURCE,
                actor=actor,
            )
        )
    return filled


# --- belge paketleri ------------------------------------------------------------------------------


def _merge_packages(
    session: Session, keep: Employee, merge: Employee
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    live_groups = set(
        session.scalars(
            select(EmployeePackage.group_id).where(
                EmployeePackage.employee_id == keep.id,
                EmployeePackage.status.in_(_LIVE_PACKAGES),
            )
        )
    )
    moved: list[int] = []
    duplicates: list[int] = []
    for package in session.scalars(
        select(EmployeePackage)
        .where(EmployeePackage.employee_id == merge.id)
        .order_by(EmployeePackage.id)
    ).all():
        package.employee_id = keep.id
        moved.append(package.id)
        if package.status not in _LIVE_PACKAGES:
            continue
        if package.group_id in live_groups:
            duplicates.append(package.id)
        else:
            live_groups.add(package.group_id)
    return tuple(moved), tuple(duplicates)
