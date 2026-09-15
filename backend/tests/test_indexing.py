from pathlib import Path

from PIL import Image

from phag.db import connect, init_database
from phag.indexer import index_path
from phag.library import list_library_images
from phag.tags import add_tag_to_image, create_tag


def create_image(path: Path, size: tuple[int, int], color: str) -> None:
    Image.new("RGB", size, color).save(path)


def test_index_path_persists_images_locations_and_thumbnails(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    root_path.mkdir()
    create_image(root_path / "blue.png", (20, 30), "blue")
    create_image(root_path / "red.jpg", (32, 24), "red")

    init_database(db_path)
    summary = index_path(db_path, root_path)

    assert summary.discovered_count == 2
    assert summary.indexed_count == 2
    assert summary.skipped_count == 0
    assert summary.orphaned_count == 0
    assert summary.thumbnail_count == 4

    with connect(db_path) as connection:
        image_count = connection.execute("SELECT COUNT(*) FROM images").fetchone()[0]
        location_count = connection.execute("SELECT COUNT(*) FROM file_locations").fetchone()[0]
        thumbnail_rows = connection.execute(
            """
            SELECT path
            FROM thumbnails
            ORDER BY path
            """
        ).fetchall()

    assert image_count == 2
    assert location_count == 2
    assert len(thumbnail_rows) == 4
    for row in thumbnail_rows:
        assert (tmp_path / row["path"]).is_file()


def test_index_path_skips_unchanged_images(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    root_path.mkdir()
    create_image(root_path / "blue.png", (20, 30), "blue")

    init_database(db_path)
    first_summary = index_path(db_path, root_path)
    second_summary = index_path(db_path, root_path)

    assert first_summary.indexed_count == 1
    assert first_summary.thumbnail_count == 2
    assert second_summary.discovered_count == 1
    assert second_summary.indexed_count == 0
    assert second_summary.skipped_count == 1
    assert second_summary.thumbnail_count == 0


def test_library_images_can_filter_by_tag(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    root_path.mkdir()
    create_image(root_path / "blue.png", (20, 30), "blue")
    create_image(root_path / "red.jpg", (32, 24), "red")

    init_database(db_path)
    index_path(db_path, root_path)

    with connect(db_path) as connection:
        blue_id = connection.execute(
            """
            SELECT images.id
            FROM images
            JOIN file_locations ON file_locations.image_id = images.id
            WHERE file_locations.path_relative = 'blue.png'
            """
        ).fetchone()["id"]
        tag_id = create_tag(connection, "people/alice")
        add_tag_to_image(connection, blue_id, tag_id)
        tagged_images = list_library_images(connection, tag_names=["PEOPLE/ALICE"])

    assert len(tagged_images) == 1
    assert tagged_images[0].id == blue_id
    assert tagged_images[0].path_relative == "blue.png"
