"""Read-only filesystem browsing helpers for server-side folder selection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
}

EXCLUDED_DIRECTORY_SUFFIXES = {
    ".app",
    ".framework",
    ".lproj",
    ".photoslibrary",
}


@dataclass(frozen=True)
class DirectoryListing:
    """A directory and its immediate child directories."""

    path: str
    parent_path: str | None
    directories: list[str]


def list_directories(path: Path | None = None) -> DirectoryListing:
    """Return immediate child directories for a server-local path."""
    current_path = (path or Path.home()).expanduser().resolve()
    if not current_path.exists():
        raise FileNotFoundError(f"Path does not exist: {current_path}")
    if not current_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {current_path}")

    directories = sorted(str(child) for child in current_path.iterdir() if is_browsable_directory(child))

    parent = current_path.parent if current_path.parent != current_path else None
    return DirectoryListing(
        path=str(current_path),
        parent_path=str(parent) if parent is not None else None,
        directories=directories,
    )


def is_browsable_directory(path: Path) -> bool:
    """Return true when a path should appear in the root folder chooser."""
    if path.name.startswith("."):
        return False
    if path.name in EXCLUDED_DIRECTORY_NAMES:
        return False
    if path.suffix.casefold() in EXCLUDED_DIRECTORY_SUFFIXES:
        return False

    try:
        return path.is_dir()
    except PermissionError:
        return False
