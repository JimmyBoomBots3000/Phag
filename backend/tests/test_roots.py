from pathlib import Path

from phag.db import init_database
from phag.indexed_roots import add_indexed_root, list_indexed_roots


def test_add_and_list_indexed_roots(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    root_path.mkdir()

    init_database(db_path)
    root_id = add_indexed_root(db_path, root_path)

    assert root_id == 1
    assert list_indexed_roots(db_path) == [root_path.resolve()]
