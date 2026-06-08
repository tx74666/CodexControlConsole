@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0Start-WorldConsole.vbs" (
  start "" wscript.exe "%~dp0Start-WorldConsole.vbs"
  exit /b
)
python "%~dp0world_console.py"
