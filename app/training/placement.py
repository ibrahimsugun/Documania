"""Eğitim modunun veri ve yerleştirme temeli (11.9; PLAN.md §C86 "Veri", "Dosya", "Değişmez
güvence").

Eğitim modu yalnız bilinen belgelerin (`app.training.known_types`) örneklerini besler:

- **Çalıştırma (`create_run`).** Bir yükleme ya da harita taraması bir `training_runs` satırıdır;
  sayaçları ve durumu öğelerden yeniden sayılır (`refresh_run`).
- **Staging (`stage_file`).** Yüklenen dosya önce örnek olabilir mi diye denetlenir
  (`check_example`: PDF/JPEG/PNG, okunabilir, boyut sınırı — mekanik tanımanın ilk adımı, 11.9.2);
  olamazsa öğe `failed` olur ve hiçbir dosya yazılmaz. Olabilirse içerik
  `KnownDocuments/_egitim/gelen/<run>/<item>.<ext>`'e atomik yazılır (uzantı içerikten). Inbox'a ve
  `upload_files`'a girilmez: gerçek bir yüklemenin tekrar tespiti (K10) kirlenmez.
- **Yerleştirme (`place_example`).** Öğenin içeriği bilinen türün `examples/<slug>/` klasörüne
  `store_example` ile kopyalanır (K11: yalnız kopya; `_egitim/gelen` kopyası kalır, silme yok) ve
  `example_files`'a yöntem, etiket (`ai` → `ai_decision`, `manual` → `verified`, `mechanical`
  etiketsiz) ve notla kaydedilir. Türler arası tekrar `example_files.sha256` dizininden bulunur:
  aynı içerik aynı türde kayıtlıysa öğe `skipped` ("zaten örnek: <ad>"), başka türde kayıtlıysa
  `conflict` ("başka türde örnek: <slug>"); iki durumda da dosya yazılmaz. Kaynak dosya zaten o
  türün örnek klasöründeyse kopyalanmaz, yerinde kaydedilir. Klasörde kayıtsız duran aynı içerik
  (eğitimden önce konmuş ya da el ile yüklenmiş) `legacy` olarak kaydedilir ve öğe `skipped` olur.
  Örneklerden çıkarılmış kayıt (11.9.4, `app.training.decisions`) tekrar sayılmaz: çıkarılan içerik
  yeniden yerleşebilir.
- **Yerleşmeyen öğe (`leave_unplaced`).** Tanıma bir türe inmediyse (`unplaced`, "Yerleştirilemedi")
  ya da ipucuyla çelişen bir türe indiyse (`conflict`) öğe İK'nın "Türe yerleştir"ini bekler; dosya
  yazılmaz (yapay zekâ yolu, 11.9.3). Harita satırının türü ya da SHA-256'sı dosyayla tutmuyorsa
  öğe `review` ("İnceleme gerekli") olur (toplu tarama, 11.9.5).
- **Denetim ve staging ayrı da çağrılır (`check_content`, `write_staged_copy`).** Toplu tarama
  öğeyi haritadan açar; yerindeki örnek dosyasının (türün örnek klasöründe duran) kopyası yazılmaz.
- **Olaylar (K15).** Yerleşen öğe `TRAINING_EXAMPLE_PLACED`, yerleşmeyen (`skipped`, `conflict`,
  `unplaced`) `TRAINING_ITEM_UNPLACED` yazar; veri kimlikle (çalıştırma, öğe, örnek kaydı) ve türle
  yazılır, dosya adı ve kişisel değer yazılmaz (CONVENTIONS §6). Çağıran olay verisine ek alan
  verebilir (`event_data`: yapay zekâ adımının sağlayıcı, model ve kullanımı, 13.1.1).

**Değişmez güvence.** Bu modül `uploads`, `upload_files`, `pages`, `plans`, çalışan tabloları,
`queue_items`, `documents` ve `candidate_document_types`'a yazmaz; Inbox, Employees ve kuyruk
dizinlerine dosya koymaz; kişi eşleştirmesi, profil alanı ve iletişim birikimi çalışmaz.

Fonksiyonlar işlemi commit etmez; iş birimini çağıran kapatır. Dosya yazıldıktan sonra işlem geri
alınırsa yazılan dosya kalır (silme yok); aynı içerik yeniden yerleştirilince klasördeki kayıtsız
kopya bulunur (`legacy`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ExampleFileRecord,
    ExampleLabel,
    ExampleMethod,
    TrainingItem,
    TrainingItemStatus,
    TrainingMethod,
    TrainingRun,
    TrainingRunKind,
    TrainingRunStatus,
    utcnow,
)
from app.events import EventType, record_event
from app.storage import ContentMismatchError, DataLayout, FileKind, sha256_bytes, write_file
from app.storage.examples import (
    EXAMPLE_EXTENSIONS,
    ExampleRejectedError,
    check_example,
    example_path,
    store_example,
)
from app.storage.filetype import UnsupportedFileTypeError, detect_file_kind
from app.training.known_types import KnownTypes

SYSTEM_ACTOR = "system"
LEGACY_NOTE = "Eğitimden önce örnek klasörüne konmuş; kaydı eğitimde tutuldu."
_NAME_MAX_LENGTH = 255

LABEL_BY_METHOD = MappingProxyType(
    {
        TrainingMethod.MECHANICAL: None,
        TrainingMethod.AI: ExampleLabel.AI_DECISION,
        TrainingMethod.MANUAL: ExampleLabel.VERIFIED,
    }
)
"""Yerleşen örneğin etiketi yöntemden gelir (§C86): mekanik etiketsiz, yapay zekâ "AI kararı",
İK'nın yerleştirmesi doğrulanmış."""

PLACEABLE_STATUSES = frozenset(
    {
        TrainingItemStatus.QUEUED,
        TrainingItemStatus.AI_PENDING,
        TrainingItemStatus.UNPLACED,
        TrainingItemStatus.CONFLICT,
        TrainingItemStatus.REVIEW,
    }
)
"""Yerleştirilebilen öğe durumları: sistemin kararını bekleyen (`queued`, `ai_pending`) ve İK'nın
"Türe yerleştir"ini bekleyen (`unplaced`, `conflict`, `review`). `placed`, `skipped` ve `failed`
son karardır."""

UNPLACED_STATUSES = frozenset(
    {TrainingItemStatus.UNPLACED, TrainingItemStatus.CONFLICT, TrainingItemStatus.REVIEW}
)
"""`leave_unplaced`'in kararları: İK'nın "Türe yerleştir"ini bekleyen durumlar."""

PENDING_STATUSES = frozenset({TrainingItemStatus.QUEUED, TrainingItemStatus.AI_PENDING})
"""Çalıştırmayı `running` tutan durumlar: kararı sistemde bekleyen öğe."""


class UnknownTypeError(ValueError):
    """Tür bilinen türlerden (katalog + önerilen) değil; örnek yerleştirilmez."""


class ItemNotPlaceableError(ValueError):
    """Öğe son kararında ya da yerleştirilecek dosyası yok."""


@dataclass(frozen=True, slots=True)
class Placement:
    """`place_example` sonucu. `status`: `placed`, `skipped` ya da `conflict`. `example`: yerleşen
    örneğin yeni kaydı ya da yerleşmeyi engelleyen var olan kayıt. `copied`: dosya örnek klasörüne
    bu çağrıda kopyalandı (yerinde kayıtta ve yerleşmeyen öğede `False`)."""

    status: TrainingItemStatus
    note: str
    example: ExampleFileRecord
    copied: bool


def create_run(
    session: Session, *, kind: TrainingRunKind, created_by: str, map_name: str | None = None
) -> TrainingRun:
    """Yeni eğitim çalıştırması (`running`, sayaçlar boş); commit etmez."""
    run = TrainingRun(
        kind=kind.value,
        created_by=created_by,
        map_name=map_name,
        status=TrainingRunStatus.RUNNING.value,
        counts_json={},
    )
    session.add(run)
    session.flush()
    return run


def stage_file(
    session: Session,
    layout: DataLayout,
    run: TrainingRun,
    original_name: str,
    content: bytes,
    *,
    max_bytes: int,
    hint_slug: str | None = None,
    row_number: int | None = None,
    source_ref: str | None = None,
) -> TrainingItem:
    """Eğitim öğesini açar ve içeriğini `_egitim/gelen/<run>/<item>.<ext>`'e atomik yazar.

    Örnek olamayan dosya (`check_example`) `failed` olur, notu reddin gerekçesidir ve dosya
    yazılmaz. Olabilen dosyanın öğesi `queued` kalır; SHA-256, dosya türü ve sayfa sayısı dolar.
    Yazma kesilirse hedefte dosya olmaz (`write_file`) ve istisna çağırana geçer. Commit etmez.
    """
    item = TrainingItem(
        run=run,
        original_name=_display_name(original_name),
        hint_slug=hint_slug,
        row_number=row_number,
        source_ref=source_ref,
        status=TrainingItemStatus.QUEUED.value,
    )
    session.add(item)
    session.flush()
    if check_content(item, original_name, content, max_bytes=max_bytes):
        write_staged_copy(layout, item, content)
    refresh_run(session, run)
    return item


def check_content(
    item: TrainingItem, original_name: str, content: bytes, *, max_bytes: int
) -> bool:
    """Staging'in denetimi (`check_example`, mekanik adım 1): içerik örnek olabiliyorsa öğenin
    SHA-256'sı, dosya türü ve sayfa sayısı dolar (`True`); olamıyorsa öğe `failed` olur, notu reddin
    gerekçesidir (`False`). Dosya yazmaz ve çalıştırmayı yeniden saymaz."""
    try:
        kind = check_example(original_name, content, max_bytes=max_bytes)
    except ExampleRejectedError as exc:
        _decide(item, TrainingItemStatus.FAILED, note=str(exc), actor=SYSTEM_ACTOR)
        return False
    item.sha256 = sha256_bytes(content)
    item.file_kind = kind.value
    item.page_count = _page_count(kind, content)
    return True


def write_staged_copy(layout: DataLayout, item: TrainingItem, content: bytes) -> None:
    """Denetimden geçmiş (`check_content`) içeriği `_egitim/gelen/<run>/<item>.<ext>`'e atomik
    yazar ve `staged_path`'i doldurur. Yazma kesilirse hedefte dosya olmaz, istisna çağırana geçer;
    içerik öğenin SHA-256'sıyla tutmuyorsa `ContentMismatchError` (hiçbir şey yazılmaz)."""
    if item.file_kind is None:
        raise ItemNotPlaceableError(f"Öğe {item.id} denetimden geçmemiş")
    if item.sha256 is not None and item.sha256 != sha256_bytes(content):
        raise ContentMismatchError(f"Öğe {item.id} içeriği kaydındaki SHA-256 ile tutmuyor")
    kind = FileKind(item.file_kind)
    target = layout.training_staged_path(item.run_id, item.id, EXAMPLE_EXTENSIONS[kind])
    stored = write_file(target, content)
    item.staged_path = layout.relative(stored.path)


def fail_item(
    session: Session, item: TrainingItem, *, note: str, actor: str = SYSTEM_ACTOR
) -> None:
    """Öğeyi `failed` kararına bağlar ("Hatalı": dosya okunamadı, örnek olamaz ya da işlenemedi) ve
    çalıştırmayı yeniden sayar; olay yazmaz (staging'in reddi gibi) ve commit etmez."""
    _decide(item, TrainingItemStatus.FAILED, note=note, actor=actor)
    refresh_run(session, item.run)


def place_example(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    item: TrainingItem,
    slug: str,
    *,
    method: TrainingMethod,
    note: str | None = None,
    actor: str = SYSTEM_ACTOR,
    source: Path | None = None,
    event_data: Mapping[str, object] | None = None,
) -> Placement:
    """Öğeyi `slug` türünün örneklerine yerleştirir (modül açıklaması); commit etmez.

    Kaynak `source` verilmezse öğenin `_egitim/gelen` kopyasıdır. `note` tanımanın notudur (Türkçe,
    kişisel değersiz); yerleşmeyen öğede gerekçe arkasına eklenir. `actor` olayın ve kararın
    sahibidir (İK'nın yerleştirmesinde kullanıcı adı). `event_data` olayın verisine eklenir. Tür
    bilinmiyorsa `UnknownTypeError`, öğe
    son kararındaysa ya da dosyası yoksa `ItemNotPlaceableError`, içerik öğenin SHA-256'sıyla
    tutmuyorsa `ContentMismatchError` — üçünde de hiçbir şey yazılmaz.
    """
    if slug not in known:
        raise UnknownTypeError(f"Bilinmeyen tür: {slug!r}")
    if item.status not in PLACEABLE_STATUSES:
        raise ItemNotPlaceableError(f"Öğe {item.id} son kararında: {item.status}")
    path = source if source is not None else _staged_path(layout, item)
    content = path.read_bytes()
    sha256 = sha256_bytes(content)
    if item.sha256 is not None and item.sha256 != sha256:
        raise ContentMismatchError(f"Öğe {item.id} içeriği kaydındaki SHA-256 ile tutmuyor")
    kind = _example_kind(content, item)
    item.sha256 = sha256
    item.file_kind = kind.value
    if item.page_count is None:
        item.page_count = _page_count(kind, content)

    recorded = session.scalars(
        select(ExampleFileRecord)
        .where(ExampleFileRecord.sha256 == sha256, ExampleFileRecord.removed_at.is_(None))
        .order_by(ExampleFileRecord.id)
    ).all()
    same_type = [record for record in recorded if record.type_slug == slug]
    extra = dict(event_data or {})
    if same_type:
        return _not_placed(
            session, item, slug, method, note, actor, same_type[0], skipped=True, extra=extra
        )
    if recorded:
        return _not_placed(
            session, item, slug, method, note, actor, recorded[0], skipped=False, extra=extra
        )

    name = _in_place_name(layout, slug, path)
    copied = name is None
    if name is None:
        stored = store_example(layout, slug, item.original_name, content, kind)
        if stored.duplicate:
            legacy = _record_legacy(session, slug, stored.name, sha256)
            return _not_placed(
                session, item, slug, method, note, actor, legacy, skipped=True, extra=extra
            )
        name = stored.name

    label = LABEL_BY_METHOD[method]
    example = ExampleFileRecord(
        type_slug=slug,
        name=name,
        sha256=sha256,
        method=method.value,
        label=label.value if label is not None else None,
        note=note,
        training_item=item,
    )
    session.add(example)
    _decide(
        item, TrainingItemStatus.PLACED, slug=slug, method=method, note=note or None, actor=actor
    )
    session.flush()
    record_event(
        session,
        EventType.TRAINING_EXAMPLE_PLACED,
        actor=actor,
        message=f"Eğitim örneği `{slug}` türüne yerleşti ({method.value}).",
        data={
            "run_id": item.run_id,
            "training_item_id": item.id,
            "example_file_id": example.id,
            "type_slug": slug,
            "method": method.value,
            "label": example.label,
            "in_place": not copied,
        }
        | extra,
    )
    refresh_run(session, item.run)
    return Placement(TrainingItemStatus.PLACED, note or "", example, copied)


def leave_unplaced(
    session: Session,
    item: TrainingItem,
    status: TrainingItemStatus,
    *,
    note: str,
    method: TrainingMethod,
    slug: str | None = None,
    actor: str = SYSTEM_ACTOR,
    event_data: Mapping[str, object] | None = None,
    message: str | None = None,
) -> None:
    """Öğeyi yerleştirmeden karara bağlar: `unplaced` (hiçbir bilinen türe inmedi), `conflict`
    (`slug` türüne indi ama ipucuyla çelişiyor) ya da `review` (harita satırı, 11.9.5: haritanın
    türü ya da SHA-256'sı dosyayla tutmuyor); öğe İK'nın "Türe yerleştir"ini bekler.
    `TRAINING_ITEM_UNPLACED` yazar (`event_data` verisine eklenir; `message` verilmezse durumun
    mesajı) ve çalıştırmayı yeniden sayar; commit etmez. Başka bir durum `ValueError`, öğe son
    kararındaysa `ItemNotPlaceableError`.
    """
    if status not in UNPLACED_STATUSES:
        raise ValueError(
            f"Yerleşmeyen öğenin durumu unplaced, conflict ya da review olur: {status}"
        )
    if item.status not in PLACEABLE_STATUSES:
        raise ItemNotPlaceableError(f"Öğe {item.id} son kararında: {item.status}")
    _decide(item, status, slug=slug, method=method, note=note, actor=actor)
    session.flush()
    if message is None and status is TrainingItemStatus.UNPLACED:
        message = "Eğitim öğesi yerleşmedi: hiçbir bilinen türe inmedi."
    elif message is None and status is TrainingItemStatus.REVIEW:
        message = "Eğitim öğesi yerleşmedi: harita satırı İK incelemesi bekliyor."
    elif message is None:
        message = f"Eğitim öğesi yerleşmedi: sonuç `{slug}` beklenen türle çelişiyor."
    record_event(
        session,
        EventType.TRAINING_ITEM_UNPLACED,
        actor=actor,
        message=message,
        data={
            "run_id": item.run_id,
            "training_item_id": item.id,
            "status": status.value,
            "type_slug": slug,
            "hint_slug": item.hint_slug,
        }
        | dict(event_data or {}),
    )
    refresh_run(session, item.run)


def refresh_run(session: Session, run: TrainingRun) -> TrainingRun:
    """Çalıştırmanın sayaçlarını öğelerden yeniden sayar; kararı sistemde bekleyen öğe yoksa
    durum `done`, varsa `running`. Commit etmez."""
    session.flush()
    counts = dict(
        session.execute(
            select(TrainingItem.status, func.count())
            .where(TrainingItem.run_id == run.id)
            .group_by(TrainingItem.status)
        )
        .tuples()
        .all()
    )
    run.counts_json = {
        status.value: counts[status] for status in TrainingItemStatus if counts.get(status)
    }
    pending = any(counts.get(status) for status in PENDING_STATUSES)
    run.status = (TrainingRunStatus.RUNNING if pending else TrainingRunStatus.DONE).value
    session.flush()
    return run


def _not_placed(
    session: Session,
    item: TrainingItem,
    slug: str,
    method: TrainingMethod,
    note: str | None,
    actor: str,
    existing: ExampleFileRecord,
    *,
    skipped: bool,
    extra: Mapping[str, object],
) -> Placement:
    if skipped:
        status = TrainingItemStatus.SKIPPED
        reason = f"zaten örnek: {existing.name}"
        message = f"Eğitim öğesi yerleşmedi: aynı içerik `{slug}` türünde zaten örnek."
    else:
        status = TrainingItemStatus.CONFLICT
        reason = f"başka türde örnek: {existing.type_slug}"
        message = (
            f"Eğitim öğesi yerleşmedi: aynı içerik başka türde örnek "
            f"(`{existing.type_slug}`, önerilen `{slug}`)."
        )
    full_note = "; ".join(part for part in (note, reason) if part)
    _decide(item, status, slug=slug, method=method, note=full_note, actor=actor)
    session.flush()
    record_event(
        session,
        EventType.TRAINING_ITEM_UNPLACED,
        actor=actor,
        message=message,
        data={
            "run_id": item.run_id,
            "training_item_id": item.id,
            "status": status.value,
            "type_slug": slug,
            "example_file_id": existing.id,
            "example_type_slug": existing.type_slug,
        }
        | dict(extra),
    )
    refresh_run(session, item.run)
    return Placement(status, full_note, existing, copied=False)


def _record_legacy(session: Session, slug: str, name: str, sha256: str) -> ExampleFileRecord:
    """Klasörde kayıtsız duran örneğin kaydı (etiketsiz); aynı ad kayıtlıysa o kayıt."""
    existing = session.scalar(
        select(ExampleFileRecord).where(
            ExampleFileRecord.type_slug == slug,
            ExampleFileRecord.name == name,
            ExampleFileRecord.removed_at.is_(None),
        )
    )
    if existing is not None:
        return existing
    legacy = ExampleFileRecord(
        type_slug=slug,
        name=name,
        sha256=sha256,
        method=ExampleMethod.LEGACY.value,
        label=None,
        note=LEGACY_NOTE,
    )
    session.add(legacy)
    session.flush()
    return legacy


def _decide(
    item: TrainingItem,
    status: TrainingItemStatus,
    *,
    note: str | None,
    actor: str,
    slug: str | None = None,
    method: TrainingMethod | None = None,
) -> None:
    item.status = status.value
    item.note = note
    item.decided_by = actor
    item.decided_at = utcnow()
    if slug is not None:
        item.result_slug = slug
    if method is not None:
        item.method = method.value


def _staged_path(layout: DataLayout, item: TrainingItem) -> Path:
    if item.staged_path is None:
        raise ItemNotPlaceableError(f"Öğe {item.id} için yerleştirilecek dosya yok")
    return layout.resolve(item.staged_path)


def _in_place_name(layout: DataLayout, slug: str, path: Path) -> str | None:
    """Kaynak dosya türün örnek klasöründe listelenen bir örnekse adı; değilse `None`."""
    listed = example_path(layout, slug, path.name)
    if listed is None or listed.resolve() != path.resolve():
        return None
    return listed.name


def _example_kind(content: bytes, item: TrainingItem) -> FileKind:
    try:
        kind = detect_file_kind(content)
    except UnsupportedFileTypeError:
        kind = None
    if kind is None or kind not in EXAMPLE_EXTENSIONS:
        raise ItemNotPlaceableError(f"Öğe {item.id} PDF, JPEG ya da PNG değil")
    return kind


def _page_count(kind: FileKind, content: bytes) -> int:
    if kind is FileKind.PDF:
        return len(PdfReader(BytesIO(content)).pages)
    return 1


def _display_name(original_name: str) -> str:
    name = PurePosixPath(original_name.replace("\\", "/")).name or "adsız dosya"
    return name[:_NAME_MAX_LENGTH]
