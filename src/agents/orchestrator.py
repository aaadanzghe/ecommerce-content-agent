# -*- coding: utf-8 -*-
"""
Agent 编排器
串联所有 Agent，完成完整的文案生成闭环：

  商品理解 → 文案生成 → SEO → 合规检查 → 质量评分 → (低分重写) → 输出

支持三路对比：base_model / fine_tuned / fine_tuned+rewrite
"""

import json
import time
from src.schemas import ProductProfile, ContentPackage, QualityScore
from src.inference.model_client import ModelClient, create_client, ModelConfig, get_mock_client
from src.agents.product_understanding import ProductUnderstandingAgent
from src.agents.copywriting import CopywritingAgent
from src.agents.seo import SEOAgent
from src.agents.compliance import ComplianceAgent
from src.agents.judge import JudgeAgent
from src.agents.rewrite import RewriteAgent


class ContentOrchestrator:
    """
    内容生成编排器

    用法:
        orchestrator = ContentOrchestrator()
        result = orchestrator.generate(product_profile)
    """

    def __init__(self, model_client: ModelClient = None, max_rewrite_rounds: int = 1):
        """
        Args:
            model_client: 模型客户端（默认使用 Mock）
            max_rewrite_rounds: 最大重写轮次（默认 1 轮）
        """
        self.model = model_client or get_mock_client()
        self.max_rewrite_rounds = max_rewrite_rounds

        # 初始化各 Agent
        self.understanding_agent = ProductUnderstandingAgent(self.model)
        self.copywriting_agent = CopywritingAgent(self.model)
        self.seo_agent = SEOAgent(self.model)
        self.compliance_agent = ComplianceAgent(self.model)
        self.judge_agent = JudgeAgent(self.model)
        self.rewrite_agent = RewriteAgent(self.model)

    def generate(self, product: ProductProfile) -> ContentPackage:
        """
        执行完整的文案生成闭环

        流程:
        1. 商品理解（补全卖点/人群）
        2. 文案生成（标题/卖点/描述/社媒）
        3. SEO 关键词
        4. 合规检查
        5. 质量评分
        6. 低分重写（如果未通过阈值）
        7. 返回 ContentPackage
        """
        print(f"\n{'='*60}")
        print(f"开始生成文案: {product.title}")
        print(f"{'='*60}")

        # Step 1: 商品理解
        print("\n[1/6] 商品理解...")
        understanding = self.understanding_agent.run(product)
        # 更新 product（补全卖点等）
        if understanding["selling_points"]:
            product.selling_points = understanding["selling_points"]
        if understanding["target_audience"]:
            product.target_audience = understanding["target_audience"]
        if understanding["price_positioning"]:
            product.price_positioning = understanding["price_positioning"]
        print(f"  卖点: {product.selling_points}")
        print(f"  目标人群: {product.target_audience}")

        # Step 2: 文案生成
        print("\n[2/6] 文案生成...")
        content = self.copywriting_agent.run(product)
        print(f"  标题: {content['optimized_title']}")
        print(f"  卖点数: {len(content['selling_points'])}")

        # Step 3: SEO 关键词
        print("\n[3/6] SEO 关键词...")
        seo_result = self.seo_agent.run(product)
        content["seo_keywords"] = seo_result.get("seo_keywords", [])
        print(f"  关键词: {content['seo_keywords']}")

        # Step 4: 合规检查
        print("\n[4/6] 合规检查...")
        full_text = f"{content['optimized_title']} {' '.join(content['selling_points'])} {content['description']} {content['social_copy']}"
        compliance = self.compliance_agent.run(product, content=full_text)
        print(f"  合规: {'通过' if compliance['is_compliant'] else '有问题'}")
        if compliance["violations"]:
            print(f"  问题: {compliance['violations']}")

        # Step 5: 质量评分
        print("\n[5/6] 质量评分...")
        score = self.judge_agent.run(product, content)
        print(f"  准确性: {score.accuracy.score}/5")
        print(f"  吸引力: {score.attractiveness.score}/5")
        print(f"  合规性: {score.compliance.score}/5")
        print(f"  SEO: {score.seo.score}/5")
        print(f"  总分: {score.total}/5 ({'通过' if score.passed else '未通过'})")

        # Step 6: 低分重写
        rewrite_history = []
        rewrite_reason = ""

        if not score.passed and self.max_rewrite_rounds > 0:
            print(f"\n[6/6] 自动重写 (最多 {self.max_rewrite_rounds} 轮)...")

            for round_num in range(1, self.max_rewrite_rounds + 1):
                print(f"\n  --- 重写第 {round_num} 轮 ---")

                rewritten = self.rewrite_agent.run(
                    product, content, score,
                    compliance_issues=compliance["violations"] if not compliance["is_compliant"] else None,
                )

                # 重新评分
                new_score = self.judge_agent.run(product, rewritten)

                rewrite_history.append({
                    "round": round_num,
                    "before_score": score.to_dict(),
                    "after_score": new_score.to_dict(),
                    "rewrite_reason": rewritten.get("rewrite_reason", ""),
                })

                # 更新内容
                content = rewritten
                rewrite_reason = rewritten.get("rewrite_reason", "")
                score = new_score

                print(f"  重写后总分: {score.total}/5 ({'通过' if score.passed else '未通过'})")
                print(f"  修改原因: {rewrite_reason}")

                if score.passed:
                    print(f"  已通过质量阈值，停止重写")
                    break
        else:
            print(f"\n[6/6] 质量达标，无需重写")

        # 组装最终输出
        package = ContentPackage(
            optimized_title=content.get("optimized_title", ""),
            selling_points=content.get("selling_points", []),
            description=content.get("description", ""),
            seo_keywords=content.get("seo_keywords", []),
            social_copy=content.get("social_copy", ""),
            quality_score=score,
            rewrite_reason=rewrite_reason,
            rewrite_history=rewrite_history,
            platform=product.platform,
        )

        print(f"\n{'='*60}")
        print(f"文案生成完成!")
        print(f"  最终评分: {score.total}/5")
        print(f"  重写轮数: {len(rewrite_history)}")
        print(f"{'='*60}")

        return package

    def generate_dict(self, product_dict: dict) -> dict:
        """便捷方法：输入 dict，输出 dict"""
        product = ProductProfile.from_dict(product_dict)
        package = self.generate(product)
        return package.to_dict()
