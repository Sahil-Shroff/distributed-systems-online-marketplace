import unittest
from datetime import datetime, timedelta, timezone

from server_side.customer_db.backends.in_memory import InMemoryClock, InMemoryCustomerRepository, InMemoryIdAllocator
from server_side.customer_db.service import AuthenticationError, CustomerDbService, SessionError


class CountingAllocator(InMemoryIdAllocator):
    def __init__(self):
        super().__init__()
        self.buyer_calls = 0
        self.seller_calls = 0
        self.session_calls = 0

    def next_buyer_id(self) -> int:
        self.buyer_calls += 1
        return super().next_buyer_id()

    def next_seller_id(self) -> int:
        self.seller_calls += 1
        return super().next_seller_id()

    def next_session_id(self) -> str:
        self.session_calls += 1
        return super().next_session_id()


class CountingClock(InMemoryClock):
    def __init__(self, initial: datetime):
        super().__init__(initial)
        self.calls = 0

    def now(self) -> datetime:
        self.calls += 1
        return super().now()


class CustomerServiceInMemoryTests(unittest.TestCase):
    def setUp(self):
        self.clock = InMemoryClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.repo = InMemoryCustomerRepository()
        self.allocator = InMemoryIdAllocator()
        self.service = CustomerDbService(self.repo, self.allocator, self.clock)

    def test_create_and_login_buyer(self):
        create_op = self.service.create_buyer("alice", "pw")
        buyer, session_op = self.service.login_buyer("alice", "pw")

        self.assertEqual(create_op.buyer_id, 1)
        self.assertEqual(buyer.buyer_id, 1)
        self.assertEqual(session_op.session_id, "1")
        self.assertEqual(session_op.created_at, self.clock.now())

    def test_create_and_login_seller(self):
        create_op = self.service.create_seller("bob", "pw")
        seller, session_op = self.service.login_seller("bob", "pw")

        self.assertEqual(create_op.seller_id, 1000)
        self.assertEqual(seller.seller_id, 1000)
        self.assertEqual(session_op.session_id, "1")

    def test_invalid_login_raises(self):
        self.service.create_buyer("alice", "pw")
        with self.assertRaises(AuthenticationError):
            self.service.login_buyer("alice", "wrong")

    def test_verify_session_touches_timestamp(self):
        self.service.create_buyer("alice", "pw")
        _, session_op = self.service.login_buyer("alice", "pw")

        self.clock.set(self.clock.now() + timedelta(minutes=1))
        result = self.service.verify_session(session_op.session_id)

        self.assertEqual(result.session.last_access_timestamp, self.clock.now())
        self.assertEqual(result.touch_operation.touched_at, self.clock.now())

    def test_verify_session_expired(self):
        self.service.create_buyer("alice", "pw")
        _, session_op = self.service.login_buyer("alice", "pw")

        self.clock.set(self.clock.now() + timedelta(minutes=6))
        with self.assertRaises(SessionError):
            self.service.verify_session(session_op.session_id)

    def test_logout_scope_all(self):
        self.service.create_buyer("alice", "pw")
        buyer, session1 = self.service.login_buyer("alice", "pw")
        _, session2 = self.service.login_buyer("alice", "pw")

        self.service.logout(session_id=session1.session_id, user_id=buyer.buyer_id, role="buyer", scope="all")

        self.assertIsNone(self.repo.get_session(session1.session_id))
        self.assertIsNone(self.repo.get_session(session2.session_id))

    def test_feedback_and_purchase(self):
        buyer_op = self.service.create_buyer("alice", "pw")
        seller_op = self.service.create_seller("bob", "pw")

        self.service.apply_seller_feedback(seller_op.seller_id, is_positive=True)
        self.service.complete_purchase(buyer_op.buyer_id, seller_op.seller_id, quantity=2)

        self.assertEqual(self.service.get_seller_feedback_counts(seller_op.seller_id), (1, 0))
        self.assertEqual(self.repo.get_buyer(buyer_op.buyer_id).items_purchased, 2)
        self.assertEqual(self.repo.get_seller(seller_op.seller_id).items_sold, 2)

    def test_build_once_replay_on_multiple_replicas(self):
        leader_clock = CountingClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
        leader_allocator = CountingAllocator()
        leader = CustomerDbService(InMemoryCustomerRepository(), leader_allocator, leader_clock)
        followers: list[tuple[CustomerDbService, CountingAllocator, CountingClock]] = []
        for _ in range(2):
            allocator = CountingAllocator()
            clock = CountingClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
            followers.append((CustomerDbService(InMemoryCustomerRepository(), allocator, clock), allocator, clock))

        operation = leader.build_create_seller("replicated", "pw")
        leader.apply_replicated(operation)
        for follower, _, _ in followers:
            follower.apply_replicated(operation)

        self.assertEqual(leader_allocator.seller_calls, 1)
        self.assertEqual(leader_clock.calls, 0)
        for follower, allocator, clock in followers:
            seller = follower.repository.get_seller(operation.seller_id)
            self.assertIsNotNone(seller)
            self.assertEqual(seller.username, "replicated")
            self.assertEqual(allocator.seller_calls, 0)
            self.assertEqual(clock.calls, 0)

    def test_followers_do_not_allocate_session_ids_or_timestamps(self):
        leader_allocator = CountingAllocator()
        leader_clock = CountingClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
        leader = CustomerDbService(InMemoryCustomerRepository(), leader_allocator, leader_clock)
        leader.apply_replicated(leader.build_create_buyer("alice", "pw"))

        follower_allocator = CountingAllocator()
        follower_clock = CountingClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
        follower = CustomerDbService(InMemoryCustomerRepository(), follower_allocator, follower_clock)
        follower.apply_replicated(leader.build_create_buyer("alice", "pw"))

        operation = leader.build_create_session(role="buyer", user_id=1)
        leader.apply_replicated(operation)
        follower.apply_replicated(operation)

        self.assertEqual(leader_allocator.session_calls, 1)
        self.assertGreaterEqual(leader_clock.calls, 1)
        self.assertEqual(follower_allocator.session_calls, 0)
        self.assertEqual(follower_clock.calls, 0)
        self.assertEqual(follower.repository.get_session(operation.session_id).last_access_timestamp, operation.created_at)


if __name__ == "__main__":
    unittest.main()
