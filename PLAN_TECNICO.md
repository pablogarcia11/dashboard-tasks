# Dashboard Tasks — Arquitectura y funcionamiento técnico

Documento de referencia técnica: describe **cómo está construido y cómo funciona** el dashboard. La guía de uso para quien lo instala está en [README.md](README.md) y la convención de commits en [CONTRIBUTING.md](CONTRIBUTING.md).

Este documento describe el estado actual del sistema, no su historia. Cuando cambie la arquitectura o el funcionamiento, actualiza la sección afectada para que siga describiendo lo que hay. Los cambios concretos quedan en el historial de git.

---

## 1. Propósito y alcance

Aplicación web **local y personal** para la gente de 1MillionBot. Reúne en una pantalla la actividad de trabajo de una persona y le prepara los textos repetitivos del día:

| Funcionalidad | Qué hace |
|---|---|
| **Vista Día** ("Qué toca hoy") | Pendientes apuntados el día laborable anterior, tareas activas de Notion, reuniones, cambios sin commitear y commits sin subir; notas del diario y commits del día, agrupados por proyecto. |
| **Stand-up** | Borrador para el canal de stand-up de Slack con lo hecho el día laborable anterior y lo previsto para hoy, imitando el formato con el que la persona ya escribe. |
| **Notas para el diario** | Borrador del día para la página diario de Notion a partir de los commits, con el formato del diario. |
| **Parte de horas** | Propuesta semanal (L–V) de bloques horarios con categoría para copiar a mano en la plataforma interna *1million hub*. |
| **Ajustes** | Configuración propia de cada persona: conexión de Notion, página diario, carpetas de repos, emails de autor, canal de stand-up, jornada y visibilidad por repo. |

Fuera de alcance: el dashboard **no escribe** en ningún servicio (Notion, Slack, Calendar, hub). Todo se copia y se pega a mano.

---

## 2. Principios de diseño

- **Solo lectura** sobre todas las fuentes externas. Los colectores nunca reciben herramientas ni permisos de escritura.
- **Recoger y redactar son pasos separados.** Los colectores son código determinista que guarda en SQLite. Claude solo interviene al final, para redactar o agrupar, sobre datos ya recogidos.
- **Sin API key de Anthropic.** Toda la IA va por `claude -p` (Claude Code en modo headless) con la suscripción de la persona. `ANTHROPIC_API_KEY` se elimina siempre del entorno del subproceso.
- **Local y privado.** El servidor escucha solo en `127.0.0.1`. A Claude se le envía contexto recortado (títulos de commit y notas, nunca diffs ni conversaciones completas). Lo que se oculta en Ajustes tampoco se envía.
- **Configuración común frente a configuración personal.** Lo que es de la empresa está en `config.yaml` (versionado). Lo que es de cada persona se elige en Ajustes y se guarda en su base de datos local. En el código no hay nada fijo de una persona.
- **Días laborables = lunes a viernes**, más los festivos configurados. "Ayer" es siempre el día laborable anterior.
- **El propio repo del dashboard nunca se recoge**: se excluye por su ruta absoluta (`ROOT`), de modo que otro repo con un nombre parecido sí cuenta.
- **Una fuente caída no tumba las demás.** Cada colector registra su error en `sync_state` y la interfaz lo muestra con el paso para arreglarlo.

---

## 3. Visión general

```
              ┌──────────────────────── Colectores (sin IA) ────────────────────────┐
              │ git local (subprocess) · Notion (OAuth propio, HTTP)                 │
              │ Google Calendar · Slack  (conectores de Claude vía `claude -p` Haiku,│
              │                           datos leídos del tool_result en bruto)     │
              └───────────────────────────────┬─────────────────────────────────────┘
                                              ▼
                     SQLite  db/dashboard.db  (activity · summaries · sync_state ·
                                               repo_settings · app_settings)
                                              │
                 ┌────────────────────────────┴──────────────────────────┐
                 ▼                                                       ▼
   core/views.py: datos por vista y contexto                 llm/claude_cli.py: `claude -p`
   para Claude (filtros de visibilidad)        ─────────▶    (sin herramientas ni conectores,
                 │                                            caché por hash en summaries)
                 ▼                                                       │
   web/app.py: FastAPI + Jinja2 + HTMX   ◀──────────────────────────────┘
   http://127.0.0.1:8765
```

**Por qué Calendar y Slack van por los conectores de Claude.** El administrador de Google Workspace bloquea la dirección iCal secreta, y Slack suele exigir la aprobación de un administrador para instalar apps propias. Los conectores ya autorizados en la cuenta de Claude de cada persona evitan los dos bloqueos. Para que el resultado siga siendo determinista, Claude solo actúa como "cliente" que llama a una herramienta de lectura concreta, y los datos se toman del `tool_result` en bruto, nunca de lo que Claude responda (ver 7.3).

---

## 4. Stack

| Pieza | Elección |
|---|---|
| Lenguaje | Python ≥ 3.11, entorno en `.venv` (con `uv` si está disponible) |
| Backend | FastAPI + Uvicorn |
| Frontend | Plantillas Jinja2 + HTMX 1.9.12 servido en local (`web/static/vendor/`) + CSS propio, sin paso de build |
| Base de datos | SQLite (`db/dashboard.db`, fuera de git) |
| Git | `git -C <repo> …` por `subprocess` |
| Notion | API REST con `httpx` y OAuth público de Notion (`Notion-Version: 2022-06-28`) |
| Calendar y Slack | Conectores de la cuenta de Claude, llamados con `claude -p` |
| IA | `claude -p` (Sonnet para redactar, Haiku para los conectores) |
| Secretos | `.env` (`python-dotenv`) y `secrets/` (fuera de git) |
| Tests | `pytest`; capturas de interfaz con Playwright (`requirements-dev.txt`) |
| Plataformas | Windows, macOS y Linux |

---

## 5. Estructura del proyecto

```
dashboard-tasks/
├─ README.md · CONTRIBUTING.md · PLAN_TECNICO.md
├─ config.yaml            # configuración común de la empresa (versionada, sin secretos)
├─ .env / .env.example    # credenciales y ajustes locales (el .env fuera de git)
├─ secrets/               # notion_token.json (fuera de git)
├─ setup.ps1 · setup.sh   # instalación + comando `dashboard-tasks`
├─ start.ps1 · start.sh   # arranque (o solo abrir el navegador si ya está en marcha)
├─ core/
│  ├─ config.py           # carga de config.yaml; ROOT del proyecto
│  ├─ settings.py         # ajustes por persona (app_settings) y effective_config()
│  ├─ search.py           # búsqueda en el historial (sin tildes ni mayúsculas)
│  ├─ dates.py            # días laborables, límites de día en la zona horaria
│  ├─ db.py               # acceso a SQLite (upserts, reemplazos por rango, resúmenes)
│  ├─ views.py            # datos de cada vista y contexto para Claude
│  ├─ timesheet.py        # cálculo determinista del parte de horas
│  ├─ identity.py         # nombre y foto de quien usa el dashboard
│  └─ claude_env.py       # entorno de los subprocesos `claude`
├─ collectors/
│  ├─ base.py             # dataclass Activity
│  ├─ git_local.py        # repos, commits (incluidos los no subidos) y WIP
│  ├─ notion_auth.py      # OAuth de Notion (web y terminal)
│  ├─ notion.py           # diario y tareas activas
│  ├─ claude_connector.py # ejecución de `claude -p` con herramientas de lectura y lectura del stream
│  ├─ gcal.py             # reuniones (conector de Google Calendar)
│  ├─ slack.py            # stand-ups propios del canal (conector de Slack)
│  └─ github.py           # pull requests abiertas (API de GitHub, opcional)
├─ llm/claude_cli.py      # `claude -p` para redactar + caché por hash
├─ jobs/collect_all.py    # orquestación de la recogida (también por terminal)
├─ prompts/               # standup.md · journal_notes.md · timesheet.md · weekly_summary.md
├─ web/
│  ├─ app.py              # rutas FastAPI
│  ├─ templates/          # base, day, timesheet, settings y parciales (_*.html)
│  └─ static/             # style.css, vendor/htmx, logo.png opcional
├─ db/schema.sql          # esquema (la .db y avatar.img, fuera de git)
└─ tests/
```

---

## 6. Configuración

La configuración efectiva se compone en tres capas (`core/settings.py · effective_config`):

1. **`config.yaml`: común a la empresa**, versionado:
   - `user.timezone`, `schedule.holidays`.
   - `timesheet`: jornada y comida por defecto, `min_block_minutes`, `block_step_minutes`, `min_daily_hours` y las cinco categorías.
   - `notion`: propiedad de persona y estados inactivos de la base de datos de tareas, y `redirect_uri` del OAuth.
   - `git.scan_depth`.
   - `projects`: proyecto según el nombre del repo o de las carpetas que lo contienen, con comodines; los encabezados del diario usan los mismos nombres. `company_meetings_project` y `meeting_keywords` asignan proyecto a las reuniones.
   - `standup`: número de ejemplos y `relearn_days`.
   - `claude`: comando, modelo para redactar y timeout.
   - `sources` (fuentes activas) y `server` (host y puerto).
2. **`.env`: local y no versionado**: `NOTION_CLIENT_ID` y `NOTION_CLIENT_SECRET` de la conexión OAuth del equipo, `NOTION_TASKS_DATABASE_ID` (la base de datos de tareas), `GITHUB_TOKEN` opcional (ver 7.6) y `CLAUDE_CONFIG_DIR` opcional (ver 7.3). Ningún identificador de un workspace, una persona o un canal concretos se versiona.
3. **Ajustes (`app_settings`): por persona**, y tienen prioridad sobre `config.yaml`:

| Clave | Contenido |
|---|---|
| `notion.journal_page_id` / `notion.journal_page_title` | Página (o base de datos) diario elegida y su título actual |
| `git.repos_roots` | JSON con las carpetas de repos (la antigua `git.repos_root` se migra sola) |
| `git.extra_authors` | Emails de autor añadidos a mano |
| `standup.channel` | Canal de stand-up. Sin él, el stand-up usa el formato por defecto |
| `standup.examples` | Últimos stand-ups propios leídos de Slack, con canal y fecha de lectura |
| `timesheet.*` | Jornada, comida y horas mínimas propias |
| `schedule.days_off` | JSON con los festivos y vacaciones de la persona (fechas ISO) |

El usuario de Notion (`user_id`) no se configura: sale del token OAuth.

---

## 7. Fuentes de datos

Todos los colectores producen `Activity` (`collectors/base.py`): `source`, `kind`, `external_id`, `ts` (ISO con zona), `work_date` (fecha en la zona de la persona), `title`, `body`, `url`, `project`, `status` y `extra` (JSON).

### 7.1 Git local (`collectors/git_local.py`)

- **Descubrimiento:** recorre cada carpeta de `git.repos_roots` hasta `scan_depth` niveles buscando `.git`, que es una carpeta en los repos y un fichero en los worktrees. No entra dentro de un repo, salta `node_modules`, `.venv`, etc., y excluye el propio dashboard. Cada repo se nombra relativo a su carpeta; si dos carpetas tienen un repo con el mismo nombre, el segundo lleva delante el nombre de su carpeta. Las carpetas anidadas no duplican repos.
- **Proyecto:** `projects` de `config.yaml` se compara con el nombre del repo y con el de cada carpeta que lo contiene. Si nada encaja, el proyecto es la carpeta de primer nivel. Los worktrees heredan el proyecto de su repo principal (agrupados por `git rev-parse --git-common-dir`).
- **Autores:** el `user.email` global, el de cada repo y los añadidos en Ajustes.
- **Commits** (`kind=commit`): `git log --all --no-merges --since … --author …` sobre el repo principal de cada grupo, de modo que los worktrees no duplican. Después se filtra por fecha de autor y email exacto. Se marca `pushed=false` si el commit no está en ningún remoto (`rev-list --all --not --remotes`) o si el repo no tiene remoto. `extra` guarda el repo, la rama, el sha corto, los ficheros y las líneas.
- **WIP** (`kind=wip`): `git status --porcelain` por repo y worktree; una entrada por repo con cambios. Solo se recoge si el rango incluye hoy, y sustituye a todo el WIP anterior porque refleja el estado actual.
- Salida en UTF-8 con `errors="replace"`. Los errores por repo se acumulan en `errors` y no detienen la recogida.

### 7.2 Notion (`collectors/notion_auth.py`, `collectors/notion.py`)

**Autenticación.** Conexión **OAuth pública** del workspace, con permisos de leer contenido y leer usuarios con email. El flujo arranca en Ajustes: `/settings/notion/connect` lleva a Notion, que vuelve a `/oauth/notion/callback` con un `state` contra CSRF. También se puede hacer por terminal con `python -m collectors.notion_auth`. El token se guarda en `secrets/notion_token.json` y se renueva con `refresh_token`. "Desconectar" borra el token, la página diario y los datos de Notion guardados.

**Diario.** Página o base de datos elegida en Ajustes, con un buscador de páginas compartidas y una vista previa del formato. El parseo es tolerante:
- **Días** (`day_sections`):
  - un encabezado de cualquier nivel, o un desplegable, con fecha;
  - un encabezado con fecha seguido de su contenido como hermanos, hasta el siguiente día del mismo nivel;
  - una página hija con la fecha en el título;
  - en un diario que es base de datos, una página por día (fecha en una propiedad o en el título).
- **Fechas** (`parse_day`): `10/11/2026`, `10-11-26`, `2026-11-10`, «10 de noviembre de 2026», abreviaturas y menciones de fecha de Notion.
- **Proyectos** (`parse_day_blocks`): un encabezado (lo que le sigue es de ese proyecto) o un desplegable con el proyecto como título. Sin proyecto, el contenido va a «General». Las subviñetas se conservan en `body`.
- **Pendientes** (`kind=task_plan`): lo que va bajo «Pendiente(s):», «Para mañana:», «Por hacer»…, una viñeta que empieza por la marca y dos puntos («Pendiente: probar el flujo») y las casillas sin marcar. No es trabajo hecho: no entra en lo hecho, en el stand-up ni en el parte de horas, y se lleva a "Qué toca hoy" del día laborable siguiente. Las casillas marcadas son trabajo hecho.
- **Notas** (`kind=note`): el resto de elementos de lista y párrafos.
- Las notas y pendientes de un rango **se reemplazan** en cada recogida, así que las ediciones y borrados en Notion se reflejan. El título del diario se refresca en cada recogida. Al cambiar de diario se borran los datos del anterior y se releen en segundo plano los últimos 60 días del nuevo.

**Tareas activas** (`kind=task`): consulta a la base de datos de tareas (`NOTION_TASKS_DATABASE_ID`) con dos condiciones: la propiedad de persona contiene al usuario del token, y `Status` no es ninguno de los estados inactivos. Se guardan el título, el estado y su color de Notion, la prioridad, el tipo y la fecha límite (primera disponible de varias propiedades de fecha). Es una instantánea de hoy y se reemplaza entera.

### 7.3 Conectores de Claude (`collectors/claude_connector.py`, `core/claude_env.py`)

Calendar y Slack se leen ejecutando:

```
claude -p "<instrucción>" --model haiku --allowedTools <herramientas de lectura> \
       --output-format stream-json --verbose
```

- `--allowedTools` incluye **solo** herramientas de lectura concretas. Las de escritura (`send_message`, `create_*`, `update_*`…) nunca se permiten.
- Los datos salen de los `tool_result` del stream (JSON o texto tal cual lo devuelve el servicio). La respuesta redactada por Claude se ignora.
- Si no hubo ningún `tool_result` y el stream termina con un `result` con `is_error`, se lanza `ConnectorError` con el motivo real. Si el motivo es la sesión de Claude Code, el mensaje indica cómo arreglarlo.
- `cwd` en el directorio temporal, lejos de los repos.
- **Entorno** (`claude_env()`, común a todas las llamadas a `claude`): elimina `ANTHROPIC_API_KEY` y, si `.env` define `CLAUDE_CONFIG_DIR`, lo pasa al subproceso. Es necesario para quien usa Claude Code con una carpeta de configuración propia (p. ej. una cuenta de empresa distinta de la de `~/.claude`). Sin ello, el dashboard usaría otra sesión, que puede no tener los conectores o haber caducado.
- Coste aproximado: unos 6 s por llamada con Haiku, a cargo de la cuota de la suscripción.

### 7.4 Google Calendar (`collectors/gcal.py`)

- Herramienta permitida: `mcp__claude_ai_Google_Calendar__list_events` sobre el calendario principal, con `timeMin`/`timeMax` del rango y paginación.
- Se descartan los eventos cancelados, los de tipo `workingLocation`, `outOfOffice` y `birthday`, los rechazados por la persona y los de día completo.
- `kind=meeting` con `extra.start`/`end`, el número de asistentes y el enlace de Meet. El proyecto se asigna por `meeting_keywords` en el título; si no encaja, va a `company_meetings_project`.
- Las reuniones de un rango se reemplazan en cada recogida.

### 7.5 Slack (`collectors/slack.py`)

Slack **no es una fuente de actividad**: solo sirve para aprender el formato del stand-up.
- Herramientas permitidas: `slack_search_channels` y `slack_read_channel`.
- `parse_messages` interpreta los dos formatos de texto que devuelve `slack_read_channel`. `own_standups` se queda con los N más recientes de la persona, reconocida por sus emails de git o de Notion.
- Necesita un canal elegido en Ajustes; sin él no se lee Slack.
- Se guardan en `standup.examples` y se renuevan cada `relearn_days` días, al cambiar de canal o con «Volver a aprender» en Ajustes. Si Slack falla, se conservan los anteriores.

### 7.6 GitHub (`collectors/github.py`, opcional)

- Solo se usa si hay `GITHUB_TOKEN` en `.env`: un token *fine-grained* de solo lectura (*Pull requests* y *Metadata*), creado por cada persona. Ajustes › GitHub explica cómo crearlo y muestra el estado.
- Dos búsquedas en la API REST (`/search/issues`), con `@me` para no tener que configurar el usuario: `is:pr is:open review-requested:@me` (`kind=review`) y `is:pr is:open author:@me` (`kind=pr`). Es una instantánea: se reemplaza entera en cada recogida, sea cual sea el rango.
- Los errores llevan el paso para arreglarlos: token no válido o caducado (401), organización con SSO (403 con SAML) o límite de consultas.

---

## 8. Recogida (`jobs/collect_all.py · run_collect`)

`run_collect(cfg, con, start, end, only=None)` ejecuta las fuentes activas (o solo las de `only`) para el rango y devuelve un informe por fuente. Cuándo se ejecuta:

| Disparador | Rango |
|---|---|
| Arranque del servidor (en un hilo, sin bloquear) | Día laborable anterior y hoy |
| «Actualizar datos» en la vista Día (`POST /collect/{d}`) | Día laborable anterior a `d` y `d` |
| «Actualizar datos de la semana» (`POST /collect-range/{start}/{end}`) | La semana, hasta hoy |
| Icono ↻ de una tarjeta (`POST /refresh/{d}/{notes\|commits}`) | Solo Notion o solo git para `d` |
| Generar notas del diario | Solo Notion para ese día (para no pisar lo recién escrito) |
| Vista de hoy abierta, cada `server.auto_refresh_minutes` (10 por defecto) | Solo Notion y git de hoy, con la pestaña a la vista; refresca las dos tarjetas |
| Cambio de diario o de carpetas en Ajustes | Relectura en segundo plano |
| Terminal: `python -m jobs.collect_all [--date D \| --since A --until B] [--show]` | El indicado |

Un `threading.Lock` garantiza que solo haya una recogida a la vez. Semántica de escritura:
- Commits: **upsert** por `(source, external_id)`.
- WIP y tareas: **reemplazo total**, porque son el estado actual.
- Notas, pendientes y reuniones: **reemplazo por rango**.

Cada fuente actualiza `sync_state` (`last_ok` o `last_error`).

---

## 9. Modelo de datos (`db/schema.sql`)

```sql
activity(id, source, kind, external_id, ts, work_date, title, body, url, project, status, extra_json,
         UNIQUE(source, external_id))          -- índice por work_date
summaries(id, work_date, kind, content_md, input_hash, created_at, UNIQUE(work_date, kind))
repo_settings(repo PRIMARY KEY, visible, show_wip)   -- sin fila = todo visible
app_settings(key PRIMARY KEY, value)                 -- ajustes por persona (sección 6)
sync_state(source PRIMARY KEY, last_ok, last_error)
```

| `source` | `kind` |
|---|---|
| `git` | `commit`, `wip` |
| `github` | `review` (piden tu revisión), `pr` (tuyas abiertas) |
| `notion` | `note`, `task_plan`, `task` |
| `gcal` | `meeting` |

Valores de `summaries.kind`: `standup`, `journal_notes`, `timesheet`, `timesheet_edit` (bloques de un día editados a mano) y `weekly_summary` (con `work_date` = lunes de la semana).

---

## 10. Fechas (`core/dates.py`)

- `is_workday`: lunes a viernes y que no esté en `holidays`. `previous_workday`: el lunes da el viernes anterior.
- `day_bounds(d, tz)`: de 00:00 a 00:00 del día siguiente en la zona de la persona, correcto con los cambios de horario. `to_work_date` convierte un instante a fecha local.
- En fin de semana, "Hoy" muestra el último día laborable con aviso (`effective_today`).
- **Días libres:** los festivos de la empresa (`schedule.holidays` de `config.yaml`) y los festivos y vacaciones de cada persona (Ajustes › Festivos y vacaciones, clave `schedule.days_off`). `web/app.py · holidays()` los une en cada petición.
- Tests de lunes, fines de semana, cambio de mes y año, y DST.

---

## 11. Generación con Claude

### 11.1 Envoltorio (`llm/claude_cli.py`)

```
claude -p <prompts/<kind>.md> --output-format json --model <claude.model> --tools "" --strict-mcp-config
```

- Sin herramientas ni conectores. El contexto JSON entra por stdin, el `cwd` es el temporal y el entorno sale de `claude_env()`.
- **Caché:** `input_hash` = SHA-256 de (prompt + contexto + modelo). Si coincide con el guardado en `summaries`, no se vuelve a llamar a Claude. `force=True` regenera. La interfaz avisa cuando los datos han cambiado desde la última generación.
- Una validación opcional (`validate`) puede rechazar la respuesta antes de guardarla. Si Claude falla (cuota, sesión…), se muestra el error y se conserva el último resultado. No se reintenta.
- Regla común en todos los prompts: usar solo la información recibida y decir lo que no esté claro en vez de inventarlo.

### 11.2 Stand-up (`prompts/standup.md`, `core/views.py · standup_context`)

- **Solo para hoy:** en los días anteriores la vista Día no muestra la pestaña Stand-up (la tarjeta enseña solo las notas para el diario) y `POST /standup/{d}` responde 409.
- **Contexto**:
  - `ayer`: notas del diario del día laborable anterior (fuente principal), commits y reuniones.
  - `hoy`: pendientes de ayer, tareas activas, reuniones de hoy y trabajo sin terminar.
  - `ejemplos_formato`: los stand-ups aprendidos de Slack (7.5).
  - Las reuniones llegan con su proyecto (`{reunion, proyecto}`, ver 7.4), y cada una va bajo ese proyecto. Las de empresa (Sprint Review, Seguimiento Sprint, Monthly Review…) forman su propio apartado «1MB».
- **Formato:** el texto sale siempre en **Markdown estándar** (`**Sección**`, `- Proyecto` y `- tarea` sangrada 4 espacios), que es lo que el editor de Slack convierte en negritas y listas al pegarlo. Imita la forma de los ejemplos (saludo, emojis, títulos, niveles de viñeta, longitud de cada tarea); como los ejemplos llegan en el formato interno de Slack (`*negrita*`, `•`, `◦`), el prompt indica cómo traducirlos a Markdown. Sin ejemplos se usa el formato por defecto del prompt.
- **Normalización** (`core/views.py · standup_markdown`, aplicada al texto nuevo y al guardado): traduce los restos del formato de Slack que Claude pueda dejar (`*negrita*` → `**negrita**`, `•`/`◦` → `- ` con 4 espacios por nivel) e inserta una línea en blanco tras cada lista. Sin esa línea, Markdown pega el título siguiente al último elemento de la lista.
- **Copiar:** el botón copia el texto plano tal cual (Markdown).

### 11.3 Notas para el diario (`prompts/journal_notes.md`, `journal_notes_context`)

Borrador del día a partir de los commits de los repos visibles, con lo ya escrito en el diario ese día para completarlo sin repetirlo. Sale en markdown con el formato del diario (`# Martes 10/11/2026`, `### Proyecto`, viñetas poco técnicas). Cada viñeta describe un cambio en la aplicación: o cómo funciona ahora, de forma impersonal («Al salir del detalle de una incidencia se vuelve a la página anterior»), o en primera persona con un verbo de hacer cambios («Corregí…», «Añadí…»), nunca como una acción de la persona usando la aplicación, que Notion convierte al pegar. Antes de generar se relee Notion para ese día.

### 11.4 Resumen de la semana (`prompts/weekly_summary.md`, `weekly_context`)

En la página del parte de horas, bajo la leyenda. Para la Sprint Review o para el responsable: lo conseguido en cada proyecto durante la semana, no un diario por días.
- **Contexto:** por cada día laborable de la semana hasta hoy, las notas del diario (fuente principal), los títulos de los commits (apoyo) y las reuniones con su proyecto; y lo último que quedó pendiente (el día más reciente con pendientes).
- **Salida:** Markdown con `**Proyecto**` y viñetas de resultados (varios días sobre lo mismo se juntan en un punto), y «Para la próxima semana» con lo pendiente.
- Se cachea por semana y avisa si el diario o los commits han cambiado desde que se generó.

### 11.5 Parte de horas (`core/timesheet.py`, `prompts/timesheet.md`)

El parte se construye en dos partes:
- **Claude agrupa y titula.** Recibe los commits del día y las notas del diario, y devuelve JSON con tareas: título `<Proyecto> - <tarea>`, proyecto, categoría, commits asignados o minutos estimados. `parse_tasks` valida la respuesta:
  - descarta commits inventados o repetidos;
  - una categoría inválida pasa a ser «Desarrollo de negocio»;
  - los commits sin asignar forman una tarea propia.

  Una respuesta inválida no se guarda.
- **Python calcula todo lo horario** (`build_blocks`, determinista y con tests):
  1. Las reuniones son bloques fijos a su hora real.
  2. La comida dura 60 min y va en el hueco sin commits ni reuniones más cercano a su hora por defecto (dentro de una ventana).
  3. La jornada (por defecto o la de Ajustes) se alarga si hay commits o reuniones fuera de ella.
  4. Cada tarea con commits va desde el final del bloque anterior hasta su último commit. Un hueco entre dos tramos de la misma tarea pertenece a esa tarea.
  5. Los demás huecos se reparten entre las tareas del diario sin commits según su peso estimado. Si no hay, se alarga la tarea anterior.
  6. Los bordes se redondean a múltiplos de `block_step_minutes` (salvo los fijos), con una duración mínima de `min_block_minutes`. Los bloques contiguos con el mismo título se fusionan y los demasiado cortos se absorben en el vecino.
  7. Se avisa si el día queda por debajo de `min_daily_hours`.
- **Edición a mano** (`parse_edited`, `POST /timesheet/day/{d}/blocks`): la persona puede mover una tarea arrastrándola, alargarla o acortarla desde su borde inferior, y cambiar su nombre, horario, tipo y proyecto, añadir tareas o eliminarlas desde un formulario. Las horas que se cambian van en tramos de `block_step_minutes` (lo impone la rejilla); las que no se tocan se guardan tal cual, porque cada cambio reenvía el día entero y las reuniones van a su hora real (10:25, 5 min). Solo las reuniones pueden solaparse entre ellas; en la rejilla se reparten el ancho en carriles (`lanes`), como en el calendario. Los bloques de menos de 12 px no tienen borde de redimensionar (lo taparía entero): se mueven, y su duración se cambia en el formulario. Cada cambio guarda el día como JSON en `summaries` (`kind=timesheet_edit`); mientras exista, manda sobre la propuesta calculada. Si el servidor rechaza un cambio, la columna vuelve a lo guardado y se muestra el motivo (el formulario no se cierra hasta que se guarda; el aviso de un arrastre rechazado se retira a los 10 s). Como el «Texto para copiar» se recalcula a partir de los bloques, si se ha editado a mano se pide confirmación antes de guardar; si se cancela, no se envía nada. «Deshacer mis cambios» (`…/blocks/reset`) lo borra, y «Regenerar» también, pero solo si Claude genera la propuesta nueva. En pantallas táctiles no hay arrastre: se edita con el formulario.
- Se cachea por día (`kind=timesheet`). Las categorías y sus colores son los del hub: Desarrollo de negocio, Reunión, Documentación, Tareas administrativas y Formación.

---

## 12. Aplicación web (`web/app.py`)

### 12.1 Rutas

| Ruta | Función |
|---|---|
| `GET /` → `GET /day/{d}` | Vista Día |
| `POST /collect/{d}`, `POST /collect-range/{a}/{b}` | Recogida completa (responde `HX-Refresh`) |
| `POST /refresh/{d}/{notes\|commits}` | Recoge una fuente y devuelve solo su tarjeta. La de commits incluye también «Para no perder» (`_keep_safe.html`) como `hx-swap-oob`, porque sale de los mismos datos de git |
| `POST /standup/{d}`, `POST /journal-notes/{d}` | Generan (o devuelven de caché) el texto; `?force=true` regenera |
| `GET /timesheet` → `GET /timesheet/week/{d}` | Parte de horas semanal |
| `GET`/`POST /timesheet/day/{d}` | Columna de un día: ver o generar |
| `POST /timesheet/day/{d}/blocks`, `POST …/blocks/reset` | Guardan los bloques editados a mano de un día, o los descartan |
| `GET /settings` y `POST /settings/…` | Ajustes: canal y aprendizaje del stand-up, jornada, festivos, emails de autor, carpetas (selector nativo, alta y baja), visibilidad por repo. Los festivos devuelven su lista (`_days_off.html`) y, al quitar un rango, un «Deshacer» (`action=restore`, sin el límite de tres meses que tiene añadir); el resto, `HX-Redirect` a Ajustes, con `HX-Refresh` si solo cambia el `#ancla` (si no, el navegador solo se desplazaría) |
| `GET /settings/notion/connect`, `GET /oauth/notion/callback`, `POST /settings/notion/disconnect` | OAuth de Notion |
| `GET /settings/notion/pages`, `POST /settings/notion/journal`, `GET /settings/notion/journal-status` | Búsqueda, elección y vista previa del diario |
| `GET /search?q=` | Buscador; con HTMX devuelve solo los resultados (`_search_results.html`) |
| `POST /weekly/{d}` | Genera (o devuelve de caché) el resumen de la semana de `d`; `?force=true` regenera |
| `GET /avatar` | Foto de perfil local |

Las acciones devuelven fragmentos HTML (`_*.html`) que HTMX coloca en su sitio. No hay API JSON.

### 12.2 Datos de las vistas (`core/views.py`)

- `day_data` reúne en una consulta lo de un día: notas, commits, pendientes del día anterior, tareas y WIP, agrupados por proyecto.
- `visible_git` aplica `repo_settings`: «Visible» oculta commits, WIP y commits sin subir de un repo; «Cambios sin commitear» oculta solo su WIP. El filtro se aplica aquí, al preparar los datos, así que **lo oculto tampoco llega a Claude**. Los datos se siguen recogiendo y reaparecen al reactivar el repo.
- Ocultar un worktree solo oculta su WIP, porque los commits son del repo principal.
- Los primeros pasos (Claude Code instalado, Notion conectado, diario elegido, carpeta de repos, Calendar sincronizado…) se calculan en `/settings`. Mientras falte alguno, la vista Día muestra un aviso.

### 12.3 Identidad (`core/identity.py`)

En la barra se muestra el nombre y la foto de quien usa el dashboard, deducidos de sus herramientas.
- **Nombre**, en este orden: el usuario de Notion del token, `git config --global user.name`, la parte local del email de autor y, por último, «Dashboard».
- **Foto:** el avatar de Notion, descargado una vez a `db/avatar.img`. Si no hay, se muestran las iniciales.

Se calcula al arrancar y se recalcula al conectar o desconectar Notion.

---

## 13. Interfaz

- **Marca 1MillionBot:**
  - colores: rojo `#CD3434` en rellenos (botones, filete, día de hoy) y coral `#FE6565` como acento puntual;
  - texto `#1D1D1D` y grises `#D2D2D2` y `#949494`;
  - tipografía Montserrat, con Verdana de reserva;
  - logo: se muestra si existe `web/static/logo.png`.
- **Temas claro y oscuro:**
  - por defecto sigue `prefers-color-scheme`. Se cambia en Ajustes › Apariencia, la elección se guarda en `localStorage` y «Sistema» la olvida. Un script en `<head>` aplica el tema antes de pintar, sin parpadeo;
  - el oscuro usa `#242424` de fondo y `#2C2C2C` en tarjetas. El texto rojo pasa a `#EE6A6A` para cumplir AA;
  - las categorías del parte tienen colores propios por tema (tokens `--dev-*`, `--doc-*`, `--meet-*`, `--admin-*`, `--learn-*`).
- **Tokens** (`web/static/style.css`):
  - radios `--r-sm` 4 px, `--r-md` 8 px, `--r-lg` 12 px y `--r-pill`;
  - curvas `--ease-out` y `--ease-in-out`, y duraciones `--press` y `--fast`.
- **Movimiento:** cada animación responde a una acción o señala un cambio; nada se anima al cargar la página ni de fondo. Solo se animan `transform`, `opacity`, `clip-path` y colores.
  - **Microinteracciones:** escala al pulsar, spinner en botones con petición en curso, fundido del contenido que llega por HTMX, modal con `<dialog>`, barras de navegación, de pestañas y de la tira semanal que se deslizan, y plegables que animan su altura.
  - **Cambio de día o de semana:** el contenido sale y entra hacia el lado al que se navega (View Transitions entre documentos con los tipos `forward` y `back`, que `base.html` añade en `pageswap` y `pagereveal` comparando las fechas de las dos URL). La barra superior y los controles de fecha tienen `view-transition-name` propio y no se mueven.
  - **Actividad:** el filete rojo de la barra superior es el indicador global. Mientras hay peticiones de HTMX en curso (`body.is-busy`), lo recorre un destello.
  - **Textos de Claude:** durante la espera, unas líneas marcan dónde caerá el texto. Al llegar, el texto se descubre de arriba abajo y los bloques del parte se colocan uno tras otro (clase `just-generated`, que `base.html` pone tras un `POST` de generación que no ha fallado; guardar bloques editados no cuenta).
  - **Filas nuevas:** al actualizar una tarjeta con ↻, las filas que no estaban antes se señalan con un fondo que se desvanece (clase `is-new`), y el foco vuelve a donde estaba.
  - **Recogida automática** (`X-Auto-Refresh`): si la lectura no trae nada distinto, la tarjeta no se sustituye (sin fundido, foco ni aviso); si solo cambia «Para no perder», se sustituye solo eso. «Actualizado hace…» solo se reinicia si la fuente se ha leído bien. Pasada la medianoche, la página vuelve a hoy.
  - **Tema:** al pulsar el interruptor, el tema nuevo se abre en círculo desde el punto pulsado. El cambio que viene del sistema o del teclado es un fundido.
  - **Lo que no se anima:** la navegación con atajos de teclado (se salta la transición) y la carga inicial de las páginas.
  - **`prefers-reduced-motion`:** se quitan desplazamientos, escalas, el círculo del tema y los bucles; quedan fundidos breves y los indicadores de carga, quietos.
- **Componentes:**
  - buscador (`/search`, `core/search.py`): busca en commits, notas, pendientes y reuniones guardados, sin distinguir tildes ni mayúsculas, con todas las palabras; resultados por día con enlace a cada uno y lo encontrado resaltado. Respeta lo oculto en Ajustes. Se abre desde la lupa de la barra o con `/`;
  - pull requests en «Qué toca hoy» (si hay token de GitHub): las que piden tu revisión y las tuyas abiertas, con enlace;
  - tira de la semana en la vista Día (`core/views.py · week_overview`): un enlace por día laborable con una marca según el diario: hay notas, hay commits sin notas (falta apuntar) o no hay actividad;
  - «Actualizado hace…» junto al botón de actualizar (`sync_state.last_ok` más reciente) y, en las reuniones de hoy, cuánto falta para la siguiente; ambos se recalculan en el navegador cada 30 s con `Intl.RelativeTimeFormat`;
  - línea discreta en la vista de hoy con los días laborables de las tres últimas semanas que tienen commits y ninguna nota (`unnoted_days`): los tres más recientes como enlaces y, si hay más, «y N más» despliega el resto (al pasar el puntero o con el foco);
  - «Para no perder» agrupa los commits sin subir por repo (`unpushed_by_repo`); el detalle está en la tarjeta Commits;
  - en escritorio, la tarjeta de textos se queda fija al desplazar la página (`position: sticky`);
  - parte de horas: línea de la hora actual en la columna de hoy, horas de la semana por categoría junto a la leyenda, «Copiar semana» (el texto de todos los días, cada uno con su nombre) y, en pantallas estrechas, eje de horas fijo y desplazamiento inicial hasta hoy;
  - atajos de teclado (`base.html`): ← → día o semana, T hoy, D y P secciones, R actualizar, C copiar el texto visible, / buscar y ? para la ayuda. No actúan mientras se escribe ni con un diálogo abierto;
  - navegación por días al estilo Google Calendar (Hoy, ‹ ›, calendario mensual que no deja elegir fines de semana ni el futuro);
  - tarjetas con proyectos plegables (recordados en `localStorage`). Donde el navegador soporta `::details-content`, los plegables y las guías de ayuda se abren y se cierran animando la altura (`interpolate-size: allow-keywords`) y la opacidad. El contenido usa `display: flow-root` para que los márgenes no salten al terminar. En el resto de navegadores, y con movimiento reducido, solo hay fundido;
  - pestañas Stand-up / Notas para el diario;
  - botón de copiar solo con icono dentro del texto;
  - estados de tarea con el color de Notion;
  - parte de horas en una rejilla de 07:00 a 20:00 a 0,8 px/min, con un modal de detalle por bloque.
- **Accesibilidad y robustez:**
  - «Saltar al contenido», `aria-label` en los controles de solo icono y región `role="status"` para cargas y «Copiado»;
  - foco visible y `tabular-nums`;
  - aviso antes de perder un texto editado;
  - Ajustes confirma cada guardado y deshace el cambio si falla;
  - HTMX servido en local, así que funciona sin internet.
- Los cambios de interfaz se revisan con capturas de Playwright.

---

## 14. Instalación y arranque

- **`setup.ps1` / `setup.sh`:**
  1. comprueban requisitos (Python ≥ 3.11 o `uv`, git, Claude Code);
  2. crean `.venv` e instalan `requirements.txt`;
  3. crean `.env` desde `.env.example`;
  4. instalan el lanzador `dashboard-tasks` en `~/.local/bin` (en Windows, un `.cmd` en la página de códigos de la consola) y añaden esa carpeta al PATH si falta. En Windows se edita el registro sin expandir variables; en macOS y Linux, el fichero de arranque del shell;
  5. borran el lanzador antiguo `dashboard-1mb`.

  Si se mueve la carpeta, hay que repetir `setup`.
- **`start.ps1` / `start.sh`:** si el puerto 8765 ya está en uso, solo abren el navegador. Si no, arrancan `python -m web.app` y abren el navegador.
- **Puerto fijo 8765:** la URI de redirección del OAuth de Notion está registrada con él.

---

## 15. Seguridad y privacidad

- Secretos solo en `.env` y `secrets/`. Ni esas carpetas ni `db/` se versionan (`.gitignore`).
- El servidor escucha solo en `127.0.0.1`. El OAuth de Notion usa `state`.
- Los permisos externos son de solo lectura: Notion con lectura de contenido y usuarios, y los conectores limitados con `--allowedTools`.
- A Claude solo llega contexto recortado (títulos de commit, notas, títulos de reuniones y tareas) de los repos visibles. Los diffs y los mensajes de otras personas nunca se envían.
- Toda la IA pasa por la suscripción de la persona, nunca por API key.

---

## 16. Tests

`python -m pytest -q`. Hay un fichero de tests por módulo:
- `dates`: días laborables, DST y cambio de año;
- `git_local`: descubrimiento, worktrees, exclusión del propio repo y parseo de `git log`;
- `notion`: formatos de día, fecha, proyecto y pendientes;
- `gcal` y `slack`: parseo del stream y de los mensajes;
- `claude_connector`: errores de ejecución y entorno;
- `settings`, `identity` y `views`;
- `timesheet`: colocación de la comida, redondeos, fusiones, validación de la respuesta de Claude y de los bloques editados;
- `app`: rutas que cambian datos (festivos, redirecciones de Ajustes, guardar y regenerar el parte), con una base de datos temporal y Claude simulado.

Los colectores se prueban con datos de ejemplo, sin red.

---

## 17. Limitaciones conocidas

- La conexión OAuth de Notion pertenece a la cuenta que la creó. Conviene que la administre una cuenta de la empresa.
- Calendar y Slack dependen de que la sesión de Claude Code de la persona tenga los conectores autorizados, con todos sus permisos.
- En el parte de horas, como los commits ocupan casi toda la jornada, las tareas sin commits (documentación, informes) suelen quedarse con poco tiempo.
- La recogida automática solo funciona con la vista de hoy abierta y no incluye Calendar (cada lectura pasa por Claude): las reuniones se leen al arrancar y con «Actualizar datos».
- Las pull requests solo se ven con un token de GitHub de cada persona; las revisiones pedidas a un equipo (no a la persona) no aparecen.
