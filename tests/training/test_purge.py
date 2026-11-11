"""11.9.10 — ham eğitim verisini boşaltma (`app.training.purge`, `python -m app.training
purge-originals`; PLAN.md §D135 d).

Kuru çalıştırma hiçbir ham dosyaya dokunmaz; `--apply` yalnız hedef dizinleri boşaltır
(`done` çalıştırmanın `gelen/` dosyaları, önizlemesi olan örnekler, `cikarilan*`, `_referans`),
haritalar, katalog, şablonlar ve çalışan verisi bayt bayt aynı kalır; önizlemesiz örnek bayraksız
silinmez, işlemdeki çalıştırma atlanır, ikinci koşu 0 dosya siler, olay yazılır. Veri sentetiktir.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    Event,
    ExampleIndexEntry,
    TrainingItem,
    TrainingItemStatus,
    TrainingRun,
    TrainingRunKind,
    TrainingRunStatus,
)
from app.db.session import create_session_factory
from app.events import EventType
from app.storage import DataLayout
from app.storage.examples import index_entry, list_examples, store_example
from app.storage.filetype import FileKind
from app.training import __main__ as cli
from app.training.purge import purge_originals
from tests.fixtures.gen import make_half_filled_image_bytes, make_pdf_bytes

SLUG = "sample_card"
BROKEN = b"\xff\xd8\xff\xe0" + b"\x00" * 64  # JPEG başlığı, çözülemez gövde


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _run(session: Session, layout: DataLayout, status: TrainingRunStatus, files: int) -> int:
    run = TrainingRun(kind=TrainingRunKind.UPLOAD.value, created_by="ik", status=status.value)
    session.add(run)
    session.flush()
    for number in range(files):
        item = TrainingItem(
            run_id=run.id,
            original_name=f"f{number}.jpg",
            status=(
                TrainingItemStatus.UNPLACED if number == 0 else TrainingItemStatus.PLACED
            ).value,
        )
        session.add(item)
        session.flush()
        path = _write(layout.training_staged_path(run.id, item.id, "jpg"), b"x" * (10 + number))
        item.staged_path = layout.relative(path)
    return run.id


@pytest.fixture
def tree(factory: sessionmaker[Session], layout: DataLayout) -> dict[str, object]:
    """Sentetik veri: iki örnek (biri önizlenemez), bitmiş ve işlemdeki çalıştırma, kayıtsız
    `gelen/` dizini, çıkarılanlar, referans ve korunan dosyalar."""
    with factory() as session:
        good = store_example(
            layout,
            SLUG,
            "iyi.jpg",
            make_half_filled_image_bytes("JPEG", (400, 300)),
            FileKind.JPEG,
            session=session,
        ).name
        pdf = store_example(
            layout, SLUG, "belge.pdf", make_pdf_bytes(1), FileKind.PDF, session=session
        ).name
        done = _run(session, layout, TrainingRunStatus.DONE, 3)
        running = _run(session, layout, TrainingRunStatus.RUNNING, 2)
        session.commit()
    _write(layout.type_examples_dir(SLUG) / "bozuk.jpg", BROKEN)
    _write(layout.training_incoming / "kayitsiz" / "a.jpg", b"k")
    _write(layout.training_removed_dir(SLUG) / "cikan.jpg", b"c" * 7)
    _write(layout.training / "cikarilan_kurasyon" / "x" / "y.jpg", b"y" * 5)
    _write(layout.reference_dir / "kaynak" / "r.txt", b"r" * 3)
    protected = [
        _write(layout.training_map_path(done), b"satir,tur\n"),
        _write(layout.catalog_path, b"types: []\n"),
        _write(layout.template_original_path(1), make_pdf_bytes(1)),
        _write(layout.upload_inbox_dir("U1") / "kimlik.pdf", make_pdf_bytes(1)),
        _write(layout.employee_dir("Ad_Soyad_E0001") / "Alinan" / "b.pdf", make_pdf_bytes(1)),
    ]
    return {"good": good, "pdf": pdf, "done": done, "running": running, "protected": protected}


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "_onizlemeler" not in path.parts
    }


def test_dry_run_reports_sections_and_deletes_nothing(
    factory: sessionmaker[Session], layout: DataLayout, tree: dict[str, object]
) -> None:
    before = _snapshot(layout.root)

    report = purge_originals(factory, layout)

    assert _snapshot(layout.root) == before
    counts = {name: (t.files, t.bytes) for name, t in report.planned.items()}
    assert counts["gelen"] == (3, 10 + 11 + 12)
    assert counts["examples"][0] == 2  # bozuk.jpg önizlenemez, sayılmaz
    assert counts["cikarilan"] == (2, 12)
    assert counts["_referans"] == (1, 3)
    assert report.unpreviewable == [f"{SLUG}/bozuk.jpg"]
    assert report.skipped_runs == [tree["running"]]
    assert report.unknown_dirs == ["kayitsiz"]
    assert report.waiting_items == 1
    assert all(t.files == 0 for t in report.deleted.values())
    with factory() as session:
        assert session.scalars(select(Event)).all() == []
        states = session.scalars(select(ExampleIndexEntry.original_state)).all()
        assert sorted(states) == ["present"] * 3  # bozuk.jpg de dizine girdi


def test_apply_empties_only_target_dirs_and_keeps_the_rest_byte_for_byte(
    factory: sessionmaker[Session], layout: DataLayout, tree: dict[str, object]
) -> None:
    protected = {path: path.read_bytes() for path in tree["protected"]}  # type: ignore[union-attr]

    report = purge_originals(factory, layout, apply=True)

    assert {path: path.read_bytes() for path in protected} == protected
    assert not layout.training_incoming_dir(tree["done"]).exists()  # type: ignore[arg-type]
    assert len(list(layout.training_incoming_dir(tree["running"]).iterdir())) == 2  # type: ignore[arg-type]
    assert (layout.training_incoming / "kayitsiz" / "a.jpg").is_file()
    assert layout.training_removed_roots == ()
    assert not layout.reference_dir.exists()
    remaining = sorted(p.name for p in layout.type_examples_dir(SLUG).iterdir())
    assert remaining == ["bozuk.jpg"]
    assert report.deleted["examples"].files == 2 and report.deleted["gelen"].files == 3
    with factory() as session:
        for name in (tree["good"], tree["pdf"]):
            row = index_entry(session, SLUG, name)  # type: ignore[arg-type]
            assert row is not None and row.original_state == "removed"
            for size in ("small", "large"):
                assert layout.preview_path(SLUG, row.preview_key, size).is_file()
        listed = [e.name for e in list_examples(layout, SLUG, session)]
        assert sorted(listed) == sorted(["bozuk.jpg", tree["good"], tree["pdf"]])
        staged = dict(
            session.execute(
                select(TrainingItem.run_id, TrainingItem.staged_path).where(
                    TrainingItem.staged_path.is_not(None)
                )
            )
            .tuples()
            .all()
        )
        assert set(staged) == {tree["running"]}
        (event,) = session.scalars(select(Event)).all()
        assert event.type == EventType.TRAINING_ORIGINALS_PURGED.value
        assert event.data_json["gelen"] == {"files": 3, "bytes": 33}
        assert event.data_json["unpreviewable"] == 1
        assert "bozuk" not in str(event.data_json) and "iyi" not in str(event.data_json)


def test_second_apply_deletes_nothing_and_flag_includes_unpreviewable(
    factory: sessionmaker[Session], layout: DataLayout, tree: dict[str, object]
) -> None:
    purge_originals(factory, layout, apply=True)

    again = purge_originals(factory, layout, apply=True)
    assert sum(t.files for t in again.deleted.values()) == 0

    forced = purge_originals(factory, layout, apply=True, include_unpreviewable=True)
    assert forced.deleted["examples"].files == 1
    assert list(layout.type_examples_dir(SLUG).iterdir()) == []
    with factory() as session:
        row = index_entry(session, SLUG, "bozuk.jpg")
        assert row is not None and row.original_state == "removed"


def test_interrupted_run_is_finished_by_the_next_run(
    factory: sessionmaker[Session], layout: DataLayout, tree: dict[str, object]
) -> None:
    """Dosyaları silinmiş ama `staged_path`'i yazılmamış (kesilen koşu) çalıştırma tamamlanır."""
    done = tree["done"]
    for path in layout.training_incoming_dir(done).iterdir():  # type: ignore[arg-type]
        path.unlink()

    report = purge_originals(factory, layout, apply=True)

    assert report.deleted["gelen"].files == 0
    with factory() as session:
        assert (
            session.scalars(
                select(TrainingItem).where(
                    TrainingItem.run_id == done, TrainingItem.staged_path.is_not(None)
                )
            ).all()
            == []
        )


def test_cli_defaults_to_dry_run(
    factory: sessionmaker[Session],
    layout: DataLayout,
    tree: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, object]] = []

    def fake(_factory: object, _layout: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return purge_originals(factory, layout, apply=bool(kwargs["apply"]))

    monkeypatch.setattr(cli, "purge_originals", fake)
    settings = SimpleNamespace(data_dir=layout.root, database_url="sqlite://")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "create_db_engine", lambda _url: None)
    monkeypatch.setattr(cli, "create_session_factory", lambda _engine: factory)

    assert cli.main(["purge-originals"]) == 0
    assert calls[-1]["apply"] is False and calls[-1]["include_unpreviewable"] is False
    out = capsys.readouterr().out
    assert "kuru çalıştırma" in out and f"{SLUG}/bozuk.jpg" in out
    assert (layout.type_examples_dir(SLUG) / str(tree["good"])).is_file()

    assert cli.main(["purge-originals", "--apply", "--include-unpreviewable"]) == 0
    assert calls[-1] == {
        "apply": True,
        "include_unpreviewable": True,
        "progress": cli._purge_progress,
    }
