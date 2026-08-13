<#
.SYNOPSIS
Runs LLaMA-Factory training with the monorepo's selected YAML configuration.
.PARAMETER Config
Configuration file relative to model-training/pipelines/training/configs.
.DESCRIPTION
Training dependencies are installed through the uv training group. The local
LLaMA-Factory checkout is preserved under vendor and may contain local patches.
#>
param([string]$Config = "train_config_8b.yaml")

$repoRoot = Split-Path $PSScriptRoot -Parent
$factory = Join-Path $repoRoot "model-training/vendor/LLaMA-Factory"
$configPath = Join-Path $repoRoot "model-training/pipelines/training/configs/$Config"
if (-not (Test-Path $factory)) { throw "model-training/vendor/LLaMA-Factory was not found." }
if (-not (Test-Path $configPath)) { throw "Training config was not found: $Config" }

Set-Location $factory
uv run --group training llamafactory-cli train $configPath
