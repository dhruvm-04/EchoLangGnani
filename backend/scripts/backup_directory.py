"""Create a consistent backup of the local directory while the API is running."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from app.directory import DirectoryStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", nargs="?", type=Path, help="Backup file path")
    args = parser.parse_args()
    store = DirectoryStore()
    default = store.path.parent / "backups" / f"echolang-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.sqlite3"
    target = store.backup(args.destination or default)
    print(f"Directory backed up to {target}")


if __name__ == "__main__":
    main()
