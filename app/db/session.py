"""Veritabanı motoru ve oturum fabrikası (PRD 00.3.1–00.3.3).

Bağlantı dizesi yalnız `app.config` üzerinden gelir (`DATABASE_URL`); geliştirmede SQLite,
üretimde PostgreSQL aynı kodla çalışır (NFR-05).

SQLite için motor şunları ayarlar:

- `PRAGMA foreign_keys=ON` — SQLite yabancı anahtarları varsayılan olarak denetlemez.
- `busy_timeout` — kilitli veritabanında hemen hata yerine bekler.
- `BEGIN IMMEDIATE` — her işlem yazma kilidini baştan alır. Okuyup sonra yazan eşzamanlı
  işlemler böylece sıraya girer; aksi halde SQLite kilit yükseltmesinde beklemeden
  "database is locked" verir. Çalışan numarası üretici bu garantiye dayanır. Sonucu: açık
  kalan bir oturum diğer yazarları bekletir — oturumu işiniz bitince kapatın.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

SQLITE_BUSY_TIMEOUT_MS = 30_000


def create_db_engine(database_url: str, **engine_options: Any) -> Engine:
    """Verilen bağlantı dizesi için motor kurar; SQLite ise yukarıdaki ayarları uygular."""
    engine = create_engine(database_url, **engine_options)
    if engine.dialect.name == "sqlite":
        _configure_sqlite(engine)
    return engine


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _connection_record: Any) -> None:
        # sqlite3 sürücüsünün kendi BEGIN yönetimini kapat; BEGIN'i aşağıda biz atarız.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        finally:
            cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(connection: Any) -> None:
        connection.exec_driver_sql("BEGIN IMMEDIATE")


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False: commit sonrası nitelik okumak yeni işlem (ve SQLite'ta yazma
    # kilidi) açmasın.
    return sessionmaker(bind=engine, expire_on_commit=False)


@lru_cache
def get_engine() -> Engine:
    """Süreç boyunca paylaşılan motor (`DATABASE_URL`)."""
    return create_db_engine(get_settings().database_url)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return create_session_factory(get_engine())


def get_session() -> Iterator[Session]:
    """İstek başına oturum; FastAPI bağımlılığı olarak kullanılır (`Depends(get_session)`)."""
    with get_session_factory()() as session:
        yield session
