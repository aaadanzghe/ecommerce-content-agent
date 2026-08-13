<#
.SYNOPSIS
Runs backend and frontend verification for the monorepo.
.DESCRIPTION
Stops immediately when Python tests, TypeScript checks, component tests, or
the production web build fails.
#>
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent

Set-Location $repoRoot
uv run pytest
if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }

Set-Location (Join-Path $repoRoot "agent-app/web")
npm run typecheck
if ($LASTEXITCODE -ne 0) { throw "Frontend type check failed." }
npm test
if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed." }
npm run build
if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }
