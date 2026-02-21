import requests


class BuyerRestClient:
    """
    Lightweight REST client for the buyer FastAPI server.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8001):
        self.base = f"http://{host}:{port}"
        self.session_id = None
        self.buyer_id = None

    # --- Auth ---
    def create_account(self, username: str, password: str) -> int:
        resp = requests.post(f"{self.base}/buyer/account", json={"username": username, "password": password})
        resp.raise_for_status()
        self.buyer_id = resp.json()["buyer_id"]
        return self.buyer_id

    def login(self, username: str, password: str) -> int:
        resp = requests.post(f"{self.base}/buyer/login", json={"username": username, "password": password})
        resp.raise_for_status()
        data = resp.json()
        self.session_id = data["session_id"]
        self.buyer_id = data["buyer_id"]
        return self.buyer_id

    def logout(self):
        self._auth_post(f"{self.base}/buyer/logout")
        self.session_id = None

    # --- Items ---
    def search_items(self, category: int = 0, keywords=None):
        kw = ",".join(keywords) if keywords else ""
        resp = requests.get(f"{self.base}/buyer/items", params={"category": category, "keywords": kw})
        resp.raise_for_status()
        return resp.json().get("items", [])

    def get_item(self, item_id: int):
        resp = requests.get(f"{self.base}/buyer/items/{item_id}")
        resp.raise_for_status()
        return resp.json()

    # --- Cart ---
    def add_to_cart(self, item_id: int, quantity: int):
        self._auth_post(f"{self.base}/buyer/cart", json={"item_id": item_id, "quantity": quantity})

    def display_cart(self):
        resp = self._auth_get(f"{self.base}/buyer/cart")
        return resp.json().get("cart", [])

    def save_cart(self):
        self._auth_post(f"{self.base}/buyer/cart/save")

    def clear_cart(self):
        self._auth_delete(f"{self.base}/buyer/cart/all")

    # --- Feedback ---
    def provide_feedback(self, item_id: int, is_positive: bool):
        self._auth_post(f"{self.base}/buyer/feedback", json={"item_id": item_id, "is_positive": bool(is_positive)})

    # --- Purchase ---
    def purchase(self, name: str, card_number: str, expiration_date: str, security_code: str):
        resp = self._auth_post(
            f"{self.base}/buyer/purchase",
            json={
                "name": name,
                "card_number": card_number,
                "expiration_date": expiration_date,
                "security_code": security_code,
            },
        )
        return resp.json()

    # --- Helpers ---
    def _headers(self):
        h = {}
        if self.session_id:
            h["x-session-id"] = str(self.session_id)
        return h

    def _auth_post(self, url, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        resp = requests.post(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    def _auth_get(self, url, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        resp = requests.get(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    def _auth_delete(self, url, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        resp = requests.delete(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp
