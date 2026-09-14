"""00.6.3 — `python -m app.catalog import|export` komutu."""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.__main__ import main
from app.catalog.yaml_io import seed_catalog_bytes
from app.config import get_settings
from app.db.models import KnownDocumentType
from app.storage import DataLayout

REPO_ROOT = Path(__file__).resolve().parents[2]

INVALID_DIRECT = """\
- slug: broken_passport
  name: Broken Passport
  file_label: Passport
  expected_file_types: [jpeg]
  sides: single
  direct: true
  analyze: true
  required_fields: [document_number]
  allowed_conversions: [wrap_image]
  output_format: pdf
"""


@pytest.fixture
def environment(
    engine: Engine, database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[DataLayout]:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    get_settings.cache_clear()
    yield DataLayout(data_dir)
    get_settings.cache_clear()


def _type_count(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(KnownDocumentType)) or 0


def test_import_without_file_installs_seed_and_loads_it(
    environment: DataLayout,
    session_factory: sessionmaker[Session],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["import"]) == 0

    assert environment.catalog_path.read_bytes() == seed_catalog_bytes()
    assert _type_count(session_factory) == 8
    out = capsys.readouterr().out
    assert "Başlangıç tohumu yazıldı" in out
    assert "Katalog yüklendi (8 tür): 8 yeni, 0 güncellendi, 0 aynı." in out

    assert main(["import"]) == 0
    assert "0 yeni, 0 güncellendi, 8 aynı." in capsys.readouterr().out


def test_export_writes_database_catalog_to_file(
    environment: DataLayout,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["import"]) == 0
    target = tmp_path / "disari" / "catalog.yaml"

    assert main(["export", "--file", str(target)]) == 0

    assert target.read_bytes() == seed_catalog_bytes()
    assert f"Katalog dışa aktarıldı (8 tür): {target}" in capsys.readouterr().out


def test_export_without_file_regenerates_data_dir_catalog(environment: DataLayout) -> None:
    assert main(["import"]) == 0
    environment.catalog_path.write_bytes(b"[]\n")

    assert main(["export"]) == 0

    assert environment.catalog_path.read_bytes() == seed_catalog_bytes()


def test_import_reports_types_missing_from_file(
    environment: DataLayout, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["import"]) == 0
    empty = tmp_path / "bos.yaml"
    empty.write_text("[]\n", encoding="utf-8")

    assert main(["import", "--file", str(empty)]) == 0

    assert "Dosyada olmayan, dokunulmayan türler: attachment, profile_picture" in (
        capsys.readouterr().out
    )


def test_invalid_catalog_is_rejected_and_nothing_loaded(
    environment: DataLayout,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(INVALID_DIRECT, encoding="utf-8")

    assert main(["import", "--file", str(bad)]) == 1

    err = capsys.readouterr().err
    assert "Katalog reddedildi" in err
    assert "kayıt #1 (broken_passport)" in err
    assert _type_count(session_factory) == 0


def test_missing_catalog_file_fails_clearly(
    environment: DataLayout, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "yok.yaml"

    assert main(["import", "--file", str(missing)]) == 1

    assert f"Katalog dosyası bulunamadı: {missing}" in capsys.readouterr().err
    assert not environment.catalog_path.exists()  # --file verildiyse tohum kurulmaz


def test_command_is_required(environment: DataLayout) -> None:
    with pytest.raises(SystemExit) as caught:
        main([])

    assert caught.value.code == 2


def test_module_entry_point_runs(
    engine: Engine, database_url: str, tmp_path: Path, session_factory: sessionmaker[Session]
) -> None:
    env = {
        **os.environ,
        "DATABASE_URL": database_url,
        "DATA_DIR": str(tmp_path / "data"),
        "PYTHONIOENCODING": "utf-8",
    }

    result = subprocess.run(
        [sys.executable, "-m", "app.catalog", "import"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert _type_count(session_factory) == 8
