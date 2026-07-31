# -*- coding: utf-8 -*-
"""
合规检查 Agent
检查虚假宣传、绝对化用语、敏感词和事实不一致
"""

import json
import re
from src.agents.base import BaseAgent
from src.schemas import ProductProfile

# 广告法违禁词（简化版）
FORBIDDEN_WORDS = [
    "最", "第一", "顶级", "国家级", "世界级", "唯一", "首个", "首选",
    "绝佳", "万能", "永久", "百分百", "100%", "绝对", "极致", "冠军",
    "之王", "之王", "霸主", "巅峰", "空前", "史无前例", "绝无仅有",
]

SYSTEM_PROMPT = """你是一名电商合规审核专家。你的任务是检查电商文案是否违反广告法和平台规则。"""

USER_PROMPT_TEMPLATE = """请检查以下电商文案是否合规。

商品原始信息：
{product_info}

待检查文案：
{content}

请以 JSON 格式输出：
{{
  "is_compliant": true/false,
  "violations": [
    {{
      "type": "absolute_words/fake_claim/sensitive_word/factual_error",
      "content": "违规内容",
      "suggestion": "修改建议"
    }}
  ],
  "risk_level": "low/medium/high",
  "summary": "总体合规评价"
}}

检查要点：
1. absolute_words: 绝对化用语（最、第一、顶级等）
2. fake_claim: 虚假宣传（虚构认证、夸大功效）
3. sensitive_word: 敏感词
4. factual_error: 文案信息与商品原始信息不一致"""


class ComplianceAgent(BaseAgent):
    """合规检查 Agent"""

    name = "compliance"
    description = "检查虚假宣传、绝对化用语、敏感词和事实不一致"

    # 确定性检查：违禁词
    @staticmethod
    def check_forbidden_words(text: str) -> list:
        """检查违禁词（确定性规则，不依赖 LLM）"""
        violations = []
        for word in FORBIDDEN_WORDS:
            if word in text:
                violations.append({
                    "type": "absolute_words",
                    "content": word,
                    "suggestion": f"删除或替换「{word}」"
                })
        return violations

    def run(self, product: ProductProfile, content: str = "", **kwargs) -> dict:
        """
        检查文案合规性

        Args:
            product: 商品信息
            content: 待检查的文案（如果为空，检查 product 中所有文本）
        """
        if not content:
            content = f"{product.title} {' '.join(product.selling_points)}"

        product_info = json.dumps(product.to_prompt_dict(), ensure_ascii=False, indent=2)
        user_msg = USER_PROMPT_TEMPLATE.format(
            product_info=product_info,
            content=content,
        )

        result = self.model.chat_json(user_msg, SYSTEM_PROMPT)

        # 合并确定性检查和 LLM 检查
        deterministic_violations = self.check_forbidden_words(content)
        llm_violations = result.get("violations", [])

        # 去重
        all_violations = deterministic_violations + llm_violations
        seen = set()
        unique_violations = []
        for v in all_violations:
            key = v.get("content", "")
            if key not in seen:
                seen.add(key)
                unique_violations.append(v)

        is_compliant = len(unique_violations) == 0 and result.get("is_compliant", True)
        risk_level = result.get("risk_level", "low")
        if deterministic_violations and risk_level == "low":
            risk_level = "medium"

        return {
            "is_compliant": is_compliant,
            "violations": unique_violations,
            "risk_level": risk_level,
            "summary": result.get("summary", ""),
        }
