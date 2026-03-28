from __future__ import annotations

import requests


class BuyerRestClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8001):
        self.bases = self._build_bases(host, port)
        self._active_base_idx = 0
        self.session_id: str | None = None
        self.buyer_id: int | None = None

    def create_account(self, username: str, password: str) -> int:
        resp = self._request_with_failover(
            "POST",
            "/buyer/account",
            json={"username": username, "password": password},
            include_auth=False,
        )
        payload = resp.json()
        self.buyer_id = payload["buyer_id"]
        return self.buyer_id

    def login(self, username: str, password: str) -> int:
        resp = self._request_with_failover(
            "POST",
            "/buyer/login",
            json={"username": username, "password": password},
            include_auth=False,
        )
        payload = resp.json()
        self.session_id = payload["session_id"]
        self.buyer_id = payload["buyer_id"]
        return self.buyer_id

    def logout(self) -> None:
        self._request_with_failover("POST", "/buyer/logout")
        self.session_id = None

    def search_items(self, category: int = 0, keywords: list[str] | None = None) -> list[dict]:
        params = {"category": int(category)}
        if keywords:
            params["keywords"] = ",".join(keywords)
        resp = self._request_with_failover("GET", "/buyer/items", params=params, include_auth=False)
        return resp.json().get("items", [])

    def get_item(self, item_id: int) -> dict:
        resp = self._request_with_failover("GET", f"/buyer/items/{item_id}", include_auth=False)
        return resp.json()

    def add_to_cart(self, item_id: int, quantity: int) -> None:
        self._request_with_failover(
            "POST",
            "/buyer/cart",
            json={"item_id": int(item_id), "quantity": int(quantity)},
        )

    def remove_from_cart(self, item_id: int) -> None:
        self._request_with_failover("DELETE", f"/buyer/cart/{int(item_id)}")

    def display_cart(self) -> list[dict]:
        resp = self._request_with_failover("GET", "/buyer/cart")
        return resp.json().get("cart", [])

    def save_cart(self) -> None:
        self._request_with_failover("POST", "/buyer/cart/save")

    def clear_cart(self) -> None:
        self._request_with_failover("DELETE", "/buyer/cart/clear")

    def provide_feedback(self, item_id: int, is_positive: bool) -> None:
        self._request_with_failover(
            "POST",
            "/buyer/feedback",
            json={"item_id": int(item_id), "is_positive": bool(is_positive)},
        )

    def get_seller_rating(self, seller_id: int) -> dict:
        resp = self._request_with_failover("GET", f"/seller/{seller_id}/rating", include_auth=False)
        return resp.json()

    def get_purchase_history(self) -> list[dict]:
        resp = self._request_with_failover("GET", "/buyer/purchases")
        return resp.json().get("purchases", [])

    def make_purchase(self, username: str, credit_card_number: str, expiration_date: str, security_code: str) -> dict:
        resp = self._request_with_failover(
            "POST",
            "/buyer/purchase",
            json={
                "name": username,
                "card_number": credit_card_number,
                "expiration_date": expiration_date,
                "security_code": security_code,
            },
        )
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
