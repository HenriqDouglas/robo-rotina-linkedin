@echo off
rem Login no LinkedIn do Chrome proprio do robo (so no modo de segundo robo no mesmo PC).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:PYTHONUTF8=1; & (Get-Content python.txt -Encoding UTF8 -TotalCount 1).Trim() robo.py entrar"
pause
