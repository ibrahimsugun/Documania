"""07.1.1 — passthrough işlemi (§20.5): bayt bayt kopya, SHA-256 eşitliği."""

from pathlib import Path

import pytest

from app.pipeline.execute import PassthroughIntegrityError, execute_passthrough
from app.storage import StoredFile, sha256_file
from tests.fixtures.gen import make_pdf_bytes


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
