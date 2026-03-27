from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pysyncobj import SyncObj, SyncObjConf, replicated


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProductRaftStore(SyncObj):
    """Replicated in-memory product state machine backed by PySyncObj."""

    def __init__(self, self_addr: str, partner_addrs: list[str], dump_file: str, apply_listener=None):
        self._state_lock = threading.RLock()
        self._next_item_id = 1
        self._items: Dict[int, Dict[str, Any]] = {}
        self._cart_items: Dict[Tuple[int, str, int, bool], int] = {}
        self._purchases: List[Dict[str, Any]] = []
        self._apply_listener = apply_listener
        conf = SyncObjConf(
            dynamicMembershipChange=False,
            commandsWaitLeader=True,
            fullDumpFile=dump_file,
        )
        super().__init__(self_addr, partner_addrs, conf=conf)

    def status(self) -> dict[str, Any]:
        return self.getStatus()

    def _copy_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "item_id": item["item_id"],
            "item_name": item["item_name"],
            "category": item["category"],
            "keywords": list(item["keywords"]),
            "condition_is_new": item["condition_is_new"],
            "price": float(item["price"]),
            "quantity": int(item["quantity"]),
            "seller_id": int(item["seller_id"]),
            "item_feedback": list(item["item_feedback"]),
        }

    def _notify(self, event_type: str, payload: Dict[str, Any]):
        if self._apply_listener is not None:
            self._apply_listener(event_type, payload)

    def search_items(self, category: int, keywords: list[str]) -> list[dict[str, Any]]:
        with self._state_lock:
            out = []
            kw_set = {kw.strip() for kw in keywords if kw.strip()}
            for item in self._items.values():
                if item["quantity"] <= 0:
                    continue
                if category and item["category"] != category:
                    continue
                if kw_set and not kw_set.intersection(item["keywords"]):
                    continue
                out.append(self._copy_item(item))
            return out

    def get_item(self, item_id: int) -> Optional[dict[str, Any]]:
        with self._state_lock:
            item = self._items.get(item_id)
            return self._copy_item(item) if item else None

    def get_items_by_seller(self, seller_id: int) -> list[dict[str, Any]]:
        with self._state_lock:
            return [
                self._copy_item(item)
                for item in self._items.values()
                if item["seller_id"] == seller_id
            ]

    def list_cart(self, buyer_id: int, session_id: str) -> list[dict[str, int]]:
        with self._state_lock:
            items = []
            for (b_id, sess_id, item_id, is_saved), qty in self._cart_items.items():
                if b_id == buyer_id and sess_id == session_id and not is_saved:
                    items.append({"item_id": item_id, "quantity": qty})
            items.sort(key=lambda x: x["item_id"])
            return items

    def list_saved_cart(self, buyer_id: int) -> list[dict[str, int]]:
        with self._state_lock:
            items = []
            for (b_id, _sess_id, item_id, is_saved), qty in self._cart_items.items():
                if b_id == buyer_id and is_saved:
                    items.append({"item_id": item_id, "quantity": qty})
            items.sort(key=lambda x: x["item_id"])
            return items

    def get_purchase_history(self, buyer_id: int) -> list[dict[str, Any]]:
        with self._state_lock:
            rows = [
                {
                    "item_id": row["item_id"],
                    "quantity": row["quantity"],
                    "purchased_at": row["purchased_at"],
                }
                for row in self._purchases
                if row["buyer_id"] == buyer_id
            ]
            rows.sort(key=lambda x: x["purchased_at"], reverse=True)
            return rows

    def list_all_items(self) -> list[dict[str, Any]]:
        with self._state_lock:
            return [self._copy_item(item) for item in self._items.values()]

    def list_all_cart_rows(self) -> list[dict[str, Any]]:
        with self._state_lock:
            rows = []
            for (buyer_id, session_id, item_id, is_saved), quantity in self._cart_items.items():
                rows.append(
                    {
                        "buyer_id": buyer_id,
                        "session_id": session_id,
                        "item_id": item_id,
                        "quantity": quantity,
                        "is_saved": is_saved,
                    }
                )
            rows.sort(key=lambda row: (row["buyer_id"], row["session_id"], row["item_id"], row["is_saved"]))
            return rows

    def list_all_purchases(self) -> list[dict[str, Any]]:
        with self._state_lock:
            return [dict(row) for row in self._purchases]

    @replicated
    def register_item(
        self,
        item_name: str,
        category: int,
        keywords: list[str],
        condition: str,
        price: float,
        quantity: int,
        seller_id: int,
    ) -> int:
        with self._state_lock:
            item_id = self._next_item_id
            self._next_item_id += 1
            self._items[item_id] = {
                "item_id": item_id,
                "item_name": item_name,
                "category": category,
                "keywords": [kw.strip() for kw in keywords if kw.strip()],
                "condition_is_new": condition.lower() in ("new", "brand new", "mint"),
                "price": float(price),
                "quantity": int(quantity),
                "seller_id": seller_id,
                "item_feedback": [0, 0],
            }
            self._notify("register_item", {"item": self._copy_item(self._items[item_id])})
            return item_id

    @replicated
    def update_item_price(self, item_id: int, seller_id: int, price: float) -> bool:
        with self._state_lock:
            item = self._items.get(item_id)
            if not item or item["seller_id"] != seller_id:
                raise ValueError("Item not found or unauthorized")
            item["price"] = float(price)
            self._notify("update_item_price", {"item_id": item_id, "price": float(price)})
            return True

    @replicated
    def update_item_quantity(self, item_id: int, seller_id: int, quantity_delta: int) -> int:
        with self._state_lock:
            item = self._items.get(item_id)
            if not item or item["seller_id"] != seller_id:
                raise ValueError("Item not found or unauthorized")
            new_qty = item["quantity"] - quantity_delta
            if new_qty < 0:
                raise ValueError("Insufficient quantity")
            item["quantity"] = new_qty
            self._notify("update_item_quantity", {"item_id": item_id, "quantity": new_qty})
            return new_qty

    @replicated
    def add_to_cart(self, buyer_id: int, session_id: str, item_id: int, quantity: int) -> bool:
        with self._state_lock:
            key = (buyer_id, session_id, item_id, False)
            self._cart_items[key] = self._cart_items.get(key, 0) + quantity
            self._notify(
                "upsert_cart",
                {
                    "buyer_id": buyer_id,
                    "session_id": session_id,
                    "item_id": item_id,
                    "quantity": self._cart_items[key],
                    "is_saved": False,
                },
            )
            return True

    @replicated
    def remove_from_cart(self, buyer_id: int, session_id: str, item_id: int) -> bool:
        with self._state_lock:
            key = (buyer_id, session_id, item_id, False)
            self._cart_items.pop(key, None)
            self._notify(
                "delete_cart",
                {"buyer_id": buyer_id, "session_id": session_id, "item_id": item_id, "is_saved": False},
            )
            return True

    @replicated
    def update_cart_item(self, buyer_id: int, session_id: str, item_id: int, quantity: int) -> bool:
        with self._state_lock:
            key = (buyer_id, session_id, item_id, False)
            if quantity <= 0:
                self._cart_items.pop(key, None)
                self._notify(
                    "delete_cart",
                    {"buyer_id": buyer_id, "session_id": session_id, "item_id": item_id, "is_saved": False},
                )
            else:
                self._cart_items[key] = quantity
                self._notify(
                    "upsert_cart",
                    {
                        "buyer_id": buyer_id,
                        "session_id": session_id,
                        "item_id": item_id,
                        "quantity": quantity,
                        "is_saved": False,
                    },
                )
            return True

    @replicated
    def save_cart(self, buyer_id: int, session_id: str) -> bool:
        with self._state_lock:
            current = []
            for (b_id, sess_id, item_id, is_saved), qty in list(self._cart_items.items()):
                if b_id == buyer_id and sess_id == session_id and not is_saved:
                    current.append((item_id, qty))
            for item_id, qty in current:
                saved_key = (buyer_id, "", item_id, True)
                self._cart_items[saved_key] = self._cart_items.get(saved_key, 0) + qty
            for key in list(self._cart_items.keys()):
                if key[0] == buyer_id and not key[3]:
                    del self._cart_items[key]
            self._notify(
                "save_cart",
                {
                    "buyer_id": buyer_id,
                    "session_id": session_id,
                    "saved_rows": self.list_saved_cart(buyer_id),
                },
            )
            return True

    @replicated
    def clear_cart(self, buyer_id: int, session_id: str) -> bool:
        with self._state_lock:
            for key in list(self._cart_items.keys()):
                if key[0] == buyer_id and key[1] == session_id and not key[3]:
                    del self._cart_items[key]
            self._notify("clear_cart", {"buyer_id": buyer_id, "session_id": session_id})
            return True

    @replicated
    def delete_unsaved_cart(self, buyer_id: int, session_id: str) -> bool:
        with self._state_lock:
            for key in list(self._cart_items.keys()):
                if key[0] == buyer_id and key[1] == session_id and not key[3]:
                    del self._cart_items[key]
            self._notify("clear_cart", {"buyer_id": buyer_id, "session_id": session_id})
            return True

    @replicated
    def clear_saved_cart(self, buyer_id: int) -> bool:
        with self._state_lock:
            for key in list(self._cart_items.keys()):
                if key[0] == buyer_id and key[3]:
                    del self._cart_items[key]
            self._notify("clear_saved_cart", {"buyer_id": buyer_id})
            return True

    @replicated
    def provide_feedback(self, item_id: int, is_positive: bool) -> int:
        with self._state_lock:
            item = self._items.get(item_id)
            if not item:
                raise ValueError("Item not found")
            idx = 0 if is_positive else 1
            item["item_feedback"][idx] += 1
            self._notify(
                "item_feedback",
                {"item_id": item_id, "item_feedback": list(item["item_feedback"])},
            )
            return item["seller_id"]

    @replicated
    def create_purchase(
        self,
        buyer_id: int,
        item_id: int,
        quantity: int,
        purchased_at: Optional[str] = None,
    ) -> bool:
        with self._state_lock:
            item = self._items.get(item_id)
            if not item:
                raise ValueError("Item not found")
            if quantity <= 0:
                raise ValueError("Quantity must be positive")
            if item["quantity"] < quantity:
                raise ValueError("Insufficient quantity")
            item["quantity"] -= quantity
            self._purchases.append(
                {
                    "buyer_id": buyer_id,
                    "item_id": item_id,
                    "quantity": quantity,
                    "purchased_at": purchased_at or _utc_now_iso(),
                }
            )
            self._notify(
                "create_purchase",
                {
                    "buyer_id": buyer_id,
                    "item_id": item_id,
                    "quantity": quantity,
                    "purchased_at": self._purchases[-1]["purchased_at"],
                    "item_quantity": item["quantity"],
                },
            )
            return True
