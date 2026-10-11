from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Union

from server_side.customer_db.models import Role


@dataclass(frozen=True)
class CreateBuyer:
    buyer_id: int
    username: str
    password: str


@dataclass(frozen=True)
class CreateSeller:
    seller_id: int
    username: str
    password: str


@dataclass(frozen=True)
class CreateSession:
    session_id: str
    role: Role
    user_id: int
    created_at: datetime


@dataclass(frozen=True)
class TouchSession:
    session_id: str
    touched_at: datetime


@dataclass(frozen=True)
class DeleteSession:
    session_id: str


@dataclass(frozen=True)
class DeleteSessionsForUserRole:
    user_id: int
    role: Role


@dataclass(frozen=True)
class UpdateSellerFeedback:
    seller_id: int
    positive_delta: int
    negative_delta: int


@dataclass(frozen=True)
class CompletePurchase:
    buyer_id: int
    seller_id: int
    quantity: int


Operation = Union[
    CreateBuyer,
    CreateSeller,
    CreateSession,
    TouchSession,
    DeleteSession,
    DeleteSessionsForUserRole,
    UpdateSellerFeedback,
    CompletePurchase,
]
