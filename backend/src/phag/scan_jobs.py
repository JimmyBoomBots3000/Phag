"""In-memory background scan job queue for API-triggered scans."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Literal
from uuid import uuid4

from phag.indexer import ScanSummary, index_path_with_progress, index_roots_with_progress

ScanJobStatus = Literal["queued", "running", "completed", "failed"]


@dataclass
class ScanJob:
    """State for one queued scan request."""

    id: str
    db_path: Path
    root_path: Path | None
    status: ScanJobStatus = "queued"
    current_path: Path | None = None
    summary: ScanSummary | None = None
    error: str | None = None


_executor = ThreadPoolExecutor(max_workers=1)
_jobs: dict[str, ScanJob] = {}
_jobs_lock = Lock()


def enqueue_scan(db_path: Path, root_path: Path | None = None) -> ScanJob:
    """Queue a scan and return its initial job state."""
    job = ScanJob(id=uuid4().hex, db_path=db_path, root_path=root_path)
    with _jobs_lock:
        _jobs[job.id] = job

    _executor.submit(_run_scan_job, job.id)
    return job


def get_scan_job(job_id: str) -> ScanJob | None:
    """Return a queued scan job by id."""
    with _jobs_lock:
        return _jobs.get(job_id)


def scan_job_to_dict(job: ScanJob) -> dict[str, object]:
    """Convert a scan job to an API response dictionary."""
    return {
        "id": job.id,
        "root_path": str(job.root_path) if job.root_path else None,
        "current_path": str(job.current_path) if job.current_path else None,
        "status": job.status,
        "summary": job.summary.__dict__ if job.summary else None,
        "error": job.error,
    }


def _run_scan_job(job_id: str) -> None:
    with _jobs_lock:
        job = _jobs[job_id]
        job.status = "running"

    try:
        summary = (
            index_path_with_progress(job.db_path, job.root_path, lambda path: _update_current_path(job_id, path))
            if job.root_path
            else index_roots_with_progress(job.db_path, lambda path: _update_current_path(job_id, path))
        )
    except Exception as exc:  # pragma: no cover - defensive job boundary
        with _jobs_lock:
            job.status = "failed"
            job.error = str(exc)
        return

    with _jobs_lock:
        job.status = "completed"
        job.summary = summary


def _update_current_path(job_id: str, path: Path) -> None:
    with _jobs_lock:
        _jobs[job_id].current_path = path
