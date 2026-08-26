@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process -Verb RunAs -WorkingDirectory '%~dp0' -FilePath '%~dp0.venv\Scripts\pythonw.exe' -ArgumentList '%~dp0run_player.pyw'"
