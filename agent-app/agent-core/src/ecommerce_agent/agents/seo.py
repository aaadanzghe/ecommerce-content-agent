# -*- coding: utf-8 -*-
"""
SEO Agent
补充搜索关键词和平台关键词
"""

import json
from ecommerce_agent.agents.base import BaseAgent
from ecommerce_agent.domain.models import ProductProfile

SYSTEM_PROMPT = """你是一名电商 SEO 专家。你的任务是根据商品信息生成搜索关键词。"""

USER_PROMPT_TEMPLATE = """请根据以下商品信息生成 SEO 关键词。

商品信息：
{product_info}

请以 JSON 格式输出：
{{
  "seo_keywords": ["关键词1", "关键词2", ...],
  "long_tail_keywords": ["长尾词1", "长尾词2", ...],
  "category_keywords": ["品类词1", "品类词2", ...]
}}

要求：
- seo_keywords: 5-10 个核心搜索词
- long_tail_keywords: 3-5 个长尾词（如"蓝牙耳机 运动防水"）
- category_keywords: 2-3 个品类词
- 关键词要符合真实搜索习惯"""


class SEOAgent(BaseAgent):
    """SEO 关键词 Agent"""

    name = "seo"
    description = "生成搜索关键词和平台关键词"

    def run(self, product: ProductProfile, **kwargs) -> dict:
        product_info = json.dumps(product.to_prompt_dict(), ensure_ascii=False, indent=2)
        user_msg = USER_PROMPT_TEMPLATE.format(product_info=product_info)

        result = self.model.chat_json(user_msg, SYSTEM_PROMPT)

        return {
            "seo_keywords": result.get("seo_keywords", []),
            "long_tail_keywords": result.get("long_tail_keywords", []),
            "category_keywords": result.get("category_keywords", []),
        }
