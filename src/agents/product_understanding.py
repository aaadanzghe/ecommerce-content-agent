# -*- coding: utf-8 -*-
"""
商品理解 Agent
解析商品属性、品类、目标人群和使用场景
如果输入缺少 selling_points 或 target_audience，则自动补全
"""

import json
from src.agents.base import BaseAgent
from src.schemas import ProductProfile

SYSTEM_PROMPT = """你是一个电商商品分析专家。你的任务是分析商品信息，提炼核心卖点和目标人群。"""

USER_PROMPT_TEMPLATE = """请分析以下商品信息，提炼出核心卖点和目标人群。

商品信息：
{product_info}

请以 JSON 格式输出：
{{
  "selling_points": ["卖点1", "卖点2", ...],
  "target_audience": "目标人群描述",
  "use_scenes": ["使用场景1", "场景2", ...],
  "price_positioning": "low/mid/high"
}}

要求：
- 卖点 3-5 个，简洁有力
- 目标人群要具体（如"25-35岁通勤白领"而非"年轻人"）
- 使用场景 2-3 个"""


class ProductUnderstandingAgent(BaseAgent):
    """商品理解 Agent：补全卖点和目标人群"""

    name = "product_understanding"
    description = "解析商品属性，提炼卖点、目标人群和使用场景"

    def run(self, product: ProductProfile, **kwargs) -> dict:
        # 如果已有卖点且有人群，直接返回
        if product.selling_points and product.target_audience:
            return {
                "selling_points": product.selling_points,
                "target_audience": product.target_audience,
                "use_scenes": [],
                "price_positioning": product.price_positioning,
            }

        product_info = json.dumps(product.to_prompt_dict(), ensure_ascii=False, indent=2)
        user_msg = USER_PROMPT_TEMPLATE.format(product_info=product_info)

        result = self.model.chat_json(user_msg, SYSTEM_PROMPT)

        # 合并：已有值不覆盖
        selling_points = product.selling_points or result.get("selling_points", [])
        target_audience = product.target_audience or result.get("target_audience", "")
        use_scenes = result.get("use_scenes", [])
        price_positioning = product.price_positioning or result.get("price_positioning", "")

        return {
            "selling_points": selling_points,
            "target_audience": target_audience,
            "use_scenes": use_scenes,
            "price_positioning": price_positioning,
        }
