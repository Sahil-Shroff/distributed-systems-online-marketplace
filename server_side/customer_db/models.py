from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal


Role = Literal["buyer", "seller"]


SESSION_TTL = timedelta(minutes=5)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Buyer:
    buyer_id: int
    username: str
    password: str
    items_purchased: int = 0


@dataclass(frozen=True)
class Seller:
    seller_id: int
    username: str
    password: str
    seller_feedback: tuple[int, int] = (0, 0)
    items_sold: int = 0


@dataclass(frozen=True)
class Session:
    session_id: str
    role: Role
    user_id: int
    last_access_timestamp: datetime = field(default_factory=utc_now)

    def is_active_at(self, observed_at: datetime) -> bool:
        return self.last_access_timestamp > observed_at - SESSION_TTL
