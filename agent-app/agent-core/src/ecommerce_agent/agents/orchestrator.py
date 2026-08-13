# -*- coding: utf-8 -*-
"""
Agent 编排器
串联所有 Agent，完成完整的文案生成闭环：

  商品理解 → 文案生成 → SEO → 合规检查 → 质量评分 → (低分重写) → (图片生成) → (视频生成) → 输出

支持三路对比：base_model / fine_tuned / fine_tuned+rewrite
图片和视频生成为可选步骤，通过 generate_image / generate_video 开启
"""

import json
import time
from ecommerce_agent.domain.models import ProductProfile, ContentPackage, QualityScore
from ecommerce_agent.providers.model_client import ModelClient, create_client, ModelConfig, get_mock_client
from ecommerce_agent.providers.video_client import VideoClient, VideoConfig, create_video_client, get_mock_video_client
from ecommerce_agent.providers.image_client import ImageClient, ImageConfig, create_image_client, get_mock_image_client
from ecommerce_agent.agents.product_understanding import ProductUnderstandingAgent
from ecommerce_agent.agents.copywriting import CopywritingAgent
from ecommerce_agent.agents.seo import SEOAgent
from ecommerce_agent.agents.compliance import ComplianceAgent
from ecommerce_agent.agents.judge import JudgeAgent
from ecommerce_agent.agents.rewrite import RewriteAgent
from ecommerce_agent.agents.video_generation import VideoGenerationAgent
from ecommerce_agent.agents.image_generation import ImageGenerationAgent


class ContentOrchestrator:
    """
    内容生成编排器

    用法:
        orchestrator = ContentOrchestrator()
        result = orchestrator.generate(product_profile)
    """

    def __init__(
        self,
        model_client: ModelClient = None,
        max_rewrite_rounds: int = 1,
        video_client: VideoClient = None,
        image_client: ImageClient = None,
    ):
        """
        Args:
            model_client: 模型客户端（默认使用 Mock）
            max_rewrite_rounds: 最大重写轮次（默认 1 轮）
            video_client: 视频生成客户端（默认 None，不启用视频生成）
            image_client: 图片生成客户端（默认 None，不启用图片生成）
        """
        self.model = model_client or get_mock_client()
        self.max_rewrite_rounds = max_rewrite_rounds

        # 初始化各智能体
        self.understanding_agent = ProductUnderstandingAgent(self.model)
        self.copywriting_agent = CopywritingAgent(self.model)
        self.seo_agent = SEOAgent(self.model)
        self.compliance_agent = ComplianceAgent(self.model)
        self.judge_agent = JudgeAgent(self.model)
        self.rewrite_agent = RewriteAgent(self.model)

        # 图片生成 Agent（可选）
        self.image_agent = None
        if image_client is not None:
            self.image_agent = ImageGenerationAgent(self.model, image_client)

        # 视频生成 Agent（可选）
        self.video_agent = None
        if video_client is not None:
            self.video_agent = VideoGenerationAgent(self.model, video_client)

    def generate(
        self,
        product: ProductProfile,
        generate_video: bool = False,
        generate_image: bool = False,
        custom_image_prompt: str = "",
        custom_video_prompt: str = "",
        upstream_video_task_id: str = "",
        on_video_task_created=None,
    ) -> ContentPackage:
        """
        执行完整的文案生成闭环

        流程:
        1. 商品理解（补全卖点/人群）
        2. 文案生成（标题/卖点/描述/社媒）
        3. SEO 关键词
        4. 合规检查
        5. 质量评分
        6. 低分重写（如果未通过阈值）
        7. 图片生成（可选，需要 image_agent）
        8. 视频生成（可选，需要 video_agent）
        9. 返回 ContentPackage
        """
        print(f"\n{'='*60}")
        print(f"开始生成文案: {product.title}")
        print(f"{'='*60}")

        # 第 1 步：商品理解
        print("\n[1/8] 商品理解...")
        understanding = self.understanding_agent.run(product)
        # 更新商品信息（补全卖点等）
        if understanding["selling_points"]:
            product.selling_points = understanding["selling_points"]
        if understanding["target_audience"]:
            product.target_audience = understanding["target_audience"]
        if understanding["price_positioning"]:
            product.price_positioning = understanding["price_positioning"]
        print(f"  卖点: {product.selling_points}")
        print(f"  目标人群: {product.target_audience}")

        # 第 2 步：文案生成
        print("\n[2/8] 文案生成...")
        content = self.copywriting_agent.run(product)
        print(f"  标题: {content['optimized_title']}")
        print(f"  卖点数: {len(content['selling_points'])}")

        # 第 3 步：SEO 关键词
        print("\n[3/8] SEO 关键词...")
        seo_result = self.seo_agent.run(product)
        content["seo_keywords"] = seo_result.get("seo_keywords", [])
        print(f"  关键词: {content['seo_keywords']}")

        # 第 4 步：合规检查
        print("\n[4/8] 合规检查...")
        full_text = f"{content['optimized_title']} {' '.join(content['selling_points'])} {content['description']} {content['social_copy']}"
        compliance = self.compliance_agent.run(product, content=full_text)
        print(f"  合规: {'通过' if compliance['is_compliant'] else '有问题'}")
        if compliance["violations"]:
            print(f"  问题: {compliance['violations']}")

        # 第 5 步：质量评分
        print("\n[5/8] 质量评分...")
        score = self.judge_agent.run(product, content)
        print(f"  准确性: {score.accuracy.score}/5")
        print(f"  吸引力: {score.attractiveness.score}/5")
        print(f"  合规性: {score.compliance.score}/5")
        print(f"  SEO: {score.seo.score}/5")
        print(f"  总分: {score.total}/5 ({'通过' if score.passed else '未通过'})")

        # 第 6 步：低分重写
        rewrite_history = []
        rewrite_reason = ""

        if not score.passed and self.max_rewrite_rounds > 0:
            print(f"\n[6/8] 自动重写 (最多 {self.max_rewrite_rounds} 轮)...")

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

                # 更新内容（保留 SEO 关键词）
                rewritten["seo_keywords"] = content.get("seo_keywords", [])
                content = rewritten
                rewrite_reason = rewritten.get("rewrite_reason", "")
                score = new_score

                print(f"  重写后总分: {score.total}/5 ({'通过' if score.passed else '未通过'})")
                print(f"  修改原因: {rewrite_reason}")

                if score.passed:
                    print(f"  已通过质量阈值，停止重写")
                    break
        else:
            print(f"\n[6/8] 质量达标，无需重写")

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

        # 第 7 步：图片生成（可选）
        if generate_image and self.image_agent is not None:
            print(f"\n[7/8] 图片生成...")
            image_result = self.image_agent.run(
                product=product,
                content=content,
                platform=product.platform,
                custom_prompt=custom_image_prompt,
            )
            package.image = image_result
            print(f"  状态: {image_result.get('status', 'unknown')}")
            if image_result.get("local_path"):
                print(f"  本地路径: {image_result['local_path']}")
            if image_result.get("image_url"):
                print(f"  图片URL: {image_result['image_url']}")
        elif generate_image and self.image_agent is None:
            print(f"\n[7/8] 图片生成跳过（未配置 image_client）")

        # 第 8 步：视频生成（可选）
        if generate_video and self.video_agent is not None:
            print(f"\n[8/8] 视频生成...")
            video_result = self.video_agent.run(
                product=product,
                content=content,
                platform=product.platform,
                custom_prompt=custom_video_prompt,
                upstream_task_id=upstream_video_task_id,
                on_task_created=on_video_task_created,
            )
            package.video = video_result
            print(f"  状态: {video_result.get('status', 'unknown')}")
            if video_result.get("local_path"):
                print(f"  本地路径: {video_result['local_path']}")
            if video_result.get("video_url"):
                print(f"  视频URL: {video_result['video_url']}")
        elif generate_video and self.video_agent is None:
            print(f"\n[8/8] 视频生成跳过（未配置 video_client）")

        print(f"\n{'='*60}")
        print(f"文案生成完成!")
        print(f"  最终评分: {score.total}/5")
        print(f"  重写轮数: {len(rewrite_history)}")
        if generate_image and self.image_agent is not None:
            print(f"  图片生成: {'完成' if package.image else '跳过'}")
        if generate_video and self.video_agent is not None:
            print(f"  视频生成: {'完成' if package.video else '跳过'}")
        print(f"{'='*60}")

        return package

    def generate_dict(self, product_dict: dict) -> dict:
        """便捷方法：输入 dict，输出 dict"""
        product = ProductProfile.from_dict(product_dict)
        package = self.generate(product)
        return package.to_dict()
