"""竞品 Listing 洞察：提取模式、证据和风险，避免复制竞品文案。"""
import json
import re
from collections import Counter
from typing import Iterable, List

from src.agents.base import BaseAgent
from src.schemas import ListingInsight, ProductProfile, ReferenceListing


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9+.-]{1,}", text.lower())]


class ListingInsightAgent(BaseAgent):
    name = "listing_insight"
    description = "从参考商品提取关键词、卖点优先级、场景和竞品缺口"

    def run(self, product: ProductProfile, references: Iterable[ReferenceListing] = (), **kwargs) -> dict:
        refs = list(references)
        if not refs:
            return ListingInsight().to_dict()

        counts = Counter(t for r in refs for t in _tokens(" ".join([r.title, r.description, *r.keywords, *r.selling_points])))
        keywords = [word for word, _ in counts.most_common(12)]
        points = [p for r in refs for p in r.selling_points][:10]
        scenes = [p for p in points if any(x in p for x in ("通勤", "运动", "办公", "旅行", "游戏", "居家"))]
        known = " ".join([product.title, product.category, *product.attributes.keys(), *product.attributes.values(), *product.selling_points]).lower()
        gaps = [f"参考商品高频词“{word}”未出现在当前商品事实中" for word in keywords if word not in known][:5]
        evidence = [{"source_url": r.source_url, "title": r.title, "confidence": r.data_confidence} for r in refs]
        insight = ListingInsight(
            keyword_clusters=keywords,
            selling_point_priorities=points,
            scene_patterns=scenes,
            competitor_gaps=gaps,
            evidence_refs=evidence,
        )
        return insight.to_dict()

