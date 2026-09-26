"""11.9.4 — etiket kararı çekirdeği: Doğrula (tek, toplu), Başka türe taşı (dosya taşınır, ad
çakışmasında `-2`), Örneklerden çıkar (eğitim arşivine taşınır, silinmez), olaylar ve çıkarılan
kaydın etkin aramalardan düşmesi (PLAN.md §C86 "Etiket kararı", §D58).

Veri sentetiktir (`tests/fixtures/gen.py`); gerçek kimlik belgesi yoktur."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Event,
    ExampleFileRecord,
    ExampleMethod,
    TrainingItem,
    TrainingItemStatus,
    TrainingMethod,
    TrainingRun,
    TrainingRunKind,
)
from app.events import EventType
from app.storage import ContentMismatchError, DataLayout, sha256_bytes
from app.storage.examples import (
    archive_example,
    check_example,
    list_examples,
    relocate_example,
    store_example,
)
from app.training import (
    ExampleDecisionError,
    KnownTypes,
    UnknownTypeError,
    create_run,
    move_example,
    place_example,
    remove_example,
    stage_file,
    verify_examples,
)
from app.training.decisions import REMOVED_NOTE, moved_note
from app.training.mechanical import recognize
from tests.fixtures.gen import make_pdf_bytes, make_portrait_image_bytes
from tests.training.invariants import assert_employee_data_untouched

LIMIT = 1024 * 1024
FROM_SLUG = "albanian_passport"
TO_SLUG = "afghan_passport"
ACTOR = "ik"


def _png(width: int) -> bytes:
    return make_portrait_image_bytes("PNG", (width, 300))


def _run(session: Session) -> TrainingRun:
    return create_run(session, kind=TrainingRunKind.UPLOAD, created_by=ACTOR)


def _placed(
    session: Session,
    layout: DataLayout,
    known: KnownTypes,
    content: bytes,
    *,
    slug: str = FROM_SLUG,
    name: str = "ornek.png",
    method: TrainingMethod = TrainingMethod.AI,
) -> ExampleFileRecord:
    item = stage_file(session, layout, _run(session), name, content, max_bytes=LIMIT)
    placement = place_example(session, layout, known, item, slug, method=method, note="AI kararı")
    assert placement.status is TrainingItemStatus.PLACED
    return placement.example


def _events(session: Session, event_type: EventType) -> list[Event]:
    return list(session.scalars(select(Event).where(Event.type == event_type.value)))


def _files(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def _examples(layout: DataLayout, slug: str) -> list[str]:
    return [example.name for example in list_examples(layout, slug)]


# --- Doğrula --------------------------------------------------------------------------------------


def test_verifying_an_ai_decision_labels_it_verified_and_logs_the_user(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    example = _placed(session, layout, known, _png(200))
    before = _files(layout.root)

    verified = verify_examples(session, [example], actor="ik.uzmani")

    assert verified == [example]
    assert example.label == "verified"
    assert _files(layout.root) == before  # dosya işlemi değil
    (event,) = _events(session, EventType.TRAINING_LABEL_VERIFIED)
    assert event.actor == "ik.uzmani"
    assert event.data_json == {
        "example_file_id": example.id,
        "training_item_id": example.training_item_id,
        "type_slug": FROM_SLUG,
        "previous_label": "ai_decision",
        "label": "verified",
    }
    assert "ornek" not in (event.message or "")  # dosya adı olaya girmez
    assert_employee_data_untouched(session, layout)


def test_bulk_verification_touches_only_active_ai_decisions(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    first = _placed(session, layout, known, _png(200), name="a.png")
    second = _placed(session, layout, known, _png(210), name="b.png")
    mechanical = _placed(
        session, layout, known, _png(220), name="c.png", method=TrainingMethod.MECHANICAL
    )
    manual = _placed(session, layout, known, _png(230), name="d.png", method=TrainingMethod.MANUAL)
    removed = _placed(session, layout, known, _png(240), name="e.png")
    remove_example(session, layout, removed, actor=ACTOR)

    verified = verify_examples(session, [first, second, mechanical, manual, removed], actor=ACTOR)

    assert verified == [first, second]
    assert (first.label, second.label, mechanical.label, manual.label, removed.label) == (
        "verified",
        "verified",
        None,
        "verified",
        "ai_decision",
    )
    assert len(_events(session, EventType.TRAINING_LABEL_VERIFIED)) == 2


def test_a_decision_needs_a_user_name(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    example = _placed(session, layout, known, _png(200))

    with pytest.raises(ValueError, match="actor"):
        verify_examples(session, [example], actor=" ")
    with pytest.raises(ValueError, match="actor"):
        move_example(session, layout, known, example, TO_SLUG, actor="")
    with pytest.raises(ValueError, match="actor"):
        remove_example(session, layout, example, actor="")
    assert example.label == "ai_decision"


# --- Başka türe taşı -----------------------------------------------------------------------------


def test_moving_relocates_the_file_and_updates_the_record_and_the_item(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = _png(200)
    example = _placed(session, layout, known, content)
    item = session.get_one(TrainingItem, example.training_item_id)
    staged = layout.resolve(item.staged_path or "")

    moved = move_example(session, layout, known, example, TO_SLUG, actor="ik.uzmani")

    assert (moved.from_slug, moved.from_name, moved.previous_label) == (
        FROM_SLUG,
        "ornek.png",
        "ai_decision",
    )
    assert _examples(layout, FROM_SLUG) == []
    assert _examples(layout, TO_SLUG) == ["ornek.png"]
    assert (layout.type_examples_dir(TO_SLUG) / "ornek.png").read_bytes() == content  # K11
    assert staged.read_bytes() == content  # `_egitim/gelen` kopyası kalır
    assert (example.type_slug, example.name, example.label, example.method) == (
        TO_SLUG,
        "ornek.png",
        "verified",
        "ai",
    )
    note = moved_note(FROM_SLUG, TO_SLUG)
    assert example.note == f"AI kararı; {note}"
    assert item.result_slug == TO_SLUG and (item.note or "").endswith(note)
    assert item.status == "placed"
    (event,) = _events(session, EventType.TRAINING_EXAMPLE_MOVED)
    assert event.actor == "ik.uzmani"
    assert event.data_json == {
        "example_file_id": example.id,
        "training_item_id": item.id,
        "from_slug": FROM_SLUG,
        "to_slug": TO_SLUG,
        "previous_label": "ai_decision",
        "label": "verified",
    }
    assert "ornek" not in (event.message or "")
    assert_employee_data_untouched(session, layout)


def test_a_name_collision_in_the_target_folder_takes_the_next_suffix(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    other = _png(300)
    store_example(
        layout, TO_SLUG, "ornek.png", other, check_example("ornek.png", other, max_bytes=LIMIT)
    )
    example = _placed(session, layout, known, _png(200))

    move_example(session, layout, known, example, TO_SLUG, actor=ACTOR)

    assert example.name == "ornek-2.png"
    assert _examples(layout, TO_SLUG) == ["ornek-2.png", "ornek.png"]
    assert (layout.type_examples_dir(TO_SLUG) / "ornek.png").read_bytes() == other


@pytest.mark.parametrize("target", ["", "not_a_known_type"])
def test_an_unknown_target_type_moves_nothing(
    session: Session, layout: DataLayout, known: KnownTypes, target: str
) -> None:
    example = _placed(session, layout, known, _png(200))
    before = _files(layout.root)

    with pytest.raises(UnknownTypeError):
        move_example(session, layout, known, example, target, actor=ACTOR)

    assert _files(layout.root) == before
    assert (example.type_slug, example.label) == (FROM_SLUG, "ai_decision")
    assert _events(session, EventType.TRAINING_EXAMPLE_MOVED) == []


def test_the_same_type_or_the_same_content_in_the_target_is_refused(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = _png(200)
    example = _placed(session, layout, known, content)
    # Aynı içerik hedef klasörde kayıtsız duruyor (el ile yüklenmiş).
    store_example(
        layout, TO_SLUG, "elle.png", content, check_example("x.png", content, max_bytes=LIMIT)
    )
    before = _files(layout.root)

    with pytest.raises(ExampleDecisionError, match="zaten bu türde"):
        move_example(session, layout, known, example, FROM_SLUG, actor=ACTOR)
    with pytest.raises(ExampleDecisionError, match=r"zaten örnek \(elle\.png\)"):
        move_example(session, layout, known, example, TO_SLUG, actor=ACTOR)

    assert _files(layout.root) == before
    assert example.type_slug == FROM_SLUG


def test_a_recorded_duplicate_in_the_target_is_refused(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = _png(200)
    example = _placed(session, layout, known, content)
    # Aynı içeriğin hedef türde kaydı var (dosyası başka adla); yerleştirme bunu önler ama elle
    # oluşmuş olabilir.
    session.add(
        ExampleFileRecord(
            type_slug=TO_SLUG,
            name="kayitli.png",
            sha256=example.sha256,
            method=ExampleMethod.LEGACY.value,
        )
    )
    session.flush()

    with pytest.raises(ExampleDecisionError, match=r"zaten örnek \(kayitli\.png\)"):
        move_example(session, layout, known, example, TO_SLUG, actor=ACTOR)


def test_a_missing_file_or_changed_content_moves_nothing(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    example = _placed(session, layout, known, _png(200))
    path = layout.type_examples_dir(FROM_SLUG) / example.name
    path.write_bytes(_png(250))  # içerik kayıttakinden farklı

    with pytest.raises(ContentMismatchError):
        move_example(session, layout, known, example, TO_SLUG, actor=ACTOR)

    assert path.exists() and _examples(layout, TO_SLUG) == []
    path.rename(path.with_name("baska.png"))
    with pytest.raises(ExampleDecisionError, match="bulunamadı"):
        move_example(session, layout, known, example, TO_SLUG, actor=ACTOR)
    with pytest.raises(ExampleDecisionError, match="bulunamadı"):
        remove_example(session, layout, example, actor=ACTOR)


# --- Örneklerden çıkar ----------------------------------------------------------------------------


def test_removing_archives_the_file_and_marks_the_record_without_deleting_anything(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = _png(200)
    example = _placed(session, layout, known, content)
    item = session.get_one(TrainingItem, example.training_item_id)
    count_before = len(_files(layout.root))

    remove_example(session, layout, example, actor="ik.uzmani")

    archived = f"KnownDocuments/_egitim/cikarilan/{FROM_SLUG}/ornek.png"
    assert _examples(layout, FROM_SLUG) == []
    assert (layout.root / archived).read_bytes() == content
    assert len(_files(layout.root)) == count_before  # hiçbir dosya silinmedi
    assert example.removed_by == "ik.uzmani" and example.removed_at is not None
    assert example.removed_path == archived
    assert (example.type_slug, example.name, example.label) == (
        FROM_SLUG,
        "ornek.png",
        "ai_decision",
    )
    assert (example.note or "").endswith(REMOVED_NOTE)
    assert (item.status, (item.note or "").endswith(REMOVED_NOTE)) == ("placed", True)
    assert session.get(ExampleFileRecord, example.id) is example  # kayıt silinmedi
    (event,) = _events(session, EventType.TRAINING_EXAMPLE_REMOVED)
    assert event.actor == "ik.uzmani"
    assert event.data_json == {
        "example_file_id": example.id,
        "training_item_id": item.id,
        "type_slug": FROM_SLUG,
        "label": "ai_decision",
    }
    with pytest.raises(ExampleDecisionError, match="zaten örneklerden çıkarılmış"):
        remove_example(session, layout, example, actor=ACTOR)
    with pytest.raises(ExampleDecisionError, match="zaten örneklerden çıkarılmış"):
        move_example(session, layout, known, example, TO_SLUG, actor=ACTOR)
    assert_employee_data_untouched(session, layout)


def test_a_second_removal_of_the_same_name_takes_the_next_suffix_in_the_archive(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    first = _placed(session, layout, known, _png(200))
    remove_example(session, layout, first, actor=ACTOR)
    # Çıkarılan örneğin adı klasörde yeniden kullanılabilir (koşullu tekil dizin).
    second = _placed(session, layout, known, _png(210))
    assert second.name == first.name == "ornek.png"

    remove_example(session, layout, second, actor=ACTOR)

    assert second.removed_path == f"KnownDocuments/_egitim/cikarilan/{FROM_SLUG}/ornek-2.png"
    session.commit()


def test_the_active_name_stays_unique(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    example = _placed(session, layout, known, _png(200))
    session.commit()
    session.add(
        ExampleFileRecord(
            type_slug=FROM_SLUG, name=example.name, sha256="0" * 64, method=ExampleMethod.AI.value
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_removed_content_is_no_longer_an_example_for_placement_or_recognition(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = _png(200)
    example = _placed(session, layout, known, content)
    remove_example(session, layout, example, actor=ACTOR)

    # SHA-256 dizini çıkarılan kaydı görmez: mekanik tanıma onu eski türe koymaz.
    item = stage_file(session, layout, _run(session), "yeniden.png", content, max_bytes=LIMIT)
    recognition = recognize(session, known, item, content, inventory=None)
    assert recognition.slug is None
    # Yerleştirme de tekrar saymaz: içerik yeniden (başka türe) yerleşebilir.
    placement = place_example(session, layout, known, item, TO_SLUG, method=TrainingMethod.MANUAL)
    assert placement.status is TrainingItemStatus.PLACED
    assert _examples(layout, TO_SLUG) == ["yeniden.png"]


# --- depolama yardımcıları ------------------------------------------------------------------------


def test_storage_moves_refuse_an_unlisted_name_and_keep_the_source_on_mismatch(
    layout: DataLayout,
) -> None:
    content = make_pdf_bytes(1)
    stored = store_example(
        layout, FROM_SLUG, "a.pdf", content, check_example("a.pdf", content, max_bytes=LIMIT)
    )

    with pytest.raises(FileNotFoundError):
        relocate_example(layout, FROM_SLUG, "../a.pdf", TO_SLUG, expected_sha256=stored.sha256)
    with pytest.raises(ContentMismatchError):
        archive_example(layout, FROM_SLUG, stored.name, expected_sha256="0" * 64)
    assert _examples(layout, FROM_SLUG) == ["a.pdf"]
    assert not layout.training_removed_dir(FROM_SLUG).exists() or not any(
        path.is_file() and not path.name.startswith(".")
        for path in layout.training_removed_dir(FROM_SLUG).iterdir()
    )

    moved = relocate_example(
        layout, FROM_SLUG, "a.pdf", TO_SLUG, expected_sha256=sha256_bytes(content)
    )

    assert moved.path == layout.type_examples_dir(TO_SLUG) / "a.pdf"
    assert _examples(layout, FROM_SLUG) == [] and moved.path.read_bytes() == content
