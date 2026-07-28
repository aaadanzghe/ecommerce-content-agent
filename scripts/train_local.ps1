# ============================================================
# 本地训练启动脚本
# 用法: .\scripts\train_local.ps1
# ============================================================

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "电商文案微调 - 本地训练 (RTX 5070 Ti 12GB)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. 检查 LLaMA-Factory
if (-not (Test-Path "LLaMA-Factory")) {
    Write-Host "错误: 未找到 LLaMA-Factory，请先运行 scripts/setup_env.ps1" -ForegroundColor Red
    exit 1
}

# 2. 检查模型
$modelPath = "models/qwen3-14b"
if (-not (Test-Path $modelPath)) {
    Write-Host "警告: 未找到本地模型 $modelPath" -ForegroundColor Yellow
    Write-Host "  尝试从 HuggingFace 下载 Qwen2.5-14B-Instruct..." -ForegroundColor Yellow
    Write-Host "  或手动下载: python scripts/download_model.py --model qwen3-14b" -ForegroundColor Yellow
    $modelPath = "Qwen/Qwen2.5-14B-Instruct"
}

# 3. 检查数据集
if (-not (Test-Path "data/labeled/train.json")) {
    Write-Host "错误: 未找到训练数据，请先运行 python data/preprocess.py" -ForegroundColor Red
    exit 1
}

$trainCount = (Get-Content "data/labeled/train.json" | ConvertFrom-Json).Count
$valCount = (Get-Content "data/labeled/val.json" | ConvertFrom-Json).Count
Write-Host "训练集: $trainCount 条" -ForegroundColor Green
Write-Host "验证集: $valCount 条" -ForegroundColor Green

# 4. 开始训练
Write-Host "`n开始 QLoRA SFT 训练..." -ForegroundColor Yellow
Write-Host "  模型: $modelPath"
Write-Host "  配置: configs/train_config.yaml"
Write-Host "  显存: ~10-11GB / 12GB"
Write-Host "  预计时间: ~2-3 小时 (3 epochs)"
Write-Host ""

Push-Location LLaMA-Factory

# 备份原有 dataset_info.json
if (Test-Path "data/dataset_info.json") {
    Copy-Item "data/dataset_info.json" "data/dataset_info.json.bak" -Force
}

# 复制我们的 dataset_info.json (合并)
$ourInfo = Get-Content "..\data\dataset_info.json" -Raw | ConvertFrom-Json
$factoryInfo = Get-Content "data\dataset_info.json" -Raw | ConvertFrom-Json

foreach ($key in $ourInfo.PSObject.Properties.Name) {
    $factoryInfo | Add-Member -NotePropertyName $key -NotePropertyValue $ourInfo.$key -Force
}

$factoryInfo | ConvertTo-Json -Depth 10 | Set-Content "data\dataset_info.json" -Encoding UTF8

# 启动训练
python src/train.py ..\configs\train_config.yaml

Pop-Location

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "训练完成！" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "输出文件:" -ForegroundColor Yellow
Write-Host "  LoRA Adapter: output/ecommerce_qlora_sft/"
Write-Host "  训练日志: output/ecommerce_qlora_sft/trainer_log.jsonl"
Write-Host ""
Write-Host "下一步:" -ForegroundColor Yellow
Write-Host "  1. 评估模型: python eval/judge.py --model $modelPath --lora output/ecommerce_qlora_sft"
Write-Host "  2. 启动推理: python inference/vllm_serve.py --model $modelPath --lora output/ecommerce_qlora_sft"