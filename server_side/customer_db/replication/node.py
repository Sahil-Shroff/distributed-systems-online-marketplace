from __future__ import annotations

from dataclasses import dataclass
import os
import threading
from typing import Callable, Protocol

from server_side.customer_db.operations import Operation
from server_side.customer_db.replication.messages import (
    ProtocolMessage,
    RequestId,
    RequestMessage,
    RetransmitRequestMessage,
    SequenceMessage,
    decode_operation,
    encode_operation,
)


class ReplicationTransport(Protocol):
    def broadcast(self, message: ProtocolMessage) -> None:
        ...

    def send(self, target_replica_id: int, message: ProtocolMessage) -> None:
        ...


@dataclass(frozen=True)
class DeliveredRecord:
    global_sequence: int
    request_id: RequestId
    operation: Operation


class RotatingSequencerNode:
    def __init__(
        self,
        replica_id: int,
        num_replicas: int,
        transport: ReplicationTransport,
        apply_callback: Callable[[Operation], None],
    ):
        self.replica_id = replica_id
        self.num_replicas = num_replicas
        self.transport = transport
        self.apply_callback = apply_callback

        self.local_request_seq = 0
        self.next_delivery_sequence = 0

        self.requests: dict[RequestId, RequestMessage] = {}
        self.sequences: dict[int, SequenceMessage] = {}
        self.request_to_sequence: dict[RequestId, int] = {}
        self.sequence_to_request: dict[int, RequestId] = {}
        self.delivered_request_ids: set[RequestId] = set()
        self.delivered_records: list[DeliveredRecord] = []

        self.received_request_numbers: dict[int, set[int]] = {idx: set() for idx in range(num_replicas)}
        self.received_sequence_numbers: set[int] = set()
        self.request_frontier: list[int] = [-1 for _ in range(num_replicas)]
        self.sequence_frontier: int = -1

        self.peer_request_frontier: dict[int, list[int]] = {idx: [-1 for _ in range(num_replicas)] for idx in range(num_replicas)}
        self.peer_sequence_frontier: dict[int, int] = {idx: -1 for idx in range(num_replicas)}
        self.peer_request_frontier[self.replica_id] = self.request_frontier.copy()
        self.peer_sequence_frontier[self.replica_id] = self.sequence_frontier
        self._lock = threading.RLock()
        self._delivery_waiters: dict[RequestId, threading.Event] = {}
        self.debug_enabled = os.getenv("CUSTOMER_DB_REPLICATION_DEBUG", "0") == "1"

    def on_client_mutation(self, operation: Operation) -> RequestId:
        with self._lock:
            request_id = RequestId(sender_id=self.replica_id, local_seq_num=self.local_request_seq)
            self.local_request_seq += 1
            self._delivery_waiters[request_id] = threading.Event()
            initial = RequestMessage(
                source_replica_id=self.replica_id,
                request_id=request_id,
                operation=encode_operation(operation),
                request_frontier=self.request_frontier.copy(),
                sequence_frontier=self.sequence_frontier,
            )
            self._accept_request(initial)
            message = RequestMessage(
                source_replica_id=self.replica_id,
                request_id=request_id,
                operation=initial.operation,
                request_frontier=self.request_frontier.copy(),
                sequence_frontier=self.sequence_frontier,
            )
            self.requests[request_id] = message
            self._debug(f"client mutation -> request {request_id} op={type(operation).__name__}")
            self.transport.broadcast(message)
            self._advance_protocol()
            return request_id

    def submit_client_mutation(self, operation: Operation, timeout: float | None = None) -> DeliveredRecord:
        request_id = self.on_client_mutation(operation)
        waiter = self._delivery_waiters[request_id]
        if not waiter.wait(timeout):
            raise TimeoutError(f"Timed out waiting for local delivery of {request_id}")
        with self._lock:
            for record in reversed(self.delivered_records):
                if record.request_id == request_id:
                    return record
        raise RuntimeError(f"Missing delivered record for {request_id}")

    def on_request_receive(self, message: RequestMessage) -> None:
        with self._lock:
            self._accept_request(message)
            self._debug(
                f"received request {message.request_id} from replica {message.source_replica_id} "
                f"req_frontier={message.request_frontier} seq_frontier={message.sequence_frontier}"
            )
            self._broadcast_progress_ping()
            self._advance_protocol()

    def on_sequence_receive(self, message: SequenceMessage) -> None:
        with self._lock:
            self._record_peer_progress(
                message.source_replica_id,
                message.request_frontier,
                max(message.sequence_frontier, message.global_sequence),
            )
            if message.global_sequence not in self.sequences:
                self.sequences[message.global_sequence] = message
                self.sequence_to_request[message.global_sequence] = message.request_id
                self.request_to_sequence[message.request_id] = message.global_sequence
                self.received_sequence_numbers.add(message.global_sequence)
                self._update_sequence_frontier()
            self._debug(
                f"received sequence {message.global_sequence} -> {message.request_id} "
                f"from replica {message.source_replica_id}"
            )
            self._broadcast_progress_ping()
            self._detect_missing_requests_for_sequence(message)
            self._detect_missing_sequences()
            self._advance_protocol()

    def on_retransmit_request_receive(self, message: RetransmitRequestMessage) -> None:
        with self._lock:
            self._record_peer_progress(message.source_replica_id, message.request_frontier, message.sequence_frontier)
            if message.target_replica_id != self.replica_id:
                return
            self._debug(
                f"received retransmit_request from replica {message.source_replica_id} "
                f"kind={message.missing_kind} request_id={message.request_id} seq={message.global_sequence}"
            )
            if message.missing_kind == "request" and message.request_id in self.requests:
                self._debug(f"re-sending request {message.request_id} to replica {message.source_replica_id}")
                self.transport.send(message.source_replica_id, self.requests[message.request_id])
            if message.missing_kind == "sequence" and message.global_sequence in self.sequences:
                self._debug(f"re-sending sequence {message.global_sequence} to replica {message.source_replica_id}")
                self.transport.send(message.source_replica_id, self.sequences[message.global_sequence])

    def periodic_retransmit_scan(self) -> None:
        with self._lock:
            self._detect_missing_sequences()
            for sequence_number, request_id in self.sequence_to_request.items():
                if sequence_number <= self.sequence_frontier and request_id not in self.requests:
                    self._send_retransmit_for_request(request_id)
            self._broadcast_progress_ping()
            self._advance_protocol()

    def delivery_check(self) -> list[DeliveredRecord]:
        newly_delivered: list[DeliveredRecord] = []
        while self._can_deliver(self.next_delivery_sequence):
            request_id = self.sequence_to_request[self.next_delivery_sequence]
            if request_id in self.delivered_request_ids:
                self.next_delivery_sequence += 1
                continue
            operation = decode_operation(self.requests[request_id].operation)
            self.apply_callback(operation)
            record = DeliveredRecord(
                global_sequence=self.next_delivery_sequence,
                request_id=request_id,
                operation=operation,
            )
            self._debug(f"delivered sequence {self.next_delivery_sequence} request {request_id}")
            self.delivered_records.append(record)
            self.delivered_request_ids.add(request_id)
            waiter = self._delivery_waiters.get(request_id)
            if waiter is not None:
                waiter.set()
            newly_delivered.append(record)
            self.next_delivery_sequence += 1
        return newly_delivered

    def _advance_protocol(self) -> None:
        self._try_assign_sequences()
        self.delivery_check()

    def _accept_request(self, message: RequestMessage) -> None:
        self._record_peer_progress(message.source_replica_id, message.request_frontier, message.sequence_frontier)
        if message.request_id not in self.requests:
            self.requests[message.request_id] = message
            self.received_request_numbers[message.request_id.sender_id].add(message.request_id.local_seq_num)
            self._update_request_frontier(message.request_id.sender_id)
            self._detect_missing_requests_from_sender(message.request_id.sender_id, message.request_id.local_seq_num)
        self._update_self_progress()

    def _try_assign_sequences(self) -> None:
        while True:
            next_global = self._next_global_sequence_to_assign()
            if next_global % self.num_replicas != self.replica_id:
                return
            if next_global > 0 and self.sequence_frontier < next_global - 1:
                return
            if not self._have_all_requests_for_assigned_sequences_below(next_global):
                return
            candidate = self._choose_request_for_sequence()
            if candidate is None:
                return
            message = SequenceMessage(
                source_replica_id=self.replica_id,
                global_sequence=next_global,
                request_id=candidate.request_id,
                request_frontier=self.request_frontier.copy(),
                sequence_frontier=max(self.sequence_frontier, next_global),
            )
            self._debug(f"assigning sequence {next_global} -> {candidate.request_id}")
            self.on_sequence_receive(message)
            self.transport.broadcast(message)

    def _choose_request_for_sequence(self) -> RequestMessage | None:
        unassigned = [msg for rid, msg in self.requests.items() if rid not in self.request_to_sequence]
        eligible = [msg for msg in unassigned if self._lower_sender_requests_are_already_assigned(msg.request_id)]
        if not eligible:
            return None
        return sorted(eligible, key=lambda msg: (msg.request_id.sender_id, msg.request_id.local_seq_num))[0]

    def _lower_sender_requests_are_already_assigned(self, request_id: RequestId) -> bool:
        for local_seq_num in range(request_id.local_seq_num):
            if RequestId(request_id.sender_id, local_seq_num) not in self.request_to_sequence:
                return False
        return True

    def _next_global_sequence_to_assign(self) -> int:
        next_global = 0
        while next_global in self.sequence_to_request:
            next_global += 1
        return next_global

    def _have_all_requests_for_assigned_sequences_below(self, next_global: int) -> bool:
        for sequence_number in range(next_global):
            request_id = self.sequence_to_request.get(sequence_number)
            if request_id is None or request_id not in self.requests:
                return False
        return True

    def _can_deliver(self, sequence_number: int) -> bool:
        request_id = self.sequence_to_request.get(sequence_number)
        if request_id is None or request_id not in self.requests:
            return False
        return self._majority_has_received_through(sequence_number)

    def _majority_has_received_through(self, sequence_number: int) -> bool:
        votes = 0
        for replica_id in range(self.num_replicas):
            request_frontier = self.request_frontier if replica_id == self.replica_id else self.peer_request_frontier[replica_id]
            sequence_frontier = self.sequence_frontier if replica_id == self.replica_id else self.peer_sequence_frontier[replica_id]
            if sequence_frontier < sequence_number:
                continue
            if self._peer_has_all_requests_through(request_frontier, sequence_number):
                votes += 1
        return votes >= (self.num_replicas // 2) + 1

    def _peer_has_all_requests_through(self, request_frontier: list[int], sequence_number: int) -> bool:
        for sequence_idx in range(sequence_number + 1):
            request_id = self.sequence_to_request.get(sequence_idx)
            if request_id is None:
                return False
            if request_frontier[request_id.sender_id] < request_id.local_seq_num:
                return False
        return True

    def _detect_missing_requests_from_sender(self, sender_id: int, observed_local_seq: int) -> None:
        for local_seq in range(self.request_frontier[sender_id] + 1, observed_local_seq):
            self._send_retransmit_for_request(RequestId(sender_id, local_seq))

    def _detect_missing_requests_for_sequence(self, message: SequenceMessage) -> None:
        if message.request_id not in self.requests:
            self._send_retransmit_for_request(message.request_id)

    def _detect_missing_sequences(self) -> None:
        if not self.received_sequence_numbers:
            return
        max_seen = max(self.received_sequence_numbers)
        for sequence_number in range(self.sequence_frontier + 1, max_seen):
            self._send_retransmit_for_sequence(sequence_number)

    def _send_retransmit_for_request(self, request_id: RequestId) -> None:
        message = RetransmitRequestMessage(
            source_replica_id=self.replica_id,
            target_replica_id=request_id.sender_id,
            missing_kind="request",
            request_id=request_id,
            global_sequence=None,
            request_frontier=self.request_frontier.copy(),
            sequence_frontier=self.sequence_frontier,
        )
        self.transport.send(request_id.sender_id, message)

    def _send_retransmit_for_sequence(self, sequence_number: int) -> None:
        sequencer_id = sequence_number % self.num_replicas
        message = RetransmitRequestMessage(
            source_replica_id=self.replica_id,
            target_replica_id=sequencer_id,
            missing_kind="sequence",
            request_id=None,
            global_sequence=sequence_number,
            request_frontier=self.request_frontier.copy(),
            sequence_frontier=self.sequence_frontier,
        )
        self.transport.send(sequencer_id, message)

    def _send_progress_ping(self, target_replica_id: int) -> None:
        message = RetransmitRequestMessage(
            source_replica_id=self.replica_id,
            target_replica_id=target_replica_id,
            missing_kind="request",
            request_id=None,
            global_sequence=None,
            request_frontier=self.request_frontier.copy(),
            sequence_frontier=self.sequence_frontier,
        )
        self.transport.send(target_replica_id, message)

    def _broadcast_progress_ping(self) -> None:
        for replica_id in range(self.num_replicas):
            if replica_id == self.replica_id:
                continue
            self._send_progress_ping(replica_id)

    def _update_request_frontier(self, sender_id: int) -> None:
        frontier = self.request_frontier[sender_id]
        while frontier + 1 in self.received_request_numbers[sender_id]:
            frontier += 1
        self.request_frontier[sender_id] = frontier
        self._update_self_progress()

    def _update_sequence_frontier(self) -> None:
        frontier = self.sequence_frontier
        while frontier + 1 in self.received_sequence_numbers:
            frontier += 1
        self.sequence_frontier = frontier
        self._update_self_progress()

    def _record_peer_progress(self, peer_id: int, request_frontier: list[int], sequence_frontier: int) -> None:
        current_request_frontier = self.peer_request_frontier[peer_id]
        self.peer_request_frontier[peer_id] = [
            max(current_request_frontier[idx], request_frontier[idx])
            for idx in range(self.num_replicas)
        ]
        self.peer_sequence_frontier[peer_id] = max(self.peer_sequence_frontier[peer_id], sequence_frontier)

    def _update_self_progress(self) -> None:
        self.peer_request_frontier[self.replica_id] = self.request_frontier.copy()
        self.peer_sequence_frontier[self.replica_id] = self.sequence_frontier

    def debug_summary(self) -> dict[str, object]:
        with self._lock:
            return {
                "replica_id": self.replica_id,
                "local_request_seq": self.local_request_seq,
                "next_delivery_sequence": self.next_delivery_sequence,
                "request_ids": [repr(r) for r in sorted(self.requests.keys())],
                "sequence_to_request": {k: repr(v) for k, v in sorted(self.sequence_to_request.items())},
                "request_frontier": list(self.request_frontier),
                "sequence_frontier": self.sequence_frontier,
                "peer_request_frontier": {k: list(v) for k, v in self.peer_request_frontier.items()},
                "peer_sequence_frontier": dict(self.peer_sequence_frontier),
                "delivered_request_ids": [repr(r) for r in sorted(self.delivered_request_ids)],
            }

    def _debug(self, message: str) -> None:
        if self.debug_enabled:
            print(f"[customer-db-repl replica={self.replica_id}] {message}", flush=True)
