from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server_side.customer_db.replication.local_cluster import LocalCustomerDbReplicaCluster


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local multi-process customer-db replica cluster.")
    parser.add_argument("--replicas", type=int, default=3)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--grpc-base-port", type=int, default=50061)
    parser.add_argument("--udp-base-port", type=int, default=51061)
    parser.add_argument(
        "--database-prefix",
        default=None,
        help="Use databases under database/<prefix>0, <prefix>1, ... instead of the default runtime/sqlite/customer-db-replica_* layout",
    )
    args = parser.parse_args()

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
            print(
                f"  replica={replica.replica_id} grpc={replica.grpc_target} "
                f"udp={replica.udp_host}:{replica.udp_port} db={cluster.database_paths[replica.replica_id]}"
            )
        print("Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        cluster.stop()


if __name__ == "__main__":
    main()
