"""Tag creation, lookup, and image association helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Tag:
    """A user-created tag."""

    id: int
    display_name: str
    normalized_name: str


def normalize_tag_name(name: str) -> str:
    """Return the case-insensitive storage key for a tag name."""
    normalized = "/".join(part.strip() for part in name.strip().split("/"))
    normalized = normalized.casefold()
    if not normalized:
        raise ValueError("Tag name must not be empty")
    return normalized


def create_tag(connection: sqlite3.Connection, display_name: str) -> int:
    """Create a tag if needed and return its database id."""
    normalized_name = normalize_tag_name(display_name)
    display_name = display_name.strip()

    cursor = connection.execute(
        """
        INSERT INTO tags (display_name, normalized_name)
        VALUES (?, ?)
        ON CONFLICT(normalized_name) DO UPDATE SET
            normalized_name = excluded.normalized_name
        RETURNING id
        """,
        (display_name, normalized_name),
    )

    return cursor.fetchone()["id"]


def list_tags(connection: sqlite3.Connection) -> list[Tag]:
    """Return tags attached to at least one active image."""
    rows = connection.execute(
        """
        SELECT DISTINCT tags.id, tags.display_name, tags.normalized_name
        FROM tags
        JOIN image_tags ON image_tags.tag_id = tags.id
        JOIN file_locations ON file_locations.image_id = image_tags.image_id
        WHERE file_locations.orphaned_at IS NULL
        ORDER BY display_name
        """
    ).fetchall()

    return [
        Tag(
            id=row["id"],
            display_name=row["display_name"],
            normalized_name=row["normalized_name"],
        )
        for row in rows
    ]


def delete_tag(connection: sqlite3.Connection, tag_id: int) -> int:
    """Delete a tag and its image associations."""
    cursor = connection.execute(
        """
        DELETE FROM tags
        WHERE id = ?
        """,
        (tag_id,),
    )

    return cursor.rowcount


def delete_unused_tags(connection: sqlite3.Connection) -> int:
    """Delete tags no longer attached to active images."""
    cursor = connection.execute(
        """
        DELETE FROM tags
        WHERE NOT EXISTS (
            SELECT 1
            FROM image_tags
            JOIN file_locations ON file_locations.image_id = image_tags.image_id
            WHERE image_tags.tag_id = tags.id
              AND file_locations.orphaned_at IS NULL
        )
        """
    )

    return cursor.rowcount


def rename_tag(connection: sqlite3.Connection, tag_id: int, display_name: str) -> int:
    """Rename a tag while preserving its image associations."""
    normalized_name = normalize_tag_name(display_name)
    cursor = connection.execute(
        """
        UPDATE tags
        SET display_name = ?,
            normalized_name = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (display_name.strip(), normalized_name, tag_id),
    )

    return cursor.rowcount


def add_tag_to_image(connection: sqlite3.Connection, image_id: int, tag_id: int) -> None:
    """Associate a tag with an image."""
    connection.execute(
        """
        INSERT OR IGNORE INTO image_tags (image_id, tag_id)
        VALUES (?, ?)
        """,
        (image_id, tag_id),
    )


def remove_tag_from_image(connection: sqlite3.Connection, image_id: int, tag_id: int) -> int:
    """Remove a tag association from an image."""
    cursor = connection.execute(
        """
        DELETE FROM image_tags
        WHERE image_id = ?
          AND tag_id = ?
        """,
        (image_id, tag_id),
    )

    return cursor.rowcount


def list_image_tags(connection: sqlite3.Connection, image_id: int) -> list[Tag]:
    """Return tags associated with one image."""
    rows = connection.execute(
        """
        SELECT tags.id, tags.display_name, tags.normalized_name
        FROM tags
        JOIN image_tags ON image_tags.tag_id = tags.id
        WHERE image_tags.image_id = ?
        ORDER BY tags.display_name
        """,
        (image_id,),
    ).fetchall()

    return [
        Tag(
            id=row["id"],
            display_name=row["display_name"],
            normalized_name=row["normalized_name"],
        )
        for row in rows
    ]
