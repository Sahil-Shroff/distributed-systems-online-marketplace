import requests


class SellerRestClient:
    """
    Lightweight REST client for the seller REST API (FastAPI).
    Keeps behavior similar to the TCP SellerClient but communicates over HTTP.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8000):
        self.base = f"http://{host}:{port}"
        self.session_id = None
        self.seller_id = None

    # --- Auth ---
    def create_account(self, username: str, password: str) -> int:
        resp = requests.post(f"{self.base}/seller/account", json={"username": username, "password": password})
        resp.raise_for_status()
        self.seller_id = resp.json()["seller_id"]
        return self.seller_id

    def login(self, username: str, password: str) -> int:
        resp = requests.post(f"{self.base}/seller/login", json={"username": username, "password": password})
        resp.raise_for_status()
        data = resp.json()
        self.session_id = data["session_id"]
        self.seller_id = data["seller_id"]
        return self.seller_id

    def logout(self):
        self._auth_post(f"{self.base}/seller/logout")
        self.session_id = None

    # --- Items ---
    def register_item_for_sale(self, item_name: str, category: int, keywords, condition: str, price: float, quantity: int) -> int:
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

    def change_item_price(self, item_id: int, new_price: float):
        self._auth_put(f"{self.base}/seller/items/{item_id}/price", json={"price": float(new_price)})

    def update_units_for_sale(self, item_id: int, quantity_delta: int):
        resp = self._auth_put(f"{self.base}/seller/items/{item_id}/quantity", json={"quantity_delta": int(quantity_delta)})
        return resp.json().get("new_quantity")

    def display_items_for_sale(self):
        resp = self._auth_get(f"{self.base}/seller/items")
        return resp.json().get("items", [])

    def get_item(self, item_id: int):
        resp = requests.get(f"{self.base}/seller/items/{item_id}", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def get_rating(self):
        resp = self._auth_get(f"{self.base}/seller/rating")
        return resp.json()

    # --- Helpers ---
    def _headers(self):
        headers = {}
        if self.session_id:
            headers["x-session-id"] = str(self.session_id)
        return headers

    def _auth_post(self, url, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        resp = requests.post(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    def _auth_put(self, url, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        resp = requests.put(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    def _auth_get(self, url, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        resp = requests.get(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp
