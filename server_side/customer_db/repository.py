from __future__ import annotations

from datetime import datetime
from typing import Protocol

from server_side.customer_db.models import Buyer, Seller, Session
from server_side.customer_db.operations import Operation


class CustomerRepository(Protocol):
    def get_buyer_by_username_password(self, username: str, password: str) -> Buyer | None:
        ...

    def get_seller_by_username_password(self, username: str, password: str) -> Seller | None:
        ...

    def get_buyer(self, buyer_id: int) -> Buyer | None:
        ...

    def get_seller(self, seller_id: int) -> Seller | None:
        ...

    def get_session(self, session_id: str) -> Session | None:
        ...

    def apply(self, operation: Operation) -> None:
        ...


class IdAllocator(Protocol):
    def next_buyer_id(self) -> int:
        ...

    def next_seller_id(self) -> int:
        ...

    def next_session_id(self) -> str:
        ...


class Clock(Protocol):
    def now(self) -> datetime:
        ...
