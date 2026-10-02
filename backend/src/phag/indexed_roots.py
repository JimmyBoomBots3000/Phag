"""Operations for folders configured as image indexing roots."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from phag.db import connect
from phag.file_locations import mark_root_file_locations_orphaned


@dataclass(frozen=True)
class IndexedRoot:
    """An enabled indexed root and its scan options."""

    id: int
    path: Path
    recursive: bool


@dataclass(frozen=True)
class RootOverlap:
    """A root that overlaps another root path."""

    id: int
    path: Path
    recursive: bool


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


def add_indexed_root(
    db_path: Path,
    root_path: Path,
    recursive: bool = True,
    replace_covered_roots: bool = False,
) -> int:
    """Register a folder path as an indexed root."""
    with connect(db_path) as conn:
        return add_indexed_root_with_connection(
            conn,
            root_path,
            recursive=recursive,
            replace_covered_roots=replace_covered_roots,
        )


def add_indexed_root_with_connection(
    conn: sqlite3.Connection,
    root_path: Path,
    recursive: bool = True,
    replace_covered_roots: bool = False,
) -> int:
    """Register a folder path using an existing database connection."""
    root_path = root_path.expanduser().resolve()
    validate_root_overlap(
        conn,
        root_path,
        recursive=recursive,
        replace_covered_roots=replace_covered_roots,
    )
    root_id = upsert_indexed_root(conn, root_path, recursive=recursive)
    if recursive and replace_covered_roots:
        disable_covered_roots(conn, root_path, excluding_root_id=root_id)
    return root_id


def upsert_indexed_root(conn: sqlite3.Connection, root_path: Path, recursive: bool = True) -> int:
    """Ensure a folder path exists as an enabled indexed root and return its id."""
    root_path = root_path.expanduser().resolve()

    cursor = conn.execute("""
                          INSERT INTO indexed_roots (path, recursive)
                          VALUES (?, ?)
                          ON CONFLICT(path) DO UPDATE SET
                              enabled = 1,
                              recursive = excluded.recursive
                          RETURNING id
                          """,
                          (str(root_path), int(recursive)))

    return cursor.fetchone()["id"]


def get_indexed_root_by_path(conn: sqlite3.Connection, root_path: Path) -> sqlite3.Row | None:
    """Return an indexed root row for an absolute path if one exists."""
    root_path = root_path.expanduser().resolve()
    return conn.execute("""
                        SELECT id, path, recursive, enabled, last_scanned_at
                        FROM indexed_roots
                        WHERE path = ?
                        """,
                        (str(root_path),)).fetchone()


def update_indexed_root_recursive(
    connection_or_db_path: sqlite3.Connection | Path,
    root_id: int,
    recursive: bool,
    replace_covered_roots: bool = False,
) -> int:
    """Update whether an indexed root should scan nested folders."""
    if isinstance(connection_or_db_path, sqlite3.Connection):
        return update_indexed_root_recursive_with_connection(
            connection_or_db_path,
            root_id,
            recursive,
            replace_covered_roots=replace_covered_roots,
        )

    with connect(connection_or_db_path) as conn:
        return update_indexed_root_recursive_with_connection(
            conn,
            root_id,
            recursive,
            replace_covered_roots=replace_covered_roots,
        )


def update_indexed_root_recursive_with_connection(
    conn: sqlite3.Connection,
    root_id: int,
    recursive: bool,
    replace_covered_roots: bool = False,
) -> int:
    """Update a root's recursive flag using an existing database connection."""
    existing_root = conn.execute("""
                                 SELECT id, path
                                 FROM indexed_roots
                                 WHERE id = ?
                                 """,
                                 (root_id,)).fetchone()
    if existing_root is None:
        return 0

    root_path = Path(existing_root["path"])
    validate_root_overlap(
        conn,
        root_path,
        recursive=recursive,
        replace_covered_roots=replace_covered_roots,
        excluding_root_id=root_id,
    )
    cursor = conn.execute("""
                          UPDATE indexed_roots
                          SET recursive = ?
                          WHERE id = ?
                          """,
                          (int(recursive), root_id))
    if cursor.rowcount and recursive and replace_covered_roots:
        disable_covered_roots(conn, root_path, excluding_root_id=root_id)
    return cursor.rowcount


def validate_root_overlap(
    conn: sqlite3.Connection,
    root_path: Path,
    recursive: bool,
    replace_covered_roots: bool = False,
    excluding_root_id: int | None = None,
) -> None:
    """Raise when a root overlaps existing enabled roots in an unsupported way."""
    covering_root = find_covering_recursive_root(conn, root_path, excluding_root_id)
    if covering_root is not None:
        raise ValueError(f"root_already_covered:{covering_root.id}")

    if recursive and find_covered_roots(conn, root_path, excluding_root_id) and not replace_covered_roots:
        raise ValueError("covered_roots_require_confirmation")


def find_covering_recursive_root(
    conn: sqlite3.Connection,
    root_path: Path,
    excluding_root_id: int | None = None,
) -> RootOverlap | None:
    """Return an enabled recursive parent root that already covers a path."""
    for root in iter_enabled_root_overlaps(conn, excluding_root_id):
        try:
            root_path.relative_to(root.path)
        except ValueError:
            continue
        if root.path != root_path and root.recursive:
            return root
    return None


def find_covered_roots(
    conn: sqlite3.Connection,
    root_path: Path,
    excluding_root_id: int | None = None,
) -> list[RootOverlap]:
    """Return enabled roots contained by a candidate parent path."""
    covered_roots: list[RootOverlap] = []
    for root in iter_enabled_root_overlaps(conn, excluding_root_id):
        try:
            root.path.relative_to(root_path)
        except ValueError:
            continue
        if root.path != root_path:
            covered_roots.append(root)
    return covered_roots


def disable_covered_roots(
    conn: sqlite3.Connection,
    root_path: Path,
    excluding_root_id: int | None = None,
) -> list[RootOverlap]:
    """Disable enabled roots contained by a recursive parent path."""
    covered_roots = find_covered_roots(conn, root_path, excluding_root_id)
    for root in covered_roots:
        disable_indexed_root_with_connection(conn, root.id)
    return covered_roots


def iter_enabled_root_overlaps(
    conn: sqlite3.Connection,
    excluding_root_id: int | None = None,
) -> list[RootOverlap]:
    """Return enabled roots for overlap checks."""
    rows = conn.execute("""
                        SELECT id, path, recursive
                        FROM indexed_roots
                        WHERE enabled = 1
                        ORDER BY length(path) DESC
                        """).fetchall()
    return [
        RootOverlap(
            id=row["id"],
            path=Path(row["path"]),
            recursive=bool(row["recursive"]),
        )
        for row in rows
        if excluding_root_id is None or row["id"] != excluding_root_id
    ]


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


def list_enabled_indexed_roots(db_path: Path) -> list[IndexedRoot]:
    """Return all enabled indexed roots with their scan options."""
    with connect(db_path) as conn:
        rows = conn.execute("""
                            SELECT id, path, recursive
                            FROM indexed_roots
                            WHERE enabled = 1
                            ORDER BY path
                            """).fetchall()

    return [
        IndexedRoot(
            id=row["id"],
            path=Path(row["path"]),
            recursive=bool(row["recursive"]),
        )
        for row in rows
    ]
