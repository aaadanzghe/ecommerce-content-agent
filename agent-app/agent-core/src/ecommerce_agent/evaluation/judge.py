# -*- coding: utf-8 -*-
"""
LLM-as-Judge 批量评估
迁移自 eval/judge.py，适配新的 Agent 架构
用于 base / fine-tuned / fine-tuned+rewrite 三路对比
"""

import json
from pathlib import Path
from typing import Dict, List

from ecommerce_agent.domain.models import ProductProfile, QualityScore
from ecommerce_agent.evaluation.metrics import (
    compute_deterministic_metrics,
    compute_rouge_l,
    aggregate_results,
    compare_models,
)
from ecommerce_agent.providers.model_client import ModelClient, create_client, ModelConfig

PROJECT_DIR = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_DIR / "output" / "eval_results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def evaluate_batch(
    model_client: ModelClient,
    test_data: List[Dict],
    max_samples: int = 200,
    use_judge: bool = True,
) -> Dict:
    """
    批量评估模型

    Args:
        model_client: 模型客户端
        test_data: 测试集（Alpaca 格式）
        max_samples: 最大评估样本数
        use_judge: 是否使用 LLM Judge

    Returns:
        {"samples": [...], "summary": {...}}
    """
    from ecommerce_agent.agents.copywriting import CopywritingAgent
    from ecommerce_agent.agents.judge import JudgeAgent

    test_data = test_data[:max_samples]
    results = []

    copy_agent = CopywritingAgent(model_client)
    judge_agent = JudgeAgent(model_client)

    for i, item in enumerate(test_data):
        print(f"  [{i+1}/{len(test_data)}] 评估中...")

        # 从 Alpaca 格式构建商品信息
        input_data = json.loads(item.get("input", "{}"))
        product = ProductProfile(
            title=input_data.get("title", ""),
            category=input_data.get("category", "other"),
            attributes=input_data.get("attributes", {}),
        )

        reference = item.get("output", "")

        # 生成文案
        content = copy_agent.run(product)

        # 确定性指标
        det = compute_deterministic_metrics(reference, content.get("description", ""))
        rouge = compute_rouge_l(reference, content.get("description", ""))

        result = {
            "input": item.get("input", ""),
            "reference": reference,
            "generated": content,
            "deterministic": det,
            "rouge": rouge,
        }

        # 大语言模型评分（可选）
        if use_judge:
            score = judge_agent.run(product, content)
            result["judge_score"] = score.to_dict()

        results.append(result)

    summary = aggregate_results(results)
    return {"samples": results, "summary": summary}


def three_way_compare(
    base_client: ModelClient,
    finetuned_client: ModelClient,
    test_data: List[Dict],
    max_samples: int = 50,
    output_path: Path = None,
) -> Dict:
    """
    三路对比：base_model / fine_tuned / fine_tuned+rewrite

    Args:
        base_client: 基座模型客户端
        finetuned_client: 微调模型客户端
        test_data: 测试集
        max_samples: 评估样本数
        output_path: 结果保存路径

    Returns:
        对比结果 dict
    """
    if output_path is None:
        output_path = OUTPUT_DIR / "three_way_comparison.json"

    print("\n" + "=" * 60)
    print("三路对比评估")
    print("=" * 60)

    # 1. 基座模型
    print("\n[1/3] 评估 Base Model...")
    base_results = evaluate_batch(base_client, test_data, max_samples, use_judge=True)

    # 2. 微调模型
    print("\n[2/3] 评估 Fine-tuned Model...")
    ft_results = evaluate_batch(finetuned_client, test_data, max_samples, use_judge=True)

    # 3. 微调模型加重写
    print("\n[3/3] 评估 Fine-tuned + Rewrite...")
    from ecommerce_agent.agents.orchestrator import ContentOrchestrator

    rewrite_results = []
    for i, item in enumerate(test_data[:max_samples]):
        print(f"  [{i+1}/{max_samples}] 重写评估中...")
        input_data = json.loads(item.get("input", "{}"))
        product = ProductProfile(
            title=input_data.get("title", ""),
            category=input_data.get("category", "other"),
            attributes=input_data.get("attributes", {}),
        )

        orchestrator = ContentOrchestrator(finetuned_client, max_rewrite_rounds=1)
        package = orchestrator.generate(product)

        reference = item.get("output", "")
        det = compute_deterministic_metrics(reference, package.description)
        rouge = compute_rouge_l(reference, package.description)

        rewrite_results.append({
            "input": item.get("input", ""),
            "reference": reference,
            "generated": package.to_dict(),
            "deterministic": det,
            "rouge": rouge,
            "judge_score": package.quality_score.to_dict() if package.quality_score else None,
        })

    rewrite_summary = aggregate_results(rewrite_results)

    # 对比
    comparison = compare_models({
        "base_model": base_results["summary"],
        "fine_tuned": ft_results["summary"],
        "fine_tuned_rewrite": rewrite_summary,
    })

    # 保存完整结果
    full_result = {
        "comparison": comparison,
        "base_model_summary": base_results["summary"],
        "fine_tuned_summary": ft_results["summary"],
        "fine_tuned_rewrite_summary": rewrite_summary,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(full_result, f, ensure_ascii=False, indent=2)

    print(f"\n三路对比结果已保存: {output_path}")
    return full_result


# ============================================================
# 命令行入口
# ============================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="电商文案质量评估")
    parser.add_argument("--test_file", type=str, default="data/labeled/test.json")
    parser.add_argument("--model_path", type=str, default=None)
    parser.add_argument("--lora_path", type=str, default=None)
    parser.add_argument("--max_samples", type=int, default=200)
    parser.add_argument("--output", type=str, default="output/eval_results")

    args = parser.parse_args()

    test_file = PROJECT_DIR / args.test_file
    if test_file.exists():
        with open(test_file, "r", encoding="utf-8") as f:
            test_data = json.load(f)
        print(f"加载测试数据: {len(test_data)} 条")
    else:
        print(f"测试集不存在: {test_file}")
        exit(1)

    # 创建模型客户端
    if args.model_path:
        config = ModelConfig(
            backend="transformers",
            model_path=args.model_path,
            lora_path=args.lora_path,
        )
        client = create_client(config)
    else:
        print("未指定模型路径，使用 Mock 客户端")
        from ecommerce_agent.providers.model_client import get_mock_client
        client = get_mock_client()

    results = evaluate_batch(client, test_data, args.max_samples)

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)
    with open(output_path / "eval_results.json", "w", encoding="utf-8") as f:
        json.dump(results["summary"], f, ensure_ascii=False, indent=2)

    print(f"\n评估完成！结果已保存至: {output_path / 'eval_results.json'}")
