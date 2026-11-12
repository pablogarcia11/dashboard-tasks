# Instalación del dashboard en Windows.
# Uso (desde la carpeta del dashboard):  powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$missing = @()

function Require($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { $script:missing += "- $cmd`: $hint" }
}
Require git "instala Git: https://git-scm.com/download/win"
Require claude "instala Claude Code (https://claude.com/claude-code) y ejecuta 'claude' una vez para iniciar sesión"

# Entorno de Python (3.11 o superior): con uv si está; si no, con el lanzador py
if (Get-Command uv -ErrorAction SilentlyContinue) {
    if (-not (Test-Path .venv\Scripts\python.exe)) { uv venv .venv --python ">=3.11" }
    uv pip install --python .venv\Scripts\python.exe -r requirements.txt
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    if (-not (Test-Path .venv)) { py -3 -m venv .venv }
    .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
} else {
    $missing += "- Python 3.11+: instálalo desde https://www.python.org/downloads/ (o instala uv: https://docs.astral.sh/uv/)"
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Creado .env: pon NOTION_CLIENT_ID y NOTION_CLIENT_SECRET (pídelos a quien administre la conexión de Notion)." -ForegroundColor Yellow
}

if ($missing.Count) {
    Write-Host "`nFalta por instalar:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host $_ }
    exit 1
}
# Comando dashboard-tasks: un .cmd en ~\.local\bin (la misma carpeta que usa uv) que lanza start.ps1.
# Se escribe con la página de códigos de la consola para que cmd lea bien rutas con tildes o eñes.
$bin = Join-Path $env:USERPROFILE ".local\bin"
New-Item -ItemType Directory -Force $bin | Out-Null
$oem = [Text.Encoding]::GetEncoding([Globalization.CultureInfo]::CurrentCulture.TextInfo.OEMCodePage)
$shim = "@echo off`r`nrem Creado por setup.ps1 del dashboard de 1MillionBot. Vuelve a ejecutar setup.ps1 si mueves la carpeta.`r`n" +
        "powershell -NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\start.ps1`"`r`n"
[IO.File]::WriteAllText((Join-Path $bin "dashboard-tasks.cmd"), $shim, $oem)
Remove-Item (Join-Path $bin "dashboard-1mb.cmd") -ErrorAction SilentlyContinue  # nombre anterior del comando

# Añade la carpeta al PATH del usuario si falta (leído sin expandir para no romper entradas como %NVM_HOME%)
$newTerminal = $false
$key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("Environment", $true)
$userPath = [string]$key.GetValue("Path", "", "DoNotExpandEnvironmentNames")
$entries = $userPath -split ";" | Where-Object { $_ } | ForEach-Object { [Environment]::ExpandEnvironmentVariables($_).TrimEnd("\") }
if ($entries -notcontains $bin) {
    $key.SetValue("Path", (@($userPath.TrimEnd(";"), $bin) | Where-Object { $_ }) -join ";", "ExpandString")
    # Avisa a Windows del cambio para que las terminales nuevas lo vean
    [Environment]::SetEnvironmentVariable("DASHBOARD_TASKS_SETUP", "1", "User")
    [Environment]::SetEnvironmentVariable("DASHBOARD_TASKS_SETUP", $null, "User")
    $newTerminal = $true
}
$key.Close()

Write-Host "`nListo. Arranca el dashboard desde cualquier terminal con:  dashboard-tasks" -ForegroundColor Green
if ($newTerminal) { Write-Host "(Abre una terminal nueva para que Windows reconozca el comando.)" -ForegroundColor Yellow }
Write-Host "También puedes usar .\start.ps1 desde esta carpeta."
Write-Host "Después, en Ajustes (⚙) sigue los «Primeros pasos»."
