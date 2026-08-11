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
from typing import Optional


@dataclass
class VideoConfig:
    """视频生成配置"""
    backend: str = "mock"                    # mock / api
    # API 后端
    api_url: str = "https://ark.cn-beijing.volces.com/api/v3/video/generations"
    api_key: str = ""
    model: str = "doubao-seedance-1.0-pro"   # doubao-seedance-1.0-pro / doubao-seedance-1.0-lite
    # 生成参数
    duration: int = 5                         # 5 / 10 秒
    resolution: str = "720p"                  # 720p / 1080p
    # 轮询参数
    poll_interval: int = 5                    # 轮询间隔（秒）
    max_wait: int = 300                       # 最大等待时间（秒）
    # 本地保存
    output_dir: str = "output/video"


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

    def generate(self, prompt: str, save: bool = True) -> dict:
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
            "prompt": prompt,
            "duration": self.config.duration,
            "resolution": self.config.resolution,
        }

        # 步骤 1：提交生成任务
        print(f"[VideoClient] 提交生成任务: model={self.config.model}, duration={self.config.duration}s")
        resp = requests.post(self.config.api_url, headers=headers, json=payload, timeout=30)

        if resp.status_code != 200:
            raise Exception(f"提交任务失败 (HTTP {resp.status_code}): {resp.text[:500]}")

        task_data = resp.json()
        task_id = task_data.get("id", "")
        if not task_id:
            raise Exception(f"未返回 task_id: {task_data}")

        print(f"[VideoClient] 任务已提交: {task_id}")

        # 步骤 2：轮询等待结果
        elapsed = 0
        while elapsed < self.config.max_wait:
            time.sleep(self.config.poll_interval)
            elapsed += self.config.poll_interval

            status_resp = requests.get(
                f"{self.config.api_url}/{task_id}",
                headers=headers,
                timeout=30,
            )
            task = status_resp.json()
            status = task.get("status", "")

            if status == "completed":
                video_url = task.get("output", {}).get("video_url", "")
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

            if status == "failed":
                error = task.get("error", "未知错误")
                raise Exception(f"视频生成失败: {error}")

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
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = filepath.stat().st_size / (1024 * 1024)
        print(f"[VideoClient] 下载完成: {filepath} ({size_mb:.2f} MB)")
        return filepath


class MockVideoClient(VideoClient):
    """Mock 视频客户端 — 用于无网络环境下的流程验证"""

    def generate(self, prompt: str, save: bool = True) -> dict:
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
