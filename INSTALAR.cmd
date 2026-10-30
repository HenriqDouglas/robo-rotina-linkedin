@echo off
rem Duplo clique para instalar ou retomar a instalação do robô.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"
pause
