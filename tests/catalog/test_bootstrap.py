"""00.6.2, 00.6.3 — açılışta boş katalog tablosunun tohumdan yüklenmesi (`app.catalog.bootstrap`,
tm 136, PLAN.md §D76).

Tablo boşsa veri dizinindeki `catalog.yaml` yüklenir; doluysa hiçbir şeye dokunulmaz (panel
düzenlemesi dosyadaki eski hâlle ezilmez). Şemasız veritabanı, geçersiz dosya ve eşzamanlı açılış
süreci durdurmaz.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import (
    Catalog,
    export_catalog,
    import_catalog,
    load_catalog_on_startup,
    load_seed_catalog,
    seed_empty_catalog,
    set_type_active,
    validate_catalog,
    write_catalog_file,
)
from app.catalog import bootstrap as bootstrap_module
from app.catalog.yaml_io import install_seed_catalog, seed_catalog_bytes
from app.db.models import KnownDocumentType
from app.db.session import create_db_engine, create_session_factory
from app.storage import DataLayout, prepare_data_dir
from tests.catalog.conftest import RecordFactory

LOGGER = "app.catalog.bootstrap"


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


def _slugs(session_factory: sessionmaker[Session]) -> set[str]:
    with session_factory() as session:
        return set(session.scalars(select(KnownDocumentType.slug)))


def _count(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(KnownDocumentType)) or 0


def _seed_plus(record: dict[str, Any]) -> Catalog:
    return validate_catalog([*(e.model_dump(mode="json") for e in load_seed_catalog()), record])


def test_an_empty_catalog_table_is_loaded_from_the_catalog_file(
    session_factory: sessionmaker[Session], layout: DataLayout, caplog: pytest.LogCaptureFixture
) -> None:
    install_seed_catalog(layout)

    with caplog.at_level(logging.INFO, logger=LOGGER):
        result = seed_empty_catalog(session_factory, layout.catalog_path)

    seed = load_seed_catalog()
    assert result is not None
    assert set(result.created) == set(seed.slugs())
    assert (result.updated, result.unchanged, result.not_in_catalog) == ((), (), ())
    with session_factory() as session:
        assert export_catalog(session) == seed  # dosyadaki katalog birebir
    assert f"Başlangıç kataloğu veritabanına yüklendi ({len(seed)} tür)" in caplog.text


def test_the_catalog_file_in_the_data_dir_is_what_gets_loaded(
    session_factory: sessionmaker[Session], layout: DataLayout, make_record: RecordFactory
) -> None:
    # Kurulumu yapan dosyayı ilk açılıştan önce kendi kataloğuyla değiştirmişse o yüklenir.
    write_catalog_file(layout.catalog_path, _seed_plus(make_record()))

    load = seed_empty_catalog(session_factory, layout.catalog_path)

    assert load is not None
    assert _slugs(session_factory) == set(load_seed_catalog().slugs()) | {"sample_card"}


def test_a_filled_catalog_table_is_left_untouched(
    session_factory: sessionmaker[Session], layout: DataLayout, make_record: RecordFactory
) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        # panelde pasifleştirildi (11.1.1)
        set_type_active(session, "work_permit", False, actor="ik")
        session.commit()
    # Dosya veritabanından farklı: yeni tür var ve work_permit etkin.
    write_catalog_file(layout.catalog_path, _seed_plus(make_record()))

    assert seed_empty_catalog(session_factory, layout.catalog_path) is None

    assert "sample_card" not in _slugs(session_factory)
    with session_factory() as session:
        assert session.get_one(KnownDocumentType, "work_permit").active is False


def test_starting_twice_loads_the_catalog_once(
    database_url: str, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    first = load_catalog_on_startup(database_url, layout)
    second = load_catalog_on_startup(database_url, layout)

    assert first is not None and len(first.created) == len(load_seed_catalog())
    assert second is None
    assert _count(session_factory) == len(load_seed_catalog())
    assert layout.catalog_path.read_bytes() == seed_catalog_bytes()


def test_an_invalid_catalog_file_loads_nothing_and_does_not_stop_startup(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    make_record: RecordFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # 00.6.1: `direct: true` türde dönüşüm listesi dolu → dosya bütün olarak reddedilir, yanındaki
    # geçerli kayıt da yüklenmez.
    records = [make_record(slug="good_card"), make_record(slug="bad_card", direct=True)]
    layout.catalog_path.write_text(yaml.safe_dump(records), encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger=LOGGER):
        assert seed_empty_catalog(session_factory, layout.catalog_path) is None

    assert _count(session_factory) == 0
    assert str(layout.catalog_path) in caplog.text
    assert "bad_card" in caplog.text
    assert "python -m app.catalog import" in caplog.text


def test_a_database_without_schema_is_reported_not_raised(
    layout: DataLayout, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert load_catalog_on_startup("sqlite://", layout) is None

    assert "alembic upgrade head" in caplog.text
    assert layout.catalog_path.read_bytes() == seed_catalog_bytes()  # tohum dosyası yine yazılır


def test_two_processes_starting_together_load_the_catalog_once(
    database_url: str, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    # Panel, işçi ve bot aynı anda açılır (ikisi de yalnız `migrate`'i bekler). SQLite'ta `BEGIN
    # IMMEDIATE` ikinci açılışı sıraya koyar; o da tabloyu dolu bulur.
    start = threading.Barrier(2)
    results: list[object] = []

    def open_process() -> None:
        start.wait()
        results.append(load_catalog_on_startup(database_url, layout))

    threads = [threading.Thread(target=open_process) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert len(results) == 2
    assert sum(result is not None for result in results) == 1
    assert _count(session_factory) == len(load_seed_catalog())


def test_a_catalog_committed_meanwhile_by_another_process_is_not_an_error(
    session_factory: sessionmaker[Session],
    database_url: str,
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # PostgreSQL yolu: iki süreç tabloyu boş görür, önce commit eden kazanır, ötekinin eklemesi
    # birincil anahtar çakışmasıyla düşer.
    install_seed_catalog(layout)

    def racing_import(session: Session, catalog: Catalog) -> Any:
        session.rollback()  # bu sürecin işlemi henüz yazmadı; kilit öteki sürece geçer
        other = create_db_engine(database_url)
        try:
            with create_session_factory(other)() as rival:
                import_catalog(rival, catalog)
                rival.commit()
        finally:
            other.dispose()
        raise IntegrityError("INSERT INTO known_document_types", {}, Exception("unique"))

    monkeypatch.setattr(bootstrap_module, "import_catalog", racing_import)

    with caplog.at_level(logging.INFO, logger=LOGGER):
        assert seed_empty_catalog(session_factory, layout.catalog_path) is None

    assert _count(session_factory) == len(load_seed_catalog())
    assert "başka bir süreç" in caplog.text


def test_an_integrity_error_without_a_rival_process_is_raised(
    session_factory: sessionmaker[Session], layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_seed_catalog(layout)

    def broken_import(session: Session, catalog: Catalog) -> Any:
        raise IntegrityError("INSERT INTO known_document_types", {}, Exception("check"))

    monkeypatch.setattr(bootstrap_module, "import_catalog", broken_import)

    with pytest.raises(IntegrityError):
        seed_empty_catalog(session_factory, layout.catalog_path)
    assert _count(session_factory) == 0
