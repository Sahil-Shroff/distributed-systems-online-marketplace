from __future__ import annotations

import requests


class SellerRestClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8000):
        self.bases = self._build_bases(host, port)
        self._active_base_idx = 0
        self.session_id: str | None = None
        self.seller_id: int | None = None

    def create_account(self, username: str, password: str) -> int:
        resp = self._request_with_failover(
            "POST",
            "/seller/account",
            json={"username": username, "password": password},
            include_auth=False,
        )
        payload = resp.json()
        self.seller_id = payload["seller_id"]
        return self.seller_id

    def login(self, username: str, password: str) -> int:
        resp = self._request_with_failover(
            "POST",
            "/seller/login",
            json={"username": username, "password": password},
            include_auth=False,
        )
        payload = resp.json()
        self.session_id = payload["session_id"]
        self.seller_id = payload["seller_id"]
        return self.seller_id

    def logout(self) -> None:
        self._request_with_failover("POST", "/seller/logout")
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
        resp = self._request_with_failover(
            "POST",
            "/seller/items",
            json={
                "item_name": item_name,
                "category": int(category),
                "keywords": list(keywords),
                "condition": condition,
                "price": float(price),
                "quantity": int(quantity),
            },
        )
        return resp.json()["item_id"]

    def change_item_price(self, item_id: int, new_price: float) -> None:
        self._request_with_failover(
            "PUT",
            f"/seller/items/{item_id}/price",
            json={"price": float(new_price)},
        )

    def update_units_for_sale(self, item_id: int, quantity_delta: int) -> int | None:
        resp = self._request_with_failover(
            "PUT",
            f"/seller/items/{item_id}/quantity",
            json={"quantity_delta": int(quantity_delta)},
        )
        return resp.json().get("new_quantity")

    def display_items_for_sale(self) -> list[dict]:
        resp = self._request_with_failover("GET", "/seller/items")
        return resp.json().get("items", [])

    def get_item(self, item_id: int) -> dict:
        resp = self._request_with_failover("GET", f"/seller/items/{item_id}")
        return resp.json()

    def get_rating(self) -> dict:
        resp = self._request_with_failover("GET", "/seller/rating")
        return resp.json()

    def _build_bases(self, host: str, port: int) -> list[str]:
        targets = [part.strip() for part in host.split(",") if part.strip()]
        if not targets:
            targets = [host]
        bases = []
        for target in targets:
            if target.startswith("http://") or target.startswith("https://"):
                bases.append(target.rstrip("/"))
            elif ":" in target:
                bases.append(f"http://{target}")
            else:
                bases.append(f"http://{target}:{port}")
        return bases

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.session_id:
            headers["x-session-id"] = str(self.session_id)
        return headers

    def _request_with_failover(self, method: str, path: str, *, include_auth: bool = True, **kwargs):
        extra_headers = dict(kwargs.pop("headers", {}))
        last_error = None
        for offset in range(len(self.bases)):
            idx = (self._active_base_idx + offset) % len(self.bases)
            headers = dict(extra_headers)
            if include_auth:
                headers.update(self._headers())
            try:
                resp = requests.request(
                    method,
                    f"{self.bases[idx]}{path}",
                    headers=headers,
                    timeout=30,
                    **kwargs,
                )
                resp.raise_for_status()
                self._active_base_idx = idx
                return resp
            except requests.RequestException as exc:
                last_error = exc
        raise last_error
