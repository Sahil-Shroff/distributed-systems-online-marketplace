import os
import sqlite3
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

class Database_Connection:

    def __init__(
        self,
        db_name: str | None = None,
        db_path: str | None = None,
        init_schema: str | None = None,
    ):
        self.db_name = db_name
        self.db_path = db_path
        self.init_schema = init_schema
        self.sqlite_path: str | None = None
        print(f"Connecting to SQLite database {self._resolve_sqlite_path()}...")
        self._connect()

    def _connect(self):
        self.sqlite_path = self._resolve_sqlite_path()
        conn = self.connect_sqlite()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            if self.init_schema:
                conn.executescript(self.init_schema)
            conn.commit()
        finally:
            conn.close()

    def execute(self, query: str, params=None, fetch: bool = False):
        conn = self.connect_sqlite()
        try:
            cur = conn.cursor()
            cur.execute(self._sqlite_query(query), self._sqlite_params(params))
            rows = cur.fetchall() if fetch else None
            conn.commit()
            return [tuple(row) for row in rows] if rows is not None else None
        finally:
            conn.close()

    def connect_sqlite(self):
        if self.sqlite_path is None:
            self.sqlite_path = self._resolve_sqlite_path()
        return sqlite3.connect(self.sqlite_path, timeout=30, check_same_thread=False)

    def _resolve_sqlite_path(self) -> str:
        if self.db_path:
            path = Path(self.db_path)
        elif self.db_name:
            path = Path(self.db_name)
            if not path.is_absolute():
                repo_root = Path(__file__).resolve().parents[2]
                path = repo_root / "database" / path
        else:
            repo_root = Path(__file__).resolve().parents[2]
            path = repo_root / "database" / "app.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    @staticmethod
    def _sqlite_query(query: str) -> str:
        return query.replace("%s", "?")

    @staticmethod
    def _sqlite_params(params):
        if params is None:
            return ()
        return tuple(params)

    def close(self):
        self.sqlite_path = None


            
            
