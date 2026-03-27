from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import grpc

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
GENERATED_PROTOS = REPO_ROOT / "generated" / "protos"
if str(GENERATED_PROTOS) not in sys.path:
    sys.path.insert(0, str(GENERATED_PROTOS))
SQLITE_DIR = REPO_ROOT / "runtime" / "sqlite"

import database_pb2
import database_pb2_grpc
from server_side.data_access_layer.db import Database_Connection


REPLICAS = [
    "127.0.0.1:50052",
    "127.0.0.1:50053",
    "127.0.0.1:50054",
    "127.0.0.1:50055",
    "127.0.0.1:50056",
]


def stub_for(addr: str):
    channel = grpc.insecure_channel(addr)
    return database_pb2_grpc.DatabaseServiceStub(channel)


def first_success(method_name: str, request, timeout: float = 3.0):
    last_error = None
    for addr in REPLICAS:
        try:
            stub = stub_for(addr)
            method = getattr(stub, method_name)
            response = method(request, timeout=timeout)
            return addr, response
        except grpc.RpcError as exc:
            last_error = exc
    raise RuntimeError(f"{method_name} failed on all replicas: {last_error}")


def wait_for_write(method_name: str, request, total_timeout: float = 12.0):
    deadline = time.time() + total_timeout
    last_error = None
    while time.time() < deadline:
        for addr in REPLICAS:
            try:
                stub = stub_for(addr)
                method = getattr(stub, method_name)
                response = method(request, timeout=2.0)
                return addr, response
            except grpc.RpcError as exc:
                last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"{method_name} did not succeed before timeout: {last_error}")


def assert_item_state(expected_price: float, expected_qty: int):
    for addr in REPLICAS:
        try:
            _addr, item = first_success("GetItem", database_pb2.GetItemRequest(item_id=1))
            break
        except Exception:
            continue
    else:
        raise AssertionError("Could not read item from any replica")

    if abs(item.price - expected_price) > 0.0001 or item.quantity != expected_qty:
        raise AssertionError(
            f"Unexpected item state: price={item.price}, qty={item.quantity}, expected price={expected_price}, qty={expected_qty}"
        )


def print_header(title: str):
    print(f"\n=== {title} ===")


def kill_with_script(script_name: str, settle_delay: float = 3.0):
    script_path = REPO_ROOT / "tools" / script_name
    subprocess.run([sys.executable, str(script_path)], check=True)
    time.sleep(settle_delay)


def product_db(sqlite_path: str | None = None):
    backend = os.getenv("PRODUCT_DB_BACKEND", "sqlite").lower()
    sqlite_path = sqlite_path or os.getenv("PRODUCT_SQLITE_PATH", str(SQLITE_DIR / "product-service-50052.db"))
    return Database_Connection(
        os.getenv("PRODUCT_DB_NAME", "product-database" if backend != "sqlite" else sqlite_path),
        host=os.getenv("PRODUCT_PGHOST") or os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PRODUCT_PGPORT") or os.getenv("PGPORT", "5434")),
        user=os.getenv("PRODUCT_PGUSER") or os.getenv("PGUSER", "postgres"),
        password=os.getenv("PRODUCT_PGPASSWORD") or os.getenv("PGPASSWORD"),
        backend=backend,
        sqlite_path=sqlite_path,
    )


def reset_product_db():
    SQLITE_DIR.mkdir(parents=True, exist_ok=True)
    for port in [50052, 50053, 50054, 50055, 50056]:
        db = product_db(str(SQLITE_DIR / f"product-service-{port}.db"))
        try:
            db.execute("DELETE FROM cart_items", fetch=False)
            db.execute("DELETE FROM purchases", fetch=False)
            db.execute("DELETE FROM items", fetch=False)
            db.execute("DELETE FROM sqlite_sequence WHERE name IN ('cart_items', 'purchases')", fetch=False)
        finally:
            db.close()


def show_db_state():
    for port in [50052, 50053, 50054, 50055, 50056]:
        db_path = SQLITE_DIR / f"product-service-{port}.db"
        if not db_path.exists():
            print(f"Replica DB {db_path.name}=missing")
            continue
        db = product_db(str(db_path))
        try:
            items = db.execute(
                "SELECT item_id, item_name, sale_price, quantity, seller_id, item_feedback FROM items ORDER BY item_id",
                fetch=True,
            ) or []
            carts = db.execute(
                "SELECT buyer_id, session_id, item_id, quantity, is_saved FROM cart_items ORDER BY cart_item_id",
                fetch=True,
            ) or []
            purchases = db.execute(
                "SELECT buyer_id, item_id, quantity FROM purchases ORDER BY purchase_id",
                fetch=True,
            ) or []
            print(f"{db_path.name} items={items}")
            print(f"{db_path.name} cart_items={carts}")
            print(f"{db_path.name} purchases={purchases}")
        finally:
            db.close()


def main():
    print_header("Reset Product Mirrored DB")
    reset_product_db()
    print("Cleared items, cart_items, and purchases in the mirrored product DB.")

    print_header("Initial Write Test")
    addr, resp = wait_for_write(
        "RegisterItem",
        database_pb2.RegisterItemRequest(
            item_name="ClusterLaptop",
            category=1,
            keywords=["cluster", "raft"],
            condition="New",
            price=1000.0,
            quantity=5,
            seller_id=42,
        ),
    )
    print(f"RegisterItem succeeded via {addr}, item_id={resp.item_id}")

    addr, _ = wait_for_write(
        "UpdateItemPrice",
        database_pb2.UpdateItemPriceRequest(item_id=1, seller_id=42, price=1200.0),
    )
    print(f"UpdateItemPrice succeeded via {addr}")

    addr, resp = wait_for_write(
        "UpdateItemQuantity",
        database_pb2.UpdateItemQuantityRequest(item_id=1, seller_id=42, quantity_delta=2),
    )
    print(f"UpdateItemQuantity succeeded via {addr}, new_quantity={resp.new_quantity}")

    addr, _ = wait_for_write(
        "AddToCart",
        database_pb2.AddToCartRequest(buyer_id=7, session_id="sess-1", item_id=1, quantity=1),
    )
    print(f"AddToCart succeeded via {addr}")

    addr, _ = wait_for_write(
        "SaveCart",
        database_pb2.SaveCartRequest(buyer_id=7, session_id="sess-1"),
    )
    print(f"SaveCart succeeded via {addr}")

    addr, _ = wait_for_write(
        "ProvideFeedback",
        database_pb2.ProvideFeedbackRequest(item_id=1, buyer_id=7, is_positive=True),
    )
    print(f"ProvideFeedback succeeded via {addr}")

    addr, _ = wait_for_write(
        "CreatePurchase",
        database_pb2.CreatePurchaseRequest(buyer_id=7, item_id=1, quantity=1),
    )
    print(f"CreatePurchase succeeded via {addr}")

    _addr, item = first_success("GetItem", database_pb2.GetItemRequest(item_id=1))
    print(f"Read item: price={item.price}, quantity={item.quantity}")

    _addr, cart = first_success("ListSavedCart", database_pb2.ListSavedCartRequest(buyer_id=7))
    print(f"Saved cart items={[(row.item_id, row.quantity) for row in cart.items]}")

    _addr, history = first_success("GetPurchaseHistory", database_pb2.GetPurchaseHistoryRequest(buyer_id=7))
    print(f"Purchase history count={len(history.records)}")
    show_db_state()

    print_header("Follower Failure")
    kill_with_script("kill_product_follower.py")
    addr, _ = wait_for_write(
        "UpdateItemPrice",
        database_pb2.UpdateItemPriceRequest(item_id=1, seller_id=42, price=1300.0),
    )
    print(f"Write after follower failure succeeded via {addr}")
    show_db_state()

    print_header("Leader Failure")
    kill_with_script("kill_product_leader.py", settle_delay=8.0)
    addr, resp = wait_for_write(
        "UpdateItemQuantity",
        database_pb2.UpdateItemQuantityRequest(item_id=1, seller_id=42, quantity_delta=-2),
        total_timeout=20.0,
    )
    print(f"Write after leader failure succeeded via {addr}, new_quantity={resp.new_quantity}")

    _addr, final_item = first_success("GetItem", database_pb2.GetItemRequest(item_id=1))
    print(f"Final item state: price={final_item.price}, quantity={final_item.quantity}")
    show_db_state()
    print("\nProduct-service cluster test completed successfully.")


if __name__ == "__main__":
    main()
