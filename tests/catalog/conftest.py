"""Katalog testleri: izole SQLite veritabanı ve geçerli kayıt üretici."""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base
from app.db.session import create_db_engine, create_session_factory

type RecordFactory = Callable[..., dict[str, Any]]


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'katalog-test.db').as_posix()}"


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    db_engine = create_db_engine(database_url)
    Base.metadata.create_all(db_engine)
    yield db_engine
    db_engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def make_record() -> RecordFactory:
    """§8.6 biçiminde geçerli bir kayıt; alanlar anahtar kelimeyle değiştirilir."""

    def factory(**overrides: Any) -> dict[str, Any]:
        record: dict[str, Any] = {
            "slug": "sample_card",
            "name": "Sample Card",
            "file_label": "Sample Card",
            "country": "RS",
            "expected_file_types": ["pdf", "jpeg"],
            "expected_pages": {"min": 1, "max": 2},
            "sides": "single",
            "direct": False,
            "analyze": True,
            "required_fields": ["surname", "document_number"],
            "allowed_conversions": ["merge", "wrap_image"],
            "output_format": "pdf",
        }
        record.update(overrides)
        return record

    return factory
