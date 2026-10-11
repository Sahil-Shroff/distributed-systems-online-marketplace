from __future__ import annotations

import json
import os
import socket
import threading
from typing import Callable

from server_side.customer_db.replication.messages import ProtocolMessage, deserialize_message, serialize_message


class UdpReplicationTransport:
    def __init__(self, replica_id: int, bind_host: str, bind_port: int, peer_addresses: dict[int, tuple[str, int]]):
        self.replica_id = replica_id
        self.peer_addresses = peer_addresses
        self.debug_enabled = os.getenv("CUSTOMER_DB_REPLICATION_DEBUG", "0") == "1"
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((bind_host, bind_port))
        self.sock.settimeout(0.2)
        self._running = False
        self._thread: threading.Thread | None = None
        self._handler: Callable[[ProtocolMessage], None] | None = None

    def start(self, handler: Callable[[ProtocolMessage], None]) -> None:
        self._handler = handler
        self._running = True
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        try:
            self.sock.close()
        finally:
            if self._thread is not None:
                self._thread.join(timeout=1)

    def broadcast(self, message: ProtocolMessage) -> None:
        for replica_id in self.peer_addresses:
            self.send(replica_id, message)

    def send(self, target_replica_id: int, message: ProtocolMessage) -> None:
        payload = json.dumps(serialize_message(message)).encode("utf-8")
        if self.debug_enabled:
            print(
                f"[customer-db-repl udp replica={self.replica_id}] send kind={getattr(message, 'kind', '?')} "
                f"to={target_replica_id}",
                flush=True,
            )
        self.sock.sendto(payload, self.peer_addresses[target_replica_id])

    def _recv_loop(self) -> None:
        while self._running:
            try:
                data, _ = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            if self._handler is None:
                continue
            message = deserialize_message(json.loads(data.decode("utf-8")))
            if self.debug_enabled:
                print(
                    f"[customer-db-repl udp replica={self.replica_id}] recv kind={getattr(message, 'kind', '?')}",
                    flush=True,
                )
            self._handler(message)
