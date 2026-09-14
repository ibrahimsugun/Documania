"""01.5.1 — Inbox'a değişmez yazma (K10)."""

from pathlib import Path

import pytest

from app.storage.inbox import write_to_inbox
from app.storage.layout import DataLayout


def test_write_to_inbox_writes_under_upload_id(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)

    stored = write_to_inbox(layout, "u_20260101_0001", "pasaport.pdf", b"%PDF-1.4 test")

    expected = tmp_path / "Inbox" / "u_20260101_0001" / "pasaport.pdf"
    assert stored.path == expected
    assert expected.read_bytes() == b"%PDF-1.4 test"


def test_second_write_to_same_name_is_rejected(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    target = tmp_path / "Inbox" / "u_20260101_0001" / "pasaport.pdf"
    write_to_inbox(layout, "u_20260101_0001", "pasaport.pdf", b"orijinal")

    with pytest.raises(FileExistsError):
        write_to_inbox(layout, "u_20260101_0001", "pasaport.pdf", b"degistirilmis")

    assert target.read_bytes() == b"orijinal"


def test_different_uploads_do_not_collide(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)

    first = write_to_inbox(layout, "u_20260101_0001", "a.pdf", b"birinci")
    second = write_to_inbox(layout, "u_20260101_0002", "a.pdf", b"ikinci")

    assert first.path != second.path
    assert first.path.read_bytes() == b"birinci"
    assert second.path.read_bytes() == b"ikinci"
