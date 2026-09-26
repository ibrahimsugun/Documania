"""11.9.5 — Harita yollarının güvenli çözümü (`app.storage.map_paths`; PLAN.md §C87 "Yol
güvenliği") ve yerindeki örneğin tanınması (`app.storage.examples.listed_example_slug`).

Yalnız göreli yol kabul edilir; Windows ve Linux yazımı aynı kuralla ele alınır; çözülen yol kökte
kalmalıdır. Kökten kaçan bağ POSIX'te sembolik bağla, Windows'ta (sembolik bağ yetki ister) bağlantı
noktasıyla (junction) kurulur. Dosyalar sentetik baytlardır.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from app.storage import DataLayout, prepare_data_dir
from app.storage.examples import listed_example_slug
from app.storage.map_paths import (
    REFERENCE_MAX_LENGTH,
    UnsafePathError,
    UnsafePathReason,
    list_map_folder,
    normalize_reference,
    resolve_reference,
)


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


def _link_dir(link: Path, target: Path) -> None:
    """`link` → `target` dizin bağı: sembolik bağ, olmazsa (Windows, yetkisiz) bağlantı noktası."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            pytest.skip("sembolik bağ kurulamadı")
    import _winapi  # yalnız Windows

    try:
        _winapi.CreateJunction(str(target), str(link))
    except OSError:
        pytest.skip("bağlantı noktası kurulamadı")


# --- normalize_reference --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("KnownDocuments/examples/a/b.jpg", "KnownDocuments/examples/a/b.jpg"),
        ("KnownDocuments\\examples\\a\\b.jpg", "KnownDocuments/examples/a/b.jpg"),
        ("  ./KnownDocuments//examples/./a/b.jpg  ", "KnownDocuments/examples/a/b.jpg"),
        ("koleksiyon\\alt/ornek.PDF", "koleksiyon/alt/ornek.PDF"),
        ("klasor/", "klasor"),
    ],
)
def test_relative_windows_and_posix_paths_normalize_the_same_way(value: str, expected: str) -> None:
    assert normalize_reference(value) == expected


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("/etc/passwd", UnsafePathReason.ABSOLUTE),
        ("/data/KnownDocuments/a.jpg", UnsafePathReason.ABSOLUTE),
        ("\\KnownDocuments\\a.jpg", UnsafePathReason.ABSOLUTE),
        ("C:\\Users\\ik\\a.jpg", UnsafePathReason.DRIVE),
        ("C:/Users/ik/a.jpg", UnsafePathReason.DRIVE),
        ("c:a.jpg", UnsafePathReason.DRIVE),
        ("KnownDocuments/C:/a.jpg", UnsafePathReason.DRIVE),
        ("a.jpg:akis", UnsafePathReason.DRIVE),
        ("\\\\sunucu\\pay\\a.jpg", UnsafePathReason.UNC),
        ("//sunucu/pay/a.jpg", UnsafePathReason.UNC),
        ("\\\\?\\C:\\a.jpg", UnsafePathReason.UNC),
        ("../disari.jpg", UnsafePathReason.PARENT),
        ("KnownDocuments/../../disari.jpg", UnsafePathReason.PARENT),
        ("KnownDocuments\\..\\Employees\\a.pdf", UnsafePathReason.PARENT),
        ("", UnsafePathReason.INVALID),
        ("   ", UnsafePathReason.INVALID),
        ("./.", UnsafePathReason.INVALID),
        ("a\x00b.jpg", UnsafePathReason.INVALID),
        ("a/" * (REFERENCE_MAX_LENGTH // 2) + "b.jpg", UnsafePathReason.INVALID),
    ],
)
def test_unsafe_references_are_refused_with_their_reason(
    value: str, reason: UnsafePathReason
) -> None:
    with pytest.raises(UnsafePathError) as refused:
        normalize_reference(value)

    assert refused.value.reason is reason


# --- resolve_reference ----------------------------------------------------------------------


def test_a_relative_path_resolves_under_the_root(tmp_path: Path) -> None:
    root = tmp_path / "kok"
    (root / "alt").mkdir(parents=True)
    (root / "alt" / "a.jpg").write_bytes(b"x")

    resolved = resolve_reference(root, "alt\\a.jpg")

    assert resolved == (root / "alt" / "a.jpg").resolve()
    assert resolved.read_bytes() == b"x"
    # Var olmayan dosya da çözülür; "dosya yok" çağıranın kararıdır.
    assert resolve_reference(root, "alt/yok.jpg") == (root / "alt" / "yok.jpg").resolve()


def test_the_root_itself_is_not_a_file_reference(tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError) as refused:
        resolve_reference(tmp_path, "./")

    assert refused.value.reason is UnsafePathReason.INVALID


def test_a_link_escaping_the_root_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "kok"
    root.mkdir()
    outside = tmp_path / "disari"
    outside.mkdir()
    (outside / "gizli.jpg").write_bytes(b"x")
    _link_dir(root / "kacak", outside)

    with pytest.raises(UnsafePathError) as refused:
        resolve_reference(root, "kacak/gizli.jpg")

    assert refused.value.reason is UnsafePathReason.ESCAPE


def test_a_link_staying_inside_the_root_is_accepted(tmp_path: Path) -> None:
    root = tmp_path / "kok"
    (root / "gercek").mkdir(parents=True)
    (root / "gercek" / "a.jpg").write_bytes(b"x")
    _link_dir(root / "kisayol", root / "gercek")

    resolved = resolve_reference(root, "kisayol/a.jpg")

    assert resolved == (root / "gercek" / "a.jpg").resolve()


# --- list_map_folder ------------------------------------------------------------------------


def test_a_folder_lists_only_its_own_pdf_jpeg_and_png_files(tmp_path: Path) -> None:
    folder = tmp_path / "klasor"
    (folder / "alt").mkdir(parents=True)
    for name in ("b.PNG", "a.jpg", "c.jpeg", "d.pdf", "e.docx", ".gizli.jpg", "notlar.txt"):
        (folder / name).write_bytes(b"x")
    (folder / "alt" / "derin.jpg").write_bytes(b"x")  # özyinelemesiz: alınmaz
    (folder / ".belgeee-tmp-0123456789abcdef0123456789abcdef.part").write_bytes(b"x")

    assert [path.name for path in list_map_folder(folder)] == ["a.jpg", "b.PNG", "c.jpeg", "d.pdf"]
    assert list_map_folder(tmp_path / "yok") == []
    assert list_map_folder(folder / "a.jpg") == []


def test_a_linked_folder_inside_a_folder_is_not_listed(tmp_path: Path) -> None:
    folder = tmp_path / "klasor"
    folder.mkdir()
    (folder / "a.jpg").write_bytes(b"x")
    outside = tmp_path / "disari.jpg"
    outside.mkdir()
    _link_dir(folder / "bag.jpg", outside)

    assert [path.name for path in list_map_folder(folder)] == ["a.jpg"]


# --- listed_example_slug --------------------------------------------------------------------


def test_a_listed_example_is_recognized_in_place(layout: DataLayout) -> None:
    folder = layout.type_examples_dir("turkish_passport")
    folder.mkdir(parents=True)
    (folder / "ornek.jpg").write_bytes(b"x")
    (folder / "notlar.txt").write_bytes(b"x")
    elsewhere = layout.known_documents / "_referans" / "turkish_passport"
    elsewhere.mkdir(parents=True)
    (elsewhere / "ornek.jpg").write_bytes(b"x")

    assert listed_example_slug(layout, folder / "ornek.jpg") == "turkish_passport"
    assert listed_example_slug(layout, folder / "notlar.txt") is None  # listelenmez
    assert listed_example_slug(layout, folder / "yok.jpg") is None
    assert listed_example_slug(layout, elsewhere / "ornek.jpg") is None
    assert listed_example_slug(layout, layout.examples / "kok.jpg") is None
