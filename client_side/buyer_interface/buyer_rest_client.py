import requests

class BuyerRESTClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session_id = None
        self.buyer_id = None

    def _get_headers(self):
        return {"X-Session-ID": self.session_id} if self.session_id else {}

    def create_account(self, username, password):
        resp = requests.post(f"{self.base_url}/buyer/account", json={
            "username": username, "password": password
        })
        resp.raise_for_status()
        self.buyer_id = resp.json()["buyer_id"]
        return self.buyer_id

    def login(self, username, password):
        resp = requests.post(f"{self.base_url}/buyer/login", json={
            "username": username, "password": password
        })
        resp.raise_for_status()
        data = resp.json()
        self.session_id = data["session_id"]
        self.buyer_id = data["buyer_id"]
        return self.session_id

    def logout(self):
        resp = requests.post(f"{self.base_url}/buyer/logout", headers=self._get_headers())
        resp.raise_for_status()
        self.session_id = None
        return resp.json()["status"]

    def search_items(self, category=0, keywords=""):
        params = {"category": category, "keywords": ",".join(keywords) if isinstance(keywords, list) else keywords}
        resp = requests.get(f"{self.base_url}/buyer/items", params=params)
        resp.raise_for_status()
        return resp.json()["items"]

    def get_item(self, item_id):
        resp = requests.get(f"{self.base_url}/buyer/items/{item_id}")
        resp.raise_for_status()
        return resp.json()

    def add_item_to_cart(self, item_id, quantity):
        resp = requests.post(f"{self.base_url}/buyer/cart", headers=self._get_headers(), json={
            "item_id": item_id, "quantity": quantity
        })
        resp.raise_for_status()
        return resp.json()["status"]

    def display_cart(self):
        resp = requests.get(f"{self.base_url}/buyer/cart", headers=self._get_headers())
        resp.raise_for_status()
        return resp.json()["cart"]

    def save_cart(self):
        resp = requests.post(f"{self.base_url}/buyer/cart/save", headers=self._get_headers())
        resp.raise_for_status()
        return resp.json()["status"]

    def clear_cart(self):
        resp = requests.delete(f"{self.base_url}/buyer/cart/all", headers=self._get_headers())
        resp.raise_for_status()
        return resp.json()["status"]

    def provide_feedback(self, item_id, is_positive):
        resp = requests.post(f"{self.base_url}/buyer/feedback", headers=self._get_headers(), json={
            "item_id": item_id, "is_positive": is_positive
        })
        resp.raise_for_status()
        return resp.json()["status"]

    def get_seller_rating(self, seller_id):
        resp = requests.get(f"{self.base_url}/seller/{seller_id}/rating")
        resp.raise_for_status()
        return resp.json()

    def get_purchase_history(self):
        resp = requests.get(f"{self.base_url}/buyer/purchases", headers=self._get_headers())
        resp.raise_for_status()
        return resp.json()["purchases"]

    def make_purchase(self, name, card_num, expiry, code):
        resp = requests.post(f"{self.base_url}/buyer/purchase", headers=self._get_headers(), json={
            "name": name,
            "card_number": card_num,
            "expiration_date": expiry,
            "security_code": code
        })
        resp.raise_for_status()
        return resp.json()
