@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal enabledelayedexpansion
set "PID="
if exist "server.pid" (
  set /p PID=<server.pid
  if defined PID taskkill /PID !PID! /F >nul 2>nul
  del /q "server.pid" >nul 2>nul
)
if not defined PID (
  powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'webui\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>nul
)
echo Server stopped.
