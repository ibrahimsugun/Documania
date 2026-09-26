"""Eğitim modu testleri: izole SQLite, geçici veri dizini, tohum katalog ∪ önerilen türler.

Veri sentetiktir (`tests/fixtures/gen.py`); gerçek kimlik belgesi yoktur (CONVENTIONS §6).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.catalog import load_seed_catalog
from app.db.models import Base
from app.db.session import create_db_engine, create_session_factory
from app.storage import DataLayout, prepare_data_dir
from app.training import KnownTypes, build_known_types


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    db_engine = create_db_engine(f"sqlite:///{(tmp_path / 'training-test.db').as_posix()}")
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


@pytest.fixture
def known() -> KnownTypes:
    return build_known_types(load_seed_catalog())
