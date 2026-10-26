"""Mevcut "AI kararı" örneklerinin çift incelemesi — PRD 11.9.4; PLAN.md §D128.

Daha önce tek yapay zekâyla yerleşmiş ve elle kontrol bekleyen ("AI kararı") örnekler, yeni
örneklerle aynı kurala göre yeniden incelenir (`app.training.pair`): GPT-6.1 Sol ve Claude Sonnet
5.5 (ikisi `low`) örneği ayrı ayrı sınıflandırır; sonuç:

- **Doğrulandı (`verified`)** — ikisi de örneğin bugünkü türünü verdi → etiket "doğrulanmış".
- **Taşındı (`moved`)** — ikisi de aynı ama başka bir bilinen türü verdi → örnek o türe taşınır
  (`move_example`) ve "doğrulanmış" olur.
- **Belirsiz (`unsure`)** — ikisi farklı tür verdi ya da biri türü belirleyemedi → örnek olduğu gibi
  "AI kararı" kalır, insan kontrolü bekler.
- **Hata (`error`)** — bir çağrı ya da dosya okuma başarısız → örnek değişmez.

Kararı sistem verir (`system`); olaylar `review: pair` ve iki modelin adını taşır. Dosyaya
dokunulmaz (taşıma dışında), kişisel değer okunmaz (istek eğitim sınıflandırmasıyla aynıdır).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.prompts.training_classification import build_training_classification_instructions
from app.ai.provider import UsageTotals
from app.catalog.sync import export_catalog
from app.config import Settings
from app.db.models import ExampleFileRecord, ExampleLabel
from app.storage import DataLayout
from app.storage.examples import example_path
from app.storage.filetype import detect_file_kind
from app.training.classification import (
    ClassificationSource,
    build_request,
    resolve_classification,
)
from app.training.decisions import move_example, verify_examples
from app.training.known_types import KnownTypes, build_known_types
from app.training.pair import ReviewPair, pair_event_data, pair_note
from app.training.placement import SYSTEM_ACTOR


class RecheckOutcome(StrEnum):
    VERIFIED = "verified"
    MOVED = "moved"
    UNSURE = "unsure"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class RecheckResult:
    """Bir örneğin incelemesi: bugünkü tür, iki modelin eşlenen türü ve sonuç."""

    example_id: int
    current_slug: str
    first_slug: str | None
    second_slug: str | None
    outcome: RecheckOutcome
    error: str | None = None


def pending_examples(session: Session, *, limit: int | None = None) -> list[ExampleFileRecord]:
    """Etkin "AI kararı" örnekleri (kayıt sırasıyla)."""
    query = (
        select(ExampleFileRecord)
        .where(
            ExampleFileRecord.label == ExampleLabel.AI_DECISION.value,
            ExampleFileRecord.removed_at.is_(None),
        )
        .order_by(ExampleFileRecord.id)
    )
    if limit is not None:
        query = query.limit(limit)
    return list(session.scalars(query))


def build_source(session: Session, settings: Settings, content: bytes) -> ClassificationSource:
    """Örnek dosyasının sınıflandırma girdisi (talimat: o anki katalog ve tür sözlüğü)."""
    catalog = export_catalog(session)
    known = build_known_types(catalog)
    return ClassificationSource(
        item_id=0,
        content=content,
        file_kind=detect_file_kind(content),
        page_count=1,
        instructions=build_training_classification_instructions(
            catalog, known.doc_kinds, configured_budget=settings.catalog_token_budget
        ),
    )


def recheck_example(
    session: Session,
    layout: DataLayout,
    settings: Settings,
    known: KnownTypes,
    pair: ReviewPair,
    example: ExampleFileRecord,
    *,
    apply: bool = True,
    source_for: Callable[[bytes], ClassificationSource] | None = None,
) -> RecheckResult:
    """Tek örneği iki modelle inceler; `apply` ise sonucu uygular (commit etmez). Dosya okunamazsa
    ya da çağrı hata verirse `error` döner ve örnek değişmez."""
    slug = example.type_slug
    path = example_path(layout, slug, example.name)
    if path is None:
        return RecheckResult(example.id, slug, None, None, RecheckOutcome.ERROR, "FileNotFound")
    try:
        source = (source_for or (lambda data: build_source(session, settings, data)))(
            path.read_bytes()
        )
        request = build_request(source, settings)
        first = pair.first.classify_training_page(request)
        second = pair.second.classify_training_page(request)
    except Exception as exc:  # noqa: BLE001 — örnek başına izole; yalnız hata türü saklanır
        return RecheckResult(example.id, slug, None, None, RecheckOutcome.ERROR, type(exc).__name__)
    first_known = resolve_classification(known, first).known
    second_known = resolve_classification(known, second).known
    first_slug = first_known.slug if first_known is not None else None
    second_slug = second_known.slug if second_known is not None else None
    if first_slug is None or first_slug != second_slug:
        return RecheckResult(example.id, slug, first_slug, second_slug, RecheckOutcome.UNSURE)
    if first_slug == slug:
        outcome = RecheckOutcome.VERIFIED
        if apply:
            verify_examples(
                session,
                [example],
                actor=SYSTEM_ACTOR,
                event_data=pair_event_data(pair.first, pair.second),
                note=pair_note(pair.first, pair.second),
            )
    else:
        outcome = RecheckOutcome.MOVED
        if apply:
            move_example(session, layout, known, example, first_slug, actor=SYSTEM_ACTOR)
    return RecheckResult(example.id, slug, first_slug, second_slug, outcome)


def usage_of(pair: ReviewPair) -> dict[str, UsageTotals]:
    """Modele göre harcanan belirteçler (maliyet raporu için)."""
    return {p.model: p.usage for p in pair.providers}


def summarize(results: Sequence[RecheckResult]) -> dict[str, int]:
    counts = {outcome.value: 0 for outcome in RecheckOutcome}
    for result in results:
        counts[result.outcome.value] += 1
    return counts
