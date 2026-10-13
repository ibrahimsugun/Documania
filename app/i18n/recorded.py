"""Kayda yazılan sistem metni: kayıtta İngilizce, panelde kullanıcının dilinde (PRD 10.10.6).

Plan öğesi gerekçesi, kuyruk gerekçesi, olay mesajı ve eğitim notu gibi sistemin kendi yazdığı
metinler kodda `Translatable`'dır (kaynak dil Türkçe, §D95). Kayda yazılırken İngilizce kataloğuyla
düz metne çevrilir (`record_text`): plan JSON'u, `queue_items.reason`, `events.message`,
`reason.json` ve eğitim notu bu İngilizce metni taşır. Metnin kaynağı (msgid şablonu ve değerleri,
iç içe `Translatable`'lar dahil) `recorded_texts` tablosuna metnin SHA-256 özetiyle yazılır.

Metin sütunları (`RECORDED_COLUMNS`) için çeviri oturumun flush'ında kendiliğinden yapılır: bu
sütunlara atanan `Translatable` Türkçe düzleşerek kayda giremez. Plan JSON'unun gerekçesi sözlük
içinde olduğu için planlayıcı `record_text`'i kendisi çağırır.

Panel kayıtlı metni gösterirken onu bu tablodan geri çağırır (`recall_texts`): bulunan metin
yeniden `Translatable` olur ve `translate` ile isteğin dilinde gösterilir. Bulunmayan metin — bu
görevden önce yazılmış Türkçe kayıt, yapay zekânın serbest notu, insanın yazdığı not — olduğu gibi
döner; geriye dönük çeviri yapılmaz (PLAN.md §D121).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.db.models import Event, ExampleFileRecord, QueueItem, RecordedText, TrainingItem, utcnow
from app.i18n import Translatable, join_text, translate, use_language

RECORD_LANGUAGE = "en"

# Sistem metni taşıyan sütunlar: atanan `Translatable` flush'ta İngilizceye çevrilir.
RECORDED_COLUMNS: dict[type, tuple[str, ...]] = {
    Event: ("message",),
    QueueItem: ("reason",),
    TrainingItem: ("note",),
    ExampleFileRecord: ("note",),
}

# İç içe `Translatable` değerinin kayıttaki biçimi: düz değer hiçbir zaman sözlük değildir.
_TEMPLATE = "template"
_VALUES = "values"


def english(text: str) -> str:
    """Metnin kayıttaki (İngilizce) hâli: `Translatable` İngilizce kataloğuyla biçimlenir, düz metin
    olduğu gibi kalır (yapay zekâ notu, insanın notu ya da zaten kayıttan okunmuş metin)."""
    if not isinstance(text, Translatable):
        return str(text)
    with use_language(RECORD_LANGUAGE):
        return translate(text)


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record_text(session: Session, text: str) -> str:
    """Kayda yazılacak metin: `Translatable` İngilizceye çevrilir ve kaynağı `recorded_texts`'e
    (yoksa) eklenir; düz metin olduğu gibi döner. Oturum commit edilmez."""
    rendered = english(text)
    if not isinstance(text, Translatable):
        return rendered
    digest = text_hash(rendered)
    if session.scalar(select(RecordedText.id).where(RecordedText.text_hash == digest)) is None:
        dialect = postgresql if session.get_bind().dialect.name == "postgresql" else sqlite
        # Aynı metni başka bir oturum az önce yazdıysa kaynak aynıdır: satır atlanır.
        session.execute(
            dialect.insert(RecordedText)
            .values(text_hash=digest, text=rendered, source_json=_dump(text), created_at=utcnow())
            .on_conflict_do_nothing(index_elements=[RecordedText.text_hash])
        )
    return rendered


def append_text(session: Session, note: str | None, addition: str, separator: str = "; ") -> str:
    """Kayıtlı nota ek: kayıttan okunan not kaynağıyla geri çağrılır, ek onun ardına gelir —
    birleşik metin de panelde parça parça çevrilir."""
    if not note:
        return addition
    return join_text((recall(session, note) or note, addition), separator)


def recall_texts(session: Session, texts: Iterable[str | None]) -> dict[str, Translatable]:
    """Kayıtlı metinlerden kaynağı bilinenlerin `Translatable`'ı (metin → kaynak); bilinmeyen
    metin sözlükte yoktur, çağıran onu olduğu gibi gösterir."""
    wanted = {text_hash(text): text for text in texts if text}
    if not wanted:
        return {}
    rows = session.execute(
        select(RecordedText.text_hash, RecordedText.text, RecordedText.source_json).where(
            RecordedText.text_hash.in_(wanted)
        )
    )
    recalled: dict[str, Translatable] = {}
    for digest, text, source in rows:
        if wanted[digest] == text:
            recalled[text] = _load(source)
    return recalled


def recall(session: Session, text: str | None) -> str | None:
    """Tek kayıtlı metnin gösterilecek hâli: kaynağı biliniyorsa `Translatable`, değilse kendisi."""
    if not text or isinstance(text, Translatable):
        return text
    return recall_texts(session, (text,)).get(text, text)


def localized(recalled: Mapping[str, Translatable], text: str | None) -> str | None:
    """`recall_texts` sonucundan metnin gösterilecek hâli (bulunmazsa metnin kendisi)."""
    if not text:
        return text
    return recalled.get(text, text)


@event.listens_for(Session, "before_flush")
def _record_columns(session: Session, flush_context: object, instances: object) -> None:
    for instance in (*session.new, *session.dirty):
        for column in RECORDED_COLUMNS.get(type(instance), ()):
            value = getattr(instance, column)
            if isinstance(value, Translatable):
                setattr(instance, column, record_text(session, value))


def _dump(text: Translatable) -> dict[str, Any]:
    return {
        _TEMPLATE: text.template,
        _VALUES: {name: _dump_value(value) for name, value in text.values.items()},
    }


def _dump_value(value: object) -> object:
    if isinstance(value, Translatable):
        return _dump(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    return str(value)


def _load(source: Mapping[str, Any]) -> Translatable:
    values = {
        name: _load(value) if isinstance(value, Mapping) else value
        for name, value in source[_VALUES].items()
    }
    return Translatable(source[_TEMPLATE], **values)
