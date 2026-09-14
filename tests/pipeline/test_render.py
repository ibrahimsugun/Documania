"""02.1.1 — PDF sayfa görüntüsü, 02.2.1 — PDF metin katmanı çıkarma."""

from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Event, Page, Upload, UploadFile
from app.events import EventType
from app.pipeline.render import (
    RenderError,
    extract_page_text,
    extract_pdf_text,
    extract_upload_file_text,
    render_pdf_pages,
    render_scale,
    render_upload_file,
)
from app.storage import DataLayout, FileKind, detect_file_kind, sha256_file, write_to_inbox
from tests.fixtures.gen import (
    A4,
    make_half_filled_pdf_bytes,
    make_pdf_bytes,
    make_sized_pdf_bytes,
    make_text_pdf_bytes,
)

ID_CARD = (243.0, 153.0)  # 85,6 × 54 mm


def _source(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / "belge.pdf"
    path.write_bytes(content)
    return path


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
    session: Session, layout: DataLayout, content: bytes, name: str = "tarama.pdf"
) -> UploadFile:
    upload = Upload(id="u_20260914_0001", channel="web")
    stored = write_to_inbox(layout, upload.id, name, content)
    upload_file = UploadFile(
        upload=upload,
        original_name=name,
        stored_path=stored.path.relative_to(layout.root).as_posix(),
        sha256=stored.sha256,
        mime="application/pdf",
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
