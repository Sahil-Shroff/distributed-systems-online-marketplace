from pathlib import Path
import sys

# for `client_side.*` imports resolve
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from client_side.common.protocol import (
    build_request,
    extract_payload,
    ClientProtocolError
)
from client_side.common.tcp_client import TCPClient


class SellerClient:
    def __init__(self, tcp_client):
        self.tcp = tcp_client
        self.session_id = None
        self.seller_id = None

    # ---------- Account / Session ----------

    def create_account(self, username: str, password: str) -> int:
        req = build_request(
            api="CreateAccount",
            session_id=None,
            payload={
                "username": username,
                "password": password
            }
        )
        resp = self.tcp.send_request(req)
        data = extract_payload(resp)
        return data["seller_id"]

    def login(self, username: str, password: str) -> int:
        req = build_request(
            api="Login",
            session_id=None,
            payload={
                "username": username,
                "password": password
            }
        )
        resp = self.tcp.send_request(req)
        data = extract_payload(resp)

        self.session_id = resp.get("session_id")
        print(data, self.session_id)
        self.seller_id = data["seller_id"]
        return self.seller_id

    def logout(self):
        self._require_session()
        req = build_request(
            api="Logout",
            session_id=self.session_id,
            payload={}
        )
        self.tcp.send_request(req)
        self.session_id = None
        self.seller_id = None

    def get_seller_rating(self):
        self._require_session()
        req = build_request(
            api="GetSellerRating",
            session_id=self.session_id,
            payload={}
        )
        resp = self.tcp.send_request(req)
        return extract_payload(resp)

    # ---------- Item Management ----------

    def register_item_for_sale(
        self,
        item_name: str,
        category: int,
        keywords: list[str],
        condition: str,
        price: float,
        quantity: int
    ) -> str:
        self._require_session()
        req = build_request(
            api="RegisterItemForSale",
            session_id=self.session_id,
            payload={
                "item_name": item_name,
                "category": category,
                "keywords": keywords,
                "condition": condition,
                "price": price,
                "quantity": quantity
            }
        )
        resp = self.tcp.send_request(req)
        return extract_payload(resp)["item_id"]

    def change_item_price(self, item_id: str, new_price: float):
        self._require_session()
        req = build_request(
            api="ChangeItemPrice",
            session_id=self.session_id,
            payload={
                "item_id": item_id,
                "price": new_price
            }
        )
        self.tcp.send_request(req)

    def update_units_for_sale(self, item_id: str, delta: int):
        """
        delta: integer quantity to remove from units for sale
        """
        self._require_session()
        req = build_request(
            api="UpdateUnitsForSale",
            session_id=self.session_id,
            payload={
                "item_id": item_id,
                "quantity": delta
            }
        )
        self.tcp.send_request(req)

    def display_items_for_sale(self):
        self._require_session()
        req = build_request(
            api="DisplayItemsForSale",
            session_id=self.session_id,
            payload={}
        )
        resp = self.tcp.send_request(req)
        return extract_payload(resp)["items"]

    # ---------- Helpers ----------

    def _require_session(self):
        if not self.session_id:
            raise ClientProtocolError(
                "NOT_LOGGED_IN",
                "Seller must be logged in to perform this operation"
            )

if __name__ == "__main__":
    tcp = TCPClient('127.0.0.1', 8080)
    client = SellerClient(tcp)

    # response = client.create_account("test_seller", "password123")
    login_response = client.login("test_seller", "password123")
    print(login_response)