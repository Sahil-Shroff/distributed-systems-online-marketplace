from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server_side.customer_db.tests.postgres_support import CUSTOMER_SCHEMA_DDL, postgres_dsn  # noqa: E402


def _admin_dsn() -> dict[str, object]:
    dsn = postgres_dsn()
    dsn["dbname"] = os.getenv("TEST_PGADMIN_DB", "postgres")
    return dsn

def create_replica_databases(prefix: str, count: int, reset: bool) -> list[str]:
    db_names = [f"{prefix}{idx}" for idx in range(count)]
    admin_conn = psycopg2.connect(**_admin_dsn())
    try:
        admin_conn.autocommit = True
        with admin_conn.cursor() as cur:
            for db_name in db_names:
                if reset:
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                        (db_name,),
                    )
                    cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
                if cur.fetchone() is None:
                    cur.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        admin_conn.close()

    for db_name in db_names:
        dsn = postgres_dsn()
        dsn["dbname"] = db_name
        conn = psycopg2.connect(**dsn)
        try:
            with conn, conn.cursor() as cur:
                if reset:
                    cur.execute("DROP TABLE IF EXISTS sessions CASCADE")
                    cur.execute("DROP TABLE IF EXISTS sellers CASCADE")
                    cur.execute("DROP TABLE IF EXISTS buyers CASCADE")
                    cur.execute("DROP SEQUENCE IF EXISTS sessions_session_id_seq CASCADE")
                    cur.execute("DROP SEQUENCE IF EXISTS seller_id_seq CASCADE")
                    cur.execute("DROP SEQUENCE IF EXISTS buyers_buyer_id_seq CASCADE")
                cur.execute(CUSTOMER_SCHEMA_DDL)
        finally:
            conn.close()
    return db_names


def main() -> None:
    parser = argparse.ArgumentParser(description="Create local customer-db replica databases in one Postgres instance.")
    parser.add_argument("--prefix", default="customer-db-replica_")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--reset", action="store_true", help="Drop and recreate the replica databases before applying schema")
    args = parser.parse_args()

    created = create_replica_databases(prefix=args.prefix, count=args.count, reset=args.reset)
    print({"databases": created})


if __name__ == "__main__":
    main()
