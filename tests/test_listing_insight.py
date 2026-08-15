import unittest

from src.agents.listing_insight import ListingInsightAgent
from src.inference.model_client import get_mock_client
from src.schemas import ProductProfile, ReferenceListing


class ListingInsightTests(unittest.TestCase):
    def test_extracts_patterns_and_evidence_without_references(self):
        product = ProductProfile(title="无线蓝牙耳机", category="3c_digital", attributes={"蓝牙版本": "5.3"})
        ref = ReferenceListing(
            title="主动降噪无线蓝牙耳机",
            source_url="https://example.test/item/1",
            selling_points=["通勤降噪", "30小时续航"],
            keywords=["主动降噪", "蓝牙耳机"],
            data_confidence=0.8,
        )
        result = ListingInsightAgent(get_mock_client()).run(product, references=[ref])
        self.assertIn("主动降噪", result["keyword_clusters"])
        self.assertEqual(result["evidence_refs"][0]["source_url"], ref.source_url)
        self.assertTrue(result["competitor_gaps"])

    def test_empty_references_are_safe(self):
        product = ProductProfile(title="商品", category="other")
        result = ListingInsightAgent(get_mock_client()).run(product)
        self.assertEqual(result["keyword_clusters"], [])
        self.assertEqual(result["evidence_refs"], [])


if __name__ == "__main__":
    unittest.main()
