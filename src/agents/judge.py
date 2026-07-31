# -*- coding: utf-8 -*-
"""
质量评分 Agent (LLM-as-Judge)
四维评估：准确性 / 吸引力 / 合规性 / SEO覆盖
"""

import json
from src.agents.base import BaseAgent
from src.schemas import ProductProfile, QualityScore, DimensionScore

JUDGE_SYSTEM_PROMPT = """你是一个严格的电商文案质量评估专家。请对给定的商品信息和生成的文案，从四个维度打分（1-5分）：

1. **准确性 (Accuracy)**：文案中的信息是否与商品信息一致？有无虚构、夸大或遗漏？
2. **吸引力 (Attractiveness)**：文案是否具有营销吸引力？语言是否流畅、有感染力？能否激发购买欲望？
3. **合规性 (Compliance)**：文案是否违反广告法（如使用"最""第一""国家级"等极限词）？是否包含虚假宣传？
4. **SEO覆盖 (SEO Coverage)**：文案是否自然涵盖了商品核心关键词？关键词密度是否合理？

评分标准:
- 1分: 严重问题，完全不合格
- 2分: 存在明显缺陷
- 3分: 基本合格，有改进空间
- 4分: 良好，符合预期
- 5分: 优秀，超出预期

请严格按照以下 JSON 格式输出，不要包含任何其他内容：
{
  "accuracy": {"score": 整数1-5, "reason": "简要理由"},
  "attractiveness": {"score": 整数1-5, "reason": "简要理由"},
  "compliance": {"score": 整数1-5, "reason": "简要理由"},
  "seo": {"score": 整数1-5, "reason": "简要理由"},
  "overall_comment": "总体评价（一句话）"
}"""

JUDGE_USER_TEMPLATE = """## 商品信息
{product_info}

## 生成的文案
标题：{title}
卖点：{selling_points}
描述：{description}
SEO关键词：{seo_keywords}
社媒文案：{social_copy}

请对以上文案进行四维评估，输出 JSON 格式。"""


class JudgeAgent(BaseAgent):
    """LLM-as-Judge 质量评分 Agent"""

    name = "judge"
    description = "四维质量评分：准确性/吸引力/合规性/SEO覆盖"

    def run(self, product: ProductProfile, content: dict, **kwargs) -> QualityScore:
        """
        对生成的内容进行四维评分

        Args:
            product: 商品信息
            content: 生成的文案 dict（包含 optimized_title, selling_points, description 等）

        Returns:
            QualityScore 对象
        """
        product_info = json.dumps(product.to_prompt_dict(), ensure_ascii=False, indent=2)

        user_msg = JUDGE_USER_TEMPLATE.format(
            product_info=product_info,
            title=content.get("optimized_title", ""),
            selling_points=" / ".join(content.get("selling_points", [])),
            description=content.get("description", ""),
            seo_keywords=" / ".join(content.get("seo_keywords", [])),
            social_copy=content.get("social_copy", ""),
        )

        result = self.model.chat_json(user_msg, JUDGE_SYSTEM_PROMPT)

        # 解析评分
        def parse_dim(key):
            d = result.get(key, {})
            score = d.get("score", 3)
            if not isinstance(score, int):
                try:
                    score = int(score)
                except (ValueError, TypeError):
                    score = 3
            score = max(1, min(5, score))
            return DimensionScore(score=score, reason=d.get("reason", ""))

        return QualityScore(
            accuracy=parse_dim("accuracy"),
            attractiveness=parse_dim("attractiveness"),
            compliance=parse_dim("compliance"),
            seo=parse_dim("seo"),
        )
