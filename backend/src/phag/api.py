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
from phag.db import connect, init_database
from phag.filesystem import list_directories
from phag.images import get_active_image_path
from phag.indexed_roots import add_indexed_root, disable_indexed_root, list_indexed_root_rows
from phag.indexer import index_path, index_roots, purge_orphans
from phag.library import list_library_images
from phag.scan_jobs import enqueue_scan, get_scan_job, scan_job_to_dict
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
    if not settings.db_path.exists():
        init_database(settings.db_path)
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

    return [dict(row) for row in rows]


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
        root_id = add_indexed_root(settings.db_path, root.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"id": root_id, "path": str(root.path.expanduser().resolve())}


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
    }


@app.post("/scan-jobs", status_code=202)
def create_scan_job(scan: ScanRequest, settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Queue an indexing scan and return immediately."""
    job = enqueue_scan(settings.db_path, scan.root_path)
    return scan_job_to_dict(job)


@app.get("/scan-jobs/{job_id}")
def get_scan_job_status(job_id: str) -> dict[str, object]:
    """Return background scan job status."""
    job = get_scan_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scan job not found")
    return scan_job_to_dict(job)


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


@app.get("/originals/{image_id}")
def get_original(image_id: int, settings: Settings = Depends(get_settings)) -> FileResponse:
    """Serve one active source file for an indexed image."""
    with connect(settings.db_path) as connection:
        path = get_active_image_path(connection, image_id)

    if path is None or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="Original image not found")

    return FileResponse(path)
