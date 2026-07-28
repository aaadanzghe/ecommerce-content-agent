# -*- coding: utf-8 -*-
"""
vLLM 推理部署脚本
支持 LoRA Adapter 热加载和 API 服务
适配: 本地 RTX 5070 Ti 12GB / 云端 A100 40GB
"""

import json
import argparse
from pathlib import Path
from typing import Optional, List

PROJECT_DIR = Path(__file__).parent.parent


def build_vllm_command(
    model_path: str,
    lora_path: Optional[str] = None,
    port: int = 8000,
    max_model_len: int = 4096,
    gpu_memory_utilization: float = 0.90,
    tensor_parallel_size: int = 1,
    dtype: str = "auto",
    quantization: Optional[str] = None,
    enforce_eager: bool = False,
    max_lora_rank: int = 64,
    max_loras: int = 4,
    enable_lora: bool = False,
    extra_args: Optional[List[str]] = None
) -> str:
    """
    构建 vLLM 启动命令
    
    参数:
    - model_path: 基座模型路径
    - lora_path: LoRA adapter 路径（可选）
    - port: API 端口
    - max_model_len: 最大序列长度
    - gpu_memory_utilization: GPU 显存利用率
    - tensor_parallel_size: 张量并行数
    - dtype: 计算精度
    - quantization: 量化方式 (None, "awq", "gptq", "fp8")
    - enforce_eager: 是否禁用 CUDA graph（节省显存）
    - max_lora_rank: 最大 LoRA rank
    - max_loras: 最大同时加载的 LoRA adapter 数
    - enable_lora: 是否启用 LoRA
    """
    cmd_parts = [
        "python -m vllm.entrypoints.openai.api_server",
        f"--model {model_path}",
        f"--port {port}",
        f"--max-model-len {max_model_len}",
        f"--gpu-memory-utilization {gpu_memory_utilization}",
        f"--tensor-parallel-size {tensor_parallel_size}",
        f"--dtype {dtype}",
        f"--served-model-name ecommerce-copywriter",
    ]
    
    if quantization:
        cmd_parts.append(f"--quantization {quantization}")
    
    if enforce_eager:
        cmd_parts.append("--enforce-eager")
    
    if enable_lora:
        cmd_parts.append("--enable-lora")
        cmd_parts.append(f"--max-lora-rank {max_lora_rank}")
        cmd_parts.append(f"--max-loras {max_loras}")
        if lora_path:
            cmd_parts.append(f"--lora-modules ecommerce-lora={lora_path}")
    
    if extra_args:
        cmd_parts.extend(extra_args)
    
    return " \\\n    ".join(cmd_parts)


def build_client_example(port: int = 8000, lora_name: str = "ecommerce-lora"):
    """生成客户端调用示例"""
    return f"""
# ============================================================
# Python 客户端调用示例
# ============================================================

from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:{port}/v1",
    api_key="not-needed"
)

# 调用示例
response = client.completions.create(
    model="{lora_name}",
    prompt='''你是一名专业的电商文案撰写师。请根据以下商品信息，生成一段吸引人的商品描述文案。

{{"category": "3c_digital", "title": "XX品牌 TWS Pro 真无线降噪耳机"}}''',
    max_tokens=512,
    temperature=0.7,
    top_p=0.9,
    extra_body={{
        "stop_token_ids": [151645]
    }}
)

print(response.choices[0].text)
"""


def main():
    parser = argparse.ArgumentParser(
        description="vLLM 推理服务启动器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 本地 5070 Ti 12GB - Qwen3-14B + LoRA
  python inference/vllm_serve.py \\
      --model Qwen/Qwen2.5-14B-Instruct \\
      --lora output/ecommerce_qlora_sft \\
      --gpu-memory 0.88 \\
      --enforce-eager

  # 云端 A100 40GB - Qwen3.5-35B-A3B MoE
  python inference/vllm_serve.py \\
      --model Qwen/Qwen3.5-35B-A3B-Instruct \\
      --lora output/ecommerce_grpo_aligned \\
      --gpu-memory 0.92 \\
      --tensor-parallel 1

  # 仅打印启动命令（不执行）
  python inference/vllm_serve.py --dry-run --model Qwen/Qwen2.5-14B-Instruct
        """
    )
    
    parser.add_argument("--model", type=str, required=True,
                        help="基座模型路径或 HuggingFace ID")
    parser.add_argument("--lora", type=str, default=None,
                        help="LoRA adapter 路径")
    parser.add_argument("--port", type=int, default=8000,
                        help="API 端口 (默认: 8000)")
    parser.add_argument("--max-model-len", type=int, default=4096,
                        help="最大序列长度 (默认: 4096)")
    parser.add_argument("--gpu-memory", type=float, default=0.90,
                        help="GPU 显存利用率 (默认: 0.90)")
    parser.add_argument("--tensor-parallel", type=int, default=1,
                        help="张量并行数 (默认: 1)")
    parser.add_argument("--dtype", type=str, default="auto",
                        choices=["auto", "float16", "bfloat16", "fp8"],
                        help="计算精度 (默认: auto)")
    parser.add_argument("--quantization", type=str, default=None,
                        choices=["awq", "gptq", "fp8"],
                        help="量化方式")
    parser.add_argument("--enforce-eager", action="store_true",
                        help="禁用 CUDA graph（节省显存，推荐 12GB 显卡开启）")
    parser.add_argument("--no-lora", action="store_true",
                        help="不启用 LoRA")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅打印命令，不执行")
    
    args = parser.parse_args()
    
    enable_lora = not args.no_lora and args.lora is not None
    
    # 构建命令
    cmd = build_vllm_command(
        model_path=args.model,
        lora_path=args.lora,
        port=args.port,
        max_model_len=args.max_model_len,
        gpu_memory_utilization=args.gpu_memory,
        tensor_parallel_size=args.tensor_parallel,
        dtype=args.dtype,
        quantization=args.quantization,
        enforce_eager=args.enforce_eager,
        enable_lora=enable_lora
    )
    
    print("=" * 70)
    print("vLLM 推理服务")
    print("=" * 70)
    print(f"模型: {args.model}")
    if enable_lora:
        print(f"LoRA: {args.lora}")
    print(f"端口: {args.port}")
    print(f"显存利用率: {args.gpu_memory}")
    print(f"最大序列长度: {args.max_model_len}")
    print()
    
    if args.dry_run:
        print("启动命令 (dry-run):")
        print("-" * 70)
        print(cmd)
        print("-" * 70)
    else:
        print("启动命令:")
        print("-" * 70)
        print(cmd)
        print("-" * 70)
    
    # 打印客户端示例
    lora_name = "ecommerce-lora" if enable_lora else "ecommerce-copywriter"
    print(build_client_example(port=args.port, lora_name=lora_name))


if __name__ == "__main__":
    main()