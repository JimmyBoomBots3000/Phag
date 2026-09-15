"""Persistence helpers for indexing activity events."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def add_scan_event(
    connection: sqlite3.Connection,
    event_type: str,
    root_id: int | None = None,
    path: Path | None = None,
    image_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> int:
    """Record one scanner/indexer activity event."""
    cursor = connection.execute(
        """
        INSERT INTO scan_events (
            root_id,
            event_type,
            path,
            image_id,
            details_json
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            root_id,
            event_type,
            str(path) if path is not None else None,
            image_id,
            json.dumps(details) if details is not None else None,
        ),
    )

    return cursor.lastrowid
