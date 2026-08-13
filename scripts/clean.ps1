<#
.SYNOPSIS
Removes only reproducible caches and temporary Mock output.
.DESCRIPTION
This script never removes models, LoRA adapters, checkpoints, real media, raw
data, or the vendored LLaMA-Factory repository.
#>
$repoRoot = Split-Path $PSScriptRoot -Parent
$targets = @(
    (Join-Path $repoRoot ".pytest_cache"),
    (Join-Path $repoRoot ".cache"),
    (Join-Path $repoRoot "agent-app/web/dist"),
    (Join-Path $repoRoot "agent-app/web/test-results"),
    (Join-Path $repoRoot "agent-app/web/playwright-report")
)

foreach ($target in $targets) {
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}
Get-ChildItem $repoRoot -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force
