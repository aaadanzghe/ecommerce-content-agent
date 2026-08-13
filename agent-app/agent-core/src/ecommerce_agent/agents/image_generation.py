# -*- coding: utf-8 -*-
"""
图片生成 Agent
根据商品信息和已生成的文案，构建图片 prompt 并调用 Seedream 生成产品展示图

流程:
    商品信息 + 文案 → 构建 image prompt → 调用 ImageClient → 返回图片路径
"""

import json
from ecommerce_agent.agents.base import BaseAgent
from ecommerce_agent.domain.models import ProductProfile
from ecommerce_agent.providers.image_client import ImageClient, ImageConfig, create_image_client, get_mock_image_client

# 平台图片风格
PLATFORM_IMAGE_STYLE = {
    "taobao": {
        "style": "电商产品白底图风格，专业摄影灯光，纯白或浅灰背景，产品居中构图，突出产品质感和细节，高清商业摄影",
        "size": "square",
    },
    "amazon": {
        "style": "Amazon Listing 主图风格，纯白背景（RGB 255,255,255），产品占画面85%以上，多角度展示，专业产品摄影",
        "size": "square",
    },
    "douyin": {
        "style": "抖音种草风格，生活化场景，自然光，年轻人使用场景，色彩鲜明有活力，适合短视频封面",
        "size": "portrait_16_9",
    },
    "xiaohongshu": {
        "style": "小红书种草风格，温暖自然光，真实使用场景，柔和色调，生活美学感，第一人称视角",
        "size": "portrait_4_3",
    },
}

SYSTEM_PROMPT = """你是一名资深电商视觉设计师。你的任务是根据商品信息和文案，设计一张高质量的产品展示图的画面描述。"""

PROMPT_TEMPLATE = """请根据以下商品信息和文案，设计一张产品展示图的画面描述（用于 AI 图片生成）。

商品信息：
{product_info}

已生成文案：
标题：{title}
核心卖点：{selling_points}
社媒文案：{social_copy}

平台风格要求：{platform_style}

请直接输出图片的画面描述（150-250字，英文 prompt），包含：
1. 构图方式（产品在画面中的位置、角度）
2. 场景和背景（纯色/场景化、光线布置）
3. 产品细节（材质、颜色、关键特征的呈现）
4. 整体风格和色调

不要输出 JSON，直接输出纯文本的英文画面描述 prompt。"""


class ImageGenerationAgent(BaseAgent):
    """图片生成 Agent：根据商品和文案生成产品展示图"""

    name = "image_generation"
    description = "根据商品信息和文案，调用 Seedream 生成产品展示图"

    def __init__(self, model_client, image_client: ImageClient = None):
        """
        Args:
            model_client: 文本模型客户端（用于生成图片 prompt）
            image_client: 图片生成客户端（Seedream / Mock）
        """
        super().__init__(model_client)
        self.image_client = image_client or get_mock_image_client()

    def build_image_prompt(
        self,
        product: ProductProfile,
        content: dict,
        platform: str = "taobao",
    ) -> str:
        """
        构建图片生成 prompt

        Args:
            product: 商品信息
            content: 已生成的文案 dict（optimized_title, selling_points, social_copy）
            platform: 目标平台

        Returns:
            图片画面描述 prompt（英文）
        """
        product_info = json.dumps(product.to_prompt_dict(), ensure_ascii=False, indent=2)

        platform_style_data = PLATFORM_IMAGE_STYLE.get(platform, PLATFORM_IMAGE_STYLE["taobao"])
        platform_style = platform_style_data["style"]

        user_msg = PROMPT_TEMPLATE.format(
            product_info=product_info,
            title=content.get("optimized_title", product.title),
            selling_points=" / ".join(content.get("selling_points", [])),
            social_copy=content.get("social_copy", ""),
            platform_style=platform_style,
        )

        # 用文本模型生成图片画面描述
        image_prompt = self.model.chat(user_msg, SYSTEM_PROMPT)

        # 加上平台风格前缀
        image_prompt = f"{platform_style}, {image_prompt}"

        return image_prompt

    def get_image_size(self, platform: str) -> str:
        """获取平台对应的推荐图片尺寸"""
        platform_style_data = PLATFORM_IMAGE_STYLE.get(platform, PLATFORM_IMAGE_STYLE["taobao"])
        return platform_style_data.get("size", "square")

    def run(
        self,
        product: ProductProfile,
        content: dict = None,
        platform: str = "taobao",
        custom_prompt: str = "",
        **kwargs,
    ) -> dict:
        """
        生成产品展示图

        Args:
            product: 商品信息
            content: 已生成的文案 dict（可选，不传则只用商品信息）
            platform: 目标平台
            custom_prompt: 自定义图片 prompt（优先使用，跳过 LLM 生成）

        Returns:
            {"image_prompt": str, "task_id": str, "status": str, "image_url": str, "local_path": str}
        """
        content = content or {}
        platform = product.platform if hasattr(product, "platform") and product.platform else platform

        # 1. 构建 image prompt
        if custom_prompt:
            image_prompt = custom_prompt
        else:
            image_prompt = self.build_image_prompt(product, content, platform)

        print(f"[ImageAgent] 图片 prompt 构建完成 ({len(image_prompt)} 字)")

        # 2. 调用图片生成
        image_size = self.get_image_size(platform)
        result = self.image_client.generate(image_prompt, save=True, image_size=image_size)

        # 3. 返回完整结果
        return {
            "image_prompt": image_prompt[:500],
            "task_id": result.get("task_id", ""),
            "status": result.get("status", "unknown"),
            "image_url": result.get("image_url", ""),
            "local_path": result.get("local_path", ""),
            "platform": platform,
            "image_size": image_size,
        }
