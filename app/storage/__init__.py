"""Depolama katmanı: veri dizini yolları, slug, adlandırma, atomik yazma (PRD 00.4).

Dosya yolu üreten tek yer bu pakettir (MASTER-PROMPT §4 yol kuralı).
"""

from app.storage.atomic import (
    StoredFile,
    copy_file,
    remove_partial_writes,
    replace_file,
    sha256_bytes,
    sha256_file,
    write_file,
    write_sequenced,
)
from app.storage.filetype import FileKind, UnsupportedFileTypeError, detect_file_kind
from app.storage.hashing import find_original_by_sha256
from app.storage.inbox import write_to_inbox
from app.storage.layout import DataLayout, prepare_data_dir
from app.storage.naming import (
    document_stem,
    employee_folder_name,
    person_slug,
    sequenced_filename,
)
from app.storage.slug import SlugError, slugify

__all__ = [
    "DataLayout",
    "FileKind",
    "SlugError",
    "StoredFile",
    "UnsupportedFileTypeError",
    "copy_file",
    "detect_file_kind",
    "document_stem",
    "employee_folder_name",
    "find_original_by_sha256",
    "person_slug",
    "prepare_data_dir",
    "remove_partial_writes",
    "replace_file",
    "sequenced_filename",
    "sha256_bytes",
    "sha256_file",
    "slugify",
    "write_file",
    "write_sequenced",
    "write_to_inbox",
]
