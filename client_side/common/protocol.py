import uuid


def build_request(api: str, session_id: str | None, payload: dict) -> dict:
    return {
        "type": "request",
        "api": api,
        "session_id": session_id,
        "payload": payload
    }


def is_error(response: dict) -> bool:
    return response.get("type") == "error"


def validate_response(response: dict):
    if not isinstance(response, dict):
        raise ValueError("Response is not a dictionary")

    if "type" not in response:
        raise ValueError("Missing 'type' field in response")

    if response["type"] not in ("response", "error"):
        raise ValueError(f"Invalid response type: {response['type']}")

    if "api" not in response:
        raise ValueError("Missing 'api' field in response")

    if response["type"] == "error":
        if "error" not in response:
            raise ValueError("Error response missing 'error' field")
        if "code" not in response["error"] or "message" not in response["error"]:
            raise ValueError("Malformed error object")

    if response["type"] == "response":
        if "payload" not in response:
            raise ValueError("Response missing 'payload' field")


def extract_payload(response: dict) -> dict:
    validate_response(response)
    if response["type"] == "error":
        raise ClientProtocolError(
            response["error"]["code"],
            response["error"]["message"]
        )
    return response.get("payload", {})


class ClientProtocolError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")
