from pathlib import Path
import sys
from typing import Any, Dict

# for `server_side.*` imports resolve
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server_side.common.protocol import build_response, build_error
from server_side.common.server import Server
from server_side.seller_interface.handlers import HANDLERS

class SellerServer(Server):
    def __init__(self, host: str, port: int):
        super().__init__(host, port)
        self.handlers = HANDLERS

    def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        api = request.get("api")
        session_id = request.get("session_id")

        if api not in self.handlers:
            return build_error(
                api=api,
                code="404_NOT_FOUND",
                message=f"UNKOWN_API {api}",
                session_id=session_id
            )
        
        handler = self.handlers.get(api)
        response_payload = handler(request, self.db_conns)
        session_id = response_payload.get("session_id")
        print("response_payload", response_payload)

        return build_response(api=api, payload=response_payload, session_id=session_id)
    

if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 8080
    server = SellerServer(HOST, PORT)
    try:
        server.start()
    except KeyboardInterrupt:
        print("Shutting down server...")
        server.stop()
