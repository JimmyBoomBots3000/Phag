from pathlib import Path
from time import sleep

from fastapi.testclient import TestClient
from PIL import Image

from phag.api import app, get_settings
from phag.config import Settings
from phag.db import init_database


def create_image(path: Path, size: tuple[int, int], color: str) -> None:
    Image.new("RGB", size, color).save(path)


def make_client(db_path: Path) -> TestClient:
    init_database(db_path)
    app.dependency_overrides[get_settings] = lambda: Settings(db_path=db_path)
    return TestClient(app)


def test_health(tmp_path: Path) -> None:
    client = make_client(tmp_path / "phag.db")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_and_docs_are_available(tmp_path: Path) -> None:
    client = make_client(tmp_path / "phag.db")

    openapi_response = client.get("/openapi.json")
    docs_response = client.get("/docs")

    assert openapi_response.status_code == 200
    assert openapi_response.json()["info"]["title"] == "Phag API"
    assert "/images" in openapi_response.json()["paths"]
    assert docs_response.status_code == 200


def test_roots_scan_images_and_tags(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    root_path.mkdir()
    create_image(root_path / "blue.png", (20, 30), "blue")
    client = make_client(db_path)

    root_response = client.post("/roots", json={"path": str(root_path)})
    scan_response = client.post("/scans", json={})
    images_response = client.get("/images")
    tag_response = client.post("/images/1/tags", json={"name": "people/alice"})
    filtered_response = client.get("/images", params={"tag": "PEOPLE/ALICE"})

    assert root_response.status_code == 201
    assert scan_response.status_code == 200
    assert scan_response.json()["indexed_count"] == 1
    assert scan_response.json()["thumbnail_count"] == 2
    assert images_response.status_code == 200
    assert images_response.json()[0]["path_relative"] == "blue.png"
    assert tag_response.status_code == 201
    assert filtered_response.status_code == 200
    assert len(filtered_response.json()) == 1


def test_images_can_filter_to_untagged(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    root_path.mkdir()
    create_image(root_path / "blue.png", (20, 30), "blue")
    create_image(root_path / "red.png", (20, 30), "red")
    client = make_client(db_path)

    client.post("/roots", json={"path": str(root_path)})
    client.post("/scans", json={})
    client.post("/images/1/tags", json={"name": "people/alice"})
    untagged_response = client.get("/images", params={"include_untagged": "true"})
    tagged_or_untagged_response = client.get(
        "/images",
        params={"tag": "people/alice", "tag_match": "or", "include_untagged": "true"},
    )
    tagged_and_untagged_response = client.get(
        "/images",
        params={"tag": "people/alice", "tag_match": "and", "include_untagged": "true"},
    )

    assert [image["path_relative"] for image in untagged_response.json()] == ["red.png"]
    assert [image["path_relative"] for image in tagged_or_untagged_response.json()] == ["blue.png", "red.png"]
    assert tagged_and_untagged_response.json() == []


def test_scan_job_can_be_queued_and_polled(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    root_path.mkdir()
    create_image(root_path / "blue.png", (20, 30), "blue")
    client = make_client(db_path)

    client.post("/roots", json={"path": str(root_path)})
    create_response = client.post("/scan-jobs", json={})

    assert create_response.status_code == 202
    job = create_response.json()
    assert job["status"] in {"queued", "running", "completed"}

    for _ in range(20):
        poll_response = client.get(f"/scan-jobs/{job['id']}")
        assert poll_response.status_code == 200
        job = poll_response.json()
        if job["status"] == "completed":
            break
        sleep(0.05)

    assert job["status"] == "completed"
    assert job["current_path"] == str(root_path)
    assert job["summary"]["indexed_count"] == 1
    assert client.get("/images").json()[0]["path_relative"] == "blue.png"


def test_tags_can_be_renamed_and_deleted(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    root_path.mkdir()
    create_image(root_path / "blue.png", (20, 30), "blue")
    client = make_client(db_path)

    client.post("/roots", json={"path": str(root_path)})
    client.post("/scans", json={})
    tag_response = client.post("/images/1/tags", json={"name": "people/alice"})
    tag_id = tag_response.json()["tag_id"]

    rename_response = client.patch(f"/tags/{tag_id}", json={"name": "people/alicia"})
    tags_response = client.get("/images/1/tags")
    delete_response = client.delete(f"/tags/{tag_id}")
    deleted_tags_response = client.get("/images/1/tags")

    assert rename_response.status_code == 200
    assert rename_response.json() == {"id": tag_id, "name": "people/alicia"}
    assert tags_response.json()[0]["display_name"] == "people/alicia"
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted_count": 1}
    assert deleted_tags_response.json() == []


def test_unused_tags_are_deleted_after_untagging(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    root_path.mkdir()
    create_image(root_path / "blue.png", (20, 30), "blue")
    client = make_client(db_path)

    client.post("/roots", json={"path": str(root_path)})
    client.post("/scans", json={})
    tag_response = client.post("/images/1/tags", json={"name": "people/alice"})
    tag_id = tag_response.json()["tag_id"]

    untag_response = client.delete(f"/images/1/tags/{tag_id}")
    tags_response = client.get("/tags")

    assert untag_response.status_code == 200
    assert untag_response.json() == {"removed_count": 1, "deleted_tag_count": 1}
    assert tags_response.json() == []


def test_root_can_be_removed(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    root_path.mkdir()
    create_image(root_path / "blue.png", (20, 30), "blue")
    client = make_client(db_path)

    root = client.post("/roots", json={"path": str(root_path)}).json()
    client.post("/scans", json={})
    client.post("/images/1/tags", json={"name": "people/alice"})
    delete_response = client.delete(f"/roots/{root['id']}")
    roots_response = client.get("/roots")
    all_roots_response = client.get("/roots", params={"include_disabled": "true"})
    images_response = client.get("/images")
    tags_response = client.get("/tags")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"removed_count": 1, "deleted_tag_count": 1}
    assert roots_response.json() == []
    assert all_roots_response.json()[0]["enabled"] == 0
    assert images_response.json() == []
    assert tags_response.json() == []


def test_filesystem_directory_browser(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    child_path = root_path / "child"
    child_path.mkdir(parents=True)
    (root_path / "file.txt").write_text("not a directory", encoding="utf-8")
    (root_path / ".hidden").mkdir()
    (root_path / "node_modules").mkdir()
    (root_path / "Example.app").mkdir()
    client = make_client(db_path)

    response = client.get("/filesystem/directories", params={"path": str(root_path)})

    assert response.status_code == 200
    assert response.json()["path"] == str(root_path)
    assert response.json()["directories"] == [str(child_path)]


def test_thumbnail_and_original_routes(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    root_path.mkdir()
    create_image(root_path / "blue.png", (20, 30), "blue")
    client = make_client(db_path)

    client.post("/roots", json={"path": str(root_path)})
    client.post("/scans", json={})
    image = client.get("/images").json()[0]

    thumbnail_response = client.get(f"/{image['small_thumbnail_path']}")
    original_response = client.get(f"/originals/{image['id']}")

    assert thumbnail_response.status_code == 200
    assert original_response.status_code == 200
    assert thumbnail_response.headers["content-type"] == "image/webp"
