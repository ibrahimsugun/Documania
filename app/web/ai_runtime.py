"""Panelin etkin yapay zekâ ayarı bağımlılığı — PRD 03.8.1; PLAN.md §D124 (b).

Sağlayıcı kuran panel bağımlılıkları `Settings`'i buradan alır: `.env` ayarının üzerine
veritabanındaki `ai_settings` satırı (`app.ai.runtime.active_settings`). İstek başına okunur; ayar
değişikliği bir sonraki istekte geçerlidir.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai.runtime import active_settings
from app.config import Settings, get_settings
from app.db.session import get_session


def active_ai_settings(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
) -> Settings:
    """Etkin yapay zekâ ayarlı `Settings` (satır yoksa `.env`'inki)."""
    return active_settings(settings, session)


ActiveAiSettings = Annotated[Settings, Depends(active_ai_settings)]
