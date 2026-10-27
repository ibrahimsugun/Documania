"""Genel önizleme kaynağı (PRD 11.9.9; PLAN.md §D132 a, g) — `app.storage.previews.PreviewSource`.

Örnek dışındaki her belge kaynağı (çalışan belgesi, yükleme sayfası, üretilen belge, şablon
sayfası, fotoğraf) aynı üretimi kullanır: istenen sayfa tek başına çizilir, en çok
`PREVIEW_MAX_PAGES` sayfa önizlenir, bozuk dosyada yer tutucu döner, orijinal değişmez. Veriler
sentetiktir (`tests/fixtures/gen.py`).
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.storage import DataLayout, prepare_data_dir, sha256_file
from app.storage.previews import (
    PREVIEW_MAX_PAGES,
    PreviewSource,
    document_page_count,
    ensure_source_preview,
)
from tests.fixtures.gen import make_half_filled_image_bytes, make_sized_pdf_bytes

A4 = (595.0, 842.0)
KIND = "employee-documents"


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


def _file(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def _size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        assert image.format == "JPEG"
        return image.size


def test_each_pdf_page_is_its_own_preview_and_the_original_is_untouched(
    layout: DataLayout, tmp_path: Path
) -> None:
    # Uzantısız saklanan yükleme gibi: PDF ilk baytlarından tanınır.
    source = _file(tmp_path, "belge", make_sized_pdf_bytes([A4, (A4[1], A4[0])]))
    digest = sha256_file(source)

    first = ensure_source_preview(layout, PreviewSource(KIND, "7", source, 0), "large")
    second = ensure_source_preview(layout, PreviewSource(KIND, "7", source, 1), "large")

    assert first is not None and first.path is not None
    assert second is not None and second.path is not None
    assert first.key != second.key
    width, height = _size(first.path)
    assert height == 1280 and width < height  # dikey ilk sayfa
    width, height = _size(second.path)
    assert width == 1280 and height < width  # yatay ikinci sayfa
    assert first.path.parent == layout.preview_cache / KIND
    assert sha256_file(source) == digest  # orijinal bayt bayt aynı (K10, K11)
    assert not layout.page_cache.exists() or not any(layout.page_cache.iterdir())


def test_a_missing_page_or_a_broken_file_gets_a_placeholder_not_an_error(
    layout: DataLayout, tmp_path: Path
) -> None:
    pdf = _file(tmp_path, "tek.pdf", make_sized_pdf_bytes([A4]))
    broken = _file(tmp_path, "bozuk.pdf", b"%PDF-1.7 bozuk")
    image = _file(tmp_path, "foto.png", make_half_filled_image_bytes("PNG", (200, 300)))

    beyond = ensure_source_preview(layout, PreviewSource(KIND, "1", pdf, 3), "small")
    unreadable = ensure_source_preview(layout, PreviewSource(KIND, "2", broken, 0), "small")
    second_of_image = ensure_source_preview(layout, PreviewSource(KIND, "3", image, 1), "small")

    for preview in (beyond, unreadable, second_of_image):
        assert preview is not None and preview.path is None


def test_out_of_range_pages_unknown_sizes_and_missing_files_are_not_found(
    layout: DataLayout, tmp_path: Path
) -> None:
    pdf = _file(tmp_path, "uzun.pdf", make_sized_pdf_bytes([A4]))

    assert ensure_source_preview(layout, PreviewSource(KIND, "1", pdf, -1), "small") is None
    beyond = PreviewSource(KIND, "1", pdf, PREVIEW_MAX_PAGES)
    assert ensure_source_preview(layout, beyond, "small") is None
    assert ensure_source_preview(layout, PreviewSource(KIND, "1", pdf), "huge") is None
    gone = PreviewSource(KIND, "1", tmp_path / "yok.pdf")
    assert ensure_source_preview(layout, gone, "small") is None


def test_the_key_follows_the_file_so_a_changed_file_gets_a_new_address(
    layout: DataLayout, tmp_path: Path
) -> None:
    path = _file(tmp_path, "foto.jpg", make_half_filled_image_bytes("JPEG", (200, 300)))
    before = PreviewSource(KIND, "1", path).key()

    path.write_bytes(make_half_filled_image_bytes("JPEG", (300, 200)))

    assert PreviewSource(KIND, "1", path).key() != before
    assert PreviewSource(KIND, "2", path).key() != PreviewSource(KIND, "1", path).key()


def test_page_count_is_the_real_count_and_one_for_images_or_unreadable_files(
    tmp_path: Path,
) -> None:
    long = _file(tmp_path, "uzun.pdf", make_sized_pdf_bytes([A4] * 25))
    image = _file(tmp_path, "foto.png", make_half_filled_image_bytes("PNG", (20, 20)))
    broken = _file(tmp_path, "bozuk.pdf", b"%PDF-bozuk")

    assert document_page_count(long) == 25
    assert document_page_count(image) == 1
    assert document_page_count(broken) == 1


def test_a_source_kind_must_not_collide_with_a_type_slug(layout: DataLayout) -> None:
    # Tür slug'ı tire taşımaz (`^[a-z][a-z0-9_]*$`); kaynak türü taşır.
    with pytest.raises(ValueError, match="tire"):
        layout.source_preview_path("passport", "a1", "small")


def test_preview_carries_no_metadata(layout: DataLayout, tmp_path: Path) -> None:
    image = Image.new("RGB", (400, 300), (10, 20, 30))
    exif = Image.Exif()
    exif[0x010F] = "SentetikKamera"
    buffer = BytesIO()
    image.save(buffer, "JPEG", exif=exif.tobytes())
    path = _file(tmp_path, "foto.jpg", buffer.getvalue())

    preview = ensure_source_preview(layout, PreviewSource(KIND, "1", path), "small")

    assert preview is not None and preview.path is not None
    with Image.open(preview.path) as rendered:
        assert not rendered.getexif()
        assert "icc_profile" not in rendered.info
