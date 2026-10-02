"""In-memory background scan job queue for API-triggered scans."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Literal
from uuid import uuid4

from phag.indexer import ScanCanceled, ScanSummary, index_path_with_progress, index_roots_with_progress

ScanJobStatus = Literal["queued", "running", "canceling", "canceled", "completed", "failed"]


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
    cancel_requested: bool = False
    future: Future[None] | None = None


_executor = ThreadPoolExecutor(max_workers=1)
_jobs: dict[str, ScanJob] = {}
_jobs_lock = Lock()


def enqueue_scan(db_path: Path, root_path: Path | None = None) -> ScanJob:
    """Queue a scan and return its initial job state."""
    job = ScanJob(id=uuid4().hex, db_path=db_path, root_path=root_path)
    with _jobs_lock:
        _jobs[job.id] = job

    future = _executor.submit(_run_scan_job, job.id)
    with _jobs_lock:
        job.future = future
    return job


def get_scan_job(job_id: str) -> ScanJob | None:
    """Return a queued scan job by id."""
    with _jobs_lock:
        return _jobs.get(job_id)


def list_scan_jobs() -> list[ScanJob]:
    """Return all known scan jobs."""
    with _jobs_lock:
        return list(reversed(_jobs.values()))


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


def cancel_scan_job(job_id: str) -> ScanJob | None:
    """Request cancellation for one scan job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        if job.status == "queued":
            job.cancel_requested = True
            job.status = "canceled"
        elif job.status == "running":
            job.cancel_requested = True
            job.status = "canceling"
        return job


def cancel_all_scan_jobs() -> tuple[list[ScanJob], int]:
    """Request cancellation for all queued or running scan jobs."""
    with _jobs_lock:
        jobs = list(_jobs.values())
        canceled_count = 0
        for job in jobs:
            if job.status == "queued":
                canceled_count += 1
                job.cancel_requested = True
                job.status = "canceled"
            elif job.status == "running":
                canceled_count += 1
                job.cancel_requested = True
                job.status = "canceling"
        return jobs, canceled_count


def _run_scan_job(job_id: str) -> None:
    with _jobs_lock:
        job = _jobs[job_id]
        if job.cancel_requested or job.status == "canceled":
            job.status = "canceled"
            return
        job.status = "running"

    try:
        summary = (
            index_path_with_progress(
                job.db_path,
                job.root_path,
                progress_callback=lambda path: _update_current_path(job_id, path),
                cancellation_callback=lambda: _is_cancel_requested(job_id),
            )
            if job.root_path
            else index_roots_with_progress(
                job.db_path,
                lambda path: _update_current_path(job_id, path),
                lambda: _is_cancel_requested(job_id),
            )
        )
    except ScanCanceled:
        with _jobs_lock:
            job.status = "canceled"
        return
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


def _is_cancel_requested(job_id: str) -> bool:
    with _jobs_lock:
        job = _jobs[job_id]
        return job.cancel_requested or job.status == "canceling"
