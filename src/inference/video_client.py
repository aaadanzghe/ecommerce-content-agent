# -*- coding: utf-8 -*-
"""
视频生成客户端
支持两种后端：
  1. Seedance API (火山引擎方舟，OpenAI 兼容视频生成接口)
  2. Mock (无网络环境下的流程验证)

用法:
    client = create_video_client(VideoConfig(backend="api"))
    result = client.generate("一只猫在窗台上伸懒腰")
    # result = {"task_id": "...", "status": "completed", "video_url": "...", "local_path": "..."}
"""

import os
import time
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class VideoConfig:
    """视频生成配置"""
    backend: str = "mock"                    # mock / api
    # API 后端
    create_url: str = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
    query_url: str = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
    api_key: str = ""
    model: str = ""                          # 方舟模型或推理接入点 ID
    # 生成参数
    duration: int = 5                         # 5 / 10 秒
    resolution: str = "720p"                  # 720p / 1080p
    ratio: str = "16:9"
    # 轮询参数
    poll_interval: int = 5                    # 轮询间隔（秒）
    max_wait: int = 300                       # 最大等待时间（秒）
    # 本地保存
    output_dir: str = "output/video"
    request_timeout: int = 30
    max_download_bytes: int = 500 * 1024 * 1024


class VideoGenerationError(RuntimeError):
    def __init__(self, message: str, status_code: int = None, error_code: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


def create_video_client(config: VideoConfig) -> "VideoClient":
    """工厂函数"""
    if config.backend == "mock":
        return MockVideoClient(config)
    return VideoClient(config)


def get_mock_video_client() -> "MockVideoClient":
    """获取 Mock 视频客户端"""
    return MockVideoClient(VideoConfig(backend="mock"))


class VideoClient:
    """
    Seedance 视频生成客户端

    用法:
        client = create_video_client(VideoConfig(backend="api", api_key="xxx"))
        result = client.generate("电商产品展示视频描述")
    """

    def __init__(self, config: VideoConfig):
        self.config = config

    def generate(
        self,
        prompt: str,
        save: bool = True,
        task_id: str = "",
        on_task_created: Optional[Callable[[str], None]] = None,
    ) -> dict:
        """
        生成视频（异步任务 + 轮询等待）

        Args:
            prompt: 视频描述 prompt
            save: 是否下载到本地

        Returns:
            {"task_id": str, "status": str, "video_url": str, "local_path": str}
        """
        import requests

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.config.model,
            "content": [{"type": "text", "text": prompt}],
            "duration": self.config.duration,
            "resolution": self.config.resolution,
            "ratio": self.config.ratio,
        }

        # 首次执行时提交任务；恢复任务时直接继续轮询。
        if not task_id:
            print(f"[VideoClient] 提交生成任务: model={self.config.model}, duration={self.config.duration}s")
            resp = requests.post(
                self.config.create_url,
                headers=headers,
                json=payload,
                timeout=self.config.request_timeout,
            )

            if resp.status_code not in {200, 201, 202}:
                raise self._api_error(resp, "提交视频任务失败")

            try:
                task_data = resp.json()
            except ValueError as exc:
                raise VideoGenerationError("视频任务接口返回了无效 JSON", resp.status_code) from exc
            task_id = task_data.get("id", "")
            if not task_id:
                raise VideoGenerationError(f"视频任务响应中缺少 task_id: {task_data}")
            if on_task_created:
                on_task_created(task_id)
            print(f"[VideoClient] 任务已提交: {task_id}")
        else:
            print(f"[VideoClient] 恢复轮询任务: {task_id}")

        # 步骤 2：轮询等待结果
        elapsed = 0
        while elapsed < self.config.max_wait:
            time.sleep(self.config.poll_interval)
            elapsed += self.config.poll_interval

            status_resp = requests.get(
                f"{self.config.query_url.rstrip('/')}/{task_id}",
                headers=headers,
                timeout=self.config.request_timeout,
            )
            if status_resp.status_code != 200:
                raise self._api_error(status_resp, "查询视频任务失败")
            try:
                task = status_resp.json()
            except ValueError as exc:
                raise VideoGenerationError("视频任务查询返回了无效 JSON", status_resp.status_code) from exc
            status = str(task.get("status", "")).lower()

            if status in {"succeeded", "completed"}:
                video_url = self._extract_video_url(task)
                if not video_url:
                    raise VideoGenerationError("视频任务成功但响应中缺少视频 URL")
                print(f"[VideoClient] 生成完成 ({elapsed}s): {video_url}")

                result = {
                    "task_id": task_id,
                    "status": "completed",
                    "video_url": video_url,
                    "local_path": "",
                }

                # 下载视频到本地
                if save and video_url:
                    local_path = self._download_video(video_url, task_id)
                    result["local_path"] = str(local_path)

                return result

            if status in {"failed", "cancelled", "canceled"}:
                error = task.get("error", "未知错误")
                raise VideoGenerationError(f"视频生成失败: {error}")

            print(f"[VideoClient] 生成中... ({elapsed}s / {self.config.max_wait}s)")

        raise TimeoutError(f"视频生成超时 ({self.config.max_wait}s)")

    def _download_video(self, url: str, task_id: str) -> Path:
        """下载视频到本地"""
        import requests

        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{task_id}.mp4"
        filepath = output_dir / filename

        print(f"[VideoClient] 下载视频到: {filepath}")
        temp_path = filepath.with_suffix(filepath.suffix + ".part")
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if content_type and not content_type.startswith("video/") and content_type != "application/octet-stream":
            raise VideoGenerationError(f"视频下载返回了非视频内容: {content_type}")

        downloaded = 0
        with open(temp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                downloaded += len(chunk)
                if downloaded > self.config.max_download_bytes:
                    f.close()
                    temp_path.unlink(missing_ok=True)
                    raise VideoGenerationError("视频文件超过允许的最大大小")
                f.write(chunk)

        if downloaded == 0:
            temp_path.unlink(missing_ok=True)
            raise VideoGenerationError("下载到的视频为空")
        temp_path.replace(filepath)

        size_mb = filepath.stat().st_size / (1024 * 1024)
        print(f"[VideoClient] 下载完成: {filepath} ({size_mb:.2f} MB)")
        return filepath

    @staticmethod
    def _extract_video_url(task: dict) -> str:
        content = task.get("content", {})
        if isinstance(content, dict):
            url = content.get("video_url", "")
            if url:
                return url
        output = task.get("output", {})
        if isinstance(output, dict):
            return output.get("video_url", "")
        return task.get("video_url", "")

    @staticmethod
    def _api_error(resp, prefix: str) -> VideoGenerationError:
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
        return VideoGenerationError(
            f"{prefix} (HTTP {resp.status_code}, code={code or 'unknown'}): {message}",
            resp.status_code,
            code,
        )


class MockVideoClient(VideoClient):
    """Mock 视频客户端 — 用于无网络环境下的流程验证"""

    def generate(
        self,
        prompt: str,
        save: bool = True,
        task_id: str = "",
        on_task_created: Optional[Callable[[str], None]] = None,
    ) -> dict:
        print(f"[MockVideoClient] 模拟视频生成...")
        print(f"[MockVideoClient] Prompt: {prompt[:80]}...")

        # 模拟生成延迟
        time.sleep(1)

        result = {
            "task_id": "mock-task-001",
            "status": "completed",
            "video_url": "mock://localhost/video/mock-task-001.mp4",
            "local_path": "",
            "prompt": prompt[:200],
        }

        # 创建占位文件
        if save:
            output_dir = Path(self.config.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            placeholder = output_dir / "mock-task-001.mp4.placeholder"
            placeholder.write_text(
                f"Mock Video Placeholder\nPrompt: {prompt[:200]}\n",
                encoding="utf-8",
            )
            result["local_path"] = str(placeholder)

        print(f"[MockVideoClient] 模拟生成完成")
        return result
