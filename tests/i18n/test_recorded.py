"""10.10.6 — sistem metni kayıtta İngilizce, panelde isteğin dilinde (PLAN.md §D121).

`app.i18n.recorded`: `Translatable` kayda İngilizce kataloğuyla düz metin olarak yazılır, kaynağı
(şablon + değerler, iç içe olanlar dahil) `recorded_texts`'e metnin özetiyle girer; panel kayıtlı
metni geri çağırıp isteğin dilinde gösterir. Kaynağı bilinmeyen metin (eski Türkçe kayıt, yapay
zekâ notu, insanın notu) olduğu gibi kalır.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from app.db.models import Base, Event, RecordedText, TrainingItem, TrainingRun
from app.db.session import create_db_engine, create_session_factory
from app.events import EventType, record_event
from app.i18n import N_, Translatable, join_text, translate, use_language
from app.i18n.recorded import (
    append_text,
    english,
    localized,
    recall,
    recall_texts,
    record_text,
)
from app.matching.status import inactive_employee_reason, is_inactive_employee_reason
from app.pipeline.group import PageRef, UnknownDocumentType

UNKNOWN_TR = (
    "Bilinmeyen belge türü (04.6.1): bu adayın (dosya 3, sayfa 2) türü katalogda yok; önerilen "
    'aday tür: "Peruvian Diploma". Belge katalogdaki bir türe zorla atanmaz.'
)
UNKNOWN_EN = (
    "Unknown document type (04.6.1): the type of this candidate (file 3, page 2) is not in the "
    'catalog; proposed candidate type: "Peruvian Diploma". The document is not forced into a '
    "catalog type."
)
UNKNOWN_SR = (
    "Nepoznat tip dokumenta (04.6.1): tip ovog kandidata (datoteka 3, stranica 2) nije u "
    'katalogu; predloženi kandidat tip: "Peruvian Diploma". Dokument se ne dodeljuje silom nekom '
    "tipu iz kataloga."
)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    db_engine = create_db_engine(f"sqlite:///{(tmp_path / 'recorded.db').as_posix()}")
    Base.metadata.create_all(db_engine)
    yield db_engine
    db_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with create_session_factory(engine)() as db_session:
        yield db_session


def _unknown() -> str:
    return UnknownDocumentType(
        pages=(PageRef(3, 1),), candidate_type_name="  Peruvian   Diploma "
    ).reason


def _count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(RecordedText)) or 0


def test_reason_is_source_language_in_code_and_english_in_the_record(session: Session) -> None:
    reason = _unknown()

    # Kodda kaynak dil (Türkçe) kalır: birim testleri ve günlük aynı metni görür (§D95).
    assert isinstance(reason, Translatable)
    assert reason == UNKNOWN_TR
    stored = record_text(session, reason)

    assert stored == english(reason) == UNKNOWN_EN
    assert type(stored) is str
    assert _count(session) == 1


@pytest.mark.parametrize(
    ("language", "expected"), [("en", UNKNOWN_EN), ("tr", UNKNOWN_TR), ("sr", UNKNOWN_SR)]
)
def test_recorded_reason_is_shown_in_the_request_language(
    session: Session, language: str, expected: str
) -> None:
    stored = record_text(session, _unknown())
    session.commit()

    shown = recall(session, stored)

    assert isinstance(shown, Translatable)
    with use_language(language):
        assert translate(shown) == expected


def test_nested_and_joined_reasons_survive_the_round_trip(session: Session) -> None:
    inner = Translatable(N_("dosya {file}, sayfa {pages}"), file=7, pages="1, 2")
    joined = join_text(
        (
            Translatable(N_("Okunamayan alanlar: {fields}"), fields="expiry_date"),
            Translatable(N_("Eşleşmemiş ön yüzler: {pages}."), pages=inner),
        )
    )
    stored = record_text(session, joined)

    assert stored == "Unreadable fields: expiry_date Unpaired front sides: file 7, page 1, 2."
    recalled = recall_texts(session, [stored])
    with use_language("sr"):
        assert translate(recalled[stored]) == (
            "Nečitljiva polja: expiry_date Neuparene prednje strane: datoteka 7, stranica 1, 2."
        )
    with use_language("tr"):
        assert translate(recalled[stored]) == str(joined)


def test_same_text_is_recorded_once(session: Session) -> None:
    record_text(session, _unknown())
    record_text(session, _unknown())
    session.commit()

    assert _count(session) == 1


def test_plain_text_is_neither_translated_nor_recorded(session: Session) -> None:
    # Yapay zekâ notu, insanın notu, eski Türkçe kayıt: düz metin olduğu gibi kalır.
    legacy = "Okunamayan alanlar: document_number"
    note = "Bottom edge slightly blurred."

    assert record_text(session, legacy) == legacy
    assert record_text(session, note) == note
    assert _count(session) == 0
    assert recall(session, legacy) == legacy
    assert localized(recall_texts(session, [legacy, note]), note) == note


def test_join_of_plain_texts_stays_plain() -> None:
    assert join_text(["a", "", "b"], "; ") == "a; b"
    assert not isinstance(join_text(["a", "b"]), Translatable)


def test_columns_get_english_text_at_flush(session: Session) -> None:
    # Olay mesajı ve eğitim notu sütununa atanan `Translatable` Türkçe düzleşerek kayda giremez.
    event = record_event(session, EventType.QUEUED_UNKNOWN, message=_unknown())
    run = TrainingRun(kind="upload", created_by="ik")
    session.add(run)
    session.flush()
    item = TrainingItem(run_id=run.id, original_name="a.pdf")
    item.note = Translatable(N_("İK yoksaydı"))
    session.add(item)
    session.commit()

    assert session.scalar(select(Event.message).where(Event.id == event.id)) == UNKNOWN_EN
    assert session.scalar(select(TrainingItem.note).where(TrainingItem.id == item.id)) == (
        "HR dismissed"
    )


def test_appended_note_keeps_each_part_translatable(session: Session) -> None:
    first = record_text(session, Translatable(N_("İK yoksaydı")))
    combined = append_text(session, first, Translatable(N_("İK yoksaymayı geri aldı")))
    stored = record_text(session, combined)

    assert stored == "HR dismissed; HR undid the dismissal"
    with use_language("tr"):
        assert translate(recall(session, stored)) == "İK yoksaydı; İK yoksaymayı geri aldı"
    # Kaynağı bilinmeyen eski not olduğu gibi kalır, ek çevrilir.
    legacy = append_text(session, "eski not", Translatable(N_("İK yoksaydı")))
    with use_language("sr"):
        assert translate(legacy) == "eski not; HR je zanemario"


def test_core_update_records_the_note_explicitly(session: Session) -> None:
    run = TrainingRun(kind="upload", created_by="ik")
    session.add(run)
    session.flush()
    item = TrainingItem(run_id=run.id, original_name="a.pdf")
    session.add(item)
    session.flush()

    session.execute(
        update(TrainingItem)
        .where(TrainingItem.id == item.id)
        .values(note=record_text(session, Translatable(N_("İK yoksaydı"))))
    )
    session.commit()

    assert session.scalar(select(TrainingItem.note)) == "HR dismissed"
    assert _count(session) == 1


def test_inactive_employee_code_survives_english_and_is_still_recognised(session: Session) -> None:
    # Kuyruk öğesi detayı pasif çalışan hükmünü gerekçedeki koddan tanır (10.5.7): İngilizce
    # kayıtta da, eski Türkçe kayıtta da.
    reason = inactive_employee_reason("E0007")
    stored = record_text(session, reason)

    assert "(inactive_employee)" in stored
    assert is_inactive_employee_reason(stored)
    assert is_inactive_employee_reason(str(reason))
