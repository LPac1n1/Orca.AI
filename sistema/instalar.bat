@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Instalando o sistema de Orcamentos OSC (gratuito, roda so neste computador)...
set VENV=%LOCALAPPDATA%\OrcamentoOSC\venv
where py >nul 2>nul && (py -3 -m venv "%VENV%") || (python -m venv "%VENV%")
if not exist "%VENV%\Scripts\python.exe" (
  echo.
  echo Nao encontrei o Python. Instale o Python 3.12 em https://www.python.org/downloads/ ^(marque "Add python.exe to PATH"^) e rode este arquivo de novo.
  pause
  exit /b 1
)
"%VENV%\Scripts\python" -m pip install --upgrade pip
"%VENV%\Scripts\python" -m pip install -r requirements.txt
echo Baixando o navegador usado para capturar as paginas de vagas (gratuito, cerca de 150 MB)...
"%VENV%\Scripts\python" -m playwright install chromium
echo.
echo Pronto. Para abrir o sistema, clique duas vezes em iniciar.bat
pause
