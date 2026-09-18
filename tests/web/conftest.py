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
from starlette.requests import Request

from app.config import Settings, get_settings
from app.db.models import Base, User
from app.db.session import create_db_engine, create_session_factory, get_session
from app.main import create_app
from app.storage import DataLayout, prepare_data_dir
from app.web.auth import SESSION_COOKIE, PanelUser, get_current_user
from app.web.confirm import Operation, issue_confirmation
from app.web.routers.uploads import get_layout

SIGNED_IN = PanelUser(id=1, username="test-yonetici", role="admin")
# Onay belirteci oturum çerezine bağlıdır (10.8.1); oturum bağımlılığı testte geçersiz kılındığı
# için çerez elle konur.
SESSION = "oturum-bir"


def issue_token(
    session_factory: sessionmaker[Session],
    operation: Operation,
    target: str,
    *,
    cookie: str = SESSION,
    user: PanelUser = SIGNED_IN,
) -> str:
    """Hazırlık adımını atlayarak `operation` + `target` için tek kullanımlık onay belirteci üretir
    (başka işlemin ya da hazırlığı reddedilen hedefin belirtecini sınamak için)."""
    request = Request(
        {"type": "http", "headers": [(b"cookie", f"{SESSION_COOKIE}={cookie}".encode())]}
    )
    with session_factory() as session:
        issued = issue_confirmation(session, request, user, operation, target)
        session.commit()
    return issued.token


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
    # Belge açma/indirme erişim logu (10.9.2) `users` satırına bağlanır: oturumdaki test kullanıcısı
    # veritabanında da vardır.
    with session_factory() as session:
        session.add(
            User(
                id=SIGNED_IN.id,
                username=SIGNED_IN.username,
                password_hash="test-parolasi-yok",
                role=SIGNED_IN.role,
            )
        )
        session.commit()
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
