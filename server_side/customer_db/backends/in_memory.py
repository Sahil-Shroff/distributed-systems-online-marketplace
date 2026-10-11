from __future__ import annotations

from dataclasses import replace
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
from server_side.customer_db.repository import Clock, CustomerRepository, IdAllocator


class InMemoryIdAllocator(IdAllocator):
    def __init__(self, next_buyer_id: int = 1, next_seller_id: int = 1000, next_session_id: int = 1):
        self._next_buyer_id = next_buyer_id
        self._next_seller_id = next_seller_id
        self._next_session_id = next_session_id

    def next_buyer_id(self) -> int:
        value = self._next_buyer_id
        self._next_buyer_id += 1
        return value

    def next_seller_id(self) -> int:
        value = self._next_seller_id
        self._next_seller_id += 1
        return value

    def next_session_id(self) -> str:
        value = str(self._next_session_id)
        self._next_session_id += 1
        return value


class InMemoryClock(Clock):
    def __init__(self, initial: datetime | None = None):
        self._now = initial or datetime.now(timezone.utc)

    def now(self) -> datetime:
        return self._now

    def set(self, value: datetime) -> None:
        self._now = value


class InMemoryCustomerRepository(CustomerRepository):
    def __init__(self):
        self.buyers: dict[int, Buyer] = {}
        self.sellers: dict[int, Seller] = {}
        self.sessions: dict[str, Session] = {}

    def get_buyer_by_username_password(self, username: str, password: str) -> Buyer | None:
        for buyer in self.buyers.values():
            if buyer.username == username and buyer.password == password:
                return buyer
        return None

    def get_seller_by_username_password(self, username: str, password: str) -> Seller | None:
        for seller in self.sellers.values():
            if seller.username == username and seller.password == password:
                return seller
        return None

    def get_buyer(self, buyer_id: int) -> Buyer | None:
        return self.buyers.get(buyer_id)

    def get_seller(self, seller_id: int) -> Seller | None:
        return self.sellers.get(seller_id)

    def get_session(self, session_id: str) -> Session | None:
        return self.sessions.get(session_id)

    def apply(self, operation: Operation) -> None:
        if isinstance(operation, CreateBuyer):
            self.buyers[operation.buyer_id] = Buyer(
                buyer_id=operation.buyer_id,
                username=operation.username,
                password=operation.password,
                items_purchased=0,
            )
            return
        if isinstance(operation, CreateSeller):
            self.sellers[operation.seller_id] = Seller(
                seller_id=operation.seller_id,
                username=operation.username,
                password=operation.password,
                seller_feedback=(0, 0),
                items_sold=0,
            )
            return
        if isinstance(operation, CreateSession):
            self.sessions[operation.session_id] = Session(
                session_id=operation.session_id,
                role=operation.role,
                user_id=operation.user_id,
                last_access_timestamp=operation.created_at,
            )
            return
        if isinstance(operation, TouchSession):
            session = self.sessions.get(operation.session_id)
            if session is not None:
                self.sessions[operation.session_id] = replace(session, last_access_timestamp=operation.touched_at)
            return
        if isinstance(operation, DeleteSession):
            self.sessions.pop(operation.session_id, None)
            return
        if isinstance(operation, DeleteSessionsForUserRole):
            self.sessions = {
                session_id: session
                for session_id, session in self.sessions.items()
                if not (session.user_id == operation.user_id and session.role == operation.role)
            }
            return
        if isinstance(operation, UpdateSellerFeedback):
            seller = self.sellers.get(operation.seller_id)
            if seller is None:
                raise KeyError(f"Seller {operation.seller_id} not found")
            pos, neg = seller.seller_feedback
            self.sellers[operation.seller_id] = replace(
                seller,
                seller_feedback=(pos + operation.positive_delta, neg + operation.negative_delta),
            )
            return
        if isinstance(operation, CompletePurchase):
            buyer = self.buyers.get(operation.buyer_id)
            seller = self.sellers.get(operation.seller_id)
            if buyer is None:
                raise KeyError(f"Buyer {operation.buyer_id} not found")
            if seller is None:
                raise KeyError(f"Seller {operation.seller_id} not found")
            self.buyers[operation.buyer_id] = replace(
                buyer,
                items_purchased=buyer.items_purchased + operation.quantity,
            )
            self.sellers[operation.seller_id] = replace(
                seller,
                items_sold=seller.items_sold + operation.quantity,
            )
            return
        raise TypeError(f"Unsupported operation type: {type(operation)!r}")
