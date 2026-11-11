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
  [ -x .venv/bin/python ] || uv venv .venv --python ">=3.11"
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

# Comando dashboard-1mb: un pequeño script en ~/.local/bin que lanza start.sh
bin="$HOME/.local/bin"
mkdir -p "$bin"
{
  echo '#!/usr/bin/env bash'
  echo '# Creado por setup.sh del dashboard de 1MillionBot. Vuelve a ejecutar setup.sh si mueves la carpeta.'
  printf 'exec %q "$@"\n' "$PWD/start.sh"
} > "$bin/dashboard-1mb"
chmod +x "$bin/dashboard-1mb"

# Añade ~/.local/bin al PATH si falta (en el fichero de arranque de tu shell)
new_terminal=0
case ":$PATH:" in
  *":$bin:"*) ;;
  *)
    if [ "$(basename "${SHELL:-}")" = zsh ]; then rc="$HOME/.zshrc"
    elif [ "$(uname)" = Darwin ]; then rc="$HOME/.bash_profile"
    else rc="$HOME/.bashrc"; fi
    grep -qs '\.local/bin' "$rc" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
    new_terminal=1
    ;;
esac

echo
echo "Listo. Arranca el dashboard desde cualquier terminal con:  dashboard-1mb"
[ "$new_terminal" = 1 ] && echo "(Abre una terminal nueva para que reconozca el comando.)"
echo "También puedes usar ./start.sh desde esta carpeta."
echo "Después, en Ajustes (⚙) sigue los «Primeros pasos»."
