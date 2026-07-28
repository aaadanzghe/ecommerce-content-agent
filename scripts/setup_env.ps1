# ============================================================
# 电商文案微调 - 一键环境安装脚本
# 适配: Windows + RTX 5070 Ti 12GB
# 用法: 右键 "使用 PowerShell 运行" 或在终端执行 .\scripts\setup_env.ps1
# ============================================================

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "电商文案微调 - 环境安装" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. 检查 Python 环境
Write-Host "`n[1/5] 检查 Python 环境..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: 未找到 Python，请先安装 Python 3.10+ 或 Anaconda" -ForegroundColor Red
    exit 1
}
Write-Host "  $pythonVersion" -ForegroundColor Green

# 2. 检查 CUDA
Write-Host "`n[2/5] 检查 CUDA 环境..." -ForegroundColor Yellow
$cudaAvailable = python -c "import torch; print(torch.cuda.is_available())" 2>&1
if ($cudaAvailable -eq "True") {
    $cudaVersion = python -c "import torch; print(torch.version.cuda)" 2>&1
    $gpuName = python -c "import torch; print(torch.cuda.get_device_name(0))" 2>&1
    Write-Host "  CUDA: $cudaVersion" -ForegroundColor Green
    Write-Host "  GPU: $gpuName" -ForegroundColor Green
} else {
    Write-Host "  警告: 未检测到 CUDA，请安装 CUDA 12.1+ 版本的 PyTorch" -ForegroundColor Yellow
    Write-Host "  执行: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121"
}

# 3. 安装核心依赖
Write-Host "`n[3/5] 安装核心依赖 (pip)..." -ForegroundColor Yellow
$pipPackages = @(
    "torch>=2.1.0",
    "transformers>=4.45.0",
    "datasets>=2.14.0",
    "accelerate>=0.28.0",
    "peft>=0.10.0",
    "trl>=0.8.0",
    "bitsandbytes>=0.43.0",
    "vllm>=0.5.0",
    "xformers>=0.0.23",
    "sentencepiece>=0.1.99",
    "protobuf>=3.20.0",
    "scipy>=1.10.0",
    "jieba>=0.42.1",
    "scikit-learn>=1.3.0",
    "matplotlib>=3.7.0",
    "seaborn>=0.12.0",
    "pandas>=2.0.0",
    "tqdm>=4.66.0",
    "wandb>=0.15.0",
    "tensorboard>=2.14.0",
    "safetensors>=0.4.0",
    "fire>=0.5.0"
)

foreach ($pkg in $pipPackages) {
    Write-Host "  安装 $pkg ..."
    python -m pip install $pkg --quiet
}

# 4. 安装 LLaMA-Factory
Write-Host "`n[4/5] 安装 LLaMA-Factory..." -ForegroundColor Yellow
if (Test-Path "LLaMA-Factory") {
    Write-Host "  LLaMA-Factory 已存在，跳过 clone" -ForegroundColor Green
} else {
    Write-Host "  克隆 LLaMA-Factory ..."
    git clone --depth 1 https://github.com/hiyouga/LLaMA-Factory.git
}

Push-Location LLaMA-Factory
Write-Host "  安装 LLaMA-Factory 依赖..."
python -m pip install -e ".[torch,metrics]" --quiet
Pop-Location

# 5. 验证安装
Write-Host "`n[5/5] 验证安装..." -ForegroundColor Yellow
python -c @"
import torch
import transformers
import peft
import bitsandbytes
import datasets

print(f'  PyTorch: {torch.__version__}')
print(f'  Transformers: {transformers.__version__}')
print(f'  PEFT: {peft.__version__}')
print(f'  bitsandbytes: {bitsandbytes.__version__}')
print(f'  Datasets: {datasets.__version__}')
print(f'  CUDA Available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
    print(f'  GPU Memory: {gb:.1f} GB')
print(f'  All checks passed!')
"@

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "环境安装完成！" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步：" -ForegroundColor Yellow
Write-Host "  1. 下载模型: python scripts/download_model.py"
Write-Host "  2. 开始训练: cd LLaMA-Factory && python src/train.py ../configs/train_config.yaml"
Write-Host "  3. 本地推理: python inference/vllm_serve.py"
Write-Host "  4. 云端 GRPO: cd LLaMA-Factory && python src/train.py ../configs/grpo_config.yaml"