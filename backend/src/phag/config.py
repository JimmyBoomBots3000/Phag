"""Runtime configuration for the backend service."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Resolved backend settings."""

    db_path: Path

    @property
    def app_data_dir(self) -> Path:
        """Return the directory that owns generated app data."""
        return self.db_path.parent


def load_settings() -> Settings:
    """Load settings from environment variables."""
    db_path = Path(os.environ.get("PHAG_DB_PATH", default_db_path())).expanduser().resolve()
    return Settings(db_path=db_path)


def default_db_path() -> Path:
    """Return the default database path for the current platform."""
    return default_app_data_dir() / "phag.db"


def default_app_data_dir() -> Path:
    """Return the app data directory for the current platform."""
    configured_dir = os.environ.get("PHAG_APP_DATA_DIR")
    if configured_dir:
        return Path(configured_dir).expanduser().resolve()

    if sys.platform == "win32":
        base_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base_dir / "Phag"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Phag"

    base_dir = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base_dir / "phag"
