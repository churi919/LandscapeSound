@echo off
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Please run install_windows.ps1 first. See README.md.
  pause
  exit /b 1
)
set HF_HOME=%~dp0models\huggingface
set HF_HUB_CACHE=%~dp0models\huggingface\hub
set HF_HUB_OFFLINE=1
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
set TEMP=%~dp0.cache\tmp
set TMP=%~dp0.cache\tmp
set PYTHONIOENCODING=utf-8
if not exist "%TEMP%" mkdir "%TEMP%"
"%~dp0.venv\Scripts\python.exe" -m streamlit run "%~dp0app.py" --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
pause
