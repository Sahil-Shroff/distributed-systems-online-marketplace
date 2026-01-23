# non-blocking server for seller interface
import logging
import socket
import sys
from pathlib import Path
from threading import Thread
from typing import Any, Dict

# for `server_side.*` imports resolve
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server_side.common.protocol import (
    build_error,
    build_response,
    validate_request,
    ServerProtocolError,
)
from server_side.common.transport import LengthPrefixedJSONConnection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Server:
    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = 1.0
        self._running = True
        self._setup()

    def _setup(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.settimeout(self.timeout)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        logger.info("Server listening on %s:%s", self.host, self.port)

    def stop(self):
        self._running = False
        try:
            self.server_socket.close()
        except Exception:
            pass

    def start(self):
        try:
            while self._running:
                try:
                    client_socket, addr = self.server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if not self._running:
                        break
                    raise

                logger.info("Accepted connection from %s", addr)
                client_thread = Thread(
                    target=self.handle_client, args=(client_socket, addr), daemon=True
                )
                client_thread.start()
        except KeyboardInterrupt:
            logger.info("Shutting down server.")
        finally:
            self.stop()

    def handle_client(self, client_socket: socket.socket, addr):
        conn = LengthPrefixedJSONConnection(client_socket)
        with client_socket:
            while True:
                try:
                    message = conn.recv_message()
                    logger.debug("Received message from %s: %s", addr, message)
                    request = validate_request(message)
                    response = self.process_request(request)
                except ServerProtocolError as exc:
                    logger.warning("Protocol error from %s: %s", addr, exc)
                    response = build_error(
                        api=message.get("api", "UNKNOWN") if isinstance(message, dict) else "UNKNOWN",
                        code=exc.code,
                        message=exc.message,
                        session_id=message.get("session_id") if isinstance(message, dict) else None,
                    )
                except ConnectionError:
                    logger.info("Client %s disconnected", addr)
                    break
                except Exception as exc:
                    logger.exception("Unexpected server error for %s", addr)
                    response = build_error(
                        api=message.get("api", "UNKNOWN") if isinstance(message, dict) else "UNKNOWN",
                        code="SERVER_ERROR",
                        message=str(exc),
                        session_id=message.get("session_id") if isinstance(message, dict) else None,
                    )
                    try:
                        conn.send_message(response)
                    finally:
                        break

                try:
                    conn.send_message(response)
                except ConnectionError:
                    logger.info("Client %s disconnected during send", addr)
                    break

    def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        api = request["api"]
        payload = request["payload"]
        session_id = request.get("session_id")

        print("debug")
        # Placeholder. To be overrided
        return build_response(
            api=api,
            payload={"echo": "Implement this API", "status": "success"},
            session_id=session_id,
        )


if __name__ == "__main__":
    server = Server(host="localhost", port=8080)
    server.start()
