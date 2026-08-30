from drumscribe_api.database import async_engine_connection


def test_neon_url_is_compatible_with_sqlalchemy_asyncpg() -> None:
    database_url, connect_args = async_engine_connection(
        "postgresql://neondb_owner:secret@ep-example-pooler.us-east-2.aws.neon.tech/"
        "neondb?sslmode=require&channel_binding=require"
    )

    assert database_url == (
        "postgresql+asyncpg://neondb_owner:secret@ep-example-pooler.us-east-2.aws.neon.tech/neondb"
    )
    assert connect_args == {"ssl": "require"}


def test_sqlite_connection_keeps_foreign_thread_support() -> None:
    database_url, connect_args = async_engine_connection("sqlite+aiosqlite:///test.db")

    assert database_url == "sqlite+aiosqlite:///test.db"
    assert connect_args == {"check_same_thread": False}
