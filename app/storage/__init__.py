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
    "SlugError",
    "StoredFile",
    "copy_file",
    "document_stem",
    "employee_folder_name",
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
]
