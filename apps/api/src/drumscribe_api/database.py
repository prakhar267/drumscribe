from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        database_url, connect_args = async_engine_connection(settings.database_url)
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        if settings.database_url.startswith("sqlite"):
            event.listen(self.engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def healthcheck(self) -> None:
        async with self.session_factory() as session:
            await session.execute(text("SELECT 1"))

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session


def async_engine_connection(database_url: str) -> tuple[str, dict[str, object]]:
    """Translate provider URLs into arguments accepted by SQLAlchemy async drivers."""
    url = make_url(database_url)
    connect_args: dict[str, object] = {}

    if url.drivername.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    elif url.drivername in {"postgresql", "postgresql+asyncpg"}:
        ssl_mode = url.query.get("sslmode")
        if ssl_mode is not None:
            connect_args["ssl"] = ssl_mode
        # Neon includes libpq-only parameters in its canonical URL. asyncpg
        # accepts TLS as a connect argument and does not implement channel binding.
        url = url.difference_update_query(["sslmode", "channel_binding"])
        url = url.set(drivername="postgresql+asyncpg")

    return url.render_as_string(hide_password=False), connect_args


def _enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
