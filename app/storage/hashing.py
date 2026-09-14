"""Tekrar yükleme tespiti (PRD 01.4.1, K10): aynı SHA-256 daha önce geldi mi?

Bayt hesaplama `app/storage/atomic.py`'dedir (`sha256_bytes`/`sha256_file`); bu modül yalnız
veritabanında eşleşen özgün dosyayı arar.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import UploadFile


def find_original_by_sha256(session: Session, sha256: str) -> UploadFile | None:
    """Aynı içerik daha önce yüklenmişse özgün (tekrar olmayan) satırı döner, yoksa `None`.

    Zincirlenmeyi önlemek için yalnız `is_duplicate_of IS NULL` satırlar aranır — bir tekrar
    asla başka bir tekrarın "orijinali" olarak işaretlenmez, her zaman kök satıra bağlanır.
    """
    return session.scalars(
        select(UploadFile)
        .where(UploadFile.sha256 == sha256, UploadFile.is_duplicate_of.is_(None))
        .order_by(UploadFile.id)
    ).first()
