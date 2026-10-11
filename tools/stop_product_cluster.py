from __future__ import annotations

import json
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    status_dir = root / "runtime" / "status"
    pid_dir = root / "runtime" / "pids"
    stopped = 0
    for status_file in sorted(status_dir.glob("product-service-*.json")):
        try:
            data = json.loads(status_file.read_text(encoding="utf-8"))
            pid = int(data["pid"])
            pid_file = pid_dir / status_file.name.replace(".json", ".pid")
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=True, capture_output=True, text=True)
            finally:
                if pid_file.exists():
                    pid_file.unlink()
                status_file.unlink(missing_ok=True)
            print(f"Stopped pid={pid} from {status_file.name}")
            stopped += 1
        except Exception as exc:
            print(f"Skipping {status_file.name}: {exc}")
    if stopped == 0:
        print("No running product replicas found.")


if __name__ == "__main__":
    main()
