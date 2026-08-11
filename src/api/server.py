"""FastAPI service for text, image, and asynchronous video generation."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from src.agents.orchestrator import ContentOrchestrator
from src.config import ConfigurationError, MediaSettings, get_env
from src.inference.image_client import ImageConfig, create_image_client, get_mock_image_client
from src.inference.model_client import ModelConfig, create_client, get_mock_client
from src.inference.video_client import VideoConfig, create_video_client, get_mock_video_client
from src.schemas import ProductProfile
from src.tasks import TaskStore, TaskWorker

logging.basicConfig(
    level=get_env("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

_settings: Optional[MediaSettings] = None
_orchestrator: Optional[ContentOrchestrator] = None
_task_store: Optional[TaskStore] = None
_task_worker: Optional[TaskWorker] = None


class GenerateRequest(BaseModel):
    title: str = Field(..., min_length=1, description="商品标题")
    category: str = Field("other", description="商品品类")
    attributes: dict = Field(default_factory=dict, description="商品属性")
    selling_points: list = Field(default_factory=list, description="卖点")
    target_audience: str = ""
    price_positioning: str = ""
    platform: str = "taobao"
    tone: str = "professional"
    constraints: list = Field(default_factory=list)


class GenerateVideoRequest(GenerateRequest):
    custom_video_prompt: str = ""


class GenerateImageRequest(GenerateRequest):
    custom_image_prompt: str = ""


class GenerateAllRequest(GenerateRequest):
    custom_image_prompt: str = ""
    custom_video_prompt: str = ""


class GenerateResponse(BaseModel):
    optimized_title: str
    selling_points: list
    description: str
    seo_keywords: list
    social_copy: str
    quality_score: dict
    rewrite_reason: str
    rewrite_history: list
    platform: str
    image: Optional[dict] = None
    video: Optional[dict] = None


class TaskAccepted(BaseModel):
    task_id: str
    kind: str
    status: str
    status_url: str


class TaskResponse(TaskAccepted):
    result: Optional[dict] = None
    error: Optional[dict] = None
    upstream_task_id: Optional[str] = None
    created_at: str
    updated_at: str


def _build_orchestrator(settings: MediaSettings) -> ContentOrchestrator:
    backend = get_env("MODEL_BACKEND", "mock").lower()
    if backend == "mock":
        model_client = get_mock_client()
    else:
        model_client = create_client(ModelConfig(
            backend=backend,
            model_name=get_env("MODEL_NAME", "ecommerce-copywriter"),
            api_base=get_env("API_BASE", "http://localhost:8000/v1"),
            api_key=get_env("API_KEY", "not-needed"),
            model_path=get_env("MODEL_PATH"),
            lora_path=get_env("LORA_PATH"),
            temperature=float(get_env("TEMPERATURE", "0.7")),
            top_p=float(get_env("TOP_P", "0.9")),
            max_tokens=int(get_env("MAX_TOKENS", "1024")),
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
    global _settings, _orchestrator, _task_store, _task_worker
    if _settings is not None:
        return
    settings = MediaSettings.from_env()
    settings.validate()
    store = TaskStore(settings.task_db_path)
    store.initialize(recover_running=True)
    _settings = settings
    _task_store = store
    _orchestrator = _build_orchestrator(settings)
    _task_worker = TaskWorker(store, _execute_task)


def _execute_task(task: dict) -> dict:
    request = dict(task["request"])
    product = ProductProfile.from_dict(request)
    kind = task["kind"]
    generate_image = kind == "all"
    generate_video = kind in {"video", "all"}
    package = get_orchestrator().generate(
        product,
        generate_image=generate_image,
        generate_video=generate_video,
        custom_image_prompt=request.get("custom_image_prompt", ""),
        custom_video_prompt=request.get("custom_video_prompt", ""),
        upstream_video_task_id=task.get("upstream_task_id") or "",
        on_video_task_created=lambda upstream_id: get_task_store().set_upstream_task_id(task["id"], upstream_id),
    )
    return package.to_dict()


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
    initialize_runtime()
    _task_worker.start()
    try:
        yield
    finally:
        if _task_worker:
            _task_worker.stop()


app = FastAPI(
    title="电商内容生产 Agent",
    description="多平台文案、图片及异步视频生成服务",
    version="0.5.0",
    lifespan=lifespan,
)


def _task_payload(task: dict) -> dict:
    return {
        "task_id": task["id"],
        "kind": task["kind"],
        "status": task["status"],
        "status_url": f"/tasks/{task['id']}",
        "result": task.get("result"),
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
        }
    except (ConfigurationError, OSError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    try:
        package = await run_in_threadpool(
            get_orchestrator().generate,
            ProductProfile.from_dict(req.model_dump()),
        )
        return GenerateResponse(**package.to_dict())
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
        return GenerateResponse(**package.to_dict())
    except Exception as exc:
        _raise_generation_error(exc)


def _enqueue(kind: str, request: dict) -> TaskAccepted:
    orchestrator = get_orchestrator()
    if orchestrator.video_agent is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Video backend is disabled")
    if kind == "all" and orchestrator.image_agent is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Image backend is disabled")
    task = get_task_store().create(kind, request)
    return TaskAccepted(
        task_id=task["id"],
        kind=task["kind"],
        status=task["status"],
        status_url=f"/tasks/{task['id']}",
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
