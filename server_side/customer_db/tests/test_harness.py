import unittest

from server_side.customer_db.harness.replica_cluster import build_inmemory_replicas


class ReplicaHarnessTests(unittest.TestCase):
    def test_builds_independent_replicas(self):
        replicas = build_inmemory_replicas(5)

        self.assertEqual(len(replicas), 5)
        op = replicas[0].service.create_buyer("alice", "pw")

        self.assertIsNotNone(replicas[0].repository.get_buyer(op.buyer_id))
        for replica in replicas[1:]:
            self.assertIsNone(replica.repository.get_buyer(op.buyer_id))


if __name__ == "__main__":
    unittest.main()
