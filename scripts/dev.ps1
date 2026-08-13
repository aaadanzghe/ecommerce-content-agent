<#
.SYNOPSIS
Starts the FastAPI backend and Vite frontend for local development.
.DESCRIPTION
Uses the uv workspace for Python and npm for the web app. Provider backends
default to Mock so the complete workflow can be demonstrated without API keys.
#>
param(
    [int]$ApiPort = 8888,
    [int]$WebPort = 5173,
    [ValidateSet("mock", "api")][string]$MediaBackend = "mock"
)

$repoRoot = Split-Path $PSScriptRoot -Parent
$env:IMAGE_BACKEND = $MediaBackend
$env:VIDEO_BACKEND = $MediaBackend

Start-Process -FilePath "uv" -ArgumentList @(
    "run", "uvicorn", "ecommerce_api.main:app", "--reload",
    "--host", "127.0.0.1", "--port", $ApiPort
) -WorkingDirectory $repoRoot -WindowStyle Hidden

Set-Location (Join-Path $repoRoot "agent-app/web")
npm run dev -- --host 127.0.0.1 --port $WebPort
