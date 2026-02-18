import requests

class SellerRESTClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session_id = None
        self.seller_id = None

    def _get_headers(self):
        return {"X-Session-ID": self.session_id} if self.session_id else {}

    def create_account(self, username, password):
        resp = requests.post(f"{self.base_url}/seller/account", json={
            "username": username, "password": password
        })
        resp.raise_for_status()
        self.seller_id = resp.json()["seller_id"]
        return self.seller_id

    def login(self, username, password):
        resp = requests.post(f"{self.base_url}/seller/login", json={
            "username": username, "password": password
        })
        resp.raise_for_status()
        data = resp.json()
        self.session_id = data["session_id"]
        self.seller_id = data["seller_id"]
        return self.session_id

    def logout(self):
        resp = requests.post(f"{self.base_url}/seller/logout", headers=self._get_headers())
        resp.raise_for_status()
        self.session_id = None
        return resp.json()["status"]

    def get_seller_rating(self):
        resp = requests.get(f"{self.base_url}/seller/rating", headers=self._get_headers())
        resp.raise_for_status()
        return resp.json()

    def register_item(self, name, category, keywords, condition, price, quantity):
        resp = requests.post(f"{self.base_url}/seller/items", headers=self._get_headers(), json={
            "item_name": name, "category": category, "keywords": keywords,
            "condition": condition, "price": float(price), "quantity": int(quantity)
        })
        resp.raise_for_status()
        return resp.json()["item_id"]

    def update_price(self, item_id, price):
        resp = requests.put(f"{self.base_url}/seller/items/{item_id}/price", headers=self._get_headers(), json={
            "price": float(price)
        })
        resp.raise_for_status()
        return resp.json()["status"]

    def update_quantity(self, item_id, delta):
        resp = requests.put(f"{self.base_url}/seller/items/{item_id}/quantity", headers=self._get_headers(), json={
            "quantity_delta": int(delta)
        })
        resp.raise_for_status()
        return resp.json()

    def display_items(self):
        resp = requests.get(f"{self.base_url}/seller/items", headers=self._get_headers())
        resp.raise_for_status()
        return resp.json()["items"]
