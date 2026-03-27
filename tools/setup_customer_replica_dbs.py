from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server_side.customer_db.backends.sqlite import CUSTOMER_SQLITE_SCHEMA  # noqa: E402
from server_side.data_access_layer.db import Database_Connection  # noqa: E402
from server_side.sqlite_schemas import CUSTOMER_SQLITE_DEFAULT_DB  # noqa: E402

def create_replica_databases(prefix: str, count: int, reset: bool) -> list[str]:
    created_paths: list[str] = []
    base_root = REPO_ROOT / "database"
    base_root.mkdir(parents=True, exist_ok=True)
    for idx in range(count):
        replica_dir = base_root / f"{prefix}{idx}"
        if reset and replica_dir.exists():
            shutil.rmtree(replica_dir)
        replica_dir.mkdir(parents=True, exist_ok=True)
        db_path = replica_dir / CUSTOMER_SQLITE_DEFAULT_DB
        db = Database_Connection(db_path=str(db_path), init_schema=CUSTOMER_SQLITE_SCHEMA)
        db.close()
        created_paths.append(str(db_path))
    return created_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Create local customer-db replica SQLite databases.")
    parser.add_argument("--prefix", default="customer-db-replica_")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--reset", action="store_true", help="Drop and recreate the replica databases before applying schema")
    args = parser.parse_args()

    created = create_replica_databases(prefix=args.prefix, count=args.count, reset=args.reset)
    print({"databases": created})


if __name__ == "__main__":
    main()
