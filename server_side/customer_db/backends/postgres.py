from __future__ import annotations

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


class PostgresIdAllocator(IdAllocator):
    def __init__(self, customer_db):
        self.customer_db = customer_db

    def next_buyer_id(self) -> int:
        rows = self.customer_db.execute("SELECT nextval('buyers_buyer_id_seq')", fetch=True)
        return int(rows[0][0])

    def next_seller_id(self) -> int:
        rows = self.customer_db.execute("SELECT nextval('seller_id_seq')", fetch=True)
        return int(rows[0][0])

    def next_session_id(self) -> str:
        rows = self.customer_db.execute("SELECT nextval('sessions_session_id_seq')", fetch=True)
        return str(rows[0][0])


class PostgresCustomerRepository(CustomerRepository):
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
                (operation.seller_id, operation.username, operation.password, [0, 0]),
            )
            return
        if isinstance(operation, CreateSession):
            self.customer_db.execute(
                "INSERT INTO sessions (session_id, role, user_id, last_access_timestamp) VALUES (%s, %s, %s, %s)",
                (int(operation.session_id), operation.role, operation.user_id, operation.created_at),
            )
            return
        if isinstance(operation, TouchSession):
            self.customer_db.execute(
                "UPDATE sessions SET last_access_timestamp = %s WHERE session_id = %s",
                (operation.touched_at, int(operation.session_id)),
            )
            return
        if isinstance(operation, DeleteSession):
            self.customer_db.execute(
                "DELETE FROM sessions WHERE session_id = %s",
                (int(operation.session_id),),
            )
            return
        if isinstance(operation, DeleteSessionsForUserRole):
            self.customer_db.execute(
                "DELETE FROM sessions WHERE user_id = %s AND role = %s",
                (operation.user_id, operation.role),
            )
            return
        if isinstance(operation, UpdateSellerFeedback):
            self.customer_db.execute(
                """
                UPDATE sellers
                SET seller_feedback = ARRAY[
                    COALESCE(seller_feedback[1], 0) + %s,
                    COALESCE(seller_feedback[2], 0) + %s
                ]
                WHERE seller_id = %s
                """,
                (operation.positive_delta, operation.negative_delta, operation.seller_id),
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
    feedback = tuple(row[3]) if row[3] is not None else (0, 0)
    return Seller(
        seller_id=int(row[0]),
        username=row[1],
        password=row[2],
        seller_feedback=(int(feedback[0]), int(feedback[1])),
        items_sold=int(row[4]),
    )


def _session_from_row(row) -> Session:
    timestamp = row[3]
    if isinstance(timestamp, datetime) and timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return Session(
        session_id=str(row[0]),
        role=row[1],
        user_id=int(row[2]),
        last_access_timestamp=timestamp,
    )
