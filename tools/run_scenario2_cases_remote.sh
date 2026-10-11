#!/bin/bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/opt/marketplace/app}"
BUYER_TARGETS="${BUYER_TARGETS:-10.10.0.30:8001,10.10.0.30:8002,10.10.0.30:8003,10.10.0.30:8004}"
SELLER_TARGETS="${SELLER_TARGETS:-10.10.0.40:8101,10.10.0.40:8102,10.10.0.40:8103,10.10.0.40:8104}"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO_ROOT/runtime/scenario2_cases}"
PYTHON_BIN="${PYTHON_BIN:-/opt/marketplace/venv/bin/python}"
BENCHMARK_SCRIPT="$REPO_ROOT/tools/pa3_benchmark.py"
WAIT_AFTER_FAILURE="${WAIT_AFTER_FAILURE:-8}"
RESPONSE_RUNS="${RESPONSE_RUNS:-3}"
THROUGHPUT_RUNS="${THROUGHPUT_RUNS:-2}"
OPS_PER_CLIENT="${OPS_PER_CLIENT:-50}"
READ_WEIGHT="${READ_WEIGHT:-5}"
WRITE_WEIGHT="${WRITE_WEIGHT:-1}"
READ_FN="${READ_FN:-buyer_search_items}"
WRITE_FN="${WRITE_FN:-seller_change_price}"

PRODUCT_HOSTS=(10.10.0.20 10.10.0.21 10.10.0.22 10.10.0.23 10.10.0.24)
CUSTOMER_HOSTS=(10.10.0.10 10.10.0.11 10.10.0.12 10.10.0.13 10.10.0.14)
SELLER_HOST="10.10.0.40"

mkdir -p "$OUTPUT_DIR"

restart_frontends() {
  sudo systemctl start marketplace-buyer-frontend-8001 marketplace-buyer-frontend-8002 marketplace-buyer-frontend-8003 marketplace-buyer-frontend-8004 marketplace-financial-service
  ssh marketplace@"$SELLER_HOST" "sudo systemctl start marketplace-seller-frontend-8101 marketplace-seller-frontend-8102 marketplace-seller-frontend-8103 marketplace-seller-frontend-8104"
}

restart_backends() {
  for host in "${CUSTOMER_HOSTS[@]}"; do
    ssh marketplace@"$host" "sudo systemctl start marketplace-customer-db"
  done
  for host in "${PRODUCT_HOSTS[@]}"; do
    ssh marketplace@"$host" "sudo systemctl start marketplace-product-db"
  done
}

wait_for_cluster() {
  sleep 20
}

run_case() {
  local failure_mode="$1"
  local output_file="$OUTPUT_DIR/scenario2_${failure_mode}.json"

  restart_backends
  restart_frontends
  wait_for_cluster

  local extra_args=()
  case "$failure_mode" in
    no_failures)
      ;;
    frontend_failure)
      extra_args+=(--frontend-failure-hook "$REPO_ROOT/tools/_kill_frontend_replica.sh")
      ;;
    product_follower_failure)
      extra_args+=(--product-follower-failure-hook "$REPO_ROOT/tools/_kill_product_follower.sh")
      ;;
    product_leader_failure)
      extra_args+=(--product-leader-failure-hook "$REPO_ROOT/tools/_kill_product_leader.sh")
      ;;
    *)
      echo "Unknown failure mode: $failure_mode" >&2
      return 1
      ;;
  esac

  "$PYTHON_BIN" "$BENCHMARK_SCRIPT" \
    --buyer-frontends "$BUYER_TARGETS" \
    --seller-frontends "$SELLER_TARGETS" \
    --scenarios 2 \
    --failure-modes "$failure_mode" \
    --response-runs "$RESPONSE_RUNS" \
    --throughput-runs "$THROUGHPUT_RUNS" \
    --ops-per-client "$OPS_PER_CLIENT" \
    --response-functions "$READ_FN" "$WRITE_FN" \
    --throughput-read-weight "$READ_WEIGHT" \
    --throughput-write-weight "$WRITE_WEIGHT" \
    --wait-after-failure "$WAIT_AFTER_FAILURE" \
    --output "$output_file" \
    "${extra_args[@]}"
}

cat >"$REPO_ROOT/tools/_kill_frontend_replica.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
sudo systemctl stop marketplace-buyer-frontend-8001
ssh marketplace@10.10.0.40 "sudo systemctl stop marketplace-seller-frontend-8101"
EOF
chmod +x "$REPO_ROOT/tools/_kill_frontend_replica.sh"

cat >"$REPO_ROOT/tools/_kill_product_follower.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
for host in 10.10.0.20 10.10.0.21 10.10.0.22 10.10.0.23 10.10.0.24; do
  status_json=$(ssh marketplace@"$host" "cat /opt/marketplace/app/runtime/status/product-service-50052.json" 2>/dev/null || true)
  if [[ -z "$status_json" ]]; then
    continue
  fi
  self_addr=$(printf '%s' "$status_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('self',''))")
  leader_addr=$(printf '%s' "$status_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('leader',''))")
  if [[ -n "$self_addr" && "$self_addr" != "$leader_addr" ]]; then
    ssh marketplace@"$host" "sudo systemctl stop marketplace-product-db"
    exit 0
  fi
done
exit 1
EOF
chmod +x "$REPO_ROOT/tools/_kill_product_follower.sh"

cat >"$REPO_ROOT/tools/_kill_product_leader.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
for host in 10.10.0.20 10.10.0.21 10.10.0.22 10.10.0.23 10.10.0.24; do
  status_json=$(ssh marketplace@"$host" "cat /opt/marketplace/app/runtime/status/product-service-50052.json" 2>/dev/null || true)
  if [[ -z "$status_json" ]]; then
    continue
  fi
  self_addr=$(printf '%s' "$status_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('self',''))")
  leader_addr=$(printf '%s' "$status_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('leader',''))")
  if [[ -n "$self_addr" && "$self_addr" == "$leader_addr" ]]; then
    ssh marketplace@"$host" "sudo systemctl stop marketplace-product-db"
    exit 0
  fi
done
exit 1
EOF
chmod +x "$REPO_ROOT/tools/_kill_product_leader.sh"

for mode in no_failures frontend_failure product_follower_failure product_leader_failure; do
  echo "Running scenario 2 case: $mode"
  run_case "$mode"
done

echo "Scenario 2 case outputs written to $OUTPUT_DIR"
