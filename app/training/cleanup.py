"""Eğitim temizliği (PRD 11.9.6; PLAN.md §C92-c, §D58, §D61-b; R11, K15).

Eğitim koşuları yüzlerce çalıştırma ve yerleşemeyen öğe bırakabilir; tür sayfasından yüklenen
örneklerin kaydı yoktu. Bu modül ikisini de silmeden toparlar:

- **Öğeyi yoksay (`dismiss_item`).** "Yerleştirilemedi" (`unplaced`), "Çelişki" (`conflict`) ya da
  "İnceleme gerekli" (`review`) öğe tek adımda `dismissed` olur (§D61-b: salt durum çevirir, geri
  alınabilir). Dosya yazılmaz, taşınmaz, silinmez: `_egitim/gelen` kopyası yerinde kalır (R11) ve
  örnek kaydı açılmaz. İK'nın isteğe bağlı notu (en çok `NOTE_MAX_LENGTH`) öğenin notuna eklenir;
  sistemin gerekçesi silinmez. `TRAINING_ITEM_DISMISSED` (öğe, çalıştırma, önceki durum) kullanıcı
  adıyla yazılır; not ve dosya adı olaya girmez (CONVENTIONS §6). Çalıştırma yeniden sayılır:
  sayaçlara `dismissed` ("yoksayılan") eklenir, eskileri değişmez.
- **Geri al (`restore_item`).** Yalnız `dismissed` öğe `unplaced`'e döner (§C92-c) ve yeniden
  "Türe yerleştir"i bekler; `TRAINING_ITEM_RESTORED`.
- **Çalıştırmayı arşivle / geri al (`archive_run`, `restore_run`).** `training_runs.archived_at`
  dolar ya da boşalır; öğeler, örnek dosyaları ve `example_files` değişmez. Arşivli çalıştırma
  listeden ve üst sayaçlardan kalkar (panel süzer). İkisi de `TRAINING_RUN_ARCHIVED` yazar
  (`restored` geri almada `true`).
- **Tür sayfasından yüklenen örneğin kaydı (`record_uploaded_example`).** El ile yükleme (11.2.1)
  artık `example_files` satırı da yazar: yöntem `manual`, etiket `verified`, öğesiz, not
  `UPLOADED_NOTE`. Olay **yazılmaz** — 11.2.1'in olaysızlığı korunur (§D58 e); kayıt ile olay
  ayrımı budur. Aynı içerik aynı türde ikinci kez eklenmez (11.9.2): `same_type_example` çağıranın
  ön denetimidir.
- **Kayıtsız örneklerin kaydı (`register_examples`).** `examples/<slug>/` klasörlerinde listelenen
  ama etkin kaydı olmayan dosyalar SHA-256'larıyla bir kez `legacy` kaydedilir (etiketsiz, not
  `REGISTERED_NOTE`); ikinci koşu hiçbir şey eklemez. Olay yazmaz (katalog malzemesi, eğitim
  kararı değil). Komut: `python -m app.catalog register-examples`.

Değişmez güvence `app.training.placement`'takiyle aynıdır: çalışan tarafına (parti, dosya, sayfa,
plan, çalışan, kuyruk, belge) hiçbir şey yazılmaz. Durum değişiklikleri koşullu güncellemedir: aynı
öğeyi aynı anda yerleştiren ya da yoksayan iki işlemden yalnız biri geçer. Fonksiyonlar commit
etmez; iş birimini çağıran kapatır.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import (
    ExampleFileRecord,
    ExampleLabel,
    ExampleMethod,
    TrainingItem,
    TrainingItemStatus,
    TrainingRun,
    utcnow,
)
from app.events import EventType, record_event
from app.storage import DataLayout, sha256_file
from app.storage.examples import StoredExample, list_examples
from app.training.placement import UNPLACED_STATUSES, refresh_run

NOTE_MAX_LENGTH = 200
DISMISSABLE_STATUSES = UNPLACED_STATUSES
"""Yoksayılabilen durumlar: İK'nın "Türe yerleştir"ini bekleyenler (`unplaced`, `conflict`,
`review`). Kararı sistemde bekleyen ya da son kararındaki öğe yoksayılmaz."""

UPLOADED_NOTE = "tür sayfasından yüklendi"
REGISTERED_NOTE = "Kayıtsız örnek; kaydı register-examples ile tutuldu."
DISMISSED_NOTE = "İK yoksaydı"
RESTORED_NOTE = "İK yoksaymayı geri aldı"

NOT_DISMISSABLE = (
    "Bu öğe yoksayılamaz: yalnız Yerleştirilemedi, Çelişki ya da İnceleme gerekli durumundaki öğe "
    "yoksayılır."
)
NOT_DISMISSED = "Bu öğe yoksayılmamış; geri alınacak bir şey yok."
NOTE_TOO_LONG = f"Not en çok {NOTE_MAX_LENGTH} karakter olabilir."
RUN_ALREADY_ARCHIVED = "Bu çalıştırma zaten arşivde."
RUN_NOT_ARCHIVED = "Bu çalıştırma arşivde değil; geri alınacak bir şey yok."


class CleanupError(ValueError):
    """Temizlik işlemi uygulanamaz (öğe yoksayılamaz / yoksayılmamış, çalıştırma zaten arşivde /
    arşivde değil); mesaj kullanıcıya gösterilir, hiçbir şey yazılmadı."""


class CleanupNoteError(ValueError):
    """Yoksayma notu çok uzun; hiçbir şey yazılmadı."""


def clean_note(note: str | None) -> str | None:
    """Notun saklanacak biçimi: baştaki ve sondaki boşluk atılır, boş not `None`; çok uzun not
    `CleanupNoteError`."""
    text = (note or "").strip()
    if len(text) > NOTE_MAX_LENGTH:
        raise CleanupNoteError(NOTE_TOO_LONG)
    return text or None


# --- öğeyi yoksay / geri al -------------------------------------------------------------------


def dismiss_item(
    session: Session, item: TrainingItem, *, actor: str, note: str | None = None
) -> TrainingItem:
    """Öğeyi yoksayar (`dismissed`; modül açıklaması). Öğe yoksayılabilir durumda değilse
    `CleanupError`, not çok uzunsa `CleanupNoteError` — ikisinde de hiçbir şey yazılmaz."""
    _require_actor(actor)
    text = clean_note(note)
    previous = item.status
    addition = f"{DISMISSED_NOTE}: {text}" if text else DISMISSED_NOTE
    _transition(
        session,
        item,
        allowed=DISMISSABLE_STATUSES,
        status=TrainingItemStatus.DISMISSED,
        note=_append(item.note, addition),
        actor=actor,
        refusal=NOT_DISMISSABLE,
    )
    record_event(
        session,
        EventType.TRAINING_ITEM_DISMISSED,
        actor=actor,
        message="Eğitim öğesi yoksayıldı.",
        data={
            "training_item_id": item.id,
            "run_id": item.run_id,
            "previous_status": previous,
            "status": TrainingItemStatus.DISMISSED.value,
        },
    )
    refresh_run(session, item.run)
    return item


def restore_item(session: Session, item: TrainingItem, *, actor: str) -> TrainingItem:
    """Yoksayılmış öğeyi `unplaced`'e döndürür; yoksayılmamışsa `CleanupError` (hiçbir şey
    yazılmaz)."""
    _require_actor(actor)
    _transition(
        session,
        item,
        allowed=frozenset({TrainingItemStatus.DISMISSED}),
        status=TrainingItemStatus.UNPLACED,
        note=_append(item.note, RESTORED_NOTE),
        actor=actor,
        refusal=NOT_DISMISSED,
    )
    record_event(
        session,
        EventType.TRAINING_ITEM_RESTORED,
        actor=actor,
        message="Eğitim öğesinin yoksayılması geri alındı.",
        data={
            "training_item_id": item.id,
            "run_id": item.run_id,
            "previous_status": TrainingItemStatus.DISMISSED.value,
            "status": TrainingItemStatus.UNPLACED.value,
        },
    )
    refresh_run(session, item.run)
    return item


def _transition(
    session: Session,
    item: TrainingItem,
    *,
    allowed: frozenset[TrainingItemStatus],
    status: TrainingItemStatus,
    note: str,
    actor: str,
    refusal: str,
) -> None:
    """Koşullu güncelleme: öğe hâlâ `allowed` durumlarındaysa yeni durum, not ve karar sahibi
    yazılır; değilse (bu arada başka bir işlem değiştirdiyse de) `CleanupError`."""
    if item.status not in allowed:
        raise CleanupError(refusal)
    session.flush()
    result = session.execute(
        update(TrainingItem)
        .where(
            TrainingItem.id == item.id,
            TrainingItem.status.in_([value.value for value in allowed]),
        )
        .values(status=status.value, note=note, decided_by=actor, decided_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.expire(item)
        raise CleanupError(refusal)
    session.refresh(item)


# --- çalıştırmayı arşivle / geri al -----------------------------------------------------------


def archive_run(session: Session, run: TrainingRun, *, actor: str) -> TrainingRun:
    """Çalıştırmayı arşivler (`archived_at`); zaten arşivdeyse `CleanupError`. Öğeler ve örnekler
    değişmez."""
    return _set_run_archive(session, run, actor=actor, archived=True)


def restore_run(session: Session, run: TrainingRun, *, actor: str) -> TrainingRun:
    """Arşivli çalıştırmayı geri alır (`archived_at` boşalır); arşivde değilse `CleanupError`."""
    return _set_run_archive(session, run, actor=actor, archived=False)


def _set_run_archive(
    session: Session, run: TrainingRun, *, actor: str, archived: bool
) -> TrainingRun:
    _require_actor(actor)
    session.flush()
    column = TrainingRun.archived_at
    condition = column.is_(None) if archived else column.is_not(None)
    result = session.execute(
        update(TrainingRun)
        .where(TrainingRun.id == run.id, condition)
        .values(archived_at=utcnow() if archived else None)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.expire(run)
        raise CleanupError(RUN_ALREADY_ARCHIVED if archived else RUN_NOT_ARCHIVED)
    session.refresh(run)
    record_event(
        session,
        EventType.TRAINING_RUN_ARCHIVED,
        actor=actor,
        message=(
            f"Eğitim çalıştırması #{run.id} arşivlendi."
            if archived
            else f"Eğitim çalıştırması #{run.id} arşivden geri alındı."
        ),
        data={"run_id": run.id, "restored": not archived},
    )
    return run


# --- katalog örneklerinin kaydı ---------------------------------------------------------------


def same_type_example(
    session: Session, slug: str, sha256: str, listed: dict[str, str] | None = None
) -> str | None:
    """Aynı içerik (SHA-256) bu türde zaten örnekse adı: etkin kaydı ya da (kaydı olmayan eski
    dosya için) `listed` — türün klasöründeki dosyaların SHA-256 → ad dizini (`listed_hashes`)."""
    name = session.scalar(
        select(ExampleFileRecord.name)
        .where(
            ExampleFileRecord.type_slug == slug,
            ExampleFileRecord.sha256 == sha256,
            ExampleFileRecord.removed_at.is_(None),
        )
        .order_by(ExampleFileRecord.id)
        .limit(1)
    )
    if name is not None:
        return name
    return (listed or {}).get(sha256)


def listed_hashes(layout: DataLayout, slug: str) -> dict[str, str]:
    """Türün klasöründe listelenen örneklerin SHA-256 → ad dizini (aynı içerikte ilk ad)."""
    directory = layout.type_examples_dir(slug)
    hashes: dict[str, str] = {}
    for example in list_examples(layout, slug):
        try:
            hashes.setdefault(sha256_file(directory / example.name), example.name)
        except FileNotFoundError:  # listeleme ile okuma arasında kalktı
            continue
    return hashes


def record_uploaded_example(
    session: Session, slug: str, stored: StoredExample
) -> ExampleFileRecord:
    """Tür sayfasından yüklenen örneğin kaydı (`manual`, `verified`, öğesiz); olay yazmaz. Aynı
    adla etkin kayıt varsa kısmi tekil dizin flush'ta `IntegrityError` verir. Commit etmez."""
    record = ExampleFileRecord(
        type_slug=slug,
        name=stored.name,
        sha256=stored.sha256,
        method=ExampleMethod.MANUAL.value,
        label=ExampleLabel.VERIFIED.value,
        note=UPLOADED_NOTE,
        training_item_id=None,
    )
    session.add(record)
    session.flush()
    return record


@dataclass(frozen=True, slots=True)
class RegisterResult:
    """`register_examples` sonucu: taranan tür klasörü, listelenen dosya, zaten kayıtlı olan ve bu
    koşuda kaydedilen dosya sayıları."""

    types: int
    listed: int
    recorded: int
    registered: int


def register_examples(
    session: Session,
    layout: DataLayout,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> RegisterResult:
    """Kaydı olmayan örnek dosyalarını `legacy` kaydeder (modül açıklaması); commit etmez.
    SHA-256 yalnız kayıtsız dosyalar için hesaplanır; `progress(i, n)` her dosyadan sonra çağrılır
    (büyük klasörde ilerleme). Listeleme ile okuma arasında kalkan dosya atlanır."""
    active = set(
        session.execute(
            select(ExampleFileRecord.type_slug, ExampleFileRecord.name).where(
                ExampleFileRecord.removed_at.is_(None)
            )
        ).tuples()
    )
    slugs = _example_slugs(layout)
    listed = 0
    pending: list[tuple[str, str]] = []
    for slug in slugs:
        for example in list_examples(layout, slug):
            listed += 1
            if (slug, example.name) not in active:
                pending.append((slug, example.name))
    registered = 0
    for index, (slug, name) in enumerate(pending, start=1):
        try:
            sha256 = sha256_file(layout.type_examples_dir(slug) / name)
        except FileNotFoundError:
            sha256 = None
        if sha256 is not None:
            session.add(
                ExampleFileRecord(
                    type_slug=slug,
                    name=name,
                    sha256=sha256,
                    method=ExampleMethod.LEGACY.value,
                    label=None,
                    note=REGISTERED_NOTE,
                )
            )
            registered += 1
        if progress is not None:
            progress(index, len(pending))
    session.flush()
    return RegisterResult(
        types=len(slugs), listed=listed, recorded=listed - len(pending), registered=registered
    )


def _example_slugs(layout: DataLayout) -> list[str]:
    """`examples/` altındaki tür klasörleri (slug olabilen adlar, ad sırasıyla)."""
    try:
        with os.scandir(layout.examples) as scanned:
            names = [entry.name for entry in scanned if entry.is_dir(follow_symlinks=False)]
    except FileNotFoundError:
        return []
    slugs = []
    for name in sorted(names):
        try:
            layout.type_examples_dir(name)
        except ValueError:
            continue
        slugs.append(name)
    return slugs


def _require_actor(actor: str) -> None:
    if not actor.strip():
        raise ValueError("Eğitim temizliği kullanıcı adıyla loglanır: actor boş olamaz")


def _append(note: str | None, addition: str) -> str:
    return f"{note}; {addition}" if note else addition
