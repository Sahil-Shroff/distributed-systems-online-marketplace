from __future__ import annotations

import json
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    status_dir = root / "runtime" / "status"
    pid_dir = root / "runtime" / "pids"
    found = False
    for status_file in sorted(status_dir.glob("product-service-*.json")):
        data = json.loads(status_file.read_text(encoding="utf-8"))
        if data.get("leader") and data.get("self") != data.get("leader"):
            pid = int(data["pid"])
            pid_file = pid_dir / status_file.name.replace(".json", ".pid")
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=True, capture_output=True, text=True)
            finally:
                if pid_file.exists():
                    pid_file.unlink()
                status_file.unlink(missing_ok=True)
            print(f"Killed follower replica pid={pid} from {status_file.name}")
            found = True
            break
    if not found:
        raise SystemExit("No follower replica status file found")


if __name__ == "__main__":
    main()
