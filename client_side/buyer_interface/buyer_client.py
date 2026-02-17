from pathlib import Path
import sys
import time

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


class BuyerClient:
    def __init__(self, tcp_client):
        self.tcp = tcp_client
        self.session_id = None
        self.buyer_id = None

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
        return data["buyer_id"]

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
        self.buyer_id = data["buyer_id"]
        return self.session_id

    def logout(self):
        self._require_session()
        req = build_request(
            api="Logout",
            session_id=self.session_id,
            payload={}
        )
        self.tcp.send_request(req)
        self.session_id = None
        self.buyer_id = None

    # ---------- Search / Browse ----------

    def search_items(self, category: int, keywords: list[str]):
        self._require_session()
        req = build_request(
            api="SearchItemsForSale",
            session_id=self.session_id,
            payload={
                "category": category,
                "keywords": keywords
            }
        )
        resp = self.tcp.send_request(req)
        return extract_payload(resp)["items"]

    def get_item(self, item_id: str):
        self._require_session()
        req = build_request(
            api="GetItem",
            session_id=self.session_id,
            payload={
                "item_id": item_id
            }
        )
        resp = self.tcp.send_request(req)
        return extract_payload(resp)

    # ---------- Cart Operations ----------

    def add_item_to_cart(self, item_id: str, quantity: int):
        self._require_session()
        req = build_request(
            api="AddItemToCart",
            session_id=self.session_id,
            payload={
                "item_id": item_id,
                "quantity": quantity
            }
        )
        resp = self.tcp.send_request(req)
        return extract_payload(resp)

    def remove_item_from_cart(self, item_id: str, quantity: int):
        self._require_session()
        req = build_request(
            api="RemoveItemFromCart",
            session_id=self.session_id,
            payload={
                "item_id": item_id,
                "quantity": quantity
            }
        )
        resp = self.tcp.send_request(req)
        return extract_payload(resp)

    def display_cart(self):
        self._require_session()
        req = build_request(
            api="DisplayCart",
            session_id=self.session_id,
            payload={}
        )
        resp = self.tcp.send_request(req)
        return extract_payload(resp)["cart"]

    def clear_cart(self):
        self._require_session()
        req = build_request(
            api="ClearCart",
            session_id=self.session_id,
            payload={}
        )
        self.tcp.send_request(req)

    def save_cart(self):
        self._require_session()
        req = build_request(
            api="SaveCart",
            session_id=self.session_id,
            payload={}
        )
        self.tcp.send_request(req)

    # ---------- Feedback / History ----------

    def provide_feedback(self, item_id: str, thumbs_up: bool):
        self._require_session()
        req = build_request(
            api="ProvideFeedback",
            session_id=self.session_id,
            payload={
                "item_id": item_id,
                "thumbs_up": thumbs_up
            }
        )
        self.tcp.send_request(req)

    def get_seller_rating(self, seller_id: int):
        self._require_session()
        req = build_request(
            api="GetSellerRating",
            session_id=self.session_id,
            payload={
                "seller_id": seller_id
            }
        )
        resp = self.tcp.send_request(req)
        return extract_payload(resp)

    def get_purchase_history(self):
        self._require_session()
        req = build_request(
            api="GetBuyerPurchases",
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
                "Buyer must be logged in to perform this operation"
            )

if __name__ == "__main__":
    tcp = TCPClient("127.0.0.1", 8081)
    client = BuyerClient(tcp)

    username = f"buyer_{int(time.time())}"
    password = "password123"

    try:
        # try:
        #     buyer_id = client.create_account(username, password)
        #     print(f"Created buyer {buyer_id} (username={username})")
        # except ClientProtocolError:
        #     print(f"Account {username} exists, logging in...")

        session_id = client.login("buyer_1770342938", password)
        print(f"Logged in. session_id={session_id}")

        # Search items (category 0 with keywords)
        items = client.search_items(category=3, keywords=["dell", "i5"])
        print("SearchItemsForSale:", items)

        test_item_id = None
        if items:
            test_item_id = items[0]["item_id"]
            item_details = client.get_item(test_item_id)
            print("GetItem:", item_details)

            # Cart operations
            client.add_item_to_cart(test_item_id, 1)
            print("Added to cart:", client.display_cart())
            


        # client.logout()
        # print("Logged out.")
    finally:
        tcp.close()
