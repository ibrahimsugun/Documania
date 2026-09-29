"""Depolama katmanı: veri dizini yolları, slug, adlandırma, atomik yazma (PRD 00.4), Alinan kopyası
(07.7.2), arşive taşıma (08.4.1), belgeyi başka çalışana taşıma (10.8.2), çalışan klasörünü yeni
ada göre yeniden adlandırma (10.5.6), iki çalışanı birleştirmenin dosya işleri (10.5.9).

Dosya yolu üreten tek yer bu pakettir (MASTER-PROMPT §4 yol kuralı).
"""

from app.storage.archive import (
    ArchivedDocument,
    DocumentNotArchivableError,
    DocumentNotFoundError,
    archive_document,
)
from app.storage.atomic import (
    ContentMismatchError,
    StoredFile,
    copy_file,
    find_sequenced,
    iter_file_chunks,
    remove_partial_writes,
    replace_file,
    sha256_bytes,
    sha256_file,
    write_file,
    write_sequenced,
    write_unique,
)
from app.storage.filetype import FileKind, UnsupportedFileTypeError, detect_file_kind
from app.storage.hashing import find_original_by_sha256
from app.storage.inbox import write_to_inbox
from app.storage.layout import DataLayout, prepare_data_dir
from app.storage.merge import (
    EmployeeMergeError,
    EmployeeMergePlan,
    FileMove,
    RelocatedDocument,
    plan_employee_merge,
    relocate_merged_files,
)
from app.storage.move import (
    DocumentNotMovableError,
    MovedDocument,
    MoveTargetNotFoundError,
    move_document,
)
from app.storage.naming import (
    document_stem,
    employee_folder_name,
    person_slug,
    sequenced_filename,
    split_document_filename,
)
from app.storage.received import ReceivedCopy, copy_to_received
from app.storage.rename import (
    EmployeeRenameError,
    EmployeeRenamePlan,
    RenamedFile,
    plan_employee_rename,
    rename_employee_folder,
)
from app.storage.slug import SlugError, slugify

__all__ = [
    "ArchivedDocument",
    "ContentMismatchError",
    "DataLayout",
    "DocumentNotArchivableError",
    "DocumentNotFoundError",
    "DocumentNotMovableError",
    "EmployeeMergeError",
    "EmployeeMergePlan",
    "EmployeeRenameError",
    "EmployeeRenamePlan",
    "FileKind",
    "FileMove",
    "MoveTargetNotFoundError",
    "MovedDocument",
    "ReceivedCopy",
    "RelocatedDocument",
    "RenamedFile",
    "SlugError",
    "StoredFile",
    "UnsupportedFileTypeError",
    "archive_document",
    "copy_file",
    "copy_to_received",
    "detect_file_kind",
    "document_stem",
    "employee_folder_name",
    "find_original_by_sha256",
    "find_sequenced",
    "iter_file_chunks",
    "move_document",
    "person_slug",
    "plan_employee_merge",
    "plan_employee_rename",
    "prepare_data_dir",
    "relocate_merged_files",
    "remove_partial_writes",
    "rename_employee_folder",
    "replace_file",
    "sequenced_filename",
    "sha256_bytes",
    "sha256_file",
    "slugify",
    "split_document_filename",
    "write_file",
    "write_sequenced",
    "write_to_inbox",
    "write_unique",
]
