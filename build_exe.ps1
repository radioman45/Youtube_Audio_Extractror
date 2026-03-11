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
    --collect-all faster_whisper `
    --collect-all ctranslate2 `
    --collect-all tokenizers `
    --collect-all huggingface_hub `
    --collect-all onnxruntime `
    --collect-all av `
    --collect-all imageio_ffmpeg `
    --collect-all multipart `
    --collect-all pydantic `
    --collect-all starlette `
    --collect-all yt_dlp `
    --collect-all uvicorn `
    --add-data "app\static;app\static" `
    launcher.py
