"""Çalışan klasörünü ve belge dosyalarını yeni ada göre yeniden adlandırma (PRD 10.5.6; K8, K10,
K11, K18; PLAN.md §C90-a).

Çalışanın adı ya da soyadı değişince klasör adı (`Ad_Soyad_E0001`) değişir; E numarası aynı kalır.
İzinli fiziksel işlemler yalnız **yeniden adlandırma** ve **taşıma**dır (K11): içerik bayt bayt
aynı kalır.

- Klasör `Employees/<eski>` → `Employees/<yeni>` tek hamlede taşınır; `Alinan/` ve `Hazir/` içindeki
  her dosya onunla gelir. `Alinan/` kopyaları yüklemedeki adlarını korur (K10) — K8 adı taşımazlar.
- `Hazir/` altındaki **etkin** belgelerin dosyası yeni K8 adını alır: `document_stem(yeni ad, yeni
  soyad, türün file_label'ı)` + belgenin sıra eki (`sequence_no`). Ek, yeni gövdeyle `Hazir/`'da
  başka bir dosyanın (uzantısı farklı olsa da, harf büyüklüğüne duyarsız) gövdesiyle çakışırsa
  `write_sequenced`'ın kuralıyla ilk boş ek seçilir. Eski sürüm (K18) ve Hazir dışındaki dosyalar
  adlarını korur; dosyası yerinde olmayan belgenin yalnız yolu güncellenir.
- Klasörün altındaki her `documents` satırının `path`'i yeni klasörü gösterir; köken kaydı
  (`source_refs_json`) ve arşiv (`Archive/…`) altındaki belgeler değişmez.
- `Uretilen/` altındaki **üretilen belgeler** (15.2.3; etkin, eski sürüm ve arşivdeki — hepsi
  `Uretilen/`'de durur) yeni K8 adını alır: `document_stem(yeni ad, yeni soyad, şablonun
  file_label'ı)` + sıra eki (`sequence_no`; gövde `Uretilen/`'de doluysa ilk boş ek). Satırın
  `path`'i ve `sequence_no`'su güncellenir; kalıcı silinmiş (yolu boş) satıra dokunulmaz.

Sıra (`move_document` sözleşmesi): plan diske dokunmadan kurulur (`plan_employee_rename`); satırlar
yeni yolla güncellenip `flush` edilir; sonra dosyalar taşınır. Taşıma yarıda kalırsa yapılan her
adım tersine alınır ve `EmployeeRenameError` yükselir — çağıran oturumu geri alır, hiçbir şey
değişmiş görünmez. Yalnız harf büyüklüğü değişen ad (Windows'ta aynı ad sayılır) geçici bir addan
geçirilerek iki adımda değiştirilir. Hiçbir dosyanın üzerine yazılmaz.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    GeneratedDocument,
    GeneratedDocumentStatus,
    KnownDocumentType,
    OutputTemplate,
)
from app.storage.layout import DataLayout
from app.storage.naming import (
    document_stem,
    employee_folder_name,
    normalize_extension,
    sequenced_filename,
    sequenced_stem,
)


class EmployeeRenameError(RuntimeError):
    """10.5.6: klasör ya da belge dosyası yeniden adlandırılamadı; yapılan adımlar geri alındı.
    Mesaj kişi adı ve yol taşımaz (CONVENTIONS §6)."""


@dataclass(frozen=True, slots=True)
class RenamedFile:
    """K8 adını değiştiren belge dosyası: yeni klasördeki eski ve yeni ad, seçilen sıra eki."""

    document_id: int
    source_name: str
    target_name: str
    sequence_no: int


@dataclass(frozen=True, slots=True)
class EmployeeRenamePlan:
    """`plan_employee_rename` sonucu: eski ve yeni klasör adı, klasörün altındaki her belgenin yeni
    göreli yolu (`paths`) ve adı değişen dosyalar (`files`); üretilen belgeler için aynısı
    (`output_paths`, `outputs`; oradaki `document_id` üretilen belgenin kimliğidir)."""

    old_folder: str
    new_folder: str
    paths: dict[int, str]
    files: tuple[RenamedFile, ...]
    output_paths: dict[int, str] = field(default_factory=dict)
    outputs: tuple[RenamedFile, ...] = ()

    @property
    def renamed_document_ids(self) -> tuple[int, ...]:
        return tuple(renamed.document_id for renamed in self.files)

    @property
    def renamed_output_ids(self) -> tuple[int, ...]:
        return tuple(renamed.document_id for renamed in self.outputs)


def plan_employee_rename(
    session: Session, layout: DataLayout, employee: Employee, *, given_names: str, surname: str
) -> EmployeeRenamePlan | None:
    """Yeni ad-soyadla klasör ve dosya adlarının planı; klasör adı değişmiyorsa `None`.

    Hiçbir şey yazmaz. Yeni klasör adı K8'e çevrilemiyorsa `SlugError`/`ValueError` (çağıran
    alanları önceden denetler).
    """
    new_folder = employee_folder_name(given_names, surname, employee.id)
    if new_folder == employee.folder_name:
        return None
    old_dir = layout.employee_dir(employee.folder_name)
    new_dir = layout.employee_dir(new_folder)
    old_ready = layout.ready_dir(employee.folder_name)
    prefix = f"{layout.relative(old_dir)}/"
    documents = session.scalars(
        select(Document)
        .where(Document.path.startswith(prefix, autoescape=True))
        .order_by(Document.sequence_no, Document.id)
    ).all()

    taken = _stems_in_use(old_ready)
    paths: dict[int, str] = {}
    files: list[RenamedFile] = []
    for document in documents:
        relative_part = PurePosixPath(document.path).relative_to(PurePosixPath(prefix))
        new_path = new_dir.joinpath(*relative_part.parts)
        renamed = _renamed_file(session, layout, employee, document, given_names, surname, taken)
        if renamed is not None:
            files.append(renamed)
            new_path = layout.ready_dir(new_folder) / renamed.target_name
        paths[document.id] = layout.relative(new_path)
    output_paths, outputs = _plan_outputs(
        session, layout, employee, new_folder, given_names=given_names, surname=surname
    )
    return EmployeeRenamePlan(
        employee.folder_name, new_folder, paths, tuple(files), output_paths, outputs
    )


def _plan_outputs(
    session: Session,
    layout: DataLayout,
    employee: Employee,
    new_folder: str,
    *,
    given_names: str,
    surname: str,
) -> tuple[dict[int, str], tuple[RenamedFile, ...]]:
    """15.2.3 — üretilen belgelerin yeni yolu ve `Uretilen/`'de adı değişen dosyalar."""
    old_generated = layout.generated_dir(employee.folder_name)
    new_generated = layout.generated_dir(new_folder)
    prefix = f"{layout.relative(old_generated)}/"
    rows = session.execute(
        select(GeneratedDocument, OutputTemplate.file_label)
        .join(OutputTemplate, OutputTemplate.id == GeneratedDocument.template_id)
        .where(
            GeneratedDocument.employee_id == employee.id,
            GeneratedDocument.status != GeneratedDocumentStatus.DELETED.value,
            GeneratedDocument.path.startswith(prefix, autoescape=True),
        )
        .order_by(GeneratedDocument.sequence_no, GeneratedDocument.id)
    ).all()
    taken = _stems_in_use(old_generated)
    paths: dict[int, str] = {}
    outputs: list[RenamedFile] = []
    for output, file_label in rows:
        relative_part = PurePosixPath(output.path).relative_to(PurePosixPath(prefix))
        new_path = new_generated.joinpath(*relative_part.parts)
        current = layout.resolve(output.path)
        if current.parent == old_generated and current.is_file():
            stem = document_stem(given_names, surname, file_label)
            sequence_no = _free_sequence(stem, max(output.sequence_no, 1), current.stem, taken)
            renamed = RenamedFile(
                document_id=output.id,
                source_name=current.name,
                target_name=sequenced_filename(stem, sequence_no, current.suffix),
                sequence_no=sequence_no,
            )
            outputs.append(renamed)
            new_path = new_generated / renamed.target_name
        paths[output.id] = layout.relative(new_path)
    return paths, tuple(outputs)


def rename_employee_folder(
    session: Session, layout: DataLayout, employee: Employee, plan: EmployeeRenamePlan
) -> None:
    """Planı uygular: satırlar (`documents.path`, `sequence_no`, `employees.folder_name`)
    güncellenip `flush` edilir, sonra klasör ve dosyalar taşınır.

    Hedef klasör zaten varsa ya da taşıma yarıda kalırsa yapılan adımlar geri alınır ve
    `EmployeeRenameError` yükselir; oturumu geri almak çağıranındır. Oturum commit edilmez.
    """
    if employee.folder_name != plan.old_folder:
        raise EmployeeRenameError("Çalışanın klasör adı plan kurulduktan sonra değişti")
    old_dir = layout.employee_dir(plan.old_folder)
    new_dir = layout.employee_dir(plan.new_folder)
    if new_dir.exists() and not _same_entry(old_dir, new_dir):
        raise EmployeeRenameError("Yeni klasör adı veri dizininde zaten var; hiçbir şey değişmedi")

    sequences = {renamed.document_id: renamed.sequence_no for renamed in plan.files}
    for document_id, path in plan.paths.items():
        document = session.get_one(Document, document_id)
        document.path = path
        if document_id in sequences:
            document.sequence_no = sequences[document_id]
    output_sequences = {renamed.document_id: renamed.sequence_no for renamed in plan.outputs}
    for output_id, path in plan.output_paths.items():
        output = session.get_one(GeneratedDocument, output_id)
        output.path = path
        if output_id in output_sequences:
            output.sequence_no = output_sequences[output_id]
    employee.folder_name = plan.new_folder
    session.flush()

    done: list[tuple[Path, Path]] = []
    try:
        if old_dir.exists():
            _rename(old_dir, new_dir)
            done.append((old_dir, new_dir))
        renames = (
            *((layout.ready_dir(plan.new_folder), renamed) for renamed in plan.files),
            *((layout.generated_dir(plan.new_folder), renamed) for renamed in plan.outputs),
        )
        for directory, renamed in renames:
            source, target = directory / renamed.source_name, directory / renamed.target_name
            if source.name != target.name:
                _rename(source, target)
                done.append((source, target))
    except OSError as exc:
        restored = _undo(done)
        detail = "yapılan adımlar geri alındı" if restored else "geri alma tamamlanamadı"
        raise EmployeeRenameError(
            f"Klasör ya da belge dosyası yeniden adlandırılamadı ({type(exc).__name__}); {detail}"
        ) from exc
    layout.ensure_employee_tree(plan.new_folder)


def _renamed_file(
    session: Session,
    layout: DataLayout,
    employee: Employee,
    document: Document,
    given_names: str,
    surname: str,
    taken: set[str],
) -> RenamedFile | None:
    """Etkin belgenin `Hazir/`'daki dosyasının yeni K8 adı; adı değişmeyecek belge (eski sürüm,
    başka çalışanın ya da Hazir dışındaki kayıt, dosyası yerinde olmayan) `None`. Seçilen gövde
    `taken`'a eklenir."""
    if document.employee_id != employee.id or document.status != DocumentStatus.ACTIVE.value:
        return None
    try:
        current = layout.resolve(document.path)
        extension = normalize_extension(current.suffix)
    except ValueError:
        return None
    if current.parent != layout.ready_dir(employee.folder_name) or not current.is_file():
        return None
    document_type = session.get(KnownDocumentType, document.type_slug)
    if document_type is None:
        return None
    stem = document_stem(given_names, surname, document_type.file_label)
    sequence_no = _free_sequence(stem, max(document.sequence_no, 1), current.stem, taken)
    return RenamedFile(
        document_id=document.id,
        source_name=current.name,
        target_name=sequenced_filename(stem, sequence_no, extension),
        sequence_no=sequence_no,
    )


def _free_sequence(stem: str, preferred: int, own_stem: str, taken: set[str]) -> int:
    """Gövdenin sıra eki: tercih edilen ek boşsa (ya da dosyanın kendi adıysa) o, değilse ilk boş
    ek; seçilen gövde `taken`'a eklenir."""
    own = own_stem.casefold()

    def free(sequence_no: int) -> bool:
        candidate = sequenced_stem(stem, sequence_no).casefold()
        return candidate == own or candidate not in taken

    sequence_no = preferred
    if not free(sequence_no):
        sequence_no = 1
        while not free(sequence_no):
            sequence_no += 1
    taken.add(sequenced_stem(stem, sequence_no).casefold())
    return sequence_no


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


def _same_entry(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def _rename(source: Path, target: Path) -> None:
    """`source`'u `target` adına taşır; hedef başka bir girişse `FileExistsError` — üzerine
    yazılmaz. Yalnız harf büyüklüğü değişen ad (Windows'ta aynı giriş) geçici addan geçer."""
    if target.exists() and not _same_entry(source, target):
        raise FileExistsError(target.name)
    if source.name != target.name and source.name.casefold() == target.name.casefold():
        temporary = source.with_name(f".belgeee-rename-{secrets.token_hex(8)}")
        os.replace(source, temporary)
        try:
            os.replace(temporary, target)
        except OSError:
            os.replace(temporary, source)
            raise
        return
    os.replace(source, target)


def _undo(done: list[tuple[Path, Path]]) -> bool:
    """Yapılan taşımaları ters sırayla geri alır; hepsi geri alındıysa `True`."""
    restored = True
    for source, target in reversed(done):
        try:
            _rename(target, source)
        except OSError:
            restored = False
    return restored
