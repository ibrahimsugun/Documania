"""Belge grupları — grup ve kalem yönetimi, kalem eşleşmesi (14.1.1, 14.1.2; PLAN.md §C89).

Bir **belge grubu** bir süreç için gereken belge kalemlerinin adlandırılmış listesidir (örn.
"Sırbistan iş başvurusu": fotoğraf, pasaport, kimlik, çevirili diploma). Grubun çalışana tanımlanmış
örneği (belge paketi) ve karşılanma hesabı `app.groups.packages`'tadır (14.2); bu modül grubu,
kalemlerini ve kalemin bir türle eşleşme kuralını verir. Kalem eklenince ya da kaldırılınca grubun
açık ve tamamlanmış paketleri aynı işlemde yeniden değerlendirilir (`refresh_group_packages`).

- **Eşleşme (14.1.2).** Kalem ya bir dosya etiketiyle (`label`: katalogdaki `file_label` değerleri)
  ya belirli bir türle (`type`: slug) tanımlanır. Etiketli kalemi, ülkesi ne olursa olsun aynı
  etiketli her tür karşılar (Rus ya da Türk pasaportu "Passport" kalemini karşılar); etiketler
  boşluk sadeleştirilip `casefold` ile karşılaştırılır (`normalize_label`). Türlü kalemi yalnız o
  tür karşılar. Ülke hiçbir yerde bakılmaz; önerilen tür sözlüğünün `doc_kind`'ı da kullanılmaz (her
  katalog türünde yoktur).
- **Ad tekil.** `normalize_group_name` adı 00.4.2 slug sadeleştirmesine indirip küçültür: harf
  büyüklüğü, Türkçe/Kiril harf ve noktalama farkı aynı ad sayılır. Arşivli grup da adını tutar.
- **Silme yok (R11, PRD §10).** Grup arşivlenir (`archived_at`; yeni paket tanımlanamaz, açık
  paketler sürer) ve geri alınır; kalem kaldırılır (`removed_at`) ve grubun eşleşmesine girmez,
  satır kalır (PLAN.md §D64). Hepsi tek adımlıdır (§D61-b: dosya taşımaz, eşleştirmeyi
  değiştirmez, geri alınabilir) ve `GROUP_CHANGED` olayı kullanıcı adıyla yazılır (K15). Olay
  verisi kişisel değer taşımaz: grup ve kalem kimliği, işlem, alan adları ve kalem sayısı.
- Grup belge içeriğine, dosyaya ya da boru hattına dokunmaz (K17).
- Hiçbir fonksiyon commit etmez; iş birimini çağıran kapatır (`app.catalog.manage` ile aynı
  sözleşme).
"""

from __future__ import annotations

import enum
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    DocumentGroup,
    DocumentGroupItem,
    EmployeePackage,
    GroupItemKind,
    KnownDocumentType,
    PackageStatus,
    utcnow,
)
from app.events import EventType, record_event
from app.i18n import N_, Translatable
from app.storage.slug import SlugError, slugify

NAME_MAX_LENGTH = 120
DESCRIPTION_MAX_LENGTH = 200
NOTE_MAX_LENGTH = 120
# `document_groups.normalized_name` sütununun uzunluğu; sadeleştirme kelime sınırından kısaltılır.
NORMALIZED_NAME_MAX_LENGTH = 255

NAME_REQUIRED = "Grup adı boş olamaz."
NAME_TOO_LONG = f"Grup adı en çok {NAME_MAX_LENGTH} karakter olabilir."
NAME_UNUSABLE = "Grup adı en az bir harf ya da rakam içermeli."
DESCRIPTION_TOO_LONG = f"Açıklama en çok {DESCRIPTION_MAX_LENGTH} karakter olabilir."
# 10.10.3: paket formunun hatası profil sayfasında görünür, gösterimde çevrilir.
NOTE_TOO_LONG = Translatable(N_("Not en çok {limit} karakter olabilir."), limit=NOTE_MAX_LENGTH)
MATCH_KIND_INVALID = "Kalem ya bir dosya etiketiyle ya da bir türle tanımlanır."
LABEL_REQUIRED = "Bir dosya etiketi seçin."
LABEL_UNKNOWN = "Bu dosya etiketi katalogdaki hiçbir türde yok."
TYPE_REQUIRED = "Bir belge türü seçin."
TYPE_UNKNOWN = "Bu belge türü katalogda yok."


class GroupAction(enum.StrEnum):
    """`GROUP_CHANGED` olayının `action` değeri (PLAN.md §C89)."""

    CREATE = "create"
    UPDATE = "update"
    ITEM_ADDED = "item_added"
    ITEM_REMOVED = "item_removed"
    ARCHIVE = "archive"
    RESTORE = "restore"


class GroupNotFoundError(LookupError):
    """Grup yok."""


class GroupItemNotFoundError(LookupError):
    """Kalem bu grupta yok ya da zaten kaldırılmış."""


class GroupFormError(ValueError):
    """Girilen değerler kurala uymuyor; `problems` alan adından mesaj listesine."""

    def __init__(self, problems: dict[str, list[str]]) -> None:
        super().__init__("; ".join(message for items in problems.values() for message in items))
        self.problems = problems


class GroupNameTakenError(ValueError):
    """Aynı sadeleşmiş adla bir grup var; `archived` o grubun arşivde olup olmadığıdır."""

    def __init__(self, name: str, *, archived: bool) -> None:
        super().__init__(name)
        self.name = name
        self.archived = archived


class DuplicateGroupItemError(ValueError):
    """Aynı etiket ya da tür grupta zaten kalem (kalem tekildir, §C89)."""


class _TypeLike(Protocol):
    """Eşleşmenin baktığı iki alan: `KnownDocumentType` ve `TypeSummary` ikisini de taşır."""

    @property
    def slug(self) -> str: ...

    @property
    def file_label(self) -> str: ...


# --- sadeleştirme ve eşleşme ---------------------------------------------------------------------


def _single_line(value: str | None) -> str:
    """Tek satırlık girdi: baştaki/sondaki boşluk atılır, içteki boşluklar teke iner."""
    return " ".join((value or "").split())


def normalize_group_name(name: str) -> str:
    """Grup adının tekillik anahtarı: 00.4.2 slug sadeleştirmesi, küçük harf
    (`"Sırbistan iş başvurusu" → "sirbistan_is_basvurusu"`). Harf ya da rakam kalmazsa
    `ValueError` (`SlugError`)."""
    return slugify(name, "_", max_length=NORMALIZED_NAME_MAX_LENGTH).casefold()


def normalize_label(label: str | None) -> str:
    """Dosya etiketinin karşılaştırma anahtarı: boşluk sadeleştirilir, `casefold`."""
    return _single_line(label).casefold()


def item_matches(item: DocumentGroupItem, document_type: _TypeLike) -> bool:
    """14.1.2 — `document_type` türünün belgesi bu kalemi karşılar mı. `label` kalemi aynı dosya
    etiketli her türe (ülkeden bağımsız), `type` kalemi yalnız kendi slug'ına `True` döner. Kalemin
    kaldırılmış olup olmadığına bakmaz (çağıran `active_items` ile süzer)."""
    if item.match_kind == GroupItemKind.LABEL:
        return normalize_label(item.file_label) == normalize_label(document_type.file_label)
    if item.match_kind == GroupItemKind.TYPE:
        return item.type_slug == document_type.slug
    return False


def active_items(group: DocumentGroup) -> list[DocumentGroupItem]:
    """Grubun kaldırılmamış kalemleri, sırasıyla."""
    return [item for item in group.items if item.removed_at is None]


# --- seçiciler -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LabelChoice:
    """Etiket seçicisinin bir seçeneği: gösterilen etiket (katalogdaki en sık yazımı), karşılaştırma
    anahtarı ve o etiketi taşıyan tür sayısı."""

    label: str
    key: str
    type_count: int


def label_choices(session: Session, *, include_archived: bool = False) -> list[LabelChoice]:
    """14.1.2 — katalogdaki türlerin dosya etiketleri, tür sayısıyla, etikete göre sıralı.

    Pasif türler de sayılır: pasif türün var olan belgeleri kalemi karşılayabilir. Arşivli türler
    (11.1.6) seçiciye girmez; `include_archived` var olan kalemlerin gösterimi içindir. Yalnız harf
    büyüklüğü ve boşlukla ayrılan yazımlar tek seçenektir (`item_matches` onları zaten aynı sayar);
    "Identity Card" ile "Identity Document" gibi yakın ama ayrı etiketler birleştirilmez — sayılar
    İK'nın farkı görmesi içindir.
    """
    spellings: dict[str, Counter[str]] = {}
    query = select(KnownDocumentType.file_label)
    if not include_archived:
        query = query.where(KnownDocumentType.archived_at.is_(None))
    for raw in session.scalars(query):
        label = _single_line(raw)
        if label:
            spellings.setdefault(label.casefold(), Counter())[label] += 1
    choices = []
    for key, counter in spellings.items():
        # En sık yazım; eşitlikte alfabetik ilk — seçenek her istekte aynı çıkar.
        label = min(counter, key=lambda spelling: (-counter[spelling], spelling))
        choices.append(LabelChoice(label=label, key=key, type_count=sum(counter.values())))
    return sorted(choices, key=lambda choice: (choice.key, choice.label))


@dataclass(frozen=True, slots=True)
class TypeChoice:
    """Tür seçicisinin bir seçeneği."""

    slug: str
    name: str
    country: str | None
    file_label: str
    active: bool


def type_choices(session: Session, *, include_archived: bool = False) -> list[TypeChoice]:
    """Katalogdaki türler (pasifler dahil; arşivliler — 11.1.6 — yalnız `include_archived` ile,
    var olan kalemlerin gösterimi için), ada göre sıralı."""
    query = select(KnownDocumentType)
    if not include_archived:
        query = query.where(KnownDocumentType.archived_at.is_(None))
    rows = session.scalars(query)
    choices = [
        TypeChoice(
            slug=row.slug,
            name=row.name,
            country=(row.country or "").strip() or None,
            file_label=row.file_label,
            active=row.active,
        )
        for row in rows
    ]
    return sorted(choices, key=lambda choice: (choice.name.casefold(), choice.slug))


# --- okuma ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GroupSummary:
    """Grup listesinin bir satırı (14.1.1)."""

    id: int
    name: str
    description: str | None
    item_count: int
    open_packages: int
    archived: bool
    archived_at: datetime | None
    created_by: str
    created_at: datetime


def open_package_counts(session: Session, group_ids: Iterable[int]) -> dict[int, int]:
    """Her grubun açık (`open`: zorunlu kalemi eksik) paket sayısı (14.1.1); liste ve grup sayfası
    bu sayıyı buradan okur. Tamamlanan ve iptal edilen paket sayılmaz."""
    counts = dict.fromkeys(group_ids, 0)
    if not counts:
        return counts
    rows = session.execute(
        select(EmployeePackage.group_id, func.count())
        .where(
            EmployeePackage.group_id.in_(list(counts)),
            EmployeePackage.status == PackageStatus.OPEN.value,
        )
        .group_by(EmployeePackage.group_id)
    )
    for group_id, count in rows:
        counts[group_id] = count
    return counts


def open_package_count(session: Session, group_id: int) -> int:
    """Tek grubun açık paket sayısı (`open_package_counts`)."""
    return open_package_counts(session, [group_id])[group_id]


def list_groups(session: Session, *, include_archived: bool = False) -> list[GroupSummary]:
    """Gruplar, ada göre sıralı; varsayılan yalnız arşivsizler. Kalem sayısı kaldırılmamış
    kalemlerdir."""
    item_counts = dict(
        session.execute(
            select(DocumentGroupItem.group_id, func.count())
            .where(DocumentGroupItem.removed_at.is_(None))
            .group_by(DocumentGroupItem.group_id)
        ).all()
    )
    query = select(DocumentGroup)
    if not include_archived:
        query = query.where(DocumentGroup.archived_at.is_(None))
    groups = sorted(session.scalars(query), key=lambda group: (group.normalized_name, group.id))
    packages = open_package_counts(session, [group.id for group in groups])
    return [
        GroupSummary(
            id=group.id,
            name=group.name,
            description=group.description,
            item_count=item_counts.get(group.id, 0),
            open_packages=packages[group.id],
            archived=group.archived_at is not None,
            archived_at=group.archived_at,
            created_by=group.created_by,
            created_at=group.created_at,
        )
        for group in groups
    ]


def count_archived_groups(session: Session) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(DocumentGroup)
            .where(DocumentGroup.archived_at.isnot(None))
        )
        or 0
    )


def get_group(session: Session, group_id: int) -> DocumentGroup:
    group = session.get(DocumentGroup, group_id)
    if group is None:
        raise GroupNotFoundError(group_id)
    return group


# --- yazma ---------------------------------------------------------------------------------------


@dataclass(slots=True)
class _Problems:
    items: dict[str, list[str]] = field(default_factory=dict)

    def add(self, name: str, message: str) -> None:
        self.items.setdefault(name, []).append(message)

    def raise_if_any(self) -> None:
        if self.items:
            raise GroupFormError(self.items)


def _clean_group_fields(name: str, description: str | None) -> tuple[str, str, str | None]:
    """Ad ve açıklamayı denetler; `(ad, sadeleşmiş ad, açıklama)` ya da `GroupFormError`."""
    problems = _Problems()
    clean_name = _single_line(name)
    normalized = ""
    if not clean_name:
        problems.add("name", NAME_REQUIRED)
    elif len(clean_name) > NAME_MAX_LENGTH:
        problems.add("name", NAME_TOO_LONG)
    else:
        try:
            normalized = normalize_group_name(clean_name)
        except SlugError:
            problems.add("name", NAME_UNUSABLE)
    clean_description = _single_line(description) or None
    if clean_description and len(clean_description) > DESCRIPTION_MAX_LENGTH:
        problems.add("description", DESCRIPTION_TOO_LONG)
    problems.raise_if_any()
    return clean_name, normalized, clean_description


def _ensure_name_free(
    session: Session, name: str, normalized: str, *, own_id: int | None = None
) -> None:
    other = session.scalar(select(DocumentGroup).where(DocumentGroup.normalized_name == normalized))
    if other is not None and other.id != own_id:
        raise GroupNameTakenError(name, archived=other.archived_at is not None)


def _active_item_count(session: Session, group_id: int) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(DocumentGroupItem)
            .where(DocumentGroupItem.group_id == group_id, DocumentGroupItem.removed_at.is_(None))
        )
        or 0
    )


def _record(
    session: Session, group: DocumentGroup, action: GroupAction, *, actor: str, **extra: object
) -> None:
    data: dict[str, object] = {
        "group_id": group.id,
        "action": action.value,
        "item_count": _active_item_count(session, group.id),
        **extra,
    }
    record_event(session, EventType.GROUP_CHANGED, actor=actor, data=data)


def _refresh_packages(session: Session, group: DocumentGroup, *, actor: str) -> None:
    # 14.1.1: kalem değişikliği grubun paketlerine anında yansır; tamamlanan paket yeni zorunlu
    # kalemle açığa döner, eksik kalemi kaldırılan açık paket tamamlanır (olaylarıyla).
    # `app.groups.packages` bu modülü içe aktarır; üst düzeyde içe aktarmak döngü kurar.
    from app.groups.packages import refresh_group_packages

    refresh_group_packages(session, group.id, actor=actor)


def create_group(
    session: Session, *, name: str, description: str | None, actor: str
) -> DocumentGroup:
    """Yeni grup açar (kalemsiz); ad kurala uymazsa `GroupFormError`, aynı sadeleşmiş adla grup
    varsa `GroupNameTakenError`. Aynı anda iki istek biri kazanır (tekil dizin)."""
    clean_name, normalized, clean_description = _clean_group_fields(name, description)
    _ensure_name_free(session, clean_name, normalized)
    group = DocumentGroup(
        name=clean_name,
        normalized_name=normalized,
        description=clean_description,
        created_by=actor,
    )
    try:
        with session.begin_nested():
            session.add(group)
    except IntegrityError:
        raise GroupNameTakenError(clean_name, archived=False) from None
    _record(session, group, GroupAction.CREATE, actor=actor)
    return group


def update_group(
    session: Session, group_id: int, *, name: str, description: str | None, actor: str
) -> bool:
    """Grubun adını ve açıklamasını yazar; bir şey değiştiyse `True` ve olay (değişen alan
    adlarıyla). Hatalar `create_group` ile aynı."""
    group = get_group(session, group_id)
    clean_name, normalized, clean_description = _clean_group_fields(name, description)
    _ensure_name_free(session, clean_name, normalized, own_id=group.id)
    changed = [
        field_name
        for field_name, value in (("name", clean_name), ("description", clean_description))
        if getattr(group, field_name) != value
    ]
    if not changed:
        return False
    try:
        with session.begin_nested():
            group.name = clean_name
            group.normalized_name = normalized
            group.description = clean_description
    except IntegrityError:
        session.refresh(group)
        raise GroupNameTakenError(clean_name, archived=False) from None
    _record(session, group, GroupAction.UPDATE, actor=actor, fields=changed)
    return True


def add_item(
    session: Session,
    group_id: int,
    *,
    match_kind: str,
    file_label: str | None = None,
    type_slug: str | None = None,
    required: bool = True,
    note: str | None = None,
    actor: str,
) -> DocumentGroupItem:
    """Gruba kalem ekler (14.1.2). `label` kalemi katalogda var olan bir dosya etiketi, `type`
    kalemi katalogdaki bir tür ister; etiket katalogdaki yazımıyla saklanır. Kural dışı değer
    `GroupFormError`, grupta aynı etiket ya da tür zaten kalemse `DuplicateGroupItemError`."""
    group = get_group(session, group_id)
    problems = _Problems()
    clean_note = _single_line(note) or None
    if clean_note and len(clean_note) > NOTE_MAX_LENGTH:
        problems.add("note", NOTE_TOO_LONG)
    key = ""
    label_value: str | None = None
    slug_value: str | None = None
    if match_kind == GroupItemKind.LABEL:
        key = normalize_label(file_label)
        choice = next((item for item in label_choices(session) if item.key == key), None)
        if not key:
            problems.add("file_label", LABEL_REQUIRED)
        elif choice is None:
            problems.add("file_label", LABEL_UNKNOWN)
        else:
            label_value = choice.label
    elif match_kind == GroupItemKind.TYPE:
        slug = (type_slug or "").strip()
        if not slug:
            problems.add("type_slug", TYPE_REQUIRED)
        elif (row := session.get(KnownDocumentType, slug)) is None or row.archived_at is not None:
            problems.add("type_slug", TYPE_UNKNOWN)
        else:
            slug_value = slug
    else:
        problems.add("match_kind", MATCH_KIND_INVALID)
    problems.raise_if_any()

    for existing in active_items(group):
        if existing.match_kind != match_kind:
            continue
        if (label_value is not None and normalize_label(existing.file_label) == key) or (
            slug_value is not None and existing.type_slug == slug_value
        ):
            raise DuplicateGroupItemError(label_value or slug_value)

    last = session.scalar(
        select(func.max(DocumentGroupItem.position)).where(DocumentGroupItem.group_id == group.id)
    )
    item = DocumentGroupItem(
        group=group,
        position=(last or 0) + 1,
        match_kind=str(match_kind),
        file_label=label_value,
        type_slug=slug_value,
        required=required,
        note=clean_note,
    )
    session.add(item)
    session.flush()
    _record(
        session,
        group,
        GroupAction.ITEM_ADDED,
        actor=actor,
        item_id=item.id,
        match_kind=item.match_kind,
        required=item.required,
    )
    _refresh_packages(session, group, actor=actor)
    return item


def remove_item(session: Session, group_id: int, item_id: int, *, actor: str) -> DocumentGroupItem:
    """Kalemi gruptan kaldırır: satır kalır, `removed_at`/`removed_by` dolar (R11). Kalem bu grupta
    yoksa ya da zaten kaldırılmışsa `GroupItemNotFoundError`."""
    group = get_group(session, group_id)
    item = session.get(DocumentGroupItem, item_id)
    if item is None or item.group_id != group.id or item.removed_at is not None:
        raise GroupItemNotFoundError(item_id)
    item.removed_at = utcnow()
    item.removed_by = actor
    session.flush()
    _record(
        session,
        group,
        GroupAction.ITEM_REMOVED,
        actor=actor,
        item_id=item.id,
        match_kind=item.match_kind,
    )
    _refresh_packages(session, group, actor=actor)
    return item


def set_group_archived(session: Session, group_id: int, archived: bool, *, actor: str) -> bool:
    """Grubu arşivler ya da arşivden geri alır (tek adım, §D61-b); durum değiştiyse `True` ve
    olay. Arşivli gruba yeni paket tanımlanamaz (`app.groups.packages.assign_package`); açık
    paketleri ve kalemleri olduğu gibi kalır."""
    group = get_group(session, group_id)
    if (group.archived_at is not None) == archived:
        return False
    if archived:
        group.archived_at = utcnow()
        group.archived_by = actor
    else:
        group.archived_at = None
        group.archived_by = None
    session.flush()
    _record(session, group, GroupAction.ARCHIVE if archived else GroupAction.RESTORE, actor=actor)
    return True
