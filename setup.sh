#!/usr/bin/env bash
# Instalación del dashboard en macOS (o Linux).
# Uso (desde la carpeta del dashboard):  bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"
missing=()

command -v git >/dev/null || missing+=("- git: instálalo con 'xcode-select --install' o Homebrew")
command -v claude >/dev/null || missing+=("- claude: instala Claude Code (https://claude.com/claude-code) y ejecuta 'claude' una vez para iniciar sesión")

# Entorno de Python (3.11 o superior): con uv si está; si no, con python3
if command -v uv >/dev/null; then
  uv venv .venv --python ">=3.11" --allow-existing
  uv pip install --python .venv/bin/python -r requirements.txt
elif command -v python3 >/dev/null; then
  [ -d .venv ] || python3 -m venv .venv
  .venv/bin/python -m pip install --quiet -r requirements.txt
else
  missing+=("- Python 3.11+: brew install python (o instala uv: https://docs.astral.sh/uv/)")
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Creado .env: pon NOTION_CLIENT_ID y NOTION_CLIENT_SECRET (pídelos a quien administre la conexión de Notion)."
fi

if [ ${#missing[@]} -gt 0 ]; then
  echo
  echo "Falta por instalar:"
  printf '%s\n' "${missing[@]}"
  exit 1
fi
chmod +x start.sh
echo
echo "Listo. Arranca el dashboard con:  ./start.sh"
echo "Después, en Ajustes (⚙) sigue los «Primeros pasos»."
