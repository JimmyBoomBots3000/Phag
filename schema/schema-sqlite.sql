PRAGMA foreign_keys = ON;

-- Image Tagger initial SQLite schema.
--
-- Time fields are stored as UTC ISO-8601 text unless noted otherwise.
-- Paths are stored as text and should be normalized by application code before insert.

CREATE TABLE indexed_roots (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    recursive INTEGER NOT NULL DEFAULT 1 CHECK (recursive IN (0, 1)),
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

CREATE TABLE file_locations (
    id INTEGER PRIMARY KEY,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    root_id INTEGER NOT NULL REFERENCES indexed_roots(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    path_relative TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL CHECK (file_size_bytes >= 0),
    modified_time TEXT NOT NULL,
    created_time TEXT,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    orphaned_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (root_id, path_relative)
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

CREATE TABLE thumbnails (
    id INTEGER PRIMARY KEY,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    size_name TEXT NOT NULL CHECK (size_name IN ('small', 'medium')),
    path TEXT NOT NULL,
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    format TEXT NOT NULL,
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (image_id, size_name)
);

CREATE TABLE scan_events (
    id INTEGER PRIMARY KEY,
    root_id INTEGER REFERENCES indexed_roots(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    path TEXT,
    image_id INTEGER REFERENCES images(id) ON DELETE SET NULL,
    details_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_images_last_seen_at ON images(last_seen_at);
CREATE INDEX idx_file_locations_image_id ON file_locations(image_id);
CREATE INDEX idx_file_locations_root_id ON file_locations(root_id);
CREATE INDEX idx_file_locations_orphaned_at ON file_locations(orphaned_at);
CREATE INDEX idx_file_locations_scan_cache
    ON file_locations(root_id, path_relative, file_size_bytes, modified_time);
CREATE INDEX idx_tags_display_name ON tags(display_name);
CREATE INDEX idx_image_tags_tag_id ON image_tags(tag_id);
CREATE INDEX idx_thumbnails_image_id ON thumbnails(image_id);
CREATE INDEX idx_scan_events_root_created ON scan_events(root_id, created_at);

CREATE TRIGGER indexed_roots_touch_updated_at
AFTER UPDATE ON indexed_roots
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE indexed_roots SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER images_touch_updated_at
AFTER UPDATE ON images
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE images SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER file_locations_touch_updated_at
AFTER UPDATE ON file_locations
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE file_locations SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER tags_touch_updated_at
AFTER UPDATE ON tags
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE tags SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
