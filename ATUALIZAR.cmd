@echo off
rem Duplo clique para buscar e instalar a versao mais nova do robo.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:PYTHONUTF8=1; & (Get-Content python.txt -Encoding UTF8 -TotalCount 1).Trim() robo.py atualizar"
pause
