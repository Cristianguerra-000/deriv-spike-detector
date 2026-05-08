# Script PowerShell alternativo de arranque
Write-Host "DERIV SPIKE ANALYZER — Iniciando..." -ForegroundColor Cyan
Set-Location $PSScriptRoot

# Abrir navegador en 3 segundos
Start-Process powershell -ArgumentList "-Command", "Start-Sleep 3; Start-Process 'http://localhost:8765'"

# Arrancar backend
& python backend.py
