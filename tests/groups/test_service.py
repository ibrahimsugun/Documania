"""14.1.1, 14.1.2 — belge grubu servisi: ad tekilliği, kalem ekleme/kaldırma, arşiv, olaylar ve
kalemin türle ülkeden bağımsız eşleşmesi (PLAN.md §C89)."""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import list_types
from app.db.models import DocumentGroupItem, Event, KnownDocumentType
from app.events import EventType
from app.groups import (
    DESCRIPTION_MAX_LENGTH,
    NAME_MAX_LENGTH,
    NOTE_MAX_LENGTH,
    DuplicateGroupItemError,
    GroupFormError,
    GroupItemNotFoundError,
    GroupNameTakenError,
    GroupNotFoundError,
    active_items,
    add_item,
    count_archived_groups,
    create_group,
    get_group,
    item_matches,
    label_choices,
    list_groups,
    normalize_group_name,
    normalize_label,
    open_package_count,
    open_package_counts,
    remove_item,
    set_group_archived,
    type_choices,
    update_group,
)

ACTOR = "ik-ayse"


def _events(session: Session) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(Event).where(Event.type == EventType.GROUP_CHANGED).order_by(Event.id)
    )
    return [{"actor": row.actor, **(row.data_json or {})} for row in rows]


def _type(session: Session, slug: str) -> KnownDocumentType:
    found = session.get(KnownDocumentType, slug)
    assert found is not None
    return found


def _group(session: Session, name: str = "Sırbistan iş başvurusu") -> int:
    group = create_group(session, name=name, description="Çalışma izni dosyası", actor=ACTOR)
    session.commit()
    return group.id


# --- sadeleştirme ve eşleşme ---------------------------------------------------------------------


def test_group_name_is_normalized_with_the_slug_rules() -> None:
    assert normalize_group_name("Sırbistan iş başvurusu") == "sirbistan_is_basvurusu"
    assert normalize_group_name("  SIRBISTAN  İş   Başvurusu! ") == "sirbistan_is_basvurusu"
    assert normalize_group_name("Сербия виза") == "serbiia_viza"
    with pytest.raises(ValueError):
        normalize_group_name("— ! —")


def test_label_normalization_ignores_case_and_spacing() -> None:
    assert normalize_label("  Identity   CARD ") == "identity card"
    assert normalize_label(None) == ""


def test_label_item_matches_every_type_with_that_label_whatever_the_country(
    session: Session,
) -> None:
    item = DocumentGroupItem(match_kind="label", file_label="Passport")

    assert item_matches(item, _type(session, "russian_passport"))
    assert item_matches(item, _type(session, "turkish_passport"))
    # Yazım farkı (baştaki/sondaki boşluk, küçük harf) aynı etikettir; pasif tür de etiket taşır.
    assert item_matches(item, _type(session, "serbian_passport"))
    assert not item_matches(item, _type(session, "residence_card"))


def test_label_item_matches_despite_case_and_spacing_on_the_item_side(session: Session) -> None:
    item = DocumentGroupItem(match_kind="label", file_label="  PASSPORT  ")

    assert item_matches(item, _type(session, "turkish_passport"))


def test_type_item_matches_only_its_own_slug(session: Session) -> None:
    item = DocumentGroupItem(match_kind="type", type_slug="russian_passport")

    assert item_matches(item, _type(session, "russian_passport"))
    assert not item_matches(item, _type(session, "turkish_passport"))
    assert not item_matches(item, _type(session, "residence_card"))


def test_near_labels_do_not_match_each_other(session: Session) -> None:
    item = DocumentGroupItem(match_kind="label", file_label="Identity Card")

    assert item_matches(item, _type(session, "turkish_id_card"))
    assert not item_matches(item, _type(session, "kosovo_id_document"))


def test_matching_works_with_catalog_summaries_too(session: Session) -> None:
    item = DocumentGroupItem(match_kind="label", file_label="Passport")
    matched = {summary.slug for summary in list_types(session) if item_matches(item, summary)}

    assert matched == {"russian_passport", "turkish_passport", "serbian_passport"}


def test_unknown_match_kind_never_matches(session: Session) -> None:
    item = DocumentGroupItem(match_kind="country", file_label="Passport")

    assert not item_matches(item, _type(session, "russian_passport"))


# --- seçiciler -----------------------------------------------------------------------------------


def test_label_choices_list_catalog_labels_with_type_counts(session: Session) -> None:
    choices = {choice.label: choice.type_count for choice in label_choices(session)}

    # "Passport" iki etkin + bir pasif türde (yazım farkıyla) — tek seçenek, 3 tür.
    assert choices == {
        "Identity Card": 1,
        "Identity Document": 1,
        "Passport": 3,
        "Profile Picture": 1,
        "Residence Card": 1,
    }
    assert [choice.key for choice in label_choices(session)] == sorted(
        choice.key for choice in label_choices(session)
    )


def test_label_choice_shows_the_most_common_spelling(session: Session) -> None:
    for index in range(2):
        session.add(
            KnownDocumentType(
                slug=f"extra_passport_{index}",
                name=f"Extra Passport {index}",
                file_label="PASSPORT",
                sides="single",
                direct=False,
                analyze=True,
                output_format="keep",
            )
        )
    session.commit()

    passport = next(choice for choice in label_choices(session) if choice.key == "passport")
    # "Passport" 2, "PASSPORT" 2, "passport" 1: eşitlikte alfabetik ilk yazım.
    assert (passport.label, passport.type_count) == ("PASSPORT", 5)


def test_type_choices_list_every_type_by_name(session: Session) -> None:
    choices = type_choices(session)

    assert [choice.name for choice in choices] == sorted(choice.name for choice in choices)
    assert len(choices) == 7
    serbian = next(choice for choice in choices if choice.slug == "serbian_passport")
    assert (serbian.country, serbian.active) == ("RS", False)
    picture = next(choice for choice in choices if choice.slug == "profile_picture")
    assert picture.country is None


# --- grup ----------------------------------------------------------------------------------------


def test_create_group_stores_the_group_and_writes_an_event(session: Session) -> None:
    group_id = _group(session)
    group = get_group(session, group_id)

    assert (group.name, group.normalized_name) == (
        "Sırbistan iş başvurusu",
        "sirbistan_is_basvurusu",
    )
    assert (group.description, group.created_by, group.archived_at) == (
        "Çalışma izni dosyası",
        ACTOR,
        None,
    )
    assert _events(session) == [
        {"actor": ACTOR, "group_id": group_id, "action": "create", "item_count": 0}
    ]


def test_create_group_simplifies_whitespace_and_empty_description(session: Session) -> None:
    group = create_group(session, name="  Almanya   vize ", description="   ", actor=ACTOR)

    assert (group.name, group.description) == ("Almanya vize", None)


def test_group_name_must_be_unique_after_normalization(session: Session) -> None:
    _group(session)

    with pytest.raises(GroupNameTakenError) as caught:
        create_group(session, name="SIRBISTAN IS BASVURUSU", description=None, actor=ACTOR)
    assert caught.value.archived is False
    assert len(_events(session)) == 1


def test_name_conflict_with_an_archived_group_is_reported_as_archived(session: Session) -> None:
    group_id = _group(session)
    set_group_archived(session, group_id, True, actor=ACTOR)
    session.commit()

    with pytest.raises(GroupNameTakenError) as caught:
        create_group(session, name="Sırbistan iş başvurusu", description=None, actor=ACTOR)
    assert caught.value.archived is True


@pytest.mark.parametrize(
    ("name", "description", "field"),
    [
        ("", None, "name"),
        ("   ", None, "name"),
        ("x" * (NAME_MAX_LENGTH + 1), None, "name"),
        ("!!! ---", None, "name"),
        ("Geçerli ad", "a" * (DESCRIPTION_MAX_LENGTH + 1), "description"),
    ],
    ids=["empty", "blank", "too-long", "no-letters", "long-description"],
)
def test_invalid_group_fields_are_rejected_without_writing(
    session: Session, name: str, description: str | None, field: str
) -> None:
    with pytest.raises(GroupFormError) as caught:
        create_group(session, name=name, description=description, actor=ACTOR)

    assert list(caught.value.problems) == [field]
    assert list_groups(session, include_archived=True) == []
    assert _events(session) == []


def test_update_group_changes_name_and_description_with_field_names(session: Session) -> None:
    group_id = _group(session)

    changed = update_group(
        session, group_id, name="Sırbistan başvurusu", description=None, actor=ACTOR
    )
    session.commit()

    group = get_group(session, group_id)
    assert changed is True
    assert (group.name, group.normalized_name, group.description) == (
        "Sırbistan başvurusu",
        "sirbistan_basvurusu",
        None,
    )
    assert _events(session)[-1] == {
        "actor": ACTOR,
        "group_id": group_id,
        "action": "update",
        "item_count": 0,
        "fields": ["name", "description"],
    }


def test_update_group_without_changes_writes_nothing(session: Session) -> None:
    group_id = _group(session)

    changed = update_group(
        session,
        group_id,
        name=" Sırbistan  iş başvurusu ",
        description="Çalışma izni dosyası",
        actor=ACTOR,
    )

    assert changed is False
    assert len(_events(session)) == 1


def test_update_group_may_change_only_the_spelling_of_its_own_name(session: Session) -> None:
    group_id = _group(session)

    assert update_group(
        session,
        group_id,
        name="SIRBISTAN İŞ BAŞVURUSU",
        description="Çalışma izni dosyası",
        actor=ACTOR,
    )
    assert _events(session)[-1]["fields"] == ["name"]


def test_update_group_refuses_another_groups_name(session: Session) -> None:
    _group(session)
    other_id = _group(session, "Almanya vize")

    with pytest.raises(GroupNameTakenError):
        update_group(
            session, other_id, name="sırbistan iş başvurusu", description=None, actor=ACTOR
        )
    session.rollback()
    assert get_group(session, other_id).name == "Almanya vize"


def test_update_group_validates_fields(session: Session) -> None:
    group_id = _group(session)

    with pytest.raises(GroupFormError):
        update_group(session, group_id, name="", description=None, actor=ACTOR)


def test_missing_group_is_reported(session: Session) -> None:
    with pytest.raises(GroupNotFoundError):
        get_group(session, 404)
    with pytest.raises(GroupNotFoundError):
        update_group(session, 404, name="x", description=None, actor=ACTOR)
    with pytest.raises(GroupNotFoundError):
        add_item(session, 404, match_kind="label", file_label="Passport", actor=ACTOR)
    with pytest.raises(GroupNotFoundError):
        set_group_archived(session, 404, True, actor=ACTOR)


# --- kalemler ------------------------------------------------------------------------------------


def test_add_label_item_stores_the_catalog_spelling(session: Session) -> None:
    group_id = _group(session)

    item = add_item(
        session,
        group_id,
        match_kind="label",
        file_label="  passport ",
        required=True,
        note="Geçerlilik 6 aydan uzun",
        actor=ACTOR,
    )
    session.commit()

    assert (item.match_kind, item.file_label, item.type_slug) == ("label", "Passport", None)
    assert (item.position, item.required, item.note) == (1, True, "Geçerlilik 6 aydan uzun")
    assert _events(session)[-1] == {
        "actor": ACTOR,
        "group_id": group_id,
        "action": "item_added",
        "item_count": 1,
        "item_id": item.id,
        "match_kind": "label",
        "required": True,
    }


def test_add_type_item_and_positions_grow(session: Session) -> None:
    group_id = _group(session)
    add_item(session, group_id, match_kind="label", file_label="Passport", actor=ACTOR)

    item = add_item(
        session,
        group_id,
        match_kind="type",
        type_slug="residence_card",
        required=False,
        actor=ACTOR,
    )
    session.commit()

    assert (item.type_slug, item.file_label, item.position, item.required) == (
        "residence_card",
        None,
        2,
        False,
    )
    assert item.document_type is not None and item.document_type.slug == "residence_card"
    assert [entry.id for entry in active_items(get_group(session, group_id))][-1] == item.id


def test_passive_type_can_be_an_item(session: Session) -> None:
    group_id = _group(session)

    item = add_item(session, group_id, match_kind="type", type_slug="serbian_passport", actor=ACTOR)

    assert item.type_slug == "serbian_passport"


@pytest.mark.parametrize(
    ("values", "field"),
    [
        ({"match_kind": "label", "file_label": ""}, "file_label"),
        ({"match_kind": "label", "file_label": "Driving Licence"}, "file_label"),
        ({"match_kind": "type", "type_slug": " "}, "type_slug"),
        ({"match_kind": "type", "type_slug": "yok_boyle_tur"}, "type_slug"),
        ({"match_kind": "country", "file_label": "Passport"}, "match_kind"),
        (
            {"match_kind": "label", "file_label": "Passport", "note": "n" * (NOTE_MAX_LENGTH + 1)},
            "note",
        ),
    ],
    ids=["no-label", "unknown-label", "no-type", "unknown-type", "bad-kind", "long-note"],
)
def test_invalid_items_are_rejected_without_writing(
    session: Session, values: dict[str, str], field: str
) -> None:
    group_id = _group(session)

    with pytest.raises(GroupFormError) as caught:
        add_item(session, group_id, actor=ACTOR, **values)

    assert field in caught.value.problems
    assert active_items(get_group(session, group_id)) == []
    assert len(_events(session)) == 1


def test_same_label_or_type_is_a_single_item(session: Session) -> None:
    group_id = _group(session)
    add_item(session, group_id, match_kind="label", file_label="Passport", actor=ACTOR)
    add_item(session, group_id, match_kind="type", type_slug="russian_passport", actor=ACTOR)

    with pytest.raises(DuplicateGroupItemError):
        add_item(session, group_id, match_kind="label", file_label="PASSPORT", actor=ACTOR)
    with pytest.raises(DuplicateGroupItemError):
        add_item(session, group_id, match_kind="type", type_slug="russian_passport", actor=ACTOR)
    # Etiket kalemiyle aynı türü gösteren tür kalemi ayrı kalemdir (farklı eşleşme anahtarı).
    assert len(active_items(get_group(session, group_id))) == 2


def test_remove_item_keeps_the_row_and_writes_an_event(session: Session) -> None:
    group_id = _group(session)
    item = add_item(session, group_id, match_kind="label", file_label="Passport", actor=ACTOR)
    session.commit()

    removed = remove_item(session, group_id, item.id, actor="ik-mehmet")
    session.commit()

    assert removed.removed_by == "ik-mehmet"
    assert removed.removed_at is not None
    assert session.get(DocumentGroupItem, item.id) is not None
    assert active_items(get_group(session, group_id)) == []
    assert _events(session)[-1] == {
        "actor": "ik-mehmet",
        "group_id": group_id,
        "action": "item_removed",
        "item_count": 0,
        "item_id": item.id,
        "match_kind": "label",
    }


def test_removed_item_can_be_added_again_as_a_new_item(session: Session) -> None:
    group_id = _group(session)
    first = add_item(session, group_id, match_kind="label", file_label="Passport", actor=ACTOR)
    remove_item(session, group_id, first.id, actor=ACTOR)

    again = add_item(session, group_id, match_kind="label", file_label="Passport", actor=ACTOR)

    assert again.id != first.id
    assert again.position == 2
    assert [item.id for item in active_items(get_group(session, group_id))] == [again.id]


def test_remove_item_refuses_foreign_missing_or_removed_items(session: Session) -> None:
    group_id = _group(session)
    other_id = _group(session, "Almanya vize")
    item = add_item(session, group_id, match_kind="label", file_label="Passport", actor=ACTOR)

    with pytest.raises(GroupItemNotFoundError):
        remove_item(session, other_id, item.id, actor=ACTOR)
    with pytest.raises(GroupItemNotFoundError):
        remove_item(session, group_id, 999, actor=ACTOR)
    remove_item(session, group_id, item.id, actor=ACTOR)
    with pytest.raises(GroupItemNotFoundError):
        remove_item(session, group_id, item.id, actor=ACTOR)
    with pytest.raises(GroupNotFoundError):
        remove_item(session, 404, item.id, actor=ACTOR)


# --- arşiv ve liste ------------------------------------------------------------------------------


def test_archive_and_restore_are_single_step_and_logged(session: Session) -> None:
    group_id = _group(session)
    add_item(session, group_id, match_kind="label", file_label="Passport", actor=ACTOR)

    assert set_group_archived(session, group_id, True, actor="ik-mehmet") is True
    group = get_group(session, group_id)
    assert (group.archived_by, group.archived_at is not None) == ("ik-mehmet", True)
    assert set_group_archived(session, group_id, True, actor=ACTOR) is False

    assert set_group_archived(session, group_id, False, actor=ACTOR) is True
    assert (group.archived_at, group.archived_by) == (None, None)
    assert set_group_archived(session, group_id, False, actor=ACTOR) is False

    actions = [(event["action"], event["actor"], event["item_count"]) for event in _events(session)]
    assert actions == [
        ("create", ACTOR, 0),
        ("item_added", ACTOR, 1),
        ("archive", "ik-mehmet", 1),
        ("restore", ACTOR, 1),
    ]
    # Arşiv kalemlere dokunmaz.
    assert len(active_items(group)) == 1


def test_list_groups_hides_archived_unless_asked_and_counts_active_items(
    session: Session,
) -> None:
    serbia = _group(session)
    germany = _group(session, "Almanya vize")
    first = add_item(session, serbia, match_kind="label", file_label="Passport", actor=ACTOR)
    add_item(session, serbia, match_kind="type", type_slug="residence_card", actor=ACTOR)
    remove_item(session, serbia, first.id, actor=ACTOR)
    set_group_archived(session, germany, True, actor=ACTOR)
    session.commit()

    visible = list_groups(session)
    assert [(group.name, group.item_count, group.archived) for group in visible] == [
        ("Sırbistan iş başvurusu", 1, False)
    ]
    everything = list_groups(session, include_archived=True)
    assert [(group.name, group.archived) for group in everything] == [
        ("Almanya vize", True),
        ("Sırbistan iş başvurusu", False),
    ]
    assert all(group.open_packages == 0 for group in everything)
    assert count_archived_groups(session) == 1


def test_open_package_counts_are_zero_until_packages_exist(session: Session) -> None:
    group_id = _group(session)

    assert open_package_counts(session, [group_id]) == {group_id: 0}
    assert open_package_count(session, group_id) == 0


def test_concurrent_name_race_is_reported_as_a_conflict(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """İki istek adı aynı anda denetlerse tekil dizin karar verir: kaybeden `GroupNameTakenError`
    alır, kazananın kaydı ve olayı kalır."""
    _group(session)
    other_id = _group(session, "Almanya vize")
    monkeypatch.setattr("app.groups.service._ensure_name_free", lambda *args, **kwargs: None)

    with pytest.raises(GroupNameTakenError):
        create_group(session, name="SIRBISTAN IS BASVURUSU", description=None, actor=ACTOR)
    with pytest.raises(GroupNameTakenError):
        update_group(
            session, other_id, name="Sırbistan iş başvurusu", description=None, actor=ACTOR
        )
    session.commit()

    assert get_group(session, other_id).name == "Almanya vize"
    assert [group.name for group in list_groups(session)] == [
        "Almanya vize",
        "Sırbistan iş başvurusu",
    ]
    assert [event["action"] for event in _events(session)] == ["create", "create"]
