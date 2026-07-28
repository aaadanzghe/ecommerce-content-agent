# -*- coding: utf-8 -*-
"""
模型下载脚本
支持 HuggingFace / ModelScope 镜像下载
"""

import argparse
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
MODEL_DIR = PROJECT_DIR / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# 模型配置
MODELS = {
    "qwen3-14b": {
        "hf_id": "Qwen/Qwen2.5-14B-Instruct",
        "ms_id": "qwen/Qwen2.5-14B-Instruct",
        "size_gb": 28,
        "description": "本地开发用 (5070 Ti 12GB)"
    },
    "qwen3-moe": {
        "hf_id": "Qwen/Qwen3.5-35B-A3B-Instruct",
        "ms_id": "qwen/Qwen3.5-35B-A3B-Instruct",
        "size_gb": 70,
        "description": "云端部署用 (A100 40GB+)"
    },
    "qwen3-8b": {
        "hf_id": "Qwen/Qwen2.5-7B-Instruct",
        "ms_id": "qwen/Qwen2.5-7B-Instruct",
        "size_gb": 16,
        "description": "轻量替代 (显存充裕)"
    }
}


def download_from_hf(model_id: str, local_dir: str, mirror: str = None):
    """从 HuggingFace 下载"""
    from huggingface_hub import snapshot_download
    
    print(f"从 HuggingFace 下载: {model_id}")
    if mirror:
        os.environ["HF_ENDPOINT"] = mirror
    
    snapshot_download(
        repo_id=model_id,
        local_dir=local_dir,
        local_dir_use_symlinks=False,
        resume_download=True,
        max_workers=4
    )
    print(f"下载完成: {local_dir}")


def download_from_modelscope(model_id: str, local_dir: str):
    """从 ModelScope 下载"""
    from modelscope import snapshot_download
    
    print(f"从 ModelScope 下载: {model_id}")
    snapshot_download(
        model_id=model_id,
        local_dir=local_dir,
        revision="master"
    )
    print(f"下载完成: {local_dir}")


def main():
    parser = argparse.ArgumentParser(description="模型下载脚本")
    parser.add_argument("--model", type=str, default="qwen3-14b",
                        choices=list(MODELS.keys()),
                        help="要下载的模型")
    parser.add_argument("--source", type=str, default="modelscope",
                        choices=["huggingface", "modelscope", "hf-mirror"],
                        help="下载源 (modelscope 国内更快)")
    parser.add_argument("--output", type=str, default=None,
                        help="输出目录 (默认: models/<model_name>)")
    
    args = parser.parse_args()
    
    model_info = MODELS[args.model]
    output_dir = args.output or str(MODEL_DIR / args.model)
    
    print("=" * 60)
    print(f"下载模型: {args.model}")
    print(f"描述: {model_info['description']}")
    print(f"大小: ~{model_info['size_gb']} GB")
    print(f"输出: {output_dir}")
    print("=" * 60)
    
    # 检查磁盘空间
    import shutil
    free_gb = shutil.disk_usage(output_dir).free / 1024**3
    if free_gb < model_info['size_gb'] * 1.2:
        print(f"警告: 磁盘空间不足! 需要 ~{model_info['size_gb']*1.2:.0f} GB, 可用 {free_gb:.0f} GB")
        return
    
    # 下载
    if args.source == "modelscope":
        download_from_modelscope(model_info["ms_id"], output_dir)
    elif args.source == "hf-mirror":
        download_from_hf(model_info["hf_id"], output_dir, mirror="https://hf-mirror.com")
    else:
        download_from_hf(model_info["hf_id"], output_dir)


if __name__ == "__main__":
    main()