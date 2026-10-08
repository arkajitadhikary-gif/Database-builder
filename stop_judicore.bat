@echo off
title Judicore Stopper
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_judicore.ps1"
pause
