from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server_side.product_replication.raft_store import ProductRaftStore


def wait_for(predicate, timeout: float, interval: float = 0.2) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def leader_store(stores: list[ProductRaftStore]) -> ProductRaftStore | None:
    for store in stores:
        status = store.status()
        if str(status.get("self")) == str(status.get("leader")):
            return store
    return None


def follower_store(stores: list[ProductRaftStore]) -> ProductRaftStore | None:
    lead = leader_store(stores)
    if lead is None:
        return None
    lead_self = str(lead.status().get("self"))
    for store in stores:
        if str(store.status().get("self")) != lead_self:
            return store
    return None


def verify_quantity(stores: list[ProductRaftStore], item_id: int, expected_qty: int):
    for store in stores:
        item = store.get_item(item_id)
        if item is None:
            raise AssertionError(f"Replica {store.status().get('self')} is missing item {item_id}")
        if item["quantity"] != expected_qty:
            raise AssertionError(
                f"Replica {store.status().get('self')} has quantity {item['quantity']} instead of {expected_qty}"
            )


def main():
    temp_dir = Path(tempfile.mkdtemp(prefix="product-raft-demo-"))
    ports = [19001, 19002, 19003, 19004, 19005]
    addrs = [f"127.0.0.1:{port}" for port in ports]
    stores: list[ProductRaftStore] = []
    try:
        for idx, addr in enumerate(addrs):
            peers = [other for other in addrs if other != addr]
            dump_file = temp_dir / f"replica-{idx + 1}.bin"
            stores.append(ProductRaftStore(addr, peers, str(dump_file)))

        ready = wait_for(lambda: all(store.isReady() for store in stores), timeout=20)
        if not ready:
            raise RuntimeError("Cluster did not become ready in time")

        lead = leader_store(stores)
        if lead is None:
            raise RuntimeError("No leader elected")
        print(f"Initial leader: {lead.status().get('self')}")

        item_id = lead.register_item(
            "DemoLaptop",
            1,
            ["demo", "raft"],
            "New",
            999.0,
            5,
            42,
            sync=True,
            timeout=5,
        )
        lead.update_item_price(item_id, 42, 1099.0, sync=True, timeout=5)
        lead.update_item_quantity(item_id, 42, 2, sync=True, timeout=5)
        lead.add_to_cart(7, "sess-1", item_id, 1, sync=True, timeout=5)
        lead.save_cart(7, "sess-1", sync=True, timeout=5)
        lead.create_purchase(7, item_id, 1, "2026-03-25T00:00:00+00:00", sync=True, timeout=5)

        time.sleep(1)
        verify_quantity(stores, item_id, 3)
        print("Replication check passed across all 5 replicas.")

        follower = follower_store(stores)
        if follower is None:
            raise RuntimeError("No follower found")
        print(f"Destroying follower: {follower.status().get('self')}")
        follower.destroy()
        stores = [store for store in stores if store is not follower]
        time.sleep(2)

        lead = leader_store(stores)
        if lead is None:
            raise RuntimeError("No leader after follower failure")
        lead.update_item_price(item_id, 42, 1199.0, sync=True, timeout=5)
        time.sleep(1)
        for store in stores:
            item = store.get_item(item_id)
            if item is None or item["price"] != 1199.0:
                raise AssertionError("Follower-failure write did not replicate")
        print("Follower failure test passed.")

        old_leader = leader_store(stores)
        if old_leader is None:
            raise RuntimeError("No leader before leader failure")
        print(f"Destroying leader: {old_leader.status().get('self')}")
        old_leader.destroy()
        stores = [store for store in stores if store is not old_leader]

        reelected = wait_for(lambda: leader_store(stores) is not None, timeout=10)
        if not reelected:
            raise RuntimeError("No new leader elected after leader failure")
        new_leader = leader_store(stores)
        print(f"New leader: {new_leader.status().get('self')}")
        new_leader.update_item_quantity(item_id, 42, -2, sync=True, timeout=5)
        time.sleep(1)
        verify_quantity(stores, item_id, 5)
        print("Leader failure / re-election test passed.")
        print("Demo completed successfully.")
    finally:
        for store in stores:
            try:
                store.destroy()
            except Exception:
                pass
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
