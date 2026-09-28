"""Çalışanın belge paketleri — tanımlama, karşılanma hesabı, tamamlanma, iptal (14.2.1–14.2.3,
14.3.1; PLAN.md §C89).

Bir **belge paketi** bir belge grubunun (14.1) çalışana tanımlanmış örneğidir (örn. "Sırbistan
iş başvurusu" Ivan'a). Kalemler paket başına kopyalanmaz: paket her değerlendirmede grubun
kaldırılmamış kalemlerini okur, bu yüzden grup değişikliği pakete anında yansır.

- **Karşılanma (14.2.2).** Kalem, çalışanın **etkin** (`documents.status == active`) bir belgesi
  14.1.2 kuralıyla (`item_matches`: etiket ülkeden bağımsız, tür yalnız kendi slug'ı) eşleşiyorsa
  tik alır ve o belgeye bağlanır; birden çok belge uyarsa en yenisi (oluşma zamanı, sonra kimlik).
  Eski sürüm (K18), arşivdeki belge ve eğitim modunun örnekleri (belge değildir, `example_files`)
  kalem karşılamaz. Aynı belge birden çok paketin kalemini karşılayabilir. Hesap her görüntülemede
  belgelerden yapılır (`evaluate_package`) ve hiçbir şey yazmaz — GET isteği olay yazmaz.
- **Durum (14.2.3).** `employee_packages.status` yazılı tutulur; geçişleri yalnız yenileme
  (`refresh_employee_packages`) yazar: zorunlu kalemlerin hepsi karşılanınca `open → completed`
  (`completed_at`, `PACKAGE_COMPLETED`), sonradan eksik oluşunca `completed → open`
  (`completed_at` boşalır, `PACKAGE_REOPENED`). Zorunlu kalemi olmayan paket karşılanmış sayılır.
  Yenileme belge yazma (boru hattının uygulaması, kuyruk ataması ve profil onayı), başka çalışana
  taşıma (iki çalışan için), arşivleme ve grup kalemi değişikliği noktalarından çağrılır; arşivden
  geri alma (tm 130) ve çalışan birleştirme (tm 129) aynı yardımcıyı çağırır. Yenileme çağıranın
  oturumunda, çağıranın işleminin içinde çalışır; sağlayıcı çağrısı ve dosya işlemi yoktur.
- **Tanımlama (14.2.1).** Yalnız arşivlenmemiş gruptan paket tanımlanır; aynı çalışanda aynı grubun
  iptal edilmemiş paketi varsa ilk istek paketi açmaz, uyarı döner (`PackageAssignment.warn`) ve
  ancak onaylı ikinci istek (`confirm_duplicate`) açar. Tanımlayan kullanıcı ve zaman yazılır,
  `PACKAGE_ASSIGNED` olayı düşer; paket tanımlandığı anda değerlendirilir (belgeler zaten varsa
  hemen tamamlanır).
- **İptal ve yeniden açma.** Paket nedeniyle tek adımda iptal edilir (§D61-b: dosya taşımaz,
  eşleştirmeyi değiştirmez, geri alınabilir) ve "Yeniden aç" ile açığa döner, ardından yeniden
  değerlendirilir. Silme yoktur (R11): iptal edilen paket satırıyla kalır.
- Olaylar (`PACKAGE_ASSIGNED`, `PACKAGE_COMPLETED`, `PACKAGE_REOPENED`, `PACKAGE_CANCELLED`) çalışan
  kimliği ve kullanıcı adıyla yazılır; veri yalnız paket ve grup kimliğini ve önceki durumu taşır —
  not ve iptal nedeni olaya girmez (CONVENTIONS §6). Paket belge içeriğine ve boru hattının
  kararına dokunmaz, yalnız okur (K17, R10). Hiçbir fonksiyon commit etmez.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeePackage,
    GroupItemKind,
    KnownDocumentType,
    PackageStatus,
    utcnow,
)
from app.events import EventType, record_event
from app.groups.service import (
    NOTE_MAX_LENGTH,
    NOTE_TOO_LONG,
    active_items,
    get_group,
    item_matches,
)

COMPLETED_LABEL = "Tamamlandı — başvuru başlatılabilir"
OPEN_LABEL = "Açık — {met}/{total} zorunlu kalem"
CANCELLED_LABEL = "İptal edildi"
CANCEL_NOTE_REQUIRED = "İptal nedeni boş olamaz."
GROUP_ARCHIVED = "Arşivdeki gruba yeni paket tanımlanamaz."
ALREADY_CANCELLED = "Paket zaten iptal edilmiş."
NOT_CANCELLED = "Yalnız iptal edilmiş paket yeniden açılır."

# Yenilemenin değerlendirdiği durumlar: iptal edilen paket İK yeniden açana dek hesaba girmez.
_LIVE = (PackageStatus.OPEN.value, PackageStatus.COMPLETED.value)


class PackageEmployeeNotFoundError(LookupError):
    """Paketin tanımlanacağı çalışan yok."""


class PackageNotFoundError(LookupError):
    """Paket yok ya da bu çalışanın değil."""


class GroupArchivedError(ValueError):
    """Grup arşivde: yeni paket tanımlanamaz (14.1.1)."""


class PackageStateError(ValueError):
    """İşlem paketin durumuna uymuyor (iptal edilmiş paket yeniden iptal edilmez, iptal edilmemiş
    paket yeniden açılmaz)."""


class PackageFormError(ValueError):
    """Girilen değerler kurala uymuyor; `problems` alan adından mesaj listesine."""

    def __init__(self, problems: dict[str, list[str]]) -> None:
        super().__init__("; ".join(message for items in problems.values() for message in items))
        self.problems = problems


# --- değerlendirme -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MatchedDocument:
    """Kalemi karşılayan belge: kimliği, dosya adı ve türünün adı."""

    id: int
    file_name: str
    type_name: str


@dataclass(frozen=True, slots=True)
class PackageItemView:
    """Paketin bir kalemi ve (varsa) onu karşılayan belge."""

    item_id: int
    position: int
    match_kind: str
    title: str
    required: bool
    note: str | None
    document: MatchedDocument | None

    @property
    def satisfied(self) -> bool:
        return self.document is not None


@dataclass(frozen=True, slots=True)
class PackageView:
    """Paketin görüntülemede hesaplanan hâli (14.2.2). `status` yazılı durumdur; `state`
    iptal edilmemiş pakette kalemlerden hesaplanan durumdur (yenileme noktaları ikisini eşit
    tutar)."""

    id: int
    employee_id: str
    group_id: int
    group_name: str
    group_archived: bool
    status: str
    note: str | None
    requested_by: str
    requested_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancelled_by: str | None
    cancel_note: str | None
    items: tuple[PackageItemView, ...]

    @property
    def required_total(self) -> int:
        return sum(1 for item in self.items if item.required)

    @property
    def required_met(self) -> int:
        return sum(1 for item in self.items if item.required and item.satisfied)

    @property
    def missing_required(self) -> int:
        return self.required_total - self.required_met

    @property
    def complete(self) -> bool:
        """Zorunlu kalemlerin hepsi karşılandı mı (zorunlu kalem yoksa `True`)."""
        return self.missing_required == 0

    @property
    def cancelled(self) -> bool:
        return self.status == PackageStatus.CANCELLED.value

    @property
    def state(self) -> PackageStatus:
        if self.cancelled:
            return PackageStatus.CANCELLED
        return PackageStatus.COMPLETED if self.complete else PackageStatus.OPEN

    @property
    def state_label(self) -> str:
        """Durum rozetinin metni (14.2.2, 14.2.3): "Açık — k/n zorunlu kalem", "Tamamlandı —
        başvuru başlatılabilir" ya da "İptal edildi"."""
        if self.state is PackageStatus.CANCELLED:
            return CANCELLED_LABEL
        if self.state is PackageStatus.COMPLETED:
            return COMPLETED_LABEL
        return OPEN_LABEL.format(met=self.required_met, total=self.required_total)


@dataclass(frozen=True, slots=True)
class _Candidate:
    """Kalem karşılayabilecek etkin belge; `item_matches`'in baktığı `slug` ve `file_label`."""

    document_id: int
    slug: str
    file_label: str
    type_name: str
    file_name: str


def _active_documents(session: Session, employee_ids: Iterable[str]) -> dict[str, list[_Candidate]]:
    """Çalışan başına etkin belgeler, en yeniden eskiye."""
    ids = sorted(set(employee_ids))
    candidates: dict[str, list[_Candidate]] = {employee_id: [] for employee_id in ids}
    if not ids:
        return candidates
    rows = session.execute(
        select(
            Document.id,
            Document.employee_id,
            Document.path,
            KnownDocumentType.slug,
            KnownDocumentType.file_label,
            KnownDocumentType.name,
        )
        .join(KnownDocumentType, KnownDocumentType.slug == Document.type_slug)
        .where(Document.employee_id.in_(ids), Document.status == DocumentStatus.ACTIVE.value)
        .order_by(Document.created_at.desc(), Document.id.desc())
    )
    for document_id, employee_id, path, slug, file_label, type_name in rows:
        candidates[employee_id].append(
            _Candidate(
                document_id=document_id,
                slug=slug,
                file_label=file_label,
                type_name=type_name,
                file_name=PurePosixPath(path).name,
            )
        )
    return candidates


def evaluate_packages(session: Session, packages: Sequence[EmployeePackage]) -> list[PackageView]:
    """Paketleri çalışanların güncel etkin belgelerine göre değerlendirir (14.2.2), aynı sırayla.
    Hiçbir şey yazmaz."""
    documents = _active_documents(session, (package.employee_id for package in packages))
    views = []
    for package in packages:
        group = package.group
        candidates = documents[package.employee_id]
        items = []
        for item in active_items(group):
            found = next(
                (candidate for candidate in candidates if item_matches(item, candidate)), None
            )
            if item.match_kind == GroupItemKind.TYPE and item.document_type is not None:
                title = item.document_type.name
            else:
                title = item.file_label or item.type_slug or ""
            items.append(
                PackageItemView(
                    item_id=item.id,
                    position=item.position,
                    match_kind=item.match_kind,
                    title=title,
                    required=item.required,
                    note=item.note,
                    document=(
                        None
                        if found is None
                        else MatchedDocument(
                            id=found.document_id,
                            file_name=found.file_name,
                            type_name=found.type_name,
                        )
                    ),
                )
            )
        views.append(
            PackageView(
                id=package.id,
                employee_id=package.employee_id,
                group_id=group.id,
                group_name=group.name,
                group_archived=group.archived_at is not None,
                status=package.status,
                note=package.note,
                requested_by=package.requested_by,
                requested_at=package.requested_at,
                completed_at=package.completed_at,
                cancelled_at=package.cancelled_at,
                cancelled_by=package.cancelled_by,
                cancel_note=package.cancel_note,
                items=tuple(items),
            )
        )
    return views


def evaluate_package(session: Session, package: EmployeePackage) -> PackageView:
    """Tek paketin değerlendirmesi (`evaluate_packages`)."""
    return evaluate_packages(session, [package])[0]


def employee_packages(session: Session, employee_id: str) -> list[PackageView]:
    """Çalışanın bütün paketleri (iptal edilenler dahil), tanımlanma sırasıyla."""
    packages = session.scalars(
        select(EmployeePackage)
        .where(EmployeePackage.employee_id == employee_id)
        .order_by(EmployeePackage.requested_at, EmployeePackage.id)
    ).all()
    return evaluate_packages(session, packages)


@dataclass(frozen=True, slots=True)
class PackageCounts:
    """Çalışan listesinin paket hücresi (14.3.1): açık paket sayısı ve o paketlerdeki eksik
    zorunlu kalem sayısı; tamamlanan paket sayısı ayrıca."""

    open: int = 0
    missing: int = 0
    completed: int = 0


def package_counts(
    session: Session, employee_ids: Iterable[str] | None = None
) -> dict[str, PackageCounts]:
    """İptal edilmemiş paketi olan çalışanların sayıları (hesaplanan durumla); `employee_ids`
    verilirse yalnız onlar. Paketi olmayan çalışan sözlükte yoktur."""
    query = select(EmployeePackage).where(EmployeePackage.status.in_(_LIVE))
    if employee_ids is not None:
        query = query.where(EmployeePackage.employee_id.in_(sorted(set(employee_ids))))
    counts: dict[str, PackageCounts] = {}
    for view in evaluate_packages(session, session.scalars(query).all()):
        current = counts.get(view.employee_id, PackageCounts())
        if view.complete:
            counts[view.employee_id] = PackageCounts(
                current.open, current.missing, current.completed + 1
            )
        else:
            counts[view.employee_id] = PackageCounts(
                current.open + 1, current.missing + view.missing_required, current.completed
            )
    return counts


def employees_with_missing_packages(session: Session) -> set[str]:
    """En az bir açık (zorunlu kalemi eksik) paketi olan çalışanlar (14.3.1 süzgeci)."""
    return {employee_id for employee_id, counts in package_counts(session).items() if counts.open}


# --- yenileme ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PackageTransition:
    """Yenilemenin yazdığı durum geçişi."""

    package_id: int
    employee_id: str
    previous: PackageStatus
    current: PackageStatus


def _record(
    session: Session,
    event_type: EventType,
    package: EmployeePackage,
    *,
    actor: str,
    **extra: object,
) -> None:
    record_event(
        session,
        event_type,
        employee_id=package.employee_id,
        actor=actor,
        data={"package_id": package.id, "group_id": package.group_id, **extra},
    )


def _refresh(
    session: Session, packages: Sequence[EmployeePackage], *, actor: str
) -> list[PackageTransition]:
    transitions = []
    for package, view in zip(packages, evaluate_packages(session, packages), strict=True):
        if package.status == PackageStatus.OPEN.value and view.complete:
            package.status = PackageStatus.COMPLETED.value
            package.completed_at = utcnow()
            _record(session, EventType.PACKAGE_COMPLETED, package, actor=actor)
            previous, current = PackageStatus.OPEN, PackageStatus.COMPLETED
        elif package.status == PackageStatus.COMPLETED.value and not view.complete:
            package.status = PackageStatus.OPEN.value
            package.completed_at = None
            _record(
                session,
                EventType.PACKAGE_REOPENED,
                package,
                actor=actor,
                previous_status=PackageStatus.COMPLETED.value,
            )
            previous, current = PackageStatus.COMPLETED, PackageStatus.OPEN
        else:
            continue
        transitions.append(PackageTransition(package.id, package.employee_id, previous, current))
    session.flush()
    return transitions


def refresh_employee_packages(
    session: Session, employee_id: str, *, actor: str = "system"
) -> list[PackageTransition]:
    """Çalışanın açık ve tamamlanmış paketlerini yeniden değerlendirir ve durum geçişlerini yazar
    (14.2.2, 14.2.3). Belgeyi yazan, taşıyan, arşivleyen, geri alan ya da çalışanları birleştiren
    her işlem, işleminin içinde, etkilenen her çalışan için bunu çağırır; `actor` o işlemin
    kullanıcısıdır (boru hattında `system`). Geçiş yoksa olay yazılmaz. Oturum commit edilmez."""
    session.flush()
    packages = session.scalars(
        select(EmployeePackage)
        .where(EmployeePackage.employee_id == employee_id, EmployeePackage.status.in_(_LIVE))
        .order_by(EmployeePackage.id)
    ).all()
    return _refresh(session, packages, actor=actor)


def refresh_group_packages(
    session: Session, group_id: int, *, actor: str
) -> list[PackageTransition]:
    """Grubun açık ve tamamlanmış paketlerini yeniden değerlendirir: kalem eklenince ya da
    kaldırılınca paketler anında yeni kalemlerle hesaplanır (14.1.1). Oturum commit edilmez."""
    session.flush()
    packages = session.scalars(
        select(EmployeePackage)
        .where(EmployeePackage.group_id == group_id, EmployeePackage.status.in_(_LIVE))
        .order_by(EmployeePackage.id)
    ).all()
    return _refresh(session, packages, actor=actor)


# --- tanımlama, iptal, yeniden açma --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PackageAssignment:
    """`assign_package` sonucu: açılan paket; aynı grubun iptal edilmemiş paketi varken onaysız
    istekte `package` boştur ve `warn` doğrudur."""

    package: EmployeePackage | None
    warn: bool = False


def _clean_note(value: str | None) -> str | None:
    return " ".join((value or "").split()) or None


def _require_actor(actor: str) -> None:
    if not actor.strip():
        raise ValueError("Paket işlemi kullanıcı adıyla loglanır (K15): actor boş olamaz")


def assign_package(
    session: Session,
    employee_id: str,
    group_id: int,
    *,
    actor: str,
    note: str | None = None,
    confirm_duplicate: bool = False,
) -> PackageAssignment:
    """Grubu çalışana paket olarak tanımlar (14.2.1).

    Çalışan yoksa `PackageEmployeeNotFoundError`, grup yoksa `app.groups.GroupNotFoundError`, grup
    arşivdeyse `GroupArchivedError`, not 120 karakteri aşarsa `PackageFormError`. Çalışanda aynı
    grubun iptal edilmemiş paketi varsa ve `confirm_duplicate` yanlışsa hiçbir şey yazılmaz, `warn`
    döner. Açılan paket hemen değerlendirilir. Oturum commit edilmez.
    """
    _require_actor(actor)
    if session.get(Employee, employee_id) is None:
        raise PackageEmployeeNotFoundError(employee_id)
    group = get_group(session, group_id)
    if group.archived_at is not None:
        raise GroupArchivedError(GROUP_ARCHIVED)
    clean_note = _clean_note(note)
    if clean_note and len(clean_note) > NOTE_MAX_LENGTH:
        raise PackageFormError({"note": [NOTE_TOO_LONG]})
    duplicate = (
        session.scalar(
            select(EmployeePackage.id)
            .where(
                EmployeePackage.employee_id == employee_id,
                EmployeePackage.group_id == group.id,
                EmployeePackage.status.in_(_LIVE),
            )
            .limit(1)
        )
        is not None
    )
    if duplicate and not confirm_duplicate:
        return PackageAssignment(None, warn=True)
    package = EmployeePackage(
        employee_id=employee_id,
        group_id=group.id,
        status=PackageStatus.OPEN.value,
        requested_by=actor,
        requested_at=utcnow(),
        note=clean_note,
    )
    session.add(package)
    session.flush()
    _record(session, EventType.PACKAGE_ASSIGNED, package, actor=actor, duplicate=duplicate)
    _refresh(session, [package], actor=actor)
    return PackageAssignment(package)


def get_package(session: Session, employee_id: str, package_id: int) -> EmployeePackage:
    """Çalışanın paketi; yoksa ya da başka çalışanınsa `PackageNotFoundError`."""
    package = session.get(EmployeePackage, package_id)
    if package is None or package.employee_id != employee_id:
        raise PackageNotFoundError(package_id)
    return package


def cancel_package(
    session: Session, employee_id: str, package_id: int, *, actor: str, note: str | None
) -> EmployeePackage:
    """Paketi nedeniyle iptal eder (14.2.3; tek adım, §D61-b). Neden boşsa ya da 120 karakteri
    aşarsa `PackageFormError`, paket zaten iptal edilmişse `PackageStateError`. Tamamlanma zamanı
    geçmiş kaydı olarak kalır. Neden olaya girmez. Oturum commit edilmez."""
    _require_actor(actor)
    package = get_package(session, employee_id, package_id)
    if package.status == PackageStatus.CANCELLED.value:
        raise PackageStateError(ALREADY_CANCELLED)
    reason = _clean_note(note)
    if reason is None:
        raise PackageFormError({"note": [CANCEL_NOTE_REQUIRED]})
    if len(reason) > NOTE_MAX_LENGTH:
        raise PackageFormError({"note": [NOTE_TOO_LONG]})
    previous = package.status
    package.status = PackageStatus.CANCELLED.value
    package.cancelled_at = utcnow()
    package.cancelled_by = actor
    package.cancel_note = reason
    session.flush()
    _record(session, EventType.PACKAGE_CANCELLED, package, actor=actor, previous_status=previous)
    return package


def reopen_package(
    session: Session, employee_id: str, package_id: int, *, actor: str
) -> EmployeePackage:
    """İptal edilmiş paketi açığa döndürür ve yeniden değerlendirir (14.2.3; tek adım). Paket
    iptal edilmemişse `PackageStateError`. Oturum commit edilmez."""
    _require_actor(actor)
    package = get_package(session, employee_id, package_id)
    if package.status != PackageStatus.CANCELLED.value:
        raise PackageStateError(NOT_CANCELLED)
    package.status = PackageStatus.OPEN.value
    package.completed_at = None
    package.cancelled_at = None
    package.cancelled_by = None
    package.cancel_note = None
    session.flush()
    _record(
        session,
        EventType.PACKAGE_REOPENED,
        package,
        actor=actor,
        previous_status=PackageStatus.CANCELLED.value,
    )
    _refresh(session, [package], actor=actor)
    return package
