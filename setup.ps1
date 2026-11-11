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
    uv venv .venv --python ">=3.11" --allow-existing
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
Write-Host "`nListo. Arranca el dashboard con:  .\start.ps1" -ForegroundColor Green
Write-Host "Después, en Ajustes (⚙) sigue los «Primeros pasos»."
