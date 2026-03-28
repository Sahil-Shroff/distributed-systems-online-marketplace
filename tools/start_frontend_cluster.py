from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime" / "frontend"
STATUS_DIR = RUNTIME_DIR / "status"


def main():
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    for stale_file in STATUS_DIR.glob("*.json"):
        stale_file.unlink(missing_ok=True)

    python_exe = sys.executable
    customer_targets = ",".join(f"127.0.0.1:{port}" for port in [55061, 55062, 55063, 55064, 55065])
    product_targets = ",".join(f"127.0.0.1:{port}" for port in [50052, 50053, 50054, 50055, 50056])

    processes = []
    for port in [8001, 8002, 8003, 8004]:
        env = os.environ.copy()
        env["CUSTOMER_SERVICE_ADDR"] = customer_targets
        env["PRODUCT_SERVICE_ADDR"] = product_targets
        proc = subprocess.Popen([python_exe, "run.py", "buyer-rest-server", "--host", "127.0.0.1", "--port", str(port)], cwd=str(REPO_ROOT), env=env)
        processes.append(("buyer", port, proc.pid))
    for port in [8101, 8102, 8103, 8104]:
        env = os.environ.copy()
        env["CUSTOMER_SERVICE_ADDR"] = customer_targets
        env["PRODUCT_SERVICE_ADDR"] = product_targets
        proc = subprocess.Popen([python_exe, "run.py", "seller-rest-server", "--host", "127.0.0.1", "--port", str(port)], cwd=str(REPO_ROOT), env=env)
        processes.append(("seller", port, proc.pid))

    time.sleep(4)
    for role, port, pid in processes:
        status_file = STATUS_DIR / f"{role}-{port}.json"
        status_file.write_text(json.dumps({"role": role, "port": port, "pid": pid}, indent=2), encoding="utf-8")
        print(f"Started {role} frontend port={port} pid={pid}")

    print("\nBuyer replicas:  127.0.0.1:8001,127.0.0.1:8002,127.0.0.1:8003,127.0.0.1:8004")
    print("Seller replicas: 127.0.0.1:8101,127.0.0.1:8102,127.0.0.1:8103,127.0.0.1:8104")
    print("Stop all: python tools/stop_frontend_cluster.py")


if __name__ == "__main__":
    main()
