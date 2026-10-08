"""FastAPI application for the image tagging backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path
import sqlite3

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from phag.config import Settings, load_settings
from phag.db import connect, ensure_database
from phag.filesystem import list_directories
from phag.images import get_active_image_path
from phag.indexed_roots import (
    add_indexed_root,
    disable_indexed_root,
    find_covered_roots,
    find_covering_recursive_root,
    list_indexed_root_rows,
    update_indexed_root_recursive,
)
from phag.indexer import index_path, index_roots, purge_orphans
from phag.library import list_library_images
from phag.mover import move_image_file
from phag.scan_jobs import (
    cancel_all_scan_jobs,
    cancel_scan_job,
    enqueue_scan,
    get_scan_job,
    list_scan_jobs,
    scan_job_to_dict,
)
from phag.tags import (
    add_tag_to_image,
    create_tag,
    delete_tag,
    delete_unused_tags,
    list_image_tags,
    list_tags,
    remove_tag_from_image,
    rename_tag,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize application resources for the API lifespan."""
    settings = load_settings()
    ensure_database(settings.db_path)
    yield


app = FastAPI(title="Phag API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RootCreate(BaseModel):
    """Request body for creating an indexed root."""

    path: Path
    recursive: bool = True
    replace_covered_roots: bool = False


class RootUpdate(BaseModel):
    """Request body for updating indexed root scan options."""

    recursive: bool
    replace_covered_roots: bool = False


class TagCreate(BaseModel):
    """Request body for creating or applying a tag."""

    name: str = Field(min_length=1)


class TagUpdate(BaseModel):
    """Request body for renaming a tag."""

    name: str = Field(min_length=1)


class ScanRequest(BaseModel):
    """Request body for starting an indexing scan."""

    root_path: Path | None = None


class PurgeRequest(BaseModel):
    """Request body for orphan metadata cleanup."""

    retention_days: int = Field(default=3, ge=0)


class ImageMoveRequest(BaseModel):
    """Request body for moving one indexed image file."""

    destination_directory: Path
    allow_unindexed: bool = False


class DirectoryListingResponse(BaseModel):
    """Response body for server-side directory browsing."""

    path: str
    parent_path: str | None
    directories: list[str]


def get_settings() -> Settings:
    """Return backend settings for request handlers."""
    return load_settings()


@app.get("/health")
def health() -> dict[str, str]:
    """Return service health."""
    return {"status": "ok"}


@app.get("/roots")
def get_roots(
    include_disabled: bool = False,
    settings: Settings = Depends(get_settings),
) -> list[dict[str, object]]:
    """List configured indexed roots."""
    with connect(settings.db_path) as connection:
        rows = list_indexed_root_rows(connection, include_disabled=include_disabled)

        return [root_row_to_dict(row) for row in rows]


@app.get("/filesystem/directories")
def get_directories(path: Path | None = None) -> DirectoryListingResponse:
    """List server-local directories for root selection."""
    try:
        listing = list_directories(path)
    except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DirectoryListingResponse(
        path=listing.path,
        parent_path=listing.parent_path,
        directories=listing.directories,
    )


@app.post("/roots", status_code=201)
def create_root(root: RootCreate, settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Register a folder as an indexed root."""
    try:
        root_id = add_indexed_root(
            settings.db_path,
            root.path,
            recursive=root.recursive,
            replace_covered_roots=root.replace_covered_roots,
        )
    except ValueError as exc:
        raise root_overlap_exception(settings.db_path, root.path, root.recursive, exc) from exc

    return {"id": root_id, "path": str(root.path.expanduser().resolve()), "recursive": root.recursive}


@app.patch("/roots/{root_id}")
def patch_root(root_id: int, root: RootUpdate, settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Update scan options for an indexed root."""
    with connect(settings.db_path) as connection:
        root_row = connection.execute("""
                                      SELECT id, path
                                      FROM indexed_roots
                                      WHERE id = ?
                                      """,
                                      (root_id,)).fetchone()
        if root_row is None:
            raise HTTPException(status_code=404, detail="Root not found")
        try:
            updated_count = update_indexed_root_recursive(
                connection,
                root_id,
                root.recursive,
                replace_covered_roots=root.replace_covered_roots,
            )
        except ValueError as exc:
            raise root_overlap_exception(
                settings.db_path,
                Path(root_row["path"]),
                root.recursive,
                exc,
                excluding_root_id=root_id,
            ) from exc
        if updated_count == 0:
            raise HTTPException(status_code=404, detail="Root not found")
        row = connection.execute("""
                                 SELECT id, path, recursive, enabled, last_scanned_at
                                 FROM indexed_roots
                                 WHERE id = ?
                                 """,
                                 (root_id,)).fetchone()

    return root_row_to_dict(row)


@app.delete("/roots/{root_id}")
def delete_root(root_id: int, settings: Settings = Depends(get_settings)) -> dict[str, int]:
    """Disable an indexed root."""
    with connect(settings.db_path) as connection:
        removed_count = disable_indexed_root(connection, root_id)
        deleted_tag_count = delete_unused_tags(connection) if removed_count else 0
    if removed_count == 0:
        raise HTTPException(status_code=404, detail="Root not found")
    return {"removed_count": removed_count, "deleted_tag_count": deleted_tag_count}


@app.post("/scans")
def create_scan(scan: ScanRequest, settings: Settings = Depends(get_settings)) -> dict[str, int]:
    """Run an indexing scan immediately."""
    try:
        summary = index_path(settings.db_path, scan.root_path) if scan.root_path else index_roots(settings.db_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "discovered_count": summary.discovered_count,
        "indexed_count": summary.indexed_count,
        "skipped_count": summary.skipped_count,
        "orphaned_count": summary.orphaned_count,
        "thumbnail_count": summary.thumbnail_count,
        "failed_count": summary.failed_count,
    }


@app.post("/scan-jobs", status_code=202)
def create_scan_job(scan: ScanRequest, settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Queue an indexing scan and return immediately."""
    job = enqueue_scan(settings.db_path, scan.root_path)
    return scan_job_to_dict(job)


@app.get("/scan-jobs")
def get_scan_jobs() -> list[dict[str, object]]:
    """Return all known scan jobs."""
    return [scan_job_to_dict(job) for job in list_scan_jobs()]


@app.get("/scan-jobs/{job_id}")
def get_scan_job_status(job_id: str) -> dict[str, object]:
    """Return background scan job status."""
    job = get_scan_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scan job not found")
    return scan_job_to_dict(job)


@app.delete("/scan-jobs/{job_id}")
def cancel_scan_job_request(job_id: str) -> dict[str, object]:
    """Cancel one queued or running scan job."""
    job = cancel_scan_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scan job not found")
    return scan_job_to_dict(job)


@app.delete("/scan-jobs")
def cancel_scan_jobs_request() -> dict[str, object]:
    """Cancel all queued or running scan jobs."""
    jobs, canceled_count = cancel_all_scan_jobs()
    return {
        "canceled_count": canceled_count,
        "jobs": [scan_job_to_dict(job) for job in jobs],
    }


@app.post("/orphans/purge")
def purge_orphan_metadata(
    request: PurgeRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, int]:
    """Purge expired orphan metadata."""
    summary = purge_orphans(settings.db_path, request.retention_days)
    with connect(settings.db_path) as connection:
        deleted_tag_count = delete_unused_tags(connection)
    return {
        "purged_file_location_count": summary.purged_file_location_count,
        "purged_image_count": summary.purged_image_count,
        "deleted_tag_count": deleted_tag_count,
    }


@app.get("/images")
def get_images(
    tag: list[str] = Query(default=[]),
    root_id: list[int] = Query(default=[]),
    include_untagged: bool = False,
    tag_match: str = "and",
    sort_by: str = "filename",
    sort_direction: str = "asc",
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, object]]:
    """List active library images."""
    try:
        with connect(settings.db_path) as connection:
            images = list_library_images(
                connection=connection,
                tag_names=tag,
                root_ids=root_id,
                include_untagged=include_untagged,
                tag_match=tag_match,
                sort_by=sort_by,
                sort_direction=sort_direction,
                limit=limit,
                offset=offset,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return [image.__dict__ for image in images]


@app.get("/images/{image_id}/tags")
def get_image_tags(image_id: int, settings: Settings = Depends(get_settings)) -> list[dict[str, object]]:
    """List tags for one image."""
    with connect(settings.db_path) as connection:
        return [tag.__dict__ for tag in list_image_tags(connection, image_id)]


@app.post("/images/{image_id}/move")
def move_image(
    image_id: int,
    request: ImageMoveRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Move one active image file into a destination directory."""
    try:
        with connect(settings.db_path) as connection:
            moved = move_image_file(
                connection,
                image_id,
                request.destination_directory,
                allow_unindexed=request.allow_unindexed,
            )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        if str(exc) == "destination_not_indexed":
            raise HTTPException(status_code=400, detail="Destination is not inside an indexed folder") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "image_id": moved.image_id,
        "source_path": str(moved.source_path),
        "destination_path": str(moved.destination_path),
        "root_id": moved.root_id,
        "path_relative": moved.path_relative,
        "indexed": moved.indexed,
    }


@app.post("/images/{image_id}/tags", status_code=201)
def tag_image(
    image_id: int,
    tag: TagCreate,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Apply a tag to one image, creating the tag if needed."""
    with connect(settings.db_path) as connection:
        tag_id = create_tag(connection, tag.name)
        add_tag_to_image(connection, image_id, tag_id)

    return {"image_id": image_id, "tag_id": tag_id, "name": tag.name}


@app.delete("/images/{image_id}/tags/{tag_id}")
def untag_image(image_id: int, tag_id: int, settings: Settings = Depends(get_settings)) -> dict[str, int]:
    """Remove one tag association from an image."""
    with connect(settings.db_path) as connection:
        removed_count = remove_tag_from_image(connection, image_id, tag_id)
        deleted_tag_count = delete_unused_tags(connection) if removed_count else 0

    return {"removed_count": removed_count, "deleted_tag_count": deleted_tag_count}


@app.get("/tags")
def get_tags(settings: Settings = Depends(get_settings)) -> list[dict[str, object]]:
    """List all tags."""
    with connect(settings.db_path) as connection:
        return [tag.__dict__ for tag in list_tags(connection)]


@app.post("/tags", status_code=201)
def post_tag(tag: TagCreate, settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Create a tag."""
    with connect(settings.db_path) as connection:
        tag_id = create_tag(connection, tag.name)

    return {"id": tag_id, "name": tag.name}


@app.delete("/tags/{tag_id}")
def remove_tag(tag_id: int, settings: Settings = Depends(get_settings)) -> dict[str, int]:
    """Delete a tag globally."""
    with connect(settings.db_path) as connection:
        deleted_count = delete_tag(connection, tag_id)

    return {"deleted_count": deleted_count}


@app.patch("/tags/{tag_id}")
def patch_tag(tag_id: int, tag: TagUpdate, settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Rename a tag globally."""
    try:
        with connect(settings.db_path) as connection:
            updated_count = rename_tag(connection, tag_id, tag.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=400, detail="Tag name already exists") from exc

    if updated_count == 0:
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"id": tag_id, "name": tag.name}


@app.get("/thumbnails/{size_name}/{prefix}/{filename}")
def get_thumbnail(
    size_name: str,
    prefix: str,
    filename: str,
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    """Serve a generated thumbnail file."""
    path = settings.app_data_dir / "thumbnails" / size_name / prefix / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(path)


def root_row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    """Convert an indexed root database row to an API response."""
    return {
        "id": row["id"],
        "path": row["path"],
        "recursive": bool(row["recursive"]),
        "enabled": bool(row["enabled"]),
        "last_scanned_at": row["last_scanned_at"],
    }


def root_overlap_exception(
    db_path: Path,
    root_path: Path,
    recursive: bool,
    exc: ValueError,
    excluding_root_id: int | None = None,
) -> HTTPException:
    """Convert root overlap validation errors to structured API errors."""
    message = str(exc)
    with connect(db_path) as connection:
        if message.startswith("root_already_covered"):
            covering_root = find_covering_recursive_root(
                connection,
                root_path.expanduser().resolve(),
                excluding_root_id,
            )
            return HTTPException(
                status_code=409,
                detail={
                    "code": "root_already_covered",
                    "covering_root": root_overlap_to_dict(covering_root) if covering_root else None,
                },
            )
        if message == "covered_roots_require_confirmation":
            covered_roots = find_covered_roots(
                connection,
                root_path.expanduser().resolve(),
                excluding_root_id,
            ) if recursive else []
            return HTTPException(
                status_code=409,
                detail={
                    "code": "covered_roots_require_confirmation",
                    "covered_roots": [root_overlap_to_dict(root) for root in covered_roots],
                },
            )

    return HTTPException(status_code=400, detail=message)


def root_overlap_to_dict(root: object) -> dict[str, object]:
    """Convert a root overlap object to API error detail."""
    return {
        "id": root.id,
        "path": str(root.path),
        "recursive": root.recursive,
    }


@app.get("/images/{image_id}/file")
def get_image_file(image_id: int, settings: Settings = Depends(get_settings)) -> FileResponse:
    """Serve one active source file for an indexed image."""
    with connect(settings.db_path) as connection:
        path = get_active_image_path(connection, image_id)

    if path is None or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="Image file not found")

    return FileResponse(path)
