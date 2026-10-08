"""Filesystem and metadata updates for moving indexed image files."""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from phag.file_locations import path_relative_to_root
from phag.indexed_roots import find_indexed_root_covering_file
from phag.scanner import timestamp_to_utc_iso


@dataclass(frozen=True)
class MovedImage:
    """Result of moving one indexed image file."""

    image_id: int
    source_path: Path
    destination_path: Path
    root_id: int | None
    path_relative: str | None
    indexed: bool


def move_image_file(
    connection: sqlite3.Connection,
    image_id: int,
    destination_directory: Path,
    allow_unindexed: bool = False,
) -> MovedImage:
    """Move one active image file and update its active file location."""
    destination_directory = destination_directory.expanduser().resolve()
    if not destination_directory.is_dir():
        raise NotADirectoryError(f"Destination is not a directory: {destination_directory}")

    row = connection.execute(
        """
        SELECT id, path
        FROM file_locations
        WHERE image_id = ?
          AND orphaned_at IS NULL
        ORDER BY path
        LIMIT 1
        """,
        (image_id,),
    ).fetchone()
    if row is None:
        raise FileNotFoundError(f"Image {image_id} has no active file location")

    location_id = row["id"]
    source_path = Path(row["path"]).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Image file not found: {source_path}")

    destination_path = destination_directory / source_path.name
    if destination_path == source_path:
        root = find_indexed_root_covering_file(connection, destination_path)
        if root is None:
            if not allow_unindexed:
                raise ValueError("destination_not_indexed")
            return MovedImage(
                image_id=image_id,
                source_path=source_path,
                destination_path=destination_path,
                root_id=None,
                path_relative=None,
                indexed=False,
            )
        return MovedImage(
            image_id=image_id,
            source_path=source_path,
            destination_path=destination_path,
            root_id=root.id,
            path_relative=path_relative_to_root(root.path, destination_path),
            indexed=True,
        )
    if destination_path.exists():
        raise FileExistsError(f"Destination already exists: {destination_path}")

    root = find_indexed_root_covering_file(connection, destination_path)
    if root is None and not allow_unindexed:
        raise ValueError("destination_not_indexed")

    path_relative = path_relative_to_root(root.path, destination_path) if root is not None else None
    if root is not None and path_relative is not None:
        existing_location = connection.execute(
            """
            SELECT id
            FROM file_locations
            WHERE root_id = ?
              AND path_relative = ?
            """,
            (root.id, path_relative),
        ).fetchone()
        if existing_location is not None and existing_location["id"] != location_id:
            raise FileExistsError(f"Destination is already indexed: {destination_path}")

    moved = False
    try:
        shutil.move(str(source_path), str(destination_path))
        moved = True
        if root is None or path_relative is None:
            connection.execute(
                """
                UPDATE file_locations
                SET path = ?,
                    last_seen_at = CURRENT_TIMESTAMP,
                    orphaned_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (str(destination_path), location_id),
            )
        else:
            stat = destination_path.stat()
            connection.execute(
                """
                UPDATE file_locations
                SET root_id = ?,
                    path = ?,
                    path_relative = ?,
                    file_size_bytes = ?,
                    modified_time = ?,
                    last_seen_at = CURRENT_TIMESTAMP,
                    orphaned_at = NULL
                WHERE id = ?
                """,
                (
                    root.id,
                    str(destination_path),
                    path_relative,
                    stat.st_size,
                    timestamp_to_utc_iso(stat.st_mtime),
                    location_id,
                ),
            )
    except Exception:
        if moved and destination_path.exists() and not source_path.exists():
            shutil.move(str(destination_path), str(source_path))
        raise

    return MovedImage(
        image_id=image_id,
        source_path=source_path,
        destination_path=destination_path,
        root_id=root.id if root is not None else None,
        path_relative=path_relative,
        indexed=root is not None,
    )
