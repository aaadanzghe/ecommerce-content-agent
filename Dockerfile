# ============================================================
# 电商内容 Agent - Dockerfile
# 支持两种模式:
#   1. API 服务 (默认): FastAPI + Mock/Transformers/vLLM 后端
#   2. 训练模式: LLaMA-Factory QLoRA 训练
# ============================================================

FROM nvidia/cuda:12.1.0-devel-ubuntu22.04 AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    git \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 升级 pip
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

# ============================================================
# 依赖层 (缓存)
# ============================================================
COPY scripts/setup_env.ps1 /tmp/
# 提取 pip 包列表并安装
RUN pip3 install --no-cache-dir \
    torch>=2.1.0 \
    transformers>=4.45.0 \
    datasets>=2.14.0 \
    accelerate>=0.28.0 \
    peft>=0.10.0 \
    trl>=0.8.0 \
    bitsandbytes>=0.43.0 \
    sentencepiece>=0.1.99 \
    protobuf>=3.20.0 \
    vllm>=0.5.0 \
    fastapi>=0.110.0 \
    uvicorn>=0.29.0 \
    openai>=1.30.0 \
    pydantic>=2.6.0 \
    scipy>=1.10.0 \
    jieba>=0.42.1 \
    scikit-learn>=1.3.0 \
    matplotlib>=3.7.0 \
    seaborn>=0.12.0 \
    pandas>=2.0.0 \
    tqdm>=4.66.0 \
    numpy>=1.24.0 \
    safetensors>=0.4.0 \
    fire>=0.5.0

# ============================================================
# 应用层
# ============================================================
COPY . /app/

# 创建必要目录
RUN mkdir -p /app/models /app/output /app/data/labeled /app/data/raw

# 暴露 API 端口
EXPOSE 8888

# 默认启动 API 服务 (Mock 模式，无需模型文件)
ENV MODEL_BACKEND=mock
ENV PYTHONPATH=/app

CMD ["python3", "-m", "uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8888"]
