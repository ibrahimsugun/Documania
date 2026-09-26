"""Eğitim modu (PRD 11.9, PLAN.md §C86): yalnız bilinen belgelerin örneklerini besler — çalışan,
kişi eşleştirmesi, kuyruk öğesi, yükleme partisi ya da çıktı belgesi oluşturmaz.

Bilinen türler (katalog + hazır önerilen türler) `known_types`, çalıştırma, staging ve örneğe
yerleştirme `placement` modülündedir.
"""

from app.training.known_types import (
    CATALOG_KINDS,
    KnownType,
    KnownTypes,
    KnownTypeSource,
    SuggestedTypeRow,
    SuggestedTypesError,
    build_known_types,
    load_known_types,
    load_suggested_types,
    normalize_type_name,
    parse_suggested_types,
)
from app.training.placement import (
    LABEL_BY_METHOD,
    PENDING_STATUSES,
    PLACEABLE_STATUSES,
    SYSTEM_ACTOR,
    ItemNotPlaceableError,
    Placement,
    UnknownTypeError,
    create_run,
    place_example,
    refresh_run,
    stage_file,
)

__all__ = [
    "CATALOG_KINDS",
    "LABEL_BY_METHOD",
    "PENDING_STATUSES",
    "PLACEABLE_STATUSES",
    "SYSTEM_ACTOR",
    "ItemNotPlaceableError",
    "KnownType",
    "KnownTypeSource",
    "KnownTypes",
    "Placement",
    "SuggestedTypeRow",
    "SuggestedTypesError",
    "UnknownTypeError",
    "build_known_types",
    "create_run",
    "load_known_types",
    "load_suggested_types",
    "normalize_type_name",
    "parse_suggested_types",
    "place_example",
    "refresh_run",
    "stage_file",
]
