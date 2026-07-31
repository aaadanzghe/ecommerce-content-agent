# -*- coding: utf-8 -*-
"""
文案生成 Agent
生成优化标题、五点卖点、详情页文案和社媒推广文案
支持多平台风格适配（淘宝 / Amazon / 抖音 / 小红书）
"""

import json
from src.agents.base import BaseAgent
from src.schemas import ProductProfile, Platform

# ============================================================
# 平台风格模板
# ============================================================
PLATFORM_STYLE = {
    "taobao": {
        "title_rule": "标题 30 字以内，含核心关键词，突出卖点",
        "desc_rule": "详情页文案 150-300 字，分段清晰，用emoji点缀",
        "social_rule": "淘宝微淘文案，种草风格",
    },
    "amazon": {
        "title_rule": "Title within 200 chars, brand + key features + size/color",
        "desc_rule": "5 bullet points + product description, professional tone",
        "social_rule": "Amazon A+ content style, feature-focused",
    },
    "douyin": {
        "title_rule": "标题 20 字以内，吸引眼球，带话题标签",
        "desc_rule": "短视频口播稿 100-200 字，有 hook 和 CTA",
        "social_rule": "抖音文案，带 #话题#，引导互动",
    },
    "xiaohongshu": {
        "title_rule": "标题 20 字以内，种草感强，带emoji",
        "desc_rule": "小红书笔记 200-400 字，第一人称体验感",
        "social_rule": "小红书种草文案，带emoji和话题标签",
    },
}

SYSTEM_PROMPT = """你是一名专业的电商文案撰写师。请根据商品信息生成多维度文案。
要求：
1. 信息准确无误，不虚构属性
2. 突出核心卖点
3. 语言流畅有吸引力
4. 不违反广告法（不用"最""第一""国家级"等极限词）"""

USER_PROMPT_TEMPLATE = """请根据以下商品信息生成电商文案。

商品信息：
{product_info}

平台风格要求：{platform_style}

请以 JSON 格式输出：
{{
  "optimized_title": "优化后的商品标题",
  "selling_points": ["卖点1", "卖点2", "卖点3", "卖点4", "卖点5"],
  "description": "详情页文案",
  "social_copy": "社媒推广文案"
}}

注意：
- 卖点必须 5 条
- 所有信息必须基于商品属性，不要虚构
- 不要使用绝对化用语（最、第一、国家级等）"""


class CopywritingAgent(BaseAgent):
    """文案生成 Agent"""

    name = "copywriting"
    description = "生成优化标题、五点卖点、详情页文案和社媒推广文案"

    def run(self, product: ProductProfile, **kwargs) -> dict:
        product_info = json.dumps(product.to_prompt_dict(), ensure_ascii=False, indent=2)

        platform = product.platform if product.platform in PLATFORM_STYLE else "taobao"
        style = PLATFORM_STYLE[platform]
        platform_style = f"标题: {style['title_rule']}; 描述: {style['desc_rule']}; 社媒: {style['social_rule']}"

        user_msg = USER_PROMPT_TEMPLATE.format(
            product_info=product_info,
            platform_style=platform_style,
        )

        result = self.model.chat_json(user_msg, SYSTEM_PROMPT)

        return {
            "optimized_title": result.get("optimized_title", product.title),
            "selling_points": result.get("selling_points", []),
            "description": result.get("description", ""),
            "social_copy": result.get("social_copy", ""),
            "platform": platform,
        }
