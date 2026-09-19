"""11.6.1 — profil fotoğrafı kural seti katalogda tutulur ve açılıp kapatılabilir.

Çekirdek: kural tanımları, kayıttan okuma (toleranslı), formdan yazma (katı) ve `set_photo_rules`.
Panel uçları `tests/web/test_photo_rules_page.py`'de."""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import (
    PHOTO_RULE_SPECS,
    PHOTO_RULE_TYPES,
    PhotoRulesError,
    PhotoRulesForm,
    PhotoRulesUnsupportedError,
    TypeNotFoundError,
    build_photo_rules,
    create_type,
    enabled_photo_rules,
    export_catalog,
    import_catalog,
    load_record,
    load_seed_catalog,
    read_photo_rules,
    set_photo_rules,
    update_type,
    validate_catalog,
)
from app.catalog.photo_rules import (
    DEFAULT_MIN_HEIGHT_PX,
    DEFAULT_MIN_WIDTH_PX,
    MAX_RESOLUTION_PX,
    RESOLUTION_RULE,
)
from app.db.models import KnownDocumentType
from tests.catalog.conftest import RecordFactory

ALL_IDS = tuple(spec.id for spec in PHOTO_RULE_SPECS)
DEFAULT_ON = tuple(spec.id for spec in PHOTO_RULE_SPECS if spec.default_enabled)


def _states(raw: dict[str, Any] | None) -> dict[str, bool]:
    return {setting.id: setting.enabled for setting in read_photo_rules(raw)}


# --- kural tanımları ------------------------------------------------------------------------------


def test_the_rule_set_names_every_photo_criterion_the_plan_asks_for() -> None:
    assert ALL_IDS == (
        "face_visible",
        "single_person",
        "neutral_expression",
        "plain_background",
        "min_resolution",
        "no_sunglasses",
        "no_head_covering",
    )
    assert len(set(ALL_IDS)) == len(ALL_IDS)
    for spec in PHOTO_RULE_SPECS:
        assert spec.label.strip() and spec.description.strip(), spec.id


def test_the_head_covering_rule_is_a_company_decision_and_off_until_turned_on() -> None:
    company = [spec.id for spec in PHOTO_RULE_SPECS if spec.company_decision]

    assert company == ["no_head_covering"]
    assert _states(None)["no_head_covering"] is False
    # Öteki kurallar açılıştan itibaren açıktır.
    assert DEFAULT_ON == tuple(i for i in ALL_IDS if i != "no_head_covering")


def test_rules_belong_to_the_profile_picture_type_only() -> None:
    assert PHOTO_RULE_TYPES == {"profile_picture"}
    assert "profile_picture" in load_seed_catalog().slugs()


# --- okuma ----------------------------------------------------------------------------------------


def test_an_unset_rule_set_reads_as_every_rule_at_its_default() -> None:
    for raw in (None, {}):
        settings = read_photo_rules(raw)

        assert tuple(setting.id for setting in settings) == ALL_IDS
        assert tuple(setting.id for setting in settings if setting.enabled) == DEFAULT_ON
        resolution = next(s for s in settings if s.id == RESOLUTION_RULE)
        assert (resolution.min_width_px, resolution.min_height_px) == (
            DEFAULT_MIN_WIDTH_PX,
            DEFAULT_MIN_HEIGHT_PX,
        )
        assert all(
            s.min_width_px is None and s.min_height_px is None
            for s in settings
            if s.id != RESOLUTION_RULE
        )


def test_a_stored_rule_set_is_read_back_exactly() -> None:
    raw = {
        "face_visible": {"enabled": False},
        "no_head_covering": {"enabled": True},
        "min_resolution": {"enabled": True, "min_width_px": 600, "min_height_px": 800},
    }

    settings = {setting.id: setting for setting in read_photo_rules(raw)}

    assert settings["face_visible"].enabled is False
    assert settings["no_head_covering"].enabled is True
    assert settings["single_person"].enabled is True  # girişi yok → varsayılan
    assert (settings["min_resolution"].min_width_px, settings["min_resolution"].min_height_px) == (
        600,
        800,
    )


@pytest.mark.parametrize(
    "raw",
    [
        {"face_visible": True},  # giriş sözlük değil
        {"face_visible": {"enabled": "hayır"}},  # açık/kapalı mantıksal değil
        {"face_visible": {"enabled": None}},
        {"face_visible": None},
        {"kural": "fotokuralxyz", "nested": {"a": [1, 2]}},  # tanımsız anahtarlar
    ],
)
def test_a_malformed_entry_falls_back_to_the_rule_default_and_never_raises(
    raw: dict[str, Any],
) -> None:
    assert _states(raw) == _states(None)


@pytest.mark.parametrize("bad", [0, -5, MAX_RESOLUTION_PX + 1, True, "600", 12.5, None])
def test_a_malformed_minimum_size_falls_back_to_the_default(bad: Any) -> None:
    raw = {"min_resolution": {"enabled": False, "min_width_px": bad, "min_height_px": bad}}

    resolution = next(s for s in read_photo_rules(raw) if s.id == RESOLUTION_RULE)

    assert resolution.enabled is False  # açık/kapalı bilgisi bozuk boyuttan etkilenmez
    assert (resolution.min_width_px, resolution.min_height_px) == (
        DEFAULT_MIN_WIDTH_PX,
        DEFAULT_MIN_HEIGHT_PX,
    )


@pytest.mark.parametrize("raw", ["kural", 5, ["face_visible"], True])
def test_a_rule_set_that_is_not_a_mapping_reads_as_the_defaults(raw: Any) -> None:
    assert _states(raw) == _states(None)


def test_only_the_enabled_rules_are_asked_of_a_photo() -> None:
    raw = {
        "face_visible": {"enabled": False},
        "single_person": {"enabled": False},
        "no_head_covering": {"enabled": True},
    }

    assert tuple(s.id for s in enabled_photo_rules(raw)) == (
        "neutral_expression",
        "plain_background",
        "min_resolution",
        "no_sunglasses",
        "no_head_covering",
    )
    assert enabled_photo_rules({i: {"enabled": False} for i in ALL_IDS}) == ()


# --- yazma ----------------------------------------------------------------------------------------


def test_the_form_builds_a_record_that_writes_every_rule_explicitly() -> None:
    record = build_photo_rules(
        PhotoRulesForm(
            enabled=("face_visible", "min_resolution", "no_head_covering"),
            min_width_px=" 640 ",
            min_height_px="480",
        )
    )

    assert tuple(record) == ALL_IDS
    assert {name: entry["enabled"] for name, entry in record.items()} == {
        i: i in {"face_visible", "min_resolution", "no_head_covering"} for i in ALL_IDS
    }
    assert record["min_resolution"] == {"enabled": True, "min_width_px": 640, "min_height_px": 480}
    assert all("min_width_px" not in v for k, v in record.items() if k != RESOLUTION_RULE)


def test_a_built_record_reads_back_as_the_form_that_made_it() -> None:
    form = PhotoRulesForm(enabled=("single_person", "no_sunglasses"), min_width_px="900")

    record = build_photo_rules(form)

    again = PhotoRulesForm.from_settings(read_photo_rules(record))
    assert again == PhotoRulesForm(
        enabled=("single_person", "no_sunglasses"),
        min_width_px="900",
        min_height_px=str(DEFAULT_MIN_HEIGHT_PX),
    )
    assert build_photo_rules(again) == record


def test_the_default_form_is_the_default_rule_set() -> None:
    assert PhotoRulesForm.from_settings(read_photo_rules(None)) == PhotoRulesForm(
        enabled=DEFAULT_ON
    )


def test_a_form_that_turns_everything_off_is_a_valid_rule_set() -> None:
    record = build_photo_rules(PhotoRulesForm(enabled=()))

    assert all(entry["enabled"] is False for entry in record.values())
    assert enabled_photo_rules(record) == ()


@pytest.mark.parametrize(
    "bad", ["", "  ", "abc", "-1", "0", "12.5", "٣٠٠", str(MAX_RESOLUTION_PX + 1)]
)
def test_a_bad_pixel_count_is_refused_per_field_even_when_the_rule_is_off(bad: str) -> None:
    with pytest.raises(PhotoRulesError) as excinfo:
        build_photo_rules(PhotoRulesForm(enabled=(), min_width_px=bad, min_height_px=bad))

    assert set(excinfo.value.problems) == {"min_width_px", "min_height_px"}
    assert str(MAX_RESOLUTION_PX) in excinfo.value.problems["min_width_px"][0]


def test_a_boundary_pixel_count_is_accepted() -> None:
    record = build_photo_rules(
        PhotoRulesForm(min_width_px="1", min_height_px=str(MAX_RESOLUTION_PX))
    )

    assert record["min_resolution"]["min_width_px"] == 1
    assert record["min_resolution"]["min_height_px"] == MAX_RESOLUTION_PX


def test_an_unknown_rule_id_is_refused_by_name() -> None:
    with pytest.raises(PhotoRulesError) as excinfo:
        build_photo_rules(PhotoRulesForm(enabled=("face_visible", "yuz_tanima", "baska")))

    assert excinfo.value.problems == {"enabled": ["Tanımsız kural: baska, yuz_tanima"]}
    assert "yuz_tanima" in str(excinfo.value)


# --- katalogda saklama ----------------------------------------------------------------------------


def _commit(session_factory: sessionmaker[Session], action: Any) -> Any:
    with session_factory() as session:
        result = action(session)
        session.commit()
        return result


def _profile_picture(make_record: RecordFactory, **overrides: Any) -> Any:
    (entry,) = validate_catalog(
        [
            make_record(
                slug="profile_picture",
                name="Profile Picture",
                file_label="Profile-Picture",
                required_fields=[],
                expected_file_types=["jpeg", "png"],
                expected_pages={"min": 1, "max": 1},
                output_format="jpeg",
                **overrides,
            )
        ]
    )
    return entry


def test_set_photo_rules_stores_the_set_and_the_catalog_still_reads(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    _commit(session_factory, lambda s: create_type(s, _profile_picture(make_record)))
    rules = build_photo_rules(PhotoRulesForm(enabled=("face_visible", "min_resolution")))

    changed = _commit(session_factory, lambda s: set_photo_rules(s, "profile_picture", rules))

    assert changed is True
    with session_factory() as session:
        stored = session.scalars(select(KnownDocumentType)).one().photo_rules
        assert stored == rules
        assert load_record(session, "profile_picture")["photo_rules"] == rules
        # Katalog (analiz ve dışa aktarım) kural setiyle birlikte okunur.
        assert export_catalog(session).get("profile_picture").photo_rules == rules  # type: ignore[union-attr]


def test_a_rule_can_be_turned_off_and_on_again(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    _commit(session_factory, lambda s: create_type(s, _profile_picture(make_record)))

    def stored_ids() -> tuple[str, ...]:
        with session_factory() as session:
            raw = load_record(session, "profile_picture")["photo_rules"]
        return tuple(s.id for s in enabled_photo_rules(raw))

    every = tuple(i for i in ALL_IDS)
    _commit(
        session_factory,
        lambda s: set_photo_rules(
            s, "profile_picture", build_photo_rules(PhotoRulesForm(enabled=every))
        ),
    )
    assert stored_ids() == every

    _commit(
        session_factory,
        lambda s: set_photo_rules(
            s,
            "profile_picture",
            build_photo_rules(
                PhotoRulesForm(enabled=tuple(i for i in every if i != "no_sunglasses"))
            ),
        ),
    )
    assert "no_sunglasses" not in stored_ids()

    _commit(
        session_factory,
        lambda s: set_photo_rules(
            s, "profile_picture", build_photo_rules(PhotoRulesForm(enabled=every))
        ),
    )
    assert "no_sunglasses" in stored_ids()


def test_writing_the_same_rules_again_changes_nothing(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    _commit(session_factory, lambda s: create_type(s, _profile_picture(make_record)))
    rules = build_photo_rules(PhotoRulesForm(enabled=("face_visible",)))
    assert _commit(session_factory, lambda s: set_photo_rules(s, "profile_picture", rules)) is True

    assert _commit(session_factory, lambda s: set_photo_rules(s, "profile_picture", rules)) is False


def test_rules_survive_a_type_edit_and_a_type_edit_survives_rules(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    _commit(session_factory, lambda s: create_type(s, _profile_picture(make_record)))
    rules = build_photo_rules(PhotoRulesForm(enabled=("single_person",)))
    _commit(session_factory, lambda s: set_photo_rules(s, "profile_picture", rules))

    _commit(
        session_factory,
        lambda s: update_type(s, _profile_picture(make_record, description="Vesikalık")),
    )

    with session_factory() as session:
        row = session.scalars(select(KnownDocumentType)).one()
        assert (row.description, row.photo_rules) == ("Vesikalık", rules)


def test_only_the_photo_type_takes_rules_and_a_missing_type_is_refused(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    (card,) = validate_catalog([make_record()])
    _commit(session_factory, lambda s: create_type(s, card))
    rules = build_photo_rules(PhotoRulesForm())

    with session_factory() as session:
        with pytest.raises(PhotoRulesUnsupportedError):
            set_photo_rules(session, "sample_card", rules)
        with pytest.raises(TypeNotFoundError):
            set_photo_rules(session, "profile_picture", rules)
        assert session.scalars(select(KnownDocumentType)).one().photo_rules is None


def test_the_seeded_photo_type_starts_without_a_stored_set_and_reads_the_defaults(
    session_factory: sessionmaker[Session],
) -> None:
    _commit(session_factory, lambda s: import_catalog(s, load_seed_catalog()))

    with session_factory() as session:
        raw = load_record(session, "profile_picture")["photo_rules"]

    assert raw is None
    assert tuple(s.id for s in enabled_photo_rules(raw)) == DEFAULT_ON
