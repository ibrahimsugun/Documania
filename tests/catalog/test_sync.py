"""00.6.3 — YAML tohumdan veritabanına yükleme ve veritabanından YAML'a dışa aktarma iki
yönlü çalışır."""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import (
    CatalogError,
    dump_catalog_yaml,
    export_catalog,
    import_catalog,
    load_seed_catalog,
    read_catalog_file,
    validate_catalog,
    write_catalog_file,
)
from app.catalog.yaml_io import seed_catalog_bytes
from app.db.models import KnownDocumentType
from tests.catalog.conftest import RecordFactory


def _rows(session: Session) -> dict[str, KnownDocumentType]:
    return {row.slug: row for row in session.scalars(select(KnownDocumentType))}


def test_import_writes_every_field_to_database(session_factory: sessionmaker[Session]) -> None:
    seed = load_seed_catalog()

    with session_factory() as session:
        result = import_catalog(session, seed)
        session.commit()

    assert result.created == seed.slugs()
    assert result.updated == result.unchanged == result.not_in_catalog == ()
    with session_factory() as session:
        passport = _rows(session)["russian_passport"]
        assert passport.name == "Russian Passport"
        assert passport.file_label == "Passport"
        assert passport.country == "RU"
        assert passport.expected_file_types == ["pdf", "jpeg"]
        assert (passport.expected_pages_min, passport.expected_pages_max) == (1, 1)
        assert passport.sides == "single"
        assert passport.direct is True
        assert passport.analyze is True
        assert passport.required_fields == [
            "surname",
            "given_names",
            "date_of_birth",
            "document_number",
            "expiry_date",
        ]
        assert passport.allowed_conversions == []
        assert passport.output_format == "keep"
        assert passport.acceptance_criteria == [
            "Kimlik sayfası tam görünür olmalı, kenarlar kesilmemiş",
            "MRZ iki satırı da okunabilir olmalı",
        ]
        assert passport.prompt_description == (
            "Kiril ve Latin çift yazımlı kimlik sayfası, sağ altta iki satır MRZ."
        )
        assert passport.photo_rules is None
        assert passport.active is True
        attachment = _rows(session)["attachment"]
        assert (attachment.expected_pages_min, attachment.expected_pages_max) == (None, None)


def test_yaml_to_database_to_yaml_is_byte_identical(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    seed_file = tmp_path / "seed.yaml"
    seed_file.write_bytes(seed_catalog_bytes())
    export_file = tmp_path / "export" / "catalog.yaml"

    with session_factory() as session:
        import_catalog(session, read_catalog_file(seed_file))
        session.commit()
    with session_factory() as session:
        exported = export_catalog(session)
    write_catalog_file(export_file, exported)

    assert exported == load_seed_catalog()
    assert export_file.read_bytes() == seed_file.read_bytes()


def test_database_edit_reaches_yaml_and_back(
    session_factory: sessionmaker[Session], tmp_path: Path, database_url: str
) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()
    # Katalog panelden düzenlenmiş gibi (11.1): tür pasif, kabul kriteri ve foto kuralı eklendi.
    with session_factory() as session:
        card = _rows(session)["serbian_residence_card"]
        card.active = False
        card.acceptance_criteria = ["Dört köşe görünür olmalı"]
        card.photo_rules = {"face_visible": True}
        session.commit()

    export_file = tmp_path / "catalog.yaml"
    with session_factory() as session:
        write_catalog_file(export_file, export_catalog(session))

    exported = read_catalog_file(export_file).get("serbian_residence_card")
    assert exported is not None
    assert exported.active is False
    assert exported.acceptance_criteria == ("Dört köşe görünür olmalı",)
    assert exported.photo_rules == {"face_visible": True}


def test_yaml_edit_updates_database_without_deleting(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()

    seed = load_seed_catalog()
    edited = [
        entry.model_dump(mode="json")
        for entry in seed
        if entry.slug not in {"work_permit", "turkish_passport"}
    ]
    for record in edited:
        if record["slug"] == "russian_passport":
            record["acceptance_criteria"] = ["MRZ iki satırı da okunabilir olmalı"]
            record["expected_pages"] = {"min": 1, "max": 2}
    edited.append(make_record(slug="peru_diploma", name="Peru Diploma", file_label="Diploma"))

    with session_factory() as session:
        result = import_catalog(session, validate_catalog(edited))
        session.commit()

    assert result.created == ("peru_diploma",)
    assert result.updated == ("russian_passport",)
    assert len(result.unchanged) == len(seed) - 3
    assert result.not_in_catalog == ("turkish_passport", "work_permit")
    with session_factory() as session:
        rows = _rows(session)
        assert set(rows) == set(seed.slugs()) | {"peru_diploma"}  # K16: silme yok
        assert rows["russian_passport"].acceptance_criteria == [
            "MRZ iki satırı da okunabilir olmalı"
        ]
        assert rows["russian_passport"].expected_pages_max == 2
        assert rows["work_permit"].active is True


def test_reimport_of_same_catalog_changes_nothing(session_factory: sessionmaker[Session]) -> None:
    seed = load_seed_catalog()
    with session_factory() as session:
        import_catalog(session, seed)
        session.commit()

    with session_factory() as session:
        result = import_catalog(session, seed)
        assert not session.dirty
        assert not session.new
        assert result.unchanged == seed.slugs()
        assert result.created == result.updated == ()


def test_export_orders_types_by_slug(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    catalog = validate_catalog([make_record(slug="zeta_type"), make_record(slug="alpha_type")])
    with session_factory() as session:
        import_catalog(session, catalog)
        session.commit()

    with session_factory() as session:
        assert export_catalog(session).slugs() == ("alpha_type", "zeta_type")


def test_export_of_empty_database_round_trips(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        exported = export_catalog(session)

    assert len(exported) == 0
    assert dump_catalog_yaml(exported).endswith("[]\n")


def test_export_rejects_inconsistent_database_row(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    with session_factory() as session:
        import_catalog(session, validate_catalog([make_record(slug="broken_type")]))
        session.commit()
    with session_factory() as session:
        row = _rows(session)["broken_type"]
        row.direct = True  # dönüşüm listesi dolu kalırken Direkt Belge yapıldı
        session.commit()

    with session_factory() as session, pytest.raises(CatalogError) as caught:
        export_catalog(session)

    (problem,) = caught.value.problems
    assert problem.startswith("kayıt #1 (broken_type)")
    assert "allowed_conversions boş olmalı" in problem


def test_export_rejects_half_page_range(
    session_factory: sessionmaker[Session], make_record: RecordFactory
) -> None:
    with session_factory() as session:
        import_catalog(session, validate_catalog([make_record(expected_pages=None)]))
        session.commit()
    with session_factory() as session:
        _rows(session)["sample_card"].expected_pages_min = 1
        session.commit()

    with session_factory() as session, pytest.raises(CatalogError, match="expected_pages.max"):
        export_catalog(session)
