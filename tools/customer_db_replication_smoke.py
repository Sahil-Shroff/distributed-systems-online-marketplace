from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

import grpc

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATED_ROOT = REPO_ROOT / "generated"
if str(GENERATED_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATED_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from protos import database_pb2, database_pb2_grpc  # noqa: E402
from server_side.customer_db.replication.local_cluster import LocalCustomerDbReplicaCluster  # noqa: E402


def _retry_rpc(fn, *, attempts: int = 10, sleep_seconds: float = 0.5):
    last_error = None
    for _ in range(attempts):
        try:
            return fn()
        except grpc.RpcError as exc:
            last_error = exc
            time.sleep(sleep_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError("retry loop ended without result")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a replicated customer-db gRPC smoke test.")
    parser.add_argument("database_prefix", nargs="?", default=None)
    parser.add_argument("--replicas", type=int, default=3)
    parser.add_argument("--grpc-base-port", type=int, default=55061)
    parser.add_argument("--udp-base-port", type=int, default=56061)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--use-existing",
        action="store_true",
        help="Connect to already-running db_service replicas instead of launching a local cluster",
    )
    args = parser.parse_args()

    cluster = None
    if args.use_existing:
        replica_targets = [f"{args.host}:{args.grpc_base_port + idx}" for idx in range(args.replicas)]
    else:
        cluster = LocalCustomerDbReplicaCluster(
            replica_count=args.replicas,
            database_prefix=args.database_prefix,
            grpc_base_port=args.grpc_base_port,
            udp_base_port=args.udp_base_port,
            host=args.host,
        )
        cluster.start(startup_timeout_seconds=30)
        cluster.wait_for_grpc_ready(timeout_seconds=30)
        replica_targets = [replica.grpc_target for replica in cluster.replicas]

    create_channel = grpc.insecure_channel(replica_targets[0])
    auth_channel = grpc.insecure_channel(replica_targets[1])
    verify_channel = grpc.insecure_channel(replica_targets[-1])
    try:
        create_stub = database_pb2_grpc.DatabaseServiceStub(create_channel)
        auth_stub = database_pb2_grpc.DatabaseServiceStub(auth_channel)
        verify_stub = database_pb2_grpc.DatabaseServiceStub(verify_channel)

        username = f"replicated_seller_smoke_{uuid.uuid4().hex[:8]}"
        password = "pw"
        created = create_stub.CreateAccount(
            database_pb2.CreateAccountRequest(role="seller", username=username, password=password)
        )
        authenticated = _retry_rpc(
            lambda: auth_stub.AuthenticateUser(
                database_pb2.AuthenticateRequest(role="seller", username=username, password=password)
            )
        )
        verified = _retry_rpc(
            lambda: verify_stub.VerifySession(
                database_pb2.VerifySessionRequest(session_id=authenticated.session_id)
            )
        )

        db_paths = cluster.database_paths if cluster is not None else []
        print(
            {
                "created_seller_id": created.user_id,
                "authenticated_user_id": authenticated.user_id,
                "session_id": authenticated.session_id,
                "verified_role": verified.role,
                "db_paths": db_paths,
                "targets": replica_targets,
            }
        )
    finally:
        create_channel.close()
        auth_channel.close()
        verify_channel.close()
        if cluster is not None:
            cluster.stop()


if __name__ == "__main__":
    main()
