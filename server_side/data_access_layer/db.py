import os
from psycopg2.pool import SimpleConnectionPool

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

class Database_Connection:

    def __init__(
        self,
        db_name: str | None = None,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        self.host = host or os.getenv("PGHOST", "localhost")
        self.port = int(port or os.getenv("PGPORT", "5434"))
        self.db_name = db_name
        self.user = user or os.getenv("PGUSER", "postgres")
        self.password = password or os.getenv("PGPASSWORD")
        if not self.password:
            raise RuntimeError("PGPASSWORD not set. Store it in .env or environment variables.")
        self.DB_POOL = None
        self._connect()

    def _connect(self):
        self.DB_POOL = SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            host=self.host,
            port=self.port,
            dbname=self.db_name,
            user=self.user,
            password=self.password,
        )

    def execute(self, query: str, params=None, fetch: bool = False):
        conn = self.DB_POOL.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall() if fetch else None
        finally:
            self.DB_POOL.putconn(conn)

    def close(self):
        if self.DB_POOL:
            try:
                self.DB_POOL.closeall()
            finally:
                self.DB_POOL = None


            
            
