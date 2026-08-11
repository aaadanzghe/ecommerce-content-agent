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
import mimetypes
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
    model: str = ""                          # 方舟模型或推理接入点 ID
    # 生成参数
    image_size: str = "landscape_16_9"       # square / portrait_4_3 / portrait_16_9 / landscape_4_3 / landscape_16_9
    num_images: int = 1                       # 生成图片数量
    # 本地保存
    output_dir: str = "output/image"
    request_timeout: int = 120
    max_download_bytes: int = 50 * 1024 * 1024


class ImageGenerationError(RuntimeError):
    def __init__(self, message: str, status_code: int = None, error_code: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


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

    def generate(self, prompt: str, save: bool = True, image_size: str = None) -> dict:
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

        requested_size = image_size or self.config.image_size
        size = SIZE_MAP.get(requested_size, requested_size)

        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "size": size,
            "n": self.config.num_images,
        }

        print(f"[ImageClient] 提交生成任务: model={self.config.model}, size={size}")
        resp = requests.post(
            self.config.api_url,
            headers=headers,
            json=payload,
            timeout=self.config.request_timeout,
        )

        if resp.status_code != 200:
            raise self._api_error(resp, "图片生成失败")

        try:
            data = resp.json()
        except ValueError as exc:
            raise ImageGenerationError("图片生成接口返回了无效 JSON", resp.status_code) from exc
        task_id = data.get("id", str(uuid.uuid4())[:8])

        # 解析图片 URL
        image_url = ""
        if "data" in data and len(data["data"]) > 0:
            image_url = data["data"][0].get("url", "")
        elif "output" in data:
            image_url = data["output"].get("image_url", "")

        if not image_url:
            raise ImageGenerationError("图片生成响应中缺少图片 URL", resp.status_code)

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
        temp_path = filepath.with_suffix(filepath.suffix + ".part")
        resp = requests.get(url, stream=True, timeout=self.config.request_timeout)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if content_type and not content_type.startswith("image/"):
            raise ImageGenerationError(f"图片下载返回了非图片内容: {content_type}")

        downloaded = 0
        with open(temp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                downloaded += len(chunk)
                if downloaded > self.config.max_download_bytes:
                    f.close()
                    temp_path.unlink(missing_ok=True)
                    raise ImageGenerationError("图片文件超过允许的最大大小")
                f.write(chunk)

        if downloaded == 0:
            temp_path.unlink(missing_ok=True)
            raise ImageGenerationError("下载到的图片为空")
        temp_path.replace(filepath)

        size_kb = filepath.stat().st_size / 1024
        print(f"[ImageClient] 下载完成: {filepath} ({size_kb:.1f} KB)")
        return filepath

    @staticmethod
    def _api_error(resp, prefix: str) -> ImageGenerationError:
        code = ""
        message = resp.text[:500]
        try:
            body = resp.json()
            error = body.get("error", body)
            if isinstance(error, dict):
                code = str(error.get("code", ""))
                message = str(error.get("message", message))
        except ValueError:
            pass
        return ImageGenerationError(
            f"{prefix} (HTTP {resp.status_code}, code={code or 'unknown'}): {message}",
            resp.status_code,
            code,
        )


class MockImageClient(ImageClient):
    """Mock 图片客户端 — 用于无网络环境下的流程验证"""

    def generate(self, prompt: str, save: bool = True, image_size: str = None) -> dict:
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
