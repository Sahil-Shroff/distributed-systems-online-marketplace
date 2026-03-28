import argparse
import os
import sys
from pathlib import Path

import uvicorn

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def run_db_service(_args):
    from server_side.db_service import serve as serve_db_service

    serve_db_service()


def run_financial_service(_args):
    from server_side.financial_service import serve as serve_financial_service

    serve_financial_service()


def run_buyer_rest_server(args):
    from server_side.buyer_interface import buyer_rest_server

    uvicorn.run(
        buyer_rest_server.app,
        host=args.host,
        port=args.port,
        reload=False,
    )


def run_seller_rest_server(args):
    from server_side.seller_interface import seller_rest_server

    uvicorn.run(
        seller_rest_server.app,
        host=args.host,
        port=args.port,
        reload=False,
    )


def run_buyer_rest_cli(args):
    from client_side.buyer_interface import buyer_cli

    original_argv = sys.argv[:]
    try:
        sys.argv = ["buyer_cli.py", args.host, str(args.port)]
        buyer_cli.main()
    finally:
        sys.argv = original_argv


def run_seller_rest_cli(args):
    from client_side.seller_interface import seller_cli

    original_argv = sys.argv[:]
    try:
        sys.argv = ["seller_cli.py", args.host, str(args.port)]
        seller_cli.main()
    finally:
        sys.argv = original_argv


def run_customer_db_replica_cluster(args):
    from server_side.customer_db.replication.local_cluster import LocalCustomerDbReplicaCluster

    cluster = LocalCustomerDbReplicaCluster(
        replica_count=args.replicas,
        grpc_base_port=args.grpc_base_port,
        udp_base_port=args.udp_base_port,
        host=args.host,
        database_prefix=args.database_prefix,
    )
    cluster.start()
    cluster.wait_for_grpc_ready()
    try:
        print("Customer-db replica cluster running:")
        for replica in cluster.replicas:
            db_name = cluster.database_paths[replica.replica_id]
            print(
                f"  replica={replica.replica_id} grpc={replica.grpc_target} "
                f"udp={replica.udp_host}:{replica.udp_port} db={db_name}"
            )
        print("Press Ctrl+C to stop.")
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        cluster.stop()


def run_setup_customer_replica_dbs(args):
    from tools.setup_customer_replica_dbs import create_replica_databases

    created = create_replica_databases(prefix=args.prefix, count=args.count, reset=args.reset)
    print({"databases": created})


def run_product_service(args):
    from server_side import product_service

    os.environ["PRODUCT_SERVICE_BIND"] = f"{args.host}:{args.port}"
    os.environ["PRODUCT_SERVICE_PORT"] = str(args.port)
    product_service.serve()


def main():
    parser = argparse.ArgumentParser(description="Run PA3 marketplace components.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("db-service", help="Run one customer-db gRPC service")
    p.set_defaults(func=run_db_service)

    p = sub.add_parser("financial-service", help="Run the SOAP financial transactions service")
    p.set_defaults(func=run_financial_service)

    p = sub.add_parser("buyer-rest-server", help="Run buyer REST server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8001)
    p.set_defaults(func=run_buyer_rest_server)

    p = sub.add_parser("seller-rest-server", help="Run seller REST server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=run_seller_rest_server)

    p = sub.add_parser("buyer-rest-cli", help="Run buyer REST CLI")
    p.add_argument("host")
    p.add_argument("port", type=int)
    p.set_defaults(func=run_buyer_rest_cli)

    p = sub.add_parser("seller-rest-cli", help="Run seller REST CLI")
    p.add_argument("host")
    p.add_argument("port", type=int)
    p.set_defaults(func=run_seller_rest_cli)

    p = sub.add_parser("customer-db-replica-cluster", help="Run a local multi-process customer-db replica cluster")
    p.add_argument("--replicas", type=int, default=5)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--grpc-base-port", type=int, default=55061)
    p.add_argument("--udp-base-port", type=int, default=56061)
    p.add_argument("--database-prefix", default=None)
    p.set_defaults(func=run_customer_db_replica_cluster)

    p = sub.add_parser("setup-customer-replica-dbs", help="Create or reset local customer-db replica databases")
    p.add_argument("--prefix", default="customer-db-replica_")
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--reset", action="store_true")
    p.set_defaults(func=run_setup_customer_replica_dbs)

    p = sub.add_parser("product-service", help="Run product Raft service")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=50052)
    p.set_defaults(func=run_product_service)

    args = parser.parse_args()
    if args.cmd == "db-service" and "DB_SERVICE_BIND" not in os.environ:
        os.environ.setdefault("DB_SERVICE_BIND", f"0.0.0.0:{os.getenv('DB_SERVICE_PORT', '50051')}")
    args.func(args)


if __name__ == "__main__":
    main()
