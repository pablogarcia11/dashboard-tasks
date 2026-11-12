#!/usr/bin/env bash
# Arranca el dashboard y lo abre en el navegador (macOS/Linux). Para pararlo: Ctrl+C.
# Tras setup.sh también se arranca desde cualquier terminal con:  dashboard-tasks
# Si ya está en marcha, solo lo abre en el navegador.
cd "$(dirname "$0")"
port=8765
url="http://127.0.0.1:$port"
open_browser() { if command -v open >/dev/null; then open "$url"; else xdg-open "$url"; fi; }

if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
  echo "El dashboard ya está en marcha: lo abro en el navegador ($url)."
  open_browser >/dev/null 2>&1
  exit 0
fi
if [ ! -x .venv/bin/python ]; then
  echo "Falta instalarlo. En la carpeta del dashboard: bash setup.sh"
  exit 1
fi
( sleep 3; open_browser ) >/dev/null 2>&1 &
exec .venv/bin/python -m web.app
