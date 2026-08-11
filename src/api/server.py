# -*- coding: utf-8 -*-
"""
FastAPI 接口
提供 REST API 供外部调用

启动:
    uvicorn src.api.server:app --host 0.0.0.0 --port 8888 --reload

接口:
    POST /generate          - 生成文案
    POST /generate/image    - 生成文案 + 图片
    POST /generate/video    - 生成文案 + 视频
    POST /generate/all      - 生成文案 + 图片 + 视频
    GET  /health            - 健康检查

环境变量:
    所有配置从 .env 文件或系统环境变量读取，详见 .env.example
"""

import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# 加载 .env 文件（项目根目录）
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from src.schemas import ProductProfile
from src.inference.model_client import create_client, ModelConfig, get_mock_client
from src.inference.video_client import VideoConfig, create_video_client, get_mock_video_client
from src.inference.image_client import ImageConfig, create_image_client, get_mock_image_client
from src.agents.orchestrator import ContentOrchestrator

app = FastAPI(
    title="电商内容生产 Agent",
    description="从商品信息到多平台内容的一站式生成服务（支持文案 + 图片 + 短视频）",
    version="0.4.0",
)

# 全局 orchestrator（延迟初始化）
_orchestrator: Optional[ContentOrchestrator] = None


def _get_env(key: str, default: str = "") -> str:
    """读取环境变量，自动去除引号和空格"""
    val = os.getenv(key, default)
    if val:
        val = val.strip().strip('"').strip("'")
    return val


def get_orchestrator() -> ContentOrchestrator:
    """获取全局 Orchestrator（延迟初始化，从 .env 读取配置）"""
    global _orchestrator
    if _orchestrator is None:
        # 文本模型客户端
        backend = _get_env("MODEL_BACKEND", "mock")
        if backend == "mock":
            client = get_mock_client()
        else:
            config = ModelConfig(
                backend=backend,
                model_name=_get_env("MODEL_NAME", "ecommerce-copywriter"),
                api_base=_get_env("API_BASE", "http://localhost:8000/v1"),
                api_key=_get_env("API_KEY", "not-needed"),
                model_path=_get_env("MODEL_PATH", ""),
                lora_path=_get_env("LORA_PATH", ""),
                temperature=float(_get_env("TEMPERATURE", "0.7")),
                top_p=float(_get_env("TOP_P", "0.9")),
                max_tokens=int(_get_env("MAX_TOKENS", "1024")),
            )
            client = create_client(config)

        # 视频生成客户端（可选）
        video_client = None
        video_backend = _get_env("VIDEO_BACKEND", "")
        if video_backend == "api":
            video_config = VideoConfig(
                backend="api",
                api_key=_get_env("SEEDANCE_API_KEY", ""),
                model=_get_env("SEEDANCE_MODEL", "doubao-seedance-1.0-pro"),
                duration=int(_get_env("VIDEO_DURATION", "5")),
                resolution=_get_env("VIDEO_RESOLUTION", "720p"),
            )
            video_client = create_video_client(video_config)
        elif video_backend == "mock":
            video_client = get_mock_video_client()

        # 图片生成客户端（可选）
        image_client = None
        image_backend = _get_env("IMAGE_BACKEND", "")
        if image_backend == "api":
            image_config = ImageConfig(
                backend="api",
                api_key=_get_env("SEEDREAM_API_KEY", ""),
                model=_get_env("SEEDREAM_MODEL", "doubao-seedream-3.0"),
                image_size=_get_env("IMAGE_SIZE", "landscape_16_9"),
            )
            image_client = create_image_client(image_config)
        elif image_backend == "mock":
            image_client = get_mock_image_client()

        max_rounds = int(_get_env("MAX_REWRITE_ROUNDS", "2"))
        _orchestrator = ContentOrchestrator(
            client,
            max_rewrite_rounds=max_rounds,
            video_client=video_client,
            image_client=image_client,
        )
    return _orchestrator


# ============================================================
# 请求/响应模型
# ============================================================
class GenerateRequest(BaseModel):
    title: str = Field(..., description="商品标题")
    category: str = Field("other", description="商品品类")
    attributes: dict = Field(default_factory=dict, description="商品属性")
    selling_points: list = Field(default_factory=list, description="卖点（可选，不填则自动生成）")
    target_audience: str = Field("", description="目标人群（可选）")
    price_positioning: str = Field("", description="价格定位: low/mid/high")
    platform: str = Field("taobao", description="平台: taobao/amazon/douyin/xiaohongshu")
    tone: str = Field("professional", description="语气风格")
    constraints: list = Field(default_factory=list, description="约束条件")


class GenerateVideoRequest(GenerateRequest):
    """生成文案 + 视频的请求"""
    custom_video_prompt: str = Field("", description="自定义视频 prompt（可选，不填则自动生成）")


class GenerateImageRequest(GenerateRequest):
    """生成文案 + 图片的请求"""
    custom_image_prompt: str = Field("", description="自定义图片 prompt（可选，不填则自动生成）")


class GenerateAllRequest(GenerateRequest):
    """生成文案 + 图片 + 视频的请求"""
    custom_image_prompt: str = Field("", description="自定义图片 prompt（可选，不填则自动生成）")
    custom_video_prompt: str = Field("", description="自定义视频 prompt（可选，不填则自动生成）")


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
    video: Optional[dict] = None
    image: Optional[dict] = None


# ============================================================
# 接口
# ============================================================
@app.get("/health")
async def health():
    backend = _get_env("MODEL_BACKEND", "mock")
    video_backend = _get_env("VIDEO_BACKEND", "")
    image_backend = _get_env("IMAGE_BACKEND", "")
    return {
        "status": "ok",
        "version": "0.4.0",
        "backend": backend,
        "image_backend": image_backend if image_backend else "disabled",
        "video_backend": video_backend if video_backend else "disabled",
    }


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    """生成电商文案"""
    try:
        product = ProductProfile.from_dict(req.dict())
        orchestrator = get_orchestrator()
        package = orchestrator.generate(product)
        return GenerateResponse(**package.to_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate/video", response_model=GenerateResponse)
async def generate_video(req: GenerateVideoRequest):
    """
    生成电商文案 + 产品展示短视频

    需要 .env 中配置 VIDEO_BACKEND=api 或 VIDEO_BACKEND=mock
    """
    try:
        product = ProductProfile.from_dict(req.dict())
        orchestrator = get_orchestrator()

        # 自定义视频 prompt
        custom_prompt = req.custom_video_prompt if req.custom_video_prompt else ""

        package = orchestrator.generate(
            product,
            generate_video=True,
        )

        # 如果有自定义 prompt，覆盖 video_agent 的结果
        if custom_prompt and orchestrator.video_agent:
            video_result = orchestrator.video_agent.run(
                product=product,
                content={
                    "optimized_title": package.optimized_title,
                    "selling_points": package.selling_points,
                    "social_copy": package.social_copy,
                },
                platform=product.platform,
                custom_prompt=custom_prompt,
            )
            package.video = video_result

        return GenerateResponse(**package.to_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate/image", response_model=GenerateResponse)
async def generate_image(req: GenerateImageRequest):
    """
    生成电商文案 + 产品展示图

    需要 .env 中配置 IMAGE_BACKEND=api 或 IMAGE_BACKEND=mock
    """
    try:
        product = ProductProfile.from_dict(req.dict())
        orchestrator = get_orchestrator()

        custom_prompt = req.custom_image_prompt if req.custom_image_prompt else ""

        package = orchestrator.generate(
            product,
            generate_image=True,
        )

        if custom_prompt and orchestrator.image_agent:
            image_result = orchestrator.image_agent.run(
                product=product,
                content={
                    "optimized_title": package.optimized_title,
                    "selling_points": package.selling_points,
                    "social_copy": package.social_copy,
                },
                platform=product.platform,
                custom_prompt=custom_prompt,
            )
            package.image = image_result

        return GenerateResponse(**package.to_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate/all", response_model=GenerateResponse)
async def generate_all(req: GenerateAllRequest):
    """
    生成电商文案 + 产品展示图 + 产品展示短视频

    一键生成全部内容
    """
    try:
        product = ProductProfile.from_dict(req.dict())
        orchestrator = get_orchestrator()

        custom_image_prompt = req.custom_image_prompt if req.custom_image_prompt else ""
        custom_video_prompt = req.custom_video_prompt if req.custom_video_prompt else ""

        package = orchestrator.generate(
            product,
            generate_image=True,
            generate_video=True,
        )

        if custom_image_prompt and orchestrator.image_agent:
            image_result = orchestrator.image_agent.run(
                product=product,
                content={
                    "optimized_title": package.optimized_title,
                    "selling_points": package.selling_points,
                    "social_copy": package.social_copy,
                },
                platform=product.platform,
                custom_prompt=custom_image_prompt,
            )
            package.image = image_result

        if custom_video_prompt and orchestrator.video_agent:
            video_result = orchestrator.video_agent.run(
                product=product,
                content={
                    "optimized_title": package.optimized_title,
                    "selling_points": package.selling_points,
                    "social_copy": package.social_copy,
                },
                platform=product.platform,
                custom_prompt=custom_video_prompt,
            )
            package.video = video_result

        return GenerateResponse(**package.to_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate/raw")
async def generate_raw(req: dict):
    """生成文案（原始 dict 输入/输出，不做 schema 校验）"""
    try:
        product = ProductProfile.from_dict(req)
        orchestrator = get_orchestrator()
        generate_vid = req.get("generate_video", False)
        generate_img = req.get("generate_image", False)
        package = orchestrator.generate(product, generate_video=generate_vid, generate_image=generate_img)
        return package.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    host = _get_env("API_HOST", "0.0.0.0")
    port = int(_get_env("API_PORT", "8888"))
    uvicorn.run(app, host=host, port=port)
