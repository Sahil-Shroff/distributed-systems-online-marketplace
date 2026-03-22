# Run Commands Cheat Sheet

## 1) Create / reset databases (customer + product only; no financial DB)
Windows:
```
set PROJECT=<gcp-project-id>
set ROOT_PW=<postgres-root-password>
database\create_dbs.bat
```
Linux/macOS:
```
PROJECT=<gcp-project-id> ROOT_PW=<postgres-root-password> ./database/create_dbs.sh
```
To reuse an existing instance on Windows, skip creation:
```
set CREATE_INSTANCE=0
database\create_dbs.bat
```

## 2) Start the gRPC DB service
```
python server_side/db_service.py
```
Env (optional):
- Customer DB: `CUSTOMER_PGHOST`, `CUSTOMER_PGPORT`, `CUSTOMER_PGUSER`, `CUSTOMER_PGPASSWORD`, `CUSTOMER_DB_NAME`
- Product DB:  `PRODUCT_PGHOST`, `PRODUCT_PGPORT`, `PRODUCT_PGUSER`, `PRODUCT_PGPASSWORD`, `PRODUCT_DB_NAME`
- Fallbacks: `PGHOST/PGPORT/PGUSER/PGPASSWORD` used if per-DB vars are not set.
- `DB_SERVICE_PORT` (default 50051)

## 3) Start servers (choose REST or TCP)
- Seller REST: `python run.py seller-rest-server --port 8000`
- Buyer REST:  `python run.py buyer-rest-server  --port 8001`
- Seller TCP:  `python run.py seller-server      --port 8080`
- Buyer TCP:   `python run.py buyer-server       --port 8081`

Point REST servers at DB gRPC: `set DB_SERVICE_ADDR=host:port` (default `localhost:50051`).

## 4) Run CLIs / clients
- Seller REST CLI: `python run.py seller-rest-cli 127.0.0.1 8000`
- Buyer REST CLI:  (not added; use HTTP client like curl or build similarly)
- Seller TCP CLI:  `python run.py seller-cli 127.0.0.1 8080`
- Buyer TCP CLI:   `python run.py buyer-cli 127.0.0.1 8081`

## 5) SSH tunnel examples (reach a remote REST server from local)
- Forward local 8000 to remote seller REST on 127.0.0.1:8000:
  ```
  ssh -L 8000:127.0.0.1:8000 student@10.224.76.51
  ```
  Then call locally: `python run.py seller-rest-cli 127.0.0.1 8000`
- (Adjust host/user/ports as needed; add another `-L 8001:127.0.0.1:8001` for the buyer REST server.)

## 5) Financial service (SOAP mock, stateless)
```
python server_side/financial_service.py
```
No DB storage; returns Yes ~90% of the time. WSDL on port 8002 by default.

## 6) Benchmarks
```
python tools/bench.py
```
Ensure the appropriate servers (TCP path) are running; adjust hosts/ports inside `bench.py` if needed.

## Notes
- Ensure `psql` and `gcloud` are in PATH if running the DB setup scripts.
- For remote DB/servers, set `DB_SERVICE_ADDR`, `PGHOST/PGPORT`, and pass `--host` to `run.py` commands accordingly.
