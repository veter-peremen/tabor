from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(db_url: str) -> async_sessionmaker[AsyncSession]:
    global _engine, _sessionmaker
    _engine = create_async_engine(db_url, echo=False)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _sessionmaker


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("Движок БД не инициализирован. Вызовите init_engine().")
    return _sessionmaker


async def create_all() -> None:
    if _engine is None:
        raise RuntimeError("Движок БД не инициализирован. Вызовите init_engine().")
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_columns(conn)


# Простейшие миграции: добавляем недостающие колонки в уже существующую БД
_COLUMN_MIGRATIONS: dict[str, dict[str, str]] = {
    "users": {
        "is_banned": "ALTER TABLE users ADD COLUMN is_banned BOOLEAN NOT NULL DEFAULT 0",
    },
}


async def _ensure_columns(conn) -> None:
    for table, columns in _COLUMN_MIGRATIONS.items():
        result = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
        existing = {row[1] for row in result.fetchall()}
        for column, ddl in columns.items():
            if column not in existing:
                await conn.execute(text(ddl))
    await _migrate_genres_m2m(conn)


async def _migrate_genres_m2m(conn) -> None:
    """Переносит старый events.genre_id (один жанр) в таблицу связей event_genres."""
    cols = await conn.exec_driver_sql("PRAGMA table_info(events)")
    event_columns = {row[1] for row in cols.fetchall()}
    if "genre_id" not in event_columns:
        return  # уже новая схема
    link_count = await conn.exec_driver_sql("SELECT COUNT(*) FROM event_genres")
    if link_count.fetchone()[0] > 0:
        return  # связи уже заполнены
    await conn.exec_driver_sql(
        "INSERT OR IGNORE INTO event_genres (event_id, genre_id) "
        "SELECT id, genre_id FROM events WHERE genre_id IS NOT NULL"
    )
