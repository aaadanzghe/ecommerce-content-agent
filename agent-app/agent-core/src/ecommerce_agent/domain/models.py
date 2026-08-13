# -*- coding: utf-8 -*-
"""
核心数据结构定义
ProductProfile: 商品信息输入
ContentPackage: 内容输出包
QualityScore: 质量评分
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class Platform(str, Enum):
    TAOBAO = "taobao"
    AMAZON = "amazon"
    DOUYIN = "douyin"
    TIKTOK = "tiktok"
    XIAOHONGSHU = "xiaohongshu"


class Tone(str, Enum):
    PROFESSIONAL = "professional"
    CASUAL = "casual"
    TRENDY = "trendy"
    LUXURY = "luxury"
    CUTE = "cute"


@dataclass
class ProductProfile:
    """商品结构化信息 — 整个 Agent 工作流的统一输入"""
    title: str
    category: str
    attributes: Dict[str, str] = field(default_factory=dict)
    selling_points: List[str] = field(default_factory=list)
    target_audience: str = ""
    price_positioning: str = ""          # 低 / 中 / 高
    platform: str = "taobao"
    tone: str = "professional"
    constraints: List[str] = field(default_factory=list)
    # 可选：原始描述（商品详情页优化时使用）
    original_description: str = ""

    def to_prompt_dict(self) -> dict:
        """转为 prompt 友好的 dict（去掉空值）"""
        d = {"title": self.title, "category": self.category}
        if self.attributes:
            d["attributes"] = self.attributes
        if self.selling_points:
            d["selling_points"] = self.selling_points
        if self.target_audience:
            d["target_audience"] = self.target_audience
        if self.price_positioning:
            d["price_positioning"] = self.price_positioning
        if self.platform:
            d["platform"] = self.platform
        if self.tone:
            d["tone"] = self.tone
        if self.constraints:
            d["constraints"] = self.constraints
        if self.original_description:
            d["original_description"] = self.original_description
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ProductProfile":
        return cls(
            title=data["title"],
            category=data.get("category", "other"),
            attributes=data.get("attributes", {}),
            selling_points=data.get("selling_points", []),
            target_audience=data.get("target_audience", ""),
            price_positioning=data.get("price_positioning", ""),
            platform=data.get("platform", "taobao"),
            tone=data.get("tone", "professional"),
            constraints=data.get("constraints", []),
            original_description=data.get("original_description", ""),
        )


@dataclass
class DimensionScore:
    """单维度评分"""
    score: int               # 1-5
    reason: str = ""


@dataclass
class QualityScore:
    """四维质量评分"""
    accuracy: DimensionScore = field(default_factory=lambda: DimensionScore(3))
    attractiveness: DimensionScore = field(default_factory=lambda: DimensionScore(3))
    compliance: DimensionScore = field(default_factory=lambda: DimensionScore(3))
    seo: DimensionScore = field(default_factory=lambda: DimensionScore(3))

    # 权重
    WEIGHTS = {
        "accuracy": 0.35,
        "attractiveness": 0.30,
        "compliance": 0.20,
        "seo": 0.15,
    }

    @property
    def total(self) -> float:
        """加权总分 (1-5)"""
        s = (
            self.accuracy.score * self.WEIGHTS["accuracy"]
            + self.attractiveness.score * self.WEIGHTS["attractiveness"]
            + self.compliance.score * self.WEIGHTS["compliance"]
            + self.seo.score * self.WEIGHTS["seo"]
        )
        return round(s, 2)

    @property
    def passed(self) -> bool:
        """是否通过质量阈值（总分 >= 3.5 且无维度 <= 2）"""
        if self.total < 3.5:
            return False
        for dim in [self.accuracy, self.attractiveness, self.compliance, self.seo]:
            if dim.score <= 2:
                return False
        return True

    def to_dict(self) -> dict:
        return {
            "accuracy": {"score": self.accuracy.score, "reason": self.accuracy.reason},
            "attractiveness": {"score": self.attractiveness.score, "reason": self.attractiveness.reason},
            "compliance": {"score": self.compliance.score, "reason": self.compliance.reason},
            "seo": {"score": self.seo.score, "reason": self.seo.reason},
            "total": self.total,
            "passed": self.passed,
        }


@dataclass
class ContentPackage:
    """内容输出包 — Agent 工作流的统一输出"""
    optimized_title: str = ""
    selling_points: List[str] = field(default_factory=list)
    description: str = ""
    seo_keywords: List[str] = field(default_factory=list)
    social_copy: str = ""             # 社媒推广文案
    quality_score: Optional[QualityScore] = None
    rewrite_reason: str = ""
    rewrite_history: List[dict] = field(default_factory=list)   # 重写记录
    platform: str = "taobao"
    video: Optional[dict] = None      # 视频生成结果（可选）
    image: Optional[dict] = None      # 图片生成结果（可选）

    def to_dict(self) -> dict:
        result = {
            "optimized_title": self.optimized_title,
            "selling_points": self.selling_points,
            "description": self.description,
            "seo_keywords": self.seo_keywords,
            "social_copy": self.social_copy,
            "platform": self.platform,
            "rewrite_reason": self.rewrite_reason,
            "rewrite_history": self.rewrite_history,
        }
        if self.quality_score:
            result["quality_score"] = self.quality_score.to_dict()
        if self.video:
            result["video"] = self.video
        if self.image:
            result["image"] = self.image
        return result
