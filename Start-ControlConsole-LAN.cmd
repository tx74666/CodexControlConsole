@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0Start-ControlConsole-LAN.vbs" (
  start "" wscript.exe "%~dp0Start-ControlConsole-LAN.vbs"
  exit /b
)
python "%~dp0world_console.py" --host 0.0.0.0
