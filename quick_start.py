# -*- coding: utf-8 -*-
"""
快速启动脚本 — 无需 GPU 即可验证 Agent 闭环流程
使用 Mock 模型客户端，演示完整的生成→评分→重写流程

用法:
    python quick_start.py                  # 使用内置示例
    python quick_start.py --product examples/sample_products.json
"""

import json
import sys
from pathlib import Path

# 确保项目根目录在 path 中
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from src.schemas import ProductProfile
from src.inference.model_client import get_mock_client
from src.agents.orchestrator import ContentOrchestrator


def main():
    import argparse

    parser = argparse.ArgumentParser(description="电商内容生产 Agent - 快速启动")
    parser.add_argument("--product", type=str, default=None,
                        help="商品 JSON 文件路径（不指定则使用内置示例）")
    args = parser.parse_args()

    # 加载商品信息
    if args.product:
        with open(args.product, "r", encoding="utf-8") as f:
            products = json.load(f)
    else:
        # 内置示例
        products = [{
            "title": "XX品牌 TWS Pro 真无线降噪耳机",
            "category": "3c_digital",
            "attributes": {
                "蓝牙版本": "5.3",
                "降噪类型": "主动降噪ANC",
                "续航时间": "30小时（含充电仓）",
                "防水等级": "IPX5",
                "驱动单元": "13mm动圈"
            },
            "platform": "taobao",
            "tone": "trendy",
        }]

    # 使用 Mock 客户端创建编排器
    print("使用 Mock 模型客户端（无需 GPU）")
    orchestrator = ContentOrchestrator(get_mock_client(), max_rewrite_rounds=1)

    # 逐个生成
    for i, product_dict in enumerate(products):
        print(f"\n{'#'*60}")
        print(f"# 商品 {i+1}/{len(products)}")
        print(f"{'#'*60}")

        product = ProductProfile.from_dict(product_dict)
        package = orchestrator.generate(product)

        # 打印最终结果
        print(f"\n--- 最终输出 ---")
        print(json.dumps(package.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
