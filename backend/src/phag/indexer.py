"""High-level indexing workflows that coordinate scanning and persistence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from phag.db import connect
from phag.file_locations import (
    is_unchanged_file_location,
    mark_missing_file_locations_orphaned,
    path_relative_to_root,
    purge_orphaned_file_locations,
    upsert_file_location,
)
from phag.images import delete_unlocated_images, upsert_image
from phag.indexed_roots import list_indexed_roots, mark_indexed_root_scanned, upsert_indexed_root
from phag.scan_events import add_scan_event
from phag.scanner import discover_images, scan_discovered_image
from phag.thumbnails import generate_thumbnails, upsert_thumbnail


@dataclass(frozen=True)
class ScanSummary:
    """Counts describing the outcome of an indexing run."""

    discovered_count: int = 0
    indexed_count: int = 0
    skipped_count: int = 0
    orphaned_count: int = 0
    thumbnail_count: int = 0


@dataclass(frozen=True)
class PurgeSummary:
    """Counts describing orphan cleanup work."""

    purged_file_location_count: int = 0
    purged_image_count: int = 0


def index_path(db_path: Path, root_path: Path) -> ScanSummary:
    """Index one root folder into the database."""
    return index_path_with_progress(db_path, root_path)


def index_path_with_progress(
    db_path: Path,
    root_path: Path,
    progress_callback: Callable[[Path], None] | None = None,
) -> ScanSummary:
    """Index one root folder and optionally report the current directory."""
    root_path = root_path.expanduser().resolve()
    discovered_count = 0
    indexed_count = 0
    skipped_count = 0
    thumbnail_count = 0
    seen_path_relatives: set[str] = set()
    app_data_dir = db_path.expanduser().resolve().parent

    if progress_callback:
        progress_callback(root_path)

    with connect(db_path) as connection:
        root_id = upsert_indexed_root(connection, root_path)
        add_scan_event(
            connection=connection,
            root_id=root_id,
            event_type="scan_started",
            path=root_path,
        )

        for discovered_image in discover_images(root_path):
            if progress_callback:
                progress_callback(discovered_image.path.parent)

            discovered_count += 1
            seen_path_relatives.add(path_relative_to_root(root_path, discovered_image.path))

            if is_unchanged_file_location(
                connection=connection,
                root_id=root_id,
                root_path=root_path,
                image_path=discovered_image.path,
                file_size_bytes=discovered_image.file_size_bytes,
                modified_time=discovered_image.modified_time,
            ):
                skipped_count += 1
                continue

            scanned_image = scan_discovered_image(discovered_image)
            image_id = upsert_image(connection, scanned_image)
            upsert_file_location(
                connection=connection,
                root_id=root_id,
                root_path=root_path,
                image_id=image_id,
                scanned_image=scanned_image,
            )
            for thumbnail in generate_thumbnails(app_data_dir, scanned_image):
                upsert_thumbnail(connection, image_id, thumbnail)
                thumbnail_count += 1
            indexed_count += 1

        orphaned_count = mark_missing_file_locations_orphaned(
            connection,
            root_id,
            seen_path_relatives,
        )
        mark_indexed_root_scanned(connection, root_id)

        summary = ScanSummary(
            discovered_count=discovered_count,
            indexed_count=indexed_count,
            skipped_count=skipped_count,
            orphaned_count=orphaned_count,
            thumbnail_count=thumbnail_count,
        )
        add_scan_event(
            connection=connection,
            root_id=root_id,
            event_type="scan_completed",
            path=root_path,
            details={
                "discovered_count": summary.discovered_count,
                "indexed_count": summary.indexed_count,
                "skipped_count": summary.skipped_count,
                "orphaned_count": summary.orphaned_count,
                "thumbnail_count": summary.thumbnail_count,
            },
        )

    return summary


def index_roots(db_path: Path) -> ScanSummary:
    """Index every enabled root registered in the database."""
    return index_roots_with_progress(db_path)


def index_roots_with_progress(
    db_path: Path,
    progress_callback: Callable[[Path], None] | None = None,
) -> ScanSummary:
    """Index every enabled root and optionally report the current directory."""
    discovered_count = 0
    indexed_count = 0
    skipped_count = 0
    orphaned_count = 0
    thumbnail_count = 0

    for root_path in list_indexed_roots(db_path):
        summary = index_path_with_progress(db_path, root_path, progress_callback)
        discovered_count += summary.discovered_count
        indexed_count += summary.indexed_count
        skipped_count += summary.skipped_count
        orphaned_count += summary.orphaned_count
        thumbnail_count += summary.thumbnail_count

    return ScanSummary(
        discovered_count=discovered_count,
        indexed_count=indexed_count,
        skipped_count=skipped_count,
        orphaned_count=orphaned_count,
        thumbnail_count=thumbnail_count,
    )


def purge_orphans(db_path: Path, retention_days: int = 3) -> PurgeSummary:
    """Purge orphaned file locations and unreferenced logical images."""
    with connect(db_path) as connection:
        purged_file_location_count = purge_orphaned_file_locations(
            connection,
            retention_days,
        )
        purged_image_count = delete_unlocated_images(connection)

    return PurgeSummary(
        purged_file_location_count=purged_file_location_count,
        purged_image_count=purged_image_count,
    )
