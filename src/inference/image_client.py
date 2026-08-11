# -*- coding: utf-8 -*-
"""
图片生成客户端
支持两种后端：
  1. Seedream API (火山引擎方舟)
  2. Mock (无网络环境下的流程验证)

用法:
    client = create_image_client(ImageConfig(backend="api"))
    result = client.generate("白色背景上的无线蓝牙耳机产品图")
    # result = {"task_id": "...", "status": "completed", "image_url": "...", "local_path": "..."}
"""

import os
import time
import json
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ImageConfig:
    """图片生成配置"""
    backend: str = "mock"                    # mock / api
    # API 后端
    api_url: str = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
    api_key: str = ""
    model: str = "doubao-seedream-3.0"       # Seedream 模型
    # 生成参数
    image_size: str = "landscape_16_9"       # square / portrait_4_3 / portrait_16_9 / landscape_4_3 / landscape_16_9
    num_images: int = 1                       # 生成图片数量
    # 本地保存
    output_dir: str = "output/image"


# 预设尺寸映射
SIZE_MAP = {
    "square": "1920x1920",
    "portrait_4_3": "1680x2240",
    "portrait_16_9": "1440x2560",
    "landscape_4_3": "2240x1680",
    "landscape_16_9": "2560x1440",
}


def create_image_client(config: ImageConfig) -> "ImageClient":
    """工厂函数"""
    if config.backend == "mock":
        return MockImageClient(config)
    return ImageClient(config)


def get_mock_image_client() -> "MockImageClient":
    """获取 Mock 图片客户端"""
    return MockImageClient(ImageConfig(backend="mock"))


class ImageClient:
    """
    Seedream 图片生成客户端

    用法:
        client = create_image_client(ImageConfig(backend="api", api_key="xxx"))
        result = client.generate("电商产品展示图描述")
    """

    def __init__(self, config: ImageConfig):
        self.config = config

    def generate(self, prompt: str, save: bool = True) -> dict:
        """
        生成图片

        Args:
            prompt: 图片描述 prompt
            save: 是否下载到本地

        Returns:
            {"task_id": str, "status": str, "image_url": str, "local_path": str}
        """
        import requests

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        size = SIZE_MAP.get(self.config.image_size, "2560x1440")

        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "size": size,
            "n": self.config.num_images,
        }

        print(f"[ImageClient] 提交生成任务: model={self.config.model}, size={size}")
        resp = requests.post(self.config.api_url, headers=headers, json=payload, timeout=120)

        if resp.status_code != 200:
            raise Exception(f"图片生成失败 (HTTP {resp.status_code}): {resp.text[:500]}")

        data = resp.json()
        task_id = data.get("id", str(uuid.uuid4())[:8])

        # 解析图片 URL
        image_url = ""
        if "data" in data and len(data["data"]) > 0:
            image_url = data["data"][0].get("url", "")
        elif "output" in data:
            image_url = data["output"].get("image_url", "")

        print(f"[ImageClient] 生成完成: {image_url}")

        result = {
            "task_id": task_id,
            "status": "completed",
            "image_url": image_url,
            "local_path": "",
        }

        # 下载图片到本地
        if save and image_url:
            local_path = self._download_image(image_url, task_id)
            result["local_path"] = str(local_path)

        return result

    def _download_image(self, url: str, task_id: str) -> Path:
        """下载图片到本地"""
        import requests

        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 根据 URL 推断扩展名
        ext = ".png"
        if ".jpg" in url or ".jpeg" in url:
            ext = ".jpg"
        elif ".webp" in url:
            ext = ".webp"

        filename = f"{task_id}{ext}"
        filepath = output_dir / filename

        print(f"[ImageClient] 下载图片到: {filepath}")
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_kb = filepath.stat().st_size / 1024
        print(f"[ImageClient] 下载完成: {filepath} ({size_kb:.1f} KB)")
        return filepath


class MockImageClient(ImageClient):
    """Mock 图片客户端 — 用于无网络环境下的流程验证"""

    def generate(self, prompt: str, save: bool = True) -> dict:
        print(f"[MockImageClient] 模拟图片生成...")
        print(f"[MockImageClient] Prompt: {prompt[:80]}...")

        # 模拟生成延迟
        time.sleep(1)

        task_id = f"mock-img-{uuid.uuid4().hex[:8]}"

        result = {
            "task_id": task_id,
            "status": "completed",
            "image_url": f"mock://localhost/image/{task_id}.png",
            "local_path": "",
            "prompt": prompt[:200],
        }

        # 创建占位文件
        if save:
            output_dir = Path(self.config.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            placeholder = output_dir / f"{task_id}.png.placeholder"
            placeholder.write_text(
                f"Mock Image Placeholder\nPrompt: {prompt[:200]}\n",
                encoding="utf-8",
            )
            result["local_path"] = str(placeholder)

        print(f"[MockImageClient] 模拟生成完成")
        return result