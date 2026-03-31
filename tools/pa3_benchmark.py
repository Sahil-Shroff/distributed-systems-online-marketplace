from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import subprocess
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


SCENARIOS = {"1": (1, 1), "2": (10, 10), "3": (100, 100)}
DEFAULT_FAILURE_MODES = ["no_failures", "frontend_failure", "product_follower_failure", "product_leader_failure"]


@dataclass
class SellerCtx:
    client: SellerRestClient
    username: str
    password: str
    item_id: int


@dataclass
class BuyerCtx:
    client: BuyerRestClient
    username: str
    password: str


class BenchmarkSuite:
    def __init__(self, buyer_targets: str, seller_targets: str):
        self.buyer_targets = buyer_targets
        self.seller_targets = seller_targets

    def setup_scenario(self, seller_count: int, buyer_count: int) -> tuple[list[SellerCtx], list[BuyerCtx]]:
        sellers = [self._setup_seller(i) for i in range(seller_count)]
        buyers = [self._setup_buyer(i) for i in range(buyer_count)]
        return sellers, buyers

    def cleanup(self, sellers: list[SellerCtx], buyers: list[BuyerCtx]) -> None:
        for seller in sellers:
            try:
                seller.client.logout()
            except Exception:
                pass
        for buyer in buyers:
            try:
                buyer.client.logout()
            except Exception:
                pass

    def _setup_seller(self, index: int) -> SellerCtx:
        client = SellerRestClient(self.seller_targets, 0)
        username = f"bench_seller_{index}_{uuid.uuid4().hex[:8]}"
        password = "pass123"
        client.create_account(username, password)
        client.login(username, password)
        item_id = client.register_item_for_sale("BenchItem", 1, ["bench", "raft"], "New", 10.0, 100000)
        return SellerCtx(client=client, username=username, password=password, item_id=item_id)

    def _setup_buyer(self, index: int) -> BuyerCtx:
        client = BuyerRestClient(self.buyer_targets, 0)
        username = f"bench_buyer_{index}_{uuid.uuid4().hex[:8]}"
        password = "pass123"
        client.create_account(username, password)
        client.login(username, password)
        return BuyerCtx(client=client, username=username, password=password)

    def response_time_functions(self, sellers: list[SellerCtx], buyers: list[BuyerCtx]) -> dict[str, Callable[[], object]]:
        primary_seller = sellers[0]
        primary_buyer = buyers[0]

        def seller_create_account():
            client = SellerRestClient(self.seller_targets, 0)
            uname = f"rt_seller_{uuid.uuid4().hex[:8]}"
            return client.create_account(uname, "pw")

        def seller_login():
            return primary_seller.client.login(primary_seller.username, primary_seller.password)

        def seller_logout():
            primary_seller.client.logout()
            primary_seller.client.login(primary_seller.username, primary_seller.password)
            return {"status": "success"}

        def seller_get_rating():
            return primary_seller.client.get_rating()

        def seller_register_item():
            return primary_seller.client.register_item_for_sale("LatencyItem", 1, ["latency"], "New", 20.0, 50)

        def seller_change_price():
            return primary_seller.client.change_item_price(primary_seller.item_id, 11.0)

        def seller_update_quantity():
            return primary_seller.client.update_units_for_sale(primary_seller.item_id, -1)

        def seller_list_items():
            return primary_seller.client.display_items_for_sale()

        def seller_get_item():
            return primary_seller.client.get_item(primary_seller.item_id)

        def buyer_create_account():
            client = BuyerRestClient(self.buyer_targets, 0)
            uname = f"rt_buyer_{uuid.uuid4().hex[:8]}"
            return client.create_account(uname, "pw")

        def buyer_login():
            return primary_buyer.client.login(primary_buyer.username, primary_buyer.password)

        def buyer_logout():
            primary_buyer.client.logout()
            primary_buyer.client.login(primary_buyer.username, primary_buyer.password)
            return {"status": "success"}

        def buyer_search_items():
            return primary_buyer.client.search_items(1, ["bench"])

        def buyer_get_item():
            return primary_buyer.client.get_item(primary_seller.item_id)

        def buyer_add_to_cart():
            primary_buyer.client.clear_cart()
            return primary_buyer.client.add_to_cart(primary_seller.item_id, 1)

        def buyer_display_cart():
            primary_buyer.client.clear_cart()
            primary_buyer.client.add_to_cart(primary_seller.item_id, 1)
            return primary_buyer.client.display_cart()

        def buyer_save_cart():
            primary_buyer.client.clear_cart()
            primary_buyer.client.add_to_cart(primary_seller.item_id, 1)
            return primary_buyer.client.save_cart()

        def buyer_remove_from_cart():
            primary_buyer.client.clear_cart()
            primary_buyer.client.add_to_cart(primary_seller.item_id, 1)
            return primary_buyer.client.remove_from_cart(primary_seller.item_id)

        def buyer_clear_cart():
            primary_buyer.client.add_to_cart(primary_seller.item_id, 1)
            return primary_buyer.client.clear_cart()

        def buyer_provide_feedback():
            return primary_buyer.client.provide_feedback(primary_seller.item_id, True)

        def buyer_get_purchase_history():
            return primary_buyer.client.get_purchase_history()

        def buyer_get_seller_rating():
            return primary_buyer.client.get_seller_rating(primary_seller.client.seller_id)

        def buyer_make_purchase():
            primary_buyer.client.clear_cart()
            primary_buyer.client.add_to_cart(primary_seller.item_id, 1)
            primary_buyer.client.save_cart()
            return primary_buyer.client.make_purchase("bench-user", "4111111111111111", "12/30", "123")

        return {
            "seller_create_account": seller_create_account,
            "seller_login": seller_login,
            "seller_logout": seller_logout,
            "seller_get_rating": seller_get_rating,
            "seller_register_item": seller_register_item,
            "seller_change_price": seller_change_price,
            "seller_update_quantity": seller_update_quantity,
            "seller_list_items": seller_list_items,
            "seller_get_item": seller_get_item,
            "buyer_create_account": buyer_create_account,
            "buyer_login": buyer_login,
            "buyer_logout": buyer_logout,
            "buyer_search_items": buyer_search_items,
            "buyer_get_item": buyer_get_item,
            "buyer_add_to_cart": buyer_add_to_cart,
            "buyer_display_cart": buyer_display_cart,
            "buyer_save_cart": buyer_save_cart,
            "buyer_remove_from_cart": buyer_remove_from_cart,
            "buyer_clear_cart": buyer_clear_cart,
            "buyer_provide_feedback": buyer_provide_feedback,
            "buyer_get_purchase_history": buyer_get_purchase_history,
            "buyer_get_seller_rating": buyer_get_seller_rating,
            "buyer_make_purchase": buyer_make_purchase,
        }

    def throughput_operations(
        self,
        sellers: list[SellerCtx],
        buyers: list[BuyerCtx],
        selected_names: list[str] | None = None,
        read_weight: int = 3,
        write_weight: int = 1,
    ) -> list[Callable[[], None]]:
        if selected_names:
            response_fns = self.response_time_functions(sellers, buyers)
            read_ops = [response_fns[name] for name in selected_names if name in {"seller_list_items", "seller_get_item", "buyer_search_items", "buyer_get_item"}]
            write_ops = [response_fns[name] for name in selected_names if name in {"seller_change_price", "seller_update_quantity", "buyer_add_to_cart", "buyer_save_cart", "buyer_remove_from_cart", "buyer_clear_cart", "buyer_provide_feedback", "buyer_make_purchase"}]
            weighted_ops: list[Callable[[], None]] = []
            for op in read_ops:
                weighted_ops.extend([op] * max(read_weight, 1))
            for op in write_ops:
                weighted_ops.extend([op] * max(write_weight, 1))
            return weighted_ops

        seller_ops = []
        for seller in sellers:
            seller_ops.append(lambda seller=seller: seller.client.display_items_for_sale())
        buyer_ops = []
        primary_item = sellers[0].item_id
        for buyer in buyers:
            buyer_ops.append(lambda buyer=buyer, item_id=primary_item: buyer.client.search_items(1, ["bench"]))
            buyer_ops.append(lambda buyer=buyer, item_id=primary_item: buyer.client.get_item(item_id))
            buyer_ops.append(lambda buyer=buyer, item_id=primary_item: buyer.client.add_to_cart(item_id, 1))
        return seller_ops + buyer_ops


def run_failure_hook(command: str | None, wait_seconds: float) -> None:
    if not command:
        return
    subprocess.run(command, shell=True, check=True)
    time.sleep(wait_seconds)


def measure_avg_response_time(fn: Callable[[], object], runs: int = 10) -> dict[str, object]:
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return {"average_seconds": statistics.mean(samples), "samples": samples}


def measure_throughput(clients: list[Callable[[], None]], runs: int = 10, ops_per_client: int = 1000) -> dict[str, object]:
    samples = []
    total_ops = ops_per_client * len(clients)
    for _ in range(runs):
        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(len(clients), 1)) as pool:
            futures = [pool.submit(lambda fn=fn: [fn() for _ in range(ops_per_client)]) for fn in clients]
            concurrent.futures.wait(futures)
        elapsed = time.perf_counter() - start
        samples.append(total_ops / elapsed if elapsed > 0 else 0.0)
    return {"average_ops_per_sec": statistics.mean(samples), "samples": samples, "ops_per_client": ops_per_client}


def benchmark_condition(
    suite: BenchmarkSuite,
    sellers: int,
    buyers: int,
    response_runs: int,
    throughput_runs: int,
    ops_per_client: int,
    failure_mode: str,
    frontend_failure_hook: str | None,
    product_follower_failure_hook: str | None,
    product_leader_failure_hook: str | None,
    wait_after_failure: float,
    response_functions: list[str] | None,
    throughput_functions: list[str] | None,
    throughput_read_weight: int,
    throughput_write_weight: int,
) -> dict[str, object]:
    seller_ctxs, buyer_ctxs = suite.setup_scenario(sellers, buyers)
    try:
        if failure_mode == "frontend_failure":
            run_failure_hook(frontend_failure_hook, wait_after_failure)
        elif failure_mode == "product_follower_failure":
            run_failure_hook(product_follower_failure_hook, wait_after_failure)
        elif failure_mode == "product_leader_failure":
            run_failure_hook(product_leader_failure_hook, wait_after_failure)

        response_results = {}
        all_functions = suite.response_time_functions(seller_ctxs, buyer_ctxs)
        active_function_names = response_functions or list(all_functions.keys())
        for name in active_function_names:
            fn = all_functions[name]
            try:
                response_results[name] = measure_avg_response_time(fn, runs=response_runs)
            except Exception as exc:
                response_results[name] = {"error": str(exc)}

        throughput_results = {}
        try:
            throughput_results["mixed_workload"] = measure_throughput(
                suite.throughput_operations(
                    seller_ctxs,
                    buyer_ctxs,
                    selected_names=throughput_functions,
                    read_weight=throughput_read_weight,
                    write_weight=throughput_write_weight,
                ),
                runs=throughput_runs,
                ops_per_client=ops_per_client,
            )
        except Exception as exc:
            throughput_results["mixed_workload"] = {"error": str(exc)}

        return {
            "seller_clients": sellers,
            "buyer_clients": buyers,
            "failure_mode": failure_mode,
            "response_times": response_results,
            "throughput": throughput_results,
        }
    finally:
        suite.cleanup(seller_ctxs, buyer_ctxs)


def main():
    parser = argparse.ArgumentParser(description="PA3 benchmark runner for deployed frontends/backends.")
    parser.add_argument("--buyer-frontends", required=True, help="Comma-separated buyer frontend addresses, e.g. 10.0.0.1:8001,10.0.0.2:8001")
    parser.add_argument("--seller-frontends", required=True, help="Comma-separated seller frontend addresses")
    parser.add_argument("--scenarios", nargs="+", default=["1", "2", "3"], choices=["1", "2", "3"])
    parser.add_argument("--failure-modes", nargs="+", default=DEFAULT_FAILURE_MODES, choices=DEFAULT_FAILURE_MODES)
    parser.add_argument("--response-runs", type=int, default=10)
    parser.add_argument("--throughput-runs", type=int, default=10)
    parser.add_argument("--ops-per-client", type=int, default=1000)
    parser.add_argument("--frontend-failure-hook", default=None, help="Command to kill one buyer and one seller frontend replica")
    parser.add_argument("--product-follower-failure-hook", default=None, help="Command to kill one product follower replica")
    parser.add_argument("--product-leader-failure-hook", default=None, help="Command to kill the product leader replica")
    parser.add_argument("--wait-after-failure", type=float, default=8.0)
    parser.add_argument("--output", default="runtime/pa3_benchmark_results.json")
    parser.add_argument("--response-functions", nargs="+", default=None, help="Subset of response-time functions to execute")
    parser.add_argument("--throughput-functions", nargs="+", default=None, help="Subset of functions to use in throughput mode")
    parser.add_argument("--throughput-read-weight", type=int, default=3, help="Relative weight of read operations in throughput mode")
    parser.add_argument("--throughput-write-weight", type=int, default=1, help="Relative weight of write operations in throughput mode")
    args = parser.parse_args()

    suite = BenchmarkSuite(args.buyer_frontends, args.seller_frontends)
    results = {
        "buyer_frontends": args.buyer_frontends,
        "seller_frontends": args.seller_frontends,
        "response_runs": args.response_runs,
        "throughput_runs": args.throughput_runs,
        "ops_per_client": args.ops_per_client,
        "response_functions": args.response_functions,
        "throughput_functions": args.throughput_functions,
        "throughput_read_weight": args.throughput_read_weight,
        "throughput_write_weight": args.throughput_write_weight,
        "results": {},
    }

    for scenario in args.scenarios:
        seller_count, buyer_count = SCENARIOS[scenario]
        scenario_key = f"scenario_{scenario}"
        results["results"][scenario_key] = {}
        for failure_mode in args.failure_modes:
            print(f"Running scenario={scenario_key} failure_mode={failure_mode} sellers={seller_count} buyers={buyer_count}")
            results["results"][scenario_key][failure_mode] = benchmark_condition(
                suite=suite,
                sellers=seller_count,
                buyers=buyer_count,
                response_runs=args.response_runs,
                throughput_runs=args.throughput_runs,
                ops_per_client=args.ops_per_client,
                failure_mode=failure_mode,
                frontend_failure_hook=args.frontend_failure_hook,
                product_follower_failure_hook=args.product_follower_failure_hook,
                product_leader_failure_hook=args.product_leader_failure_hook,
                wait_after_failure=args.wait_after_failure,
                response_functions=args.response_functions,
                throughput_functions=args.throughput_functions,
                throughput_read_weight=args.throughput_read_weight,
                throughput_write_weight=args.throughput_write_weight,
            )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"\nWrote results to {output_path}")


if __name__ == "__main__":
    main()
