from __future__ import annotations

import base64
import json
import os
import shutil
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import pytest
from live_server import LiveServer
from patchright.sync_api import sync_playwright as sync_patchright

from prompta.delivery_queue import DeliveryQueueStore
from prompta.image_store import ImageStore
from prompta.jobs import add_job, load_jobs

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
    queued = queue.get(str(receipt["send_id"]))
    assert queued is not None
    assert queued["images"] == (ref,)


@pytest.mark.parametrize("name,raw", [
    ("photo.png", "this-is-not-base64"),
    ("photo.png", base64.b64encode(b"<svg></svg>").decode()),
    ("photo.svg", base64.b64encode(PNG).decode()),
])
def test_invalid_images_are_rejected(tmp_path: Path, name: str, raw: str) -> None:
    with pytest.raises(ValueError):
        ImageStore(tmp_path).save(name, raw)


MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"
MOV = b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00"
WEBM = b"\x1a\x45\xdf\xa3\x9f\x42\x82\x84webm"


@pytest.mark.parametrize(
    "name,mime,data",
    [
        ("clip.mp4", "video/mp4", MP4),
        ("clip.mov", "video/quicktime", MOV),
        ("clip.webm", "video/webm", WEBM),
    ],
)
def test_video_files_are_stored_with_verified_media_types(
    tmp_path: Path, name: str, mime: str, data: bytes,
) -> None:
    store = ImageStore(tmp_path)
    ref = store.save(name, base64.b64encode(data).decode())
    assert store.read(ref) == (mime, data)
    assert store.path(ref).stat().st_mode & 0o077 == 0
    with pytest.raises(ValueError, match="extension"):
        store.save("wrong.png", base64.b64encode(data).decode())


def test_video_upload_size_limit_and_spoofed_media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import prompta.image_store as image_store

    store = ImageStore(tmp_path)
    with pytest.raises(ValueError, match="Unsupported"):
        store.save("fake.mp4", base64.b64encode(b"<svg></svg>").decode())
    monkeypatch.setattr(image_store, "MAX_VIDEO_BYTES", len(MP4) - 1)
    with pytest.raises(ValueError, match="50 MiB"):
        store.save("clip.mp4", base64.b64encode(MP4).decode())


def test_video_upload_http_and_fresh_chat_receipt(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite3"
    server = LiveServer(("127.0.0.1", 0), state_path=database, jobs_path=database)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def post(path: str, payload: dict[str, object]) -> dict[str, object]:
        request = Request(
            base + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urlopen(request, timeout=5) as response:
            return object_map(json.load(response))

    try:
        video = object_map(post("/api/videos", {
            "name": "sample.mp4", "data": base64.b64encode(MP4).decode(),
        })["image"])
        ref = video["ref"]
        assert isinstance(ref, str)
        with urlopen(base + "/api/images/" + ref, timeout=5) as response:
            assert response.headers["Content-Type"] == "video/mp4"
            assert response.read() == MP4
        receipt = post("/api/chats", {
            "request_id": "1" * 32, "prompt": "Describe the attached clip", "images": [ref],
        })
        assert receipt["ok"] is True
        with urlopen(base + "/api/chats/requests/" + "1" * 32, timeout=5) as response:
            assert object_map(json.load(response))["send_id"] == receipt["send_id"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def object_map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    parsed: dict[str, object] = {}
    for key, item in value.items():
        assert isinstance(key, str)
        parsed[key] = item
    return parsed


def test_web_image_upload_preview_and_job_submission(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite3"
    server = LiveServer(("127.0.0.1", 0), state_path=database, jobs_path=database)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def post(path: str, payload: dict[str, object]) -> dict[str, object]:
        request = Request(
            base + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urlopen(request, timeout=5) as response:
            return object_map(json.load(response))
    try:
        uploaded = object_map(post("/api/images", {
            "name": "demo.png", "data": base64.b64encode(PNG).decode(),
        })["image"])
        ref = uploaded["ref"]
        url = uploaded["url"]
        assert isinstance(ref, str)
        assert isinstance(url, str)
        assert url.startswith("./api/images/")
        assert urljoin("https://example.test/private/", url).startswith(
            "https://example.test/private/api/images/"
        )
        with urlopen(urljoin(base + "/", url), timeout=5) as response:
            assert response.headers["Content-Type"] == "image/png"
            assert response.read() == PNG
        result = post("/api/jobs", {
            "action": "add", "name": "image-test", "prompt": "What colour?",
            "schedule": "once", "delay_minutes": 43200, "images": [ref],
        })
        assert result["ok"] is True
        assert load_jobs(database)["image-test"].images == (ref,)
        job_rows = result["jobs"]
        assert isinstance(job_rows, list)
        jobs = [object_map(row) for row in job_rows]
        saved_job = next(job for job in jobs if job["name"] == "image-test")
        images = saved_job["images"]
        assert isinstance(images, list)
        saved_image = object_map(images[0])
        assert saved_image["url"] == url
        with pytest.raises(HTTPError) as exc:
            urlopen(base + "/api/images/../../etc/passwd", timeout=5)
        assert exc.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_video_attachment_composer_preview_in_browser(tmp_path: Path) -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM") or shutil.which("chromium")
    if chromium is None:
        pytest.skip("Chromium is not installed")
    database = tmp_path / "runtime.sqlite3"
    server = LiveServer(("127.0.0.1", 0), state_path=database, jobs_path=database)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_patchright() as patchright:
            browser = patchright.chromium.launch(
                headless=True, executable_path=chromium, args=["--no-sandbox"],
            )
            try:
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.goto(f"http://127.0.0.1:{server.server_port}/?view=chats&draft=new")
                field = page.locator('input[type="file"][accept*="video/mp4"]')
                field.set_input_files({
                    "name": "clip.mp4", "mimeType": "video/mp4", "buffer": MP4,
                })
                page.get_by_label("Attachments to send").locator("video").wait_for()
                assert page.get_by_label("Attachments to send").locator("video").count() == 1
                assert page.get_by_role("button", name="Remove clip.mp4").count() == 1
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_mobile_image_previews_do_not_hide_under_footer(tmp_path: Path) -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM") or shutil.which("chromium")
    if chromium is None:
        pytest.skip("Chromium is not installed")

    database = tmp_path / "runtime.sqlite3"
    files = [tmp_path / f"preview-{index}.png" for index in range(4)]
    for file in files:
        file.write_bytes(PNG)

    server = LiveServer(("127.0.0.1", 0), state_path=database, jobs_path=database)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_patchright() as patchright:
            browser = patchright.chromium.launch(
                headless=True, executable_path=chromium, args=["--no-sandbox"]
            )
            try:
                page = browser.new_page(viewport={"width": 320, "height": 568})
                page.goto(f"http://127.0.0.1:{server.server_port}/?view=jobs")
                page.get_by_role("button", name="Run once").first.click()
                page.locator("textarea").fill("Check four image previews")
                page.locator('input[type="file"]').set_input_files(files)
                page.locator(".job-image-preview").nth(3).wait_for()
                page.wait_for_timeout(1000)
                metrics = page.evaluate(
                    """() => ({
                        lastBottom: document.querySelector(".job-image-preview:last-child").getBoundingClientRect().bottom,
                        footerTop: document.querySelector(".editor-footer").getBoundingClientRect().top,
                        objectFit: getComputedStyle(document.querySelector(".job-image-preview img")).objectFit,
                        horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
                    })"""
                )
                assert metrics["lastBottom"] <= metrics["footerTop"]
                assert metrics["objectFit"] == "contain"
                assert metrics["horizontalOverflow"] is False
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
