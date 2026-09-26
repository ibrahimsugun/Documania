"""Etiket kararı — İK'nın eğitim örneği üzerindeki kararları (PRD 11.9.4; PLAN.md §C86 "Etiket
kararı", §D58).

Yapay zekânın yerleştirdiği örnek "AI kararı" (`ai_decision`) etiketiyle elle kontrol bekler. İK üç
karardan birini verir:

- **Doğrula (`verify_examples`).** Etiket `verified` olur; dosyaya dokunulmaz. Tek ya da toplu
  seçimle çalışır, tek adımdır (§D58 c). Yalnız etkin "AI kararı" örneği doğrulanır; öteki kayıt
  (etiketsiz, zaten doğrulanmış, çıkarılmış) olduğu gibi kalır. Her doğrulama bir
  `TRAINING_LABEL_VERIFIED` olayıdır (kullanıcı adıyla).
- **Başka türe taşı (`move_example`).** Dosya `examples/<eski>/`'den `examples/<yeni>/`'ye taşınır
  (`relocate_example`; ad doluysa `-2`), kayıt yeni türe ve ada geçer, etiket `verified` olur (türü
  İK seçti), not taşımayı yazar. Öğe varsa sonuç türü yeni türdür. `TRAINING_EXAMPLE_MOVED`.
- **Örneklerden çıkar (`remove_example`).** Dosya eğitim arşivine (`_egitim/cikarilan/<slug>/`)
  taşınır, **silinmez** (R11, §D58 d); kayıt silinmez, çıkarıldı olarak işaretlenir
  (`removed_at`, `removed_by`, `removed_path`). Çıkarılan örnek tekrar tespitine, sayımlara ve
  açıklama üretimine girmez. `TRAINING_EXAMPLE_REMOVED`.

Taşıma ve çıkarma iki aşamalı onaylıdır; belirteci çağıran (panel) tüketir, bu modül yalnız işlemi
yapar. Denetimlerin hepsi diske dokunmadan önce yapılır; reddedilen karar hiçbir şey yazmaz. Dosya
kayıt güncellendikten sonra, en son taşınır: taşıma düşerse istisna çağırana geçer ve işlem geri
alınır. Fonksiyonlar commit etmez.

Olay mesajı ve verisi kimlik ve tür taşır; dosya adı ve kişisel değer taşımaz (CONVENTIONS §6).
Notlar Türkçe ve kişisel değersizdir.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ExampleFileRecord, ExampleLabel, utcnow
from app.events import EventType, record_event
from app.storage import DataLayout
from app.storage.examples import archive_example, example_path, find_example, relocate_example
from app.training.known_types import KnownTypes
from app.training.placement import UnknownTypeError

REMOVED_NOTE = "İK örneklerden çıkardı; dosya eğitim arşivinde."


class ExampleDecisionError(ValueError):
    """Karar uygulanamaz (örnek çıkarılmış, dosyası yerinde değil, hedef tür aynı ya da aynı içerik
    hedefte zaten örnek); mesaj kullanıcıya gösterilir, hiçbir şey yazılmadı."""


@dataclass(frozen=True, slots=True)
class MovedExample:
    """`move_example` sonucu: güncellenen kayıt ve taşımadan önceki türü, adı, etiketi."""

    example: ExampleFileRecord
    from_slug: str
    from_name: str
    previous_label: str | None


def moved_note(from_slug: str, to_slug: str) -> str:
    return f"İK başka türe taşıdı: `{from_slug}` → `{to_slug}`"


def verify_examples(
    session: Session, examples: Iterable[ExampleFileRecord], *, actor: str
) -> list[ExampleFileRecord]:
    """Etkin "AI kararı" örneklerini doğrular (`verified`) ve her biri için
    `TRAINING_LABEL_VERIFIED` yazar; doğrulananları döner. Öteki kayıtlar değişmez."""
    _require_actor(actor)
    verified = []
    for example in examples:
        if example.removed_at is not None or example.label != ExampleLabel.AI_DECISION:
            continue
        example.label = ExampleLabel.VERIFIED.value
        session.flush()
        record_event(
            session,
            EventType.TRAINING_LABEL_VERIFIED,
            actor=actor,
            message=f"Eğitim örneği doğrulandı (`{example.type_slug}`).",
            data={
                "example_file_id": example.id,
                "training_item_id": example.training_item_id,
                "type_slug": example.type_slug,
                "previous_label": ExampleLabel.AI_DECISION.value,
                "label": ExampleLabel.VERIFIED.value,
            },
        )
        verified.append(example)
    return verified


def check_move(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    example: ExampleFileRecord,
    slug: str,
) -> None:
    """Taşıma yapılabilir mi (onay adımları da bunu sorar); değilse `UnknownTypeError` ya da
    `ExampleDecisionError`. Hiçbir şey yazmaz."""
    if slug not in known:
        raise UnknownTypeError(f"Bilinmeyen tür: {slug!r}")
    _check_active(layout, example)
    if slug == example.type_slug:
        raise ExampleDecisionError("Örnek zaten bu türde; başka bir tür seçin.")
    recorded = session.scalar(
        select(ExampleFileRecord).where(
            ExampleFileRecord.sha256 == example.sha256,
            ExampleFileRecord.type_slug == slug,
            ExampleFileRecord.removed_at.is_(None),
        )
    )
    listed = find_example(layout, slug, example.sha256) if recorded is None else None
    name = recorded.name if recorded is not None else listed.name if listed is not None else None
    if name is not None:
        raise ExampleDecisionError(f"Aynı içerik seçilen türde zaten örnek ({name}); taşınmadı.")


def move_example(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    example: ExampleFileRecord,
    slug: str,
    *,
    actor: str,
) -> MovedExample:
    """Örneği `slug` türüne taşır (modül açıklaması); commit etmez."""
    _require_actor(actor)
    check_move(session, layout, known, example, slug)
    from_slug, from_name, previous_label = example.type_slug, example.name, example.label
    note = moved_note(from_slug, slug)
    stored = relocate_example(layout, from_slug, from_name, slug, expected_sha256=example.sha256)
    example.type_slug = slug
    example.name = stored.path.name
    example.label = ExampleLabel.VERIFIED.value
    example.note = _append(example.note, note)
    item = example.training_item
    if item is not None:
        item.result_slug = slug
        item.note = _append(item.note, note)
    session.flush()
    record_event(
        session,
        EventType.TRAINING_EXAMPLE_MOVED,
        actor=actor,
        message=f"Eğitim örneği `{from_slug}` türünden `{slug}` türüne taşındı.",
        data={
            "example_file_id": example.id,
            "training_item_id": example.training_item_id,
            "from_slug": from_slug,
            "to_slug": slug,
            "previous_label": previous_label,
            "label": example.label,
        },
    )
    return MovedExample(example, from_slug, from_name, previous_label)


def check_remove(layout: DataLayout, example: ExampleFileRecord) -> None:
    """Çıkarma yapılabilir mi; değilse `ExampleDecisionError`. Hiçbir şey yazmaz."""
    _check_active(layout, example)


def remove_example(
    session: Session, layout: DataLayout, example: ExampleFileRecord, *, actor: str
) -> ExampleFileRecord:
    """Örneği örneklerden çıkarır: dosya eğitim arşivine taşınır, kayıt işaretlenir (modül
    açıklaması); commit etmez."""
    _require_actor(actor)
    check_remove(layout, example)
    stored = archive_example(
        layout, example.type_slug, example.name, expected_sha256=example.sha256
    )
    example.removed_at = utcnow()
    example.removed_by = actor
    example.removed_path = layout.relative(stored.path)
    example.note = _append(example.note, REMOVED_NOTE)
    item = example.training_item
    if item is not None:
        item.note = _append(item.note, REMOVED_NOTE)
    session.flush()
    record_event(
        session,
        EventType.TRAINING_EXAMPLE_REMOVED,
        actor=actor,
        message=f"Eğitim örneği `{example.type_slug}` örneklerinden çıkarıldı; arşive taşındı.",
        data={
            "example_file_id": example.id,
            "training_item_id": example.training_item_id,
            "type_slug": example.type_slug,
            "label": example.label,
        },
    )
    return example


def _check_active(layout: DataLayout, example: ExampleFileRecord) -> None:
    if example.removed_at is not None:
        raise ExampleDecisionError("Örnek zaten örneklerden çıkarılmış.")
    if example_path(layout, example.type_slug, example.name) is None:
        raise ExampleDecisionError("Örnek dosyası türün klasöründe bulunamadı; işlem yapılmadı.")


def _require_actor(actor: str) -> None:
    if not actor.strip():
        raise ValueError("Etiket kararı kullanıcı adıyla loglanır: actor boş olamaz")


def _append(note: str | None, addition: str) -> str:
    return f"{note}; {addition}" if note else addition
