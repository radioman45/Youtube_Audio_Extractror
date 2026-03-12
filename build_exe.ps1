$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw ".venv\Scripts\python.exe not found. Create the virtual environment first."
}

& $python -m PyInstaller `
    --noconfirm `
    --onedir `
    --name "YouTubeAudioExtractorDesktop" `
    --collect-all faster_whisper `
    --collect-all ctranslate2 `
    --collect-all tokenizers `
    --collect-data huggingface_hub `
    --collect-binaries onnxruntime `
    --collect-data onnxruntime `
    --collect-all av `
    --collect-all imageio_ffmpeg `
    --collect-all yt_dlp `
    launcher.py

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
