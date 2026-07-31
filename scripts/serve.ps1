# ============================================================
# vLLM 推理服务启动脚本
# 支持 LoRA Adapter 热加载
# 用法: .\scripts\serve.ps1 [--lora output\ecommerce_qlora_sft]
# ============================================================

$ErrorActionPreference = "Stop"

param(
    [string]$lora = "",
    [string]$model = "models/Qwen3-14B-Instruct",
    [int]$port = 8000,
    [float]$gpuMemory = 0.88,
    [switch]$enforceEager
)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "电商内容 Agent - vLLM 推理服务" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 检查模型
if (-not (Test-Path $model)) {
    Write-Host "错误: 未找到模型 $model" -ForegroundColor Red
    Write-Host "  请先运行: python scripts\download_model.py --model qwen3-14b" -ForegroundColor Yellow
    exit 1
}

$cmd = @(
    "python -m vllm.entrypoints.openai.api_server",
    "--model `"$model`"",
    "--port $port",
    "--max-model-len 4096",
    "--gpu-memory-utilization $gpuMemory",
    "--tensor-parallel-size 1",
    "--dtype auto",
    "--served-model-name ecommerce-copywriter"
)

if ($enforceEager) {
    $cmd += "--enforce-eager"
}

if ($lora -and (Test-Path $lora)) {
    Write-Host "LoRA Adapter: $lora" -ForegroundColor Green
    $cmd += "--enable-lora"
    $cmd += "--max-lora-rank 64"
    $cmd += "--max-loras 4"
    $cmd += "--lora-modules ecommerce-lora=`"$lora`""
} else {
    Write-Host "LoRA: 未指定" -ForegroundColor Yellow
}

$cmdStr = $cmd -join " `
    "

Write-Host "`n启动命令:" -ForegroundColor Yellow
Write-Host $cmdStr -ForegroundColor Gray
Write-Host ""

Invoke-Expression $cmdStr
