# -*- coding: utf-8 -*-
"""
FastAPI 接口
提供 REST API 供外部调用

启动:
    uvicorn src.api.server:app --host 0.0.0.0 --port 8888 --reload

接口:
    POST /generate     - 生成文案
    GET  /health       - 健康检查
"""

import json
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.schemas import ProductProfile
from src.inference.model_client import create_client, ModelConfig, get_mock_client
from src.agents.orchestrator import ContentOrchestrator

app = FastAPI(
    title="电商内容生产 Agent",
    description="从商品信息到多平台内容的一站式生成服务",
    version="0.1.0",
)

# 全局 orchestrator（延迟初始化）
_orchestrator: Optional[ContentOrchestrator] = None


def get_orchestrator() -> ContentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        # 默认使用 Mock，生产环境通过环境变量配置
        import os
        backend = os.getenv("MODEL_BACKEND", "mock")
        if backend == "mock":
            client = get_mock_client()
        else:
            config = ModelConfig(
                backend=backend,
                model_name=os.getenv("MODEL_NAME", "ecommerce-copywriter"),
                api_base=os.getenv("API_BASE", "http://localhost:8000/v1"),
                model_path=os.getenv("MODEL_PATH", ""),
                lora_path=os.getenv("LORA_PATH", ""),
            )
            client = create_client(config)
        _orchestrator = ContentOrchestrator(client, max_rewrite_rounds=1)
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


# ============================================================
# 接口
# ============================================================
@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


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


@app.post("/generate/raw")
async def generate_raw(req: dict):
    """生成文案（原始 dict 输入/输出，不做 schema 校验）"""
    try:
        product = ProductProfile.from_dict(req)
        orchestrator = get_orchestrator()
        package = orchestrator.generate(product)
        return package.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)
