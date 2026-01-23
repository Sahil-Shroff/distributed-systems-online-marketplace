"""
Request:
{
    "type": "request",
    "api": "<ApiName>",
    "session_id": "<optional session id>",
    "payload": {...}
}

Response:
{
    "type": "response",
    "api": "<ApiName>",
    "session_id": "<optional session id>",
    "payload": {...}
}

Error:
{
    "type": "error",
    "api": "<ApiName>",
    "session_id": "<optional session id>",
    "error": {
        "code": "<ERROR_CODE>",
        "message": "<error message>"
    }
}
"""

from typing import Any, Dict, Optional


class ServerProtocolError(Exception):
    
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def validate_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the incoming request and return it back for convenience."""
    if not isinstance(request, dict):
        raise ServerProtocolError("BAD_REQUEST", "Request is not a dictionary")

    if request.get("type") != "request":
        raise ServerProtocolError("BAD_REQUEST", "Invalid or missing request type")

    if "api" not in request or not isinstance(request["api"], str):
        raise ServerProtocolError("BAD_REQUEST", "Missing or invalid 'api' field")

    if "payload" not in request or not isinstance(request["payload"], dict):
        raise ServerProtocolError("BAD_REQUEST", "Missing or invalid 'payload' field")

    # session_id can be None or a string; no strict validation for now
    return request


def build_response(api: str, payload: Dict[str, Any], session_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "type": "response",
        "api": api,
        "session_id": session_id,
        "payload": payload,
    }


def build_error(api: str, code: str, message: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "type": "error",
        "api": api,
        "session_id": session_id,
        "error": {
            "code": code,
            "message": message,
        },
    }
