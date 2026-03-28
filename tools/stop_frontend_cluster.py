from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_DIR = REPO_ROOT / "runtime" / "frontend" / "status"


def main():
    stopped = 0
    for status_file in sorted(STATUS_DIR.glob("*.json")):
        data = json.loads(status_file.read_text(encoding="utf-8"))
        pid = str(data["pid"])
        try:
            subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True, text=True)
        finally:
            status_file.unlink(missing_ok=True)
        print(f"Stopped {data['role']} frontend pid={pid} port={data['port']}")
        stopped += 1
    if stopped == 0:
        print("No running frontend replicas found.")


if __name__ == "__main__":
    main()
