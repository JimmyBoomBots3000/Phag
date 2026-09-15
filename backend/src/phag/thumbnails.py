"""Thumbnail generation and persistence helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from phag.scanner import ScannedImage

THUMBNAIL_SIZES = {
    "small": 256,
    "medium": 1024,
}


@dataclass(frozen=True)
class GeneratedThumbnail:
    """Metadata for one generated thumbnail file."""

    size_name: str
    path: Path
    width: int
    height: int
    format: str


def thumbnail_relative_path(content_hash: str, size_name: str) -> Path:
    """Return the app-data-relative thumbnail path for a content hash."""
    return Path("thumbnails") / size_name / content_hash[:2] / f"{content_hash}.webp"


def generate_thumbnail(
    source_path: Path,
    output_path: Path,
    max_size: int,
) -> tuple[int, int]:
    """Generate one WebP thumbnail and return its dimensions."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((max_size, max_size))
        image.save(output_path, format="WEBP", quality=85)
        return image.size


def generate_thumbnails(
    app_data_dir: Path,
    scanned_image: ScannedImage,
) -> list[GeneratedThumbnail]:
    """Generate all configured thumbnails for a scanned image."""
    app_data_dir = app_data_dir.expanduser().resolve()
    thumbnails: list[GeneratedThumbnail] = []

    for size_name, max_size in THUMBNAIL_SIZES.items():
        relative_path = thumbnail_relative_path(scanned_image.content_hash, size_name)
        output_path = app_data_dir / relative_path
        width, height = generate_thumbnail(scanned_image.path, output_path, max_size)
        thumbnails.append(
            GeneratedThumbnail(
                size_name=size_name,
                path=relative_path,
                width=width,
                height=height,
                format="webp",
            )
        )

    return thumbnails


def upsert_thumbnail(
    connection: sqlite3.Connection,
    image_id: int,
    thumbnail: GeneratedThumbnail,
) -> int:
    """Insert or update one thumbnail record for an image."""
    cursor = connection.execute(
        """
        INSERT INTO thumbnails (
            image_id,
            size_name,
            path,
            width,
            height,
            format,
            generated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(image_id, size_name) DO UPDATE SET
            path = excluded.path,
            width = excluded.width,
            height = excluded.height,
            format = excluded.format,
            generated_at = CURRENT_TIMESTAMP
        RETURNING id
        """,
        (
            image_id,
            thumbnail.size_name,
            str(thumbnail.path),
            thumbnail.width,
            thumbnail.height,
            thumbnail.format,
        ),
    )

    return cursor.fetchone()["id"]
