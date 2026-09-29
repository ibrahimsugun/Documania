"""11.9.6 — `python -m app.catalog register-examples`: örnek klasörlerinde olup etkin kaydı
olmayan dosyalar SHA-256'larıyla bir kez `legacy` kaydedilir, sayılar yazılır, ikinci koşu hiçbir
şey eklemez.

Veri sentetiktir (`tests/fixtures/gen.py`); gerçek kimlik belgesi yoktur."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import __main__ as cli
from app.catalog.__main__ import main
from app.config import get_settings
from app.db.models import Event, ExampleFileRecord
from app.storage import DataLayout, prepare_data_dir, sha256_bytes
from tests.fixtures.gen import make_pdf_bytes, make_portrait_image_bytes

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def environment(
    engine: Engine, database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[DataLayout]:
    layout = prepare_data_dir(tmp_path / "data")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("DATA_DIR", str(layout.root))
    get_settings.cache_clear()
    yield layout
    get_settings.cache_clear()


def _place(layout: DataLayout, slug: str, name: str, content: bytes) -> None:
    directory = layout.type_examples_dir(slug)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(content)


def _records(session_factory: sessionmaker[Session]) -> list[ExampleFileRecord]:
    with session_factory() as session:
        records = list(session.scalars(select(ExampleFileRecord).order_by(ExampleFileRecord.id)))
        session.expunge_all()
        return records


def test_register_examples_records_three_unregistered_files_and_then_none(
    environment: DataLayout,
    session_factory: sessionmaker[Session],
    capsys: pytest.CaptureFixture[str],
) -> None:
    kayitli = make_portrait_image_bytes("PNG", (200, 300))
    _place(environment, "sample_card", "kayitli.png", kayitli)
    with session_factory() as session:
        session.add(
            ExampleFileRecord(
                type_slug="sample_card",
                name="kayitli.png",
                sha256=sha256_bytes(kayitli),
                method="manual",
                label="verified",
            )
        )
        session.commit()
    unregistered = {
        ("sample_card", "on.png"): make_portrait_image_bytes("PNG", (210, 300)),
        ("sample_card", "arka.pdf"): make_pdf_bytes(1),
        ("other_card", "tek.jpg"): make_portrait_image_bytes("JPEG", (220, 300)),
    }
    for (slug, name), content in unregistered.items():
        _place(environment, slug, name, content)

    assert main(["register-examples"]) == 0

    out, err = capsys.readouterr()
    assert out.strip() == (
        "Örnek klasörleri tarandı (2 tür, 4 dosya): 1 zaten kayıtlı, 3 yeni kaydedildi."
    )
    assert "Kaydediliyor: 3/3" in err
    records = _records(session_factory)
    legacy = {(r.type_slug, r.name): r for r in records if r.method == "legacy"}
    assert set(legacy) == set(unregistered)
    for key, content in unregistered.items():
        assert legacy[key].sha256 == sha256_bytes(content)
        assert legacy[key].label is None
    with session_factory() as session:
        assert session.scalars(select(Event)).all() == []
    # Dosyalara dokunulmaz.
    for (slug, name), content in unregistered.items():
        assert (environment.type_examples_dir(slug) / name).read_bytes() == content

    assert main(["register-examples"]) == 0

    out, err = capsys.readouterr()
    assert out.strip() == (
        "Örnek klasörleri tarandı (2 tür, 4 dosya): 4 zaten kayıtlı, 0 yeni kaydedildi."
    )
    assert err == ""
    assert len(_records(session_factory)) == 4


def test_progress_is_written_every_hundred_files_and_at_the_end(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for done in (1, 99, 100, 101, 200, 250):
        cli._progress(done, 250)

    assert capsys.readouterr().err.splitlines() == [
        "Kaydediliyor: 100/250",
        "Kaydediliyor: 200/250",
        "Kaydediliyor: 250/250",
    ]


def test_a_record_clash_while_registering_writes_nothing_and_fails(
    environment: DataLayout,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _place(environment, "sample_card", "on.png", make_portrait_image_bytes("PNG"))

    def clash(*_args: object, **_kwargs: object) -> None:
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))

    monkeypatch.setattr(cli, "register_examples", clash)

    assert main(["register-examples"]) == 1

    assert "komutu yeniden çalıştırın" in capsys.readouterr().err
    assert _records(session_factory) == []


def test_module_entry_point_runs_register_examples(
    environment: DataLayout, database_url: str, session_factory: sessionmaker[Session]
) -> None:
    _place(environment, "sample_card", "on.png", make_portrait_image_bytes("PNG"))
    env = {
        **os.environ,
        "DATABASE_URL": database_url,
        "DATA_DIR": str(environment.root),
        "PYTHONIOENCODING": "utf-8",  # Windows konsol kod sayfası değil: çıktı UTF-8 okunur
    }

    completed = subprocess.run(
        [sys.executable, "-m", "app.catalog", "register-examples"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "1 yeni kaydedildi" in completed.stdout
    assert [r.name for r in _records(session_factory)] == ["on.png"]
