"""00.6.3 — katalog YAML dosyası: kanonik yazım, okuma hataları, atomik dışa aktarım ve tohum
dosyasının veri dizinine kurulması."""

from pathlib import Path

import pytest

from app.catalog import (
    CatalogError,
    dump_catalog_yaml,
    install_seed_catalog,
    parse_catalog_yaml,
    read_catalog_file,
    validate_catalog,
    write_catalog_file,
)
from app.catalog.yaml_io import CATALOG_HEADER, seed_catalog_bytes
from app.storage import DataLayout
from tests.catalog.conftest import RecordFactory


def test_dump_then_parse_returns_equal_catalog(make_record: RecordFactory) -> None:
    catalog = validate_catalog(
        [
            make_record(
                slug="full_type",
                country="NO",  # YAML 1.1'de tırnaksız NO → false; yazarken tırnaklanmalı
                description="Açıklama: iki nokta, 'tırnak' ve \"çift tırnak\" içerir",
                acceptance_criteria=["- tire ile başlar", "# diyez ile başlar", "yes"],
                prompt_description="Uzun " * 60,
                photo_rules={"face_visible": True, "min_width_px": 300, "nested": {"a": [1, 2]}},
                active=False,
            ),
            make_record(
                slug="bare_type",
                country=None,
                expected_pages=None,
                direct=True,
                analyze=False,
                required_fields=[],
                allowed_conversions=[],
                output_format="keep",
            ),
        ]
    )

    text = dump_catalog_yaml(catalog)

    assert parse_catalog_yaml(text) == catalog
    assert parse_catalog_yaml(text.encode("utf-8")) == catalog
    assert dump_catalog_yaml(parse_catalog_yaml(text)) == text


def test_dump_uses_section_8_6_layout(make_record: RecordFactory) -> None:
    catalog = validate_catalog(
        [
            make_record(
                acceptance_criteria=["Kenarlar kesilmemiş"], expected_pages={"min": 1, "max": 1}
            )
        ]
    )

    text = dump_catalog_yaml(catalog)

    assert text.startswith(CATALOG_HEADER)
    lines = text.removeprefix(CATALOG_HEADER).splitlines()
    assert lines[0] == "- slug: sample_card"
    assert "  expected_file_types: [pdf, jpeg]" in lines
    assert "  expected_pages: {min: 1, max: 1}" in lines
    assert "  allowed_conversions: [merge, wrap_image]" in lines
    assert "  front_back_layouts: []" in lines
    assert lines[lines.index("  acceptance_criteria:") + 1] == "    - Kenarlar kesilmemiş"
    keys = [line.split(":")[0].strip("- ") for line in lines if not line.startswith("    ")]
    assert keys == [
        "slug",
        "name",
        "file_label",
        "country",
        "description",
        "expected_file_types",
        "expected_pages",
        "sides",
        "front_back_layouts",
        "direct",
        "analyze",
        "required_fields",
        "allowed_conversions",
        "output_format",
        "acceptance_criteria",
        "prompt_description",
        "photo_rules",
        "active",
    ]


def test_empty_catalog_round_trips() -> None:
    catalog = validate_catalog([])

    assert parse_catalog_yaml(dump_catalog_yaml(catalog)) == catalog


def test_duplicate_key_is_rejected() -> None:
    text = "- slug: sample\n  direct: false\n  direct: true\n"

    with pytest.raises(CatalogError, match="tekrarlanan anahtar: 'direct'"):
        parse_catalog_yaml(text)


@pytest.mark.parametrize("text", ["- slug: [açık", "", "# yalnız yorum\n"])
def test_unreadable_or_empty_yaml_is_rejected(text: str) -> None:
    with pytest.raises(CatalogError):
        parse_catalog_yaml(text)


def test_yaml_tags_cannot_build_python_objects() -> None:
    with pytest.raises(CatalogError, match="YAML okunamadı"):
        parse_catalog_yaml("- !!python/object/apply:os.system ['echo']\n")


def test_write_catalog_file_replaces_previous_export(
    tmp_path: Path, make_record: RecordFactory
) -> None:
    path = tmp_path / "KnownDocuments" / "catalog.yaml"
    first = validate_catalog([make_record(slug="first_type")])
    second = validate_catalog([make_record(slug="second_type")])

    write_catalog_file(path, first)
    stored = write_catalog_file(path, second)

    assert read_catalog_file(path) == second
    assert stored.path == path
    assert path.read_bytes().decode("utf-8") == dump_catalog_yaml(second)
    assert [p.name for p in path.parent.iterdir()] == ["catalog.yaml"]  # geçici dosya kalmaz


def test_install_seed_writes_catalog_into_data_dir(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)

    assert install_seed_catalog(layout) is True
    assert layout.catalog_path == tmp_path / "KnownDocuments" / "catalog.yaml"
    assert layout.catalog_path.read_bytes() == seed_catalog_bytes()


def test_install_seed_keeps_existing_catalog(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    layout.catalog_path.parent.mkdir(parents=True)
    layout.catalog_path.write_bytes(b"# IK tarafindan duzenlendi\n[]\n")

    assert install_seed_catalog(layout) is False
    assert layout.catalog_path.read_bytes() == b"# IK tarafindan duzenlendi\n[]\n"


def test_install_seed_loses_race_without_overwriting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = DataLayout(tmp_path)

    def other_process_wins(path: Path, content: bytes) -> None:
        raise FileExistsError(path)

    monkeypatch.setattr("app.catalog.yaml_io.write_file", other_process_wins)

    assert install_seed_catalog(layout) is False
