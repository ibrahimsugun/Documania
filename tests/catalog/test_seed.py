"""00.6.2 — başlangıç tohumunda en az 8 tür vardır ve açılışta veri dizinine, komutla
veritabanına yüklenir."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import (
    Conversion,
    FileType,
    OutputFormat,
    Sides,
    import_catalog,
    load_seed_catalog,
    parse_catalog_yaml,
    read_catalog_file,
)
from app.catalog.yaml_io import seed_catalog_bytes
from app.config import load_settings
from app.db.models import KnownDocumentType
from app.main import create_app
from app.storage import DataLayout
from tests.catalog.test_schema import SECTION_8_6_EXAMPLE

# PRD 00.6.2 kabul kriterindeki türler (ad → slug).
REQUIRED_TYPES = {
    "Russian Passport": "russian_passport",
    "Turkish Passport": "turkish_passport",
    "Serbian Passport": "serbian_passport",
    "Serbian Residence Card": "serbian_residence_card",
    "Serbian Driving License": "serbian_driving_license",
    "Work Permit": "work_permit",
    "Profile Picture": "profile_picture",
    "Attachment": "attachment",
}
PASSPORTS = ("russian_passport", "turkish_passport", "serbian_passport")
OFFICE_TYPES = {FileType.DOC, FileType.DOCX, FileType.XLS, FileType.XLSX}


def test_seed_has_at_least_eight_types_including_required_ones() -> None:
    catalog = load_seed_catalog()

    assert len(catalog) >= 8
    names = {entry.slug: entry.name for entry in catalog}
    assert {slug: names.get(slug) for slug in REQUIRED_TYPES.values()} == {
        slug: name for name, slug in REQUIRED_TYPES.items()
    }


def test_seed_russian_passport_matches_section_8_6_example() -> None:
    (example,) = parse_catalog_yaml(SECTION_8_6_EXAMPLE)
    seeded = load_seed_catalog().get("russian_passport")

    assert seeded is not None
    assert seeded.model_copy(update={"description": None}) == example


def test_seed_passports_are_direct_documents() -> None:
    catalog = load_seed_catalog()

    for slug in PASSPORTS:
        entry = catalog.get(slug)
        assert entry is not None
        assert entry.direct is True
        assert entry.allowed_conversions == ()
        assert entry.output_format is OutputFormat.KEEP
        assert entry.file_label == "Passport"
        assert "document_number" in entry.required_fields


def test_seed_cards_pair_front_and_back() -> None:
    catalog = load_seed_catalog()

    for slug in ("serbian_residence_card", "serbian_driving_license"):
        entry = catalog.get(slug)
        assert entry is not None
        assert entry.sides is Sides.FRONT_BACK
        assert entry.expected_pages is not None
        assert (entry.expected_pages.min, entry.expected_pages.max) == (2, 2)
        # S5: aynı partide ayrı ön/arka JPEG → kayıpsız sarma + birleştirme (direkt kapalı).
        assert entry.direct is False
        assert {Conversion.MERGE, Conversion.WRAP_IMAGE} <= set(entry.allowed_conversions)
        assert entry.output_format is OutputFormat.PDF


def test_seed_profile_picture_is_the_visual_type() -> None:
    entry = load_seed_catalog().get("profile_picture")

    assert entry is not None
    # K12: PDF → JPEG yalnız görsel türde; S3: sayfa 2 → Profile-Picture.jpeg.
    assert entry.output_format is OutputFormat.JPEG
    assert set(entry.allowed_conversions) == {Conversion.EXTRACT_IMAGE, Conversion.RENDER_IMAGE}
    assert entry.required_fields == ()


def test_seed_only_profile_picture_converts_pdf_to_image() -> None:
    image_conversions = {Conversion.EXTRACT_IMAGE, Conversion.RENDER_IMAGE}

    converting = [
        e.slug for e in load_seed_catalog() if image_conversions & set(e.allowed_conversions)
    ]

    assert converting == ["profile_picture"]


def test_seed_attachment_stores_office_files_unanalyzed() -> None:
    entry = load_seed_catalog().get("attachment")

    assert entry is not None
    # K2: Word/Excel analiz edilmez, dönüştürülmez; olduğu gibi saklanır.
    assert set(entry.expected_file_types) == OFFICE_TYPES
    assert entry.analyze is False
    assert entry.direct is True
    assert entry.allowed_conversions == ()
    assert entry.output_format is OutputFormat.KEEP
    assert all(
        not OFFICE_TYPES & set(e.expected_file_types) for e in load_seed_catalog() if e != entry
    )


def test_seed_analyzed_types_describe_themselves_to_the_analyzer() -> None:
    for entry in load_seed_catalog():
        assert entry.active is True
        if entry.analyze:
            assert entry.prompt_description


def test_seed_loads_into_database(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()

    with session_factory() as session:
        slugs = set(session.scalars(select(KnownDocumentType.slug)))
        assert session.scalar(select(func.count()).select_from(KnownDocumentType)) >= 8
    assert set(REQUIRED_TYPES.values()) <= slugs


def test_app_startup_installs_seed_catalog(
    tmp_path: Path, session_factory: sessionmaker[Session]
) -> None:
    settings = load_settings(_env_file=None, database_url="sqlite://", data_dir=tmp_path)

    with TestClient(create_app(settings)):
        catalog_path = DataLayout(tmp_path).catalog_path
        assert catalog_path.read_bytes() == seed_catalog_bytes()

    with session_factory() as session:
        result = import_catalog(session, read_catalog_file(catalog_path))
    assert set(result.created) == {entry.slug for entry in load_seed_catalog()}


def test_app_restart_keeps_edited_catalog(tmp_path: Path) -> None:
    settings = load_settings(_env_file=None, database_url="sqlite://", data_dir=tmp_path)
    catalog_path = DataLayout(tmp_path).catalog_path
    with TestClient(create_app(settings)):
        catalog_path.write_bytes(b"[]\n")

    with TestClient(create_app(settings)):
        assert catalog_path.read_bytes() == b"[]\n"
