from __future__ import annotations

import os
import threading
import time

from server_side.customer_db.operations import Operation
from server_side.customer_db.replication.messages import ProtocolMessage, RequestMessage, RetransmitRequestMessage, SequenceMessage
from server_side.customer_db.replication.node import DeliveredRecord, RotatingSequencerNode
from server_side.customer_db.replication.udp_transport import UdpReplicationTransport


def _parse_peer_addresses(raw: str) -> dict[int, tuple[str, int]]:
    peers: dict[int, tuple[str, int]] = {}
    for entry in raw.split(","):
        item = entry.strip()
        if not item:
            continue
        replica_id_raw, host, port_raw = item.split(":")
        peers[int(replica_id_raw)] = (host, int(port_raw))
    return peers


class CustomerDbReplicationRuntime:
    def __init__(self, node: RotatingSequencerNode, transport: UdpReplicationTransport, scan_interval_seconds: float):
        self.node = node
        self.transport = transport
        self.scan_interval_seconds = scan_interval_seconds
        self._running = False
        self._scan_thread: threading.Thread | None = None
        self.debug_enabled = os.getenv("CUSTOMER_DB_REPLICATION_DEBUG", "0") == "1"

    @classmethod
    def from_env(cls, apply_callback) -> CustomerDbReplicationRuntime | None:
        peers_raw = os.getenv("CUSTOMER_DB_REPLICA_PEERS", "").strip()
        replica_id_raw = os.getenv("CUSTOMER_DB_REPLICA_ID", "").strip()
        if not peers_raw or not replica_id_raw:
            return None
        replica_id = int(replica_id_raw)
        peer_addresses = _parse_peer_addresses(peers_raw)
        if replica_id not in peer_addresses:
            raise RuntimeError(f"Replica ID {replica_id} missing from CUSTOMER_DB_REPLICA_PEERS")
        bind_host = os.getenv("CUSTOMER_DB_REPLICATION_BIND_HOST", peer_addresses[replica_id][0])
        bind_port = int(os.getenv("CUSTOMER_DB_REPLICATION_BIND_PORT", str(peer_addresses[replica_id][1])))
        scan_interval_seconds = float(os.getenv("CUSTOMER_DB_REPLICATION_SCAN_INTERVAL", "0.2"))
        transport = UdpReplicationTransport(
            replica_id=replica_id,
            bind_host=bind_host,
            bind_port=bind_port,
            peer_addresses=peer_addresses,
        )
        node = RotatingSequencerNode(
            replica_id=replica_id,
            num_replicas=len(peer_addresses),
            transport=transport,
            apply_callback=apply_callback,
        )
        return cls(node=node, transport=transport, scan_interval_seconds=scan_interval_seconds)

    def start(self) -> None:
        self.transport.start(self._handle_message)
        self._running = True
        self._scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._scan_thread.start()

    def stop(self) -> None:
        self._running = False
        self.transport.stop()
        if self._scan_thread is not None:
            self._scan_thread.join(timeout=1)

    def submit(self, operation: Operation, timeout: float | None = None) -> DeliveredRecord:
        try:
            return self.node.submit_client_mutation(operation, timeout=timeout)
        except TimeoutError:
            if self.debug_enabled:
                print(
                    f"[customer-db-repl runtime replica={self.node.replica_id}] timeout waiting for delivery; "
                    f"state={self.node.debug_summary()}",
                    flush=True,
                )
            raise

    def _scan_loop(self) -> None:
        while self._running:
            time.sleep(self.scan_interval_seconds)
            self.node.periodic_retransmit_scan()

    def _handle_message(self, message: ProtocolMessage) -> None:
        if isinstance(message, RequestMessage):
            self.node.on_request_receive(message)
            return
        if isinstance(message, SequenceMessage):
            self.node.on_sequence_receive(message)
            return
        if isinstance(message, RetransmitRequestMessage):
            self.node.on_retransmit_request_receive(message)
            return
        raise TypeError(type(message))
