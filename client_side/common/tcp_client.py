import socket
import struct
import json


class TCPClient:
    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None
        self._connect()

    def _connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def _send_all(self, data: bytes):
        total_sent = 0
        while total_sent < len(data):
            sent = self.sock.send(data[total_sent:])
            if sent == 0:
                raise ConnectionError("Socket connection broken")
            total_sent += sent

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

    def send_request(self, message: dict) -> dict:
        """
        Sends a single request and waits for a single response.
        Message must be a dict (JSON-serializable).
        Returns parsed response dict.
        """

        try:
            payload = json.dumps(message).encode("utf-8")
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid JSON message: {e}")

        length_prefix = struct.pack("!I", len(payload))
        self._send_all(length_prefix + payload)

        resp_len_bytes = self._recv_all(4)
        resp_len = struct.unpack("!I", resp_len_bytes)[0]

        resp_payload = self._recv_all(resp_len)
        try:
            response = json.loads(resp_payload.decode("utf-8"))
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid JSON response: {e}")

        return response
