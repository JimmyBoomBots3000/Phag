"""SQLite connection and schema initialization helpers."""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

CURRENT_SCHEMA_VERSION = 1


def find_schema_file(start: Path | None = None) -> Path:
    """Find the project's SQLite schema file by walking upward from a path."""
    search_start = (start or Path(__file__).parent).resolve()

    for base in [search_start, *search_start.parents]:
        schema_path = base / "schema" / "schema-sqlite.sql"
        if schema_path.is_file():
            return schema_path

    raise FileNotFoundError("Could not find schema/schema-sqlite.sql")


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection configured for this application."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_database(db_path: Path, schema_path: Path | None = None) -> None:
    """Create a SQLite database by executing the project schema."""
    db_path = db_path.expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    schema_path = schema_path or find_schema_file()
    schema_sql = schema_path.read_text(encoding="utf-8")

    with connect(db_path) as conn:
        conn.executescript(schema_sql)
        set_user_version(conn, CURRENT_SCHEMA_VERSION)


def ensure_database(db_path: Path, schema_path: Path | None = None) -> None:
    """Create or migrate a SQLite database in place."""
    db_path = db_path.expanduser().resolve()
    if not db_path.exists():
        init_database(db_path, schema_path)
        return

    with connect(db_path) as conn:
        migrations = needed_migrations(conn)
        if not migrations:
            set_user_version(conn, CURRENT_SCHEMA_VERSION)
            return

    backup_database(db_path)
    with connect(db_path) as conn:
        for migration in migrations:
            migration(conn)
        set_user_version(conn, CURRENT_SCHEMA_VERSION)


def needed_migrations(conn: sqlite3.Connection) -> list[Callable[[sqlite3.Connection], None]]:
    """Return migrations required by the current database shape."""
    migrations = []
    root_columns = table_columns(conn, "indexed_roots")
    if not root_columns:
        raise RuntimeError("Database is missing required table: indexed_roots")
    if "recursive" not in root_columns:
        migrations.append(add_indexed_roots_recursive_column)
    return migrations


def add_indexed_roots_recursive_column(conn: sqlite3.Connection) -> None:
    """Add recursive root tracking to existing root rows."""
    conn.execute(
        """
        ALTER TABLE indexed_roots
        ADD COLUMN recursive INTEGER NOT NULL DEFAULT 1 CHECK (recursive IN (0, 1))
        """
    )


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """Return column names for a table, or an empty set if it does not exist."""
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def set_user_version(conn: sqlite3.Connection, version: int) -> None:
    """Set the SQLite user_version pragma."""
    conn.execute(f"PRAGMA user_version = {version}")


def backup_database(db_path: Path) -> Path:
    """Copy a database before applying migrations."""
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup_path = db_path.with_name(f"{db_path.name}.backup-{timestamp}")
    shutil.copy2(db_path, backup_path)
    return backup_path
