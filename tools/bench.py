"""
Benchmark client-side API calls over real TCP sockets.

Scenarios:
 1) 1 seller, 1 buyer
 2) 10 sellers, 10 buyers
 3) 100 sellers, 100 buyers

Metrics:
 - Average response time (10 runs of a representative API call)
 - Average throughput (10 runs; each run = each client performs 1000 API calls)

Prerequisites:
 - Seller server running (default: localhost:8080)
 - Buyer server running  (default: localhost:8081)
 - PostgreSQL data seeded with required tables

Run:
    python tools/bench.py
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

# for `client_side.*` imports resolve
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from client_side.seller_interface.seller_client import SellerClient
from client_side.buyer_interface.buyer_client import BuyerClient
from client_side.common.tcp_client import TCPClient


# ------------- Helpers -------------

def measure_avg_response_time(fn: Callable[[], object], runs: int = 10) -> Tuple[float, List[float]]:
    samples: List[float] = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return (statistics.mean(samples), samples)


def throughput_run(clients: List[Callable[[], None]], ops_per_client: int = 1000) -> float:
    total_ops = ops_per_client * len(clients)
    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(clients)) as pool:
        futures = [
            pool.submit(lambda fn=fn: [fn() for _ in range(ops_per_client)])
            for fn in clients
        ]
        concurrent.futures.wait(futures)
    elapsed = time.perf_counter() - start
    return total_ops / elapsed if elapsed > 0 else 0.0


def measure_throughput(clients: List[Callable[[], None]], runs: int = 10, ops_per_client: int = 1000) -> Tuple[float, List[float]]:
    samples = [throughput_run(clients, ops_per_client) for _ in range(runs)]
    return (statistics.mean(samples), samples)


# ------------- Client setup -------------

@dataclass
class SellerCtx:
    client: SellerClient
    tcp: TCPClient
    item_id: str


@dataclass
class BuyerCtx:
    client: BuyerClient
    tcp: TCPClient


def setup_seller(host: str, port: int) -> SellerCtx:
    tcp = TCPClient(host, port)
    client = SellerClient(tcp)
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
        quantity=100000,  # large to avoid depletion during throughput test
    )
    return SellerCtx(client=client, tcp=tcp, item_id=item_id)


def setup_buyer(host: str, port: int) -> BuyerCtx:
    tcp = TCPClient(host, port)
    client = BuyerClient(tcp)
    username = f"buyer_{uuid.uuid4().hex[:8]}"
    password = "pass123"
    try:
        client.create_account(username, password)
    except Exception:
        pass
    client.login(username, password)
    return BuyerCtx(client=client, tcp=tcp)


# ------------- Bench tasks -------------

def seller_call(ctx: SellerCtx):
    # representative seller op: display items
    ctx.client.display_items_for_sale()


def buyer_call(ctx: BuyerCtx, item_id: str):
    # representative buyer op: add to cart
    ctx.client.add_item_to_cart(item_id, 1)


def run_scenario(sellers: int, buyers: int, seller_host="127.0.0.1", seller_port=8080, buyer_host="127.0.0.1", buyer_port=8081):
    seller_ctxs = [setup_seller(seller_host, seller_port) for _ in range(sellers)]
    buyer_ctxs = [setup_buyer(buyer_host, buyer_port) for _ in range(buyers)]

    # Use first seller item for buyer cart ops
    item_id = seller_ctxs[0].item_id if seller_ctxs else None

    # Response time (single seller op)
    avg_rt_seller, _ = measure_avg_response_time(lambda: seller_call(seller_ctxs[0]), runs=10) if seller_ctxs else (0, [])
    avg_rt_buyer, _ = measure_avg_response_time(lambda: buyer_call(buyer_ctxs[0], item_id), runs=10) if buyer_ctxs and item_id else (0, [])

    # Throughput: sellers + buyers together
    seller_fns = [lambda ctx=ctx: seller_call(ctx) for ctx in seller_ctxs]
    buyer_fns = [lambda ctx=ctx, iid=item_id: buyer_call(ctx, iid) for ctx in buyer_ctxs] if item_id else []
    all_fns = seller_fns + buyer_fns

    avg_tput, _ = measure_throughput(all_fns, runs=10, ops_per_client=1000) if all_fns else (0, [])

    # Cleanup
    for ctx in seller_ctxs:
        try:
            ctx.client.logout()
        except Exception:
            pass
        ctx.tcp.close()
    for ctx in buyer_ctxs:
        try:
            ctx.client.logout()
        except Exception:
            pass
        ctx.tcp.close()

    return {
        "sellers": sellers,
        "buyers": buyers,
        "avg_response_time_seller": avg_rt_seller,
        "avg_response_time_buyer": avg_rt_buyer,
        "avg_throughput_ops_per_sec": avg_tput,
    }


def main():
    scenarios = [
        (1, 1),
        (10, 10),
        (100, 100),
    ]
    for s, b in scenarios:
        result = run_scenario(s, b)
        print(f"Scenario sellers={s}, buyers={b}: {result}")


if __name__ == "__main__":
    main()
