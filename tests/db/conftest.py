"""Veritabanı testleri için izole motorlar.

Her test kendi geçici SQLite dosyasını kullanır (CONVENTIONS §1.4). PostgreSQL testleri
yalnız `BELGEEE_TEST_POSTGRES_URL` tanımlıysa koşar ve her test kendi şemasını açar;
değişken boş bir, atılabilir veritabanını göstermelidir (ör. geçici `postgres:16` kapsayıcısı).
"""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.orm import Session

from app.db.models import Base
from app.db.session import create_db_engine, create_session_factory

POSTGRES_URL_ENV = "BELGEEE_TEST_POSTGRES_URL"


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'belgeee-test.db').as_posix()}"


@pytest.fixture
def engine(sqlite_url: str) -> Iterator[Engine]:
    db_engine = create_db_engine(sqlite_url)
    Base.metadata.create_all(db_engine)
    yield db_engine
    db_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with create_session_factory(engine)() as db_session:
        yield db_session


@pytest.fixture
def postgres_url() -> str:
    """Boş, izole bir şemayı gösteren PostgreSQL bağlantı dizesi."""
    base_url = os.environ.get(POSTGRES_URL_ENV)
    if not base_url:
        pytest.skip(f"{POSTGRES_URL_ENV} tanımlı değil; PostgreSQL testi atlandı")
    schema = f"test_{uuid.uuid4().hex[:12]}"
    admin_engine = create_engine(base_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    finally:
        admin_engine.dispose()
    url = make_url(base_url).update_query_dict({"options": f"-csearch_path={schema}"})
    return url.render_as_string(hide_password=False)
