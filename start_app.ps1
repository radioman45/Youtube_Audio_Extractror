$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "[.venv not found]"
    Write-Host "Create the virtual environment first:"
    Write-Host "  python -m venv .venv"
    Write-Host "  .venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

Write-Host "Starting YouTube Multi Extractor on http://127.0.0.1:8000"
Write-Host "Press Ctrl+C to stop the server."
& $python -m app.main
