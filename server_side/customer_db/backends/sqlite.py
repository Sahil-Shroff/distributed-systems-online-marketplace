from __future__ import annotations

import json
from datetime import datetime, timezone

from server_side.customer_db.models import Buyer, Seller, Session
from server_side.customer_db.operations import (
    CompletePurchase,
    CreateBuyer,
    CreateSeller,
    CreateSession,
    DeleteSession,
    DeleteSessionsForUserRole,
    Operation,
    TouchSession,
    UpdateSellerFeedback,
)
from server_side.customer_db.repository import CustomerRepository, IdAllocator


CUSTOMER_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS buyers (
  buyer_id INTEGER PRIMARY KEY,
  username TEXT NOT NULL,
  password TEXT NOT NULL,
  items_purchased INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sellers (
  seller_id INTEGER PRIMARY KEY,
  username TEXT NOT NULL,
  password TEXT NOT NULL,
  seller_feedback TEXT NOT NULL DEFAULT '[0, 0]',
  items_sold INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK (role IN ('seller', 'buyer')),
  user_id INTEGER NOT NULL,
  last_access_timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_role ON sessions(user_id, role);

CREATE TABLE IF NOT EXISTS id_counters (
  name TEXT PRIMARY KEY,
  next_value INTEGER NOT NULL
);

INSERT OR IGNORE INTO id_counters(name, next_value) VALUES
  ('buyer', 1),
  ('seller', 1000),
  ('session', 1);
"""


class SQLiteIdAllocator(IdAllocator):
    def __init__(self, customer_db):
        self.customer_db = customer_db

    def next_buyer_id(self) -> int:
        return self._next_value("buyer")

    def next_seller_id(self) -> int:
        return self._next_value("seller")

    def next_session_id(self) -> str:
        return str(self._next_value("session"))

    def _next_value(self, name: str) -> int:
        conn = self.customer_db.connect_sqlite()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT next_value FROM id_counters WHERE name = ?", (name,)).fetchone()
            if row is None:
                raise RuntimeError(f"Missing SQLite counter: {name}")
            current = int(row[0])
            conn.execute("UPDATE id_counters SET next_value = ? WHERE name = ?", (current + 1, name))
            conn.commit()
            return current
        finally:
            conn.close()


class SQLiteCustomerRepository(CustomerRepository):
    def __init__(self, customer_db):
        self.customer_db = customer_db

    def get_buyer_by_username_password(self, username: str, password: str) -> Buyer | None:
        rows = self.customer_db.execute(
            "SELECT buyer_id, username, password, items_purchased FROM buyers WHERE username = %s AND password = %s",
            (username, password),
            fetch=True,
        )
        return _buyer_from_row(rows[0]) if rows else None

    def get_seller_by_username_password(self, username: str, password: str) -> Seller | None:
        rows = self.customer_db.execute(
            "SELECT seller_id, username, password, seller_feedback, items_sold FROM sellers WHERE username = %s AND password = %s",
            (username, password),
            fetch=True,
        )
        return _seller_from_row(rows[0]) if rows else None

    def get_buyer(self, buyer_id: int) -> Buyer | None:
        rows = self.customer_db.execute(
            "SELECT buyer_id, username, password, items_purchased FROM buyers WHERE buyer_id = %s",
            (buyer_id,),
            fetch=True,
        )
        return _buyer_from_row(rows[0]) if rows else None

    def get_seller(self, seller_id: int) -> Seller | None:
        rows = self.customer_db.execute(
            "SELECT seller_id, username, password, seller_feedback, items_sold FROM sellers WHERE seller_id = %s",
            (seller_id,),
            fetch=True,
        )
        return _seller_from_row(rows[0]) if rows else None

    def get_session(self, session_id: str) -> Session | None:
        rows = self.customer_db.execute(
            "SELECT session_id, role, user_id, last_access_timestamp FROM sessions WHERE session_id = %s",
            (session_id,),
            fetch=True,
        )
        return _session_from_row(rows[0]) if rows else None

    def apply(self, operation: Operation) -> None:
        if isinstance(operation, CreateBuyer):
            self.customer_db.execute(
                "INSERT INTO buyers (buyer_id, username, password, items_purchased) VALUES (%s, %s, %s, 0)",
                (operation.buyer_id, operation.username, operation.password),
            )
            return
        if isinstance(operation, CreateSeller):
            self.customer_db.execute(
                "INSERT INTO sellers (seller_id, username, password, seller_feedback, items_sold) VALUES (%s, %s, %s, %s, 0)",
                (operation.seller_id, operation.username, operation.password, json.dumps([0, 0])),
            )
            return
        if isinstance(operation, CreateSession):
            self.customer_db.execute(
                "INSERT INTO sessions (session_id, role, user_id, last_access_timestamp) VALUES (%s, %s, %s, %s)",
                (operation.session_id, operation.role, operation.user_id, operation.created_at.isoformat()),
            )
            return
        if isinstance(operation, TouchSession):
            self.customer_db.execute(
                "UPDATE sessions SET last_access_timestamp = %s WHERE session_id = %s",
                (operation.touched_at.isoformat(), operation.session_id),
            )
            return
        if isinstance(operation, DeleteSession):
            self.customer_db.execute(
                "DELETE FROM sessions WHERE session_id = %s",
                (operation.session_id,),
            )
            return
        if isinstance(operation, DeleteSessionsForUserRole):
            self.customer_db.execute(
                "DELETE FROM sessions WHERE user_id = %s AND role = %s",
                (operation.user_id, operation.role),
            )
            return
        if isinstance(operation, UpdateSellerFeedback):
            seller = self.get_seller(operation.seller_id)
            if seller is None:
                return
            feedback = [
                seller.seller_feedback[0] + operation.positive_delta,
                seller.seller_feedback[1] + operation.negative_delta,
            ]
            self.customer_db.execute(
                "UPDATE sellers SET seller_feedback = %s WHERE seller_id = %s",
                (json.dumps(feedback), operation.seller_id),
            )
            return
        if isinstance(operation, CompletePurchase):
            self.customer_db.execute(
                "UPDATE buyers SET items_purchased = items_purchased + %s WHERE buyer_id = %s",
                (operation.quantity, operation.buyer_id),
            )
            self.customer_db.execute(
                "UPDATE sellers SET items_sold = items_sold + %s WHERE seller_id = %s",
                (operation.quantity, operation.seller_id),
            )
            return
        raise TypeError(f"Unsupported operation type: {type(operation)!r}")


def _buyer_from_row(row) -> Buyer:
    return Buyer(
        buyer_id=int(row[0]),
        username=row[1],
        password=row[2],
        items_purchased=int(row[3]),
    )


def _seller_from_row(row) -> Seller:
    feedback = json.loads(row[3]) if row[3] else [0, 0]
    return Seller(
        seller_id=int(row[0]),
        username=row[1],
        password=row[2],
        seller_feedback=(int(feedback[0]), int(feedback[1])),
        items_sold=int(row[4]),
    )


def _session_from_row(row) -> Session:
    timestamp = datetime.fromisoformat(row[3])
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return Session(
        session_id=str(row[0]),
        role=row[1],
        user_id=int(row[2]),
        last_access_timestamp=timestamp,
    )
