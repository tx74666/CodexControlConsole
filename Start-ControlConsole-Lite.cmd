@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0Start-ControlConsole-Lite.vbs" (
  start "" wscript.exe "%~dp0Start-ControlConsole-Lite.vbs"
  exit /b
)
python "%~dp0world_console.py" --edition lite
