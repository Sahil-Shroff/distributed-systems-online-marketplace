# PA3 Online Marketplace

## Overview
This repository contains the PA3 version of the distributed online marketplace. The PA3 system extends the PA2 architecture by adding replication and fault tolerance to the main server-side components. The customer database is replicated over five replicas using a rotating sequencer atomic broadcast protocol over UDP. The product database is replicated over five replicas using Raft. The buyer frontend and seller frontend are each replicated over four stateless replicas, and the client code is configured with replica lists so it can reconnect to another frontend when a replica fails. The communication stack remains the same as PA2: clients talk to frontends over REST, frontends talk to backend services over gRPC, and payment-related paths use a SOAP/WSDL financial service.

## System Design
- `client_side/`
  - Buyer and seller REST clients with replica-list failover support.
- `server_side/buyer_interface/`
  - Stateless buyer frontend replicas.
- `server_side/seller_interface/`
  - Stateless seller frontend replicas.
- `server_side/customer_db/`
  - Customer DB logic, deterministic operations, SQLite persistence, and rotating-sequencer replication runtime.
- `server_side/product_replication/`
  - Product DB replicated-state-machine logic backed by Raft.
- `server_side/db_service.py`
  - gRPC service for customer DB operations.
- `server_side/product_service.py`
  - gRPC service for replicated product DB operations.
- `server_side/financial_service.py`
  - SOAP/WSDL financial service used by purchase paths.
- `infra/terraform/`
  - Terraform deployment for Google Cloud.
- `tools/`
  - Cluster launchers, failure scripts, smoke tests, and benchmark drivers.

## Replication Design

### Customer Database
The customer database is replicated over five replicas using a rotating sequencer atomic broadcast protocol. A client mutation can enter any customer-db replica. That replica packages the mutation as a deterministic operation and broadcasts a `RequestMessage` over UDP. Global sequence number `k` is assigned by replica `k mod n`, so sequencer responsibility rotates across replicas rather than being fixed on one node. Replicas only deliver an operation when they have the request, the assigned sequence, and majority evidence that peers have received all earlier requests and sequences. Missing requests or sequence assignments are recovered using retransmission messages and a periodic hole-detection scan.

### Product Database
The product database is replicated over five replicas using Raft. Writes are routed through the current Raft leader. Product mutations are applied through the replicated-state-machine layer, and followers mirror the committed state. The implementation handles both follower failure and leader failure, including leader re-election.

### Frontend Replication
The buyer frontend and seller frontend are stateless and each run with four replicas. No replication protocol is needed for frontend state because the frontends are stateless. Instead, the client maintains a list of frontend replicas and reconnects to another replica on failure. If a frontend replica crashes, it is restarted with the same IP/host.

## Communication Stack
- Client ↔ Frontend: REST / FastAPI
- Frontend ↔ Backend: gRPC / Protocol Buffers
- Frontend ↔ Financial Service: SOAP/WSDL

These communication mechanisms are unchanged from PA2, as required by the PA3 handout.

## Deployment Setup
The cloud deployment is provisioned with Terraform under `infra/terraform/`. In the quota-constrained deployment used for this project, the system is spread across 12 Google Cloud VMs:

- 5 VMs for customer DB replicas
- 5 VMs for product DB replicas
- 1 VM hosting 4 buyer frontend replicas and the SOAP financial service
- 1 VM hosting 4 seller frontend replicas

Each replica still runs as a separate process and communicates over the network stack, even when multiple replicas share the same VM. This satisfies the PA3 requirement that deployment use at least four VMs and that replicas be networked processes.

## How To Run Locally

### Customer DB Replica Cluster
Start a local 5-replica customer-db cluster:

```powershell
python run.py customer-db-replica-cluster --replicas 5 --grpc-base-port 55061 --udp-base-port 56061
```

Smoke-test customer-db replication:

```powershell
python tools/customer_db_replication_smoke.py --use-existing --replicas 5 --grpc-base-port 55061 --udp-base-port 56061
```

### Product DB Raft Cluster
Start the local product cluster:

```powershell
python tools/start_product_cluster.py
```

Run the product replication/failover test:

```powershell
python tools/test_product_service_cluster.py
```

Stop the local product cluster:

```powershell
python tools/stop_product_cluster.py
```

### Frontend Replicas
Start local buyer/seller frontend replicas:

```powershell
python tools/start_frontend_cluster.py
```

Stop them:

```powershell
python tools/stop_frontend_cluster.py
```

## How To Deploy on GCP
Terraform files live in `infra/terraform/`.

Typical workflow:

```powershell
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform plan -var="project_id=<gcp-project-id>"
terraform -chdir=infra/terraform apply -var="project_id=<gcp-project-id>"
```

Useful commands after deployment:

```powershell
gcloud compute instances list --project=<gcp-project-id>
terraform -chdir=infra/terraform output
```

## Failure / Recovery Scripts
- `tools/kill_product_follower.py`
  - kills one non-leader product replica
- `tools/kill_product_leader.py`
  - kills the current product leader
- `tools/kill_frontend_replica.py`
  - kills one buyer or seller frontend replica

These scripts are used to exercise the PA3 failure scenarios described in the handout.

## Benchmarking
The benchmark runner is `tools/pa3_benchmark.py`. It supports:
- Scenario 1: 1 buyer, 1 seller
- Scenario 2: 10 buyers, 10 sellers
- Scenario 3: 100 buyers, 100 sellers
- No-failure baseline
- Frontend replica failure
- Product follower failure
- Product leader failure

Example invocation:

```powershell
python tools/pa3_benchmark.py --buyer-frontends "<buyer-targets>" --seller-frontends "<seller-targets>"
```

Scenario-specific remote runner scripts under `tools/` can also be used to launch benchmark cases on the deployed buyer host so they continue running independently of the local machine.

## Assumptions
- Crash failures are the primary failure model for replicas.
- Frontend replicas are stateless and can be restarted without state recovery logic.
- Customer DB operations are deterministic and safe to replay in the same total order.
- Product DB replication relies on quorum and leader election behavior provided by the chosen Raft library.
- If multiple replicas share a VM due to quota limits, they still run as distinct processes and communicate over the network stack.
- Client failover assumes at least one healthy frontend replica remains reachable.

## Current State

### Working
- Customer DB replication over five replicas using rotating sequencer atomic broadcast.
- Product DB replication over five replicas using Raft.
- Buyer and seller frontend replication with client-side failover.
- SQLite-backed replica storage for local inspection and testing.
- Local and cloud deployment tooling.
- Failure scripts for frontend failure, product follower failure, and product leader failure.

### Known Issues / Limitations
- Some full-benchmark runs still show buyer cart-related API errors in certain failure scenarios.
- Some benchmark scenarios have been run in reduced configurations for faster iteration during development.
- Cloud deployment layout may be adjusted to fit GCP quota constraints; in that case multiple stateless replicas may share the same VM.

## Submission Notes
This repository contains:
- source code
- deployment files
- benchmark tooling
- README content aligned with PA3 handout expectations

The performance report is maintained separately as the submission report document.
