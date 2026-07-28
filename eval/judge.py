# -*- coding: utf-8 -*-
"""
LLM-as-Judge 四维评估脚本
评估维度: 准确性 / 吸引力 / 合规性 / SEO关键词覆盖
用途: SFT 后量化评估、GRPO Reward Model、消融实验对比
"""

import json
import re
import time
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_DIR = PROJECT_DIR / "output" / "eval_results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 评估 Prompt 模板
# ============================================================
JUDGE_SYSTEM_PROMPT = """你是一个严格的电商文案质量评估专家。请对给定的商品信息和生成的文案，从四个维度打分（1-5分）：

1. **准确性 (Accuracy)**：文案中的信息是否与商品信息一致？有无虚构、夸大或遗漏？
2. **吸引力 (Attractiveness)**：文案是否具有营销吸引力？语言是否流畅、有感染力？能否激发购买欲望？
3. **合规性 (Compliance)**：文案是否违反广告法（如使用"最""第一""国家级"等极限词）？是否包含虚假宣传？
4. **SEO覆盖 (SEO Coverage)**：文案是否自然涵盖了商品核心关键词？关键词密度是否合理？

评分标准:
- 1分: 严重问题，完全不合格
- 2分: 存在明显缺陷
- 3分: 基本合格，有改进空间
- 4分: 良好，符合预期
- 5分: 优秀，超出预期

请严格按照以下 JSON 格式输出，不要包含任何其他内容：
{
  "accuracy": {"score": 整数1-5, "reason": "简要理由"},
  "attractiveness": {"score": 整数1-5, "reason": "简要理由"},
  "compliance": {"score": 整数1-5, "reason": "简要理由"},
  "seo": {"score": 整数1-5, "reason": "简要理由"},
  "overall_comment": "总体评价（一句话）"
}"""


def build_judge_prompt(product_info: str, generated_copy: str) -> str:
    """构建 LLM Judge 评估 prompt"""
    return f"""## 商品信息
{product_info}

## 生成的文案
{generated_copy}

请对以上文案进行四维评估，输出 JSON 格式。"""


def parse_judge_output(text: str) -> Optional[Dict]:
    """解析 LLM Judge 的 JSON 输出"""
    # 提取 JSON 块
    json_match = re.search(r'\{[\s\S]*\}', text)
    if not json_match:
        return None
    
    try:
        result = json.loads(json_match.group())
        return result
    except json.JSONDecodeError:
        return None


def compute_weighted_score(scores: Dict) -> float:
    """计算加权总分"""
    weights = {
        "accuracy": 0.35,
        "attractiveness": 0.30,
        "compliance": 0.20,
        "seo": 0.15
    }
    total = 0.0
    for dim, weight in weights.items():
        if dim in scores:
            total += scores[dim].get("score", 3) * weight
    return round(total, 2)


# ============================================================
# 确定性指标（不依赖 LLM Judge）
# ============================================================
def compute_deterministic_metrics(reference: str, generated: str) -> Dict:
    """
    计算确定性指标
    - 长度比
    - 重复度 (n-gram 重复率)
    - 词表覆盖率
    """
    # 长度比
    ref_len = len(reference)
    gen_len = len(generated)
    length_ratio = gen_len / max(ref_len, 1)
    
    # 2-gram 重复率（检测文案是否有模板化重复）
    def get_ngrams(text, n=2):
        chars = list(text)
        return [tuple(chars[i:i+n]) for i in range(len(chars)-n+1)]
    
    gen_2grams = get_ngrams(generated, 2)
    if gen_2grams:
        unique_2grams = len(set(gen_2grams))
        repetition_rate = 1 - (unique_2grams / len(gen_2grams))
    else:
        repetition_rate = 0.0
    
    # 首尾完整性（是否以合理标点结尾）
    ends_properly = generated.strip().endswith(('。', '！', '？', '.', '!', '?', '~', '…'))
    
    return {
        "length_ratio": round(length_ratio, 2),
        "repetition_rate": round(repetition_rate, 3),
        "ends_properly": ends_properly,
        "ref_length": ref_len,
        "gen_length": gen_len
    }


def compute_rouge_like(reference: str, generated: str) -> Dict:
    """
    简化版 ROUGE-L 计算（不依赖 rouge 库）
    基于最长公共子序列
    """
    import jieba
    
    ref_tokens = list(jieba.cut(reference))
    gen_tokens = list(jieba.cut(generated))
    
    # LCS 长度
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
        "rouge_l_r": round(recall, 4)
    }


# ============================================================
# 批量评估
# ============================================================
def evaluate_model(
    model,
    tokenizer,
    test_data: List[Dict],
    batch_size: int = 4,
    use_judge: bool = False,
    judge_model=None,
    judge_tokenizer=None,
    max_samples: int = 200
) -> Dict:
    """
    批量评估模型
    - 确定性指标: 全部样本
    - LLM Judge: 抽样 max_samples 条
    """
    import torch
    from tqdm import tqdm
    
    test_data = test_data[:len(test_data)]  # 复制
    results = []
    
    for i in tqdm(range(0, len(test_data), batch_size), desc="评估中"):
        batch = test_data[i:i+batch_size]
        
        # 构建 prompt
        prompts = []
        for item in batch:
            instruction = item.get("instruction", "")
            inp = item.get("input", "")
            full_prompt = f"{instruction}\n\n{inp}"
            prompts.append(full_prompt)
        
        # 生成
        inputs = tokenizer(prompts, return_tensors="pt", padding=True, truncation=True, max_length=1024)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                pad_token_id=tokenizer.pad_token_id
            )
        
        generated = tokenizer.batch_decode(outputs, skip_special_tokens=True)
        
        # 提取生成部分（去掉 prompt）
        for j, item in enumerate(batch):
            gen_text = generated[j]
            # 尝试去掉 prompt 部分
            prompt_text = prompts[j]
            if gen_text.startswith(prompt_text):
                gen_text = gen_text[len(prompt_text):].strip()
            
            ref = item.get("output", "")
            
            result = {
                "input": item.get("input", ""),
                "reference": ref,
                "generated": gen_text,
                "deterministic": compute_deterministic_metrics(ref, gen_text),
                "rouge": compute_rouge_like(ref, gen_text)
            }
            results.append(result)
    
    # 汇总统计
    summary = aggregate_results(results)
    return {"samples": results, "summary": summary}


def aggregate_results(results: List[Dict]) -> Dict:
    """汇总评估结果"""
    n = len(results)
    if n == 0:
        return {"error": "No results"}
    
    # 确定性指标汇总
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
            "max": round(float(np.max(arr)), 4)
        }
    
    summary = {
        "total_samples": n,
        "deterministic": {k: stats(v) for k, v in det_metrics.items()},
        "rouge": {k: stats(v) for k, v in rouge_metrics.items()}
    }
    
    return summary


# ============================================================
# 消融实验对比
# ============================================================
def ablation_compare(
    model_results: Dict[str, Dict],
    output_path: Path = None
):
    """
    对比不同模型/配置的评估结果
    model_results: {"base_model": aggregated_results, "sft_model": ..., "grpo_model": ...}
    """
    if output_path is None:
        output_path = OUTPUT_DIR / "ablation_comparison.json"
    
    comparison = {}
    for model_name, result in model_results.items():
        summary = result.get("summary", {})
        comparison[model_name] = {
            "rouge_l_f1": summary.get("rouge", {}).get("rouge_l_f", {}).get("mean", 0),
            "length_ratio": summary.get("deterministic", {}).get("length_ratio", {}).get("mean", 0),
            "repetition_rate": summary.get("deterministic", {}).get("repetition_rate", {}).get("mean", 0),
        }
    
    # 输出对比表
    print("\n" + "=" * 70)
    print("消融实验对比")
    print("=" * 70)
    print(f"{'模型':<20} {'ROUGE-L':>10} {'长度比':>8} {'重复率':>8}")
    print("-" * 46)
    for name, metrics in comparison.items():
        print(f"{name:<20} {metrics['rouge_l_f1']:>10.4f} {metrics['length_ratio']:>8.2f} {metrics['repetition_rate']:>8.3f}")
    print("=" * 70)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)
    
    print(f"\n消融实验结果已保存: {output_path}")
    return comparison


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="电商文案质量评估")
    parser.add_argument("--test_file", type=str, default="data/labeled/test.json",
                        help="测试集路径")
    parser.add_argument("--model_path", type=str, default=None,
                        help="模型路径")
    parser.add_argument("--lora_path", type=str, default=None,
                        help="LoRA adapter 路径")
    parser.add_argument("--max_samples", type=int, default=200,
                        help="最大评估样本数")
    parser.add_argument("--batch_size", type=int, default=4,
                        help="批量大小")
    parser.add_argument("--output", type=str, default="output/eval_results",
                        help="输出目录")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("电商文案质量评估")
    print("=" * 60)
    print(f"测试集: {args.test_file}")
    print(f"模型: {args.model_path or '未指定'}")
    print(f"LoRA: {args.lora_path or '未指定'}")
    print(f"最大样本: {args.max_samples}")
    
    # 加载测试数据
    test_file = PROJECT_DIR / args.test_file
    if test_file.exists():
        with open(test_file, "r", encoding="utf-8") as f:
            test_data = json.load(f)
        print(f"加载测试数据: {len(test_data)} 条")
    else:
        print(f"测试集不存在: {test_file}")
        test_data = []
    
    # 如果指定了模型，运行评估
    if args.model_path and test_data:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
        import torch
        
        print(f"\n加载模型: {args.model_path}")
        tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            args.model_path,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=True
        )
        
        if args.lora_path:
            print(f"加载 LoRA: {args.lora_path}")
            model = PeftModel.from_pretrained(model, args.lora_path)
        
        model.eval()
        
        results = evaluate_model(
            model, tokenizer, test_data[:args.max_samples],
            batch_size=args.batch_size
        )
        
        # 保存结果
        output_path = Path(args.output)
        output_path.mkdir(parents=True, exist_ok=True)
        
        with open(output_path / "eval_results.json", "w", encoding="utf-8") as f:
            # 保存摘要（不保存完整样本以节省空间）
            json.dump(results["summary"], f, ensure_ascii=False, indent=2)
        
        print(f"\n评估完成！结果已保存至: {output_path / 'eval_results.json'}")
        
        # 打印摘要
        summary = results["summary"]
        print(f"\n确定性指标:")
        for metric, stats in summary.get("deterministic", {}).items():
            print(f"  {metric}: mean={stats['mean']:.4f}, std={stats['std']:.4f}")
        
        print(f"\nROUGE-L:")
        rouge = summary.get("rouge", {}).get("rouge_l_f", {})
        print(f"  F1: {rouge.get('mean', 0):.4f} ± {rouge.get('std', 0):.4f}")
    else:
        print("\n未指定模型路径，跳过评估。")
        print("用法示例:")
        print("  python eval/judge.py --model_path Qwen/Qwen2.5-14B-Instruct --lora_path output/ecommerce_qlora_sft")