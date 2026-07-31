# -*- coding: utf-8 -*-
"""
自动重写 Agent
根据评分结果和合规问题，自动重写低质量内容
"""

import json
from src.agents.base import BaseAgent
from src.schemas import ProductProfile, QualityScore

SYSTEM_PROMPT = """你是一名电商文案优化专家。你的任务是根据评分反馈和合规问题，重写文案中的低质量部分。
要求：
1. 只修改有问题的部分，保留好的内容
2. 信息必须基于商品原始属性，不要虚构
3. 不要使用绝对化用语
4. 提升文案的吸引力和 SEO 覆盖"""

USER_PROMPT_TEMPLATE = """请根据以下反馈重写文案。

商品原始信息：
{product_info}

原始文案：
{original_content}

评分反馈：
{score_feedback}

合规问题：
{compliance_issues}

请以 JSON 格式输出重写后的文案：
{{
  "optimized_title": "重写后的标题",
  "selling_points": ["卖点1", "卖点2", "卖点3", "卖点4", "卖点5"],
  "description": "重写后的详情页文案",
  "social_copy": "重写后的社媒文案",
  "rewrite_reason": "说明做了哪些修改"
}}

注意：
- 卖点必须 5 条
- 只修改有问题的部分，不要全盘重写
- rewrite_reason 要具体说明修改了什么"""


class RewriteAgent(BaseAgent):
    """自动重写 Agent"""

    name = "rewrite"
    description = "根据评分和合规反馈自动重写低质量内容"

    def run(
        self,
        product: ProductProfile,
        content: dict,
        score: QualityScore,
        compliance_issues: list = None,
        **kwargs
    ) -> dict:
        """
        根据评分和合规问题重写文案

        Args:
            product: 商品信息
            content: 原始文案
            score: 质量评分
            compliance_issues: 合规问题列表

        Returns:
            重写后的文案 dict
        """
        product_info = json.dumps(product.to_prompt_dict(), ensure_ascii=False, indent=2)
        original_content = json.dumps(content, ensure_ascii=False, indent=2)

        # 构建评分反馈
        score_feedback = (
            f"准确性: {score.accuracy.score}/5 - {score.accuracy.reason}\n"
            f"吸引力: {score.attractiveness.score}/5 - {score.attractiveness.reason}\n"
            f"合规性: {score.compliance.score}/5 - {score.compliance.reason}\n"
            f"SEO覆盖: {score.seo.score}/5 - {score.seo.reason}\n"
            f"总分: {score.total}/5"
        )

        compliance_str = "无问题"
        if compliance_issues:
            compliance_str = json.dumps(compliance_issues, ensure_ascii=False, indent=2)

        user_msg = USER_PROMPT_TEMPLATE.format(
            product_info=product_info,
            original_content=original_content,
            score_feedback=score_feedback,
            compliance_issues=compliance_str,
        )

        result = self.model.chat_json(user_msg, SYSTEM_PROMPT)

        return {
            "optimized_title": result.get("optimized_title", content.get("optimized_title", "")),
            "selling_points": result.get("selling_points", content.get("selling_points", [])),
            "description": result.get("description", content.get("description", "")),
            "social_copy": result.get("social_copy", content.get("social_copy", "")),
            "rewrite_reason": result.get("rewrite_reason", ""),
        }
