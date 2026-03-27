import unittest
from datetime import datetime, timezone

from server_side.customer_db.apply import apply_operation
from server_side.customer_db.backends.in_memory import InMemoryCustomerRepository
from server_side.customer_db.operations import (
    CompletePurchase,
    CreateBuyer,
    CreateSeller,
    CreateSession,
    DeleteSession,
    DeleteSessionsForUserRole,
    TouchSession,
    UpdateSellerFeedback,
)


class ApplyOperationTests(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryCustomerRepository()

    def test_apply_create_entities(self):
        apply_operation(self.repo, CreateBuyer(buyer_id=1, username="buyer", password="pw"))
        apply_operation(self.repo, CreateSeller(seller_id=1000, username="seller", password="pw"))
        created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        apply_operation(self.repo, CreateSession(session_id="1", role="buyer", user_id=1, created_at=created_at))

        self.assertEqual(self.repo.get_buyer(1).username, "buyer")
        self.assertEqual(self.repo.get_seller(1000).username, "seller")
        self.assertEqual(self.repo.get_session("1").last_access_timestamp, created_at)

    def test_touch_and_delete_session(self):
        created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        touched_at = datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc)
        apply_operation(self.repo, CreateSession(session_id="7", role="buyer", user_id=1, created_at=created_at))
        apply_operation(self.repo, TouchSession(session_id="7", touched_at=touched_at))
        self.assertEqual(self.repo.get_session("7").last_access_timestamp, touched_at)

        apply_operation(self.repo, DeleteSession(session_id="7"))
        self.assertIsNone(self.repo.get_session("7"))

    def test_delete_sessions_for_user_role(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        apply_operation(self.repo, CreateSession(session_id="1", role="buyer", user_id=1, created_at=now))
        apply_operation(self.repo, CreateSession(session_id="2", role="buyer", user_id=1, created_at=now))
        apply_operation(self.repo, CreateSession(session_id="3", role="seller", user_id=1, created_at=now))

        apply_operation(self.repo, DeleteSessionsForUserRole(user_id=1, role="buyer"))

        self.assertIsNone(self.repo.get_session("1"))
        self.assertIsNone(self.repo.get_session("2"))
        self.assertIsNotNone(self.repo.get_session("3"))

    def test_feedback_and_purchase_counters(self):
        apply_operation(self.repo, CreateBuyer(buyer_id=1, username="buyer", password="pw"))
        apply_operation(self.repo, CreateSeller(seller_id=1000, username="seller", password="pw"))

        apply_operation(self.repo, UpdateSellerFeedback(seller_id=1000, positive_delta=1, negative_delta=0))
        apply_operation(self.repo, CompletePurchase(buyer_id=1, seller_id=1000, quantity=3))

        self.assertEqual(self.repo.get_seller(1000).seller_feedback, (1, 0))
        self.assertEqual(self.repo.get_buyer(1).items_purchased, 3)
        self.assertEqual(self.repo.get_seller(1000).items_sold, 3)


if __name__ == "__main__":
    unittest.main()
