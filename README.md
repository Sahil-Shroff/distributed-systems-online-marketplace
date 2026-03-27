# PA3 Customer-DB Replication

This repository now contains the PA3 customer-database implementation centered on:
- PostgreSQL-backed customer-db state
- deterministic customer-db operations
- rotating-sequencer atomic broadcast over UDP
- gRPC service entrypoints for customer-db mutations and reads

## Main Components
- [server_side/db_service.py](f:/MS%20CS/Distributed%20Systems/distributed-systems-online-marketplace/server_side/db_service.py)
  - gRPC service process
- [server_side/customer_db](f:/MS%20CS/Distributed%20Systems/distributed-systems-online-marketplace/server_side/customer_db)
  - models, operations, repository, service, apply logic
- [server_side/customer_db/replication](f:/MS%20CS/Distributed%20Systems/distributed-systems-online-marketplace/server_side/customer_db/replication)
  - UDP transport, rotating sequencer node, runtime, local cluster helper
- [tools/setup_customer_replica_dbs.py](f:/MS%20CS/Distributed%20Systems/distributed-systems-online-marketplace/tools/setup_customer_replica_dbs.py)
  - creates local replica databases
- [tools/customer_db_replication_smoke.py](f:/MS%20CS/Distributed%20Systems/distributed-systems-online-marketplace/tools/customer_db_replication_smoke.py)
  - end-to-end replicated smoke test

## Folder Layout
```text
server_side/
  db_service.py
  financial_service.py
  data_access_layer/
    db.py
  customer_db/
    apply.py
    models.py
    operations.py
    repository.py
    service.py
    backends/
    replication/
    tests/

tools/
  setup_customer_replica_dbs.py
  run_customer_db_replica_cluster.py
  customer_db_replication_smoke.py

protos/
  database.proto

generated/
  protos/

database/
  create_dbs.*
  drop_dbs.*
```

## Local Workflow
1. Create/reset replica databases.
2. Start one `db_service` per replica, or use the cluster launcher.
3. Submit customer-db RPCs to any replica.
4. Replication orders and delivers the mutation before the entry replica returns.

## Tests
Run the customer-db test suite:
```bash
python -m unittest discover -s server_side/customer_db/tests -p "test_*.py" -v
```
