"""Filesystem scanning, metadata discovery, and content hashing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ExifTags

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class DiscoveredImage:
    """Cheap filesystem metadata for a candidate image file."""

    path: Path
    file_size_bytes: int
    modified_time: str


@dataclass(frozen=True)
class ScannedImage:
    """Image metadata plus a content hash for persistence."""

    path: Path
    file_size_bytes: int
    modified_time: str
    content_hash: str
    width: int
    height: int
    date_taken: str | None
    exif_json: str | None


def timestamp_to_utc_iso(timestamp: float) -> str:
    """Convert a filesystem timestamp to a UTC ISO-8601 string."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def iter_image_files(root_path: Path) -> Iterator[Path]:
    """Yield supported image files under a root folder recursively."""
    root_path = root_path.expanduser().resolve()

    for path in root_path.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            yield path


def discover_images(root_path: Path) -> Iterator[DiscoveredImage]:
    """Yield supported image files with cheap filesystem metadata."""
    for path in iter_image_files(root_path):
        stat = path.stat()
        yield DiscoveredImage(
            path=path,
            file_size_bytes=stat.st_size,
            modified_time=timestamp_to_utc_iso(stat.st_mtime),
        )


def hash_file(path: Path) -> str:
    """Return the SHA-256 content hash for a file."""
    hasher = hashlib.sha256()

    with path.open(mode="rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)

    return hasher.hexdigest()


def read_image_metadata(path: Path) -> tuple[int, int, str | None, str | None]:
    """Read dimensions and basic EXIF metadata from an image file."""
    with Image.open(path) as image:
        width, height = image.size
        exif = image.getexif()

    if not exif:
        return width, height, None, None

    exif_by_name = {
        ExifTags.TAGS.get(tag_id, str(tag_id)): value
        for tag_id, value in exif.items()
        if isinstance(value, str | int | float)
    }
    date_taken = exif_by_name.get("DateTimeOriginal") or exif_by_name.get("DateTime")

    return width, height, date_taken, json.dumps(exif_by_name, sort_keys=True)


def scan_discovered_image(image: DiscoveredImage) -> ScannedImage:
    """Add hash and image metadata to a discovered image."""
    width, height, date_taken, exif_json = read_image_metadata(image.path)
    return ScannedImage(
        path=image.path,
        file_size_bytes=image.file_size_bytes,
        modified_time=image.modified_time,
        content_hash=hash_file(image.path),
        width=width,
        height=height,
        date_taken=date_taken,
        exif_json=exif_json,
    )


def scan_images(root_path: Path) -> Iterator[ScannedImage]:
    """Yield supported image files with metadata and content hashes."""
    for image in discover_images(root_path):
        yield scan_discovered_image(image)
