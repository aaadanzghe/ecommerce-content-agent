# -*- coding: utf-8 -*-
"""
模型下载脚本
支持从 HuggingFace / ModelScope 下载模型

用法:
    python scripts/download_model.py --model qwen3-14b
    python scripts/download_model.py --model qwen3-moe
"""

import os
import sys
import argparse
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
MODELS_DIR = PROJECT_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_REGISTRY = {
    "qwen3-14b": {
        "hf": "Qwen/Qwen3-14B-Instruct",
        "ms": "qwen/Qwen3-14B-Instruct",
        "desc": "Qwen3-14B Dense (本地训练)",
    },
    "qwen3-moe": {
        "hf": "Qwen/Qwen3.5-35B-A3B-Instruct",
        "ms": "qwen/Qwen3.5-35B-A3B-Instruct",
        "desc": "Qwen3.5-35B-A3B MoE (云端训练)",
    },
}


def download_from_hf(model_id: str, output_dir: Path):
    """从 HuggingFace 下载"""
    from huggingface_hub import snapshot_download
    print(f"从 HuggingFace 下载: {model_id}")
    snapshot_download(
        repo_id=model_id,
        local_dir=str(output_dir),
        local_dir_use_symlinks=False,
        resume_download=True,
    )
    print(f"下载完成: {output_dir}")


def download_from_modelscope(model_id: str, output_dir: Path):
    """从 ModelScope 下载"""
    from modelscope import snapshot_download
    print(f"从 ModelScope 下载: {model_id}")
    snapshot_download(
        model_id,
        cache_dir=str(output_dir.parent),
    )
    print(f"下载完成: {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="下载预训练模型")
    parser.add_argument("--model", type=str, required=True,
                        help="模型名称: qwen3-14b | qwen3-moe")
    parser.add_argument("--source", type=str, default="hf",
                        choices=["hf", "modelscope"],
                        help="下载源")
    parser.add_argument("--output", type=str, default=None,
                        help="输出目录（默认 models/{model}）")

    args = parser.parse_args()

    if args.model not in MODEL_REGISTRY:
        print(f"错误: 不支持的模型 '{args.model}'")
        print(f"支持的模型: {', '.join(MODEL_REGISTRY.keys())}")
        sys.exit(1)

    info = MODEL_REGISTRY[args.model]
    output_dir = Path(args.output) if args.output else MODELS_DIR / info["hf"].split("/")[-1]

    if output_dir.exists() and any(output_dir.iterdir()):
        print(f"模型已存在于: {output_dir}")
        print("如需重新下载，请先删除该目录")
        return

    print("=" * 60)
    print(f"模型: {info['desc']}")
    print(f"ID: {info['hf']}")
    print(f"输出: {output_dir}")
    print("=" * 60)

    if args.source == "hf":
        download_from_hf(info["hf"], output_dir)
    else:
        download_from_modelscope(info["ms"], output_dir)

    print("\n下载完成！")
    print(f"模型路径: {output_dir}")


if __name__ == "__main__":
    main()
