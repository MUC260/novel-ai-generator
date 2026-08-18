@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Novel AI Generator

set "URL=http://127.0.0.1:8000"

rem Already running? Just open browser and exit.
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%URL%/api/health' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 (
  start "" "%URL%"
  exit /b 0
)

set "PY=python"
where pythonw >nul 2>nul && set "PY=pythonw"
if exist ".venv\Scripts\pythonw.exe" set "PY=.venv\Scripts\pythonw.exe"
if exist ".venv\Scripts\python.exe" if not exist ".venv\Scripts\pythonw.exe" set "PY=.venv\Scripts\python.exe"

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

echo Starting server in background...
powershell -NoProfile -Command "$exe = '%PY%'; if (Test-Path $exe) { $exe = (Resolve-Path $exe).Path }; $p = Start-Process -FilePath $exe -ArgumentList 'webui.py','--no-browser' -WorkingDirectory (Get-Location) -WindowStyle Hidden -PassThru; $p.Id | Out-File -FilePath 'server.pid' -Encoding ascii" >nul

set /a tries=0
:wait
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%URL%/api/health' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 goto ready
set /a tries+=1
if %tries% geq 30 (
  echo [ERROR] Server failed to start. Check Python and .env.
  pause
  exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait

:ready
start "" "%URL%"
echo Server is running: %URL%
exit /b 0
