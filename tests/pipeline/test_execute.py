"""Uygulayıcı işlemleri (§20.5).

07.1.1 — passthrough: bayt bayt kopya, SHA-256 eşitliği.
07.2.1 — extract: sayfa nesnesi kopyası, render yok, metin katmanı korunur (S7).
07.3.1 — merge: yalnız Direkt Belge olmayan türde, kaynaklar plan sırasıyla; görüntü kayıpsız
sarılır (S5).
"""

from io import BytesIO
from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageDraw
from pypdf import PageObject, PdfReader, PdfWriter
from sqlalchemy.orm import Session

import app.pipeline.execute as execute_module
from app.ai.recording_provider import RecordingProvider
from app.pipeline.analyze import analyze_upload
from app.pipeline.execute import (
    DirectDocumentMergeError,
    ExtractIntegrityError,
    ExtractSourceError,
    MergeIntegrityError,
    MergeSource,
    MergeSourceError,
    PassthroughIntegrityError,
    execute_extract,
    execute_merge,
    execute_passthrough,
)
from app.pipeline.plan import Operation, Route, create_plan, read_plan
from app.storage import DataLayout, StoredFile, sha256_file
from tests.fixtures.gen import (
    A4,
    make_docx_bytes,
    make_half_filled_image_bytes,
    make_pdf_bytes,
    make_sized_pdf_bytes,
    make_text_pdf_bytes,
)
from tests.pipeline.test_group import (
    CATALOG,
    INSTRUCTIONS,
    LICENSE,
    PASSPORT,
    S5_RECORDINGS,
    _recording,
    _recordings,
    _upload,
)


def _source(tmp_path: Path, content: bytes, name: str = "kaynak.pdf") -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_execute_passthrough_copies_bytes_identically(tmp_path: Path) -> None:
    content = make_pdf_bytes(page_count=3)
    source = _source(tmp_path, content)
    destination = tmp_path / "out" / "hedef.pdf"

    stored = execute_passthrough(source, destination)

    assert destination.read_bytes() == content
    assert stored.path == destination
    assert stored.size == len(content)


def test_execute_passthrough_hash_matches_source(tmp_path: Path) -> None:
    source = _source(tmp_path, make_pdf_bytes())
    destination = tmp_path / "hedef.pdf"

    stored = execute_passthrough(source, destination)

    assert stored.sha256 == sha256_file(source)
    assert stored.sha256 == sha256_file(destination)


def test_execute_passthrough_does_not_overwrite_existing_destination(tmp_path: Path) -> None:
    source = _source(tmp_path, make_pdf_bytes())
    destination = tmp_path / "hedef.pdf"
    destination.write_bytes(b"onceden var olan icerik")

    with pytest.raises(FileExistsError):
        execute_passthrough(source, destination)

    assert destination.read_bytes() == b"onceden var olan icerik"


def test_execute_passthrough_rejects_mismatched_hash(tmp_path: Path, monkeypatch) -> None:
    source = _source(tmp_path, make_pdf_bytes())
    destination = tmp_path / "hedef.pdf"

    def _fake_copy_file(_source: Path, dest: Path) -> StoredFile:
        dest.write_bytes(b"baska bir icerik")
        return StoredFile(dest, sha256="0" * 64, size=16)

    monkeypatch.setattr("app.pipeline.execute.copy_file", _fake_copy_file)

    with pytest.raises(PassthroughIntegrityError):
        execute_passthrough(source, destination)


# --- 07.2.1 — extract ---


def _multi_page_pdf_bytes(*, compressed: bool = True) -> tuple[bytes, bytes]:
    """Dört sayfalı sentetik PDF ve gömülü JPEG'in baytları.

    0: kapak metni · 1: metin + gömülü JPEG (sentetik pasaport sayfası) · 2: 90° döndürülmüş,
    farklı boyutlu metin sayfası · 3: yalnız gömülü görüntü, metin katmanı yok (taranmış sayfa).
    """
    jpeg = make_half_filled_image_bytes("JPEG", (120, 80))
    document = pymupdf.open()
    cover = document.new_page(width=A4[0], height=A4[1])
    cover.insert_text((72, 72), "SENTETIK KAPAK")
    passport = document.new_page(width=A4[0], height=A4[1])
    passport.insert_text((72, 72), "SENTETIK PASAPORT")
    passport.insert_text((72, 700), "P<SNTTEST<<ORNEK<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
    passport.insert_image(pymupdf.Rect(72, 100, 312, 260), stream=jpeg)
    rotated = document.new_page(width=420, height=600)
    rotated.insert_text((72, 72), "SENTETIK DONUK SAYFA")
    rotated.set_rotation(90)
    scanned = document.new_page(width=A4[0], height=A4[1])
    scanned.insert_image(pymupdf.Rect(0, 0, A4[0], A4[1]), stream=jpeg)
    content = document.tobytes(deflate=compressed)
    document.close()
    return content, jpeg


def _inherited_attributes_pdf_bytes() -> bytes:
    """İki sayfalı el yapımı PDF: `MediaBox`, `Rotate` ve `Resources` sayfada değil `/Pages`'te.

    Sayfa nesnesi kopyası kalıtılan özellikleri düşürürse çıktı sayfasının boyutu, döndürmesi ve
    fontu değişir.
    """
    streams = [
        b"BT /F1 18 Tf 72 500 Td (SENTETIK BIR) Tj ET",
        b"BT /F1 18 Tf 72 500 Td (SENTETIK IKI) Tj ET",
    ]
    bodies = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 /MediaBox [0 0 400 700] /Rotate 270"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Type /Page /Parent 2 0 R /Contents 6 0 R >>",
        b"<< /Type /Page /Parent 2 0 R /Contents 7 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        *(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(data), data) for data in streams),
    ]
    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for number, body in enumerate(bodies, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(bodies) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n" % (len(bodies) + 1, xref)
    out += b"%%EOF\n"
    return bytes(out)


def _open(path: Path) -> pymupdf.Document:
    return pymupdf.open(stream=path.read_bytes(), filetype="pdf")


def _raw_contents(document: pymupdf.Document, index: int) -> bytes:
    """Sayfanın içerik akışlarının dosyadaki (sıkıştırılmışsa sıkıştırılmış) baytları."""
    return b"".join(document.xref_stream_raw(xref) for xref in document[index].get_contents())


def _raw_images(document: pymupdf.Document, index: int) -> list[bytes]:
    return [document.xref_stream_raw(image[0]) for image in document[index].get_images(full=True)]


def _embedded_images(document: pymupdf.Document, index: int) -> list[bytes]:
    return [document.extract_image(image[0])["image"] for image in document[index].get_images()]


def test_execute_extract_single_page_from_multi_page_pdf_s7(tmp_path: Path) -> None:
    content, jpeg = _multi_page_pdf_bytes()
    source = _source(tmp_path, content)
    destination = tmp_path / "Hazir" / "Ornek_Kisi-Passport.pdf"

    stored = execute_extract(source, destination, pages=[1])

    assert stored.path == destination
    assert stored.sha256 == sha256_file(destination)
    assert stored.size == destination.stat().st_size
    with _open(source) as src, _open(destination) as out:
        assert out.page_count == 1
        assert out[0].get_text() == src[1].get_text()
        assert "SENTETIK PASAPORT" in out[0].get_text()
        # Render yok: sayfa görüntüye çevrilmedi — aynı içerik akışı, aynı tek gömülü JPEG.
        assert _raw_contents(out, 0) == _raw_contents(src, 1)
        assert _raw_images(out, 0) == _raw_images(src, 1)
        assert _embedded_images(out, 0) == [jpeg]


def test_execute_extract_keeps_page_objects_of_every_selected_page_in_order(
    tmp_path: Path,
) -> None:
    content, _jpeg = _multi_page_pdf_bytes()
    source = _source(tmp_path, content)
    destination = tmp_path / "hedef.pdf"

    execute_extract(source, destination, pages=(0, 2, 3))

    with _open(source) as src, _open(destination) as out:
        assert out.page_count == 3
        for output_index, source_index in enumerate((0, 2, 3)):
            assert out[output_index].get_text() == src[source_index].get_text()
            assert _raw_contents(out, output_index) == _raw_contents(src, source_index)
            assert _raw_images(out, output_index) == _raw_images(src, source_index)
            assert out[output_index].rotation == src[source_index].rotation
            assert out[output_index].mediabox == src[source_index].mediabox


def test_execute_extract_preserves_uncompressed_content_streams(tmp_path: Path) -> None:
    content, _jpeg = _multi_page_pdf_bytes(compressed=False)
    source = _source(tmp_path, content)
    destination = tmp_path / "hedef.pdf"

    execute_extract(source, destination, pages=[1])

    with _open(source) as src, _open(destination) as out:
        assert _raw_contents(out, 0) == _raw_contents(src, 1)
        assert b"BT\n1 0 0 1 72 770 Tm\n" in _raw_contents(out, 0)


def test_execute_extract_keeps_rotation_and_size(tmp_path: Path) -> None:
    content, _jpeg = _multi_page_pdf_bytes()
    source = _source(tmp_path, content)
    destination = tmp_path / "hedef.pdf"

    execute_extract(source, destination, pages=[2])

    with _open(destination) as out:
        assert out[0].rotation == 90
        assert out[0].mediabox == pymupdf.Rect(0, 0, 420, 600)
        assert out[0].get_text().strip() == "SENTETIK DONUK SAYFA"


def test_execute_extract_keeps_attributes_inherited_from_page_tree(tmp_path: Path) -> None:
    source = _source(tmp_path, _inherited_attributes_pdf_bytes())
    destination = tmp_path / "hedef.pdf"

    execute_extract(source, destination, pages=[1])

    with _open(source) as src, _open(destination) as out:
        assert out.page_count == 1
        assert out[0].rotation == src[1].rotation == 270
        assert out[0].mediabox == src[1].mediabox == pymupdf.Rect(0, 0, 400, 700)
        assert out[0].get_text() == src[1].get_text() == "SENTETIK IKI\n"
        assert _raw_contents(out, 0) == _raw_contents(src, 1)


def test_execute_extract_page_without_text_layer_keeps_embedded_image(tmp_path: Path) -> None:
    content, jpeg = _multi_page_pdf_bytes()
    source = _source(tmp_path, content)
    destination = tmp_path / "hedef.pdf"

    execute_extract(source, destination, pages=[3])

    with _open(destination) as out:
        assert out[0].get_text() == ""
        assert _embedded_images(out, 0) == [jpeg]


def test_execute_extract_does_not_compress_content_streams(tmp_path: Path, monkeypatch) -> None:
    content, _jpeg = _multi_page_pdf_bytes(compressed=False)
    source = _source(tmp_path, content)

    def _forbidden(*_args, **_kwargs) -> None:
        raise AssertionError("compress_content_streams çağrılmamalı (§20.5)")

    monkeypatch.setattr(PageObject, "compress_content_streams", _forbidden)

    execute_extract(source, tmp_path / "hedef.pdf", pages=[0, 1])

    assert (tmp_path / "hedef.pdf").exists()


def test_execute_extract_leaves_source_untouched(tmp_path: Path) -> None:
    content, _jpeg = _multi_page_pdf_bytes()
    source = _source(tmp_path, content)

    execute_extract(source, tmp_path / "hedef.pdf", pages=[1])

    assert source.read_bytes() == content


def test_execute_extract_does_not_overwrite_existing_destination(tmp_path: Path) -> None:
    content, _jpeg = _multi_page_pdf_bytes()
    source = _source(tmp_path, content)
    destination = tmp_path / "hedef.pdf"
    destination.write_bytes(b"onceden var olan icerik")

    with pytest.raises(FileExistsError):
        execute_extract(source, destination, pages=[1])

    assert destination.read_bytes() == b"onceden var olan icerik"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["hedef.pdf", "kaynak.pdf"]


@pytest.mark.parametrize("pages", [[], [-1], [2, 1], [1, 1], [0, 2, 2]])
def test_execute_extract_rejects_invalid_page_selection(tmp_path: Path, pages) -> None:
    content, _jpeg = _multi_page_pdf_bytes()
    source = _source(tmp_path, content)
    destination = tmp_path / "hedef.pdf"

    with pytest.raises(ValueError):
        execute_extract(source, destination, pages=pages)

    assert not destination.exists()


def test_execute_extract_rejects_page_missing_from_source(tmp_path: Path) -> None:
    content, _jpeg = _multi_page_pdf_bytes()
    source = _source(tmp_path, content)
    destination = tmp_path / "hedef.pdf"

    with pytest.raises(ExtractSourceError, match="sayfa 4"):
        execute_extract(source, destination, pages=[1, 4])

    assert not destination.exists()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        pytest.param(make_half_filled_image_bytes("JPEG"), "PDF değil", id="jpeg"),
        pytest.param(make_half_filled_image_bytes("PNG"), "PDF değil", id="png"),
        pytest.param(make_docx_bytes(), "PDF değil", id="docx"),
        pytest.param(b"duz metin, taninmayan tur", "PDF değil", id="taninmayan"),
        pytest.param(b"%PDF-1.7\ngarbage garbage\n", "açılamadı", id="mupdf-acamiyor"),
        pytest.param(
            b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n",
            "pypdf ile okunamadı",
            id="pypdf-okuyamiyor",
        ),
        pytest.param(make_sized_pdf_bytes([A4], password="gizli"), "parola", id="parola"),
    ],
)
def test_execute_extract_rejects_unreadable_source(
    tmp_path: Path, content: bytes, message: str
) -> None:
    source = _source(tmp_path, content)
    destination = tmp_path / "hedef.pdf"

    with pytest.raises(ExtractSourceError, match=message):
        execute_extract(source, destination, pages=[0])

    assert not destination.exists()


def test_execute_extract_rejects_page_count_disagreement_between_readers(
    tmp_path: Path, monkeypatch
) -> None:
    content, _jpeg = _multi_page_pdf_bytes()
    source = _source(tmp_path, content)
    destination = tmp_path / "hedef.pdf"

    class _ShortReader(PdfReader):
        """Bozuk PDF'i MuPDF'ten farklı onaran okuyucu: son sayfayı görmez."""

        @property
        def pages(self):
            return super().pages[:-1]

    monkeypatch.setattr(execute_module, "PdfReader", _ShortReader)

    with pytest.raises(ExtractSourceError, match="MuPDF 4, pypdf 3"):
        execute_extract(source, destination, pages=[1])

    assert not destination.exists()


def test_execute_extract_opens_owner_password_only_pdf(tmp_path: Path) -> None:
    writer = PdfWriter(clone_from=BytesIO(make_text_pdf_bytes(["SENTETIK A", "SENTETIK B"])))
    writer.encrypt(user_password="", owner_password="sahip")
    buffer = BytesIO()
    writer.write(buffer)
    source = _source(tmp_path, buffer.getvalue())
    destination = tmp_path / "hedef.pdf"

    execute_extract(source, destination, pages=[1])

    with _open(source) as src, _open(destination) as out:
        assert out.page_count == 1
        assert out[0].get_text() == src[1].get_text() == "SENTETIK B\n"


class _ExtraPageWriter(PdfWriter):
    """Her sayfanın ardına boş bir sayfa ekler — sayfa sayısı doğrulamasını sınar."""

    def add_page(self, page, *args, **kwargs):
        added = super().add_page(page, *args, **kwargs)
        super().add_page(PageObject.create_blank_page(width=100, height=100))
        return added


class _WrongPageWriter(PdfWriter):
    """İstenen sayfa yerine kaynağın ilk sayfasını ekler — metin katmanı doğrulamasını sınar."""

    def add_page(self, page, *args, **kwargs):
        return super().add_page(page.pdf.pages[0], *args, **kwargs)


class _GarbageWriter(PdfWriter):
    """PDF olmayan bayt yazar — çıktının açılamadığı durumu sınar."""

    def write(self, stream):
        stream.write(b"PDF degil")
        return True, stream


@pytest.mark.parametrize(
    ("writer", "message"),
    [
        (_ExtraPageWriter, "sayfa sayısı"),
        (_WrongPageWriter, "metin katmanı"),
        (_GarbageWriter, "açılamadı"),
    ],
)
def test_execute_extract_verifies_output_before_publishing(
    tmp_path: Path, monkeypatch, writer, message: str
) -> None:
    content, _jpeg = _multi_page_pdf_bytes()
    source = _source(tmp_path, content)
    destination = tmp_path / "hedef.pdf"
    monkeypatch.setattr(execute_module, "PdfWriter", writer)

    with pytest.raises(ExtractIntegrityError, match=message):
        execute_extract(source, destination, pages=[1, 2])

    assert not destination.exists()
    assert [path.name for path in tmp_path.iterdir()] == ["kaynak.pdf"]


# --- 07.3.1 — merge ---


def _texts(path: Path) -> list[str]:
    with _open(path) as document:
        return [page.get_text() for page in document]


def _text_pdf(tmp_path: Path, name: str, *texts: str) -> Path:
    return _source(tmp_path, make_text_pdf_bytes(texts), name)


def test_execute_merge_wraps_front_and_back_images_losslessly_into_one_pdf_s5(
    tmp_path: Path,
) -> None:
    front = make_half_filled_image_bytes("JPEG", (300, 190))
    back = make_half_filled_image_bytes("JPEG", (310, 195))
    sources = [
        MergeSource(_source(tmp_path, front, "on.jpg"), (0,)),
        MergeSource(_source(tmp_path, back, "arka.jpg"), (0,)),
    ]
    destination = tmp_path / "Hazir" / "Ornek_Kisi-Driving-License.pdf"

    stored = execute_merge(sources, destination, direct=False)

    assert stored.path == destination
    assert stored.sha256 == sha256_file(destination)
    assert stored.size == destination.stat().st_size
    with _open(destination) as out:
        assert out.page_count == 2
        # Kayıpsız sarma: JPEG baytları yeniden kodlanmadan gömülü; sayfa görüntünün kendisidir.
        assert [_raw_images(out, index) for index in (0, 1)] == [[front], [back]]
        assert [_embedded_images(out, index) for index in (0, 1)] == [[front], [back]]
        for page in out:
            (image,) = page.get_images(full=True)
            assert page.get_image_bbox(image) == page.rect
            assert page.rotation == 0
            assert page.get_text() == ""
    assert [source.path.read_bytes() for source in sources] == [front, back]


@pytest.mark.parametrize("reverse", [False, True], ids=["a-b", "b-a"])
def test_execute_merge_takes_pages_in_sources_order_without_reordering(
    tmp_path: Path, reverse: bool
) -> None:
    first = MergeSource(_text_pdf(tmp_path, "a.pdf", "SENTETIK A0", "SENTETIK A1", "A2"), (0, 2))
    second = MergeSource(_text_pdf(tmp_path, "b.pdf", "SENTETIK B0", "SENTETIK B1"), (0, 1))
    sources = [second, first] if reverse else [first, second]
    destination = tmp_path / "hedef.pdf"

    execute_merge(sources, destination, direct=False)

    a_pages = ["SENTETIK A0\n", "A2\n"]
    b_pages = ["SENTETIK B0\n", "SENTETIK B1\n"]
    assert _texts(destination) == (b_pages + a_pages if reverse else a_pages + b_pages)


def test_execute_merge_copies_pdf_page_objects_and_wraps_images_without_reencoding(
    tmp_path: Path,
) -> None:
    content, jpeg = _multi_page_pdf_bytes()
    png = make_half_filled_image_bytes("PNG", (120, 80))
    turned = make_half_filled_image_bytes("JPEG", (120, 80), orientation=6)
    pdf = _source(tmp_path, content)
    sources = [
        MergeSource(pdf, (1, 2)),
        MergeSource(_source(tmp_path, png, "foto.png"), (0,)),
        MergeSource(_source(tmp_path, turned, "donuk.jpg"), (0,)),
    ]
    destination = tmp_path / "hedef.pdf"

    execute_merge(sources, destination, direct=False)

    with _open(pdf) as src, _open(destination) as out:
        assert out.page_count == 4
        # PDF sayfaları sayfa nesnesi kopyası: içerik akışı, görüntü, boyut ve döndürme aynı.
        for output_index, source_index in ((0, 1), (1, 2)):
            assert out[output_index].get_text() == src[source_index].get_text()
            assert _raw_contents(out, output_index) == _raw_contents(src, source_index)
            assert _raw_images(out, output_index) == _raw_images(src, source_index)
            assert out[output_index].rotation == src[source_index].rotation
            assert out[output_index].mediabox == src[source_index].mediabox
        assert _embedded_images(out, 0) == [jpeg]
        # PNG kayıpsız: gömülü görüntünün pikselleri kaynağınkiyle birebir aynı.
        (image,) = out[2].get_images(full=True)
        pixmap = pymupdf.Pixmap(out, image[0])
        with Image.open(BytesIO(png)) as original:
            assert (pixmap.width, pixmap.height) == original.size
            assert pixmap.samples == original.convert("RGB").tobytes()
        # EXIF yönelimi yalnız `/Rotate`: JPEG baytları değişmez, pikseller döndürülmez.
        assert _raw_images(out, 3) == [turned]
        assert out[3].rotation == 90


def test_execute_merge_keeps_png_alpha_as_soft_mask_without_flattening(tmp_path: Path) -> None:
    # img2pdf 0.6 alfa kanallı PNG'yi reddetmez; saydamlığı ayrı `/SMask` görüntüsünde saklar.
    # Renk ve alfa kanalları kayıpsız ayrılır, beyaz zemine düzleştirme yapılmaz (PLAN.md §D17).
    image = Image.new("RGBA", (60, 40), (255, 255, 255, 0))
    ImageDraw.Draw(image).rectangle([0, 0, 29, 39], fill=(0, 0, 0, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    sources = [
        MergeSource(_text_pdf(tmp_path, "a.pdf", "SENTETIK A"), (0,)),
        MergeSource(_source(tmp_path, buffer.getvalue(), "saydam.png"), (0,)),
    ]
    destination = tmp_path / "hedef.pdf"

    execute_merge(sources, destination, direct=False)

    with _open(destination) as out:
        (embedded,) = out[1].get_images(full=True)
        xref, smask = embedded[0], embedded[1]
        assert smask != 0
        assert pymupdf.Pixmap(out, xref).samples == image.convert("RGB").tobytes()
        assert pymupdf.Pixmap(out, smask).samples == image.getchannel("A").tobytes()


def test_execute_merge_does_not_compress_content_streams(tmp_path: Path, monkeypatch) -> None:
    content, _jpeg = _multi_page_pdf_bytes(compressed=False)
    sources = [
        MergeSource(_source(tmp_path, content), (0, 1)),
        MergeSource(_source(tmp_path, make_half_filled_image_bytes("JPEG"), "on.jpg"), (0,)),
    ]

    def _forbidden(*_args, **_kwargs) -> None:
        raise AssertionError("compress_content_streams çağrılmamalı (§20.5)")

    monkeypatch.setattr(PageObject, "compress_content_streams", _forbidden)

    execute_merge(sources, tmp_path / "hedef.pdf", direct=False)

    with _open(sources[0].path) as src, _open(tmp_path / "hedef.pdf") as out:
        assert _raw_contents(out, 1) == _raw_contents(src, 1)


def test_execute_merge_refuses_direct_document_types_without_reading_sources(
    tmp_path: Path,
) -> None:
    # 07.3.1 / §20.4 / K3: Direkt Belge başka kaynaklardan kurulmaz. Kaynaklar okunsaydı olmayan
    # dosya `FileNotFoundError` verirdi.
    passport, license_ = CATALOG.get(PASSPORT), CATALOG.get(LICENSE)
    assert passport is not None and passport.direct
    assert license_ is not None and not license_.direct
    sources = [MergeSource(tmp_path / "yok-1.jpg", (0,)), MergeSource(tmp_path / "yok-2.jpg", (0,))]
    destination = tmp_path / "hedef.pdf"

    with pytest.raises(DirectDocumentMergeError, match="Direkt Belge"):
        execute_merge(sources, destination, direct=passport.direct)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("count", [0, 1])
def test_execute_merge_requires_at_least_two_sources(tmp_path: Path, count: int) -> None:
    source = MergeSource(_text_pdf(tmp_path, "a.pdf", "SENTETIK A"), (0,))
    destination = tmp_path / "hedef.pdf"

    with pytest.raises(ValueError, match="en az iki kaynak"):
        execute_merge([source] * count, destination, direct=False)

    assert not destination.exists()


@pytest.mark.parametrize("pages", [(), (-1,), (1, 0), (0, 0)])
def test_execute_merge_rejects_invalid_page_selection_before_reading_sources(
    tmp_path: Path, pages: tuple[int, ...]
) -> None:
    sources = [
        MergeSource(tmp_path / "yok-1.pdf", (0,)),
        MergeSource(tmp_path / "yok-2.pdf", pages),
    ]
    destination = tmp_path / "hedef.pdf"

    with pytest.raises(ValueError, match=r"merge sources\[1\]"):
        execute_merge(sources, destination, direct=False)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("content", "message"),
    [
        pytest.param(make_docx_bytes(), "PDF, JPEG ya da PNG değil", id="docx"),
        pytest.param(b"duz metin, taninmayan tur", "PDF, JPEG ya da PNG değil", id="taninmayan"),
        pytest.param(b"%PDF-1.7\ngarbage garbage\n", "açılamadı", id="mupdf-acamiyor"),
        pytest.param(
            b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n",
            "pypdf ile okunamadı",
            id="pypdf-okuyamiyor",
        ),
        pytest.param(make_sized_pdf_bytes([A4], password="gizli"), "parola", id="parola"),
        pytest.param(
            make_half_filled_image_bytes("JPEG")[:40], "sarılamadı: ImageOpenError", id="bozuk-jpeg"
        ),
        pytest.param(
            b"\x89PNG\r\n\x1a\n" + b"x" * 100, "sarılamadı: ImageOpenError", id="bozuk-png"
        ),
        pytest.param(
            make_half_filled_image_bytes("JPEG", orientation=2),
            "sarılamadı: ExifOrientationError",
            id="aynali-exif",
        ),
        pytest.param(
            make_half_filled_image_bytes("PNG", orientation=9),
            "sarılamadı: ExifOrientationError",
            id="gecersiz-exif",
        ),
    ],
)
def test_execute_merge_rejects_unreadable_source(
    tmp_path: Path, content: bytes, message: str
) -> None:
    sources = [
        MergeSource(_text_pdf(tmp_path, "a.pdf", "SENTETIK A"), (0,)),
        MergeSource(_source(tmp_path, content, "kaynak-2"), (0,)),
    ]
    destination = tmp_path / "hedef.pdf"

    with pytest.raises(MergeSourceError, match=message) as raised:
        execute_merge(sources, destination, direct=False)

    assert "merge kaynağı sources[1] " in str(raised.value)
    assert "kaynak-2" not in str(raised.value)
    assert not destination.exists()


@pytest.mark.parametrize(
    ("content", "pages", "message"),
    [
        pytest.param(
            make_half_filled_image_bytes("JPEG"),
            (1,),
            "sayfa 1, kaynak sources[1] 1 sayfa",
            id="jpeg",
        ),
        pytest.param(
            make_text_pdf_bytes(["B0", "B1"]),
            (1, 2),
            "sayfa 2, kaynak sources[1] 2 sayfa",
            id="pdf",
        ),
    ],
)
def test_execute_merge_rejects_page_missing_from_source(
    tmp_path: Path, content: bytes, pages: tuple[int, ...], message: str
) -> None:
    sources = [
        MergeSource(_text_pdf(tmp_path, "a.pdf", "SENTETIK A"), (0,)),
        MergeSource(_source(tmp_path, content, "kaynak-2"), pages),
    ]
    destination = tmp_path / "hedef.pdf"

    with pytest.raises(MergeSourceError, match="kaynakta yok") as raised:
        execute_merge(sources, destination, direct=False)

    assert message in str(raised.value)
    assert not destination.exists()


def test_execute_merge_rejects_page_count_disagreement_between_readers(
    tmp_path: Path, monkeypatch
) -> None:
    content, _jpeg = _multi_page_pdf_bytes()
    sources = [
        MergeSource(_source(tmp_path, content), (1,)),
        MergeSource(_text_pdf(tmp_path, "b.pdf", "SENTETIK B0", "SENTETIK B1"), (0,)),
    ]
    destination = tmp_path / "hedef.pdf"

    class _ShortReader(PdfReader):
        """Bozuk PDF'i MuPDF'ten farklı onaran okuyucu: son sayfayı görmez."""

        @property
        def pages(self):
            return super().pages[:-1]

    monkeypatch.setattr(execute_module, "PdfReader", _ShortReader)

    with pytest.raises(MergeSourceError, match="MuPDF 4, pypdf 3") as raised:
        execute_merge(sources, destination, direct=False)

    assert "sources[0]" in str(raised.value)
    assert not destination.exists()


@pytest.mark.parametrize(
    ("writer", "message"),
    [
        (_ExtraPageWriter, "sayfa sayısı hatası: beklenen 3"),
        (_WrongPageWriter, "metin katmanı hatası: çıktı sayfası 1, kaynak sources[0] sayfası 1"),
        (_GarbageWriter, "çıktısı PDF olarak açılamadı"),
    ],
)
def test_execute_merge_verifies_output_before_publishing(
    tmp_path: Path, monkeypatch, writer, message: str
) -> None:
    sources = [
        MergeSource(_text_pdf(tmp_path, "a.pdf", "SENTETIK A0", "SENTETIK A1"), (0, 1)),
        MergeSource(_text_pdf(tmp_path, "b.pdf", "SENTETIK B0"), (0,)),
    ]
    destination = tmp_path / "hedef.pdf"
    monkeypatch.setattr(execute_module, "PdfWriter", writer)

    with pytest.raises(MergeIntegrityError) as raised:
        execute_merge(sources, destination, direct=False)

    assert message in str(raised.value)
    assert not destination.exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["a.pdf", "b.pdf"]


def test_execute_merge_does_not_overwrite_existing_destination(tmp_path: Path) -> None:
    sources = [
        MergeSource(_text_pdf(tmp_path, "a.pdf", "SENTETIK A"), (0,)),
        MergeSource(_text_pdf(tmp_path, "b.pdf", "SENTETIK B"), (0,)),
    ]
    destination = tmp_path / "hedef.pdf"
    destination.write_bytes(b"onceden var olan icerik")

    with pytest.raises(FileExistsError):
        execute_merge(sources, destination, direct=False)

    assert destination.read_bytes() == b"onceden var olan icerik"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["a.pdf", "b.pdf", "hedef.pdf"]


@pytest.mark.parametrize("back_uploaded_first", [False, True], ids=["on-once", "arka-once"])
def test_s5_planned_merge_item_yields_one_driving_license_pdf(
    session: Session, layout: DataLayout, tmp_path: Path, back_uploaded_first: bool
) -> None:
    # S5 plan → uygulayıcı: aynı partide `on.jpg` ve `arka.jpg` ehliyet (Direkt Belge kapalı)
    # planda tek `merge` öğesidir; uygulayıcı sırayı yükleme sırasından değil öğenin `sources`'undan
    # alır (önce ön yüz). Çıktının yeri, köken kaydı ve `Alinan` kopyası 07.7'nindir.
    front = ("on.jpg", make_half_filled_image_bytes("JPEG", size=(300, 190)))
    back = ("arka.jpg", make_half_filled_image_bytes("JPEG", size=(310, 195)))
    if back_uploaded_first:
        upload = _upload(session, layout, [back, front])
        responses = [_recording(S5_RECORDINGS, 1), _recording(S5_RECORDINGS, 0)]
        provider = _recordings(tmp_path, responses)
    else:
        upload = _upload(session, layout, [front, back])
        provider = RecordingProvider.from_directory(S5_RECORDINGS)
    analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    (item,) = read_plan(create_plan(session, layout, upload, catalog=CATALOG)).items

    entry = CATALOG.get(LICENSE)
    assert entry is not None and not entry.direct
    assert (item.document_type_slug, item.route, item.operation, item.target_format) == (
        LICENSE,
        Route.READY,
        Operation.MERGE,
        "pdf",
    )
    assert item.target_name is not None and item.target_name.endswith("-Driving-License.pdf")
    files = {upload_file.id: upload_file for upload_file in upload.files}
    assert [files[source.file_id].original_name for source in item.sources] == [
        "on.jpg",
        "arka.jpg",
    ]
    destination = tmp_path / "Hazir" / item.target_name

    execute_merge(
        [
            MergeSource(layout.resolve(files[source.file_id].stored_path), source.pages)
            for source in item.sources
        ],
        destination,
        direct=entry.direct,
    )

    assert [path.name for path in destination.parent.iterdir()] == [item.target_name]
    with _open(destination) as out:
        assert out.page_count == 2
        assert [_raw_images(out, index) for index in (0, 1)] == [[front[1]], [back[1]]]
