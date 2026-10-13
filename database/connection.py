"""
database/connection.py
Gestiona la conexión a PostgreSQL en Railway usando un pool de conexiones.
"""
import psycopg2
from psycopg2 import pool, OperationalError
from config.settings import settings


class Database:
    _pool: pool.SimpleConnectionPool | None = None

    @classmethod
    def init(cls) -> None:
        """Inicializa el pool de conexiones. Llamar una sola vez al inicio."""
        if cls._pool is not None:
            return
        try:
            cls._pool = pool.SimpleConnectionPool(
                minconn=1,
                maxconn=5,
                dsn=settings.DATABASE_URL,
                connect_timeout=10,
            )
        except OperationalError as exc:
            raise ConnectionError(
                f"No se pudo conectar a la base de datos.\n"
                f"Verifica DATABASE_URL en tu archivo .env\n\nDetalle: {exc}"
            ) from exc

    @classmethod
    def get_connection(cls) -> psycopg2.extensions.connection:
        if cls._pool is None:
            cls.init()
        return cls._pool.getconn()

    @classmethod
    def release_connection(cls, conn: psycopg2.extensions.connection) -> None:
        if cls._pool:
            cls._pool.putconn(conn)

    @classmethod
    def close_all(cls) -> None:
        if cls._pool:
            cls._pool.closeall()
            cls._pool = None
