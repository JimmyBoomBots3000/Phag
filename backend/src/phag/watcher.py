"""Simple polling watcher for indexed roots."""

from __future__ import annotations

import time
from pathlib import Path

from phag.indexer import index_roots


def watch_roots(db_path: Path, interval_seconds: int = 30) -> None:
    """Continuously rescan enabled roots at a fixed interval."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")

    while True:
        index_roots(db_path)
        time.sleep(interval_seconds)
