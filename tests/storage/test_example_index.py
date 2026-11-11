"""11.9.10 — kalıcı örnek dizini ve kalıcı önizleme (`app.storage.examples`,
`app.storage.previews`; PLAN.md §D135 a, b, c).

Ham dosya silindikten sonra örnek dizin kaydı ve kalıcı önizlemesiyle yaşar: liste aynı ad ve
sırayla gösterir, önizleme dizindeki anahtarla bulunur, aynı içerik tekrar sayılır, taşıma ve
çıkarma dizin satırını ve önizlemeleri taşır. Ham dosya varken davranış değişmez. Veri sentetiktir.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import Base, ExampleIndexEntry
from app.db.session import create_db_engine, create_session_factory
from app.storage import DataLayout, prepare_data_dir, sha256_bytes
from app.storage.examples import (
    archive_indexed_example,
    example_hashes,
    find_example,
    index_entry,
    list_examples,
    relocate_indexed_example,
    store_example,
    sync_example_index,
)
from app.storage.filetype import FileKind
from app.storage.previews import ensure_preview, stored_large_preview, warm_previews
from tests.fixtures.gen import make_half_filled_image_bytes, make_pdf_bytes

SLUG = "sample_card"
OTHER = "other_card"


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    db_engine = create_db_engine(f"sqlite:///{(tmp_path / 'index.db').as_posix()}")
    Base.metadata.create_all(db_engine)
    yield db_engine
    db_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with create_session_factory(engine)() as db_session:
        yield db_session


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


def _jpeg(width: int = 400) -> bytes:
    return make_half_filled_image_bytes("JPEG", (width, 300))


def _store(session: Session, layout: DataLayout, name: str, content: bytes, kind: FileKind) -> str:
    return store_example(layout, SLUG, name, content, kind, session=session).name


def _purge(session: Session, layout: DataLayout, slug: str, name: str) -> None:
    """Ham dosyayı siler ve dizini eşitler (boşaltma komutunun yaptığı, tm 202)."""
    (layout.type_examples_dir(slug) / name).unlink()
    sync_example_index(session, layout)


def test_store_records_the_example_with_a_sha_based_preview_key(
    session: Session, layout: DataLayout
) -> None:
    content = make_pdf_bytes(2)
    name = _store(session, layout, "pasaport.pdf", content, FileKind.PDF)

    row = index_entry(session, SLUG, name)

    assert row is not None
    assert (row.size, row.sha256, row.file_kind, row.page_count) == (
        len(content),
        sha256_bytes(content),
        "pdf",
        2,
    )
    assert row.preview_key == sha256_bytes(content)[:20]
    assert (row.original_state, row.removed_at) == ("present", None)


def test_list_keeps_name_and_order_after_the_original_is_removed(
    session: Session, layout: DataLayout
) -> None:
    for name in ("b.jpg", "a.jpg", "c.jpg"):
        _store(session, layout, name, _jpeg(300 + ord(name[0])), FileKind.JPEG)
    before = list_examples(layout, SLUG, session)

    _purge(session, layout, SLUG, "b.jpg")
    after = list_examples(layout, SLUG, session)

    assert [e.name for e in after] == [e.name for e in before] == ["a.jpg", "b.jpg", "c.jpg"]
    assert [e.present for e in after] == [True, False, True]
    assert after[1].size == before[1].size and after[1].preview_key == before[1].preview_key
    assert [e.name for e in list_examples(layout, SLUG)] == ["a.jpg", "c.jpg"]  # oturumsuz: disk
    row = index_entry(session, SLUG, "b.jpg")
    assert row is not None and row.original_state == "removed" and row.removed_at is not None


def test_sync_indexes_unregistered_files_and_is_idempotent(
    session: Session, layout: DataLayout
) -> None:
    directory = layout.type_examples_dir(SLUG)
    directory.mkdir(parents=True)
    (directory / "elle.png").write_bytes(make_half_filled_image_bytes("PNG", (200, 100)))

    first = sync_example_index(session, layout)
    second = sync_example_index(session, layout)

    assert (first.present, first.indexed, first.removed) == (1, 1, 0)
    assert (second.indexed, second.removed) == (0, 0)
    row = index_entry(session, SLUG, "elle.png")
    assert row is not None and row.file_kind == "png" and row.page_count == 1


def test_removed_example_is_still_a_duplicate_and_its_name_stays_taken(
    session: Session, layout: DataLayout
) -> None:
    content = _jpeg()
    name = _store(session, layout, "kart.jpg", content, FileKind.JPEG)
    _purge(session, layout, SLUG, name)

    again = store_example(layout, SLUG, "yeni.jpg", content, FileKind.JPEG, session=session)
    other = store_example(layout, SLUG, "kart.jpg", _jpeg(500), FileKind.JPEG, session=session)

    assert again.duplicate and again.name == name
    assert find_example(layout, SLUG, sha256_bytes(content), session=session) is not None
    assert example_hashes(layout, SLUG, session)[sha256_bytes(content)] == name
    assert other.name == "kart-2.jpg"  # silinmiş örneğin adı dolu sayılır


def test_preview_survives_the_removal_and_missing_one_is_a_placeholder(
    session: Session, layout: DataLayout
) -> None:
    kept = _store(session, layout, "kalan.jpg", _jpeg(), FileKind.JPEG)
    lost = _store(session, layout, "kayip.jpg", _jpeg(600), FileKind.JPEG)
    large = ensure_preview(layout, SLUG, kept, "large", session=session)
    assert large is not None and large.path is not None
    assert large.path.parent == layout.known_documents / "_onizlemeler" / SLUG

    _purge(session, layout, SLUG, kept)
    _purge(session, layout, SLUG, lost)

    again = ensure_preview(layout, SLUG, kept, "large", session=session)
    assert again == large
    row = index_entry(session, SLUG, kept)
    assert row is not None
    assert stored_large_preview(layout, SLUG, row.preview_key) == large.path
    missing = ensure_preview(layout, SLUG, lost, "small", session=session)
    assert missing is not None and missing.path is None
    assert ensure_preview(layout, SLUG, "yok.jpg", "small", session=session) is None


def test_relocating_a_removed_example_moves_its_row_and_previews(
    session: Session, layout: DataLayout
) -> None:
    content = _jpeg()
    name = _store(session, layout, "kart.jpg", content, FileKind.JPEG)
    for size in ("small", "large"):
        ensure_preview(layout, SLUG, name, size, session=session)
    store_example(layout, OTHER, "kart.jpg", _jpeg(700), FileKind.JPEG, session=session)
    _purge(session, layout, SLUG, name)

    moved = relocate_indexed_example(
        session, layout, SLUG, name, OTHER, expected_sha256=sha256_bytes(content)
    )

    assert moved.stored is None and moved.name == "kart-2.jpg"
    assert list_examples(layout, SLUG, session) == []
    listed = {e.name: e for e in list_examples(layout, OTHER, session)}
    assert not listed["kart-2.jpg"].present
    key = sha256_bytes(content)[:20]
    assert sorted(p.name for p in layout.preview_dir(OTHER).iterdir()) == [
        f"{key}-large.jpg",
        f"{key}-small.jpg",
    ]
    assert not any(layout.preview_dir(SLUG).iterdir())


def test_archiving_a_removed_example_keeps_its_preview_out_of_the_list(
    session: Session, layout: DataLayout
) -> None:
    content = _jpeg()
    name = _store(session, layout, "kart.jpg", content, FileKind.JPEG)
    ensure_preview(layout, SLUG, name, "small", session=session)
    _purge(session, layout, SLUG, name)

    stored = archive_indexed_example(
        session, layout, SLUG, name, expected_sha256=sha256_bytes(content)
    )

    assert stored is None
    assert list_examples(layout, SLUG, session) == []
    row = session.scalar(select(ExampleIndexEntry).where(ExampleIndexEntry.name == name))
    assert row is not None and row.archived_at is not None
    archived = layout.archived_preview_dir(SLUG) / f"{row.preview_key}-small.jpg"
    assert archived.is_file()


def test_an_original_that_vanished_unmarked_is_not_moved(
    session: Session, layout: DataLayout
) -> None:
    content = _jpeg()
    name = _store(session, layout, "kart.jpg", content, FileKind.JPEG)
    (layout.type_examples_dir(SLUG) / name).unlink()  # dizin eşitlenmedi: `present` kaldı

    with pytest.raises(FileNotFoundError):
        relocate_indexed_example(
            session, layout, SLUG, name, OTHER, expected_sha256=sha256_bytes(content)
        )


def test_warm_previews_with_the_index_counts_a_removed_example_without_preview(
    session: Session, layout: DataLayout
) -> None:
    _store(session, layout, "a.jpg", _jpeg(), FileKind.JPEG)
    lost = _store(session, layout, "b.jpg", _jpeg(500), FileKind.JPEG)
    _purge(session, layout, SLUG, lost)
    session.commit()  # ısıtma okumadan sonra işlemi bırakır: bekleyen yazma olmamalı

    first = warm_previews(layout, session)
    second = warm_previews(layout, session)

    assert first == {"created": 2, "existing": 0, "failed": 2}
    assert second == {"created": 0, "existing": 2, "failed": 2}
