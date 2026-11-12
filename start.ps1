# Arranca el dashboard y lo abre en el navegador (Windows). Para pararlo: Ctrl+C.
# Tras setup.ps1 también se arranca desde cualquier terminal con:  dashboard-tasks
# Si ya está en marcha, solo lo abre en el navegador.
Set-Location $PSScriptRoot
$port = 8765
$url = "http://127.0.0.1:$port"

$tcp = New-Object Net.Sockets.TcpClient
$running = $false
try { $running = $tcp.ConnectAsync("127.0.0.1", $port).Wait(500) } catch {} finally { $tcp.Dispose() }
if ($running) {
    Write-Host "El dashboard ya está en marcha: lo abro en el navegador ($url)."
    Start-Process $url
    exit
}
if (-not (Test-Path .venv\Scripts\python.exe)) {
    Write-Host "Falta instalarlo. En la carpeta del dashboard: powershell -ExecutionPolicy Bypass -File setup.ps1" -ForegroundColor Red
    exit 1
}
Start-Job -ArgumentList $url { param($u) Start-Sleep -Seconds 3; Start-Process $u } | Out-Null
.venv\Scripts\python.exe -m web.app
