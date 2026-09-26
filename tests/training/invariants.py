"""Eğitim modunun değişmez güvencesi (PRD 11.9.1, PLAN.md §C86 "Değişmez güvence").

Eğitim yolu yalnız bilinen belgelerin örneklerini besler: parti, dosya, sayfa, plan, çalışan (ad,
numara, iletişim, profil alanı), kuyruk öğesi, çıktı belgesi, işçi işi ya da aday tür satırı açmaz;
Inbox, çalışan, kuyruk, arşiv ve sayfa önbelleği dizinlerine dosya koymaz. Her eğitim görevi (tm
115–120) kendi yolunu koştuktan sonra `assert_employee_data_untouched`'ı çağırır.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    CandidateDocumentType,
    Document,
    Employee,
    EmployeeAlias,
    EmployeeContact,
    EmployeeFieldObservation,
    EmployeeIdentifier,
    Page,
    Plan,
    QueueItem,
    Upload,
    UploadFile,
    UploadJob,
)
from app.storage import DataLayout

EMPLOYEE_SIDE_MODELS = (
    Upload,
    UploadFile,
    Page,
    Plan,
    Employee,
    EmployeeAlias,
    EmployeeIdentifier,
    EmployeeContact,
    EmployeeFieldObservation,
    QueueItem,
    Document,
    UploadJob,
    CandidateDocumentType,
)
EMPLOYEE_SIDE_DIRS = (
    "Inbox",
    "Employees",
    "Unknown",
    "Unreadable",
    "Unresolved",
    "Archive",
    "cache",
)


def employee_side_rows(session: Session) -> dict[str, int]:
    """Eğitimin dokunmaması gereken tabloların satır sayıları."""
    return {
        model.__tablename__: session.scalar(select(func.count()).select_from(model)) or 0
        for model in EMPLOYEE_SIDE_MODELS
    }


def employee_side_files(layout: DataLayout) -> list[str]:
    """Eğitimin dosya koymaması gereken dizinlerdeki dosyalar (veri köküne göreli)."""
    return sorted(
        path.relative_to(layout.root).as_posix()
        for directory in EMPLOYEE_SIDE_DIRS
        for path in (layout.root / directory).rglob("*")
        if path.is_file()
    )


def assert_employee_data_untouched(session: Session, layout: DataLayout) -> None:
    assert employee_side_rows(session) == dict.fromkeys(
        (model.__tablename__ for model in EMPLOYEE_SIDE_MODELS), 0
    )
    assert employee_side_files(layout) == []
