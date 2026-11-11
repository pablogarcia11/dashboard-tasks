# Dashboard personal de trabajo

Dashboard local (solo `127.0.0.1`) que une la actividad de trabajo en 1MillionBot: git local, Notion (I'M BACK y Tareas), Google Calendar y Slack. Genera el borrador del stand-up con `claude -p` usando la suscripción, sin API key. Diseño completo y decisiones en [PLAN_TECNICO.md](PLAN_TECNICO.md).

## Puesta en marcha

```powershell
uv venv .venv --python 3.14
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
copy .env.example .env          # y rellena NOTION_CLIENT_ID / NOTION_CLIENT_SECRET (credenciales de la conexión OAuth del equipo)
.venv\Scripts\python.exe -m web.app
```

Después, en http://127.0.0.1:8765 → **Ajustes** (⚙):
1. **Notion → Conectar con Notion**: inicia sesión y comparte tu página diario (y la base de tareas).
2. **Página diario**: búscala por su título y pulsa «Usar como diario». La vista previa confirma que el formato es correcto.
3. **Repositorios → Elegir carpeta…**: la carpeta donde guardas tus proyectos; aparecerán todos sus repos.

Google Calendar se lee con el conector de la cuenta de Claude (claude.ai → Configuración → Conectores).

## Uso

```powershell
.venv\Scripts\python.exe -m web.app                  # abre http://127.0.0.1:8765
.venv\Scripts\python.exe -m jobs.collect_all --show  # recoge el día laborable anterior y hoy
.venv\Scripts\python.exe -m jobs.collect_all --date 2026-11-10 --show
.venv\Scripts\python.exe -m pytest -q
```

Para revisar la interfaz con capturas (skill `webapp-testing`): `uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt` y `.venv\Scripts\python.exe -m playwright install chromium`.

Logo: copia el PNG oficial de 1MillionBot (versión principal, para fondo blanco) en `web/static/logo.png` y reinicia el servidor.

La configuración (autor de git, repos excluidos, proyectos, jornada…) está en `config.yaml`. Los prompts que usa Claude están en `prompts/` y se pueden ajustar sin tocar código.

Convención de commits: ver [CONTRIBUTING.md](CONTRIBUTING.md).
