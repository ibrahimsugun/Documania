"""00.6.2, 00.6.3 — taze kurulumda katalog tablosu açılışta dolar (tm 136, PLAN.md §D76).

Kurulum README'deki gibidir: temiz veritabanında `alembic upgrade head`, ardından panel
(`create_app()`) ya da işçi (`python -m app.worker`) açılır. Katalog için elle adım
(`python -m app.catalog import`) YOKTUR. Önceden açılış yalnız `catalog.yaml`'ı yazıyordu;
analiz kataloğu tablodan okuduğu için taze kurulumdaki her belge Unknown'a düşüyordu.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.catalog import load_seed_catalog
from app.config import get_settings
from app.db.models import KnownDocumentType
from app.db.session import create_db_engine, create_session_factory
from app.main import create_app
from app.worker import __main__ as worker_entrypoint

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def fresh_install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[str]:
    """Göçleri koşulmuş boş veritabanı ve boş veri dizini; ayarlar ortam değişkenlerinden."""
    database_url = f"sqlite:///{(tmp_path / 'belgeee.db').as_posix()}"
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    monkeypatch.chdir(tmp_path)  # depo kökündeki `.env` okunmasın
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "veri"))
    get_settings.cache_clear()
    yield database_url
    get_settings.cache_clear()


def _slugs(database_url: str) -> set[str]:
    engine = create_db_engine(database_url)
    try:
        with create_session_factory(engine)() as session:
            return set(session.scalars(select(KnownDocumentType.slug)))
    finally:
        engine.dispose()


def test_panel_startup_fills_the_catalog_table_of_a_fresh_install(
    fresh_install: str, tmp_path: Path
) -> None:
    assert _slugs(fresh_install) == set()

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200

    assert _slugs(fresh_install) == set(load_seed_catalog().slugs())
    assert (tmp_path / "veri" / "KnownDocuments" / "catalog.yaml").is_file()


def test_worker_startup_fills_the_catalog_before_the_queue_starts(
    fresh_install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # İşçi paneli beklemez; ilk partiyi işlemeye başladığında katalog tabloda olmalıdır.
    catalog_at_build: list[set[str]] = []

    class StoppedWorker:
        def start(self, *, paused: bool = False) -> None:
            pass

        def resume(self) -> None:
            pass

        def request_stop(self) -> None:
            pass

        def wait(self) -> bool:
            return True

        def stop(self, timeout: float = 5.0) -> None:
            pass

    def build(_settings: Any, _layout: Any) -> StoppedWorker:
        catalog_at_build.append(_slugs(fresh_install))
        return StoppedWorker()

    monkeypatch.setattr(worker_entrypoint, "create_worker", build)
    monkeypatch.setattr(worker_entrypoint.signal, "signal", lambda _signum, _handler: None)

    assert worker_entrypoint.main() == 0

    assert catalog_at_build == [set(load_seed_catalog().slugs())]
