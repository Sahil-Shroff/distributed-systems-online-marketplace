from __future__ import annotations

from dataclasses import dataclass

from server_side.customer_db.backends.in_memory import InMemoryClock, InMemoryCustomerRepository, InMemoryIdAllocator
from server_side.customer_db.service import CustomerDbService


@dataclass
class Replica:
    name: str
    repository: InMemoryCustomerRepository
    allocator: InMemoryIdAllocator
    clock: InMemoryClock
    service: CustomerDbService


def build_inmemory_replicas(count: int) -> list[Replica]:
    replicas: list[Replica] = []
    for idx in range(count):
        repository = InMemoryCustomerRepository()
        allocator = InMemoryIdAllocator()
        clock = InMemoryClock()
        service = CustomerDbService(repository=repository, allocator=allocator, clock=clock)
        replicas.append(
            Replica(
                name=f"replica-{idx}",
                repository=repository,
                allocator=allocator,
                clock=clock,
                service=service,
            )
        )
    return replicas
