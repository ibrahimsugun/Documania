"""Ham eğitim verisini boşaltma (PRD 11.9.10; PLAN.md §D135 d–f).

Eğitim ve katalog **malzemesinin** ham dosyaları kalıcı silinir; örnek bundan sonra kalıcı örnek
dizini kaydı ve kalıcı önizlemesiyle yaşar (tm 201). Arşiv yapılmaz, geri dönüş yoktur (§D135 e).
Çalışan belgesine bu modül hiçbir koşulda dokunmaz.

Bölümler (`SECTIONS`) ve dokunulan tek yerler — izinli kökler sabittir, yollar `DataLayout`'tan:

- `gelen` — `_egitim/gelen/<run>/`: yalnız `done` çalıştırmaların dosyaları; öğelerin
  `staged_path`'i boşalır. İşlemdeki (`running`) çalıştırma ve kaydı olmayan dizin atlanır.
- `examples` — `examples/<tur_slug>/<örnek>`: iki kalıcı önizlemesi olan örneğin ham dosyası;
  dizin satırı `removed` olur. Önizlemesi üretilemeyen örnek atlanır
  (`include_unpreviewable` ile o da silinir, yer tutucuyla görünür).
- `cikarilan` — `_egitim/cikarilan*/`: örneklerden çıkarılanların arşivi (kayıtları kalır).
- `_referans` — harici toplayıcının çıktısı.

`_egitim/haritalar`, `catalog.yaml`, `_sablonlar`, `_onizlemeler` ve çalışan verisi KALIR.

Sıra (`prepare` → `purge`): önce dizin diskle eşitlenir ve eksik önizlemeler üretilir, sonra
silinir. Kuru çalıştırma (`apply=False`) yalnız önizleme ve dizin yazar, hiçbir ham dosyayı
silmez. Her silme adımı kendi işlemiyle commit edilir: kesilen koşu yeniden çalıştırılınca kalanı
siler, ikinci koşu 0 dosya siler. Silmeden sonra `TRAINING_ORIGINALS_PURGED` yazılır (bölüm başına
dosya ve bayt; ad ya da içerik yok).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import TrainingItem, TrainingRun, TrainingRunStatus
from app.events import EventType, record_event
from app.i18n import N_, Translatable
from app.storage import DataLayout
from app.storage.examples import (
    IndexSync,
    example_path,
    example_slugs,
    index_entry,
    indexed_slugs,
    list_examples,
    mark_original_removed,
    sync_example_index,
)
from app.storage.previews import PREVIEW_SIZES, ensure_preview
from app.training.placement import UNPLACED_STATUSES

INCOMING = "gelen"
EXAMPLES = "examples"
REMOVED = "cikarilan"
REFERENCE = "_referans"
SECTIONS = (INCOMING, EXAMPLES, REMOVED, REFERENCE)
"""Raporun ve olayın bölüm adları (sabit sıra)."""

ACTOR = "system"


@dataclass(slots=True)
class Totals:
    """Bir bölümün dosya ve bayt sayısı."""

    files: int = 0
    bytes: int = 0

    def add(self, size: int) -> None:
        self.files += 1
        self.bytes += size

    def as_dict(self) -> dict[str, int]:
        return {"files": self.files, "bytes": self.bytes}


@dataclass(frozen=True, slots=True)
class PlannedExample:
    """Ham dosyası klasörde duran örnek ve iki kalıcı önizlemesinin olup olmadığı."""

    type_slug: str
    name: str
    size: int
    previewable: bool


@dataclass(slots=True)
class PurgeReport:
    """Boşaltmanın raporu. `planned`: silinecek (kuru çalıştırmada silinebilecek) dosya ve bayt;
    `deleted`: gerçekten silinen. `unpreviewable`: önizlemesi üretilemeyen örnekler
    (`<tur_slug>/<ad>`; bayraksız silinmez). `skipped_runs`: işlemdeki çalıştırmalar;
    `unknown_dirs`: `gelen/` altında kaydı olmayan dizinler (dokunulmaz). `waiting_items`:
    `done` çalıştırmada İK kararını bekleyen ve dosyası silinecek öğe sayısı (silindikten sonra
    "Türe yerleştir" yapılamaz)."""

    applied: bool
    index: IndexSync
    previews: dict[str, int]
    planned: dict[str, Totals] = field(default_factory=lambda: {s: Totals() for s in SECTIONS})
    deleted: dict[str, Totals] = field(default_factory=lambda: {s: Totals() for s in SECTIONS})
    unpreviewable: list[str] = field(default_factory=list)
    skipped_runs: list[int] = field(default_factory=list)
    unknown_dirs: list[str] = field(default_factory=list)
    waiting_items: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "applied": self.applied,
            "index": {
                "indexed": self.index.indexed,
                "removed": self.index.removed,
                "present": self.index.present,
            },
            "previews": self.previews,
            "planned": {name: totals.as_dict() for name, totals in self.planned.items()},
            "deleted": {name: totals.as_dict() for name, totals in self.deleted.items()},
            "unpreviewable": self.unpreviewable,
            "skipped_runs": self.skipped_runs,
            "unknown_dirs": self.unknown_dirs,
            "waiting_items": self.waiting_items,
        }


Progress = Callable[[str, int, int], None]


def purge_originals(
    factory: sessionmaker[Session],
    layout: DataLayout,
    *,
    apply: bool = False,
    include_unpreviewable: bool = False,
    progress: Progress | None = None,
) -> PurgeReport:
    """Dizini eşitler, eksik önizlemeleri üretir, bölüm bölüm raporlar; `apply` ise siler.
    Her adım kendi oturumu ve commit'iyle çalışır (uzun bir işlem açık kalmaz)."""
    with factory() as session:
        synced = sync_example_index(
            session,
            layout,
            progress=(lambda i, n: progress("index", i, n)) if progress else None,
        )
        session.commit()
    with factory() as session:
        examples, previews = _prepare_previews(session, layout, progress)
    report = PurgeReport(applied=apply, index=synced, previews=previews)
    for example in examples:
        if not example.previewable:
            report.unpreviewable.append(f"{example.type_slug}/{example.name}")
        if example.previewable or include_unpreviewable:
            report.planned[EXAMPLES].add(example.size)
    with factory() as session:
        done_runs = _plan_incoming(session, layout, report)
        session.rollback()
    removed_roots = _removed_roots(layout)
    reference_roots = _reference_roots(layout)
    for path in _files_under(removed_roots):
        report.planned[REMOVED].add(_size(path))
    for path in _files_under(reference_roots):
        report.planned[REFERENCE].add(_size(path))
    if not apply:
        return report

    for example in examples:
        if example.previewable or include_unpreviewable:
            with factory() as session:
                _purge_example(session, layout, example, report)
                session.commit()
    for run_id in done_runs:
        with factory() as session:
            _purge_run(session, layout, run_id, report)
            session.commit()
    _purge_tree(removed_roots, report.deleted[REMOVED])
    _purge_tree(reference_roots, report.deleted[REFERENCE])
    with factory() as session:
        _record(session, report)
        session.commit()
    return report


# --- hazırlık ---------------------------------------------------------------------------------


def _prepare_previews(
    session: Session, layout: DataLayout, progress: Progress | None
) -> tuple[list[PlannedExample], dict[str, int]]:
    """Ham dosyası duran her örneğin iki kalıcı önizlemesini üretir (var olanı atlar). Liste ve
    anahtarlar dizinden okunur, okuma bitince işlem bırakılır (üretim boyunca işlem açık kalmaz)."""
    try:
        slugs = sorted(set(example_slugs(layout)) | set(indexed_slugs(session)))
        targets = [
            (slug, example)
            for slug in slugs
            for example in list_examples(layout, slug, session)
            if example.present
        ]
    finally:
        session.rollback()
    counts = {"created": 0, "existing": 0, "failed": 0}
    planned: list[PlannedExample] = []
    for number, (slug, example) in enumerate(targets, start=1):
        ready = example.preview_key is not None
        for size in PREVIEW_SIZES:
            key = example.preview_key
            if key is not None and layout.preview_path(slug, key, size).is_file():
                counts["existing"] += 1
                continue
            preview = (
                ensure_preview(layout, slug, example.name, size, key=key)
                if key is not None
                else None
            )
            created = preview is not None and preview.path is not None
            counts["created" if created else "failed"] += 1
            ready = ready and created
        planned.append(PlannedExample(slug, example.name, example.size, ready))
        if progress is not None:
            progress("previews", number, len(targets))
    return planned, counts


def _plan_incoming(session: Session, layout: DataLayout, report: PurgeReport) -> list[int]:
    """`gelen/` dizinlerini çalıştırmalarla eşler; silinecek `done` çalıştırmaların kimlikleri.
    Dizini kalmamış ama öğesinde `staged_path` dolu `done` çalıştırma da listeye girer (kesilen
    koşunun kalan veritabanı işi)."""
    statuses = dict(session.execute(select(TrainingRun.id, TrainingRun.status)).tuples().all())
    done: set[int] = set()
    for directory in _subdirectories(layout.training_incoming):
        run_id = int(directory.name) if directory.name.isdigit() else None
        status = statuses.get(run_id) if run_id is not None else None
        if status is None:
            report.unknown_dirs.append(directory.name)
            continue
        if status != TrainingRunStatus.DONE.value:
            report.skipped_runs.append(run_id)  # type: ignore[arg-type]
            continue
        done.add(run_id)  # type: ignore[arg-type]
        for path in _files_under((directory,)):
            report.planned[INCOMING].add(_size(path))
    done.update(
        session.scalars(
            select(TrainingItem.run_id)
            .join(TrainingRun)
            .where(
                TrainingRun.status == TrainingRunStatus.DONE.value,
                TrainingItem.staged_path.is_not(None),
            )
            .distinct()
        )
    )
    report.waiting_items = (
        session.scalar(
            select(func.count(TrainingItem.id))
            .join(TrainingRun)
            .where(
                TrainingRun.status == TrainingRunStatus.DONE.value,
                TrainingItem.staged_path.is_not(None),
                TrainingItem.status.in_([status.value for status in UNPLACED_STATUSES]),
            )
        )
        or 0
    )
    report.skipped_runs.sort()
    return sorted(done)


# --- silme ------------------------------------------------------------------------------------


def _purge_example(
    session: Session, layout: DataLayout, example: PlannedExample, report: PurgeReport
) -> None:
    """Örneğin ham dosyasını siler ve dizin satırını `removed` yapar. Ham dosya bu arada
    kalktıysa yalnız satır işaretlenir."""
    path = example_path(layout, example.type_slug, example.name)
    if path is not None and _inside(path, (layout.examples,)):
        size = _size(path)
        path.unlink(missing_ok=True)
        report.deleted[EXAMPLES].add(size)
    row = index_entry(session, example.type_slug, example.name)
    if row is not None and example_path(layout, example.type_slug, example.name) is None:
        mark_original_removed(row)
    session.flush()


def _purge_run(session: Session, layout: DataLayout, run_id: int, report: PurgeReport) -> None:
    """`done` çalıştırmanın `gelen/<run>/` dosyalarını siler ve öğelerin `staged_path`'ini
    boşaltır. Çalıştırma bu arada yeniden açıldıysa (`running`) dokunulmaz."""
    run = session.get(TrainingRun, run_id)
    if run is None or run.status != TrainingRunStatus.DONE.value:
        return
    directory = layout.training_incoming_dir(run_id)
    _purge_tree((directory,), report.deleted[INCOMING])
    session.execute(
        update(TrainingItem)
        .where(TrainingItem.run_id == run_id, TrainingItem.staged_path.is_not(None))
        .values(staged_path=None)
        .execution_options(synchronize_session=False)
    )


def _purge_tree(roots: tuple[Path, ...], totals: Totals) -> None:
    """Köklerin altındaki dosyaları siler, boşalan dizinleri kaldırır (bağlantı izlenmez)."""
    for path in list(_files_under(roots)):
        size = _size(path)
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        totals.add(size)
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        for current, _dirs, _files in os.walk(root, topdown=False):
            try:
                Path(current).rmdir()
            except OSError:
                continue


def _record(session: Session, report: PurgeReport) -> None:
    files = sum(totals.files for totals in report.deleted.values())
    size = sum(totals.bytes for totals in report.deleted.values())
    record_event(
        session,
        EventType.TRAINING_ORIGINALS_PURGED,
        actor=ACTOR,
        message=Translatable(
            N_("Ham eğitim verisi boşaltıldı: {files} dosya, {megabytes} MB."),
            files=files,
            megabytes=f"{size / (1024 * 1024):.1f}",
        ),
        data={
            **{name: totals.as_dict() for name, totals in report.deleted.items()},
            "unpreviewable": len(report.unpreviewable),
            "skipped_runs": len(report.skipped_runs),
        },
    )


# --- yardımcılar ------------------------------------------------------------------------------


def _removed_roots(layout: DataLayout) -> tuple[Path, ...]:
    return tuple(
        root for root in layout.training_removed_roots if _inside(root, (layout.training,))
    )


def _reference_roots(layout: DataLayout) -> tuple[Path, ...]:
    root = layout.reference_dir
    return (root,) if root.is_dir() and not root.is_symlink() else ()


def _subdirectories(root: Path) -> list[Path]:
    try:
        with os.scandir(root) as scanned:
            found = [Path(e.path) for e in scanned if e.is_dir(follow_symlinks=False)]
    except FileNotFoundError:
        return []
    return sorted(found, key=lambda path: path.name)


def _files_under(roots: tuple[Path, ...]) -> Iterator[Path]:
    """Köklerin altındaki düz dosyalar ve bağlantılar (bağlantının hedefi izlenmez)."""
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        for current, dirs, files in os.walk(root):
            directory = Path(current)
            dirs[:] = sorted(d for d in dirs if not (directory / d).is_symlink())
            for name in sorted(files):
                yield directory / name


def _inside(path: Path, roots: tuple[Path, ...]) -> bool:
    parent = path.parent.resolve()
    return any(parent.is_relative_to(root.resolve()) for root in roots)


def _size(path: Path) -> int:
    try:
        return path.lstat().st_size
    except FileNotFoundError:
        return 0
