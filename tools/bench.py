from __future__ import annotations

import concurrent.futures
import statistics
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from client_side.buyer_interface.buyer_rest_client import BuyerRestClient
from client_side.seller_interface.seller_rest_client import SellerRestClient


def measure_avg_response_time(fn: Callable[[], object], runs: int = 10) -> float:
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return statistics.mean(samples)


def measure_throughput(clients: list[Callable[[], None]], runs: int = 10, ops_per_client: int = 1000) -> float:
    samples = []
    for _ in range(runs):
        total_ops = ops_per_client * len(clients)
        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(clients)) as pool:
            futures = [pool.submit(lambda fn=fn: [fn() for _ in range(ops_per_client)]) for fn in clients]
            concurrent.futures.wait(futures)
        elapsed = time.perf_counter() - start
        samples.append(total_ops / elapsed if elapsed > 0 else 0.0)
    return statistics.mean(samples)


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
    item_id = client.register_item_for_sale("BenchItem", 1, ["bench"], "New", 10.0, 100000)
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


def seller_call(ctx: SellerCtx):
    ctx.client.display_items_for_sale()


def buyer_call(ctx: BuyerCtx, item_id: int):
    ctx.client.add_to_cart(item_id, 1)


def run_scenario(sellers: int, buyers: int, seller_host="127.0.0.1", seller_port=8000, buyer_host="127.0.0.1", buyer_port=8001):
    seller_ctxs = [setup_seller(seller_host, seller_port) for _ in range(sellers)]
    buyer_ctxs = [setup_buyer(buyer_host, buyer_port) for _ in range(buyers)]

    item_id = seller_ctxs[0].item_id if seller_ctxs else None
    avg_rt_seller = measure_avg_response_time(lambda: seller_call(seller_ctxs[0])) if seller_ctxs else 0.0
    avg_rt_buyer = measure_avg_response_time(lambda: buyer_call(buyer_ctxs[0], item_id)) if buyer_ctxs and item_id else 0.0

    seller_fns = [lambda ctx=ctx: seller_call(ctx) for ctx in seller_ctxs]
    buyer_fns = [lambda ctx=ctx, iid=item_id: buyer_call(ctx, iid) for ctx in buyer_ctxs] if item_id else []
    avg_tput = measure_throughput(seller_fns + buyer_fns) if (seller_fns or buyer_fns) else 0.0

    for ctx in seller_ctxs:
        try:
            ctx.client.logout()
        except Exception:
            pass
    for ctx in buyer_ctxs:
        try:
            ctx.client.logout()
        except Exception:
            pass

    return {
        "sellers": sellers,
        "buyers": buyers,
        "avg_response_time_seller": avg_rt_seller,
        "avg_response_time_buyer": avg_rt_buyer,
        "avg_throughput_ops_per_sec": avg_tput,
    }


def main():
    for sellers, buyers in [(1, 1), (10, 10), (100, 100)]:
        print(run_scenario(sellers, buyers))


if __name__ == "__main__":
    main()
