from __future__ import annotations

import requests


class BuyerRestClient:
    """
    Thin REST client for the buyer-facing API.
    Assumes the backend buyer server exposes the PA2-style REST endpoints.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8001):
        self.base = f"http://{host}:{port}"
        self.session_id: str | None = None
        self.buyer_id: int | None = None

    def create_account(self, username: str, password: str) -> int:
        resp = requests.post(
            f"{self.base}/buyer/account",
            json={"username": username, "password": password},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        self.buyer_id = payload["buyer_id"]
        return self.buyer_id

    def login(self, username: str, password: str) -> int:
        resp = requests.post(
            f"{self.base}/buyer/login",
            json={"username": username, "password": password},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        self.session_id = payload["session_id"]
        self.buyer_id = payload["buyer_id"]
        return self.buyer_id

    def logout(self) -> None:
        self._auth_post(f"{self.base}/buyer/logout")
        self.session_id = None

    def search_items(self, category: int = 0, keywords: list[str] | None = None) -> list[dict]:
        params = {"category": int(category)}
        if keywords:
            params["keywords"] = ",".join(keywords)
        resp = requests.get(f"{self.base}/buyer/items", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json().get("items", [])

    def get_item(self, item_id: int) -> dict:
        resp = requests.get(f"{self.base}/buyer/items/{item_id}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def add_to_cart(self, item_id: int, quantity: int) -> None:
        self._auth_post(
            f"{self.base}/buyer/cart/items",
            json={"item_id": int(item_id), "quantity": int(quantity)},
        )

    def remove_from_cart(self, item_id: int) -> None:
        resp = requests.delete(
            f"{self.base}/buyer/cart/items/{int(item_id)}",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()

    def display_cart(self) -> list[dict]:
        resp = self._auth_get(f"{self.base}/buyer/cart")
        return resp.json().get("items", [])

    def save_cart(self) -> None:
        self._auth_post(f"{self.base}/buyer/cart/save")

    def clear_cart(self) -> None:
        resp = requests.delete(
            f"{self.base}/buyer/cart/clear",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()

    def provide_feedback(self, item_id: int, is_positive: bool) -> None:
        self._auth_post(
            f"{self.base}/buyer/feedback",
            json={"item_id": int(item_id), "is_positive": bool(is_positive)},
        )

    def get_purchase_history(self) -> list[dict]:
        resp = self._auth_get(f"{self.base}/buyer/purchases")
        return resp.json().get("records", [])

    def make_purchase(self, username: str, credit_card_number: str, expiration_date: str, security_code: str) -> dict:
        resp = self._auth_post(
            f"{self.base}/buyer/purchase",
            json={
                "username": username,
                "credit_card_number": credit_card_number,
                "expiration_date": expiration_date,
                "security_code": security_code,
            },
        )
        return resp.json()

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.session_id:
            headers["x-session-id"] = str(self.session_id)
        return headers

    def _auth_post(self, url: str, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        resp = requests.post(url, headers=headers, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    def _auth_get(self, url: str, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        resp = requests.get(url, headers=headers, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp
