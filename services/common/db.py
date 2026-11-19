"""Database helper used by order-service.

Two drivers:
  * postgres (default in Docker/Kubernetes) via psycopg2
  * sqlite   (PG_DRIVER=sqlite) for running the whole app on a laptop with no
             containers. The SQL dialect differences are translated below.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import time

import psycopg2

DSN = {
    "host": os.getenv("PGHOST", "postgres"),
    "port": int(os.getenv("PGPORT", "5432")),
    "dbname": os.getenv("PGDATABASE", "shop"),
    "user": os.getenv("PGUSER", "shop"),
    "password": os.getenv("PGPASSWORD", "shop"),
}

LOCAL_SQLITE = os.getenv("PG_DRIVER", "postgres").lower() == "sqlite"
SQLITE_PATH = os.getenv("SQLITE_PATH", os.path.join(tempfile.gettempdir(), "chaosarena_shop.db"))


class _SqliteCursor:
    """Adapts the two Postgres statements used by order-service to SQLite."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._cursor = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql: str, params=None):
        adapted = (
            sql.replace("JSONB", "TEXT")
            .replace("NUMERIC(10,2)", "REAL")
            .replace("TIMESTAMPTZ NOT NULL DEFAULT now()", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
            .replace("TIMESTAMPTZ", "TEXT")
            .replace("%s", "?")
        )
        self._cursor = self._conn.execute(adapted, params or ())
        return self._cursor

    def fetchone(self):
        return self._cursor.fetchone()


class _SqliteConn:
    def __enter__(self):
        self._conn = sqlite3.connect(SQLITE_PATH)
        return self

    def __exit__(self, *args):
        self._conn.commit()
        self._conn.close()
        return False

    def cursor(self) -> _SqliteCursor:
        return _SqliteCursor(self._conn)


def connect():
    if LOCAL_SQLITE:
        return _SqliteConn()
    return psycopg2.connect(**DSN, connect_timeout=2)


def init_schema() -> None:
    """Create the orders table, retrying while Postgres is still starting."""
    last: Exception | None = None
    for _ in range(30):
        try:
            with connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS orders (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        items JSONB NOT NULL,
                        total NUMERIC(10,2) NOT NULL,
                        status TEXT NOT NULL,
                        version TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            if LOCAL_SQLITE:
                raise
            time.sleep(1)
    raise RuntimeError(f"could not initialise Postgres schema: {last}") from last
