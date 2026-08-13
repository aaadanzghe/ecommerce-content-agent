# -*- coding: utf-8 -*-
"""
确定性评估指标（不依赖 LLM Judge）
- ROUGE-L (基于最长公共子序列)
- 长度比
- 2-gram 重复率（检测模板化）
- 首尾完整性
"""

from typing import Dict, List
from collections import defaultdict


def compute_deterministic_metrics(reference: str, generated: str) -> Dict:
    """计算确定性指标"""
    ref_len = len(reference)
    gen_len = len(generated)
    length_ratio = gen_len / max(ref_len, 1)

    # 2-gram 重复率
    def get_ngrams(text, n=2):
        chars = list(text)
        return [tuple(chars[i:i+n]) for i in range(len(chars)-n+1)]

    gen_2grams = get_ngrams(generated, 2)
    if gen_2grams:
        unique_2grams = len(set(gen_2grams))
        repetition_rate = 1 - (unique_2grams / len(gen_2grams))
    else:
        repetition_rate = 0.0

    ends_properly = generated.strip().endswith(('。', '！', '？', '.', '!', '?', '~', '…'))

    return {
        "length_ratio": round(length_ratio, 2),
        "repetition_rate": round(repetition_rate, 3),
        "ends_properly": ends_properly,
        "ref_length": ref_len,
        "gen_length": gen_len,
    }


def compute_rouge_l(reference: str, generated: str) -> Dict:
    """简化版 ROUGE-L（基于最长公共子序列）"""
    try:
        import jieba
    except ImportError:
        # jieba 未安装时退化为字符级
        ref_tokens = list(reference)
        gen_tokens = list(generated)
    else:
        ref_tokens = list(jieba.cut(reference))
        gen_tokens = list(jieba.cut(generated))

    m, n = len(ref_tokens), len(gen_tokens)
    if m == 0 or n == 0:
        return {"rouge_l_f": 0.0, "rouge_l_p": 0.0, "rouge_l_r": 0.0}

    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_tokens[i-1] == gen_tokens[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])

    lcs_len = dp[m][n]
    precision = lcs_len / n if n > 0 else 0
    recall = lcs_len / m if m > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {
        "rouge_l_f": round(f1, 4),
        "rouge_l_p": round(precision, 4),
        "rouge_l_r": round(recall, 4),
    }


def aggregate_results(results: List[Dict]) -> Dict:
    """汇总评估结果"""
    n = len(results)
    if n == 0:
        return {"error": "No results"}

    det_metrics = defaultdict(list)
    rouge_metrics = defaultdict(list)

    for r in results:
        for k, v in r.get("deterministic", {}).items():
            if isinstance(v, (int, float)):
                det_metrics[k].append(v)
        for k, v in r.get("rouge", {}).items():
            rouge_metrics[k].append(v)

    def stats(values):
        if not values:
            return {"mean": 0, "std": 0, "min": 0, "max": 0}
        import numpy as np
        arr = np.array(values)
        return {
            "mean": round(float(np.mean(arr)), 4),
            "std": round(float(np.std(arr)), 4),
            "min": round(float(np.min(arr)), 4),
            "max": round(float(np.max(arr)), 4),
        }

    return {
        "total_samples": n,
        "deterministic": {k: stats(v) for k, v in det_metrics.items()},
        "rouge": {k: stats(v) for k, v in rouge_metrics.items()},
    }


def compare_models(model_results: Dict[str, Dict]) -> Dict:
    """
    对比不同模型的评估结果
    model_results: {"base_model": aggregated, "fine_tuned": aggregated, "fine_tuned_rewrite": aggregated}
    """
    comparison = {}
    for model_name, result in model_results.items():
        summary = result.get("summary", {}) if "summary" in result else result
        comparison[model_name] = {
            "rouge_l_f1": summary.get("rouge", {}).get("rouge_l_f", {}).get("mean", 0),
            "length_ratio": summary.get("deterministic", {}).get("length_ratio", {}).get("mean", 0),
            "repetition_rate": summary.get("deterministic", {}).get("repetition_rate", {}).get("mean", 0),
        }

    # 打印对比表
    print("\n" + "=" * 70)
    print("模型对比")
    print("=" * 70)
    print(f"{'模型':<25} {'ROUGE-L':>10} {'长度比':>8} {'重复率':>8}")
    print("-" * 51)
    for name, metrics in comparison.items():
        print(f"{name:<25} {metrics['rouge_l_f1']:>10.4f} {metrics['length_ratio']:>8.2f} {metrics['repetition_rate']:>8.3f}")
    print("=" * 70)

    return comparison
