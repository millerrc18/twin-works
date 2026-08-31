"""Alembic env — targets the app's Base metadata; sync SQLite URL for migrations."""
from logging.config import fileConfig
from sqlalchemy import engine_from_config, event, pool
from alembic import context

from app.config import settings
from app.database import Base
from app import models  # noqa: F401  (register all tables on Base.metadata)

config = context.config
# migrations run synchronously — strip the async driver
sync_url = settings.database_url.replace("+aiosqlite", "")
config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=sync_url, target_metadata=target_metadata,
                      literal_binds=True, render_as_batch=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}),
                                     prefix="sqlalchemy.", poolclass=pool.NullPool)
    if connectable.dialect.name == "sqlite":
        @event.listens_for(connectable, "connect")
        def _configure_sqlite(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA recursive_triggers=ON")
            cursor.execute("PRAGMA foreign_keys")
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("SQLite foreign_keys pragma could not be enabled")
            cursor.execute("PRAGMA recursive_triggers")
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("SQLite recursive_triggers pragma could not be enabled")
            cursor.close()
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=True)  # batch mode required for SQLite ALTER
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
