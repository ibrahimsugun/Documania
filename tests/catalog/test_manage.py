"""11.1.1 — tür oluşturma, düzenleme ve pasifleştirme veritabanına yazılır; silme yoktur (K16).

Değişiklik `export_catalog` ile okunur: analiz kataloğu her çalıştığında tabloyu baştan okur, bu
yüzden burada yazılan değer bir sonraki analizde geçerlidir (11.1.3)."""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import (
    CatalogEntry,
    TypeExistsError,
    TypeNotFoundError,
    create_type,
    export_catalog,
    import_catalog,
    list_types,
    load_record,
    load_seed_catalog,
    record_problems,
    set_type_active,
    update_type,
    validate_catalog,
)
from app.db.models import KnownDocumentType
from tests.catalog.conftest import RecordFactory


def _entry(make_record: RecordFactory, **overrides: Any) -> CatalogEntry:
    (entry,) = validate_catalog([make_record(**overrides)])
    return entry


def _commit(session_factory: sessionmaker[Session], action: Any) -> Any:
    with session_factory() as session:
        result = action(session)
        session.commit()
        return result


def _row(session: Session, slug: str) -> KnownDocumentType:
    return session.scalars(select(KnownDocumentType).where(KnownDocumentType.slug == slug)).one()


def test_create_writes_a_type_the_catalog_can_read(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    entry = _entry(make_record, acceptance_criteria=["Kenarlar görünür"])

    _commit(session_factory, lambda session: create_type(session, entry))

    with session_factory() as session:
        catalog = export_catalog(session)
        assert catalog.slugs() == ("sample_card",)
        assert catalog.get("sample_card") == entry


def test_create_refuses_an_existing_slug_and_keeps_the_stored_type(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    _commit(session_factory, lambda session: create_type(session, _entry(make_record)))

    with session_factory() as session, pytest.raises(TypeExistsError):
        create_type(session, _entry(make_record, name="Başka Ad"))

    with session_factory() as session:
        assert _row(session, "sample_card").name == "Sample Card"


def test_a_concurrent_create_loses_cleanly_and_leaves_the_session_usable(
    session_factory: sessionmaker[Session],
    make_record: RecordFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _commit(session_factory, lambda session: create_type(session, _entry(make_record)))

    with session_factory() as session:
        # Öndenetim başka istek yazmadan önce yapılmış gibi: kayıt yokmuş görünür, PK reddeder.
        monkeypatch.setattr(session, "get", lambda *_args, **_kwargs: None)
        with pytest.raises(TypeExistsError):
            create_type(session, _entry(make_record, name="Yarışan"))
        monkeypatch.undo()

        create_type(session, _entry(make_record, slug="other_card"))
        session.commit()

    with session_factory() as session:
        assert export_catalog(session).slugs() == ("other_card", "sample_card")
        assert _row(session, "sample_card").name == "Sample Card"


def test_update_writes_the_form_fields(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    _commit(session_factory, lambda session: create_type(session, _entry(make_record)))
    edited = _entry(
        make_record,
        name="Yeni Ad",
        expected_pages={"min": 1, "max": 3},
        required_fields=["surname"],
        acceptance_criteria=["Bir", "İki"],
        prompt_description="Açıklama",
    )

    changed = _commit(session_factory, lambda session: update_type(session, edited))

    assert changed is True
    with session_factory() as session:
        assert export_catalog(session).get("sample_card") == edited
        row = _row(session, "sample_card")
        assert (row.expected_pages_min, row.expected_pages_max) == (1, 3)
        assert row.acceptance_criteria == ["Bir", "İki"]


def test_update_without_a_change_reports_none(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    entry = _entry(make_record)
    _commit(session_factory, lambda session: create_type(session, entry))

    assert _commit(session_factory, lambda session: update_type(session, entry)) is False


def test_update_leaves_activity_and_photo_rules_alone(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    rules = {"face_visible": True}
    _commit(
        session_factory,
        lambda session: create_type(session, _entry(make_record, photo_rules=rules)),
    )
    _commit(
        session_factory, lambda session: set_type_active(session, "sample_card", False, actor="ik")
    )

    # Form `active`/`photo_rules` taşımaz: kayıt varsayılanlarıyla gelse de bunlar yazılmaz.
    _commit(session_factory, lambda session: update_type(session, _entry(make_record, name="Ad")))

    with session_factory() as session:
        row = _row(session, "sample_card")
        assert (row.name, row.active, row.photo_rules) == ("Ad", False, rules)


def test_update_and_activation_of_an_unknown_type_are_refused(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    with session_factory() as session:
        with pytest.raises(TypeNotFoundError):
            update_type(session, _entry(make_record))
        with pytest.raises(TypeNotFoundError):
            set_type_active(session, "sample_card", False, actor="ik")
        with pytest.raises(TypeNotFoundError):
            load_record(session, "sample_card")


def test_deactivation_keeps_the_type_and_can_be_undone(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    _commit(session_factory, lambda session: create_type(session, _entry(make_record)))

    assert _commit(
        session_factory, lambda session: set_type_active(session, "sample_card", False, actor="ik")
    )
    with session_factory() as session:
        assert export_catalog(session).get("sample_card").active is False  # type: ignore[union-attr]
        assert [item.active for item in list_types(session)] == [False]

    # Aynı durumu yeniden istemek bir şey değiştirmez.
    assert not _commit(
        session_factory, lambda session: set_type_active(session, "sample_card", False, actor="ik")
    )
    assert _commit(
        session_factory, lambda session: set_type_active(session, "sample_card", True, actor="ik")
    )
    with session_factory() as session:
        assert export_catalog(session).get("sample_card").active is True  # type: ignore[union-attr]


def test_the_management_module_has_no_way_to_delete_a_type() -> None:
    import app.catalog.manage as manage

    assert [
        name for name in dir(manage) if "delete" in name.lower() or "remove" in name.lower()
    ] == []


def test_list_shows_every_type_including_passive_ones_in_slug_order(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    def seed(session: Session) -> None:
        create_type(session, _entry(make_record, slug="b_type", acceptance_criteria=["x", "y"]))
        create_type(session, _entry(make_record, slug="a_type", active=False))

    _commit(session_factory, seed)

    with session_factory() as session:
        first, second = list_types(session)

    assert (first.slug, first.active, first.criteria_count, first.problems) == (
        "a_type",
        False,
        0,
        (),
    )
    assert (second.slug, second.active, second.criteria_count) == ("b_type", True, 2)


def test_list_flags_an_inconsistent_row_instead_of_failing(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    _commit(session_factory, lambda session: create_type(session, _entry(make_record)))
    _commit(
        session_factory,
        lambda session: setattr(_row(session, "sample_card"), "direct", True),  # dönüşümler dolu
    )

    with session_factory() as session:
        (item,) = list_types(session)
        record = load_record(session, "sample_card")

    (problem,) = item.problems
    assert "allowed_conversions boş olmalı" in problem
    assert record_problems(record) == item.problems


def test_seed_catalog_lists_with_no_problems(session_factory: sessionmaker[Session]) -> None:
    seed = load_seed_catalog()
    _commit(session_factory, lambda session: import_catalog(session, seed))

    with session_factory() as session:
        items = list_types(session)

    assert len(items) == len(seed)
    assert all(item.problems == () for item in items)
