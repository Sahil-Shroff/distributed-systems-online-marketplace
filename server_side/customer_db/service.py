from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from server_side.customer_db.apply import apply_operation
from server_side.customer_db.models import SESSION_TTL, Buyer, Seller, Session
from server_side.customer_db.operations import Operation
from server_side.customer_db.operations import (
    CompletePurchase,
    CreateBuyer,
    CreateSeller,
    CreateSession,
    DeleteSession,
    DeleteSessionsForUserRole,
    TouchSession,
    UpdateSellerFeedback,
)
from server_side.customer_db.repository import Clock, CustomerRepository, IdAllocator


class AuthenticationError(ValueError):
    pass


class SessionError(ValueError):
    pass


@dataclass(frozen=True)
class VerifySessionResult:
    session: Session
    touch_operation: TouchSession


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class CustomerDbService:
    def __init__(self, repository: CustomerRepository, allocator: IdAllocator, clock: Clock | None = None):
        self.repository = repository
        self.allocator = allocator
        self.clock = clock or SystemClock()

    # Entry-replica operation builders
    def build_create_buyer(self, username: str, password: str) -> CreateBuyer:
        return CreateBuyer(
            buyer_id=self.allocator.next_buyer_id(),
            username=username,
            password=password,
        )

    def build_create_seller(self, username: str, password: str) -> CreateSeller:
        return CreateSeller(
            seller_id=self.allocator.next_seller_id(),
            username=username,
            password=password,
        )

    def build_create_session(self, role: str, user_id: int) -> CreateSession:
        return CreateSession(
            session_id=self.allocator.next_session_id(),
            role=role,
            user_id=user_id,
            created_at=self.clock.now(),
        )

    def build_touch_session(self, session_id: str, touched_at: datetime | None = None) -> TouchSession:
        return TouchSession(session_id=session_id, touched_at=touched_at or self.clock.now())

    def build_delete_session(self, session_id: str) -> DeleteSession:
        return DeleteSession(session_id=session_id)

    def build_delete_sessions_for_user_role(self, user_id: int, role: str) -> DeleteSessionsForUserRole:
        return DeleteSessionsForUserRole(user_id=user_id, role=role)

    def build_update_seller_feedback(self, seller_id: int, is_positive: bool) -> UpdateSellerFeedback:
        return UpdateSellerFeedback(
            seller_id=seller_id,
            positive_delta=1 if is_positive else 0,
            negative_delta=0 if is_positive else 1,
        )

    def build_complete_purchase(self, buyer_id: int, seller_id: int, quantity: int) -> CompletePurchase:
        return CompletePurchase(buyer_id=buyer_id, seller_id=seller_id, quantity=quantity)

    # Replay path: all replicas must use only this for mutations
    def apply_replicated(self, operation: Operation) -> None:
        apply_operation(self.repository, operation)

    # Compatibility/service entrypoints used by gRPC today
    def create_buyer(self, username: str, password: str) -> CreateBuyer:
        operation = self.build_create_buyer(username, password)
        self.apply_replicated(operation)
        return operation

    def create_seller(self, username: str, password: str) -> CreateSeller:
        operation = self.build_create_seller(username, password)
        self.apply_replicated(operation)
        return operation

    def login_buyer(self, username: str, password: str) -> tuple[Buyer, CreateSession]:
        buyer = self.repository.get_buyer_by_username_password(username, password)
        if buyer is None:
            raise AuthenticationError("Invalid username or password")
        operation = self.build_create_session(role="buyer", user_id=buyer.buyer_id)
        self.apply_replicated(operation)
        return buyer, operation

    def login_seller(self, username: str, password: str) -> tuple[Seller, CreateSession]:
        seller = self.repository.get_seller_by_username_password(username, password)
        if seller is None:
            raise AuthenticationError("Invalid username or password")
        operation = self.build_create_session(role="seller", user_id=seller.seller_id)
        self.apply_replicated(operation)
        return seller, operation

    def verify_session(self, session_id: str) -> VerifySessionResult:
        observed_at = self.clock.now()
        session = self.repository.get_session(session_id)
        if session is None:
            raise SessionError("Session invalid or expired")
        if session.last_access_timestamp <= observed_at - SESSION_TTL:
            raise SessionError("Session invalid or expired")
        operation = self.build_touch_session(session_id=session_id, touched_at=observed_at)
        self.apply_replicated(operation)
        refreshed = self.repository.get_session(session_id)
        if refreshed is None:
            raise SessionError("Session invalid or expired")
        return VerifySessionResult(session=refreshed, touch_operation=operation)

    def logout(self, session_id: str, user_id: int, role: str, scope: str) -> None:
        if scope == "all":
            operation = self.build_delete_sessions_for_user_role(user_id=user_id, role=role)
        else:
            operation = self.build_delete_session(session_id=session_id)
        self.apply_replicated(operation)

    def apply_seller_feedback(self, seller_id: int, is_positive: bool) -> UpdateSellerFeedback:
        operation = self.build_update_seller_feedback(seller_id=seller_id, is_positive=is_positive)
        self.apply_replicated(operation)
        return operation

    def complete_purchase(self, buyer_id: int, seller_id: int, quantity: int) -> CompletePurchase:
        operation = self.build_complete_purchase(buyer_id=buyer_id, seller_id=seller_id, quantity=quantity)
        self.apply_replicated(operation)
        return operation

    # Reads
    def get_seller_feedback_counts(self, seller_id: int) -> tuple[int, int] | None:
        seller = self.repository.get_seller(seller_id)
        if seller is None:
            return None
        return seller.seller_feedback

    def get_session(self, session_id: str) -> Session | None:
        return self.repository.get_session(session_id)
