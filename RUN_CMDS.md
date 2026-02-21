# Run Commands Cheat Sheet

## 1) Create / reset databases
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
Env (optional): `DB_SERVICE_PORT` (default 50051), `PGHOST/PGPORT/PGUSER/PGPASSWORD`, `CUSTOMER_DB_NAME`, `PRODUCT_DB_NAME`, `FIN_DB_NAME`.

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

## 5) Financial service (SOAP mock)
```
python server_side/financial_service.py
```
Env (optional): `FIN_DB_*` for its DB; WSDL served on port 8002 by default.

## 6) Benchmarks
```
python tools/bench.py
```
Ensure the appropriate servers (TCP path) are running; adjust hosts/ports inside `bench.py` if needed.

## Notes
- Ensure `psql` and `gcloud` are in PATH if running the DB setup scripts.
- For remote DB/servers, set `DB_SERVICE_ADDR`, `PGHOST/PGPORT`, and pass `--host` to `run.py` commands accordingly.
