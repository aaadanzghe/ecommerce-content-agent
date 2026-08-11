import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from src.config import ConfigurationError, MediaSettings
from src.inference.image_client import ImageClient, ImageConfig
from src.inference.image_client import ImageGenerationError
from src.inference.video_client import VideoClient, VideoConfig
from src.tasks import TaskStore


class FakeResponse:
    def __init__(self, status_code=200, body=None, content=b"", content_type="application/json"):
        self.status_code = status_code
        self._body = body
        self._content = content
        self.text = str(body) if body is not None else ""
        self.headers = {"Content-Type": content_type}

    def json(self):
        if self._body is None:
            raise ValueError("invalid json")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=8192):
        yield self._content


class ClientProtocolTests(unittest.TestCase):
    def test_seedream_upstream_error_is_structured(self):
        client = ImageClient(ImageConfig(backend="api", api_key="test", model="model"))
        response = FakeResponse(
            status_code=401,
            body={"error": {"code": "Unauthorized", "message": "invalid credential"}},
        )
        with patch("requests.post", return_value=response), self.assertRaises(ImageGenerationError) as caught:
            client.generate("prompt", save=False)
        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(caught.exception.error_code, "Unauthorized")

    def test_seedream_request_and_safe_download(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = ImageClient(ImageConfig(
                backend="api",
                api_key="test-key",
                model="seedream-model-id",
                output_dir=temp_dir,
            ))
            create_response = FakeResponse(body={
                "id": "image-1",
                "data": [{"url": "https://media.example/image.png"}],
            })
            download_response = FakeResponse(content=b"png-data", content_type="image/png")
            with patch("requests.post", return_value=create_response) as post, patch(
                "requests.get", return_value=download_response
            ):
                result = client.generate("product image", image_size="square")

            payload = post.call_args.kwargs["json"]
            self.assertEqual(payload["model"], "seedream-model-id")
            self.assertEqual(payload["size"], "1920x1920")
            self.assertEqual(Path(result["local_path"]).read_bytes(), b"png-data")
            self.assertFalse(Path(result["local_path"] + ".part").exists())

    def test_seedance_task_protocol_and_callback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = VideoClient(VideoConfig(
                backend="api",
                api_key="test-key",
                model="seedance-model-id",
                output_dir=temp_dir,
                poll_interval=1,
                max_wait=2,
            ))
            created = []
            create_response = FakeResponse(status_code=202, body={"id": "video-1"})
            query_response = FakeResponse(body={
                "id": "video-1",
                "status": "succeeded",
                "content": {"video_url": "https://media.example/video.mp4"},
            })
            download_response = FakeResponse(content=b"mp4-data", content_type="video/mp4")
            with patch("requests.post", return_value=create_response) as post, patch(
                "requests.get", side_effect=[query_response, download_response]
            ) as get, patch("src.inference.video_client.time.sleep", return_value=None):
                result = client.generate("product video", on_task_created=created.append)

            payload = post.call_args.kwargs["json"]
            self.assertEqual(payload["content"], [{"type": "text", "text": "product video"}])
            self.assertEqual(created, ["video-1"])
            self.assertIn("/contents/generations/tasks/video-1", get.call_args_list[0].args[0])
            self.assertEqual(Path(result["local_path"]).read_bytes(), b"mp4-data")

    def test_seedance_resume_does_not_submit_again(self):
        client = VideoClient(VideoConfig(
            backend="api",
            api_key="test-key",
            model="seedance-model-id",
            poll_interval=1,
            max_wait=2,
        ))
        query_response = FakeResponse(body={
            "status": "succeeded",
            "content": {"video_url": "https://media.example/video.mp4"},
        })
        with patch("requests.post") as post, patch(
            "requests.get", return_value=query_response
        ), patch("src.inference.video_client.time.sleep", return_value=None):
            result = client.generate("prompt", save=False, task_id="existing-task")
        post.assert_not_called()
        self.assertEqual(result["task_id"], "existing-task")


class ConfigurationTests(unittest.TestCase):
    def test_api_backend_requires_real_credentials_and_model(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {
            "IMAGE_BACKEND": "api",
            "SEEDREAM_API_KEY": "",
            "SEEDREAM_MODEL": "",
            "VIDEO_BACKEND": "",
            "MEDIA_OUTPUT_DIR": temp_dir,
        }, clear=False):
            settings = MediaSettings.from_env()
            with self.assertRaises(ConfigurationError):
                settings.validate()


class TaskStoreTests(unittest.TestCase):
    def test_running_task_is_recovered_without_losing_upstream_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TaskStore(Path(temp_dir) / "tasks.db")
            store.initialize()
            task = store.create("video", {"title": "test"})
            claimed = store.claim_next()
            self.assertEqual(claimed["status"], "running")
            store.set_upstream_task_id(task["id"], "upstream-1")

            recovered_store = TaskStore(Path(temp_dir) / "tasks.db")
            recovered_store.initialize(recover_running=True)
            recovered = recovered_store.get(task["id"])
            self.assertEqual(recovered["status"], "queued")
            self.assertEqual(recovered["upstream_task_id"], "upstream-1")


class ApiTests(unittest.TestCase):
    def test_async_video_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {
            "MODEL_BACKEND": "mock",
            "IMAGE_BACKEND": "mock",
            "VIDEO_BACKEND": "mock",
            "MEDIA_OUTPUT_DIR": temp_dir,
            "TASK_DB_PATH": str(Path(temp_dir) / "tasks.db"),
        }, clear=False):
            from src.api import server

            server._settings = None
            server._orchestrator = None
            server._task_store = None
            server._task_worker = None
            payload = {
                "title": "wireless earbuds",
                "category": "3c_digital",
                "platform": "taobao",
                "custom_video_prompt": "single custom prompt",
            }
            with TestClient(server.app) as client:
                response = client.post("/generate/video", json=payload)
                self.assertEqual(response.status_code, 202)
                task_id = response.json()["task_id"]
                deadline = time.time() + 5
                task = None
                while time.time() < deadline:
                    task = client.get(f"/tasks/{task_id}").json()
                    if task["status"] in {"succeeded", "failed"}:
                        break
                    threading.Event().wait(0.05)

                self.assertEqual(task["status"], "succeeded")
                self.assertEqual(task["result"]["video"]["video_prompt"], "single custom prompt")
                self.assertTrue(Path(task["result"]["video"]["local_path"]).exists())


if __name__ == "__main__":
    unittest.main()
