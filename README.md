# Dashboard de trabajo

Dashboard local para la gente de 1MillionBot. Junta en una pantalla tu actividad del día: tus commits (también los que aún no has subido), tu diario y tus tareas de Notion, y tus reuniones de Google Calendar. Con eso te prepara el **stand-up**, las **notas para tu diario** y el **parte de horas** para el hub, listos para copiar.

Funciona solo en tu ordenador (`http://127.0.0.1:8765`), lee tus herramientas sin escribir nada en ellas y usa **Claude Code con tu suscripción** para redactar (sin API key).

## Qué necesitas

- **Python 3.11 o superior** (o [uv](https://docs.astral.sh/uv/), que lo instala por ti).
- **Git** y tus repos clonados en una carpeta.
- **Claude Code** instalado y con tu sesión iniciada (ejecuta `claude` una vez en una terminal).
- En [claude.ai](https://claude.ai) → Configuración → Conectores: **Google Calendar** conectado (con todos los permisos).
- Las credenciales de la conexión de Notion del equipo (`NOTION_CLIENT_ID` y `NOTION_CLIENT_SECRET`): pídelas a quien la administre.

## Instalación

**Windows** (PowerShell, en la carpeta del dashboard):

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
.\start.ps1
```

**macOS** (Terminal, en la carpeta del dashboard):

```bash
bash setup.sh
./start.sh
```

`setup` comprueba lo que falta, crea el entorno de Python, instala las dependencias y crea el fichero `.env`. Abre `.env` y rellena las dos credenciales de Notion. `start` arranca el dashboard y lo abre en el navegador (para pararlo: Ctrl+C).

## Primer arranque

Ve a **Ajustes** (⚙, arriba a la derecha) y sigue **Primeros pasos**:

1. **Conectar con Notion**: inicia sesión y comparte tu página diario (y la base de Tareas).
2. **Página diario**: búscala y pulsa «Usar como diario». La vista previa te dice si el dashboard entiende su formato.
3. **Carpetas de repositorios**: «Elegir carpeta…» y selecciona donde guardas tus proyectos. Si los tienes repartidos, añade todas las carpetas que necesites con «Añadir otra carpeta…».
4. **Emails de autor**: se detectan de tu git; añade otros si firmas commits con más de uno.

Mientras falte algo, la vista Día te lo recuerda.

## Uso diario

- **Día**: qué toca hoy, tus notas del diario, tus commits y, en la tarjeta de la derecha, el **stand-up** y las **notas para tu diario**. El icono ↻ de cada tarjeta actualiza o regenera solo esa parte.
- **Parte de horas**: la semana en formato calendario, con las tareas agrupadas y las horas estimadas a partir de tus commits y reuniones. Revísala y cópiala al hub.
- **Ajustes**: qué repos se muestran, tu diario, tus emails y el estado de las conexiones.

El stand-up imita el formato de tus últimos stand-ups del canal del equipo, y las notas siguen el formato de tu diario.

## Problemas frecuentes

- **No salen commits**: revisa en Ajustes la carpeta de repositorios y tus emails de autor.
- **Error en gcal**: reconecta Google Calendar en claude.ai → Conectores, con todos los permisos.
- **Error en notion**: vuelve a conectar Notion en Ajustes.
- **«Elegir carpeta…» no abre nada**: el selector puede quedar detrás del navegador; también puedes escribir la ruta a mano.

---

## Para quien lo desarrolla

```bash
python -m pytest -q                          # tests
python -m jobs.collect_all --date 2026-11-10 --show   # recoger un día desde la terminal
```

- Configuración común de la empresa: `config.yaml`. Lo de cada persona se guarda en su `db/` local desde Ajustes.
- Prompts que usa Claude: `prompts/`. Diseño y decisiones: [PLAN_TECNICO.md](PLAN_TECNICO.md). Commits: [CONTRIBUTING.md](CONTRIBUTING.md).
- Capturas de la interfaz con Playwright: instala `requirements-dev.txt` y `python -m playwright install chromium`.
- Logo: copia el PNG oficial de 1MillionBot en `web/static/logo.png`.
