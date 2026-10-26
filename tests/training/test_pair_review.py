"""Çift inceleme (PRD 11.9.3, 11.9.4; PLAN.md §D128): iki yapay zekâ aynı türü verirse örnek
doğrudan "doğrulanmış" olur; yoksa "AI kararı" kalır. Sağlayıcılar sahtedir (ağsız)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.provider import UsageTotals
from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import Event, ExampleFileRecord
from app.events import EventType
from app.storage import DataLayout
from app.training import KnownTypes
from app.training.classification import AI_CHECK_KEY, REVIEW_CHECK_KEY, apply_classification
from app.training.pair import (
    PAIR_ANTHROPIC_MODEL,
    PAIR_EFFORT,
    PAIR_OPENAI_MODEL,
    ReviewPair,
    build_review_pair,
)
from app.training.recheck import RecheckOutcome, pending_examples, recheck_example
from tests.recorded import source_events, source_message
from tests.training.test_classification import (
    SETTINGS,
    Classifier,
    _answer,
    _pending,
)

PASSPORT = {"catalog_slug": "turkish_passport", "country_iso3": "TUR", "doc_kind": "pasaport"}
OTHER = {"catalog_slug": "russian_passport", "country_iso3": "RUS", "doc_kind": "pasaport"}


class Named(Classifier):
    name = "ikinci"

    def __init__(self, model: str, *responses: object) -> None:
        super().__init__(*responses)
        self.model = model


@pytest.fixture(autouse=True)
def _catalog(session: Session) -> None:
    import_catalog(session, load_seed_catalog())
    session.flush()


def _place(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    second: object | None,
    *,
    answer: dict[str, Any] = PASSPORT,
) -> ExampleFileRecord:
    item = _pending(session, layout, known)
    second_arg = None if second is None else (Named("sonnet-test", second), _answer(**second))
    apply_classification(
        session,
        layout,
        item,
        _answer(**answer),
        provider=Named("sol-test"),
        known=known,
        second=second_arg,  # type: ignore[arg-type]
    )
    return session.scalars(select(ExampleFileRecord)).one()


def _verified_events(session: Session) -> list[Event]:
    return source_events(
        session,
        session.scalars(select(Event).where(Event.type == EventType.TRAINING_LABEL_VERIFIED.value)),
    )


def test_two_agreeing_reviews_save_the_example_as_verified_without_human_approval(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    example = _place(session, layout, known, PASSPORT)

    assert (example.type_slug, example.label) == ("turkish_passport", "verified")
    (event,) = _verified_events(session)
    assert event.actor == "system"
    assert event.data_json["review"] == "pair"
    assert event.data_json["models"] == ["ikinci:sol-test", "ikinci:sonnet-test"]
    assert "sol-test ve sonnet-test aynı türü verdi" in (
        source_message(session, example.note) or ""
    )
    review = example.training_item.checks_json[REVIEW_CHECK_KEY]
    assert review["agreed"] is True and review["slug"] == "turkish_passport"
    assert AI_CHECK_KEY in example.training_item.checks_json


@pytest.mark.parametrize(
    "second",
    [OTHER, {"catalog_slug": None, "country_iso3": None, "doc_kind": None}],
    ids=["baska-tur", "belirleyemedi"],
)
def test_a_disagreeing_second_review_leaves_the_example_for_manual_check(
    session: Session, layout: DataLayout, known: KnownTypes, second: dict[str, Any]
) -> None:
    example = _place(session, layout, known, second)

    assert (example.type_slug, example.label) == ("turkish_passport", "ai_decision")
    assert _verified_events(session) == []
    assert example.training_item.checks_json[REVIEW_CHECK_KEY]["agreed"] is False


def test_without_a_second_review_the_label_stays_ai_decision(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    example = _place(session, layout, known, None)

    assert example.label == "ai_decision"
    assert REVIEW_CHECK_KEY not in example.training_item.checks_json


# --- çiftin kurulumu ---------------------------------------------------------------------------


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "sqlite://",
        "anthropic_api_key": "ant-test",
        "openai_api_key": "oai-test",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_the_pair_is_pinned_to_sol_and_sonnet_at_low_effort_whatever_the_panel_says() -> None:
    pair = build_review_pair(
        _settings(openai_model="gpt-baska", openai_effort="max", anthropic_model="claude-baska")
    )

    assert pair is not None
    assert (pair.first.name, pair.first.model, pair.first.effort) == (
        "openai",
        PAIR_OPENAI_MODEL,
        PAIR_EFFORT,
    )
    assert (pair.second.name, pair.second.model, pair.second.effort) == (
        "anthropic",
        PAIR_ANTHROPIC_MODEL,
        PAIR_EFFORT,
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"anthropic_api_key": None},
        {"openai_api_key": None},
        {"training_auto_confirm": False},
    ],
    ids=["anthropic-anahtari-yok", "openai-anahtari-yok", "kapali"],
)
def test_no_pair_without_both_keys_or_when_turned_off(overrides: dict[str, Any]) -> None:
    assert build_review_pair(_settings(**overrides)) is None


def test_usage_totals_add_up_and_tolerate_missing_counts() -> None:
    usage = UsageTotals()
    usage.add(100, 20)
    usage.add(None, None)

    assert (usage.calls, usage.input_tokens, usage.output_tokens) == (2, 100, 20)


# --- mevcut "AI kararı" örneklerinin yeniden incelenmesi ---------------------------------------


def _pair(first: object, second: object) -> ReviewPair:
    return ReviewPair(Named("sol-test", first), Named("sonnet-test", second))  # type: ignore[arg-type]


def _ai_decision(session: Session, layout: DataLayout, known: KnownTypes) -> ExampleFileRecord:
    example = _place(session, layout, known, None)
    assert example.label == "ai_decision"
    return example


def _recheck(session: Session, layout: DataLayout, known: KnownTypes, pair: ReviewPair, example):
    return recheck_example(session, layout, SETTINGS, known, pair, example)


def test_recheck_verifies_when_both_models_confirm_the_current_type(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    example = _ai_decision(session, layout, known)

    result = _recheck(
        session, layout, known, _pair(_answer(**PASSPORT), _answer(**PASSPORT)), example
    )

    assert result.outcome is RecheckOutcome.VERIFIED
    assert (example.type_slug, example.label) == ("turkish_passport", "verified")
    assert _verified_events(session)[0].data_json["review"] == "pair"
    assert pending_examples(session) == []


def test_recheck_moves_the_example_when_both_models_agree_on_another_type(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    example = _ai_decision(session, layout, known)

    result = _recheck(session, layout, known, _pair(_answer(**OTHER), _answer(**OTHER)), example)

    assert result.outcome is RecheckOutcome.MOVED
    assert (example.type_slug, example.label) == ("russian_passport", "verified")


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (PASSPORT, OTHER),
        (PASSPORT, {"catalog_slug": None, "country_iso3": None, "doc_kind": None}),
        ({"catalog_slug": None, "country_iso3": None, "doc_kind": None}, PASSPORT),
    ],
    ids=["farkli", "ikinci-belirleyemedi", "birinci-belirleyemedi"],
)
def test_recheck_leaves_unsure_examples_as_ai_decision(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    first: dict[str, Any],
    second: dict[str, Any],
) -> None:
    example = _ai_decision(session, layout, known)

    result = _recheck(session, layout, known, _pair(_answer(**first), _answer(**second)), example)

    assert result.outcome is RecheckOutcome.UNSURE
    assert (example.type_slug, example.label) == ("turkish_passport", "ai_decision")
    assert _verified_events(session) == []


def test_a_failing_call_leaves_the_example_untouched_and_reports_only_the_error_type(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    class Failing(Named):
        def _request_training_classification(self, request: object) -> object:
            raise RuntimeError("ayrıntı kişisel değer içerebilir")

    example = _ai_decision(session, layout, known)
    pair = ReviewPair(Failing("sol-test"), Named("sonnet-test", _answer(**PASSPORT)))

    result = _recheck(session, layout, known, pair, example)

    assert result.outcome is RecheckOutcome.ERROR and result.error == "RuntimeError"
    assert example.label == "ai_decision"


def test_dry_run_changes_nothing(session: Session, layout: DataLayout, known: KnownTypes) -> None:
    example = _ai_decision(session, layout, known)
    pair = _pair(_answer(**PASSPORT), _answer(**PASSPORT))

    result = recheck_example(session, layout, SETTINGS, known, pair, example, apply=False)

    assert result.outcome is RecheckOutcome.VERIFIED
    assert example.label == "ai_decision"
    assert _verified_events(session) == []
