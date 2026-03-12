$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw ".venv\Scripts\python.exe not found. Create the virtual environment first."
}

$runningProcesses = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -in @("YouTubeAudioExtractor", "YouTubeAudioExtractorDesktop")
}
if ($runningProcesses) {
    $runningProcesses | Stop-Process -Force
    Start-Sleep -Seconds 2
}

& $python -m PyInstaller --noconfirm --clean "YouTubeAudioExtractor.spec"

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& (Join-Path $root "create_desktop_shortcut.ps1")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
