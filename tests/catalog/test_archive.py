"""11.1.6, 11.5.7 — tür arşivi, geri alma, etkinleştirme olayları ve aday türü retten geri alma.

Arşivli tür silinmez (R11): kaydı `load_record` ile okunur, `export_catalog`/YAML'da kalır; ama
listeden (`list_types` varsayılanı), analiz talimatından, grup seçicilerinden ve eğitimin bilinen
türlerinden kalkar. Boru hattının adıyla andığı türler (`PROTECTED_SLUGS`) arşivlenemez; liste kodun
kendisinden taranır, elle sayılmaz (PLAN.md §C92-a)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.prompts.page_analysis import build_page_analysis_instructions
from app.catalog import (
    PROTECTED_SLUGS,
    CandidateNotFoundError,
    CandidateNotRejectedError,
    CatalogEntry,
    FileType,
    TypeNotFoundError,
    TypeProtectedError,
    analyzable_types,
    archive_type,
    create_type,
    dump_catalog_yaml,
    export_catalog,
    import_catalog,
    list_candidate_types,
    list_types,
    load_record,
    load_seed_catalog,
    parse_catalog_yaml,
    reject_candidate_type,
    restore_candidate_type,
    restore_type,
    set_type_active,
    validate_catalog,
)
from app.db.models import (
    CandidateTypeStatus,
    Event,
    KnownDocumentType,
    Page,
    Upload,
    UploadFile,
    record_candidate_type_sighting,
)
from app.events import EventType
from app.groups import GroupFormError, add_item, create_group, label_choices, type_choices
from app.training.known_types import SuggestedTypeRow, build_known_types, load_known_types
from tests.catalog.conftest import RecordFactory

ROOT = Path(__file__).resolve().parents[2]
ACTOR = "ik-yonetici"


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db_session:
        yield db_session


def _add(session: Session, make_record: RecordFactory, **overrides: Any) -> CatalogEntry:
    (entry,) = validate_catalog([make_record(**overrides)])
    create_type(session, entry)
    session.commit()
    return entry


def _events(session: Session, *types: EventType) -> list[Event]:
    return list(
        session.scalars(
            select(Event).where(Event.type.in_([t.value for t in types])).order_by(Event.id)
        )
    )


# --- korunan türler ------------------------------------------------------------------------------


def test_every_slug_the_code_names_is_protected() -> None:
    """Açık `*_SLUG = "..."` sabitiyle anılan her tür arşivlenemez (ek ve profil fotoğrafı dahil);
    `_` ile başlayan özel sabitler katalog türü değildir (ör. `prefill._PROBE_SLUG`)."""
    named = set()
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        named |= set(
            re.findall(
                r'^\s*[A-Z][A-Z_]*_SLUG\s*(?::\s*str\s*)?=\s*"([a-z][a-z0-9_]*)"', text, re.M
            )
        )

    assert {"attachment", "profile_picture"} <= named
    assert named <= PROTECTED_SLUGS


def test_a_protected_type_cannot_be_archived(session: Session, make_record: RecordFactory) -> None:
    _add(session, make_record, slug="profile_picture", name="Profile Picture")

    with pytest.raises(TypeProtectedError):
        archive_type(session, "profile_picture", actor=ACTOR)
    session.rollback()

    assert session.get_one(KnownDocumentType, "profile_picture").archived_at is None
    assert _events(session, EventType.TYPE_ARCHIVED) == []


def test_an_unknown_type_is_not_found(session: Session) -> None:
    with pytest.raises(TypeNotFoundError):
        archive_type(session, "nope", actor=ACTOR)
    with pytest.raises(TypeNotFoundError):
        restore_type(session, "nope", actor=ACTOR)


# --- arşiv ve geri alma --------------------------------------------------------------------------


def test_an_archived_type_leaves_the_list_and_the_prompt_but_keeps_its_record(
    session: Session, make_record: RecordFactory
) -> None:
    _add(session, make_record)
    _add(session, make_record, slug="other_card", name="Other Card")

    assert archive_type(session, "sample_card", actor=ACTOR) is True
    session.commit()

    assert [item.slug for item in list_types(session)] == ["other_card"]
    archived = {item.slug: item for item in list_types(session, include_archived=True)}
    assert set(archived) == {"sample_card", "other_card"}
    assert archived["sample_card"].archived_by == ACTOR
    assert archived["sample_card"].archived_at is not None
    record = load_record(session, "sample_card")  # belge listeleri adı okumaya devam eder
    assert record["name"] == "Sample Card"
    assert record["archived_at"] is not None
    catalog = export_catalog(session)
    assert catalog.get("sample_card") is not None  # silinmedi, dışa aktarımda
    assert [entry.slug for entry in analyzable_types(catalog)] == ["other_card"]
    assert "sample_card" not in build_page_analysis_instructions(catalog).known_slugs
    (event,) = _events(session, EventType.TYPE_ARCHIVED)
    assert (event.actor, event.data_json) == (ACTOR, {"slug": "sample_card"})


def test_archiving_twice_and_restoring_a_current_type_write_nothing(
    session: Session, make_record: RecordFactory
) -> None:
    _add(session, make_record)

    assert restore_type(session, "sample_card", actor=ACTOR) is False
    assert archive_type(session, "sample_card", actor=ACTOR) is True
    assert archive_type(session, "sample_card", actor=ACTOR, bulk=True) is False
    session.commit()

    assert len(_events(session, EventType.TYPE_ARCHIVED)) == 1
    assert _events(session, EventType.TYPE_RESTORED) == []


def test_restoring_brings_the_type_back_with_its_activity(
    session: Session, make_record: RecordFactory
) -> None:
    _add(session, make_record)
    set_type_active(session, "sample_card", False, actor=ACTOR)
    archive_type(session, "sample_card", actor=ACTOR)
    session.commit()

    assert restore_type(session, "sample_card", actor="ik-iki") is True
    session.commit()

    (item,) = list_types(session)
    assert (item.slug, item.active, item.archived_at, item.archived_by) == (
        "sample_card",
        False,
        None,
        None,
    )
    (event,) = _events(session, EventType.TYPE_RESTORED)
    assert (event.actor, event.data_json) == ("ik-iki", {"slug": "sample_card"})
    set_type_active(session, "sample_card", True, actor=ACTOR)
    assert "sample_card" in build_page_analysis_instructions(export_catalog(session)).known_slugs


def test_activity_changes_write_events_only_when_the_state_changes(
    session: Session, make_record: RecordFactory
) -> None:
    _add(session, make_record)

    assert set_type_active(session, "sample_card", True, actor=ACTOR) is False
    assert set_type_active(session, "sample_card", False, actor=ACTOR) is True
    assert set_type_active(session, "sample_card", True, actor="ik-iki", bulk=True) is True
    session.commit()

    events = _events(session, EventType.TYPE_ACTIVATED, EventType.TYPE_DEACTIVATED)
    assert [(e.type, e.actor, e.data_json) for e in events] == [
        ("TYPE_DEACTIVATED", ACTOR, {"slug": "sample_card"}),
        ("TYPE_ACTIVATED", "ik-iki", {"slug": "sample_card", "bulk": True}),
    ]


def test_an_archived_attachment_like_type_is_not_given_to_word_files(
    session: Session, make_record: RecordFactory
) -> None:
    _add(
        session,
        make_record,
        slug="office_file",
        name="Office File",
        expected_file_types=["docx"],
        analyze=False,
        required_fields=[],
        allowed_conversions=[],
        output_format="keep",
    )
    assert export_catalog(session).unanalyzed_entry_for(FileType.DOCX) is not None

    archive_type(session, "office_file", actor=ACTOR)

    assert export_catalog(session).unanalyzed_entry_for(FileType.DOCX) is None


# --- YAML dışa/içe aktarım -----------------------------------------------------------------------


def test_the_export_writes_archived_at_only_for_archived_types_and_the_import_keeps_it(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    with session_factory() as session:
        _add(session, make_record)
        _add(session, make_record, slug="other_card", name="Other Card")
        archive_type(session, "sample_card", actor=ACTOR)
        session.commit()
        archived_at = session.get_one(KnownDocumentType, "sample_card").archived_at
        text = dump_catalog_yaml(export_catalog(session))

    assert text.count("archived_at:") == 1
    assert dump_catalog_yaml(parse_catalog_yaml(text)) == text  # kanonik biçim korunur

    # Başka bir veritabanına içe aktarım: arşiv zamanı dosyadan gelir.
    with session_factory() as session:
        session.query(KnownDocumentType).delete()
        session.commit()
        result = import_catalog(session, parse_catalog_yaml(text))
        session.commit()
        assert set(result.created) == {"sample_card", "other_card"}
        assert session.get_one(KnownDocumentType, "sample_card").archived_at == archived_at
        assert session.get_one(KnownDocumentType, "other_card").archived_at is None


def test_an_old_yaml_without_the_field_reads_and_leaves_the_archive_alone(
    session: Session, make_record: RecordFactory
) -> None:
    _add(session, make_record)
    archive_type(session, "sample_card", actor=ACTOR)
    session.commit()
    old = dump_catalog_yaml(validate_catalog([make_record()]))
    assert "archived_at" not in old

    result = import_catalog(session, parse_catalog_yaml(old))
    session.commit()

    assert result.unchanged == ("sample_card",)
    row = session.get_one(KnownDocumentType, "sample_card")
    assert (row.archived_at is not None, row.archived_by) == (True, ACTOR)


def test_the_seed_catalog_stays_canonical_without_the_archive_field() -> None:
    seed = load_seed_catalog()

    assert all(entry.archived_at is None for entry in seed)
    assert "archived_at" not in dump_catalog_yaml(seed)


def test_a_naive_archive_time_is_refused(make_record: RecordFactory) -> None:
    with pytest.raises(Exception, match="archived_at"):
        validate_catalog([make_record(archived_at="2026-09-29T10:00:00")])


# --- seçiciler ve eğitimin bilinen türleri ------------------------------------------------------


def test_training_known_types_drop_an_archived_type_and_its_suggested_twin(
    session: Session, make_record: RecordFactory
) -> None:
    _add(session, make_record)
    _add(session, make_record, slug="other_card", name="Other Card")
    twin = SuggestedTypeRow(
        slug="sample_card",
        name="Sample Card Alias",
        file_label="Sample Card",
        country_iso3="SRB",
        country_iso2="RS",
        doc_kind="kimlik_karti",
    )
    assert build_known_types(export_catalog(session), [twin]).get("sample_card") is not None

    archive_type(session, "sample_card", actor=ACTOR)

    known = build_known_types(export_catalog(session), [twin])
    assert known.get("sample_card") is None
    assert known.match_name("Sample Card Alias") is None
    assert known.get("other_card") is not None
    assert load_known_types(session).get("sample_card") is None


def test_group_selectors_drop_an_archived_type_but_the_display_still_knows_it(
    session: Session, make_record: RecordFactory
) -> None:
    _add(session, make_record, file_label="Sample Label")
    _add(session, make_record, slug="other_card", name="Other Card", file_label="Other Label")
    archive_type(session, "sample_card", actor=ACTOR)
    session.commit()

    assert [choice.slug for choice in type_choices(session)] == ["other_card"]
    assert [choice.label for choice in label_choices(session)] == ["Other Label"]
    assert {choice.slug for choice in type_choices(session, include_archived=True)} == {
        "sample_card",
        "other_card",
    }
    assert "Sample Label" in {
        choice.label for choice in label_choices(session, include_archived=True)
    }
    group = create_group(session, name="Sirbistan basvurusu", description=None, actor=ACTOR)
    with pytest.raises(GroupFormError):
        add_item(session, group.id, match_kind="type", type_slug="sample_card", actor=ACTOR)
    with pytest.raises(GroupFormError):
        add_item(session, group.id, match_kind="label", file_label="Sample Label", actor=ACTOR)


# --- 11.5.7: aday türü retten geri alma ----------------------------------------------------------


def _candidate(session: Session, name: str = "Peruvian Diploma") -> int:
    session.add(Upload(id="u_20260929_0001", channel="web"))
    upload_file = UploadFile(
        upload_id="u_20260929_0001",
        original_name="diploma.pdf",
        stored_path="inbox/u_20260929_0001/diploma.pdf",
        sha256="0" * 64,
        mime="application/pdf",
        page_count=1,
    )
    page = Page(file=upload_file, index=0, image_path="cache/diploma-0.png")
    session.add_all([upload_file, page])
    session.flush()
    candidate = record_candidate_type_sighting(
        session, proposed_name=name, upload_id="u_20260929_0001", page_id=page.id
    ).candidate_type
    session.commit()
    return candidate.id


def test_a_rejected_candidate_is_restored_to_pending_with_an_event(session: Session) -> None:
    candidate_id = _candidate(session)
    reject_candidate_type(session, candidate_id, actor=ACTOR)
    session.commit()
    assert [item.id for item in list_candidate_types(session, CandidateTypeStatus.REJECTED)] == [
        candidate_id
    ]

    restored = restore_candidate_type(session, candidate_id, actor="ik-iki")
    session.commit()

    assert restored.status == CandidateTypeStatus.PENDING.value
    assert [item.id for item in list_candidate_types(session)] == [candidate_id]
    assert list_candidate_types(session, CandidateTypeStatus.REJECTED) == []
    (event,) = _events(session, EventType.CANDIDATE_TYPE_RESTORED)
    assert (event.actor, event.data_json) == (
        "ik-iki",
        {"candidate_type_id": candidate_id, "candidate_type_name": "Peruvian Diploma"},
    )


def test_only_a_rejected_candidate_is_restored(session: Session) -> None:
    candidate_id = _candidate(session)

    with pytest.raises(CandidateNotRejectedError) as raised:
        restore_candidate_type(session, candidate_id, actor=ACTOR)
    assert raised.value.status == CandidateTypeStatus.PENDING.value
    with pytest.raises(CandidateNotFoundError):
        restore_candidate_type(session, candidate_id + 99, actor=ACTOR)
    assert _events(session, EventType.CANDIDATE_TYPE_RESTORED) == []
