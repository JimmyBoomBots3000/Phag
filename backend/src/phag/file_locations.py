"""Persistence helpers for image file paths under indexed roots."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from phag.scanner import ScannedImage


def path_relative_to_root(root_path: Path, image_path: Path) -> str:
    """Return an image path as a string relative to an indexed root."""
    root_path = root_path.expanduser().resolve()
    image_path = image_path.expanduser().resolve()
    return str(image_path.relative_to(root_path))


def is_unchanged_file_location(
    connection: sqlite3.Connection,
    root_id: int,
    root_path: Path,
    image_path: Path,
    file_size_bytes: int,
    modified_time: str,
) -> bool:
    """Return true when a file path's cached scan metadata still matches."""
    path_relative = path_relative_to_root(root_path, image_path)

    row = connection.execute(
        """
        SELECT 1
        FROM file_locations
        WHERE root_id = ?
          AND path_relative = ?
          AND file_size_bytes = ?
          AND modified_time = ?
          AND orphaned_at IS NULL
        """,
        (
            root_id,
            path_relative,
            file_size_bytes,
            modified_time,
        ),
    ).fetchone()

    return row is not None


def upsert_file_location(
    connection: sqlite3.Connection,
    root_id: int,
    root_path: Path,
    image_id: int,
    scanned_image: ScannedImage,
) -> int:
    """Insert or update a file location for a logical image."""
    root_path = root_path.expanduser().resolve()
    image_path = scanned_image.path.expanduser().resolve()
    path_relative = path_relative_to_root(root_path, image_path)

    cursor = connection.execute(
        """
        INSERT INTO file_locations (
            image_id,
            root_id,
            path,
            path_relative,
            file_size_bytes,
            modified_time,
            last_seen_at,
            orphaned_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, NULL)
        ON CONFLICT(root_id, path_relative) DO UPDATE SET
            image_id = excluded.image_id,
            path = excluded.path,
            file_size_bytes = excluded.file_size_bytes,
            modified_time = excluded.modified_time,
            last_seen_at = CURRENT_TIMESTAMP,
            orphaned_at = NULL
        RETURNING id
        """,
        (
            image_id,
            root_id,
            str(image_path),
            path_relative,
            scanned_image.file_size_bytes,
            scanned_image.modified_time,
        ),
    )

    return cursor.fetchone()["id"]


def mark_missing_file_locations_orphaned(
    connection: sqlite3.Connection,
    root_id: int,
    seen_path_relatives: set[str],
) -> int:
    """Mark active file locations not seen in the latest scan as orphaned."""
    if not seen_path_relatives:
        cursor = connection.execute(
            """
            UPDATE file_locations
            SET orphaned_at = CURRENT_TIMESTAMP
            WHERE root_id = ?
              AND orphaned_at IS NULL
            """,
            (root_id,),
        )
        return cursor.rowcount

    placeholders = ", ".join("?" for _ in seen_path_relatives)
    cursor = connection.execute(
        f"""
        UPDATE file_locations
        SET orphaned_at = CURRENT_TIMESTAMP
        WHERE root_id = ?
          AND orphaned_at IS NULL
          AND path_relative NOT IN ({placeholders})
        """,
        (root_id, *seen_path_relatives),
    )

    return cursor.rowcount


def mark_root_file_locations_orphaned(connection: sqlite3.Connection, root_id: int) -> int:
    """Mark all active file locations for a root as orphaned."""
    cursor = connection.execute(
        """
        UPDATE file_locations
        SET orphaned_at = CURRENT_TIMESTAMP
        WHERE root_id = ?
          AND orphaned_at IS NULL
        """,
        (root_id,),
    )

    return cursor.rowcount


def purge_orphaned_file_locations(
    connection: sqlite3.Connection,
    retention_days: int = 3,
) -> int:
    """Delete file locations orphaned for at least the retention period."""
    if retention_days < 0:
        raise ValueError("retention_days must be non-negative")

    cursor = connection.execute(
        """
        DELETE FROM file_locations
        WHERE orphaned_at IS NOT NULL
          AND orphaned_at <= datetime('now', ?)
        """,
        (f"-{retention_days} days",),
    )

    return cursor.rowcount
