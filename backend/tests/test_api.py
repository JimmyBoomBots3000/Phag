from pathlib import Path
from threading import Event
from time import sleep

from fastapi.testclient import TestClient
from PIL import Image

import phag.scan_jobs as scan_jobs
from phag.api import app, get_settings
from phag.config import Settings
from phag.db import init_database
from phag.indexer import ScanCanceled


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


def test_root_can_be_added_as_non_recursive(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    nested_path = root_path / "nested"
    nested_path.mkdir(parents=True)
    create_image(root_path / "blue.png", (20, 30), "blue")
    create_image(nested_path / "red.png", (20, 30), "red")
    client = make_client(db_path)

    root_response = client.post("/roots", json={"path": str(root_path), "recursive": False})
    scan_response = client.post("/scans", json={})
    images_response = client.get("/images")

    assert root_response.status_code == 201
    assert root_response.json()["recursive"] is False
    assert scan_response.json()["discovered_count"] == 1
    assert [image["path_relative"] for image in images_response.json()] == ["blue.png"]


def test_root_recursive_setting_can_be_updated(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    nested_path = root_path / "nested"
    nested_path.mkdir(parents=True)
    create_image(root_path / "blue.png", (20, 30), "blue")
    create_image(nested_path / "red.png", (20, 30), "red")
    client = make_client(db_path)

    root = client.post("/roots", json={"path": str(root_path)}).json()
    recursive_scan_response = client.post("/scans", json={})
    update_response = client.patch(f"/roots/{root['id']}", json={"recursive": False})
    non_recursive_scan_response = client.post("/scans", json={"root_path": str(root_path)})
    images_response = client.get("/images")

    assert recursive_scan_response.json()["discovered_count"] == 2
    assert update_response.status_code == 200
    assert update_response.json()["recursive"] is False
    assert non_recursive_scan_response.json()["discovered_count"] == 1
    assert non_recursive_scan_response.json()["orphaned_count"] == 1
    assert [image["path_relative"] for image in images_response.json()] == ["blue.png"]


def test_child_root_under_recursive_parent_is_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    parent_path = tmp_path / "images"
    child_path = parent_path / "child"
    child_path.mkdir(parents=True)
    client = make_client(db_path)

    client.post("/roots", json={"path": str(parent_path), "recursive": True})
    response = client.post("/roots", json={"path": str(child_path), "recursive": True})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "root_already_covered"
    assert response.json()["detail"]["covering_root"]["path"] == str(parent_path.resolve())


def test_parent_root_can_replace_child_roots_after_confirmation(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    parent_path = tmp_path / "images"
    child_path = parent_path / "child"
    child_path.mkdir(parents=True)
    client = make_client(db_path)

    child_root = client.post("/roots", json={"path": str(child_path), "recursive": True}).json()
    conflict_response = client.post("/roots", json={"path": str(parent_path), "recursive": True})
    replace_response = client.post(
        "/roots",
        json={"path": str(parent_path), "recursive": True, "replace_covered_roots": True},
    )
    all_roots_response = client.get("/roots", params={"include_disabled": "true"})

    assert conflict_response.status_code == 409
    assert conflict_response.json()["detail"]["code"] == "covered_roots_require_confirmation"
    assert conflict_response.json()["detail"]["covered_roots"][0]["id"] == child_root["id"]
    assert replace_response.status_code == 201
    assert {root["path"]: root["enabled"] for root in all_roots_response.json()} == {
        str(child_path.resolve()): False,
        str(parent_path.resolve()): True,
    }


def test_non_recursive_parent_can_have_child_root(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    parent_path = tmp_path / "images"
    child_path = parent_path / "child"
    child_path.mkdir(parents=True)
    client = make_client(db_path)

    parent_response = client.post("/roots", json={"path": str(parent_path), "recursive": False})
    child_response = client.post("/roots", json={"path": str(child_path), "recursive": True})

    assert parent_response.status_code == 201
    assert child_response.status_code == 201


def test_making_parent_recursive_can_replace_child_roots_after_confirmation(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    parent_path = tmp_path / "images"
    child_path = parent_path / "child"
    child_path.mkdir(parents=True)
    client = make_client(db_path)

    parent_root = client.post("/roots", json={"path": str(parent_path), "recursive": False}).json()
    child_root = client.post("/roots", json={"path": str(child_path), "recursive": True}).json()
    conflict_response = client.patch(f"/roots/{parent_root['id']}", json={"recursive": True})
    replace_response = client.patch(
        f"/roots/{parent_root['id']}",
        json={"recursive": True, "replace_covered_roots": True},
    )
    all_roots_response = client.get("/roots", params={"include_disabled": "true"})

    assert conflict_response.status_code == 409
    assert conflict_response.json()["detail"]["code"] == "covered_roots_require_confirmation"
    assert conflict_response.json()["detail"]["covered_roots"][0]["id"] == child_root["id"]
    assert replace_response.status_code == 200
    assert replace_response.json()["recursive"] is True
    assert {root["path"]: root["enabled"] for root in all_roots_response.json()} == {
        str(child_path.resolve()): False,
        str(parent_path.resolve()): True,
    }


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


def test_images_can_filter_by_root(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    create_image(first_root / "blue.png", (20, 30), "blue")
    create_image(second_root / "red.png", (20, 30), "red")
    client = make_client(db_path)

    first_root_response = client.post("/roots", json={"path": str(first_root)})
    second_root_response = client.post("/roots", json={"path": str(second_root)})
    client.post("/scans", json={})
    first_images_response = client.get("/images", params={"root_id": first_root_response.json()["id"]})
    both_images_response = client.get(
        "/images",
        params=[
            ("root_id", first_root_response.json()["id"]),
            ("root_id", second_root_response.json()["id"]),
        ],
    )

    assert [image["path_relative"] for image in first_images_response.json()] == ["blue.png"]
    assert [image["path_relative"] for image in both_images_response.json()] == ["blue.png", "red.png"]


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
    assert any(scan_job["id"] == job["id"] for scan_job in client.get("/scan-jobs").json())

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


def test_scan_jobs_can_be_canceled(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "phag.db"
    started = Event()
    client = make_client(db_path)

    def wait_until_canceled(db_path, progress_callback=None, cancellation_callback=None):
        started.set()
        while not cancellation_callback():
            sleep(0.01)
        raise ScanCanceled

    monkeypatch.setattr(scan_jobs, "index_roots_with_progress", wait_until_canceled)

    running_job = client.post("/scan-jobs", json={}).json()
    assert started.wait(timeout=1)
    queued_job = client.post("/scan-jobs", json={}).json()

    cancel_queued_response = client.delete(f"/scan-jobs/{queued_job['id']}")
    cancel_all_response = client.delete("/scan-jobs")
    unknown_response = client.delete("/scan-jobs/not-a-real-job")

    assert cancel_queued_response.status_code == 200
    assert cancel_queued_response.json()["status"] == "canceled"
    assert cancel_all_response.status_code == 200
    assert unknown_response.status_code == 404

    for _ in range(20):
        running_status = client.get(f"/scan-jobs/{running_job['id']}").json()
        if running_status["status"] == "canceled":
            break
        sleep(0.05)

    assert running_status["status"] == "canceled"


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


def test_thumbnail_and_image_file_routes(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    root_path.mkdir()
    create_image(root_path / "blue.png", (20, 30), "blue")
    client = make_client(db_path)

    client.post("/roots", json={"path": str(root_path)})
    client.post("/scans", json={})
    image = client.get("/images").json()[0]

    thumbnail_response = client.get(f"/{image['small_thumbnail_path']}")
    image_file_response = client.get(f"/images/{image['id']}/file")

    assert thumbnail_response.status_code == 200
    assert image_file_response.status_code == 200
    assert thumbnail_response.headers["content-type"] == "image/webp"


def test_image_can_be_moved_to_indexed_folder_and_keeps_tags(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    destination_path = root_path / "sorted"
    destination_path.mkdir(parents=True)
    source_path = root_path / "blue.png"
    create_image(source_path, (20, 30), "blue")
    client = make_client(db_path)

    client.post("/roots", json={"path": str(root_path), "recursive": True})
    client.post("/scans", json={})
    image = client.get("/images").json()[0]
    client.post(f"/images/{image['id']}/tags", json={"name": "color/blue"})

    response = client.post(
        f"/images/{image['id']}/move",
        json={"destination_directory": str(destination_path)},
    )
    moved_images = client.get("/images").json()
    tags = client.get(f"/images/{image['id']}/tags").json()

    assert response.status_code == 200
    assert not source_path.exists()
    assert (destination_path / "blue.png").is_file()
    assert response.json()["path_relative"] == "sorted/blue.png"
    assert response.json()["indexed"] is True
    assert moved_images[0]["path_relative"] == "sorted/blue.png"
    assert tags[0]["display_name"] == "color/blue"


def test_image_move_rejects_unindexed_destination(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    destination_path = tmp_path / "outside"
    root_path.mkdir()
    destination_path.mkdir()
    create_image(root_path / "blue.png", (20, 30), "blue")
    client = make_client(db_path)

    client.post("/roots", json={"path": str(root_path), "recursive": True})
    client.post("/scans", json={})
    image = client.get("/images").json()[0]

    response = client.post(
        f"/images/{image['id']}/move",
        json={"destination_directory": str(destination_path)},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Destination is not inside an indexed folder"
    assert (root_path / "blue.png").is_file()


def test_image_move_can_allow_unindexed_destination(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    destination_path = tmp_path / "outside"
    source_path = root_path / "blue.png"
    root_path.mkdir()
    destination_path.mkdir()
    create_image(source_path, (20, 30), "blue")
    client = make_client(db_path)

    client.post("/roots", json={"path": str(root_path), "recursive": True})
    client.post("/scans", json={})
    image = client.get("/images").json()[0]
    client.post(f"/images/{image['id']}/tags", json={"name": "color/blue"})

    response = client.post(
        f"/images/{image['id']}/move",
        json={"destination_directory": str(destination_path), "allow_unindexed": True},
    )
    images_response = client.get("/images")
    tags_response = client.get(f"/images/{image['id']}/tags")

    assert response.status_code == 200
    assert response.json()["indexed"] is False
    assert response.json()["root_id"] is None
    assert response.json()["path_relative"] is None
    assert not source_path.exists()
    assert (destination_path / "blue.png").is_file()
    assert images_response.json() == []
    assert tags_response.json()[0]["display_name"] == "color/blue"


def test_image_move_rejects_existing_destination_file(tmp_path: Path) -> None:
    db_path = tmp_path / "phag.db"
    root_path = tmp_path / "images"
    destination_path = root_path / "sorted"
    destination_path.mkdir(parents=True)
    source_path = root_path / "blue.png"
    create_image(source_path, (20, 30), "blue")
    create_image(destination_path / "blue.png", (20, 30), "red")
    client = make_client(db_path)

    client.post("/roots", json={"path": str(root_path), "recursive": True})
    client.post("/scans", json={})
    image = next(image for image in client.get("/images").json() if image["path_relative"] == "blue.png")

    response = client.post(
        f"/images/{image['id']}/move",
        json={"destination_directory": str(destination_path)},
    )

    assert response.status_code == 409
    assert source_path.is_file()
