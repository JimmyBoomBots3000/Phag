"""Read queries for the browsable image library."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from phag.tags import normalize_tag_name


@dataclass(frozen=True)
class LibraryImage:
    """An image row shaped for grid/list display."""

    id: int
    content_hash: str
    width: int | None
    height: int | None
    mime_type: str
    file_size_bytes: int
    path: str
    path_relative: str
    modified_time: str
    date_taken: str | None
    small_thumbnail_path: str | None
    medium_thumbnail_path: str | None


SORT_COLUMNS = {
    "filename": "file_locations.path_relative",
    "date_modified": "file_locations.modified_time",
    "date_taken": "images.date_taken",
    "file_size": "images.file_size_bytes",
}


def list_library_images(
    connection: sqlite3.Connection,
    tag_names: list[str] | None = None,
    root_ids: list[int] | None = None,
    include_untagged: bool = False,
    tag_match: str = "and",
    sort_by: str = "filename",
    sort_direction: str = "asc",
    limit: int = 100,
    offset: int = 0,
) -> list[LibraryImage]:
    """Return active library images with optional tag filtering and sorting."""
    tag_names = tag_names or []
    root_ids = root_ids or []
    normalized_tags = [normalize_tag_name(tag_name) for tag_name in tag_names]
    normalized_tag_patterns = [f"{tag_name}/%" for tag_name in normalized_tags]
    sort_column = SORT_COLUMNS.get(sort_by)
    if sort_column is None:
        raise ValueError(f"Unsupported sort field: {sort_by}")
    if sort_direction not in {"asc", "desc"}:
        raise ValueError("sort_direction must be 'asc' or 'desc'")
    if tag_match not in {"and", "or"}:
        raise ValueError("tag_match must be 'and' or 'or'")

    params: list[object] = []
    where = ["file_locations.orphaned_at IS NULL"]
    if root_ids:
        root_placeholders = ", ".join("?" for _ in root_ids)
        where.append(f"file_locations.root_id IN ({root_placeholders})")
        params.extend(root_ids)

    untagged_filter = """
        NOT EXISTS (
            SELECT 1
            FROM image_tags
            WHERE image_tags.image_id = images.id
        )
    """

    if normalized_tags:
        tag_clauses = " OR ".join("tags.normalized_name = ? OR tags.normalized_name LIKE ?" for _ in normalized_tags)
        tag_params = [
            value
            for tag_name, tag_pattern in zip(normalized_tags, normalized_tag_patterns)
            for value in (tag_name, tag_pattern)
        ]
        if tag_match == "or":
            params.extend(tag_params)
            where.append(
                f"""
                (
                    images.id IN (
                        SELECT image_tags.image_id
                        FROM image_tags
                        JOIN tags ON tags.id = image_tags.tag_id
                        WHERE {tag_clauses}
                    )
                    {"OR " + untagged_filter if include_untagged else ""}
                )
                """
            )
        elif include_untagged:
            where.append("0 = 1")
        else:
            match_params = [
                value
                for tag_name, tag_pattern in zip(normalized_tags, normalized_tag_patterns)
                for value in (tag_name, tag_name, tag_pattern)
            ]
            params.extend(match_params)
            where.append(
                f"""
                images.id IN (
                    SELECT matched_tags.image_id
                    FROM (
                        {tag_filter_matches_sql(normalized_tags)}
                    ) AS matched_tags
                    GROUP BY matched_tags.image_id
                    HAVING COUNT(DISTINCT matched_filter) = ?
                )
                """
            )
            params.append(len(normalized_tags))
    elif include_untagged:
        where.append(untagged_filter)

    params.extend([limit, offset])
    direction_sql = sort_direction.upper()
    rows = connection.execute(
        f"""
        SELECT
            images.id,
            images.content_hash,
            images.width,
            images.height,
            images.mime_type,
            images.file_size_bytes,
            images.date_taken,
            file_locations.path,
            file_locations.path_relative,
            file_locations.modified_time,
            small_thumb.path AS small_thumbnail_path,
            medium_thumb.path AS medium_thumbnail_path
        FROM images
        JOIN file_locations ON file_locations.image_id = images.id
        LEFT JOIN thumbnails AS small_thumb
            ON small_thumb.image_id = images.id
           AND small_thumb.size_name = 'small'
        LEFT JOIN thumbnails AS medium_thumb
            ON medium_thumb.image_id = images.id
           AND medium_thumb.size_name = 'medium'
        WHERE {" AND ".join(where)}
        ORDER BY {sort_column} {direction_sql}, images.id ASC
        LIMIT ?
        OFFSET ?
        """,
        params,
    ).fetchall()

    return [
        LibraryImage(
            id=row["id"],
            content_hash=row["content_hash"],
            width=row["width"],
            height=row["height"],
            mime_type=row["mime_type"],
            file_size_bytes=row["file_size_bytes"],
            path=row["path"],
            path_relative=row["path_relative"],
            modified_time=row["modified_time"],
            date_taken=row["date_taken"],
            small_thumbnail_path=row["small_thumbnail_path"],
            medium_thumbnail_path=row["medium_thumbnail_path"],
        )
        for row in rows
    ]


def tag_filter_matches_sql(normalized_tags: list[str]) -> str:
    """Return SQL that maps each selected filter to matching image ids."""
    return "\nUNION ALL\n".join(
        """
        SELECT image_tags.image_id, ? AS matched_filter
        FROM image_tags
        JOIN tags ON tags.id = image_tags.tag_id
        WHERE tags.normalized_name = ? OR tags.normalized_name LIKE ?
        """
        for _ in normalized_tags
    )
