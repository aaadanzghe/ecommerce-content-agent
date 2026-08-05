# -*- coding: utf-8 -*-
"""
模型下载脚本。

用法:
    python scripts/download_model.py --model qwen3-8b
    python scripts/download_model.py --model qwen3-14b
    python scripts/download_model.py --model qwen3-moe
"""

import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
MODELS_DIR = PROJECT_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_REGISTRY = {
    "qwen3-8b": {
        "hf": "Qwen/Qwen3-8B",
        "ms": "Qwen/Qwen3-8B",
        "output": "Qwen3-8B",
        "desc": "Qwen3-8B Dense (本地训练优先)",
    },
    "qwen3-14b": {
        "hf": "Qwen/Qwen3-14B",
        "ms": "Qwen/Qwen3-14B",
        "output": "Qwen3-14B",
        "desc": "Qwen3-14B Dense (保留方案)",
    },
    "qwen3-moe": {
        "hf": "Qwen/Qwen3.5-35B-A3B-Instruct",
        "ms": "Qwen/Qwen3.5-35B-A3B-Instruct",
        "output": "Qwen3.5-35B-A3B-Instruct",
        "desc": "Qwen3.5-35B-A3B MoE (云端训练)",
    },
}


def download_from_hf(model_id: str, output_dir: Path) -> None:
    """从 HuggingFace 下载到指定目录。"""
    from huggingface_hub import snapshot_download

    print(f"从 HuggingFace 下载: {model_id}")
    snapshot_download(
        repo_id=model_id,
        local_dir=str(output_dir),
        resume_download=True,
    )
    print(f"下载完成: {output_dir}")


def download_from_modelscope(model_id: str, output_dir: Path) -> None:
    """从 ModelScope 下载到指定目录。"""
    from modelscope import snapshot_download

    print(f"从 ModelScope 下载: {model_id}")
    snapshot_download(
        model_id=model_id,
        local_dir=str(output_dir),
    )
    print(f"下载完成: {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="下载预训练模型")
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        choices=sorted(MODEL_REGISTRY),
        help="模型名称",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="modelscope",
        choices=["hf", "modelscope"],
        help="下载来源",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出目录，默认写入 models/{模型目录名}",
    )

    args = parser.parse_args()
    info = MODEL_REGISTRY[args.model]
    output_dir = Path(args.output) if args.output else MODELS_DIR / info["output"]

    if output_dir.exists() and any(output_dir.iterdir()):
        print(f"模型已存在于: {output_dir}")
        print("如需重新下载，请先清空该目录。")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"模型: {info['desc']}")
    print(f"ID: {info[args.source if args.source == 'hf' else 'ms']}")
    print(f"输出: {output_dir}")
    print("=" * 60)

    if args.source == "hf":
        download_from_hf(info["hf"], output_dir)
    else:
        download_from_modelscope(info["ms"], output_dir)

    print("\n下载完成。")
    print(f"模型路径: {output_dir}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消下载。")
        sys.exit(130)
