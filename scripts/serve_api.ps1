# ============================================================
# FastAPI Agent 服务启动脚本
# 用法: .\scripts\serve_api.ps1 [--backend mock|vllm] [--lora output\ecommerce_qlora_sft]
# ============================================================

param(
    [string]$backend = "mock",
    [string]$lora = "",
    [string]$model = "models/Qwen3-14B-Instruct",
    [string]$apiBase = "http://localhost:8000/v1",
    [int]$port = 8888
)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "电商内容 Agent - API 服务" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$env:MODEL_BACKEND = $backend
$env:MODEL_PATH = $model
$env:LORA_PATH = $lora
$env:API_BASE = $apiBase

Write-Host "配置:" -ForegroundColor Yellow
Write-Host "  Backend: $backend" -ForegroundColor Green
Write-Host "  Model: $model" -ForegroundColor Green
Write-Host "  LoRA: $lora" -ForegroundColor Green
Write-Host "  API 端口: $port" -ForegroundColor Green

Write-Host "`n启动 FastAPI..." -ForegroundColor Yellow

python -m uvicorn src.api.server:app --host 0.0.0.0 --port $port

Write-Host "`n服务已停止。" -ForegroundColor Yellow
