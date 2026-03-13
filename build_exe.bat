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

powershell -ExecutionPolicy Bypass -File "%~dp0build_exe.ps1"
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo Build completed under: dist\
echo Desktop shortcuts updated on: %USERPROFILE%\Desktop
pause
