"""FastAPI service for text, image, and asynchronous video generation."""

import logging
import os
import threading
from dataclasses import replace
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from ecommerce_api.schemas import (
    GenerateAllRequest,
    GenerateImageRequest,
    GenerateRequest,
    GenerateResponse,
    GenerateVideoRequest,
    TaskAccepted,
    TaskResponse,
    ModelSettingsResponse,
    ModelSettingsUpdate,
    ProviderSettings,
)

_env_path = Path(__file__).resolve().parents[4] / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from ecommerce_agent.agents.orchestrator import ContentOrchestrator
from ecommerce_agent.settings.runtime import ConfigurationError, MediaSettings, get_env
from ecommerce_agent.providers.image_client import ImageConfig, create_image_client, get_mock_image_client
from ecommerce_agent.providers.model_client import ModelConfig, create_client, get_mock_client
from ecommerce_agent.providers.video_client import VideoConfig, create_video_client, get_mock_video_client
from ecommerce_agent.domain.models import ProductProfile
from ecommerce_api.infrastructure.tasks import TaskStore, TaskWorker

logging.basicConfig(
    level=get_env("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

_settings: Optional[MediaSettings] = None
_orchestrator: Optional[ContentOrchestrator] = None
_task_store: Optional[TaskStore] = None
_task_worker: Optional[TaskWorker] = None
_runtime_model_overrides: dict[str, str] = {}
_runtime_lock = threading.RLock()
CONFIG_SNAPSHOT_VERSION = 1



def _poll_timeout_seconds(settings: Optional[MediaSettings] = None) -> int:
    settings = settings or _effective_media_settings()
    return settings.max_wait + 300


def _configured_text(key: str, default: str = "") -> str:
    return _runtime_model_overrides.get(key, get_env(key, default))


def _validate_text_runtime(backend: str, model_path: str = "", lora_path: str = "") -> None:
    if backend not in {"mock", "api", "vllm", "transformers"}:
        raise ConfigurationError("MODEL_BACKEND must be mock, api, vllm, or transformers")
    if backend != "transformers":
        return
    if not model_path or not Path(model_path).is_dir():
        raise ConfigurationError("MODEL_PATH must be an existing directory when MODEL_BACKEND is transformers")
    if lora_path and not Path(lora_path).is_dir():
        raise ConfigurationError("LORA_PATH must be an existing directory when MODEL_BACKEND is transformers")


def _build_orchestrator(settings: MediaSettings, text_snapshot: Optional[dict] = None) -> ContentOrchestrator:
    """Build provider clients using runtime overrides before environment defaults."""
    def configured(key: str, default: str = "") -> str:
        """Read an in-memory setting first, then fall back to the environment."""
        return _runtime_model_overrides.get(key, get_env(key, default))

    text_snapshot = text_snapshot or {}
    backend = str(text_snapshot.get("backend") or configured("MODEL_BACKEND", "mock")).lower()
    model_path = get_env("MODEL_PATH")
    lora_path = get_env("LORA_PATH")
    _validate_text_runtime(backend, model_path, lora_path)
    if backend == "mock":
        model_client = get_mock_client()
    else:
        model_client = create_client(ModelConfig(
            backend=backend,
            model_name=text_snapshot.get("model") or configured("MODEL_NAME", "ecommerce-copywriter"),
            api_base=text_snapshot.get("api_base") or configured("API_BASE", "http://localhost:8000/v1"),
            api_key=configured("API_KEY", "not-needed"),
            model_path=model_path,
            lora_path=lora_path,
            temperature=float(text_snapshot.get("temperature") or get_env("TEMPERATURE", "0.7")),
            top_p=float(text_snapshot.get("top_p") or get_env("TOP_P", "0.9")),
            max_tokens=int(text_snapshot.get("max_tokens") or get_env("MAX_TOKENS", "1024")),
        ))

    image_client = None
    if settings.image_backend == "mock":
        image_client = get_mock_image_client()
        image_client.config.output_dir = str(settings.output_dir / "image")
    elif settings.image_backend == "api":
        image_client = create_image_client(ImageConfig(
            backend="api",
            api_url=settings.seedream_api_url,
            api_key=settings.seedream_api_key,
            model=settings.seedream_model,
            image_size=settings.image_size,
            output_dir=str(settings.output_dir / "image"),
        ))

    video_client = None
    if settings.video_backend == "mock":
        video_client = get_mock_video_client()
        video_client.config.output_dir = str(settings.output_dir / "video")
    elif settings.video_backend == "api":
        video_client = create_video_client(VideoConfig(
            backend="api",
            create_url=settings.seedance_create_url,
            query_url=settings.seedance_query_url,
            api_key=settings.seedance_api_key,
            model=settings.seedance_model,
            duration=settings.video_duration,
            resolution=settings.video_resolution,
            ratio=settings.video_ratio,
            poll_interval=settings.poll_interval,
            max_wait=settings.max_wait,
            output_dir=str(settings.output_dir / "video"),
        ))

    return ContentOrchestrator(
        model_client,
        max_rewrite_rounds=int(get_env("MAX_REWRITE_ROUNDS", "2")),
        image_client=image_client,
        video_client=video_client,
    )


def initialize_runtime() -> None:
    """Initialize singleton runtime services once for the application process."""
    global _settings, _orchestrator, _task_store, _task_worker
    if _settings is not None:
        return
    settings = _effective_media_settings()
    _validate_text_runtime(_configured_text("MODEL_BACKEND", "mock").lower(), get_env("MODEL_PATH"), get_env("LORA_PATH"))
    settings.validate()
    store = TaskStore(settings.task_db_path)
    store.initialize(recover_running=True)
    _settings = settings
    _task_store = store
    _orchestrator = _build_orchestrator(settings)
    _task_worker = TaskWorker(store, _execute_task)


def _effective_media_settings() -> MediaSettings:
    """Build media settings with in-memory overrides layered over environment values."""
    settings = MediaSettings.from_env()
    values = settings.__dict__.copy()
    mapping = {
        "IMAGE_BACKEND": "image_backend", "SEEDREAM_API_URL": "seedream_api_url",
        "SEEDREAM_API_KEY": "seedream_api_key", "SEEDREAM_MODEL": "seedream_model",
        "VIDEO_BACKEND": "video_backend", "SEEDANCE_CREATE_URL": "seedance_create_url",
        "SEEDANCE_QUERY_URL": "seedance_query_url", "SEEDANCE_API_KEY": "seedance_api_key",
        "SEEDANCE_MODEL": "seedance_model",
    }
    for key, field_name in mapping.items():
        if key in _runtime_model_overrides:
            values[field_name] = _runtime_model_overrides[key]
    return MediaSettings(**values)


def _execution_snapshot(settings: MediaSettings) -> dict:
    return {
        "version": CONFIG_SNAPSHOT_VERSION,
        "text": {
            "backend": _configured_text("MODEL_BACKEND", "mock").lower(),
            "model": _configured_text("MODEL_NAME", "ecommerce-copywriter"),
            "api_base": _configured_text("API_BASE", "http://localhost:8000/v1"),
            "temperature": float(get_env("TEMPERATURE", "0.7")),
            "top_p": float(get_env("TOP_P", "0.9")),
            "max_tokens": int(get_env("MAX_TOKENS", "1024")),
        },
        "image": {
            "backend": settings.image_backend,
            "model": settings.seedream_model,
            "api_url": settings.seedream_api_url,
            "image_size": settings.image_size,
        },
        "video": {
            "backend": settings.video_backend,
            "model": settings.seedance_model,
            "create_url": settings.seedance_create_url,
            "query_url": settings.seedance_query_url,
            "duration": settings.video_duration,
            "resolution": settings.video_resolution,
            "ratio": settings.video_ratio,
            "poll_interval": settings.poll_interval,
            "max_wait": settings.max_wait,
        },
    }


def _settings_from_snapshot(snapshot: dict) -> MediaSettings:
    current = _effective_media_settings()
    image = snapshot.get("image", {}) if isinstance(snapshot, dict) else {}
    video = snapshot.get("video", {}) if isinstance(snapshot, dict) else {}
    return replace(
        current,
        image_backend=image.get("backend", current.image_backend),
        seedream_api_url=image.get("api_url", current.seedream_api_url),
        seedream_model=image.get("model", current.seedream_model),
        image_size=image.get("image_size", current.image_size),
        video_backend=video.get("backend", current.video_backend),
        seedance_create_url=video.get("create_url", current.seedance_create_url),
        seedance_query_url=video.get("query_url") or video.get("create_url") or current.seedance_query_url,
        seedance_model=video.get("model", current.seedance_model),
        video_duration=int(video.get("duration", current.video_duration)),
        video_resolution=video.get("resolution", current.video_resolution),
        video_ratio=video.get("ratio", current.video_ratio),
        poll_interval=int(video.get("poll_interval", current.poll_interval)),
        max_wait=int(video.get("max_wait", current.max_wait)),
    )


def _execution_metadata(snapshot: dict) -> dict:
    text = snapshot.get("text", {}) if isinstance(snapshot, dict) else {}
    image = snapshot.get("image", {}) if isinstance(snapshot, dict) else {}
    video = snapshot.get("video", {}) if isinstance(snapshot, dict) else {}
    return {
        "config_version": snapshot.get("version", 0) if isinstance(snapshot, dict) else 0,
        "text": {"backend": text.get("backend", ""), "model": text.get("model", "")},
        "image": {"backend": image.get("backend", ""), "model": image.get("model", "")},
        "video": {"backend": video.get("backend", ""), "model": video.get("model", "")},
    }


def _execute_task(task: dict) -> dict:
    request = dict(task["request"])
    snapshot = request.pop("_execution_snapshot", None)
    product = ProductProfile.from_dict(request)
    kind = task["kind"]
    generate_image = kind == "all"
    generate_video = kind in {"video", "all"}
    orchestrator = get_orchestrator()
    if snapshot:
        settings = _settings_from_snapshot(snapshot)
        settings.validate()
        orchestrator = _build_orchestrator(settings, snapshot.get("text", {}))
    package = orchestrator.generate(
        product,
        generate_image=generate_image,
        generate_video=generate_video,
        custom_image_prompt=request.get("custom_image_prompt", ""),
        custom_video_prompt=request.get("custom_video_prompt", ""),
        upstream_video_task_id=task.get("upstream_task_id") or "",
        on_video_task_created=lambda upstream_id: get_task_store().set_upstream_task_id(task["id"], upstream_id),
    )
    result = package.to_dict()
    if snapshot:
        result["execution"] = _execution_metadata(snapshot)
    return result


def get_orchestrator() -> ContentOrchestrator:
    if _orchestrator is None:
        initialize_runtime()
    return _orchestrator


def get_task_store() -> TaskStore:
    if _task_store is None:
        initialize_runtime()
    return _task_store


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        initialize_runtime()
    except (ConfigurationError, OSError):
        logger.exception("Runtime initialization failed; readiness will report the configuration error")
    if _task_worker:
        _task_worker.start()
    try:
        yield
    finally:
        if _task_worker:
            _task_worker.stop()


app = FastAPI(
    title="电商内容生成 Agent",
    description="多平台文案、图片及异步视频生成服务",
    version="0.5.0",
    lifespan=lifespan,
)


def _cors_origins() -> list[str]:
    raw = get_env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _media_url(kind: str, local_path: str) -> Optional[str]:
    if not local_path or local_path.endswith(".placeholder"):
        return None
    candidate = Path(local_path)
    if _settings is None:
        initialize_runtime()
    root = (_settings.output_dir / kind).resolve()
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return f"/media/{kind}/{resolved.name}" if resolved.is_file() else None


def _decorate_media(result: Optional[dict]) -> Optional[dict]:
    if not result:
        return result
    decorated = dict(result)
    for kind in ("image", "video"):
        media = decorated.get(kind)
        if isinstance(media, dict):
            media = dict(media)
            media["media_url"] = _media_url(kind, str(media.get("local_path", "")))
            decorated[kind] = media
    return decorated


def _task_payload(task: dict) -> dict:
    snapshot = task.get("request", {}).get("_execution_snapshot", {})
    video_snapshot = snapshot.get("video", {}) if isinstance(snapshot, dict) else {}
    poll_timeout = int(video_snapshot.get("max_wait", 0) or _effective_media_settings().max_wait) + 300
    return {
        "task_id": task["id"],
        "kind": task["kind"],
        "status": task["status"],
        "status_url": f"/tasks/{task['id']}",
        "poll_timeout_seconds": poll_timeout,
        "result": _decorate_media(task.get("result")),
        "error": task.get("error"),
        "upstream_task_id": task.get("upstream_task_id"),
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
    }


def _raise_generation_error(exc: Exception) -> None:
    logger.exception("Generation request failed")
    upstream_status = getattr(exc, "status_code", None)
    response_status = status.HTTP_502_BAD_GATEWAY if upstream_status else status.HTTP_500_INTERNAL_SERVER_ERROR
    raise HTTPException(response_status, detail={
        "type": type(exc).__name__,
        "message": str(exc),
        "upstream_status": upstream_status,
        "upstream_code": getattr(exc, "error_code", ""),
    }) from exc


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.5.0"}


@app.get("/ready")
async def ready():
    try:
        initialize_runtime()
        get_task_store().initialize()
        return {
            "status": "ready",
            "image_backend": _settings.image_backend or "disabled",
            "video_backend": _settings.video_backend or "disabled",
            "text_backend": _configured_text("MODEL_BACKEND", "mock"),
        }
    except (ConfigurationError, OSError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def _settings_payload() -> ModelSettingsResponse:
    """Return effective settings while exposing only credential presence flags."""
    settings = _effective_media_settings()
    configured = lambda key, default="": _runtime_model_overrides.get(key, get_env(key, default))
    text_backend = configured("MODEL_BACKEND", "mock")
    text_managed = text_backend == "transformers" and "MODEL_BACKEND" not in _runtime_model_overrides
    return ModelSettingsResponse(
        text=ProviderSettings(
            backend=text_backend,
            model=configured("MODEL_NAME", "ecommerce-copywriter"),
            api_url=configured("API_BASE", "http://localhost:8000/v1"),
            api_key_configured=bool(configured("API_KEY")),
            managed_by_env=text_managed,
        ),
        image=ProviderSettings(
            backend=settings.image_backend or "disabled",
            model=settings.seedream_model,
            api_url=settings.seedream_api_url,
            api_key_configured=bool(settings.seedream_api_key),
        ),
        video=ProviderSettings(
            backend=settings.video_backend or "disabled",
            model=settings.seedance_model,
            api_url=settings.seedance_create_url,
            query_url=settings.seedance_query_url,
            api_key_configured=bool(settings.seedance_api_key),
        ),
    )


@app.get("/settings/models", response_model=ModelSettingsResponse)
async def get_model_settings():
    """Read current model endpoints and masked credential state."""
    return _settings_payload()


@app.put("/settings/models", response_model=ModelSettingsResponse)
async def update_model_settings(update: ModelSettingsUpdate):
    """Validate and atomically apply process-local model provider settings.

    Blank API keys retain existing credentials. Settings live only in memory and
    revert to environment/code defaults when FastAPI restarts.
    """
    global _settings, _orchestrator
    allowed_text = {"mock", "api", "vllm"}
    allowed_media = {"disabled", "mock", "api"}
    current = _settings_payload()
    text_managed = current.text.managed_by_env
    if not text_managed and update.text.backend not in allowed_text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported text backend")
    if text_managed and update.text.backend != "transformers":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Transformers text backend is managed by environment")
    if update.image.backend not in allowed_media or update.video.backend not in allowed_media:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported media backend")

    candidate = {
        "IMAGE_BACKEND": "" if update.image.backend == "disabled" else update.image.backend,
        "SEEDREAM_MODEL": update.image.model.strip(),
        "SEEDREAM_API_URL": update.image.api_url.strip(),
        "VIDEO_BACKEND": "" if update.video.backend == "disabled" else update.video.backend,
        "SEEDANCE_MODEL": update.video.model.strip(),
        "SEEDANCE_CREATE_URL": update.video.api_url.strip(),
        "SEEDANCE_QUERY_URL": (update.video.query_url or update.video.api_url).strip(),
    }
    if not text_managed:
        candidate.update({
            "MODEL_BACKEND": update.text.backend,
            "MODEL_NAME": update.text.model.strip(),
            "API_BASE": update.text.api_url.strip(),
        })
    if update.text.api_key and not text_managed:
        candidate["API_KEY"] = update.text.api_key.strip()
    if update.image.api_key:
        candidate["SEEDREAM_API_KEY"] = update.image.api_key.strip()
    if update.video.api_key:
        candidate["SEEDANCE_API_KEY"] = update.video.api_key.strip()

    with _runtime_lock:
        previous = dict(_runtime_model_overrides)
        try:
            _runtime_model_overrides.update(candidate)
            settings = _effective_media_settings()
            _validate_text_runtime(_configured_text("MODEL_BACKEND", "mock").lower(), get_env("MODEL_PATH"), get_env("LORA_PATH"))
            settings.validate()
            orchestrator = _build_orchestrator(settings)
        except (ConfigurationError, ValueError) as exc:
            _runtime_model_overrides.clear()
            _runtime_model_overrides.update(previous)
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        _settings = settings
        _orchestrator = orchestrator
    return _settings_payload()


@app.get("/media/{kind}/{filename}")
async def media_file(kind: str, filename: str):
    if kind not in {"image", "video"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media kind not found")
    if not filename or filename != Path(filename).name or filename.endswith(".placeholder"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media file not found")
    if _settings is None:
        initialize_runtime()
    root = (_settings.output_dir / kind).resolve()
    target = (root / filename).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media file not found") from exc
    if not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media file not found")
    return FileResponse(target)


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    try:
        package = await run_in_threadpool(
            get_orchestrator().generate,
            ProductProfile.from_dict(req.model_dump()),
        )
        return GenerateResponse(**_decorate_media(package.to_dict()))
    except Exception as exc:
        _raise_generation_error(exc)


@app.post("/generate/image", response_model=GenerateResponse)
async def generate_image(req: GenerateImageRequest):
    orchestrator = get_orchestrator()
    if orchestrator.image_agent is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Image backend is disabled")
    try:
        package = await run_in_threadpool(
            orchestrator.generate,
            ProductProfile.from_dict(req.model_dump()),
            False,
            True,
            req.custom_image_prompt,
        )
        return GenerateResponse(**_decorate_media(package.to_dict()))
    except Exception as exc:
        _raise_generation_error(exc)


def _enqueue(kind: str, request: dict) -> TaskAccepted:
    orchestrator = get_orchestrator()
    if orchestrator.video_agent is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Video backend is disabled")
    if kind == "all" and orchestrator.image_agent is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Image backend is disabled")
    settings = _effective_media_settings()
    request["_execution_snapshot"] = _execution_snapshot(settings)
    task = get_task_store().create(kind, request)
    return TaskAccepted(
        task_id=task["id"],
        kind=task["kind"],
        status=task["status"],
        status_url=f"/tasks/{task['id']}",
        poll_timeout_seconds=_poll_timeout_seconds(settings),
    )


@app.post("/generate/video", response_model=TaskAccepted, status_code=status.HTTP_202_ACCEPTED)
async def generate_video(req: GenerateVideoRequest):
    return _enqueue("video", req.model_dump())


@app.post("/generate/all", response_model=TaskAccepted, status_code=status.HTTP_202_ACCEPTED)
async def generate_all(req: GenerateAllRequest):
    return _enqueue("all", req.model_dump())


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    task = get_task_store().get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return TaskResponse(**_task_payload(task))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=get_env("API_HOST", "127.0.0.1"),
        port=int(get_env("API_PORT", "8888")),
    )



