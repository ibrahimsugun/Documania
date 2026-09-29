"""İki çalışanı birleştirmenin dosya işleri — birleşenin belge dosyaları ve `Alinan/` kopyaları
kalan kaydın klasörüne taşınır (PRD 10.5.9; K8, K10, K11, K18, R11; PLAN.md §C90-d, §D69).

İzinli fiziksel işlemler yalnız **taşıma** ve **yeniden adlandırma**dır (K11): içerik bayt bayt aynı
kalır, hiçbir dosya kopyalanmaz ya da silinmez. Taşıma sabit bağ + eski adın kaldırılmasıdır
(`os.link`, sonra `unlink`): hedef ad doluysa `os.link` `FileExistsError` verir, üzerine yazılmaz.

- **Etkin belge** `Hazir/`'da kalan kaydın K8 adını alır: `document_stem(kalanın adı, kalanın
  soyadı, türün file_label'ı)` ve kalanın `Hazir/`'ında ilk boş sıra eki (`write_sequenced`'ın
  kuralı: uzantısız gövde, harf büyüklüğüne duyarsız) — belgeyi başka çalışana taşımanın (10.8.2)
  fiziksel kuralı.
- **Eski sürüm** (K18) yeniden adlandırılmaz, adıyla kalanın `Hazir/`'ına taşınır; aynı gövde
  orada doluysa ilk boş `-2`, `-3`… eki alır (üzerine yazılmaz). Sıra numarası değişmez.
- **Arşivdeki belge** `Archive/<yyyy-mm>/` altında kalır; dosyası taşınmaz (yalnız sahibi değişir,
  çağıranın işi).
- **Dosyası yerinde olmayan** belgenin dosya işi yoktur; yolu değişmez.
- **`Alinan/`** klasöründeki her dosya adıyla kalanın `Alinan/`'ına taşınır; ad doluysa
  `ad-2.uzantı` (`write_unique`'in kuralı). Aynı içerik orada olsa da taşınır — silme yoktur
  (K16, R11).

Birleşenin klasörü, `Alinan/` ve `Hazir/` dizinleri yerinde kalır (boş); `profil.md`'si çağıranca
yönlendirme notuyla yeniden üretilir.

Sıra (`move_document` / `rename_employee_folder` sözleşmesi): plan diske dokunmadan kurulur
(`plan_employee_merge`); çağıran satırları plandaki yolla günceller ve `flush` eder; sonra
`relocate_merged_files` dosyaları taşır. Taşıma yarıda kalırsa yapılan her adım tersine alınır ve
`EmployeeMergeError` yükselir — çağıran oturumu geri alır, hiçbir şey değişmiş görünmez.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePath

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentStatus, Employee, KnownDocumentType
from app.storage.atomic import is_partial_write
from app.storage.layout import DataLayout
from app.storage.naming import document_stem, normalize_extension, sequenced_stem


class EmployeeMergeError(RuntimeError):
    """10.5.9: belge ya da `Alinan/` dosyası taşınamadı; yapılan adımlar geri alındı. Mesaj kişi
    adı ve yol taşımaz (CONVENTIONS §6)."""


@dataclass(frozen=True, slots=True)
class FileMove:
    """Tek dosyanın taşınması: kaynak ve hedef mutlak yol (ikisi de veri dizininin içinde)."""

    source: Path
    target: Path


@dataclass(frozen=True, slots=True)
class RelocatedDocument:
    """Dosyası kalanın `Hazir/`'ına taşınacak belge: yeni göreli yol ve sıra numarası."""

    document_id: int
    path: str
    sequence_no: int
    move: FileMove


@dataclass(frozen=True, slots=True)
class EmployeeMergePlan:
    """`plan_employee_merge` sonucu: dosyası taşınacak belgeler ve `Alinan/` kopyaları."""

    keep_folder: str
    merge_folder: str
    documents: tuple[RelocatedDocument, ...]
    received: tuple[FileMove, ...]

    @property
    def moves(self) -> tuple[FileMove, ...]:
        return (*(document.move for document in self.documents), *self.received)


def plan_employee_merge(
    session: Session, layout: DataLayout, keep: Employee, merge: Employee
) -> EmployeeMergePlan:
    """Birleşenin (`merge`) dosyalarının kalanın (`keep`) klasöründeki yeni adları; hiçbir şey
    yazmaz. Kurallar modül açıklamasındadır. Etkin belgeler önce (sıra numarası, kimlik sırasıyla)
    ilk boş ekleri alır, eski sürümler sonra."""
    ready = layout.ready_dir(keep.folder_name)
    taken = _stems_in_use(ready)
    documents = session.scalars(
        select(Document)
        .where(
            Document.employee_id == merge.id,
            Document.status.in_([DocumentStatus.ACTIVE.value, DocumentStatus.SUPERSEDED.value]),
        )
        .order_by(Document.sequence_no, Document.id)
    ).all()
    ordered = sorted(documents, key=lambda each: each.status != DocumentStatus.ACTIVE.value)
    relocated: list[RelocatedDocument] = []
    for document in ordered:
        current = _current_file(layout, document)
        if current is None:
            continue
        stem, extension, sequence_no = _target_name(session, keep, document, current, taken)
        target = ready / f"{stem}.{extension}" if extension else ready / stem
        relocated.append(
            RelocatedDocument(
                document_id=document.id,
                path=layout.relative(target),
                sequence_no=sequence_no,
                move=FileMove(current, target),
            )
        )
    return EmployeeMergePlan(
        keep_folder=keep.folder_name,
        merge_folder=merge.folder_name,
        documents=tuple(relocated),
        received=_received_moves(layout, keep.folder_name, merge.folder_name),
    )


def relocate_merged_files(layout: DataLayout, plan: EmployeeMergePlan) -> None:
    """Planın dosyalarını taşır (satırlar önceden güncellenip `flush` edilmiştir). Bir adım düşerse
    yapılanlar ters sırayla geri alınır ve `EmployeeMergeError` yükselir; oturumu geri almak
    çağıranındır. Birleşenin `Alinan/` ve `Hazir/` dizinleri boş olarak kalır."""
    layout.ensure_employee_tree(plan.keep_folder)
    done: list[FileMove] = []
    try:
        for move in plan.moves:
            _move(move.source, move.target)
            done.append(move)
    except OSError as exc:
        restored = _undo(done)
        detail = "yapılan adımlar geri alındı" if restored else "geri alma tamamlanamadı"
        raise EmployeeMergeError(
            f"Belge ya da Alinan dosyası taşınamadı ({type(exc).__name__}); {detail}"
        ) from exc
    layout.ensure_employee_tree(plan.merge_folder)


def _current_file(layout: DataLayout, document: Document) -> Path | None:
    try:
        path = layout.resolve(document.path)
    except ValueError:
        return None
    return path if path.is_file() else None


def _target_name(
    session: Session, keep: Employee, document: Document, current: Path, taken: set[str]
) -> tuple[str, str, int]:
    """Belgenin kalanın `Hazir/`'ındaki gövdesi, uzantısı ve sıra numarası; seçilen gövde
    `taken`'a eklenir. Etkin belge K8 adını alır; eski sürüm (ya da K8 adına çevrilemeyen etkin
    belge) adını korur, gövdesi doluysa `-2`, `-3`… eki alır."""
    document_type = session.get(KnownDocumentType, document.type_slug)
    try:
        extension = normalize_extension(current.suffix)
    except ValueError:
        extension = None
    if (
        document.status == DocumentStatus.ACTIVE.value
        and document_type is not None
        and extension is not None
    ):
        stem = document_stem(keep.given_names, keep.surname, document_type.file_label)
        sequence_no = 1
        while sequenced_stem(stem, sequence_no).casefold() in taken:
            sequence_no += 1
        chosen = sequenced_stem(stem, sequence_no)
        taken.add(chosen.casefold())
        return chosen, extension, sequence_no
    stem = current.stem if current.suffix else current.name
    suffix = current.suffix.removeprefix(".")
    chosen, number = stem, 1
    while chosen.casefold() in taken:
        number += 1
        chosen = f"{stem}-{number}"
    taken.add(chosen.casefold())
    return chosen, suffix, document.sequence_no


def _received_moves(
    layout: DataLayout, keep_folder: str, merge_folder: str
) -> tuple[FileMove, ...]:
    source_dir = layout.received_dir(merge_folder)
    target_dir = layout.received_dir(keep_folder)
    names = sorted(
        entry
        for entry in _file_names(source_dir)
        if not is_partial_write(entry) and not entry.startswith(".")
    )
    taken = {name.casefold() for name in _file_names(target_dir)}
    moves: list[FileMove] = []
    for name in names:
        suffix = PurePath(name).suffix
        stem = name.removesuffix(suffix)
        chosen, number = name, 1
        while chosen.casefold() in taken:
            number += 1
            chosen = f"{stem}-{number}{suffix}"
        taken.add(chosen.casefold())
        moves.append(FileMove(source_dir / name, target_dir / chosen))
    return tuple(moves)


def _file_names(directory: Path) -> list[str]:
    try:
        with os.scandir(directory) as entries:
            return [entry.name for entry in entries if entry.is_file(follow_symlinks=False)]
    except FileNotFoundError:
        return []


def _stems_in_use(directory: Path) -> set[str]:
    # `write_sequenced` gibi: uzantısız gövde, harf büyüklüğüne duyarsız; gizli dosya sayılmaz.
    try:
        with os.scandir(directory) as entries:
            return {
                entry.name.rsplit(".", 1)[0].casefold()
                for entry in entries
                if not entry.name.startswith(".")
            }
    except FileNotFoundError:
        return set()


def _move(source: Path, target: Path) -> None:
    """`source`'u `target` adına taşır: sabit bağ, sonra eski ad kaldırılır. Hedef doluysa
    `FileExistsError` — üzerine yazılmaz; eski ad kaldırılamazsa yeni bağ geri alınır."""
    os.link(source, target)
    try:
        source.unlink()
    except OSError:
        target.unlink(missing_ok=True)
        raise


def _undo(done: list[FileMove]) -> bool:
    """Yapılan taşımaları ters sırayla geri alır; hepsi geri alındıysa `True`."""
    restored = True
    for move in reversed(done):
        try:
            _move(move.target, move.source)
        except OSError:
            restored = False
    return restored
