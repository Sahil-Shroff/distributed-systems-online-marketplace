import unittest
from datetime import datetime, timezone

from server_side.customer_db.backends.in_memory import InMemoryClock, InMemoryCustomerRepository, InMemoryIdAllocator
from server_side.customer_db.replication.messages import RequestMessage, RetransmitRequestMessage, SequenceMessage
from server_side.customer_db.replication.node import RotatingSequencerNode
from server_side.customer_db.service import CustomerDbService


class ReplicaBundle:
    def __init__(self, replica_id: int):
        self.repository = InMemoryCustomerRepository()
        self.allocator = InMemoryIdAllocator()
        self.clock = InMemoryClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.service = CustomerDbService(self.repository, self.allocator, self.clock)
        self.node = None


class FakeTransport:
    def __init__(self):
        self.nodes: dict[int, RotatingSequencerNode] = {}
        self.drop_once: set[tuple[int, int, str]] = set()

    def register(self, replica_id: int, node: RotatingSequencerNode) -> None:
        self.nodes[replica_id] = node

    def broadcast(self, message) -> None:
        for replica_id in self.nodes:
            self.send(replica_id, message)

    def send(self, target_replica_id: int, message) -> None:
        key = (getattr(message, "source_replica_id"), target_replica_id, getattr(message, "kind"))
        if key in self.drop_once:
            self.drop_once.remove(key)
            return
        self._deliver(target_replica_id, message)

    def _deliver(self, target_replica_id: int, message) -> None:
        node = self.nodes[target_replica_id]
        if isinstance(message, RequestMessage):
            node.on_request_receive(message)
        elif isinstance(message, SequenceMessage):
            node.on_sequence_receive(message)
        elif isinstance(message, RetransmitRequestMessage):
            node.on_retransmit_request_receive(message)
        else:
            raise TypeError(type(message))


class RotatingSequencerNodeTests(unittest.TestCase):
    def _build_cluster(self, count: int = 3) -> list[ReplicaBundle]:
        transport = FakeTransport()
        replicas: list[ReplicaBundle] = []
        for replica_id in range(count):
            bundle = ReplicaBundle(replica_id)
            node = RotatingSequencerNode(
                replica_id=replica_id,
                num_replicas=count,
                transport=transport,
                apply_callback=bundle.service.apply_replicated,
            )
            bundle.node = node
            transport.register(replica_id, node)
            replicas.append(bundle)
        self.transport = transport
        return replicas

    def test_client_mutation_to_non_sequencer_delivers_to_all(self):
        replicas = self._build_cluster(3)
        operation = replicas[1].service.build_create_seller("seller_a", "pw")

        request_id = replicas[1].node.on_client_mutation(operation)

        for replica in replicas:
            seller = replica.repository.get_seller(operation.seller_id)
            self.assertIsNotNone(seller)
            self.assertEqual(seller.username, "seller_a")
        self.assertEqual(replicas[0].node.sequence_to_request[0], request_id)

    def test_rotating_sequencer_assigns_by_k_mod_n(self):
        replicas = self._build_cluster(3)

        op0 = replicas[1].service.build_create_seller("seller_0", "pw")
        op1 = replicas[2].service.build_create_seller("seller_1", "pw")

        replicas[1].node.on_client_mutation(op0)
        replicas[2].node.on_client_mutation(op1)

        self.assertEqual(replicas[0].node.sequences[0].source_replica_id, 0)
        self.assertEqual(replicas[1].node.sequences[1].source_replica_id, 1)

    def test_missing_request_causes_retransmit_and_delivery(self):
        replicas = self._build_cluster(3)
        self.transport.drop_once.add((1, 2, "request"))

        operation = replicas[1].service.build_create_seller("seller_missing", "pw")
        replicas[1].node.on_client_mutation(operation)

        seller = replicas[2].repository.get_seller(operation.seller_id)
        self.assertIsNotNone(seller)
        self.assertEqual(seller.username, "seller_missing")


if __name__ == "__main__":
    unittest.main()
