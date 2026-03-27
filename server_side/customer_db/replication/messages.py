from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

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


MessageKind = Literal["request", "sequence", "retransmit_request"]
RetransmitKind = Literal["request", "sequence"]


@dataclass(frozen=True, order=True)
class RequestId:
    sender_id: int
    local_seq_num: int


@dataclass(frozen=True)
class RequestMessage:
    source_replica_id: int
    request_id: RequestId
    operation: dict[str, Any]
    request_frontier: list[int]
    sequence_frontier: int
    kind: MessageKind = "request"


@dataclass(frozen=True)
class SequenceMessage:
    source_replica_id: int
    global_sequence: int
    request_id: RequestId
    request_frontier: list[int]
    sequence_frontier: int
    kind: MessageKind = "sequence"


@dataclass(frozen=True)
class RetransmitRequestMessage:
    source_replica_id: int
    target_replica_id: int
    missing_kind: RetransmitKind
    request_id: RequestId | None
    global_sequence: int | None
    request_frontier: list[int]
    sequence_frontier: int
    kind: MessageKind = "retransmit_request"


ProtocolMessage = RequestMessage | SequenceMessage | RetransmitRequestMessage


def serialize_message(message: ProtocolMessage) -> dict[str, Any]:
    payload = asdict(message)
    if "request_id" in payload and payload["request_id"] is not None:
        payload["request_id"] = asdict(message.request_id)
    return payload


def deserialize_message(payload: dict[str, Any]) -> ProtocolMessage:
    kind = payload["kind"]
    request_id_payload = payload.get("request_id")
    request_id = RequestId(**request_id_payload) if request_id_payload else None
    if kind == "request":
        return RequestMessage(
            source_replica_id=payload["source_replica_id"],
            request_id=request_id,
            operation=payload["operation"],
            request_frontier=list(payload["request_frontier"]),
            sequence_frontier=payload["sequence_frontier"],
        )
    if kind == "sequence":
        return SequenceMessage(
            source_replica_id=payload["source_replica_id"],
            global_sequence=payload["global_sequence"],
            request_id=request_id,
            request_frontier=list(payload["request_frontier"]),
            sequence_frontier=payload["sequence_frontier"],
        )
    if kind == "retransmit_request":
        return RetransmitRequestMessage(
            source_replica_id=payload["source_replica_id"],
            target_replica_id=payload["target_replica_id"],
            missing_kind=payload["missing_kind"],
            request_id=request_id,
            global_sequence=payload["global_sequence"],
            request_frontier=list(payload["request_frontier"]),
            sequence_frontier=payload["sequence_frontier"],
        )
    raise ValueError(f"Unknown message kind: {kind}")


def encode_operation(operation: Operation) -> dict[str, Any]:
    if isinstance(operation, CreateBuyer):
        return {"type": "CreateBuyer", "buyer_id": operation.buyer_id, "username": operation.username, "password": operation.password}
    if isinstance(operation, CreateSeller):
        return {"type": "CreateSeller", "seller_id": operation.seller_id, "username": operation.username, "password": operation.password}
    if isinstance(operation, CreateSession):
        return {
            "type": "CreateSession",
            "session_id": operation.session_id,
            "role": operation.role,
            "user_id": operation.user_id,
            "created_at": operation.created_at.isoformat(),
        }
    if isinstance(operation, TouchSession):
        return {"type": "TouchSession", "session_id": operation.session_id, "touched_at": operation.touched_at.isoformat()}
    if isinstance(operation, DeleteSession):
        return {"type": "DeleteSession", "session_id": operation.session_id}
    if isinstance(operation, DeleteSessionsForUserRole):
        return {"type": "DeleteSessionsForUserRole", "user_id": operation.user_id, "role": operation.role}
    if isinstance(operation, UpdateSellerFeedback):
        return {
            "type": "UpdateSellerFeedback",
            "seller_id": operation.seller_id,
            "positive_delta": operation.positive_delta,
            "negative_delta": operation.negative_delta,
        }
    if isinstance(operation, CompletePurchase):
        return {"type": "CompletePurchase", "buyer_id": operation.buyer_id, "seller_id": operation.seller_id, "quantity": operation.quantity}
    raise TypeError(f"Unsupported operation type: {type(operation)!r}")


def decode_operation(payload: dict[str, Any]) -> Operation:
    op_type = payload["type"]
    if op_type == "CreateBuyer":
        return CreateBuyer(buyer_id=payload["buyer_id"], username=payload["username"], password=payload["password"])
    if op_type == "CreateSeller":
        return CreateSeller(seller_id=payload["seller_id"], username=payload["username"], password=payload["password"])
    if op_type == "CreateSession":
        return CreateSession(
            session_id=payload["session_id"],
            role=payload["role"],
            user_id=payload["user_id"],
            created_at=datetime.fromisoformat(payload["created_at"]),
        )
    if op_type == "TouchSession":
        return TouchSession(session_id=payload["session_id"], touched_at=datetime.fromisoformat(payload["touched_at"]))
    if op_type == "DeleteSession":
        return DeleteSession(session_id=payload["session_id"])
    if op_type == "DeleteSessionsForUserRole":
        return DeleteSessionsForUserRole(user_id=payload["user_id"], role=payload["role"])
    if op_type == "UpdateSellerFeedback":
        return UpdateSellerFeedback(
            seller_id=payload["seller_id"],
            positive_delta=payload["positive_delta"],
            negative_delta=payload["negative_delta"],
        )
    if op_type == "CompletePurchase":
        return CompletePurchase(buyer_id=payload["buyer_id"], seller_id=payload["seller_id"], quantity=payload["quantity"])
    raise ValueError(f"Unknown operation type: {op_type}")
