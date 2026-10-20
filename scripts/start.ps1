$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { throw 'Run .\scripts\setup.ps1 first.' }
if (-not (Test-Path -LiteralPath 'apps/web/dist/index.html')) { throw 'Run npm run build first.' }
if (-not $env:FINOPS_ENABLE_LIVE) { $env:FINOPS_ENABLE_LIVE = 'true' }
Write-Host 'FinOps Autopilot: http://127.0.0.1:8000'
Write-Host 'Local API docs: http://127.0.0.1:8000/docs'
Write-Host 'Press Ctrl+C to stop. Saved workspace data survives restarts.'
& '.\.venv\Scripts\python.exe' -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000
if ($LASTEXITCODE -ne 0) { throw 'Local API server stopped with an error. Check whether port 8000 is already in use.' }
