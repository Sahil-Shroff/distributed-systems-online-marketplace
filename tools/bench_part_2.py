"""
Benchmark client-side API calls over REST (FastAPI) servers.

Scenarios:
 1) 1 seller, 1 buyer
 2) 10 sellers, 10 buyers
 3) (optional) 100 sellers, 100 buyers   # uncomment in main if desired

Metrics:
 - Average response time (10 runs of a representative API call)
 - Average throughput (10 runs; each run = each client performs 1000 API calls)

Prerequisites:
 - Seller REST server running (default: localhost:8000)
 - Buyer REST server running  (default: localhost:8001)
 - DB service reachable by the servers

Run:
    python tools/bench_part_2.py
"""

from __future__ import annotations

import concurrent.futures
import statistics
import time
import uuid
from dataclasses import dataclass
from typing import Callable, List, Tuple
from pathlib import Path
import sys

# ensure repo root on path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from client_side.seller_interface.seller_rest_client import SellerRestClient
from client_side.buyer_interface.buyer_rest_client import BuyerRestClient


# ------------- Helpers -------------

def measure_perf(clients: List[Callable[[], None]], runs: int = 10, ops_per_client: int = 1000) -> Tuple[float, float]:
    """
    Measures average per-call latency and throughput together, using the same
    API calls under load. Returns (avg_latency_seconds, avg_throughput_ops_per_sec).
    """
    if not clients:
        return 0.0, 0.0

    latency_samples: List[float] = []
    throughput_samples: List[float] = []

    for _ in range(runs):
        total_ops = ops_per_client * len(clients)
        start_run = time.perf_counter()

        def worker(fn: Callable[[], None]):
            local = []
            for _ in range(ops_per_client):
                t0 = time.perf_counter()
                fn()
                local.append(time.perf_counter() - t0)
            return local

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(clients)) as pool:
            futures = [pool.submit(worker, fn) for fn in clients]
            for fut in concurrent.futures.as_completed(futures):
                latency_samples.extend(fut.result())

        elapsed = time.perf_counter() - start_run
        throughput_samples.append(total_ops / elapsed if elapsed > 0 else 0.0)

    avg_latency = statistics.mean(latency_samples) if latency_samples else 0.0
    avg_throughput = statistics.mean(throughput_samples) if throughput_samples else 0.0
    return avg_latency, avg_throughput


# ------------- Client setup -------------

@dataclass
class SellerCtx:
    client: SellerRestClient
    item_id: int


@dataclass
class BuyerCtx:
    client: BuyerRestClient


def setup_seller(host: str, port: int) -> SellerCtx:
    client = SellerRestClient(host, port)
    username = f"seller_{uuid.uuid4().hex[:8]}"
    password = "pass123"
    try:
        client.create_account(username, password)
    except Exception:
        pass
    client.login(username, password)
    item_id = client.register_item_for_sale(
        item_name="BenchItem",
        category=1,
        keywords=["bench"],
        condition="New",
        price=10.0,
        quantity=100000,
    )
    return SellerCtx(client=client, item_id=item_id)


def setup_buyer(host: str, port: int) -> BuyerCtx:
    client = BuyerRestClient(host, port)
    username = f"buyer_{uuid.uuid4().hex[:8]}"
    password = "pass123"
    try:
        client.create_account(username, password)
    except Exception:
        pass
    client.login(username, password)
    return BuyerCtx(client=client)


# ------------- Bench tasks -------------

def seller_call(ctx: SellerCtx):
    # representative seller op: display items
    ctx.client.display_items_for_sale()


def buyer_call(ctx: BuyerCtx, item_id: int):
    # representative buyer op: add to cart
    ctx.client.add_to_cart(item_id, 1)


def run_scenario(sellers: int, buyers: int, seller_host="127.0.0.1", seller_port=8000, buyer_host="127.0.0.1", buyer_port=8001):
    seller_ctxs = [setup_seller(seller_host, seller_port) for _ in range(sellers)]
    buyer_ctxs = [setup_buyer(buyer_host, buyer_port) for _ in range(buyers)]

    item_id = seller_ctxs[0].item_id if seller_ctxs else None

    seller_fns = [lambda ctx=ctx: seller_call(ctx) for ctx in seller_ctxs]
    buyer_fns = [lambda ctx=ctx, iid=item_id: buyer_call(ctx, iid) for ctx in buyer_ctxs] if item_id else []
    all_fns = seller_fns + buyer_fns

    avg_latency, avg_tput = measure_perf(all_fns, runs=10, ops_per_client=1000) if all_fns else (0, 0)

    # no explicit logout endpoint needed; sessions will expire server-side
    return {
        "sellers": sellers,
        "buyers": buyers,
        "avg_response_time_seconds": avg_latency,
        "avg_throughput_ops_per_sec": avg_tput,
    }


def main():
    scenarios = [
        (1, 1),
        (10, 10),
        # (100, 100),
    ]
    for s, b in scenarios:
        result = run_scenario(s, b)
        print(f"Scenario sellers={s}, buyers={b}: {result}")


if __name__ == "__main__":
    main()
