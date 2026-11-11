#!/usr/bin/env bash
# Arranca el dashboard y lo abre en el navegador (macOS/Linux). Para pararlo: Ctrl+C.
cd "$(dirname "$0")"
( sleep 3; command -v open >/dev/null && open "http://127.0.0.1:8765" || xdg-open "http://127.0.0.1:8765" ) >/dev/null 2>&1 &
exec .venv/bin/python -m web.app
