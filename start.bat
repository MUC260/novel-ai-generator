@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Novel AI Generator - One-Click Start

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

%PY% --version >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found. Please install Python 3.8+ and add it to PATH.
  pause
  exit /b 1
)

%PY% -c "import requests" >nul 2>nul
if errorlevel 1 (
  echo Installing dependencies ...
  %PY% -m pip install -r requirements.txt
)

echo Starting server, browser will open automatically ...
%PY% webui.py
pause
