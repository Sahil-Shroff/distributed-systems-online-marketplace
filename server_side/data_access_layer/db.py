from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

try:
    from psycopg2.pool import SimpleConnectionPool
except Exception:
    SimpleConnectionPool = None


SQLITE_JSON_COLUMNS = {"keywords", "item_feedback"}
SQLITE_BOOL_COLUMNS = {"condition_is_new", "is_saved"}


class Database_Connection:
    def __init__(
        self,
        db_name: str | None = None,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        backend: str | None = None,
        sqlite_path: str | None = None,
        db_path: str | None = None,
        init_schema: str | None = None,
    ):
        self.db_name = db_name
        self.backend = (backend or os.getenv("DB_BACKEND", "sqlite")).lower()
        self.host = host or os.getenv("PGHOST", "localhost")
        self.port = int(port or os.getenv("PGPORT", "5434"))
        self.user = user or os.getenv("PGUSER", "postgres")
        self.password = password or os.getenv("PGPASSWORD")
        self.sqlite_path = sqlite_path or db_path
        self.init_schema = init_schema
        self.DB_POOL = None
        self._sqlite_conn = None
        self._connect()

    def _connect(self):
        if self.backend == "sqlite":
            self._connect_sqlite()
            return
        self._connect_postgres()

    def _connect_postgres(self):
        if SimpleConnectionPool is None:
            raise RuntimeError("psycopg2 is not installed. Use SQLite or install psycopg2-binary.")
        if not self.password:
            raise RuntimeError("PGPASSWORD not set. Store it in .env or environment variables.")
        self.DB_POOL = SimpleConnectionPool(
            minconn=1,
            maxconn=15,
            host=self.host,
            port=self.port,
            dbname=self.db_name,
            user=self.user,
            password=self.password,
        )

    def _resolve_sqlite_path(self) -> Path:
        raw_path = self.sqlite_path or self.db_name
        if not raw_path:
            raise RuntimeError("sqlite_path or db_name is required for SQLite backend")
        path = Path(raw_path)
        if not path.is_absolute():
            repo_root = Path(__file__).resolve().parents[2]
            if str(path).endswith(".sqlite") or str(path).endswith(".db"):
                path = repo_root / "database" / path
            else:
                path = Path.cwd() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _connect_sqlite(self):
        path = self._resolve_sqlite_path()
        self.sqlite_path = str(path)
        self._sqlite_conn = sqlite3.connect(str(path), check_same_thread=False)
        self._sqlite_conn.row_factory = sqlite3.Row
        self._sqlite_conn.execute("PRAGMA journal_mode=WAL")
        self._sqlite_conn.execute("PRAGMA synchronous=NORMAL")
        self._sqlite_conn.execute("PRAGMA foreign_keys=ON")
        if self.init_schema:
            self._sqlite_conn.executescript(self.init_schema)
        self._ensure_sqlite_schema()

    def _ensure_sqlite_schema(self):
        if self.init_schema:
            self._sqlite_conn.commit()
            return
        if self.db_name and "product" in self.db_name:
            self._sqlite_conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS items (
                    item_id INTEGER PRIMARY KEY,
                    item_name TEXT NOT NULL,
                    category INTEGER NOT NULL DEFAULT 0,
                    keywords TEXT,
                    condition_is_new INTEGER NOT NULL DEFAULT 1,
                    sale_price REAL NOT NULL DEFAULT 0,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    item_feedback TEXT NOT NULL DEFAULT '[0, 0]',
                    seller_id INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cart_items (
                    cart_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    buyer_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    item_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    is_saved INTEGER NOT NULL DEFAULT 0,
                    UNIQUE (buyer_id, session_id, item_id, is_saved)
                );

                CREATE TABLE IF NOT EXISTS purchases (
                    purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    buyer_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    purchased_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            self._sqlite_conn.commit()

    def _sqlite_placeholders(self, query: str) -> str:
        return query.replace("%s", "?")

    def _sqlite_param(self, value: Any) -> Any:
        if isinstance(value, list):
            return json.dumps(value)
        if isinstance(value, tuple):
            return json.dumps(list(value))
        if isinstance(value, bool):
            return int(value)
        return value

    def _sqlite_row_value(self, column: str, value: Any) -> Any:
        if value is None:
            return None
        if column in SQLITE_JSON_COLUMNS and isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        if column in SQLITE_BOOL_COLUMNS:
            return bool(value)
        return value

    def _execute_sqlite(self, query: str, params=None, fetch: bool = False):
        sql = self._sqlite_placeholders(query)
        normalized_params = tuple(self._sqlite_param(v) for v in (params or ()))
        cur = self._sqlite_conn.cursor()
        try:
            cur.execute(sql, normalized_params)
            rows = []
            if fetch:
                fetched = cur.fetchall()
                columns = [desc[0] for desc in (cur.description or [])]
                for row in fetched:
                    rows.append(tuple(self._sqlite_row_value(col, row[col]) for col in columns))
            self._sqlite_conn.commit()
            return rows if fetch else None
        finally:
            cur.close()

    def execute(self, query: str, params=None, fetch: bool = False):
        if self.backend == "sqlite":
            return self._execute_sqlite(query, params=params, fetch=fetch)
        conn = self.DB_POOL.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall() if fetch else None
        finally:
            self.DB_POOL.putconn(conn)

    def connect_sqlite(self):
        if self.backend != "sqlite":
            raise RuntimeError("connect_sqlite is only available for SQLite backends")
        return sqlite3.connect(self.sqlite_path, timeout=30, check_same_thread=False)

    def close(self):
        if self.backend == "sqlite":
            if self._sqlite_conn:
                try:
                    self._sqlite_conn.close()
                finally:
                    self._sqlite_conn = None
            return
        if self.DB_POOL:
            try:
                self.DB_POOL.closeall()
            finally:
                self.DB_POOL = None
