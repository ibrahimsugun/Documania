"""00.4.1 — uygulama açılışında §8.2 veri dizini ağacı eksiksiz oluşur."""

import os
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings, load_settings
from app.db.models import QueueKind
from app.main import create_app
from app.storage.layout import DataLayout, prepare_data_dir

# PRD §8.2'deki sabit dizinler, veri köküne göre.
SECTION_8_2_DIRS = [
    "Inbox",
    "Employees",
    "Unknown",
    "Unreadable",
    "Unresolved",
    "Archive",
    "KnownDocuments",
    "KnownDocuments/examples",
    "cache",
    "cache/pages",
]


def _assert_tree(root: Path) -> None:
    missing = [name for name in SECTION_8_2_DIRS if not (root / name).is_dir()]
    assert missing == []


def test_app_startup_creates_full_data_tree(tmp_path: Path) -> None:
    data_dir = tmp_path / "veri" / "data"
    settings = load_settings(_env_file=None, database_url="sqlite://", data_dir=data_dir)

    with TestClient(create_app(settings)) as client:
        _assert_tree(data_dir)
        assert client.get("/health").status_code == 200


def test_app_startup_reads_data_dir_from_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "ortam"))
    get_settings.cache_clear()
    try:
        with TestClient(create_app()):
            _assert_tree(tmp_path / "ortam")
    finally:
        get_settings.cache_clear()


def test_startup_is_idempotent_and_keeps_existing_files(tmp_path: Path) -> None:
    layout = prepare_data_dir(tmp_path)
    existing = layout.inbox / "u1" / "original.pdf"
    existing.parent.mkdir()
    existing.write_bytes(b"%PDF-sentetik")

    prepare_data_dir(tmp_path)

    _assert_tree(tmp_path)
    assert existing.read_bytes() == b"%PDF-sentetik"


def test_static_dirs_cover_section_8_2(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    assert sorted(p.relative_to(tmp_path).as_posix() for p in layout.static_dirs()) == sorted(
        name for name in SECTION_8_2_DIRS if name != "cache"
    )


def test_identity_paths(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    folder = "Ahmet_Cakar_E0001"

    assert layout.upload_inbox_dir("01J8Z3-abc") == tmp_path / "Inbox" / "01J8Z3-abc"
    assert layout.received_dir(folder) == tmp_path / "Employees" / folder / "Alinan"
    assert layout.ready_dir(folder) == tmp_path / "Employees" / folder / "Hazir"
    assert layout.profile_path(folder) == tmp_path / "Employees" / folder / "profil.md"
    assert layout.catalog_path == tmp_path / "KnownDocuments" / "catalog.yaml"
    assert layout.example_inventory_path == tmp_path / "KnownDocuments" / "_ornek_envanteri.csv"
    assert layout.type_examples_dir("russian_passport") == (
        tmp_path / "KnownDocuments" / "examples" / "russian_passport"
    )
    assert layout.page_cache_dir(42) == tmp_path / "cache" / "pages" / "42"
    # Eğitim modu (11.9, §8.2): `_egitim/` örnek klasörlerinin dışındadır.
    training = tmp_path / "KnownDocuments" / "_egitim"
    assert layout.training == training
    assert layout.training_incoming_dir(7) == training / "gelen" / "7"
    assert layout.training_staged_path(7, 31, "pdf") == training / "gelen" / "7" / "31.pdf"
    assert layout.training_maps == training / "haritalar"
    assert layout.training_removed_dir("albanian_passport") == (
        training / "cikarilan" / "albanian_passport"
    )
    assert layout.archive_dir(date(2026, 9, 14)) == tmp_path / "Archive" / "2026-09"
    assert layout.archive_dir(datetime(2027, 1, 2, 3, 4)) == tmp_path / "Archive" / "2027-01"


@pytest.mark.parametrize(
    ("kind", "folder"),
    [
        (QueueKind.UNKNOWN, "Unknown"),
        (QueueKind.UNREADABLE, "Unreadable"),
        (QueueKind.UNRESOLVED, "Unresolved"),
    ],
)
def test_queue_paths(tmp_path: Path, kind: QueueKind, folder: str) -> None:
    layout = DataLayout(tmp_path)

    assert layout.queue_dir(kind, "u1") == tmp_path / folder / "u1"
    assert layout.queue_reason_path(kind.value, "u1") == tmp_path / folder / "u1" / "reason.json"


def test_unknown_queue_kind_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="kuyruk türü"):
        DataLayout(tmp_path).queue_dir("hazir", "u1")


def test_ensure_employee_tree(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)

    employee_dir = layout.ensure_employee_tree("Ahmet_Cakar_E0001")

    assert employee_dir == tmp_path / "Employees" / "Ahmet_Cakar_E0001"
    assert (employee_dir / "Alinan").is_dir()
    assert (employee_dir / "Hazir").is_dir()


@pytest.mark.parametrize("segment", ["", ".", "..", "../Inbox", "a/b", "a\\b", "C:", "a b", "_x"])
def test_path_segments_cannot_escape_data_root(tmp_path: Path, segment: str) -> None:
    layout = DataLayout(tmp_path)

    for build in (
        layout.upload_inbox_dir,
        layout.employee_dir,
        layout.type_examples_dir,
        layout.page_cache_dir,
        layout.training_incoming_dir,
        layout.training_removed_dir,
    ):
        with pytest.raises(ValueError, match="yol parçası"):
            build(segment)
    for staged in ((segment, 1, "pdf"), (1, segment, "pdf"), (1, 1, segment)):
        with pytest.raises(ValueError, match="yol parçası"):
            layout.training_staged_path(*staged)
    with pytest.raises(ValueError, match="yol parçası"):
        layout.queue_dir("unknown", segment)
    with pytest.raises(ValueError, match="yol parçası"):
        layout.page_image_path(segment, 0)


def test_page_image_path(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)

    assert layout.page_image_path(42, 0) == tmp_path / "cache" / "pages" / "42" / "0000.jpg"
    assert layout.page_image_path("42", 29) == tmp_path / "cache" / "pages" / "42" / "0029.jpg"
    with pytest.raises(ValueError, match="sayfa sırası"):
        layout.page_image_path(42, -1)


def test_page_image_path_accepts_extension_override(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)

    assert layout.page_image_path(42, 0, extension="png") == (
        tmp_path / "cache" / "pages" / "42" / "0000.png"
    )


def test_resolve_relative_stored_path(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)

    assert layout.resolve("Inbox/u_20260914_0001/pasaport ön yüz.pdf") == (
        tmp_path / "Inbox" / "u_20260914_0001" / "pasaport ön yüz.pdf"
    )
    assert layout.resolve("cache/pages/7/0000.jpg") == layout.page_image_path(7, 0)


@pytest.mark.parametrize(
    "relative",
    [
        "",
        "/etc/passwd",
        "../Inbox/a.pdf",
        "Inbox/../../a.pdf",
        "Inbox/./a.pdf",
        "Inbox//a.pdf",
        "Inbox/",
        "Inbox\\a.pdf",
        pytest.param(
            "C:/Windows/a.pdf",
            marks=pytest.mark.skipif(os.name != "nt", reason="sürücü parçası yalnız Windows'ta"),
        ),
        pytest.param(
            "Inbox/Z:a.pdf",
            marks=pytest.mark.skipif(os.name != "nt", reason="sürücü parçası yalnız Windows'ta"),
        ),
    ],
)
def test_resolve_rejects_paths_outside_data_root(tmp_path: Path, relative: str) -> None:
    with pytest.raises(ValueError, match="göreli yol"):
        DataLayout(tmp_path).resolve(relative)


def test_relative_is_the_inverse_of_resolve(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    output = layout.ready_dir("Ahmet_Cakar_E0001") / "Ahmet_Cakar-Passport-2.pdf"

    relative = layout.relative(output)

    assert relative == "Employees/Ahmet_Cakar_E0001/Hazir/Ahmet_Cakar-Passport-2.pdf"
    assert layout.resolve(relative) == output


@pytest.mark.parametrize("outside", ["..", "../Inbox/a.pdf", "."])
def test_relative_rejects_paths_outside_or_at_data_root(tmp_path: Path, outside: str) -> None:
    layout = DataLayout(tmp_path / "data")

    with pytest.raises(ValueError):
        layout.relative(layout.root / outside)
