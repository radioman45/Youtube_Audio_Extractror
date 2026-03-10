$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw ".venv\Scripts\python.exe not found. Create the virtual environment first."
}

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name "YouTubeAudioExtractor" `
    --collect-all anyio `
    --collect-all fastapi `
    --collect-all imageio_ffmpeg `
    --collect-all pydantic `
    --collect-all starlette `
    --collect-all yt_dlp `
    --collect-all uvicorn `
    --add-data "app\static;app\static" `
    launcher.py
