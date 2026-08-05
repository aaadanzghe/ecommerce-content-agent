# ============================================================
# Local training launcher
# Usage:
#   .\scripts\train_local.ps1
#   .\scripts\train_local.ps1 -SmokeTest
#   .\scripts\train_local.ps1 -ConfigPath configs\train_config.yaml -ModelPath models\Qwen3-14B
# Environment: venv312 (Python 3.12 + PyTorch 2.11 + CUDA 12.8)
# ============================================================

param(
    [string]$ConfigPath = "configs\train_config_8b.yaml",
    [string]$ModelPath = "models\Qwen3-8B",
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"

$python = "venv312\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "ERROR: venv312 was not found." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ConfigPath)) {
    Write-Host "ERROR: training config was not found: $ConfigPath" -ForegroundColor Red
    exit 1
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Ecommerce Agent - local QLoRA training (RTX 5070 Ti 12GB)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if (-not (Test-Path "LLaMA-Factory")) {
    Write-Host "ERROR: LLaMA-Factory was not found. Run .\scripts\setup_env.ps1 first." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ModelPath)) {
    Write-Host "ERROR: local model was not found: $ModelPath" -ForegroundColor Red
    Write-Host "  Default 8B download: venv312\Scripts\python.exe scripts\download_model.py --model qwen3-8b --source modelscope" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path "data\labeled\train.json")) {
    Write-Host "ERROR: training data was not found. Run venv312\Scripts\python.exe data\preprocess.py first." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "data\labeled\val.json")) {
    Write-Host "ERROR: validation data was not found. Run venv312\Scripts\python.exe data\preprocess.py first." -ForegroundColor Red
    exit 1
}

$trainCount = (& $python -c "import json; print(len(json.load(open('data/labeled/train.json', encoding='utf-8'))))")
$valCount = (& $python -c "import json; print(len(json.load(open('data/labeled/val.json', encoding='utf-8'))))")
Write-Host "Train samples: $trainCount" -ForegroundColor Green
Write-Host "Validation samples: $valCount" -ForegroundColor Green

New-Item -ItemType Directory -Path ".cache" -Force | Out-Null

$configText = Get-Content $ConfigPath -Raw -Encoding UTF8
if ([System.IO.Path]::IsPathRooted($ModelPath)) {
    $modelPathForConfig = $ModelPath -replace "\\", "/"
} else {
    $modelPathForConfig = "../" + (($ModelPath -replace "\\", "/").TrimStart("./"))
}

$configText = [regex]::Replace($configText, "(?m)^model_name_or_path:.*$", "model_name_or_path: `"$modelPathForConfig`"")

if ($SmokeTest) {
    $configText = [regex]::Replace($configText, "(?m)^output_dir:.*$", "output_dir: `"../output/ecommerce_qlora_sft_8b_smoke`"")
    if ($configText -match "(?m)^do_eval:") {
        $configText = [regex]::Replace($configText, "(?m)^do_eval:.*$", "do_eval: false")
    }
    if ($configText -match "(?m)^eval_dataset:") {
        $configText = [regex]::Replace($configText, "(?m)^eval_dataset:.*$", "# eval_dataset disabled for smoke test")
    }
    if ($configText -match "(?m)^eval_strategy:") {
        $configText = [regex]::Replace($configText, "(?m)^eval_strategy:.*$", "eval_strategy: `"no`"")
    }
    if ($configText -match "(?m)^predict_with_generate:") {
        $configText = [regex]::Replace($configText, "(?m)^predict_with_generate:.*$", "predict_with_generate: false")
    }
    if ($configText -match "(?m)^max_samples:") {
        $configText = [regex]::Replace($configText, "(?m)^max_samples:.*$", "max_samples: 64")
    } else {
        $configText += "`nmax_samples: 64`n"
    }
    if ($configText -match "(?m)^max_steps:") {
        $configText = [regex]::Replace($configText, "(?m)^max_steps:.*$", "max_steps: 5")
    } else {
        $configText += "`nmax_steps: 5`n"
    }
    if ($configText -match "(?m)^save_steps:") {
        $configText = [regex]::Replace($configText, "(?m)^save_steps:.*$", "save_steps: 5")
    }
    if ($configText -match "(?m)^eval_steps:") {
        $configText = [regex]::Replace($configText, "(?m)^eval_steps:.*$", "eval_steps: 5")
    }
}

$runtimeConfig = ".cache\train_config_runtime.yaml"
Set-Content -Path $runtimeConfig -Value $configText -Encoding UTF8

Write-Host ""
Write-Host "Starting QLoRA SFT training..." -ForegroundColor Yellow
Write-Host "  Model: $ModelPath"
Write-Host "  Config: $ConfigPath"
Write-Host "  Runtime config: $runtimeConfig"
if ($SmokeTest) {
    Write-Host "  Mode: smoke test (max_steps=5)"
} else {
    Write-Host "  Mode: full training"
}
Write-Host ""

Push-Location LLaMA-Factory
try {
    $datasetInfoPath = "data\dataset_info.json"
    $backupPath = "data\dataset_info.json.bak"

    if (Test-Path $datasetInfoPath) {
        Copy-Item $datasetInfoPath $backupPath -Force
    }

    $ourInfo = Get-Content "..\data\dataset_info.json" -Raw -Encoding UTF8 | ConvertFrom-Json
    $factoryInfo = Get-Content $datasetInfoPath -Raw -Encoding UTF8 | ConvertFrom-Json

    foreach ($key in $ourInfo.PSObject.Properties.Name) {
        $factoryInfo | Add-Member -NotePropertyName $key -NotePropertyValue $ourInfo.$key -Force
    }

    $factoryInfo | ConvertTo-Json -Depth 10 | Set-Content $datasetInfoPath -Encoding UTF8

    & "..\$python" src\train.py "..\$runtimeConfig"
    if ($LASTEXITCODE -ne 0) {
        throw "LLaMA-Factory training failed with exit code $LASTEXITCODE"
    }
} finally {
    if (Test-Path $backupPath) {
        Move-Item $backupPath $datasetInfoPath -Force
    }
    Pop-Location
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Training finished." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
if ($SmokeTest) {
    Write-Host "Output:" -ForegroundColor Yellow
    Write-Host "  Smoke LoRA Adapter: output\ecommerce_qlora_sft_8b_smoke\"
} else {
    Write-Host "Output:" -ForegroundColor Yellow
    Write-Host "  LoRA Adapter: output\ecommerce_qlora_sft_8b\"
}
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1. Full training: .\scripts\train_local.ps1"
Write-Host "  2. Eval: venv312\Scripts\python.exe scripts\compare_models.py --base $ModelPath --lora output\ecommerce_qlora_sft_8b"
