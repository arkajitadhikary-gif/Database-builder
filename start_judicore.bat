@echo off
title Judicore Launcher
echo Starting Judicore Legal Database Builder...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_judicore.ps1"
pause
