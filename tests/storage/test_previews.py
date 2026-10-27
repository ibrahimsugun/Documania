"""11.9.7 — örnek önizlemeleri (`app.storage.previews`; PLAN.md §D130).

Önizleme küçük, yeniden kodlanmış JPEG'dir: uzun kenar boyut sınırında, EXIF taşımaz; PDF'te ilk
sayfa çizilir; bozuk ya da piksel sınırını aşan dosyada önizleme yoktur (yer tutucu). Orijinal bayt
bayt aynı kalır; yazım atomiktir ve anahtar örnek değişince değişir. Veri sentetiktir.
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.storage import DataLayout, prepare_data_dir, sha256_file
from app.storage import previews as previews_module
from app.storage.examples import store_example
from app.storage.filetype import FileKind
from app.storage.previews import ensure_preview, placeholder_jpeg, preview_key, warm_previews
from tests.fixtures.gen import make_half_filled_image_bytes, make_pdf_bytes

SLUG = "sample_card"


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


def _store(layout: DataLayout, name: str, content: bytes, kind: FileKind) -> Path:
    stored = store_example(layout, SLUG, name, content, kind)
    return layout.type_examples_dir(SLUG) / stored.name


def _exif_jpeg() -> bytes:
    image = Image.open(BytesIO(make_half_filled_image_bytes("JPEG", (2000, 1000))))
    exif = Image.Exif()
    exif[0x010F] = "Sentetik Kamera"  # Make
    exif[0x0112] = 6  # yönelim: 90° döndürülmüş
    buffer = BytesIO()
    image.save(buffer, "JPEG", exif=exif.tobytes())
    return buffer.getvalue()


def test_small_and_large_previews_are_jpegs_within_their_long_edge(layout: DataLayout) -> None:
    source = _store(
        layout, "kart.jpg", make_half_filled_image_bytes("JPEG", (3000, 1500)), FileKind.JPEG
    )

    small = ensure_preview(layout, SLUG, source.name, "small")
    large = ensure_preview(layout, SLUG, source.name, "large")

    assert small is not None and small.path is not None
    assert large is not None and large.path is not None
    with Image.open(small.path) as image:
        assert image.format == "JPEG" and max(image.size) == 320
    with Image.open(large.path) as image:
        assert max(image.size) == 1280
    assert small.path.parent == layout.preview_cache / SLUG
    assert small.path.name == f"{preview_key(source)}-small.jpg"


def test_preview_carries_no_exif_and_the_original_is_untouched(layout: DataLayout) -> None:
    content = _exif_jpeg()
    source = _store(layout, "exif.jpg", content, FileKind.JPEG)
    before = sha256_file(source)

    preview = ensure_preview(layout, SLUG, source.name, "small")

    assert preview is not None and preview.path is not None
    with Image.open(preview.path) as image:
        assert not image.getexif()
        assert "icc_profile" not in image.info
        # Yönelim fiziksel olarak uygulanır: yatay kaynak dikey önizleme olur.
        assert image.height > image.width
    assert sha256_file(source) == before
    assert source.read_bytes() == content


def test_pdf_preview_is_the_first_page(layout: DataLayout) -> None:
    source = _store(layout, "pasaport.pdf", make_pdf_bytes(3), FileKind.PDF)

    preview = ensure_preview(layout, SLUG, source.name, "large")

    assert preview is not None and preview.path is not None
    with Image.open(preview.path) as image:
        assert image.format == "JPEG" and max(image.size) == 1280


def test_corrupt_example_has_no_preview(layout: DataLayout) -> None:
    directory = layout.type_examples_dir(SLUG)
    directory.mkdir(parents=True)
    (directory / "bozuk.jpg").write_bytes(b"\xff\xd8\xff bozuk")
    (directory / "bozuk.pdf").write_bytes(b"%PDF-1.7 bozuk")

    for name in ("bozuk.jpg", "bozuk.pdf"):
        preview = ensure_preview(layout, SLUG, name, "small")
        assert preview is not None and preview.path is None
    assert not (layout.preview_cache / SLUG).exists() or not any(
        (layout.preview_cache / SLUG).iterdir()
    )


def test_image_over_the_pixel_limit_has_no_preview(
    layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _store(
        layout, "buyuk.png", make_half_filled_image_bytes("PNG", (400, 300)), FileKind.PNG
    )
    monkeypatch.setattr(previews_module, "PREVIEW_MAX_PIXELS", 100_000)

    preview = ensure_preview(layout, SLUG, source.name, "small")

    assert preview is not None and preview.path is None


def test_decompression_bomb_is_caught(layout: DataLayout, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _store(
        layout, "bomba.png", make_half_filled_image_bytes("PNG", (400, 300)), FileKind.PNG
    )
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10_000)

    preview = ensure_preview(layout, SLUG, source.name, "small")

    assert preview is not None and preview.path is None


@pytest.mark.parametrize(
    ("name", "size"),
    [("yok.jpg", "small"), ("../catalog.yaml", "small"), ("kart.jpg", "huge")],
)
def test_unlisted_name_or_unknown_size_is_none(layout: DataLayout, name: str, size: str) -> None:
    _store(layout, "kart.jpg", make_half_filled_image_bytes("JPEG", (300, 200)), FileKind.JPEG)

    assert ensure_preview(layout, SLUG, name, size) is None


def test_key_changes_when_the_example_changes(layout: DataLayout) -> None:
    source = _store(
        layout, "kart.jpg", make_half_filled_image_bytes("JPEG", (300, 200)), FileKind.JPEG
    )
    first = preview_key(source)

    source.write_bytes(make_half_filled_image_bytes("JPEG", (600, 200)))
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

    assert preview_key(source) != first


def test_existing_preview_is_reused_and_no_partial_file_is_left(layout: DataLayout) -> None:
    source = _store(
        layout, "kart.jpg", make_half_filled_image_bytes("JPEG", (900, 600)), FileKind.JPEG
    )
    first = ensure_preview(layout, SLUG, source.name, "small")
    assert first is not None and first.path is not None
    mtime = first.path.stat().st_mtime_ns

    again = ensure_preview(layout, SLUG, source.name, "small")

    assert again == first and first.path.stat().st_mtime_ns == mtime
    assert [p.name for p in first.path.parent.iterdir()] == [first.path.name]


def test_warm_previews_builds_every_preview_and_resumes(layout: DataLayout) -> None:
    _store(layout, "a.jpg", make_half_filled_image_bytes("JPEG", (500, 300)), FileKind.JPEG)
    _store(layout, "b.pdf", make_pdf_bytes(1), FileKind.PDF)
    bad = layout.type_examples_dir(SLUG) / "c.png"
    bad.write_bytes(b"\x89PNG bozuk")

    first = warm_previews(layout)
    second = warm_previews(layout)

    assert first == {"created": 4, "existing": 0, "failed": 2}
    assert second == {"created": 0, "existing": 4, "failed": 2}


def test_placeholder_is_a_jpeg() -> None:
    with Image.open(BytesIO(placeholder_jpeg())) as image:
        assert image.format == "JPEG"
