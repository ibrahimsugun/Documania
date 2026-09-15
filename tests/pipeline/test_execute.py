"""Uygulayıcı işlemleri (§20.5).

07.1.1 — passthrough: bayt bayt kopya, SHA-256 eşitliği.
07.2.1 — extract: sayfa nesnesi kopyası, render yok, metin katmanı korunur (S7).
"""

from io import BytesIO
from pathlib import Path

import pymupdf
import pytest
from pypdf import PageObject, PdfReader, PdfWriter

import app.pipeline.execute as execute_module
from app.pipeline.execute import (
    ExtractIntegrityError,
    ExtractSourceError,
    PassthroughIntegrityError,
    execute_extract,
    execute_passthrough,
)
from app.storage import StoredFile, sha256_file
from tests.fixtures.gen import (
    A4,
    make_docx_bytes,
    make_half_filled_image_bytes,
    make_pdf_bytes,
    make_sized_pdf_bytes,
    make_text_pdf_bytes,
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
