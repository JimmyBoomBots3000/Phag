"""Command-line entry point for development and admin tasks."""

from __future__ import annotations

import argparse
from pathlib import Path

from phag.db import connect, init_database
from phag.indexed_roots import add_indexed_root, disable_indexed_root, list_indexed_roots
from phag.indexer import index_path, index_roots, purge_orphans
from phag.library import list_library_images
from phag.openapi import export_openapi_spec
from phag.scanner import discover_images, hash_file, iter_image_files, scan_images
from phag.tags import add_tag_to_image, create_tag, list_tags, remove_tag_from_image
from phag.watcher import watch_roots


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(prog="phag")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Create a SQLite database")
    init_db.add_argument("db_path", type=Path, help="Path to the database file")

    add_root = subparsers.add_parser("add-root", help="Register a folder to index")
    add_root.add_argument("db_path", type=Path, help="Path to the database file")
    add_root.add_argument("root_path", type=Path, help="Folder to index")

    list_roots = subparsers.add_parser("list-roots", help="List enabled indexed roots")
    list_roots.add_argument("db_path", type=Path, help="Path to the database file")

    remove_root = subparsers.add_parser("remove-root", help="Disable an indexed root")
    remove_root.add_argument("db_path", type=Path, help="Path to the database file")
    remove_root.add_argument("root_id", type=int, help="Indexed root id")

    scan_files = subparsers.add_parser("scan-files", help="Print image files under a folder")
    scan_files.add_argument("root_path", type=Path, help="Folder to scan")

    discover = subparsers.add_parser("discover-images", help="Print image file metadata under a folder")
    discover.add_argument("root_path", type=Path, help="Folder to scan")

    hash_image = subparsers.add_parser("hash-file", help="Print SHA-256 for one file")
    hash_image.add_argument("path", type=Path, help="File to hash")

    scan_images_parser = subparsers.add_parser("scan-images", help="Print image metadata and hashes under a folder")
    scan_images_parser.add_argument("root_path", type=Path, help="Folder to scan")

    index_path_parser = subparsers.add_parser("index-path", help="Scan and index a path")
    index_path_parser.add_argument("db_path", type=Path, help="Path to the database file")
    index_path_parser.add_argument("root_path", type=Path, help="Folder to index")

    index_roots_parser = subparsers.add_parser("index-roots", help="Scan and index all enabled roots")
    index_roots_parser.add_argument("db_path", type=Path, help="Path to the database file")

    purge_orphans_parser = subparsers.add_parser("purge-orphans", help="Delete expired orphan metadata")
    purge_orphans_parser.add_argument("db_path", type=Path, help="Path to the database file")
    purge_orphans_parser.add_argument(
        "--retention-days",
        type=int,
        default=3,
        help="Days to retain orphan metadata before purging",
    )

    create_tag_parser = subparsers.add_parser("create-tag", help="Create a tag")
    create_tag_parser.add_argument("db_path", type=Path, help="Path to the database file")
    create_tag_parser.add_argument("name", help="Tag name")

    list_tags_parser = subparsers.add_parser("list-tags", help="List tags")
    list_tags_parser.add_argument("db_path", type=Path, help="Path to the database file")

    tag_image_parser = subparsers.add_parser("tag-image", help="Apply a tag to an image")
    tag_image_parser.add_argument("db_path", type=Path, help="Path to the database file")
    tag_image_parser.add_argument("image_id", type=int, help="Image id")
    tag_image_parser.add_argument("tag_name", help="Tag name")

    untag_image_parser = subparsers.add_parser("untag-image", help="Remove a tag from an image")
    untag_image_parser.add_argument("db_path", type=Path, help="Path to the database file")
    untag_image_parser.add_argument("image_id", type=int, help="Image id")
    untag_image_parser.add_argument("tag_id", type=int, help="Tag id")

    list_images_parser = subparsers.add_parser("list-images", help="List indexed library images")
    list_images_parser.add_argument("db_path", type=Path, help="Path to the database file")
    list_images_parser.add_argument("--tag", action="append", default=[], help="Filter by tag name")
    list_images_parser.add_argument("--tag-match", choices=["and", "or"], default="and")
    list_images_parser.add_argument(
        "--sort-by",
        choices=["filename", "date_modified", "date_taken", "file_size"],
        default="filename",
    )
    list_images_parser.add_argument("--sort-direction", choices=["asc", "desc"], default="asc")
    list_images_parser.add_argument("--limit", type=int, default=100)
    list_images_parser.add_argument("--offset", type=int, default=0)

    watch_roots_parser = subparsers.add_parser("watch-roots", help="Continuously rescan enabled roots")
    watch_roots_parser.add_argument("db_path", type=Path, help="Path to the database file")
    watch_roots_parser.add_argument("--interval-seconds", type=int, default=30)

    serve_parser = subparsers.add_parser("serve", help="Run the FastAPI development server")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")

    export_openapi_parser = subparsers.add_parser("export-openapi", help="Write the OpenAPI spec to JSON")
    export_openapi_parser.add_argument("output_path", type=Path, help="OpenAPI JSON output path")

    return parser


def main() -> None:
    """Run the phag command-line interface."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-db":
        init_database(args.db_path)
        print(f"Initialized {args.db_path}")
        return

    if args.command == "add-root":
        root_id = add_indexed_root(args.db_path, args.root_path)
        print(f"Added indexed root {root_id}: {args.root_path}")
        return

    if args.command == "list-roots":
        for root_path in list_indexed_roots(args.db_path):
            print(root_path)
        return

    if args.command == "remove-root":
        removed_count = disable_indexed_root(args.db_path, args.root_id)
        print(f"Removed {removed_count} indexed roots")
        return

    if args.command == "scan-files":
        for image_path in iter_image_files(args.root_path):
            print(image_path)
        return

    if args.command == "discover-images":
        for image in discover_images(args.root_path):
            print(f"{image.path}\t{image.file_size_bytes}\t{image.modified_time}")
        return

    if args.command == "hash-file":
        print(hash_file(args.path))
        return

    if args.command == "scan-images":
        for image in scan_images(args.root_path):
            print(f"{image.path}\t{image.file_size_bytes}\t{image.modified_time}\t{image.content_hash}")
        return

    if args.command == "index-path":
        summary = index_path(args.db_path, args.root_path)
        print(
            f"Discovered {summary.discovered_count} images; "
            f"indexed {summary.indexed_count}; "
            f"skipped {summary.skipped_count} unchanged; "
            f"orphaned {summary.orphaned_count}; "
            f"thumbnails {summary.thumbnail_count}"
        )
        return

    if args.command == "index-roots":
        summary = index_roots(args.db_path)
        print(
            f"Discovered {summary.discovered_count} images; "
            f"indexed {summary.indexed_count}; "
            f"skipped {summary.skipped_count} unchanged; "
            f"orphaned {summary.orphaned_count}; "
            f"thumbnails {summary.thumbnail_count}"
        )
        return

    if args.command == "purge-orphans":
        summary = purge_orphans(args.db_path, args.retention_days)
        print(
            f"Purged {summary.purged_file_location_count} file locations; "
            f"purged {summary.purged_image_count} images"
        )
        return

    if args.command == "create-tag":
        with connect(args.db_path) as connection:
            tag_id = create_tag(connection, args.name)
        print(f"Created tag {tag_id}: {args.name}")
        return

    if args.command == "list-tags":
        with connect(args.db_path) as connection:
            for tag in list_tags(connection):
                print(f"{tag.id}\t{tag.display_name}")
        return

    if args.command == "tag-image":
        with connect(args.db_path) as connection:
            tag_id = create_tag(connection, args.tag_name)
            add_tag_to_image(connection, args.image_id, tag_id)
        print(f"Tagged image {args.image_id} with tag {tag_id}: {args.tag_name}")
        return

    if args.command == "untag-image":
        with connect(args.db_path) as connection:
            remove_tag_from_image(connection, args.image_id, args.tag_id)
        print(f"Removed tag {args.tag_id} from image {args.image_id}")
        return

    if args.command == "list-images":
        with connect(args.db_path) as connection:
            for image in list_library_images(
                connection=connection,
                tag_names=args.tag,
                tag_match=args.tag_match,
                sort_by=args.sort_by,
                sort_direction=args.sort_direction,
                limit=args.limit,
                offset=args.offset,
            ):
                print(
                    f"{image.id}\t{image.path_relative}\t{image.file_size_bytes}\t"
                    f"{image.modified_time}\t{image.small_thumbnail_path or ''}"
                )
        return

    if args.command == "watch-roots":
        watch_roots(args.db_path, args.interval_seconds)
        return

    if args.command == "serve":
        import uvicorn

        uvicorn.run("phag.api:app", host=args.host, port=args.port, reload=args.reload)
        return

    if args.command == "export-openapi":
        export_openapi_spec(args.output_path)
        print(f"Wrote OpenAPI spec to {args.output_path}")
        return

    parser.error(f"Unknown command: {args.command}")
