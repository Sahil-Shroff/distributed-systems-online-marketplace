from __future__ import annotations

import json
import os
import sys
import threading
import time
from concurrent import futures
from datetime import datetime, timezone
from pathlib import Path

import grpc

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "generated"))

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from protos import database_pb2
from protos import database_pb2_grpc
from server_side.data_access_layer.db import Database_Connection
from server_side.product_replication.raft_store import ProductRaftStore

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


class _NoopCustomerDB:
    """Testing stub used when running the product cluster without Postgres."""

    def execute(self, query, params=None, fetch: bool = False):
        return [] if fetch else None

    def close(self):
        return None


class _NoopProductDB(_NoopCustomerDB):
    pass


class ProductServiceServicer(database_pb2_grpc.DatabaseServiceServicer):
    def __init__(self):
        grpc_port = os.getenv("PRODUCT_SERVICE_PORT", "50052")
        raft_self = os.getenv("PRODUCT_RAFT_SELF", f"127.0.0.1:{int(grpc_port) + 1000}")
        raft_partners = [
            addr.strip()
            for addr in os.getenv("PRODUCT_RAFT_PARTNERS", "").split(",")
            if addr.strip()
        ]
        runtime_dir = REPO_ROOT / "runtime"
        status_dir = runtime_dir / "status"
        pids_dir = runtime_dir / "pids"
        dump_dir = runtime_dir / "raft"
        status_dir.mkdir(parents=True, exist_ok=True)
        pids_dir.mkdir(parents=True, exist_ok=True)
        dump_dir.mkdir(parents=True, exist_ok=True)
        self._status_file = status_dir / f"product-service-{grpc_port}.json"
        self._pid_file = pids_dir / f"product-service-{grpc_port}.pid"
        self._pid_file.write_text(str(os.getpid()), encoding="utf-8")

        dump_file = dump_dir / f"product-{raft_self.replace(':', '_')}.bin"
        self.store = ProductRaftStore(raft_self, raft_partners, str(dump_file), apply_listener=self._apply_product_event)
        disable_customer_db = os.getenv("PRODUCT_SERVICE_DISABLE_CUSTOMER_DB", "").lower() in {"1", "true", "yes"}
        disable_product_db = os.getenv("PRODUCT_SERVICE_DISABLE_PRODUCT_DB", "").lower() in {"1", "true", "yes"}
        product_backend = os.getenv("PRODUCT_DB_BACKEND", os.getenv("DB_BACKEND", "postgres")).lower()
        product_sqlite_path = os.getenv(
            "PRODUCT_SQLITE_PATH",
            str(runtime_dir / "sqlite" / f"product-service-{grpc_port}.db"),
        )
        if disable_customer_db:
            self.customer_db = _NoopCustomerDB()
        else:
            self.customer_db = Database_Connection(
                os.getenv("CUSTOMER_DB_NAME", "customer-database"),
                host=os.getenv("CUSTOMER_PGHOST") or os.getenv("PGHOST", "localhost"),
                port=int(os.getenv("CUSTOMER_PGPORT") or os.getenv("PGPORT", "5434")),
                user=os.getenv("CUSTOMER_PGUSER") or os.getenv("PGUSER", "postgres"),
                password=os.getenv("CUSTOMER_PGPASSWORD") or os.getenv("PGPASSWORD"),
            )
        if disable_product_db:
            self.product_db = _NoopProductDB()
        else:
            self.product_db = Database_Connection(
                os.getenv("PRODUCT_DB_NAME", "product-database" if product_backend != "sqlite" else product_sqlite_path),
                host=os.getenv("PRODUCT_PGHOST") or os.getenv("PGHOST", "localhost"),
                port=int(os.getenv("PRODUCT_PGPORT") or os.getenv("PGPORT", "5434")),
                user=os.getenv("PRODUCT_PGUSER") or os.getenv("PGUSER", "postgres"),
                password=os.getenv("PRODUCT_PGPASSWORD") or os.getenv("PGPASSWORD"),
                backend=product_backend,
                sqlite_path=product_sqlite_path,
            )
        self._stop_event = threading.Event()
        self._rebuild_product_db_from_store()
        self._status_thread = threading.Thread(target=self._write_status_loop, daemon=True)
        self._status_thread.start()

    def close(self):
        self._stop_event.set()
        try:
            self.customer_db.close()
        except Exception:
            pass
        try:
            self.product_db.close()
        except Exception:
            pass

    def _write_status_loop(self):
        while not self._stop_event.is_set():
            try:
                status = self.store.status()
                payload = {
                    "self": str(status.get("self")),
                    "leader": str(status.get("leader")),
                    "state": status.get("state"),
                    "has_quorum": status.get("has_quorum"),
                    "raft_term": status.get("raft_term"),
                    "commit_idx": status.get("commit_idx"),
                    "pid": os.getpid(),
                }
                self._status_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            except Exception:
                pass
            time.sleep(1)

    def _abort_unimplemented(self, context, method: str):
        context.abort(grpc.StatusCode.UNIMPLEMENTED, f"{method} is handled by the customer service")

    def _sync_call(self, context, fn, *args, **kwargs):
        try:
            return fn(*args, sync=True, timeout=10.0, **kwargs)
        except ValueError as exc:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))
        except Exception as exc:
            context.abort(grpc.StatusCode.UNAVAILABLE, str(exc))

    def _mirror_get_item(self, item_id: int) -> dict | None:
        item = self.store.get_item(item_id)
        return item

    def _mirror_register_item(self, item: dict):
        self.product_db.execute(
            """
            INSERT INTO items (item_id, item_name, category, keywords, condition_is_new, sale_price, quantity, item_feedback, seller_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (item_id) DO UPDATE
            SET item_name = EXCLUDED.item_name,
                category = EXCLUDED.category,
                keywords = EXCLUDED.keywords,
                condition_is_new = EXCLUDED.condition_is_new,
                sale_price = EXCLUDED.sale_price,
                quantity = EXCLUDED.quantity,
                item_feedback = EXCLUDED.item_feedback,
                seller_id = EXCLUDED.seller_id
            """,
            (
                item["item_id"],
                item["item_name"],
                item["category"],
                item["keywords"],
                item["condition_is_new"],
                item["price"],
                item["quantity"],
                item["item_feedback"],
                item["seller_id"],
            ),
            fetch=False,
        )

    def _mirror_item_price(self, item_id: int, price: float):
        self.product_db.execute(
            "UPDATE items SET sale_price = %s WHERE item_id = %s",
            (price, item_id),
            fetch=False,
        )

    def _mirror_item_quantity(self, item_id: int, quantity: int):
        self.product_db.execute(
            "UPDATE items SET quantity = %s WHERE item_id = %s",
            (quantity, item_id),
            fetch=False,
        )

    def _mirror_upsert_cart_row(self, buyer_id: int, session_id: str, item_id: int, quantity: int, is_saved: bool):
        self.product_db.execute(
            """
            INSERT INTO cart_items (buyer_id, session_id, item_id, quantity, is_saved)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (buyer_id, session_id, item_id, is_saved) DO UPDATE
            SET quantity = EXCLUDED.quantity
            """,
            (buyer_id, session_id, item_id, quantity, is_saved),
            fetch=False,
        )

    def _mirror_delete_cart_row(self, buyer_id: int, session_id: str, item_id: int, is_saved: bool):
        self.product_db.execute(
            "DELETE FROM cart_items WHERE buyer_id = %s AND session_id = %s AND item_id = %s AND is_saved = %s",
            (buyer_id, session_id, item_id, is_saved),
            fetch=False,
        )

    def _mirror_delete_unsaved_cart(self, buyer_id: int, session_id: str):
        self.product_db.execute(
            "DELETE FROM cart_items WHERE buyer_id = %s AND session_id = %s AND is_saved = FALSE",
            (buyer_id, session_id),
            fetch=False,
        )

    def _mirror_saved_cart(self, buyer_id: int):
        self.product_db.execute(
            "DELETE FROM cart_items WHERE buyer_id = %s AND is_saved = TRUE",
            (buyer_id,),
            fetch=False,
        )
        for row in self.store.list_saved_cart(buyer_id):
            self._mirror_upsert_cart_row(buyer_id, "", row["item_id"], row["quantity"], True)

    def _mirror_item_feedback(self, item_id: int, item_feedback: list[int]):
        self.product_db.execute(
            "UPDATE items SET item_feedback = %s WHERE item_id = %s",
            (item_feedback, item_id),
            fetch=False,
        )

    def _mirror_purchase(self, buyer_id: int, item_id: int, quantity: int, purchased_at: str):
        self.product_db.execute(
            "INSERT INTO purchases (buyer_id, item_id, quantity, purchased_at) VALUES (%s, %s, %s, %s)",
            (buyer_id, item_id, quantity, purchased_at),
            fetch=False,
        )

    def _apply_product_event(self, event_type: str, payload: dict):
        if isinstance(self.product_db, _NoopProductDB):
            return
        if event_type == "register_item":
            self._mirror_register_item(payload["item"])
            return
        if event_type == "update_item_price":
            self._mirror_item_price(payload["item_id"], payload["price"])
            return
        if event_type == "update_item_quantity":
            self._mirror_item_quantity(payload["item_id"], payload["quantity"])
            return
        if event_type == "upsert_cart":
            self._mirror_upsert_cart_row(
                payload["buyer_id"],
                payload["session_id"],
                payload["item_id"],
                payload["quantity"],
                payload["is_saved"],
            )
            return
        if event_type == "delete_cart":
            self._mirror_delete_cart_row(
                payload["buyer_id"],
                payload["session_id"],
                payload["item_id"],
                payload["is_saved"],
            )
            return
        if event_type == "save_cart":
            self._mirror_delete_unsaved_cart(payload["buyer_id"], payload["session_id"])
            self.product_db.execute(
                "DELETE FROM cart_items WHERE buyer_id = %s AND is_saved = TRUE",
                (payload["buyer_id"],),
                fetch=False,
            )
            for row in payload["saved_rows"]:
                self._mirror_upsert_cart_row(payload["buyer_id"], "", row["item_id"], row["quantity"], True)
            return
        if event_type == "clear_cart":
            self._mirror_delete_unsaved_cart(payload["buyer_id"], payload["session_id"])
            return
        if event_type == "clear_saved_cart":
            self.product_db.execute(
                "DELETE FROM cart_items WHERE buyer_id = %s AND is_saved = TRUE",
                (payload["buyer_id"],),
                fetch=False,
            )
            return
        if event_type == "item_feedback":
            self._mirror_item_feedback(payload["item_id"], payload["item_feedback"])
            return
        if event_type == "create_purchase":
            self._mirror_purchase(
                payload["buyer_id"],
                payload["item_id"],
                payload["quantity"],
                payload["purchased_at"],
            )
            self._mirror_item_quantity(payload["item_id"], payload["item_quantity"])

    def _rebuild_product_db_from_store(self):
        if isinstance(self.product_db, _NoopProductDB):
            return
        self.product_db.execute("DELETE FROM cart_items", fetch=False)
        self.product_db.execute("DELETE FROM purchases", fetch=False)
        self.product_db.execute("DELETE FROM items", fetch=False)
        for item in self.store.list_all_items():
            self._mirror_register_item(item)
        for row in self.store.list_all_cart_rows():
            self._mirror_upsert_cart_row(
                row["buyer_id"],
                row["session_id"],
                row["item_id"],
                row["quantity"],
                row["is_saved"],
            )
        for row in self.store.list_all_purchases():
            self._mirror_purchase(row["buyer_id"], row["item_id"], row["quantity"], row["purchased_at"])

    # Customer methods remain in the separate customer service.
    def CreateAccount(self, request, context):
        self._abort_unimplemented(context, "CreateAccount")

    def AuthenticateUser(self, request, context):
        self._abort_unimplemented(context, "AuthenticateUser")

    def VerifySession(self, request, context):
        self._abort_unimplemented(context, "VerifySession")

    def DeleteSessions(self, request, context):
        self._abort_unimplemented(context, "DeleteSessions")

    # Product methods
    def SearchItems(self, request, context):
        items = self.store.search_items(request.category, list(request.keywords))
        return database_pb2.SearchItemsResponse(
            items=[
                database_pb2.Item(
                    item_id=item["item_id"],
                    item_name=item["item_name"],
                    category=item["category"],
                    keywords=item["keywords"],
                    condition_is_new=item["condition_is_new"],
                    price=float(item["price"]),
                    quantity=item["quantity"],
                    seller_id=item["seller_id"],
                )
                for item in items
            ]
        )

    def GetItem(self, request, context):
        item = self.store.get_item(request.item_id)
        if not item:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item not found")
        return database_pb2.Item(
            item_id=item["item_id"],
            item_name=item["item_name"],
            category=item["category"],
            keywords=item["keywords"],
            condition_is_new=item["condition_is_new"],
            price=float(item["price"]),
            quantity=item["quantity"],
            seller_id=item["seller_id"],
        )

    def RegisterItem(self, request, context):
        item_id = self._sync_call(
            context,
            self.store.register_item,
            request.item_name,
            request.category,
            list(request.keywords),
            request.condition,
            request.price,
            request.quantity,
            request.seller_id,
        )
        return database_pb2.RegisterItemResponse(item_id=item_id)

    def UpdateItemPrice(self, request, context):
        self._sync_call(context, self.store.update_item_price, request.item_id, request.seller_id, request.price)
        return database_pb2.Empty()

    def UpdateItemQuantity(self, request, context):
        new_quantity = self._sync_call(
            context,
            self.store.update_item_quantity,
            request.item_id,
            request.seller_id,
            request.quantity_delta,
        )
        return database_pb2.UpdateItemQuantityResponse(new_quantity=new_quantity)

    def GetItemsBySeller(self, request, context):
        items = self.store.get_items_by_seller(request.seller_id)
        return database_pb2.SearchItemsResponse(
            items=[
                database_pb2.Item(
                    item_id=item["item_id"],
                    item_name=item["item_name"],
                    category=item["category"],
                    keywords=item["keywords"],
                    condition_is_new=item["condition_is_new"],
                    price=float(item["price"]),
                    quantity=item["quantity"],
                    seller_id=item["seller_id"],
                )
                for item in items
            ]
        )

    def AddToCart(self, request, context):
        self._sync_call(context, self.store.add_to_cart, request.buyer_id, request.session_id, request.item_id, request.quantity)
        return database_pb2.Empty()

    def RemoveFromCart(self, request, context):
        self._sync_call(context, self.store.remove_from_cart, request.buyer_id, request.session_id, request.item_id)
        return database_pb2.Empty()

    def GetCartItemQuantity(self, request, context):
        cart = self.store.list_cart(request.buyer_id, request.session_id)
        quantity = 0
        for item in cart:
            if item["item_id"] == request.item_id:
                quantity = item["quantity"]
                break
        return database_pb2.QuantityResponse(quantity=quantity)

    def UpdateCartItem(self, request, context):
        self._sync_call(context, self.store.update_cart_item, request.buyer_id, request.session_id, request.item_id, request.quantity)
        return database_pb2.Empty()

    def SaveCart(self, request, context):
        self._sync_call(context, self.store.save_cart, request.buyer_id, request.session_id)
        return database_pb2.Empty()

    def ClearCart(self, request, context):
        self._sync_call(context, self.store.clear_cart, request.buyer_id, request.session_id)
        return database_pb2.Empty()

    def ListCart(self, request, context):
        rows = self.store.list_cart(request.buyer_id, request.session_id)
        return database_pb2.CartListResponse(
            items=[database_pb2.CartItem(item_id=row["item_id"], quantity=row["quantity"]) for row in rows]
        )

    def DeleteUnsavedCart(self, request, context):
        self._sync_call(context, self.store.delete_unsaved_cart, request.buyer_id, request.session_id)
        return database_pb2.Empty()

    def ListSavedCart(self, request, context):
        rows = self.store.list_saved_cart(request.buyer_id)
        return database_pb2.CartListResponse(
            items=[database_pb2.CartItem(item_id=row["item_id"], quantity=row["quantity"]) for row in rows]
        )

    def ClearSavedCart(self, request, context):
        self._sync_call(context, self.store.clear_saved_cart, request.buyer_id)
        return database_pb2.Empty()

    def ProvideFeedback(self, request, context):
        seller_id = self._sync_call(context, self.store.provide_feedback, request.item_id, request.is_positive)
        idx = 1 if request.is_positive else 2
        self.customer_db.execute(
            f"UPDATE sellers SET seller_feedback[{idx}] = seller_feedback[{idx}] + 1 WHERE seller_id = %s",
            (seller_id,),
            fetch=False,
        )
        return database_pb2.Empty()

    def GetSellerRating(self, request, context):
        self._abort_unimplemented(context, "GetSellerRating")

    def GetPurchaseHistory(self, request, context):
        rows = self.store.get_purchase_history(request.buyer_id)
        return database_pb2.PurchaseHistoryResponse(
            records=[
                database_pb2.PurchaseRecord(
                    item_id=row["item_id"],
                    quantity=row["quantity"],
                    purchased_at=row["purchased_at"],
                )
                for row in rows
            ]
        )

    def CreatePurchase(self, request, context):
        purchased_at = datetime.now(timezone.utc).isoformat()
        self._sync_call(
            context,
            self.store.create_purchase,
            request.buyer_id,
            request.item_id,
            request.quantity,
            purchased_at,
        )
        item = self.store.get_item(request.item_id)
        if item:
            seller_id = item["seller_id"]
            self.customer_db.execute(
                "UPDATE buyers SET items_purchased = items_purchased + %s WHERE buyer_id = %s",
                (request.quantity, request.buyer_id),
                fetch=False,
            )
            self.customer_db.execute(
                "UPDATE sellers SET items_sold = items_sold + %s WHERE seller_id = %s",
                (request.quantity, seller_id),
                fetch=False,
            )
        return database_pb2.Empty()


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = ProductServiceServicer()
    database_pb2_grpc.add_DatabaseServiceServicer_to_server(servicer, server)
    port = os.getenv("PRODUCT_SERVICE_PORT", "50052")
    bind_addr = os.getenv("PRODUCT_SERVICE_BIND", f"0.0.0.0:{port}")
    server.add_insecure_port(bind_addr)
    print(f"Product Raft service starting on {bind_addr}...")
    try:
        server.start()
        server.wait_for_termination()
    finally:
        servicer.close()


if __name__ == "__main__":
    serve()
