from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime"
PIDS_DIR = RUNTIME_DIR / "pids"
STATUS_DIR = RUNTIME_DIR / "status"
SQLITE_DIR = RUNTIME_DIR / "sqlite"


def kill_processes_on_port(port: int):
    result = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True,
        text=True,
        check=True,
    )
    seen_pids = set()
    for line in result.stdout.splitlines():
        if f":{port}" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_addr = parts[1]
        state = parts[3] if len(parts) > 4 else ""
        pid = parts[-1]
        if not local_addr.endswith(f":{port}"):
            continue
        if state.upper() not in {"LISTENING", "ESTABLISHED"}:
            continue
        if pid in seen_pids:
            continue
        seen_pids.add(pid)
        subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True, text=True)


def main():
    PIDS_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    SQLITE_DIR.mkdir(parents=True, exist_ok=True)
    for stale_file in STATUS_DIR.glob("product-service-*.json"):
        stale_file.unlink(missing_ok=True)
    for stale_file in PIDS_DIR.glob("product-service-*.pid"):
        stale_file.unlink(missing_ok=True)

    python_exe = sys.executable
    grpc_ports = [50052, 50053, 50054, 50055, 50056]
    raft_ports = [6001, 6002, 6003, 6004, 6005]
    for port in grpc_ports + raft_ports:
        kill_processes_on_port(port)
    raft_addrs = [f"127.0.0.1:{port}" for port in raft_ports]

    procs = []
    for grpc_port, raft_addr in zip(grpc_ports, raft_addrs):
        partners = ",".join(addr for addr in raft_addrs if addr != raft_addr)
        env = os.environ.copy()
        env["PRODUCT_SERVICE_PORT"] = str(grpc_port)
        env["PRODUCT_SERVICE_BIND"] = f"127.0.0.1:{grpc_port}"
        env["PRODUCT_RAFT_SELF"] = raft_addr
        env["PRODUCT_RAFT_PARTNERS"] = partners
        env.setdefault("PRODUCT_SERVICE_DISABLE_CUSTOMER_DB", "1")
        env.setdefault("PRODUCT_SERVICE_DISABLE_PRODUCT_DB", "0")
        env.setdefault("PRODUCT_DB_BACKEND", "sqlite")
        env["PRODUCT_SQLITE_PATH"] = str(SQLITE_DIR / f"product-service-{grpc_port}.db")
        proc = subprocess.Popen(
            [python_exe, "run.py", "product-service", "--host", "127.0.0.1", "--port", str(grpc_port)],
            cwd=str(REPO_ROOT),
            env=env,
        )
        procs.append((grpc_port, proc.pid))
        print(f"Started product replica grpc={grpc_port} pid={proc.pid}")

    print("\nWaiting 5 seconds for cluster startup...")
    time.sleep(5)
    print("Status files:")
    for status_file in sorted(STATUS_DIR.glob("product-service-*.json")):
        print(f"  {status_file}")

    print("\nProduct cluster startup complete.")
    print("Kill follower: python tools/kill_product_follower.py")
    print("Kill leader:   python tools/kill_product_leader.py")
    print("Stop all:      python tools/stop_product_cluster.py")


if __name__ == "__main__":
    main()
