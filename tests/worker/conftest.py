"""İşçi kuyruğu testleri için izole veritabanı ve veri dizini (CONVENTIONS §1.4).

Veritabanı geçici bir SQLite dosyasıdır: "yeniden başlatma" testleri aynı dosyaya yeni bir motorla
bağlanır. PostgreSQL testleri yalnız `BELGEEE_TEST_POSTGRES_URL` tanımlıysa koşar
(`tests.db.conftest.postgres_url`).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.db.models import Base
from app.db.session import create_db_engine, create_session_factory
from app.storage import DataLayout, prepare_data_dir
from tests.db.conftest import postgres_url  # noqa: F401 — PostgreSQL fikstürü burada da geçerli


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'worker-test.db').as_posix()}"


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
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db_session:
        yield db_session


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


@pytest.fixture
def catalog(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()
