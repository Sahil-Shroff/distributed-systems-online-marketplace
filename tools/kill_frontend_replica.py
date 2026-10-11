from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_DIR = REPO_ROOT / "runtime" / "frontend" / "status"


def main():
    parser = argparse.ArgumentParser(description="Kill one buyer/seller frontend replica by port.")
    parser.add_argument("--role", choices=["buyer", "seller"], required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    status_file = STATUS_DIR / f"{args.role}-{args.port}.json"
    if not status_file.exists():
        raise SystemExit(f"No status file found for {args.role} frontend on port {args.port}")

    data = json.loads(status_file.read_text(encoding="utf-8"))
    subprocess.run(["taskkill", "/PID", str(data["pid"]), "/T", "/F"], capture_output=True, text=True)
    status_file.unlink(missing_ok=True)
    print(f"Killed {args.role} frontend pid={data['pid']} port={args.port}")


if __name__ == "__main__":
    main()
