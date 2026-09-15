"""Persistence helpers for logical images identified by content hash."""

from __future__ import annotations

import sqlite3

from phag.scanner import ScannedImage


def upsert_image(conn: sqlite3.Connection, scanned_image: ScannedImage) -> int:
    """Insert or update a logical image and return its database id."""
    cursor = conn.execute(
        """
        INSERT INTO images (content_hash,
                            hash_algorithm,
                            width,
                            height,
                            mime_type,
                            file_size_bytes,
                            date_taken,
                            exif_json,
                            last_seen_at)
        VALUES (?, 'sha256', ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(hash_algorithm, content_hash) DO UPDATE SET last_seen_at    = CURRENT_TIMESTAMP,
                                                                width          = excluded.width,
                                                                height         = excluded.height,
                                                                mime_type      = excluded.mime_type,
                                                                file_size_bytes = excluded.file_size_bytes,
                                                                date_taken     = excluded.date_taken,
                                                                exif_json      = excluded.exif_json
        RETURNING id
        """,
        (
            scanned_image.content_hash,
            scanned_image.width,
            scanned_image.height,
            image_mime_type(scanned_image),
            scanned_image.file_size_bytes,
            scanned_image.date_taken,
            scanned_image.exif_json,
        ),
    )

    return cursor.fetchone()["id"]


def image_mime_type(scanned_image: ScannedImage) -> str:
    """Infer an image MIME type from the file extension."""
    match scanned_image.path.suffix.lower():
        case ".jpg" | ".jpeg":
            return "image/jpeg"
        case ".png":
            return "image/png"
        case ".webp":
            return "image/webp"
        case _:
            raise ValueError(f"Unsupported image extension: {scanned_image.path}")


def delete_unlocated_images(conn: sqlite3.Connection) -> int:
    """Delete logical images that no longer have any file locations."""
    cursor = conn.execute(
        """
        DELETE FROM images
        WHERE NOT EXISTS (
            SELECT 1
            FROM file_locations
            WHERE file_locations.image_id = images.id
        )
        """
    )

    return cursor.rowcount


def get_active_image_path(conn: sqlite3.Connection, image_id: int) -> str | None:
    """Return one active source path for an image."""
    row = conn.execute(
        """
        SELECT path
        FROM file_locations
        WHERE image_id = ?
          AND orphaned_at IS NULL
        ORDER BY path
        LIMIT 1
        """,
        (image_id,),
    ).fetchone()

    return row["path"] if row is not None else None
