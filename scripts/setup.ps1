$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Install Python 3.12 or newer.' }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22.12 or newer.' }
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& '.\.venv\Scripts\python.exe' -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment pip setup failed.' }
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-cloud.txt
if ($LASTEXITCODE -ne 0) { throw 'API dependency installation failed.' }
npm.cmd ci --prefix apps/web
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
Write-Host 'Setup complete. Run .\scripts\start.ps1 and open http://127.0.0.1:8000'
