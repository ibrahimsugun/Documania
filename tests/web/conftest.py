"""Router testleri için: gerçek `DATABASE_URL`/`DATA_DIR` ortam değişkeni gerektirmeyen,
`app.dependency_overrides` ile geçici SQLite + geçici veri dizinine bağlanan `TestClient`.

Uç noktalar oturum ister (10.1.2); `app` fikstürü oturumu açık bir kullanıcıyla gelir
(`SIGNED_IN`). Girişin kendisini sınayan testler bu override'ı kaldırır (`tests/web/test_auth.py`).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db.models import Base
from app.db.session import create_db_engine, create_session_factory, get_session
from app.main import create_app
from app.storage import DataLayout, prepare_data_dir
from app.web.auth import PanelUser, get_current_user
from app.web.routers.uploads import get_layout

SIGNED_IN = PanelUser(id=1, username="test-yonetici", role="admin")


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    db_engine = create_db_engine(f"sqlite:///{(tmp_path / 'uploads-test.db').as_posix()}")
    Base.metadata.create_all(db_engine)
    yield db_engine
    db_engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


@pytest.fixture
def app(session_factory: sessionmaker[Session], layout: DataLayout) -> FastAPI:
    application = create_app()

    def _override_get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    application.dependency_overrides[get_session] = _override_get_session
    application.dependency_overrides[get_layout] = lambda: layout
    # Gerçek DATABASE_URL/.env gerektirmesin diye varsayılan sınırlarla (01.3.1) sabit ayar;
    # sınır testleri kendi override'ını `app.dependency_overrides[get_settings]` ile ekler.
    application.dependency_overrides[get_settings] = lambda: Settings(database_url="sqlite://")
    application.dependency_overrides[get_current_user] = lambda: SIGNED_IN
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()
