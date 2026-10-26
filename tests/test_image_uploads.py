from __future__ import annotations

import base64
import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from prompta.delivery_queue import DeliveryQueueStore
from prompta.image_store import ImageStore
from prompta.jobs import add_job, load_jobs
from prompta.web import PromptaJobServer

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZ0AAAAASUVORK5CYII="
)


def test_images_stay_on_disk_and_queue_retains_a_snapshot(tmp_path: Path) -> None:
    store = ImageStore(tmp_path)
    ref = store.save("example.png", base64.b64encode(PNG).decode())
    assert ref.endswith("/example.png")
    assert store.read(ref) == ("image/png", PNG)
    assert store.path(ref).stat().st_mode & 0o077 == 0

    jobs = tmp_path / "jobs.sqlite3"
    add_job(jobs, "photo", "What is in this image?", images=(ref,))
    assert load_jobs(jobs)["photo"].images == (ref,)
    queue = DeliveryQueueStore(tmp_path / "queue.sqlite3")
    receipt = queue.enqueue_manual("What is in this image?", images=(ref,))
    assert receipt["images"] == (ref,)
    assert queue.get(str(receipt["send_id"]))["images"] == (ref,)


@pytest.mark.parametrize("name,raw", [
    ("photo.png", "this-is-not-base64"),
    ("photo.png", base64.b64encode(b"<svg></svg>").decode()),
    ("photo.svg", base64.b64encode(PNG).decode()),
])
def test_invalid_images_are_rejected(tmp_path: Path, name: str, raw: str) -> None:
    with pytest.raises(ValueError):
        ImageStore(tmp_path).save(name, raw)


def test_web_image_upload_preview_and_job_submission(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite3"
    server = PromptaJobServer(("127.0.0.1", 0), state_path=database, jobs_path=database)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def post(path: str, payload: dict[str, object]) -> dict[str, object]:
        request = Request(
            base + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)
    try:
        uploaded = post("/api/images", {
            "name": "demo.png", "data": base64.b64encode(PNG).decode(),
        })["image"]
        assert isinstance(uploaded, dict)
        ref = uploaded["ref"]
        with urlopen(base + str(uploaded["url"]), timeout=5) as response:
            assert response.headers["Content-Type"] == "image/png"
            assert response.read() == PNG
        result = post("/api/jobs", {
            "action": "add", "name": "image-test", "prompt": "What colour?",
            "schedule": "once", "delay_minutes": 43200, "images": [ref],
        })
        assert result["ok"] is True
        assert load_jobs(database)["image-test"].images == (ref,)
        with pytest.raises(HTTPError) as exc:
            urlopen(base + "/api/images/../../etc/passwd", timeout=5)
        assert exc.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
