"""Kayıttaki İngilizce sistem metnini testte kaynak (Türkçe) hâliyle okumak (PRD 10.10.6).

Gerekçe, plan öğesi ve olay metni kayda İngilizce yazılır, kaynağı `recorded_texts`'tedir
(`app.i18n.recorded`, PLAN.md §D121). Var olan testler gerekçenin içeriğini kaynak dilde (Türkçe)
yazar; bu yardımcılar kayıttaki metni kaynağına geri çağırır. Metin kayıtlı değilse — Türkçe
düzleşmiş ya da hiç kaydedilmemiş — test kırmızıdır: içerik kadar "kayıtta İngilizce ve kaynağı
saklı" kuralı da sınanır.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.db.models import Event
from app.i18n.recorded import english, recall_texts
from app.pipeline.plan import PlanDocument, PlanItem


def source_text(session: Session, text: str | None) -> str | None:
    """Kayıtlı metnin kaynak (Türkçe) hâli; boş metin boş kalır, kayıtlı olmayan metin hatadır."""
    if not text:
        return text
    recalled = recall_texts(session, (text,))
    assert text in recalled, f"kayıtlı sistem metni değil: {text!r}"
    source = recalled[text]
    assert english(source) == text
    return str(source)


def source_texts(session: Session, texts: Iterable[str | None]) -> list[str | None]:
    return [source_text(session, text) for text in texts]


def source_item(session: Session, item: PlanItem) -> PlanItem:
    """Plan öğesi, gerekçesi kaynak dilde."""
    return item.model_copy(update={"route_reason": source_text(session, item.route_reason)})


def source_document(session: Session, document: PlanDocument) -> PlanDocument:
    """Plan, öğelerinin gerekçeleri kaynak dilde."""
    items = tuple(source_item(session, item) for item in document.items)
    return document.model_copy(update={"items": items})


def source_message(session: Session, message: str | None) -> str | None:
    """Olay mesajı kaynak dilde; mesajın kaynağı yoksa (insanın notu, dosya adı) olduğu gibi."""
    if not message:
        return message
    recalled = recall_texts(session, (message,))
    return str(recalled[message]) if message in recalled else message


def source_value(session: Session, value: Any) -> Any:
    """Sözlük/liste içindeki kayıtlı metinler kaynak dilde (`reason.json` gibi yapılar için)."""
    if isinstance(value, str):
        return source_message(session, value)
    if isinstance(value, dict):
        return {key: source_value(session, item) for key, item in value.items()}
    if isinstance(value, list):
        return [source_value(session, item) for item in value]
    return value


def source_events(session: Session, events: Iterable[Event]) -> list[Event]:
    """Olayların mesajı kaynak dilde, yalnız bellekte: satır kirli sayılmaz, kayda yazılmaz."""
    listed = list(events)
    for event in listed:
        set_committed_value(event, "message", source_message(session, event.message))
    return listed


def source_notes(session: Session, rows: Iterable[Any]) -> list[Any]:
    """Eğitim öğesi ya da örnek kaydının notu kaynak dilde, yalnız bellekte (kirli sayılmaz)."""
    listed = list(rows)
    for row in listed:
        set_committed_value(row, "note", source_message(session, row.note))
    return listed
