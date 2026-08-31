"""Async SQLAlchemy engine + session dependency."""
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=False)


@event.listens_for(engine.sync_engine, "connect")
def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    """Apply integrity pragmas on every application SQLite connection."""
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


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session
