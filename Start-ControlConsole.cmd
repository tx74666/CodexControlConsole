@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0Start-ControlConsole.vbs" (
  start "" wscript.exe "%~dp0Start-ControlConsole.vbs"
  exit /b
)
python "%~dp0world_console.py"
