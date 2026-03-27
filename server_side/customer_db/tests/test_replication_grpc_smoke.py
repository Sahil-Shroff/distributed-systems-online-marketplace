from __future__ import annotations

import os
import sqlite3
import sys
import time
import unittest

import grpc

from server_side.customer_db.replication.local_cluster import LocalCustomerDbReplicaCluster


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
GENERATED_ROOT = os.path.join(REPO_ROOT, "generated")
if GENERATED_ROOT not in sys.path:
    sys.path.insert(0, GENERATED_ROOT)

from protos import database_pb2, database_pb2_grpc  # noqa: E402


@unittest.skipUnless(
    os.getenv("RUN_CUSTOMER_DB_REPLICATION_SMOKE", "0") == "1",
    "Set RUN_CUSTOMER_DB_REPLICATION_SMOKE=1 to run replicated gRPC smoke test",
)
class CustomerDbReplicationGrpcSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cluster = LocalCustomerDbReplicaCluster(replica_count=3)
        self.cluster.start()
        self.cluster.wait_for_grpc_ready()

    def tearDown(self) -> None:
        self.cluster.stop()

    def test_create_authenticate_and_verify_across_replicas(self) -> None:
        create_channel = grpc.insecure_channel(self.cluster.replicas[0].grpc_target)
        auth_channel = grpc.insecure_channel(self.cluster.replicas[1].grpc_target)
        verify_channel = grpc.insecure_channel(self.cluster.replicas[2].grpc_target)
        try:
            create_stub = database_pb2_grpc.DatabaseServiceStub(create_channel)
            auth_stub = database_pb2_grpc.DatabaseServiceStub(auth_channel)
            verify_stub = database_pb2_grpc.DatabaseServiceStub(verify_channel)

            username = "replicated_seller_smoke"
            password = "pw"
            created = create_stub.CreateAccount(
                database_pb2.CreateAccountRequest(role="seller", username=username, password=password)
            )
            seller_id = created.user_id

            authenticated = auth_stub.AuthenticateUser(
                database_pb2.AuthenticateRequest(role="seller", username=username, password=password)
            )
            self.assertEqual(authenticated.user_id, seller_id)

            time.sleep(2)
            verified = verify_stub.VerifySession(
                database_pb2.VerifySessionRequest(session_id=authenticated.session_id)
            )
            self.assertEqual(verified.user_id, seller_id)
            self.assertEqual(verified.role, "seller")

            for db_path in self.cluster.database_paths:
                self.assertEqual(self._seller_count(db_path, seller_id), 1)
                self.assertEqual(self._session_count(db_path, authenticated.session_id), 1)
        finally:
            create_channel.close()
            auth_channel.close()
            verify_channel.close()

    def _seller_count(self, db_path: str, seller_id: int) -> int:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM sellers WHERE seller_id = ?", (seller_id,))
            return int(cur.fetchone()[0])
        finally:
            conn.close()

    def _session_count(self, db_path: str, session_id: str) -> int:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM sessions WHERE session_id = ?", (session_id,))
            return int(cur.fetchone()[0])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
