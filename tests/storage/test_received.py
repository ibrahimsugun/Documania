"""07.7.2 — Alinan kopyası: kaynak çalışanın `Alinan/` klasörüne kopyalanır, aynı hash tekrar
kopyalanmaz (K10).

İçerikler sentetik bayt dizileridir; gerçek belge kullanılmaz (CONVENTIONS §6).
"""

from pathlib import Path

import pytest

from app.storage import (
    ContentMismatchError,
    DataLayout,
    ReceivedCopy,
    copy_to_received,
    prepare_data_dir,
    sha256_bytes,
    sha256_file,
)

FOLDER = "Test_Ornekova_E0001"


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


def _inbox_file(layout: DataLayout, name: str, content: bytes, upload_id: str = "u1") -> Path:
    path = layout.upload_inbox_dir(upload_id) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _copy(layout: DataLayout, source: Path) -> ReceivedCopy:
    return copy_to_received(layout, FOLDER, source, sha256=sha256_file(source))


def _received(layout: DataLayout) -> list[str]:
    return sorted(path.name for path in layout.received_dir(FOLDER).iterdir())


def test_source_is_copied_byte_identically_under_its_inbox_name(layout: DataLayout) -> None:
    content = b"%PDF-1.7 sentetik kaynak"
    source = _inbox_file(layout, "tarama 01.pdf", content)

    copy = _copy(layout, source)

    assert copy.copied
    assert copy.stored.path == layout.received_dir(FOLDER) / "tarama 01.pdf"
    assert copy.stored.path.read_bytes() == content
    assert (copy.stored.sha256, copy.stored.size) == (sha256_bytes(content), len(content))
    assert source.read_bytes() == content  # orijinal Inbox'ta yerinde (K10)


def test_same_hash_is_not_copied_again(layout: DataLayout) -> None:
    source = _inbox_file(layout, "tarama.pdf", b"ayni icerik")
    first = _copy(layout, source)

    second = _copy(layout, source)

    assert not second.copied
    assert second.stored == first.stored
    assert _received(layout) == ["tarama.pdf"]


def test_same_content_under_another_name_is_not_copied_again(layout: DataLayout) -> None:
    # Aynı içerik başka bir partide başka adla yeniden gelmiş: hash aynı, kopya yazılmaz.
    _copy(layout, _inbox_file(layout, "ilk-ad.pdf", b"ayni icerik"))
    again = _inbox_file(layout, "baska-ad.pdf", b"ayni icerik", upload_id="u2")

    copy = _copy(layout, again)

    assert not copy.copied
    assert copy.stored.path == layout.received_dir(FOLDER) / "ilk-ad.pdf"
    assert _received(layout) == ["ilk-ad.pdf"]


def test_other_content_with_same_name_gets_a_suffix(layout: DataLayout) -> None:
    _copy(layout, _inbox_file(layout, "tarama.pdf", b"birinci icerik"))
    other = _inbox_file(layout, "tarama.pdf", b"ikinci icerik!", upload_id="u2")

    copy = _copy(layout, other)

    assert copy.copied
    assert copy.stored.path.name == "tarama-2.pdf"
    assert (layout.received_dir(FOLDER) / "tarama.pdf").read_bytes() == b"birinci icerik"
    assert copy.stored.path.read_bytes() == b"ikinci icerik!"


def test_same_size_with_other_content_is_copied(layout: DataLayout) -> None:
    _copy(layout, _inbox_file(layout, "a.pdf", b"AAAA"))

    copy = _copy(layout, _inbox_file(layout, "b.pdf", b"BBBB"))

    assert copy.copied
    assert _received(layout) == ["a.pdf", "b.pdf"]


def test_unpublished_partial_write_does_not_count_as_a_copy(layout: DataLayout) -> None:
    received = layout.received_dir(FOLDER)
    received.mkdir(parents=True)
    partial = received / f".belgeee-{'0a' * 16}.part"
    partial.write_bytes(b"ayni icerik")

    copy = _copy(layout, _inbox_file(layout, "tarama.pdf", b"ayni icerik"))

    assert copy.copied
    assert copy.stored.path.name == "tarama.pdf"


def test_subdirectory_does_not_count_as_a_copy(layout: DataLayout) -> None:
    (layout.received_dir(FOLDER) / "alt").mkdir(parents=True)

    copy = _copy(layout, _inbox_file(layout, "tarama.pdf", b"icerik"))

    assert copy.copied
    assert _received(layout) == ["alt", "tarama.pdf"]


def test_copy_not_matching_the_recorded_hash_is_not_published(layout: DataLayout) -> None:
    source = _inbox_file(layout, "tarama.pdf", b"degismis icerik")

    with pytest.raises(ContentMismatchError):
        copy_to_received(layout, FOLDER, source, sha256=sha256_bytes(b"yuklenen icerik"))

    assert _received(layout) == []
