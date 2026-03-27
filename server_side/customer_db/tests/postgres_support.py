from __future__ import annotations

import os
import uuid

import psycopg2

from server_side.customer_db.backends.in_memory import InMemoryClock, InMemoryIdAllocator
from server_side.customer_db.backends.postgres import PostgresCustomerRepository
from server_side.customer_db.service import CustomerDbService


CUSTOMER_SCHEMA_DDL = """
CREATE SEQUENCE buyers_buyer_id_seq START 1 INCREMENT 1;
CREATE SEQUENCE seller_id_seq START 1000 INCREMENT 1;
CREATE SEQUENCE sessions_session_id_seq START 1 INCREMENT 1;

CREATE TABLE buyers (
  buyer_id integer NOT NULL DEFAULT nextval('buyers_buyer_id_seq'::regclass),
  username varchar NOT NULL,
  password text NOT NULL,
  items_purchased integer NOT NULL DEFAULT 0,
  CONSTRAINT buyers_pkey PRIMARY KEY (buyer_id)
);

CREATE TABLE sellers (
  seller_id integer NOT NULL DEFAULT nextval('seller_id_seq'::regclass),
  seller_feedback integer[] DEFAULT '{0,0}'::integer[],
  items_sold integer DEFAULT 0,
  username varchar NOT NULL,
  password varchar NOT NULL,
  CONSTRAINT sellers_pkey PRIMARY KEY (seller_id)
);

CREATE TABLE sessions (
  session_id integer NOT NULL DEFAULT nextval('sessions_session_id_seq'::regclass),
  role varchar NOT NULL,
  user_id integer NOT NULL,
  last_access_timestamp timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT sessions_pkey PRIMARY KEY (session_id),
  CONSTRAINT sessions_role_check CHECK (role IN ('seller', 'buyer'))
);

CREATE INDEX idx_sessions_user_role ON sessions(user_id, role);
"""


def postgres_tests_enabled() -> bool:
    return os.getenv("RUN_CUSTOMER_DB_POSTGRES_TESTS", "0") == "1"


def postgres_dsn() -> dict[str, object]:
    return {
        "host": os.getenv("TEST_PGHOST", "localhost"),
        "port": int(os.getenv("TEST_PGPORT", os.getenv("PGPORT", "5434"))),
        "user": os.getenv("TEST_PGUSER", os.getenv("PGUSER", "postgres")),
        "password": os.getenv("TEST_PGPASSWORD", os.getenv("PGPASSWORD", "password")),
        "dbname": os.getenv("TEST_PGDATABASE", os.getenv("CUSTOMER_DB_NAME", "customer-database")),
    }


class SchemaConnectionAdapter:
    def __init__(self, schema: str):
        self.schema = schema
        self._dsn = postgres_dsn()

    def execute(self, query: str, params=None, fetch: bool = False):
        conn = psycopg2.connect(options=f"-c search_path={self.schema}", **self._dsn)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall() if fetch else None
        finally:
            conn.close()


class PostgresReplica:
    def __init__(self, schema: str):
        self.schema = schema
        self.customer_db = SchemaConnectionAdapter(schema)
        self.repository = PostgresCustomerRepository(self.customer_db)
        self.allocator = InMemoryIdAllocator()
        self.clock = InMemoryClock()
        self.service = CustomerDbService(self.repository, self.allocator, self.clock)


def create_isolated_postgres_replicas(count: int) -> list[PostgresReplica]:
    root_conn = psycopg2.connect(**postgres_dsn())
    try:
        with root_conn, root_conn.cursor() as cur:
            replicas: list[PostgresReplica] = []
            for _ in range(count):
                schema = f"customer_replica_{uuid.uuid4().hex[:8]}"
                cur.execute(f"CREATE SCHEMA {schema}")
                cur.execute(f"SET search_path TO {schema}")
                cur.execute(CUSTOMER_SCHEMA_DDL)
                replicas.append(PostgresReplica(schema))
            return replicas
    finally:
        root_conn.close()


def drop_isolated_postgres_replicas(replicas: list[PostgresReplica]) -> None:
    if not replicas:
        return
    root_conn = psycopg2.connect(**postgres_dsn())
    try:
        with root_conn, root_conn.cursor() as cur:
            for replica in replicas:
                cur.execute(f"DROP SCHEMA IF EXISTS {replica.schema} CASCADE")
    finally:
        root_conn.close()
