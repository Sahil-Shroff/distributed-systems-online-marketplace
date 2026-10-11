from __future__ import annotations

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
from server_side.customer_db.repository import CustomerRepository


def apply_operation(repository: CustomerRepository, operation: Operation) -> None:
    repository.apply(operation)


def operation_name(operation: Operation) -> str:
    if isinstance(operation, CreateBuyer):
        return "create_buyer"
    if isinstance(operation, CreateSeller):
        return "create_seller"
    if isinstance(operation, CreateSession):
        return "create_session"
    if isinstance(operation, TouchSession):
        return "touch_session"
    if isinstance(operation, DeleteSession):
        return "delete_session"
    if isinstance(operation, DeleteSessionsForUserRole):
        return "delete_sessions_for_user_role"
    if isinstance(operation, UpdateSellerFeedback):
        return "update_seller_feedback"
    if isinstance(operation, CompletePurchase):
        return "complete_purchase"
    raise TypeError(f"Unsupported operation type: {type(operation)!r}")
