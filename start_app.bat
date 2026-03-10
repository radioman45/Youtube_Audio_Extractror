@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [.venv not found]
  echo Create the virtual environment first:
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

echo Starting YouTube Audio Extractor on http://127.0.0.1:8000
echo Press Ctrl+C to stop the server.
".venv\Scripts\python.exe" -m app.main
