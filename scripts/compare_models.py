# -*- coding: utf-8 -*-
"""
三路对比评估脚本
对比: base_model vs fine_tuned vs fine_tuned + rewrite

用法:
    # 需要 GPU：对比真实模型
    python scripts/compare_models.py --base models/Qwen3-14B-Instruct --lora output/ecommerce_qlora_sft --test data/labeled/test.json

    # Mock 模式：验证流程（无需 GPU）
    python scripts/compare_models.py --mock
"""

import json
import sys
import argparse
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.inference.model_client import create_client, ModelConfig, get_mock_client
from src.evaluation.judge import three_way_compare


def main():
    parser = argparse.ArgumentParser(description="三路对比评估: base vs fine-tuned vs rewrite")
    parser.add_argument("--base", type=str, default=None,
                        help="基座模型路径")
    parser.add_argument("--lora", type=str, default=None,
                        help="LoRA adapter 路径")
    parser.add_argument("--test", type=str, default="data/labeled/test.json",
                        help="测试集路径")
    parser.add_argument("--max_samples", type=int, default=50,
                        help="最大评估样本数")
    parser.add_argument("--output", type=str, default="output/eval_results/three_way.json",
                        help="结果输出路径")
    parser.add_argument("--mock", action="store_true",
                        help="Mock 模式（无需 GPU）")

    args = parser.parse_args()

    # 加载测试数据
    test_file = PROJECT_DIR / args.test
    if test_file.exists():
        with open(test_file, "r", encoding="utf-8") as f:
            test_data = json.load(f)
        print(f"测试集: {len(test_data)} 条")
    else:
        print(f"测试集不存在: {test_file}")
        sys.exit(1)

    if args.mock:
        print("使用 Mock 客户端（无需 GPU）")
        base_client = get_mock_client()
        ft_client = get_mock_client()
    else:
        if not args.base:
            print("错误: 请指定 --base 模型路径，或使用 --mock")
            sys.exit(1)

        base_config = ModelConfig(backend="transformers", model_path=args.base)
        base_client = create_client(base_config)

        if args.lora and Path(args.lora).exists():
            ft_config = ModelConfig(backend="transformers", model_path=args.base, lora_path=args.lora)
        else:
            print("警告: 未找到 LoRA，fine_tuned 和 base 使用相同模型")
            ft_config = base_config
        ft_client = create_client(ft_config)

    result = three_way_compare(
        base_client, ft_client, test_data,
        max_samples=args.max_samples,
        output_path=Path(args.output),
    )

    print("\n对比完成！")
    print(f"结果已保存: {args.output}")


if __name__ == "__main__":
    main()
