from __future__ import annotations

import requests


class SellerRestClient:
    """
    Thin REST client for the seller-facing API.
    Assumes the backend seller server exposes the PA2-style REST endpoints.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8000):
        self.base = f"http://{host}:{port}"
        self.session_id: str | None = None
        self.seller_id: int | None = None

    def create_account(self, username: str, password: str) -> int:
        resp = requests.post(
            f"{self.base}/seller/account",
            json={"username": username, "password": password},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        self.seller_id = payload["seller_id"]
        return self.seller_id

    def login(self, username: str, password: str) -> int:
        resp = requests.post(
            f"{self.base}/seller/login",
            json={"username": username, "password": password},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        self.session_id = payload["session_id"]
        self.seller_id = payload["seller_id"]
        return self.seller_id

    def logout(self) -> None:
        self._auth_post(f"{self.base}/seller/logout")
        self.session_id = None

    def register_item_for_sale(
        self,
        item_name: str,
        category: int,
        keywords: list[str],
        condition: str,
        price: float,
        quantity: int,
    ) -> int:
        body = {
            "item_name": item_name,
            "category": int(category),
            "keywords": list(keywords),
            "condition": condition,
            "price": float(price),
            "quantity": int(quantity),
        }
        resp = self._auth_post(f"{self.base}/seller/items", json=body)
        return resp.json()["item_id"]

    def change_item_price(self, item_id: int, new_price: float) -> None:
        self._auth_put(
            f"{self.base}/seller/items/{item_id}/price",
            json={"price": float(new_price)},
        )

    def update_units_for_sale(self, item_id: int, quantity_delta: int) -> int | None:
        resp = self._auth_put(
            f"{self.base}/seller/items/{item_id}/quantity",
            json={"quantity_delta": int(quantity_delta)},
        )
        return resp.json().get("new_quantity")

    def display_items_for_sale(self) -> list[dict]:
        resp = self._auth_get(f"{self.base}/seller/items")
        return resp.json().get("items", [])

    def get_item(self, item_id: int) -> dict:
        resp = requests.get(
            f"{self.base}/seller/items/{item_id}",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_rating(self) -> dict:
        resp = self._auth_get(f"{self.base}/seller/rating")
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

    def _auth_put(self, url: str, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        resp = requests.put(url, headers=headers, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    def _auth_get(self, url: str, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        resp = requests.get(url, headers=headers, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp
