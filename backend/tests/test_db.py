import sqlite3
from pathlib import Path

from phag.db import CURRENT_SCHEMA_VERSION, connect, ensure_database, init_database


def create_old_database_without_recursive(db_path: Path) -> None:
    """Create a pre-recursive-root database shape with representative user data."""
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE indexed_roots (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_scanned_at TEXT,
                UNIQUE (path)
            );

            CREATE TABLE images (
                id INTEGER PRIMARY KEY,
                content_hash TEXT NOT NULL,
                hash_algorithm TEXT NOT NULL DEFAULT 'sha256',
                width INTEGER CHECK (width IS NULL OR width > 0),
                height INTEGER CHECK (height IS NULL OR height > 0),
                mime_type TEXT NOT NULL,
                file_size_bytes INTEGER NOT NULL CHECK (file_size_bytes >= 0),
                date_taken TEXT,
                exif_json TEXT,
                first_indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (hash_algorithm, content_hash)
            );

            CREATE TABLE tags (
                id INTEGER PRIMARY KEY,
                display_name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK (length(trim(display_name)) > 0),
                CHECK (length(trim(normalized_name)) > 0),
                UNIQUE (normalized_name)
            );

            CREATE TABLE image_tags (
                image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
                tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (image_id, tag_id)
            );

            INSERT INTO indexed_roots (id, path) VALUES (1, '/tmp/photos');
            INSERT INTO images (
                id,
                content_hash,
                width,
                height,
                mime_type,
                file_size_bytes
            )
            VALUES (1, 'abc123', 20, 30, 'image/png', 123);
            INSERT INTO tags (id, display_name, normalized_name)
            VALUES (1, 'people/alice', 'people/alice');
            INSERT INTO image_tags (image_id, tag_id) VALUES (1, 1);
            """
        )


def test_ensure_database_migrates_old_database_without_losing_user_data(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    create_old_database_without_recursive(db_path)

    ensure_database(db_path)

    with connect(db_path) as connection:
        root = connection.execute("SELECT path, recursive FROM indexed_roots").fetchone()
        tag = connection.execute("SELECT display_name FROM tags").fetchone()
        image_tag_count = connection.execute("SELECT COUNT(*) FROM image_tags").fetchone()[0]
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert root["path"] == "/tmp/photos"
    assert root["recursive"] == 1
    assert tag["display_name"] == "people/alice"
    assert image_tag_count == 1
    assert user_version == CURRENT_SCHEMA_VERSION
    assert len(list(tmp_path.glob("phag.db.backup-*"))) == 1


def test_ensure_database_is_idempotent_for_migrated_database(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    create_old_database_without_recursive(db_path)

    ensure_database(db_path)
    ensure_database(db_path)

    with connect(db_path) as connection:
        root_count = connection.execute("SELECT COUNT(*) FROM indexed_roots").fetchone()[0]
        recursive_values = [
            row["recursive"]
            for row in connection.execute("SELECT recursive FROM indexed_roots").fetchall()
        ]

    assert root_count == 1
    assert recursive_values == [1]
    assert len(list(tmp_path.glob("phag.db.backup-*"))) == 1


def test_ensure_database_creates_new_database_at_current_version(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"

    ensure_database(db_path)

    with connect(db_path) as connection:
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        root_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(indexed_roots)").fetchall()
        }

    assert user_version == CURRENT_SCHEMA_VERSION
    assert "recursive" in root_columns


def test_ensure_database_rejects_existing_non_phag_database(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    db_path.touch()

    try:
        ensure_database(db_path)
    except RuntimeError as exc:
        assert str(exc) == "Database is missing required table: indexed_roots"
    else:
        raise AssertionError("Expected ensure_database to reject an empty existing database")


def test_init_database_marks_schema_version(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"

    init_database(db_path)

    with connect(db_path) as connection:
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert user_version == CURRENT_SCHEMA_VERSION
