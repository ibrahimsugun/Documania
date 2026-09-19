"""Belge türü kataloğu: şema ve tutarlılık kuralı (00.6.1), başlangıç tohumu (00.6.2),
YAML ↔ veritabanı eşitleme (00.6.3), panelden yönetim ve form doğrulaması (11.1)."""

from app.catalog.form import TypeForm, TypeFormError, build_entry
from app.catalog.manage import (
    TypeExistsError,
    TypeNotFoundError,
    TypeSummary,
    create_type,
    list_types,
    load_record,
    record_problems,
    set_type_active,
    update_type,
)
from app.catalog.schema import (
    Catalog,
    CatalogEntry,
    CatalogError,
    Conversion,
    FileType,
    OutputFormat,
    PageRange,
    Sides,
    validate_catalog,
)
from app.catalog.sync import CatalogImportResult, export_catalog, import_catalog
from app.catalog.yaml_io import (
    dump_catalog_yaml,
    install_seed_catalog,
    load_seed_catalog,
    parse_catalog_yaml,
    read_catalog_file,
    write_catalog_file,
)

__all__ = [
    "Catalog",
    "CatalogEntry",
    "CatalogError",
    "CatalogImportResult",
    "Conversion",
    "FileType",
    "OutputFormat",
    "PageRange",
    "Sides",
    "TypeExistsError",
    "TypeForm",
    "TypeFormError",
    "TypeNotFoundError",
    "TypeSummary",
    "build_entry",
    "create_type",
    "dump_catalog_yaml",
    "export_catalog",
    "import_catalog",
    "install_seed_catalog",
    "list_types",
    "load_record",
    "load_seed_catalog",
    "parse_catalog_yaml",
    "read_catalog_file",
    "record_problems",
    "set_type_active",
    "update_type",
    "validate_catalog",
    "write_catalog_file",
]
