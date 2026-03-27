import unittest

from server_side.customer_db.operations import CompletePurchase
from server_side.customer_db.tests.postgres_support import (
    create_isolated_postgres_replicas,
    drop_isolated_postgres_replicas,
    postgres_tests_enabled,
)


@unittest.skipUnless(postgres_tests_enabled(), "Set RUN_CUSTOMER_DB_POSTGRES_TESTS=1 to run Postgres customer-db tests")
class CustomerServicePostgresTests(unittest.TestCase):
    def setUp(self):
        self.replicas = create_isolated_postgres_replicas(2)

    def tearDown(self):
        drop_isolated_postgres_replicas(self.replicas)

    def test_replay_create_seller_across_postgres_replicas(self):
        leader = self.replicas[0].service
        operation = leader.build_create_seller("pg_seller", "pw")

        for replica in self.replicas:
            replica.service.apply_replicated(operation)

        seller0 = self.replicas[0].repository.get_seller(operation.seller_id)
        seller1 = self.replicas[1].repository.get_seller(operation.seller_id)
        self.assertEqual(seller0, seller1)

    def test_core_customer_mutations_have_backend_parity(self):
        seller_op = self.replicas[0].service.build_create_seller("pg_seller", "pw")
        buyer_op = self.replicas[0].service.build_create_buyer("pg_buyer", "pw")
        feedback_op = self.replicas[0].service.build_update_seller_feedback(seller_op.seller_id, True)
        purchase_op = CompletePurchase(buyer_id=buyer_op.buyer_id, seller_id=seller_op.seller_id, quantity=2)

        for replica in self.replicas:
            replica.service.apply_replicated(seller_op)
            replica.service.apply_replicated(buyer_op)
            replica.service.apply_replicated(feedback_op)
            replica.service.apply_replicated(purchase_op)

        for replica in self.replicas:
            seller = replica.repository.get_seller(seller_op.seller_id)
            buyer = replica.repository.get_buyer(buyer_op.buyer_id)
            self.assertEqual(seller.seller_feedback, (1, 0))
            self.assertEqual(seller.items_sold, 2)
            self.assertEqual(buyer.items_purchased, 2)


if __name__ == "__main__":
    unittest.main()
