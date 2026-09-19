"""02.1.1 — PDF sayfa görüntüsü, 02.2.1 — PDF metin katmanı, 02.3.1 — görüntü analiz kopyası,
02.4.1 — boş sayfa, 02.5.1 — gömülü tek görüntü tespiti."""

from collections.abc import Callable
from io import BytesIO
from pathlib import Path

import pymupdf
import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Event, Page, Upload, UploadFile
from app.events import EventType
from app.pipeline.render import (
    RenderError,
    detect_pdf_blank_pages,
    detect_pdf_single_image_pages,
    extract_page_text,
    extract_pdf_text,
    extract_upload_file_text,
    image_copy,
    is_page_blank,
    mark_upload_file_blank_pages,
    mark_upload_file_single_image_pages,
    render_image_copy,
    render_image_file,
    render_pdf_images,
    render_pdf_pages,
    render_scale,
    render_upload_file,
    single_full_page_image_xref,
)
from app.storage import DataLayout, FileKind, detect_file_kind, sha256_file, write_to_inbox
from tests.fixtures.gen import (
    A4,
    make_half_filled_image_bytes,
    make_half_filled_pdf_bytes,
    make_pdf_bytes,
    make_sized_pdf_bytes,
    make_text_pdf_bytes,
)

ID_CARD = (243.0, 153.0)  # 85,6 × 54 mm


def _source(tmp_path: Path, content: bytes, name: str = "belge.pdf") -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def _pdf_with_embedded_image_bytes() -> bytes:
    """Tek sayfalı PDF: metinsiz/çizimsiz ama gömülü bir görüntü taşır (boş sayılmamalı)."""
    document = pymupdf.open()
    page = document.new_page(width=A4[0], height=A4[1])
    image_buffer = BytesIO()
    Image.new("RGB", (10, 10), "white").save(image_buffer, format="PNG")
    page.insert_image(pymupdf.Rect(0, 0, 100, 100), stream=image_buffer.getvalue())
    content = document.tobytes()
    document.close()
    return content


def _render(
    source: Path,
    layout: DataLayout,
    *,
    file_id: int = 1,
    dpi: int = 200,
    max_long_edge: int = 1568,
    jpeg_quality: int = 90,
):
    return render_pdf_pages(
        source,
        layout,
        file_id,
        dpi=dpi,
        max_long_edge=max_long_edge,
        jpeg_quality=jpeg_quality,
    )


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, database_url="sqlite://", **overrides)


def _stored_upload_file(
    session: Session,
    layout: DataLayout,
    content: bytes,
    name: str = "tarama.pdf",
    *,
    mime: str = "application/pdf",
) -> UploadFile:
    upload = Upload(id="u_20260914_0001", channel="web")
    stored = write_to_inbox(layout, upload.id, name, content)
    upload_file = UploadFile(
        upload=upload,
        original_name=name,
        stored_path=stored.path.relative_to(layout.root).as_posix(),
        sha256=stored.sha256,
        mime=mime,
    )
    session.add(upload_file)
    session.flush()
    return upload_file


# --- ölçek ------------------------------------------------------------------------------------


def test_render_scale_uses_configured_dpi_below_limit() -> None:
    assert render_scale(pymupdf.Rect(0, 0, *ID_CARD), 200, 1568) == pytest.approx(200 / 72)


def test_render_scale_shrinks_to_long_edge_limit() -> None:
    assert render_scale(pymupdf.Rect(0, 0, *A4), 200, 1568) == pytest.approx(1568 / 842)


def test_render_scale_corrects_outward_pixel_rounding() -> None:
    # Kesirli başlangıçlı kutu 1:1 ölçekte 101 px'e yuvarlanır; ölçek sınıra sığacak kadar kısılır.
    rect = pymupdf.Rect(0.5, 0, 100.5, 50)
    assert (rect * pymupdf.Matrix(1, 1)).irect.width == 101

    scale = render_scale(rect, 72, 100)

    assert scale < 1
    assert (rect * pymupdf.Matrix(scale, scale)).irect.width == 100


@pytest.mark.parametrize(("dpi", "max_long_edge"), [(0, 1568), (200, 0), (-1, 1568)])
def test_render_scale_rejects_non_positive_settings(dpi: int, max_long_edge: int) -> None:
    with pytest.raises(ValueError, match="pozitif"):
        render_scale(pymupdf.Rect(0, 0, *A4), dpi, max_long_edge)


def test_render_scale_rejects_empty_page() -> None:
    with pytest.raises(RenderError, match="boyutu"):
        render_scale(pymupdf.Rect(0, 0, 0, 0), 200, 1568)


# --- render -----------------------------------------------------------------------------------


@pytest.mark.parametrize("dpi", [72, 150, 200, 300])
def test_page_within_limit_is_rendered_at_configured_dpi(
    tmp_path: Path, layout: DataLayout, dpi: int
) -> None:
    [page] = _render(_source(tmp_path, make_sized_pdf_bytes([ID_CARD])), layout, dpi=dpi)

    assert page.dpi == pytest.approx(dpi)
    assert page.width == pytest.approx(ID_CARD[0] * dpi / 72, abs=1)
    assert page.height == pytest.approx(ID_CARD[1] * dpi / 72, abs=1)
    image = pymupdf.Pixmap(str(page.path))
    assert (image.width, image.height) == (page.width, page.height)


def test_page_exceeding_long_edge_is_downscaled_to_limit(
    tmp_path: Path, layout: DataLayout
) -> None:
    # 200 DPI'da A4 1654×2339 px olurdu; uzun kenar sınıra iner, en-boy oranı korunur.
    [page] = _render(_source(tmp_path, make_sized_pdf_bytes([A4])), layout, dpi=200)

    assert page.height == 1568
    assert page.width == pytest.approx(1568 * A4[0] / A4[1], abs=1)
    assert page.dpi == pytest.approx(1568 / A4[1] * 72)
    image = pymupdf.Pixmap(str(page.path))
    assert (image.width, image.height) == (page.width, page.height)


@pytest.mark.parametrize(
    ("size", "rotate"), [((A4[1], A4[0]), 0), (A4, 90), (A4, 270)], ids=["yatay", "r90", "r270"]
)
def test_landscape_page_limits_width(
    tmp_path: Path, layout: DataLayout, size: tuple[float, float], rotate: int
) -> None:
    [page] = _render(_source(tmp_path, make_sized_pdf_bytes([size], rotate=rotate)), layout)

    assert page.width == 1568
    assert page.height == pytest.approx(1568 * A4[0] / A4[1], abs=1)


def test_long_edge_never_exceeds_limit_for_odd_page_sizes(
    tmp_path: Path, layout: DataLayout
) -> None:
    sizes = [(w, h) for w in (100.1, 333.3, 612.0, 791.7, 1190.55) for h in (99.9, 595.3, 1683.8)]
    pages = _render(
        _source(tmp_path, make_sized_pdf_bytes(sizes)), layout, dpi=300, max_long_edge=1000
    )

    assert [page.index for page in pages] == list(range(len(sizes)))
    for (width, height), page in zip(sizes, pages, strict=True):
        natural_long_edge = max(width, height) * 300 / 72
        if natural_long_edge > 1000:
            assert max(page.width, page.height) in (999, 1000)
        else:
            assert page.dpi == pytest.approx(300)
        assert page.width == pytest.approx(width * page.dpi / 72, abs=1)
        assert page.height == pytest.approx(height * page.dpi / 72, abs=1)


def test_every_page_is_written_as_jpeg_to_page_cache(tmp_path: Path, layout: DataLayout) -> None:
    pages = _render(_source(tmp_path, make_pdf_bytes(3)), layout, file_id=42)

    assert [page.path for page in pages] == [
        layout.page_cache / "42" / f"000{index}.jpg" for index in range(3)
    ]
    for page in pages:
        assert detect_file_kind(page.path.read_bytes()) is FileKind.JPEG


def test_rendered_image_keeps_page_geometry(tmp_path: Path, layout: DataLayout) -> None:
    """Sol yarısı siyah sayfa: görüntü kırpılmamış, döndürülmemiş, aynalanmamış olmalı."""
    [page] = _render(_source(tmp_path, make_half_filled_pdf_bytes()), layout)

    image = pymupdf.Pixmap(str(page.path))
    assert max(image.pixel(image.width // 4, image.height // 2)) < 40
    assert min(image.pixel(image.width * 3 // 4, image.height // 2)) > 215


def test_jpeg_quality_setting_is_applied(tmp_path: Path, layout: DataLayout) -> None:
    source = _source(tmp_path, make_half_filled_pdf_bytes())

    [low] = _render(source, layout, file_id=1, jpeg_quality=10)
    [high] = _render(source, layout, file_id=2, jpeg_quality=100)

    assert low.path.stat().st_size < high.path.stat().st_size


def test_rendering_again_replaces_cached_images(tmp_path: Path, layout: DataLayout) -> None:
    source = _source(tmp_path, make_pdf_bytes(1))

    [first] = _render(source, layout, max_long_edge=1568)
    [second] = _render(source, layout, max_long_edge=800)

    assert second.path == first.path
    assert pymupdf.Pixmap(str(second.path)).height == 800


def test_render_does_not_touch_source_pdf(tmp_path: Path, layout: DataLayout) -> None:
    content = make_half_filled_pdf_bytes()
    source = _source(tmp_path, content)
    before = sha256_file(source)

    _render(source, layout)

    assert sha256_file(source) == before
    assert source.read_bytes() == content


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"\xff\xd8\xff\xe0 sentetik", "PDF değil"),
        (b"\x89PNG\r\n\x1a\n sentetik", "PDF değil"),
        (b"duz metin", "PDF değil"),
        (b"%PDF-1.4 bozuk", "açılamadı"),
        (make_sized_pdf_bytes([]), "sayfa yok"),
        (make_sized_pdf_bytes([A4], password="sentetik"), "parola"),
    ],
    ids=["jpeg", "png", "metin", "bozuk", "sayfasiz", "parolali"],
)
def test_unrenderable_file_raises_render_error(
    tmp_path: Path, layout: DataLayout, content: bytes, message: str
) -> None:
    with pytest.raises(RenderError, match=message):
        _render(_source(tmp_path, content), layout)

    assert list(layout.page_cache.iterdir()) == []


# --- bellekte render (tür açıklaması girdisi, 11.3.1) -------------------------------------------


def test_render_pdf_images_returns_first_pages_as_jpeg_and_the_page_count(
    tmp_path: Path, layout: DataLayout
) -> None:
    content = make_sized_pdf_bytes([A4, ID_CARD, A4])

    images, page_count = render_pdf_images(
        content, dpi=200, max_long_edge=1568, jpeg_quality=90, max_pages=2
    )

    assert page_count == 3
    assert len(images) == 2
    on_disk = [page.path.read_bytes() for page in _render(_source(tmp_path, content), layout)[:2]]
    # Diske yazan render ile aynı ölçek ve biçim.
    assert [detect_file_kind(image) for image in images] == [FileKind.JPEG, FileKind.JPEG]
    for image, written in zip(images, on_disk, strict=True):
        with Image.open(BytesIO(image)) as memory, Image.open(BytesIO(written)) as disk:
            assert memory.size == disk.size


def test_render_pdf_images_writes_nothing_and_can_only_count(layout: DataLayout) -> None:
    images, page_count = render_pdf_images(
        make_pdf_bytes(4), dpi=72, max_long_edge=500, jpeg_quality=80, max_pages=0
    )

    assert (images, page_count) == ([], 4)
    assert list(layout.page_cache.iterdir()) == []


def test_render_pdf_images_respects_the_long_edge_limit() -> None:
    (image,), _ = render_pdf_images(
        make_sized_pdf_bytes([A4]), dpi=300, max_long_edge=400, jpeg_quality=80, max_pages=5
    )

    with Image.open(BytesIO(image)) as opened:
        assert max(opened.size) <= 400


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (make_half_filled_image_bytes("JPEG"), "PDF değil"),
        (b"%PDF-1.4 bozuk", "açılamadı"),
        (make_sized_pdf_bytes([A4], password="sentetik"), "parola"),
    ],
    ids=["jpeg", "bozuk", "parolali"],
)
def test_render_pdf_images_raises_render_error(content: bytes, message: str) -> None:
    with pytest.raises(RenderError, match=message):
        render_pdf_images(content, dpi=72, max_long_edge=500, jpeg_quality=80, max_pages=1)


def test_render_pdf_images_rejects_negative_page_limit() -> None:
    with pytest.raises(ValueError, match="max_pages"):
        render_pdf_images(
            make_pdf_bytes(), dpi=72, max_long_edge=500, jpeg_quality=80, max_pages=-1
        )


# --- veritabanı bağlama -----------------------------------------------------------------------


def test_render_upload_file_records_pages_page_count_and_events(
    session: Session, layout: DataLayout
) -> None:
    upload_file = _stored_upload_file(
        session, layout, make_sized_pdf_bytes([A4, ID_CARD]), name="pasaport tarama.pdf"
    )
    settings = _settings(page_render_dpi=100, page_render_max_long_edge_px=500)

    pages = render_upload_file(session, layout, settings, upload_file)
    session.commit()

    assert upload_file.page_count == 2
    rows = session.scalars(
        select(Page).where(Page.file_id == upload_file.id).order_by(Page.index)
    ).all()
    assert rows == pages
    assert [row.index for row in rows] == [0, 1]
    assert [row.image_path for row in rows] == [
        f"cache/pages/{upload_file.id}/0000.jpg",
        f"cache/pages/{upload_file.id}/0001.jpg",
    ]
    assert all(layout.resolve(row.image_path).is_file() for row in rows)

    events = session.scalars(
        select(Event).where(Event.type == EventType.PAGE_RENDERED.value).order_by(Event.id)
    ).all()
    assert [(e.upload_id, e.file_id, e.page_index) for e in events] == [
        (upload_file.upload_id, upload_file.id, 0),
        (upload_file.upload_id, upload_file.id, 1),
    ]
    # A4 100 DPI'da 827×1170 px olurdu → 500 px uzun kenara iner; kimlik kartı sınır altında.
    assert events[0].data_json["height"] == 500
    assert events[0].data_json["image_path"] == rows[0].image_path
    assert events[1].data_json["dpi"] == 100.0
    assert events[1].data_json["width"] == pytest.approx(ID_CARD[0] * 100 / 72, abs=1)


def test_render_upload_file_again_keeps_existing_page_rows(
    session: Session, layout: DataLayout
) -> None:
    upload_file = _stored_upload_file(session, layout, make_pdf_bytes(2))
    render_upload_file(session, layout, _settings(), upload_file)
    session.commit()
    first_ids = [page.id for page in upload_file.pages]
    upload_file.pages[0].is_blank = True
    upload_file.pages[0].text_layer = "sentetik"
    session.commit()

    render_upload_file(session, layout, _settings(), upload_file)
    session.commit()

    assert [page.id for page in upload_file.pages] == first_ids
    assert upload_file.pages[0].is_blank is True
    assert upload_file.pages[0].text_layer == "sentetik"
    assert session.scalar(select(func.count()).select_from(Page)) == 2
    rendered_events = session.scalar(
        select(func.count()).where(Event.type == EventType.PAGE_RENDERED.value)
    )
    assert rendered_events == 4


def test_render_upload_file_rejects_non_pdf_without_side_effects(
    session: Session, layout: DataLayout
) -> None:
    upload_file = _stored_upload_file(session, layout, b"\xff\xd8\xff\xe0 sentetik", "foto.pdf")

    with pytest.raises(RenderError, match="PDF değil"):
        render_upload_file(session, layout, _settings(), upload_file)

    assert upload_file.page_count is None
    assert session.scalar(select(func.count()).select_from(Page)) == 0
    assert session.scalar(select(func.count()).select_from(Event)) == 0


# --- metin katmanı ------------------------------------------------------------------------------


def test_extract_page_text_returns_text_when_present() -> None:
    document = pymupdf.open(stream=make_text_pdf_bytes(["merhaba dünya"]), filetype="pdf")
    with document:
        [text] = [extract_page_text(page) for page in document]

    assert text is not None
    assert "merhaba" in text


def test_extract_page_text_is_none_for_scanned_page() -> None:
    document = pymupdf.open(stream=make_text_pdf_bytes([None]), filetype="pdf")
    with document:
        [text] = [extract_page_text(page) for page in document]

    assert text is None


def test_extract_pdf_text_matches_text_layer_per_page(tmp_path: Path) -> None:
    content = make_text_pdf_bytes(["birinci sayfa", None, "üçüncü sayfa"])
    texts = extract_pdf_text(_source(tmp_path, content))

    assert texts[1] is None
    assert texts[0] is not None and "birinci" in texts[0]
    assert texts[2] is not None and "üçüncü" in texts[2]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"\xff\xd8\xff\xe0 sentetik", "PDF değil"),
        (make_sized_pdf_bytes([A4], password="sentetik"), "parola"),
    ],
    ids=["jpeg", "parolali"],
)
def test_extract_pdf_text_raises_render_error(tmp_path: Path, content: bytes, message: str) -> None:
    with pytest.raises(RenderError, match=message):
        extract_pdf_text(_source(tmp_path, content))


def test_extract_upload_file_text_writes_text_layer_on_rendered_pages(
    session: Session, layout: DataLayout
) -> None:
    content = make_text_pdf_bytes(["gömülü metin burada", None])
    upload_file = _stored_upload_file(session, layout, content, name="taranmis.pdf")
    render_upload_file(session, layout, _settings(), upload_file)
    session.commit()

    pages = extract_upload_file_text(session, layout, upload_file)
    session.commit()

    assert [page.index for page in pages] == [0, 1]
    assert pages[0].text_layer is not None and "gömülü metin" in pages[0].text_layer
    assert pages[1].text_layer is None
    # Metin çıkarma render adımının ürettiği alanlara dokunmaz.
    assert all(page.image_path is not None for page in pages)


def test_extract_upload_file_text_does_not_create_duplicate_rows(
    session: Session, layout: DataLayout
) -> None:
    upload_file = _stored_upload_file(session, layout, make_text_pdf_bytes(["a", "b"]))
    render_upload_file(session, layout, _settings(), upload_file)
    session.commit()
    first_ids = [page.id for page in upload_file.pages]

    extract_upload_file_text(session, layout, upload_file)
    session.commit()

    assert [page.id for page in upload_file.pages] == first_ids
    assert session.scalar(select(func.count()).select_from(Page)) == 2


def test_extract_upload_file_text_does_not_touch_image_path(
    session: Session, layout: DataLayout
) -> None:
    upload_file = _stored_upload_file(session, layout, make_text_pdf_bytes(["a"]))
    render_upload_file(session, layout, _settings(), upload_file)
    session.commit()
    original_image_path = upload_file.pages[0].image_path

    extract_upload_file_text(session, layout, upload_file)
    session.commit()

    assert upload_file.pages[0].image_path == original_image_path


def test_extract_upload_file_text_creates_page_rows_when_none_rendered_yet(
    session: Session, layout: DataLayout
) -> None:
    upload_file = _stored_upload_file(session, layout, make_text_pdf_bytes(["a", None]))

    pages = extract_upload_file_text(session, layout, upload_file)
    session.commit()

    assert [page.index for page in pages] == [0, 1]
    assert pages[0].text_layer is not None
    assert pages[1].text_layer is None
    assert all(page.image_path is None for page in pages)


# --- görüntü dosyası analiz kopyası (02.3.1) ---------------------------------------------------


def test_image_copy_applies_exif_orientation(tmp_path: Path, layout: DataLayout) -> None:
    """Orijinalde sol yarı siyah; 180° EXIF yönelimiyle kopyada sağ yarı siyah olmalı."""
    content = make_half_filled_image_bytes(orientation=3)
    source = _source(tmp_path, content, name="foto.jpg")

    page = render_image_copy(source, layout, file_id=1, jpeg_quality=95)

    with Image.open(page.path) as image:
        rgb = image.convert("RGB")
        assert rgb.getpixel((10, 50)) == (255, 255, 255)
        assert rgb.getpixel((190, 50)) == (0, 0, 0)


def test_image_copy_without_exif_orientation_matches_source_layout(
    tmp_path: Path, layout: DataLayout
) -> None:
    content = make_half_filled_image_bytes()
    source = _source(tmp_path, content, name="foto.jpg")

    page = render_image_copy(source, layout, file_id=1, jpeg_quality=95)

    with Image.open(page.path) as image:
        rgb = image.convert("RGB")
        assert rgb.getpixel((10, 50)) == (0, 0, 0)
        assert rgb.getpixel((190, 50)) == (255, 255, 255)


@pytest.mark.parametrize(("fmt", "extension"), [("JPEG", "jpg"), ("PNG", "png")])
def test_image_copy_keeps_source_format(
    tmp_path: Path, layout: DataLayout, fmt: str, extension: str
) -> None:
    content = make_half_filled_image_bytes(fmt=fmt)
    source = _source(tmp_path, content, name=f"foto.{extension}")

    page = render_image_copy(source, layout, file_id=7, jpeg_quality=95)

    assert page.path == layout.page_cache / "7" / f"0000.{extension}"
    assert detect_file_kind(page.path.read_bytes()) is (
        FileKind.JPEG if extension == "jpg" else FileKind.PNG
    )


def test_image_copy_does_not_touch_source_file(tmp_path: Path, layout: DataLayout) -> None:
    content = make_half_filled_image_bytes(orientation=6)
    source = _source(tmp_path, content, name="foto.jpg")
    before = sha256_file(source)

    render_image_copy(source, layout, file_id=1, jpeg_quality=95)

    assert sha256_file(source) == before
    assert source.read_bytes() == content


@pytest.mark.parametrize(("fmt", "extension"), [("JPEG", "jpg"), ("PNG", "png")])
def test_in_memory_image_copy_matches_the_cached_copy(
    tmp_path: Path, layout: DataLayout, fmt: str, extension: str
) -> None:
    content = make_half_filled_image_bytes(fmt=fmt, orientation=3)

    copy = image_copy(content, jpeg_quality=95)
    page = render_image_copy(
        _source(tmp_path, content, f"foto.{extension}"), layout, 1, jpeg_quality=95
    )

    assert copy.content == page.path.read_bytes()
    assert (copy.extension, copy.width, copy.height) == (extension, page.width, page.height)


@pytest.mark.parametrize("content", [make_pdf_bytes(1), b"duz metin"], ids=["pdf", "metin"])
def test_in_memory_image_copy_rejects_non_image_content(content: bytes) -> None:
    with pytest.raises(RenderError, match="görüntü değil"):
        image_copy(content, jpeg_quality=95)


def test_image_copy_rejects_non_image_content(tmp_path: Path, layout: DataLayout) -> None:
    source = _source(tmp_path, make_pdf_bytes(1), name="belge.jpg")

    with pytest.raises(RenderError, match="görüntü değil"):
        render_image_copy(source, layout, file_id=1, jpeg_quality=95)


def test_render_image_file_records_page_page_count_and_event(
    session: Session, layout: DataLayout
) -> None:
    content = make_half_filled_image_bytes(orientation=3)
    upload_file = _stored_upload_file(session, layout, content, name="foto.jpg", mime="image/jpeg")

    pages = render_image_file(session, layout, _settings(), upload_file)
    session.commit()

    assert upload_file.page_count == 1
    [row] = session.scalars(select(Page).where(Page.file_id == upload_file.id)).all()
    assert pages == [row]
    assert row.index == 0
    assert row.image_path == f"cache/pages/{upload_file.id}/0000.jpg"
    assert layout.resolve(row.image_path).is_file()

    [event] = session.scalars(
        select(Event).where(Event.type == EventType.PAGE_RENDERED.value)
    ).all()
    assert (event.upload_id, event.file_id, event.page_index) == (
        upload_file.upload_id,
        upload_file.id,
        0,
    )
    assert event.data_json["image_path"] == row.image_path


def test_render_image_file_again_keeps_existing_page_row(
    session: Session, layout: DataLayout
) -> None:
    upload_file = _stored_upload_file(
        session, layout, make_half_filled_image_bytes(), name="foto.jpg", mime="image/jpeg"
    )
    render_image_file(session, layout, _settings(), upload_file)
    session.commit()
    first_id = upload_file.pages[0].id
    upload_file.pages[0].is_blank = True
    session.commit()

    render_image_file(session, layout, _settings(), upload_file)
    session.commit()

    assert [page.id for page in upload_file.pages] == [first_id]
    assert upload_file.pages[0].is_blank is True
    assert session.scalar(select(func.count()).select_from(Page)) == 1


def test_render_image_file_rejects_non_image_without_side_effects(
    session: Session, layout: DataLayout
) -> None:
    upload_file = _stored_upload_file(session, layout, make_pdf_bytes(1), name="belge.jpg")

    with pytest.raises(RenderError, match="görüntü değil"):
        render_image_file(session, layout, _settings(), upload_file)

    assert upload_file.page_count is None
    assert session.scalar(select(func.count()).select_from(Page)) == 0
    assert session.scalar(select(func.count()).select_from(Event)) == 0


# --- boş sayfa tespiti (02.4.1) ------------------------------------------------------------


def test_is_page_blank_true_for_page_without_content() -> None:
    document = pymupdf.open(stream=make_pdf_bytes(1), filetype="pdf")
    with document:
        assert is_page_blank(document[0]) is True


def test_is_page_blank_false_when_text_present() -> None:
    document = pymupdf.open(stream=make_text_pdf_bytes(["merhaba"]), filetype="pdf")
    with document:
        assert is_page_blank(document[0]) is False


def test_is_page_blank_false_when_drawing_present() -> None:
    document = pymupdf.open(stream=make_half_filled_pdf_bytes(), filetype="pdf")
    with document:
        assert is_page_blank(document[0]) is False


def test_is_page_blank_false_when_image_present() -> None:
    document = pymupdf.open(stream=_pdf_with_embedded_image_bytes(), filetype="pdf")
    with document:
        assert is_page_blank(document[0]) is False


def test_detect_pdf_blank_pages_matches_page_content(tmp_path: Path) -> None:
    content = make_text_pdf_bytes(["birinci sayfa", None, "üçüncü sayfa"])
    blanks = detect_pdf_blank_pages(_source(tmp_path, content))

    assert blanks == [False, True, False]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"\xff\xd8\xff\xe0 sentetik", "PDF değil"),
        (make_sized_pdf_bytes([A4], password="sentetik"), "parola"),
    ],
    ids=["jpeg", "parolali"],
)
def test_detect_pdf_blank_pages_raises_render_error(
    tmp_path: Path, content: bytes, message: str
) -> None:
    with pytest.raises(RenderError, match=message):
        detect_pdf_blank_pages(_source(tmp_path, content))


def test_mark_upload_file_blank_pages_writes_flag_and_event(
    session: Session, layout: DataLayout
) -> None:
    content = make_text_pdf_bytes(["metin var", None])
    upload_file = _stored_upload_file(session, layout, content, name="karma.pdf")
    render_upload_file(session, layout, _settings(), upload_file)
    session.commit()

    pages = mark_upload_file_blank_pages(session, layout, upload_file)
    session.commit()

    assert [page.index for page in pages] == [0, 1]
    assert pages[0].is_blank is False
    assert pages[1].is_blank is True
    # Boş sayfa işaretleme render adımının ürettiği alanlara dokunmaz.
    assert all(page.image_path is not None for page in pages)

    events = session.scalars(
        select(Event).where(Event.type == EventType.PAGE_BLANK.value).order_by(Event.id)
    ).all()
    assert [(e.upload_id, e.file_id, e.page_index) for e in events] == [
        (upload_file.upload_id, upload_file.id, 1),
    ]


def test_mark_upload_file_blank_pages_does_not_create_duplicate_rows(
    session: Session, layout: DataLayout
) -> None:
    upload_file = _stored_upload_file(session, layout, make_text_pdf_bytes(["a", "b"]))
    render_upload_file(session, layout, _settings(), upload_file)
    session.commit()
    first_ids = [page.id for page in upload_file.pages]

    mark_upload_file_blank_pages(session, layout, upload_file)
    session.commit()

    assert [page.id for page in upload_file.pages] == first_ids
    assert session.scalar(select(func.count()).select_from(Page)) == 2


def test_mark_upload_file_blank_pages_creates_page_rows_when_none_rendered_yet(
    session: Session, layout: DataLayout
) -> None:
    upload_file = _stored_upload_file(session, layout, make_text_pdf_bytes(["a", None]))

    pages = mark_upload_file_blank_pages(session, layout, upload_file)
    session.commit()

    assert [page.index for page in pages] == [0, 1]
    assert pages[0].is_blank is False
    assert pages[1].is_blank is True
    assert all(page.image_path is None for page in pages)


# --- gömülü tek görüntü tespiti (02.5.1) -----------------------------------------------------

PageEdit = Callable[[pymupdf.Document, pymupdf.Page, int], None]


def _image_page_pdf_bytes(
    edit: PageEdit | None = None,
    *,
    image: bytes | None = None,
    size: tuple[float, float] = A4,
    rect: tuple[float, float, float, float] | None = None,
) -> bytes:
    """Tek sayfalı PDF: sentetik görüntü sayfaya (varsayılan tüm sayfa kutusu) gömülür.

    Tarayıcı çıktısı gibi "tek tam sayfa görüntü" sayfasıdır; `edit(document, page, xref)`
    sayfayı bu tabandan saptırmak (metin, kırpma, maske eklemek vb.) için kullanılır.
    """
    document = pymupdf.open()
    page = document.new_page(width=size[0], height=size[1])
    xref = page.insert_image(
        pymupdf.Rect(rect) if rect is not None else page.rect,
        stream=image if image is not None else make_half_filled_image_bytes(size=(60, 85)),
        keep_proportion=False,
    )
    if edit is not None:
        edit(document, page, xref)
    content = document.tobytes()
    document.close()
    return content


def _set_content(document: pymupdf.Document, page: pymupdf.Page, stream: bytes) -> None:
    document.update_stream(page.get_contents()[0], stream)


def _wrap_content(before: bytes, after: bytes = b"") -> PageEdit:
    def edit(document: pymupdf.Document, page: pymupdf.Page, xref: int) -> None:
        original = document.xref_stream(page.get_contents()[0])
        _set_content(document, page, before + b"\n" + original + b"\n" + after)

    return edit


def _with_ext_gstate(gstate: str) -> PageEdit:
    def edit(document: pymupdf.Document, page: pymupdf.Page, xref: int) -> None:
        gs_xref = document.get_new_xref()
        document.update_object(gs_xref, gstate)
        resources = int(document.xref_get_key(page.xref, "Resources")[1].split()[0])
        document.xref_set_key(resources, "ExtGState", f"<</GS0 {gs_xref} 0 R>>")
        _wrap_content(b"/GS0 gs")(document, page, xref)

    return edit


def _draw_image_with(matrix: bytes) -> PageEdit:
    def edit(document: pymupdf.Document, page: pymupdf.Page, xref: int) -> None:
        name = page.get_images(full=True)[0][7].encode()
        _set_content(document, page, b"q " + matrix + b" cm /" + name + b" Do Q")

    return edit


def _drawn_twice(document: pymupdf.Document, page: pymupdf.Page, xref: int) -> None:
    original = document.xref_stream(page.get_contents()[0])
    _set_content(document, page, original + b"\n" + original)


def _inline_image_only(document: pymupdf.Document, page: pymupdf.Page, xref: int) -> None:
    # Kaynakta görüntü nesnesi durur ama çizilen, xref'i olmayan satır içi görüntüdür.
    inline = b"q 595 0 0 842 0 0 cm BI /W 2 /H 2 /CS /G /BPC 8 ID \x00\xff\xff\x00 EI Q"
    _set_content(document, page, inline)


def _second_image(document: pymupdf.Document, page: pymupdf.Page, xref: int) -> None:
    page.insert_image(pymupdf.Rect(20, 20, 80, 80), stream=make_half_filled_image_bytes("PNG"))


def _unused_second_image(document: pymupdf.Document, page: pymupdf.Page, xref: int) -> None:
    # Sayfa yalnız ilk görüntüyü çizer; ikincisi kaynaklarda kullanılmadan durur.
    name = page.get_images(full=True)[0][7].encode()
    _second_image(document, page, xref)
    for contents in page.get_contents():
        document.update_stream(contents, b"")
    _set_content(document, page, b"q 595 0 0 842 0 0 cm /" + name + b" Do Q")


def _cropbox_inside_image(document: pymupdf.Document, page: pymupdf.Page, xref: int) -> None:
    page.set_cropbox(pymupdf.Rect(50, 50, page.rect.width - 50, page.rect.height - 50))


def _cropped_page_with_image_on_cropbox() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=700, height=900)
    page.set_cropbox(pymupdf.Rect(50, 50, 645, 892))
    page.insert_image(page.rect, stream=make_half_filled_image_bytes(), keep_proportion=False)
    content = document.tobytes()
    document.close()
    return content


def _pillow_pdf_bytes() -> bytes:
    buffer = BytesIO()
    with Image.open(BytesIO(make_half_filled_image_bytes(size=(600, 850)))) as image:
        image.save(buffer, format="PDF", resolution=72.0)
    return buffer.getvalue()


def _rgba_png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", (40, 60), (0, 0, 0, 128)).save(buffer, format="PNG")
    return buffer.getvalue()


def _edited(edit: PageEdit) -> Callable[[], bytes]:
    return lambda: _image_page_pdf_bytes(edit)


# (kimlik, PDF üretici, tek tam sayfa görüntü mü)
SINGLE_IMAGE_CASES: list[tuple[str, Callable[[], bytes], bool]] = [
    ("jpeg_tam_sayfa", _image_page_pdf_bytes, True),
    (
        "png_tam_sayfa",
        lambda: _image_page_pdf_bytes(image=make_half_filled_image_bytes("PNG")),
        True,
    ),
    (
        "gorunmez_ocr_metni",
        _edited(lambda d, p, x: p.insert_text((72, 72), "ocr", render_mode=3)),
        True,
    ),
    ("sayfayi_kaplayan_kirpma", _edited(_wrap_content(b"q 0 0 595 842 re W n", b"Q")), True),
    (
        "sayfa_saydamlik_grubu",
        _edited(
            lambda d, p, x: d.xref_set_key(p.xref, "Group", "<</S/Transparency/CS/DeviceRGB>>")
        ),
        True,
    ),
    (
        "tolerans_icinde_kenar_farki",
        lambda: _image_page_pdf_bytes(rect=(0.6, 0.6, A4[0] - 0.6, A4[1] - 0.6)),
        True,
    ),
    ("kirpma_kutusuna_oturan_goruntu", _cropped_page_with_image_on_cropbox, True),
    ("pillow_pdf_ciktisi", _pillow_pdf_bytes, True),
    ("bos_sayfa", lambda: make_pdf_bytes(1), False),
    ("yalniz_metin", lambda: make_text_pdf_bytes(["metin"]), False),
    ("yalniz_cizim", make_half_filled_pdf_bytes, False),
    ("kucuk_goruntu", _pdf_with_embedded_image_bytes, False),
    (
        "tolerans_disinda_kenar_boslugu",
        lambda: _image_page_pdf_bytes(rect=(2, 2, A4[0] - 2, A4[1] - 2)),
        False,
    ),
    ("goruntu_ve_gorunur_metin", _edited(lambda d, p, x: p.insert_text((72, 72), "damga")), False),
    (
        "goruntu_ve_cizim",
        _edited(lambda d, p, x: p.draw_rect(pymupdf.Rect(10, 10, 50, 50), color=(1, 0, 0))),
        False,
    ),
    ("iki_goruntu", _edited(_second_image), False),
    ("kullanilmayan_ikinci_goruntu_kaynagi", _edited(_unused_second_image), False),
    ("ayni_goruntu_iki_kez", _edited(_drawn_twice), False),
    (
        "aciklama_notu",
        _edited(lambda d, p, x: p.add_rect_annot(pymupdf.Rect(10, 10, 50, 50))),
        False,
    ),
    ("doksan_derece_yerlestirme", _edited(_draw_image_with(b"0 842 -595 0 595 0")), False),
    ("aynalanmis_yerlestirme", _edited(_draw_image_with(b"595 0 0 -842 0 842")), False),
    ("sayfa_rotate_90", _edited(lambda d, p, x: p.set_rotation(90)), False),
    ("alfa_kanalli_png", lambda: _image_page_pdf_bytes(image=_rgba_png_bytes()), False),
    ("decode_dizisi", _edited(lambda d, p, x: d.xref_set_key(x, "Decode", "[1 0 1 0 1 0]")), False),
    (
        "renk_anahtari_maskesi",
        _edited(lambda d, p, x: d.xref_set_key(x, "Mask", "[0 9 0 9 0 9]")),
        False,
    ),
    ("sayfadan_dar_kirpma", _edited(_wrap_content(b"q 0 0 300 842 re W n", b"Q")), False),
    (
        "dikdortgen_olmayan_kirpma",
        _edited(
            _wrap_content(
                b"q 297.5 842 m 595 842 595 0 297.5 0 c 0 0 0 842 297.5 842 c h W n", b"Q"
            )
        ),
        False,
    ),
    ("yari_saydam_cizim", _edited(_with_ext_gstate("<</Type/ExtGState/ca 0.5>>")), False),
    ("normal_disi_karisim", _edited(_with_ext_gstate("<</Type/ExtGState/BM/Multiply>>")), False),
    ("satir_ici_goruntu", _edited(_inline_image_only), False),
    ("kirpma_kutusundan_tasan_goruntu", _edited(_cropbox_inside_image), False),
]


@pytest.mark.parametrize(
    ("build", "expected"),
    [(build, expected) for _, build, expected in SINGLE_IMAGE_CASES],
    ids=[case_id for case_id, _, _ in SINGLE_IMAGE_CASES],
)
def test_single_full_page_image_xref_only_for_page_made_of_one_full_page_image(
    build: Callable[[], bytes], expected: bool
) -> None:
    document = pymupdf.open(stream=build(), filetype="pdf")
    with document:
        page = document[0]
        xref = single_full_page_image_xref(page)

        assert (xref is not None) is expected
        if expected:
            assert xref == page.get_images(full=True)[0][0]


def test_single_full_page_image_xref_points_to_original_embedded_bytes() -> None:
    image = make_half_filled_image_bytes("JPEG", size=(60, 85))
    document = pymupdf.open(stream=_image_page_pdf_bytes(image=image), filetype="pdf")
    with document:
        xref = single_full_page_image_xref(document[0])

        assert xref is not None
        # §20.5 extract_image: işaretli sayfanın xref'i orijinal gömülü baytları verir.
        extracted = document.extract_image(xref)
        assert extracted["image"] == image
        assert extracted["ext"] == "jpeg"


def _image_text_blank_pdf_bytes() -> bytes:
    document = pymupdf.open(stream=_image_page_pdf_bytes(), filetype="pdf")
    text_page = document.new_page(width=A4[0], height=A4[1])
    text_page.insert_text((72, 72), "ikinci sayfa")
    document.new_page(width=A4[0], height=A4[1])
    content = document.tobytes()
    document.close()
    return content


def test_detect_pdf_single_image_pages_matches_page_content(tmp_path: Path) -> None:
    flags = detect_pdf_single_image_pages(_source(tmp_path, _image_text_blank_pdf_bytes()))

    assert flags == [True, False, False]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"\xff\xd8\xff\xe0 sentetik", "PDF değil"),
        (make_sized_pdf_bytes([A4], password="sentetik"), "parola"),
    ],
    ids=["jpeg", "parolali"],
)
def test_detect_pdf_single_image_pages_raises_render_error(
    tmp_path: Path, content: bytes, message: str
) -> None:
    with pytest.raises(RenderError, match=message):
        detect_pdf_single_image_pages(_source(tmp_path, content))


def test_mark_upload_file_single_image_pages_writes_flag_without_touching_other_fields(
    session: Session, layout: DataLayout
) -> None:
    upload_file = _stored_upload_file(session, layout, _image_text_blank_pdf_bytes())
    render_upload_file(session, layout, _settings(), upload_file)
    extract_upload_file_text(session, layout, upload_file)
    mark_upload_file_blank_pages(session, layout, upload_file)
    session.commit()
    before = [(page.image_path, page.text_layer, page.is_blank) for page in upload_file.pages]
    event_count = session.scalar(select(func.count()).select_from(Event))

    pages = mark_upload_file_single_image_pages(session, layout, upload_file)
    session.commit()

    assert [page.index for page in pages] == [0, 1, 2]
    assert [page.has_single_embedded_image for page in pages] == [True, False, False]
    assert [(page.image_path, page.text_layer, page.is_blank) for page in pages] == before
    # PRD §8.3'ün kapalı listesinde bu tespit için olay türü yok (PLAN.md §D6).
    assert session.scalar(select(func.count()).select_from(Event)) == event_count


def test_mark_upload_file_single_image_pages_does_not_create_duplicate_rows(
    session: Session, layout: DataLayout
) -> None:
    upload_file = _stored_upload_file(session, layout, _image_text_blank_pdf_bytes())
    render_upload_file(session, layout, _settings(), upload_file)
    session.commit()
    first_ids = [page.id for page in upload_file.pages]

    mark_upload_file_single_image_pages(session, layout, upload_file)
    session.commit()

    assert [page.id for page in upload_file.pages] == first_ids
    assert session.scalar(select(func.count()).select_from(Page)) == 3


def test_mark_upload_file_single_image_pages_creates_page_rows_when_none_rendered_yet(
    session: Session, layout: DataLayout
) -> None:
    upload_file = _stored_upload_file(session, layout, _image_page_pdf_bytes())

    pages = mark_upload_file_single_image_pages(session, layout, upload_file)
    session.commit()

    assert [page.index for page in pages] == [0]
    assert pages[0].has_single_embedded_image is True
    assert pages[0].image_path is None
