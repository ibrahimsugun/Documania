"""Alembic ortamı (PRD 00.3.2).

Bağlantı dizesi önceliği: programatik `sqlalchemy.url` seçeneği (testler) → `DATABASE_URL`
(`app.config`). Aynı göç zinciri SQLite ve PostgreSQL'de çalışır; SQLite'ın ALTER kısıtları
için göçler batch kipinde üretilir.
"""

from logging.config import fileConfig

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.db.models import Base, UtcDateTime

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def _render_item(type_: str, obj: object, _autogen_context: AutogenContext) -> str | bool:
    # Göç dosyaları uygulama koduna bağlanmasın: UtcDateTime saf SQLAlchemy tipiyle yazılır.
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def _configure_options() -> dict[str, object]:
    return {
        "target_metadata": target_metadata,
        "render_as_batch": True,
        "compare_type": True,
        "render_item": _render_item,
    }


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_configure_options(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, **_configure_options())
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
