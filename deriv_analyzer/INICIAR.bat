@echo off
title DERIV SPIKE ANALYZER — Iniciando...
color 0A
echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║   DERIV SYNTHETIC INDICES — SPIKE DETECTION SYSTEM  ║
echo  ║   Backend: FastAPI + Python                          ║
echo  ║   Solo analisis — NO ejecuta operaciones             ║
echo  ╚══════════════════════════════════════════════════════╝
echo.
echo  [1] Iniciando servidor Python en puerto 8765...
echo  [2] El navegador se abrira automaticamente
echo  [3] Para detener: CTRL+C
echo.

cd /d "%~dp0"

:: Abrir navegador tras 2 segundos
start "" timeout /t 2 /nobreak >nul
start "" "http://localhost:8765"

:: Iniciar backend
python backend.py

pause
