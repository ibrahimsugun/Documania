"""Boru hattı testleri için izole veritabanı ve veri dizini (CONVENTIONS §1.4)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.models import Base
from app.db.session import create_db_engine, create_session_factory
from app.storage import DataLayout, prepare_data_dir


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    db_engine = create_db_engine(f"sqlite:///{(tmp_path / 'pipeline-test.db').as_posix()}")
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
