@echo off
chcp 65001 >nul
cd /d "%~dp0"
set VENV=%LOCALAPPDATA%\OrcamentoOSC\venv
if not exist "%VENV%\Scripts\python.exe" (
  echo O sistema ainda nao foi instalado. Clique duas vezes em instalar.bat primeiro.
  pause
  exit /b 1
)
echo Abrindo o sistema em http://127.0.0.1:8000  (feche esta janela para desligar)
start "" http://127.0.0.1:8000
"%VENV%\Scripts\python" -m uvicorn app:app --host 127.0.0.1 --port 8000
