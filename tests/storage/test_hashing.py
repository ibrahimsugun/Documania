"""01.4.1 — tekrar yükleme tespiti: aynı SHA-256'nın özgün satırını bulma."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.models import Base, Upload, UploadFile
from app.db.session import create_db_engine, create_session_factory
from app.storage import find_original_by_sha256, sha256_bytes


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine: Engine = create_db_engine(f"sqlite:///{(tmp_path / 'hashing-test.db').as_posix()}")
    Base.metadata.create_all(engine)
    try:
        with create_session_factory(engine)() as db_session:
            yield db_session
    finally:
        engine.dispose()


def _add_file(session: Session, upload_id: str, name: str, sha256: str) -> UploadFile:
    if session.get(Upload, upload_id) is None:
        session.add(Upload(id=upload_id, channel="web"))
        session.flush()
    upload_file = UploadFile(
        upload_id=upload_id,
        original_name=name,
        stored_path=f"Inbox/{upload_id}/{name}",
        sha256=sha256,
        mime="application/octet-stream",
    )
    session.add(upload_file)
    session.flush()
    return upload_file


def test_no_match_returns_none(session: Session) -> None:
    assert find_original_by_sha256(session, sha256_bytes(b"yeni")) is None


def test_finds_earlier_file_with_same_hash(session: Session) -> None:
    digest = sha256_bytes(b"ayni icerik")
    first = _add_file(session, "u_20260914_0001", "a.pdf", digest)

    found = find_original_by_sha256(session, digest)

    assert found is not None
    assert found.id == first.id


def test_different_hash_does_not_match(session: Session) -> None:
    _add_file(session, "u_20260914_0001", "a.pdf", sha256_bytes(b"birinci"))

    assert find_original_by_sha256(session, sha256_bytes(b"ikinci")) is None


def test_chained_duplicate_resolves_to_root(session: Session) -> None:
    """Bir tekrarın kendisi asla başka bir tekrarın "orijinali" sayılmaz — kök satır döner."""
    digest = sha256_bytes(b"zincir")
    root = _add_file(session, "u_20260914_0001", "a.pdf", digest)
    duplicate = _add_file(session, "u_20260914_0002", "b.pdf", digest)
    duplicate.is_duplicate_of = root.id
    session.flush()

    found = find_original_by_sha256(session, digest)

    assert found is not None
    assert found.id == root.id
