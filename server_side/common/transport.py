import json
import socket
import struct
from typing import Any, Dict


class LengthPrefixedJSONConnection:

    def __init__(self, sock: socket.socket):
        self.sock = sock

    def _recv_all(self, n: int) -> bytes:
        chunks = []
        bytes_received = 0
        while bytes_received < n:
            chunk = self.sock.recv(n - bytes_received)
            if chunk == b"":
                raise ConnectionError("Socket connection broken")
            chunks.append(chunk)
            bytes_received += len(chunk)
        return b"".join(chunks)

    def _send_all(self, data: bytes):
        total_sent = 0
        while total_sent < len(data):
            sent = self.sock.send(data[total_sent:])
            if sent == 0:
                raise ConnectionError("Socket connection broken")
            total_sent += sent

    # --- Public API ---
    def recv_message(self) -> Dict[str, Any]:
        length_prefix = self._recv_all(4)
        msg_length = struct.unpack("!I", length_prefix)[0]
        payload = self._recv_all(msg_length)
        try:
            return json.loads(payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError(f"Invalid JSON payload: {exc}") from exc

    def send_message(self, message: Dict[str, Any]):
        try:
            payload = json.dumps(message).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Unable to encode message as JSON: {exc}") from exc

        prefix = struct.pack("!I", len(payload))
        self._send_all(prefix + payload)
