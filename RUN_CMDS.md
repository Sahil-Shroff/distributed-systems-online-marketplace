# PA3 Run Commands

## 1) Create/reset local replica SQLite databases
```powershell
python run.py setup-customer-replica-dbs --count 5 --reset
```

## 2) Start one gRPC customer-db service
```powershell
python run.py db-service
```

Typical per-replica env vars:
```powershell
$env:CUSTOMER_DB_NAME='customer-database.sqlite'
$env:CUSTOMER_DB_PATH='database\customer-db-replica_0\customer-database.sqlite'
$env:CUSTOMER_DB_REPLICA_ID='0'
$env:CUSTOMER_DB_REPLICA_PEERS='0:127.0.0.1:56061,1:127.0.0.1:56062,2:127.0.0.1:56063,3:127.0.0.1:56064,4:127.0.0.1:56065'
$env:CUSTOMER_DB_REPLICATION_BIND_HOST='127.0.0.1'
$env:CUSTOMER_DB_REPLICATION_BIND_PORT='56061'
$env:DB_SERVICE_BIND='127.0.0.1:55061'
$env:CUSTOMER_DB_REPLICATION_DELIVERY_TIMEOUT='30'
$env:CUSTOMER_DB_REPLICATION_SCAN_INTERVAL='0.1'
```

Optional debug:
```powershell
$env:CUSTOMER_DB_REPLICATION_DEBUG='1'
```

## 3) Start all 5 customer-db services with one command
```powershell
python run.py customer-db-replica-cluster --replicas 5 --database-prefix customer-db-replica_ --grpc-base-port 55061 --udp-base-port 56061
```

## 4) Smoke test against already-running replicas
```powershell
python tools/customer_db_replication_smoke.py --use-existing --replicas 5 --grpc-base-port 55061
```

## 5) Smoke test with launcher-managed cluster
```powershell
python tools/customer_db_replication_smoke.py customer-db-replica_ --replicas 5
```

## 6) Run tests
```powershell
python -m unittest discover -s server_side/customer_db/tests -p "test_*.py" -v
```

## 7) Start SOAP financial transactions service
```powershell
python run.py financial-service
```

Optional env:
```powershell
$env:FINANCIAL_SERVICE_HOST='0.0.0.0'
$env:FINANCIAL_SERVICE_PORT='8002'
```
