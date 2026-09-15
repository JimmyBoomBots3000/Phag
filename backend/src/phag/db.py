"""SQLite connection and schema initialization helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path


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
