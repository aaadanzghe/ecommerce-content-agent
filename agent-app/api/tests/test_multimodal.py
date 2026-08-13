import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from ecommerce_agent.settings.runtime import ConfigurationError, MediaSettings
from ecommerce_agent.providers.image_client import ImageClient, ImageConfig
from ecommerce_agent.providers.image_client import ImageGenerationError
from ecommerce_agent.providers.video_client import VideoClient, VideoConfig
from ecommerce_api.infrastructure.tasks import TaskStore


class FakePackage:
    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return dict(self.payload)


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
                create_url="https://create.example/tasks",
                query_url="https://query.example/tasks",
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
            ) as get, patch("ecommerce_agent.providers.video_client.time.sleep", return_value=None):
                result = client.generate("product video", on_task_created=created.append)

            payload = post.call_args.kwargs["json"]
            self.assertEqual(post.call_args.args[0], "https://create.example/tasks")
            self.assertEqual(payload["content"], [{"type": "text", "text": "product video"}])
            self.assertEqual(created, ["video-1"])
            self.assertEqual(get.call_args_list[0].args[0], "https://query.example/tasks/video-1")
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
        ), patch("ecommerce_agent.providers.video_client.time.sleep", return_value=None):
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
    def test_model_settings_update_never_returns_api_keys(self):
        """Runtime settings accept secrets but expose only configured flags."""
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {
            "MODEL_BACKEND": "mock", "IMAGE_BACKEND": "mock", "VIDEO_BACKEND": "mock",
            "MEDIA_OUTPUT_DIR": temp_dir, "TASK_DB_PATH": str(Path(temp_dir) / "tasks.db"),
        }, clear=False):
            from ecommerce_api import main as server
            server._settings = None
            server._orchestrator = None
            server._task_store = None
            server._task_worker = None
            server._runtime_model_overrides.clear()
            with TestClient(server.app) as client:
                payload = client.get("/settings/models").json()
                payload["text"]["api_key"] = "secret-text-key"
                payload["image"]["api_key"] = "secret-image-key"
                payload["video"]["api_key"] = "secret-video-key"
                response = client.put("/settings/models", json=payload)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertNotIn("secret-", str(body))
                for provider in body.values():
                    self.assertNotIn("api_key", provider)
                self.assertTrue(body["text"]["api_key_configured"])
                self.assertTrue(body["image"]["api_key_configured"])
                self.assertTrue(body["video"]["api_key_configured"])

    def test_video_settings_accept_separate_query_url_and_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {
            "MODEL_BACKEND": "mock", "IMAGE_BACKEND": "mock", "VIDEO_BACKEND": "mock",
            "MEDIA_OUTPUT_DIR": temp_dir, "TASK_DB_PATH": str(Path(temp_dir) / "tasks.db"),
        }, clear=False):
            from ecommerce_api import main as server
            server._settings = None
            server._orchestrator = None
            server._task_store = None
            server._task_worker = None
            server._runtime_model_overrides.clear()
            with TestClient(server.app) as client:
                payload = client.get("/settings/models").json()
                payload["video"].update({
                    "backend": "api",
                    "model": "seedance",
                    "api_url": "https://create.example/tasks",
                    "query_url": "https://query.example/tasks",
                    "api_key": "video-key",
                })
                response = client.put("/settings/models", json=payload)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["video"]["api_url"], "https://create.example/tasks")
                self.assertEqual(response.json()["video"]["query_url"], "https://query.example/tasks")

                payload = response.json()
                payload["video"]["query_url"] = ""
                response = client.put("/settings/models", json=payload)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["video"]["query_url"], "https://create.example/tasks")

    def test_invalid_platform_and_tone_return_422(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {
            "MODEL_BACKEND": "mock", "IMAGE_BACKEND": "mock", "VIDEO_BACKEND": "mock",
            "MEDIA_OUTPUT_DIR": temp_dir, "TASK_DB_PATH": str(Path(temp_dir) / "tasks.db"),
        }, clear=False):
            from ecommerce_api import main as server
            server._settings = None
            server._orchestrator = None
            server._task_store = None
            server._task_worker = None
            with TestClient(server.app) as client:
                self.assertEqual(client.post("/generate", json={"title": "x", "platform": "bad"}).status_code, 422)
                self.assertEqual(client.post("/generate", json={"title": "x", "tone": "bad"}).status_code, 422)

    def test_media_route_and_placeholder_url(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {
            "MODEL_BACKEND": "mock", "IMAGE_BACKEND": "mock", "VIDEO_BACKEND": "mock",
            "MEDIA_OUTPUT_DIR": temp_dir, "TASK_DB_PATH": str(Path(temp_dir) / "tasks.db"),
        }, clear=False):
            from ecommerce_api import main as server
            server._settings = None
            server._orchestrator = None
            server._task_store = None
            server._task_worker = None
            image_dir = Path(temp_dir) / "image"
            image_dir.mkdir()
            (image_dir / "preview.png").write_bytes(b"png-data")
            with TestClient(server.app) as client:
                response = client.get("/media/image/preview.png")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, b"png-data")
                self.assertEqual(client.get("/media/image/missing.png").status_code, 404)
                self.assertEqual(client.get("/media/audio/preview.png").status_code, 404)
                self.assertEqual(client.get("/media/image/preview.png.placeholder").status_code, 404)
                decorated = server._decorate_media({"image": {
                    "local_path": str(image_dir / "mock.png.placeholder")
                }})
                self.assertIsNone(decorated["image"]["media_url"])

    def test_async_video_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {
            "MODEL_BACKEND": "mock",
            "IMAGE_BACKEND": "mock",
            "VIDEO_BACKEND": "mock",
            "MEDIA_OUTPUT_DIR": temp_dir,
            "TASK_DB_PATH": str(Path(temp_dir) / "tasks.db"),
        }, clear=False):
            from ecommerce_api import main as server

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
                self.assertGreaterEqual(response.json()["poll_timeout_seconds"], 301)
                self.assertIn("execution", task["result"])
                self.assertNotIn("key", str(server.get_task_store().get(task_id)["request"]).lower())

    def test_queued_task_uses_execution_snapshot_after_hot_switch(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {
            "MODEL_BACKEND": "mock",
            "IMAGE_BACKEND": "mock",
            "VIDEO_BACKEND": "mock",
            "MEDIA_OUTPUT_DIR": temp_dir,
            "TASK_DB_PATH": str(Path(temp_dir) / "tasks.db"),
            "VIDEO_MAX_WAIT": "10",
        }, clear=False):
            from ecommerce_api import main as server
            server._settings = None
            server._orchestrator = None
            server._task_store = None
            server._task_worker = None
            server._runtime_model_overrides.clear()
            server.initialize_runtime()
            server._runtime_model_overrides.update({
                "MODEL_BACKEND": "api",
                "MODEL_NAME": "created-model",
                "API_BASE": "https://created.example/v1",
                "VIDEO_BACKEND": "api",
                "SEEDANCE_MODEL": "created-video",
                "SEEDANCE_CREATE_URL": "https://created.example/create",
                "SEEDANCE_QUERY_URL": "https://created.example/query",
                "SEEDANCE_API_KEY": "current-video-key",
            })
            settings = server._effective_media_settings()
            request = {"title": "x", "_execution_snapshot": server._execution_snapshot(settings)}
            server._runtime_model_overrides.update({
                "MODEL_NAME": "switched-model",
                "SEEDANCE_MODEL": "switched-video",
                "SEEDANCE_CREATE_URL": "https://switched.example/create",
                "SEEDANCE_QUERY_URL": "https://switched.example/query",
            })

            captured = {}

            class FakeOrchestrator:
                image_agent = object()
                video_agent = object()

                def __init__(self, settings, text_snapshot):
                    captured["text"] = dict(text_snapshot)
                    captured["video_model"] = settings.seedance_model
                    captured["create_url"] = settings.seedance_create_url
                    captured["query_url"] = settings.seedance_query_url

                def generate(self, *args, **kwargs):
                    return FakePackage({"optimized_title": "ok", "selling_points": [], "description": "", "seo_keywords": [], "social_copy": "", "platform": "taobao"})

            with patch.object(server, "_build_orchestrator", side_effect=lambda settings, text_snapshot=None: FakeOrchestrator(settings, text_snapshot or {})):
                result = server._execute_task({"id": "task-1", "kind": "video", "request": request, "upstream_task_id": ""})

            self.assertEqual(captured["text"]["model"], "created-model")
            self.assertEqual(captured["video_model"], "created-video")
            self.assertEqual(captured["create_url"], "https://created.example/create")
            self.assertEqual(captured["query_url"], "https://created.example/query")
            self.assertEqual(result["execution"]["text"]["model"], "created-model")

    def test_transformers_is_rejected_from_runtime_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {
            "MODEL_BACKEND": "mock", "IMAGE_BACKEND": "mock", "VIDEO_BACKEND": "mock",
            "MEDIA_OUTPUT_DIR": temp_dir, "TASK_DB_PATH": str(Path(temp_dir) / "tasks.db"),
        }, clear=False):
            from ecommerce_api import main as server
            server._settings = None
            server._orchestrator = None
            server._task_store = None
            server._task_worker = None
            server._runtime_model_overrides.clear()
            with TestClient(server.app) as client:
                payload = client.get("/settings/models").json()
                payload["text"]["backend"] = "transformers"
                self.assertEqual(client.put("/settings/models", json=payload).status_code, 422)

    def test_transformers_readiness_validates_model_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {
            "MODEL_BACKEND": "transformers",
            "MODEL_PATH": str(Path(temp_dir) / "missing-model"),
            "IMAGE_BACKEND": "mock",
            "VIDEO_BACKEND": "mock",
            "MEDIA_OUTPUT_DIR": temp_dir,
            "TASK_DB_PATH": str(Path(temp_dir) / "tasks.db"),
        }, clear=False):
            from ecommerce_api import main as server
            server._settings = None
            server._orchestrator = None
            server._task_store = None
            server._task_worker = None
            server._runtime_model_overrides.clear()
            with TestClient(server.app) as client:
                response = client.get("/ready")
                self.assertEqual(response.status_code, 503)
                self.assertIn("MODEL_PATH", response.text)


if __name__ == "__main__":
    unittest.main()

