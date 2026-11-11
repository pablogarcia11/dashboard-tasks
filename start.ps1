# Arranca el dashboard y lo abre en el navegador (Windows). Para pararlo: Ctrl+C.
Set-Location $PSScriptRoot
Start-Job { Start-Sleep -Seconds 3; Start-Process "http://127.0.0.1:8765" } | Out-Null
.venv\Scripts\python.exe -m web.app
