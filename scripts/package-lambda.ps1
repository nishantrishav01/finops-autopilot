$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$destination = Join-Path $projectRoot '.cache/lambda'
if (Test-Path -LiteralPath $destination) {
    $resolved = (Resolve-Path -LiteralPath $destination).Path
    if ($resolved -ne (Join-Path $projectRoot '.cache/lambda').Replace('/', '\')) { throw 'Unexpected dependency bundle path.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $destination | Out-Null
& '.venv/Scripts/python.exe' -m pip install --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 --only-binary=:all: --target $destination -r requirements-lambda.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Lambda dependency packaging failed.' }
$serviceTarget = Join-Path $destination 'services'
if (Test-Path -LiteralPath $serviceTarget) {
    $resolved = (Resolve-Path -LiteralPath $serviceTarget).Path
    if ($resolved -ne (Join-Path $projectRoot '.cache/lambda/services').Replace('/', '\')) { throw 'Unexpected bundle path.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Copy-Item -LiteralPath 'services' -Destination $destination -Recurse -Force
$totalBytes = (Get-ChildItem -LiteralPath $destination -Recurse -File | Measure-Object -Property Length -Sum).Sum
if ($totalBytes -ge 250MB) { throw 'Lambda asset exceeds AWS uncompressed size limit.' }
Write-Host "Lambda bundle ready: $([math]::Round($totalBytes / 1MB, 1)) MiB"
