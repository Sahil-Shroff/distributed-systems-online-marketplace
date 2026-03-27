# Customer-DB UDP Phase Note

## Implemented Protocol Shape
Customer-db mutations now have an explicit UDP replication layer above `apply_replicated(operation)`.

Faithful PA3 semantics retained:
- client may submit to any replica
- entry replica broadcasts a `Request`
- global sequence `k` is assigned by replica `k mod n`
- delivery is strict global-sequence order
- delivery of `s` requires:
  - all lower sequences delivered
  - majority evidence for all `Request` and `Sequence` messages through `s`
- retransmit requests are used for message loss recovery

## Message Schemas

### RequestId
```python
RequestId(
  sender_id: int,
  local_seq_num: int,
)
```

### RequestMessage
```python
RequestMessage(
  source_replica_id: int,
  request_id: RequestId,
  operation: dict,
  request_frontier: list[int],
  sequence_frontier: int,
)
```

Fields:
- `request_id`: PA3 `<sender_ID, local_seq_num>`
- `operation`: deterministic application payload
- `request_frontier[i]`: highest contiguous local request number from replica `i` known by sender
- `sequence_frontier`: highest contiguous global sequence number known by sender

### SequenceMessage
```python
SequenceMessage(
  source_replica_id: int,
  global_sequence: int,
  request_id: RequestId,
  request_frontier: list[int],
  sequence_frontier: int,
)
```

Fields:
- `global_sequence`: assigned total order
- `request_id`: request chosen for that sequence
- metadata fields carry sender progress for majority checks and hole detection

### RetransmitRequestMessage
```python
RetransmitRequestMessage(
  source_replica_id: int,
  target_replica_id: int,
  missing_kind: Literal["request", "sequence"],
  request_id: RequestId | None,
  global_sequence: int | None,
  request_frontier: list[int],
  sequence_frontier: int,
)
```

Use:
- request retransmission of a missing `Request`
- request retransmission of a missing `Sequence`
- carry progress metadata back to peers/sequencer

## Replica State Variables
Implemented in `server_side/customer_db/replication/node.py`:

- `local_request_seq`
- `next_delivery_sequence`
- `requests: dict[RequestId, RequestMessage]`
- `sequences: dict[int, SequenceMessage]`
- `request_to_sequence`
- `sequence_to_request`
- `delivered_request_ids`
- `delivered_records`
- `received_request_numbers`
- `received_sequence_numbers`
- `request_frontier`
- `sequence_frontier`
- `peer_request_frontier`
- `peer_sequence_frontier`
- delivery waiters for local client submissions

## Event Handlers

### on client mutation
1. build deterministic operation
2. allocate local `RequestId(sender_id, local_seq_num)`
3. store local request
4. broadcast `RequestMessage`
5. try sequencing / delivery
6. wait until local delivery before returning to gRPC caller

### on Request receive
1. store request if new
2. advance per-sender request frontier
3. detect missing lower local requests from same sender
4. send progress metadata back to source
5. try sequencing / delivery

### on Sequence receive
1. store sequence if new
2. advance contiguous sequence frontier
3. if referenced request is missing, request retransmission
4. send progress metadata back to sequencer
5. detect missing lower sequence numbers
6. try sequencing / delivery

### on RetransmitRequest receive
1. update peer progress metadata
2. if targeted locally and missing message is available, resend it

### periodic hole detection / retransmit scan
1. scan for missing sequence holes
2. scan for missing requests referenced by known sequences
3. send retransmit requests as needed
4. retry sequencing / delivery

### delivery check
Deliver sequence `s` only when:
1. `s == next_delivery_sequence`
2. request and sequence for `s` are present locally
3. majority metadata shows replicas have received all `Request` and `Sequence` messages through `s`

On delivery:
- decode request payload into operation
- call `apply_replicated(operation)`
- mark delivered
- wake any local waiter for that request

## Application Payload Format
`RequestMessage.operation` stores a deterministic encoded operation.

Currently supported:
- `CreateBuyer`
- `CreateSeller`
- `CreateSession`
- `TouchSession`
- `DeleteSession`
- `DeleteSessionsForUserRole`
- `UpdateSellerFeedback`
- `CompletePurchase`

Encoding/decoding lives in `server_side/customer_db/replication/messages.py`.

## gRPC Mutation Flow
If customer-db replication env vars are configured, `db_service.py` now uses:

```text
request
-> build operation
-> submit to UDP rotating-sequencer runtime
-> local delivery
-> apply_replicated(operation)
-> return response
```

If replication env vars are absent, the service falls back to direct local `apply_replicated(operation)`.

## Runtime Configuration
Replication runtime is enabled when these env vars are set:
- `CUSTOMER_DB_REPLICA_ID`
- `CUSTOMER_DB_REPLICA_PEERS`

Optional:
- `CUSTOMER_DB_REPLICATION_BIND_HOST`
- `CUSTOMER_DB_REPLICATION_BIND_PORT`
- `CUSTOMER_DB_REPLICATION_SCAN_INTERVAL`
- `CUSTOMER_DB_REPLICATION_DELIVERY_TIMEOUT`

`CUSTOMER_DB_REPLICA_PEERS` format:
```text
0:host0:port0,1:host1:port1,2:host2:port2
```

## Current Validation
Passing tests cover:
- build once / replay across replicas
- rotating sequencer selection by `k mod n`
- retransmit recovery for dropped `Request`
- in-memory customer-db behavior
- Postgres parity scaffolding for later backend validation
