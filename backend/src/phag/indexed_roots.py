"""Operations for folders configured as image indexing roots."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from phag.db import connect
from phag.file_locations import mark_root_file_locations_orphaned


def list_indexed_root_rows(
    conn: sqlite3.Connection,
    include_disabled: bool = False,
) -> list[sqlite3.Row]:
    """Return indexed root database rows."""
    if include_disabled:
        return conn.execute("""
                            SELECT id, path, recursive, enabled, last_scanned_at
                            FROM indexed_roots
                            ORDER BY path
                            """).fetchall()

    return conn.execute("""
                        SELECT id, path, recursive, enabled, last_scanned_at
                        FROM indexed_roots
                        WHERE enabled = 1
                        ORDER BY path
                        """).fetchall()


def add_indexed_root(db_path: Path, root_path: Path) -> int:
    """Register a folder path as an indexed root."""
    with connect(db_path) as conn:
        return upsert_indexed_root(conn, root_path)


def upsert_indexed_root(conn: sqlite3.Connection, root_path: Path) -> int:
    """Ensure a folder path exists as an enabled indexed root and return its id."""
    root_path = root_path.expanduser().resolve()

    cursor = conn.execute("""
                          INSERT INTO indexed_roots (path)
                          VALUES (?)
                          ON CONFLICT(path) DO UPDATE SET
                              enabled = 1
                          RETURNING id
                          """,
                          (str(root_path),))

    return cursor.fetchone()["id"]


def mark_indexed_root_scanned(conn: sqlite3.Connection, root_id: int) -> None:
    """Record that an indexed root finished a scan."""
    conn.execute("""
                 UPDATE indexed_roots
                 SET last_scanned_at = CURRENT_TIMESTAMP
                 WHERE id = ?
                 """,
                 (root_id,))


def disable_indexed_root(connection_or_db_path: sqlite3.Connection | Path, root_id: int) -> int:
    """Disable an indexed root and orphan its active file locations."""
    if isinstance(connection_or_db_path, sqlite3.Connection):
        return disable_indexed_root_with_connection(connection_or_db_path, root_id)

    with connect(connection_or_db_path) as conn:
        return disable_indexed_root_with_connection(conn, root_id)


def disable_indexed_root_with_connection(conn: sqlite3.Connection, root_id: int) -> int:
    """Disable an indexed root using an existing database connection."""
    cursor = conn.execute("""
                          UPDATE indexed_roots
                          SET enabled = 0
                          WHERE id = ?
                          """,
                          (root_id,))
    if cursor.rowcount:
        mark_root_file_locations_orphaned(conn, root_id)

    return cursor.rowcount


def list_indexed_roots(db_path: Path) -> list[Path]:
    """Return all enabled indexed root paths."""
    with connect(db_path) as conn:
        rows = conn.execute("""
                            select path
                            from indexed_roots
                            where enabled = 1
                            order by path
                            """).fetchall()

    return [Path(row["path"]) for row in rows]
