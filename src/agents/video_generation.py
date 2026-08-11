# -*- coding: utf-8 -*-
"""
视频生成 Agent
根据商品信息和已生成的文案，构建视频 prompt 并调用 Seedance 生成产品展示短视频

流程:
    商品信息 + 文案 → 构建 video prompt → 调用 VideoClient → 返回视频路径
"""

import json
from src.agents.base import BaseAgent
from src.schemas import ProductProfile
from src.inference.video_client import VideoClient, VideoConfig, create_video_client, get_mock_video_client

# 平台视频风格
PLATFORM_VIDEO_STYLE = {
    "taobao": {
        "style": "电商产品展示风格，专业灯光，白色或浅色背景，突出产品细节和卖点",
        "duration": 5,
    },
    "amazon": {
        "style": "Amazon Listing 产品展示风格，多角度特写，功能演示，英文标注",
        "duration": 5,
    },
    "douyin": {
        "style": "抖音短视频风格，节奏快，生活化场景，年轻活力，带字幕动效",
        "duration": 5,
    },
    "xiaohongshu": {
        "style": "小红书种草风格，第一人称视角，温馨自然光，真实使用场景",
        "duration": 5,
    },
}

SYSTEM_PROMPT = """你是一名电商产品短视频创意导演。你的任务是根据商品信息和文案，构思一段 5-10 秒的产品展示短视频画面描述。"""

PROMPT_TEMPLATE = """请根据以下商品信息和文案，构思一段产品展示短视频的画面描述。

商品信息：
{product_info}

已生成文案：
标题：{title}
核心卖点：{selling_points}
社媒文案：{social_copy}

平台风格要求：{platform_style}

请直接输出视频画面描述（200-300字），包含：
1. 开场镜头（产品如何出场）
2. 核心卖点展示镜头（2-3个场景）
3. 结尾镜头（品牌/行动引导）
4. 整体色调和氛围

不要输出 JSON，直接输出纯文本的画面描述。"""


class VideoGenerationAgent(BaseAgent):
    """视频生成 Agent：根据商品和文案生成产品展示短视频"""

    name = "video_generation"
    description = "根据商品信息和文案，调用 Seedance 生成产品展示短视频"

    def __init__(self, model_client, video_client: VideoClient = None):
        """
        Args:
            model_client: 文本模型客户端（用于生成视频 prompt）
            video_client: 视频生成客户端（Seedance / Mock）
        """
        super().__init__(model_client)
        self.video_client = video_client or get_mock_video_client()

    def build_video_prompt(
        self,
        product: ProductProfile,
        content: dict,
        platform: str = "taobao",
    ) -> str:
        """
        构建视频生成 prompt

        Args:
            product: 商品信息
            content: 已生成的文案 dict（optimized_title, selling_points, social_copy）
            platform: 目标平台

        Returns:
            视频画面描述 prompt
        """
        product_info = json.dumps(product.to_prompt_dict(), ensure_ascii=False, indent=2)

        platform_style_data = PLATFORM_VIDEO_STYLE.get(platform, PLATFORM_VIDEO_STYLE["taobao"])
        platform_style = platform_style_data["style"]

        user_msg = PROMPT_TEMPLATE.format(
            product_info=product_info,
            title=content.get("optimized_title", product.title),
            selling_points=" / ".join(content.get("selling_points", [])),
            social_copy=content.get("social_copy", ""),
            platform_style=platform_style,
        )

        # 用文本模型生成视频画面描述
        video_prompt = self.model.chat(user_msg, SYSTEM_PROMPT)

        # 加上平台风格后缀
        video_prompt = f"[{platform_style}] {video_prompt}"

        return video_prompt

    def run(
        self,
        product: ProductProfile,
        content: dict = None,
        platform: str = "taobao",
        custom_prompt: str = "",
        **kwargs,
    ) -> dict:
        """
        生成产品展示短视频

        Args:
            product: 商品信息
            content: 已生成的文案 dict（可选，不传则只用商品信息）
            platform: 目标平台
            custom_prompt: 自定义视频 prompt（优先使用，跳过 LLM 生成）

        Returns:
            {"video_prompt": str, "task_id": str, "status": str, "video_url": str, "local_path": str}
        """
        content = content or {}
        platform = product.platform if hasattr(product, "platform") and product.platform else platform

        # 1. 构建 video prompt
        if custom_prompt:
            video_prompt = custom_prompt
        else:
            video_prompt = self.build_video_prompt(product, content, platform)

        print(f"[VideoAgent] 视频 prompt 构建完成 ({len(video_prompt)} 字)")

        # 2. 调用视频生成
        result = self.video_client.generate(video_prompt, save=True)

        # 3. 返回完整结果
        return {
            "video_prompt": video_prompt[:500],
            "task_id": result.get("task_id", ""),
            "status": result.get("status", "unknown"),
            "video_url": result.get("video_url", ""),
            "local_path": result.get("local_path", ""),
            "platform": platform,
        }
