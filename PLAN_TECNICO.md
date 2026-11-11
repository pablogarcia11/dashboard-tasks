# Dashboard personal de trabajo — Plan técnico y guía de arranque

> **Para el Claude Code que lea esto:** no tienes contexto previo. Este documento es tu contexto completo.
> Léelo entero y empieza por la **sección 0 (Protocolo de arranque)**. Habla con el usuario en **español**.
> No escribas código de la aplicación hasta completar la fase de conexiones (sección 0 y 5), salvo el esqueleto del proyecto.

---

## 0. Protocolo de arranque (haz esto primero)

La cuenta de Claude Code en la que estás es nueva: **no tiene ninguna herramienta conectada**. Tú no puedes iniciar sesión, pegar contraseñas ni aprobar permisos OAuth por el usuario. Guíale paso a paso, **un paso cada vez**, esperando su confirmación antes de pasar al siguiente. Cada paso: di qué hacer, dónde pulsar y qué debe contestarte.

Orden recomendado (de menos a más fricción; así hay algo funcionando pronto):

1. **Entorno local.** Ejecuta tú mismo: `git --version`, `python --version`, `node --version`, `claude --version`. (En la máquina del usuario ya había git 2.51, Python 3.14.7, Node 22, Claude Code 2.1.x; `gh` NO está instalado.) Si Python 3.14 da problemas con alguna librería, crea el venv con 3.12/3.13 (`uv` o `py -3.12`).
2. **Comprobar que `claude -p` funciona con la suscripción**, sin API key:
   - Ejecuta `echo $env:ANTHROPIC_API_KEY` (PowerShell). Si tiene valor, pide al usuario que la elimine del entorno: con esa variable Claude Code factura por API y **el usuario no quiere ese coste**.
   - Prueba `claude -p "responde solo OK" --output-format json`. Debe responder usando el login de la cuenta. Si pide login, que el usuario ejecute `claude` y entre con su cuenta.
3. **Datos del usuario** (pregúntalos y guárdalos en `config.yaml`, no en el código):
   - Emails y nombres con los que firma commits (`git config user.email` de cada repo puede variar; pide todos: personal y de empresa).
   - Usuario de GitHub, zona horaria (por defecto `Europe/Madrid`), hora a la que quiere el stand-up listo (por defecto 08:30).
4. **Git local** (no requiere autenticación). Verifica que lees los repos de `C:\Users\daxte\Documents\1MillionBot` (sección 4.1).
5. **Notion** (sección 5.1): crear integración interna y compartir con ella las páginas necesarias.
6. **Google Calendar** (sección 5.2): crear credenciales OAuth de escritorio y autorizar solo lectura.
7. **Slack** (sección 5.3): puede requerir aprobación de un administrador; déjalo para el final y no bloquees el resto.
8. **GitHub remoto** (sección 5.4): opcional; con el git local casi todo está cubierto.
9. **Conectores MCP de Claude Code (opcional, secundario).** Si el usuario quiere, que conecte Notion/Calendar/Slack/GitHub como conectores en su cuenta de Claude para consultas libres. **No son la base del proyecto**: los colectores usan sus propias credenciales (ver sección 2).

Cada credencial va a un fichero `.env` (que nunca se versiona) o al almacén de credenciales de Windows vía `keyring`. **Nunca pegues secretos en el chat ni en commits**; si el usuario los pega por error, avísale para que los revoque.

---

## 1. Qué se quiere construir y por qué

Un **dashboard local de uso personal** que unifique en una sola pantalla la actividad de trabajo del usuario en la empresa (1MillionBot) y le ahorre trabajo repetitivo:

1. **Vista principal diaria (funcionalidad principal): "Qué toca hoy".** Cada día muestra las tareas del día, combinando:
   - **Reuniones del día** (Google Calendar).
   - **Pendientes apuntados el día laborable anterior en "I'M BACK"**: lo que ese día quedó pendiente y se pretende hacer al siguiente (ver 5.1 para cómo se marca).
   - **Tareas de la base "Tareas" del workspace 1millionbot**, solo las del usuario y activas (ver 5.1).
   - Trabajo sin commitear y commits sin subir (para no perder nada).
   - Más adelante: PRs pendientes de su revisión, menciones y hilos de Slack relevantes.
2. **Timeline de actividad** de cualquier día o rango: commits (incluidos **locales sin subir**), reuniones, tareas de Notion, mensajes de Slack.
3. **Resumen de lo hecho (para volcar a "I'M BACK").** La página "I'M BACK" es el **diario de trabajo** del usuario (lo que hace cada día). El dashboard genera un borrador del bloque del día **con el mismo formato que la página** (fecha → proyecto → lista), a partir de commits, reuniones y WIP, para que **el usuario lo copie y lo pegue él mismo** en I'M BACK. **El dashboard no escribe en Notion** (solo botón "Copiar"). Escritura en Notion = mejora futura y siempre con confirmación.
4. **Borrador de stand-up** para el canal de Slack **`#equipo-tecnologia-stand-up`**: "Ayer / Hoy / Bloqueos", generado con Claude. El "Ayer" es **sobre todo un resumen de lo apuntado en I'M BACK el día laborable anterior**; commits y reuniones solo complementan (p. ej. avisar de algo hecho y no apuntado). El usuario lo copia y lo pega en Slack; el dashboard no publica.
5. **Parte de horas en formato calendario** (ver 7.5): para un día o una semana, propone en qué franjas se hizo cada tarea, con horas aproximadas y categoría, para que el usuario lo copie a mano en el calendario de la plataforma interna **1million hub**. El dashboard **no** tiene acceso al hub ni lo rellena.

### Reglas de negocio (no negociables)

- **Días laborables = lunes a viernes.** "El día anterior" es el **día laborable anterior**: si hoy es lunes, ayer = viernes. Sábados y domingos no se trabaja: no cuentan como "ayer" ni se muestran como días de trabajo. (Festivos: fuera de alcance salvo que el usuario lo pida; deja un `holidays: []` en config.)
- **Este repo (el del dashboard) se excluye siempre** de commits, resúmenes, stand-up y tareas de Notion. Es un proyecto personal, no trabajo de empresa. Excluye por ruta absoluta del propio repo (`dashboard/`) en `config.yaml` (`exclude_repos`). Aplica el filtro en el colector, no en la UI.
- **Sin API key de Anthropic.** Toda la IA va por `claude -p` (Claude Code en modo headless, con la suscripción). Prohibido usar el SDK/HTTP de la API.
- **Solo lectura** sobre todas las fuentes externas (Notion, Calendar, Slack, GitHub).
- **Privacidad:** el servidor escucha solo en `127.0.0.1`. Envía a Claude datos agregados y recortados (títulos de commit, nunca diffs completos ni conversaciones enteras de Slack). Recuérdale al usuario que revise la política de su empresa sobre enviar contenido de Slack/Notion a un proveedor de IA.

---

## 2. Arquitectura: separar *recoger datos* de *resumir*

La lectura de las fuentes **no usa IA**: scripts normales con sus propias credenciales guardan todo en SQLite. Claude solo se usa al final para resumir y redactar. Motivos: gasta poca cuota de la suscripción, es rápido y reproducible.

```
┌──────────────── Colectores (Python, sin IA) ────────────────┐
│ Git local · Notion · Google Calendar · Slack · GitHub       │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
                  SQLite  (tabla "activity")
                            │
           ┌────────────────┴──────────────────┐
           ▼                                   ▼
   Dashboard web local                Resumidor: `claude -p`
   (FastAPI + HTMX)                   (stand-up, resumen del día,
           ▲                           resumen para Notion)
           └──────── resultados guardados en SQLite ──────────
```

Por qué NO dejar que Claude *interprete* las fuentes vía MCP: gasta más cuota, es lento y da resultados distintos cada vez.

**Excepción decidida el 2026-11-11 — Calendar y Slack vía conectores de Claude.** El admin de Workspace bloquea la iCal secreta y Slack suele exigir aprobación de admin, así que estos dos colectores leen a través de los conectores de la cuenta de Claude (ya conectados: Google Calendar, Notion, Slack), pero **de forma determinista**:
- `claude -p` con `--model haiku`, `--output-format stream-json --verbose` y `--allowedTools` limitado a las herramientas **de lectura** concretas que hagan falta (ver 5.2 y 5.3). Nunca permitir herramientas de escritura (`send_message`, `create_*`, `update_*`, `add_*`, `schedule_*`).
- Los datos se sacan **del `tool_result` en bruto** del stream (JSON tal cual lo devuelve Google/Slack), **no** de la respuesta redactada por Claude. Si no hay `tool_result` válido o viene con `is_error`, el colector falla y lo registra en `sync_state`.
- Frecuencia baja (p. ej. al arrancar el dashboard, en el job matinal y con botón "Actualizar"), no cada 30 min.
- Coste medido: ~6 s y ~0,004 USD equivalentes por llamada con Haiku (con suscripción, consume cuota, no se factura).
- Notion **no** usa el conector: tiene su propio OAuth (5.1), más rápido y sin cuota.
- La interfaz `collect(since, until)` es la misma; si algún día hay credenciales propias, se cambia el colector sin tocar el resto.

### Llamar a Claude desde Python

```python
import os, subprocess, json
env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # fuerza suscripción
p = subprocess.run(
    ["claude", "-p", prompt, "--output-format", "json", "--model", "sonnet"],
    input=json.dumps(contexto, ensure_ascii=False),
    capture_output=True, text=True, encoding="utf-8", env=env, timeout=300,
)
resultado = json.loads(p.stdout)["result"]
```

- Guarda en `summaries.input_hash` un hash del contexto; si no cambió, **no vuelvas a llamar** a Claude.
- Si `claude` no está en el PATH desde el programador de tareas de Windows, usa la ruta absoluta (configurable).
- Si la llamada falla por límite de cuota, muestra el error en la UI y conserva el último resultado; no reintentes en bucle.

---

## 3. Stack

| Pieza | Elección |
|---|---|
| Lenguaje | Python (3.12–3.14 según compatibilidad de librerías) con `venv`/`uv` |
| Backend | FastAPI + Uvicorn |
| Frontend | Plantillas Jinja2 + HTMX + CSS sencillo (sin paso de build). Identidad visual de 1MillionBot (skill `brand-1mb`): rojo `#CD3434` muy presente, coral `#FE6565` solo como acento puntual (commits "solo local", reuniones), fondo blanco, texto `#1D1D1D`, grises `#D2D2D2`/`#949494` en detalles, Montserrat (Google Fonts) con Verdana de reserva. **Modo claro y oscuro** (decisión del usuario, 2026-11-11, sustituye a "sin modo oscuro"): por defecto sigue `prefers-color-scheme`; interruptor en la barra superior que guarda la elección en `localStorage`; el tema se aplica con un script mínimo en el `<head>` (sin parpadeo). El oscuro usa gris muy oscuro (`#242424` fondo, `#2C2C2C` tarjetas), nunca negro puro; el rojo `#CD3434` se mantiene en rellenos (botones, filete, hoy: blanco encima 5,08:1) y para texto rojo en oscuro se usa `#EE6A6A` (4,59:1 sobre tarjeta; `#CD3434` daría 2,75:1, no cumple AA). **Colores de categoría del parte de horas** (decisión del usuario, 2026-11-11; fuera de la paleta de marca a propósito, como en el hub): mismo tono en ambos temas, **claro en el tema claro** y **más oscuro en el oscuro** (fondos `#2D4C7C`, `#1E5A52`, `#6A5416`, `#484C54`, `#2C5A32` con texto `#F3F5F9` ≥ 6,6:1 y bordes brillantes). Tema claro, con texto `#1D1D1D` dentro: Desarrollo de negocio = azul (`#BCD4FB`, borde `#2F6FDB`), Documentación = azul verdoso (`#AEE5DD`/`#12A08B`), Reunión = amarillo (`#FCE29A`/`#D9A400`), Tareas administrativas = gris (`#D9DCE1`/`#737A85`), Formación = verde (`#C3E8C1`/`#2E9D49`); contraste del texto ≥ 11:1. Logo: se muestra si existe `web/static/logo.png` (la skill no trae los ficheros; no se recrea a mano) |
| Pruebas de UI | Playwright (`requirements-dev.txt`) con la skill `webapp-testing`: capturas de las pantallas para revisarlas |
| Movimiento | Microinteracciones solo en CSS siguiendo `emil-design-eng`: escala 0,97 al pulsar, spinner en botones con petición en curso (`hx-disabled-elt`), fundido de 200 ms del contenido que llega por HTMX, "Copiado ✓", modal con `<dialog>` nativo (entra 220 ms, sale 150 ms), cambio de tema con fundido de 350 ms (View Transitions, con transición de colores de reserva). Solo `transform`/`opacity`/colores; `prefers-reduced-motion` quita escalas y desplazamientos |
| Skills de UI (nivel usuario, 2026-11-11) | Instaladas tras revisar su código: `frontend-design`, `webapp-testing`, `web-design-guidelines` (reglas fijadas en local, vercel-labs/web-interface-guidelines@434b7f9, sin descarga en cada uso) y `emil-design-eng`. Descartadas: `impeccable` (descarga y ejecuta un binario, hooks automáticos, telemetría, marca Montserrat como fuente "sobreusada") y `ui-ux-pro-max` (genera paletas/tipografías propias; su plugin trae skills con API key de Gemini y `npx shadcn`) |
| BD | SQLite (`db/dashboard.db`, fuera de git) |
| Git | Llamadas a `git` por `subprocess` (`git -C <repo> ...`) |
| Notion | `notion-client` (integración interna) |
| Calendar | `google-api-python-client`, `google-auth-oauthlib` |
| Slack | `slack_sdk` |
| Secretos | `.env` (python-dotenv) y/o `keyring` |
| Planificación | Programador de tareas de Windows (`schtasks`) |

---

## 4. Fuentes de datos

### 4.1 Git local (prioridad máxima, sin autenticación)

Directorio raíz de repos: `C:\Users\daxte\Documents\1MillionBot`. Los repos del usuario conviven con carpetas que no son repos.

Estado observado el 2026-11-11 (puede cambiar; **descúbrelos dinámicamente**, no los codifiques):
- Repos (carpeta `.git`): `Kanvas`, `airisk-api`, `airiskmanagement`, `boilerplate-api`, `migration-boilerplate-api`, `shannon`.
- **Worktrees** (`.git` es un *fichero* `gitdir: …`): `airisk-api-cdu` y `airisk-api-roles` (de `airisk-api`), `airiskmanagement-roles` (de `airiskmanagement`). Comparten commits con su repo principal → **deduplica commits por SHA**; el WIP (`git status`) sí se lee por worktree.
- `aurea/.git` existe pero está vacío (no es repo). Los repos reales están anidados.
- **Repos anidados**: `aurea/aurea-1mb`, `aurea/aurea-api`, `ibh/bff-user-control-panel`, `ibh/ibh-api`, `millie/apiREST`, `millie/dashboard`, `rec-aereas/juridocraft-api`, `rec-aereas/juridocraft-assist`. Escanea hasta profundidad 3 buscando `.git` (carpeta o fichero).
- La carpeta `dashboard/` (este proyecto) debe **excluirse por ruta absoluta**: `millie/dashboard` es un repo de trabajo distinto con el mismo nombre y **sí** cuenta.
- **También excluidos** (decisión del usuario, 2026-11-11): `Kanvas` y `shannon`.
- **Repo → proyecto** (en `config.yaml`, `projects`; el nombre del proyecto = encabezado 3 de I'M BACK): AI Risk = `airisk-api`, `airiskmanagement` y sus worktrees; Kit migración = `boilerplate-api`, `migration-boilerplate-api`; Aurea = `aurea/*`; IBH = `ibh/*`; Millie = `millie/*`; Rec Aéreas = `rec-aereas/*`. Repo nuevo sin mapear → proyecto = nombre de la carpeta de primer nivel, y avisa en la UI.
- Proyecto especial **"1MB"** = reuniones de empresa (Sprint Review, Monthly Review…). Puede aparecer como encabezado 3 en I'M BACK. Las reuniones de Calendar que no encajan en ningún proyecto van a "1MB" (en stand-up, resumen y parte de horas).
- Identidad de autor: `pablogarcia@1millionbot.com` (firma como "Pablo García" y "pablogarcia11"); filtra por email.

Qué extraer por repo y rango de fechas (zona horaria del usuario):

1. **Commits propios, incluidos los NO subidos:**
   `git -C <repo> log --all --no-merges --author=<email> --since=<ini> --until=<fin> --format=%H%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%D`
   - `--all` incluye ramas locales sin push. Para cada commit calcula si está **sin subir** (`git branch -r --contains <sha>` vacío → `pushed=false`) y márcalo en la UI como "solo local".
   - Repite `--author` por cada email/nombre configurado (el usuario puede firmar con varios).
   - Incluye también `git reflog --date=iso` del día como señal de commits amendados/rebasados (solo informativo).
   - Guarda por commit: repo, rama(s), sha corto, mensaje, fecha, `--shortstat` (ficheros/líneas), `pushed`.
2. **Trabajo en curso sin commitear:** `git status --porcelain` y `git diff --stat` por repo → entradas `kind=wip` ("cambios sin commitear en N ficheros"). Útil para el "hoy" y para no olvidar nada del "ayer".
3. **Rama actual** de cada repo con actividad (contexto para el resumen).

Detalles de Windows: usa siempre `git -C <ruta>`; si salta "dubious ownership" no cambies la config global sin avisar, pregunta al usuario. Rutas con espacios entre comillas (varias carpetas las tienen). Codifica la salida como UTF-8 (`encoding="utf-8", errors="replace"`).

### 4.2 Diseño del modelo de datos

```sql
CREATE TABLE activity (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,        -- git | notion | gcal | slack | github
  kind TEXT NOT NULL,          -- commit | wip | note | task | task_plan | meeting | message | pr | review
  external_id TEXT NOT NULL,
  ts TEXT NOT NULL,            -- ISO 8601 con zona
  work_date TEXT NOT NULL,     -- YYYY-MM-DD en zona del usuario
  title TEXT, body TEXT, url TEXT, project TEXT, status TEXT,
  extra_json TEXT,             -- p.ej. {"pushed": false, "branch": "..."}
  UNIQUE(source, external_id)
);
CREATE TABLE summaries (
  id INTEGER PRIMARY KEY,
  work_date TEXT, kind TEXT,   -- standup | day_summary | notion_summary | weekly
  content_md TEXT, input_hash TEXT, created_at TEXT,
  UNIQUE(work_date, kind)
);
CREATE TABLE sync_state (source TEXT PRIMARY KEY, last_ok TEXT, last_error TEXT);
```

Upserts idempotentes sobre `(source, external_id)`. Todos los colectores implementan una interfaz común `collect(since, until) -> list[Activity]`.

---

## 5. Conexiones y autenticación (guía para pedirle los pasos al usuario)

### 5.1 Notion (workspace `1millionbot`)

Páginas relevantes:
- **Página "I'M BACK"** (diario de trabajo y destino del resumen) — `https://app.notion.com/p/1millionbot/I-M-BACK-3f3687e73de18073956ac811a2c466e2`
  ID de página: `3f3687e7-3de1-8073-956a-c811a2c466e2`. Estructura:
  - **Encabezado 1 desplegable (`heading_1`) por día**, en orden cronológico, con formato `<Día de la semana> <dd>/<mm>/<aaaa>` (verificado: "Martes 10/11/2026", "Miércoles 11/11/2026"). Parsea con tolerancia: tildes, mayúsculas, ceros a la izquierda, año de 2 o 4 cifras. Hay huecos de días (p. ej. del 26/10 al 10/11 no hay entradas).
  - Los hijos del H1 son una **secuencia plana**: un `heading_3` por proyecto (p. ej. "AI Risk", "Kit migración") seguido de sus `bulleted_list_item` **como hermanos** (no como hijos del H3) hasta el siguiente H3. Las viñetas pueden tener sub-viñetas anidadas (lee recursivamente).
  - Dentro de cada proyecto, **lista de lo hecho ese día**: cambios de código (poco técnicos), cambios de documentación, reuniones de Calendar con apuntes. Frases como "Pasado a production" indican despliegue.
  - Ignora viñetas vacías (el día en curso suele tener una).
  - **Un proyecto vacío significa "aún no apuntado"**, no "no se ha hecho nada": no lo trates como ausencia de trabajo (para "ayer", indica que no hay notas y apóyate en git/Calendar; para "hoy", no saques conclusiones).
  - La página no está al día en el pasado; el usuario la rellenará a diario desde el 2026-11-11. Si falta el bloque de un día, avisa y usa git/Calendar como respaldo.
  - **Pendientes para el día siguiente**: dentro de cada proyecto, un subapartado **"Pendiente:"** seguido de la lista de pendientes. Lo que va bajo "Pendiente:" **no es trabajo hecho**: exclúyelo de resúmenes, stand-up "Ayer" y parte de horas, y llévalo a "Hoy" del día laborable siguiente. Parsea con tolerancia (puede ser texto, negrita o un encabezado; con o sin dos puntos; los ítems pueden ser hijos del bloque o los elementos de lista que le siguen hasta el siguiente encabezado). Aún no hay ningún caso real (se empieza a usar el 2026-11-11): cuando aparezca el primero, verifica el parseo con el usuario.
- **Base de datos "Tareas"** (workspace 1millionbot) — `https://app.notion.com/p/1millionbot/b92ea782b9114e74b4d20998a47c343e?v=1c3a90e3e55343e3b6e1502aa7e7fa31`
  ID: `b92ea782-b911-4e74-b4d2-0998a47c343e`. Cada tarea es una página. Columnas de estado vistas: **Backlog, In progress, Done, Weekly backlog**. Vistas: "Mis tareas", "Mis tareas activas", "Tareas de todos", "Por proyecto", "Mías", "Tablero", "Tabla".
  Filtra **solo tareas del usuario y activas**. Verificado el 2026-11-11 con la API (`Notion-Version: 2022-06-28`, `POST /databases/{id}/query`):
  - "Mis tareas" = propiedad people **`Persona Responsable`** contiene al usuario (Notion user id `356d872b-594c-81c5-a0ce-00025064453c`, "Pablo García Aljibe"). La propiedad `Asignar` no se usa (0 tareas).
  - Activas = `Status` (tipo status) **distinto de `Done` y `Archived`**. Valores: To assign, Blocked, Paused, Backlog, Weekly backlog, Daily Backlog, In progress, To validate, Done, Archived. Resultado real: 3 activas (2 In progress, 1 Weekly backlog), 120 Done — coincide con el tablero.
  - Título en `Tarea`. Otras útiles: `Fecha`, `Fecha inicio`, `Fecha Fin`, `Fecha límite`, `Fecha de Vencimiento` (date), `Prioridad`, `Tipo`, `Etiquetas`, `Sprint History`, `ID de la tarea`. La base es compartida por toda la empresa y tiene muchas propiedades de otros equipos: ignóralas.
  - Orden en "Hoy": In progress → Daily Backlog → To validate → Weekly backlog → Blocked/Paused → Backlog/To assign.

Autenticación (el usuario **no tiene permiso para crear conexiones internas** con token en el workspace; solo puede crear conexiones **OAuth** con alcance de usuario):
1. ✅ (2026-11-11) Creada la conexión OAuth `dashboard-personal`, espacio de desarrollo 1millionbot, URI de redirección `http://localhost:8765/oauth/notion/callback` (aceptada por Notion).
2. ✅ Capacidades: solo **Leer contenido** + **leer información de usuario incluidos emails** (para filtrar "mis tareas"). Sin actualizar/insertar ni comentarios.
3. Copiar *OAuth client ID* y *client secret* → `.env` como `NOTION_CLIENT_ID` y `NOTION_CLIENT_SECRET` (que no los pegue en el chat).
4. ✅ (2026-11-11) Autorizado con `python -m collectors.notion_auth`: token en `secrets/notion_token.json`, workspace 1millionbot, lectura de I'M BACK y Tareas verificada. Si el token caduca, renuévalo con `grant_type=refresh_token`.
   - Si Notion no acepta `http://localhost` como redirección o un admin bloquea la instalación, **plan B**: leer Notion a través del conector MCP de Notion de la cuenta de Claude (`claude -p` con salida en bruto, solo lectura, pocas veces al día por el coste de cuota), o pedir a un admin un token interno.

Verifica leyendo la página I'M BACK con `notion-client` y enséñale al usuario el texto extraído para confirmar el parseo.

### 5.2 Google Calendar

✅ **Vía elegida (2026-11-11): conector Google Calendar de Claude** (ver sección 2). Verificado: `claude -p --allowedTools "mcp__claude_ai_Google_Calendar__list_events"` devuelve en el `tool_result` el JSON de eventos de Google (`events[]` con `id`, `summary`, `start.dateTime`, `end.dateTime`, `attendees`, `organizer`, `htmlLink`, `status`, `eventType`, `conferenceUrl`); sin `events` = día sin eventos. Ejemplo real: 2026-11-10 11:00–12:00 "Migración - Revisión kit". Un primer intento dio `Insufficient scope`; se resolvió reconectando el conector en claude.ai marcando todos los permisos.
- Guarda solo eventos `confirmed` en los que el usuario no haya rechazado (`attendees[self].responseStatus != declined`); ignora eventos de día completo para el parte de horas.
- ✅ Implementado en `collectors/gcal.py` (`kind=meeting`, `extra.start/end`). Proyecto de la reunión por palabras clave del título (`meeting_keywords` en `config.yaml`); si no encaja → "1MB". Verificado: 3 reuniones del 02 al 11/11/2026.

Alternativa con credenciales propias (solo si el conector deja de servir):

1. `https://console.cloud.google.com` → proyecto nuevo (p. ej. "dashboard-personal") → habilitar **Google Calendar API**.
2. Pantalla de consentimiento OAuth (usuario interno o de prueba) → crear credenciales **OAuth client ID → Aplicación de escritorio** → descargar `credentials.json` a `dashboard/secrets/` (ignorada por git).
3. Primera ejecución: abre el navegador para autorizar con scope **`https://www.googleapis.com/auth/calendar.readonly`**; el token queda en `secrets/token.json`.
4. Pregunta qué calendarios incluir (principal y/o de equipo).
- (2026-11-11) La **dirección secreta iCal no está disponible** (el admin de Workspace la tiene desactivada; solo aparece "Dirección pública de iCal", que exige hacer público el calendario: **no usarla**). Por eso se va por OAuth (pasos 1–3).
- Si el admin también bloquea las apps OAuth propias, plan B: leer Calendar con el conector MCP de Google Calendar de la cuenta de Claude (ya conectado), pocas veces al día por el coste de cuota.

### 5.3 Slack

**Vía elegida (2026-11-11): conector Slack de Claude** (ver sección 2), conectado por el usuario. Herramientas **de lectura** permitidas: `mcp__claude_ai_Slack__slack_search_public_and_private`, `slack_search_public`, `slack_read_channel`, `slack_read_thread`, `slack_read_user_profile`, `slack_search_users`, `slack_search_channels`, `slack_list_user_channels`. El conector también expone herramientas de escritura (`slack_send_message`, `slack_send_message_draft`, `slack_schedule_message`, `slack_create_*`, `slack_update_*`, `slack_add_*`…): **prohibidas** en los colectores. (Publicar el stand-up como borrador con `slack_send_message_draft` sería una mejora futura, solo con petición expresa y confirmación.)

Alternativa con credenciales propias (solo si el conector deja de servir):

1. `https://api.slack.com/apps` → **Create New App** (from scratch) en el workspace de la empresa.
2. *User Token Scopes* de solo lectura: `search:read`, `channels:history`, `groups:history`, `im:history`, `users:read` (ajusta al mínimo necesario).
3. Instalar en el workspace → copiar *User OAuth Token* (`xoxp-…`) a `.env` como `SLACK_USER_TOKEN`.
4. **Probable bloqueo:** muchos workspaces exigen aprobación de un administrador para instalar apps. Si pasa, avisa al usuario, deja Slack desactivado (`enabled: false` en config) y continúa con el resto; no es bloqueante.
5. Qué leer: `search.messages` con `from:@usuario after:<fecha>`, menciones al usuario, y canales concretos que él indique. Guarda texto recortado (≤300 caracteres por mensaje).

### 5.4 GitHub remoto (opcional)

Con el git local casi todo está cubierto. Para PRs y reviews pendientes: token *fine-grained* (solo lectura: `Contents`, `Pull requests`, `Metadata`) en `GITHUB_TOKEN`, o instalar `gh` (`winget install GitHub.cli`) y `gh auth login`. Consultas útiles: PRs abiertas del usuario, PRs en las que se le pide review (`review-requested:@me`).

---

## 6. Lógica de fechas (implementar y testear primero)

```python
def previous_workday(d):  # d: date
    d -= timedelta(days=1)
    while d.weekday() >= 5:  # sáb=5, dom=6
        d -= timedelta(days=1)
    return d
```

- Lunes → viernes anterior. Si el usuario abre el dashboard en fin de semana, "hoy" se muestra como último día laborable (viernes) con aviso, o vista vacía; confírmalo con él.
- "Ayer" para el stand-up = `previous_workday(hoy)`. El rango del timeline por defecto es ese día completo 00:00–23:59 en la zona del usuario.
- Tests unitarios obligatorios: lunes, martes, sábado, domingo, cambio de mes/año y cambio horario (DST).

---

## 7. Funcionalidades y prompts

### 7.1 Vista "Hoy" (principal)
Secciones: **Tareas de hoy** (tareas activas del usuario en la base Tareas + pendientes apuntados ayer en I'M BACK), **Reuniones** (Calendar), **Trabajo sin commitear / commits sin subir** (para no perder nada), y más adelante **Pendientes de revisión/menciones**. Cada ítem con su origen y enlace.

### 7.2 Timeline por día/rango
Selector de fecha (saltando fines de semana con las flechas), filtros por fuente y repo, marcas "solo local" en commits sin push.

### 7.3 Resumen para I'M BACK
Selector de día o rango → botón **Generar** → borrador con el formato de I'M BACK (encabezado de fecha → un apartado por proyecto → lista de lo hecho, poco técnico; reuniones con hueco para apuntes), en markdown que se pegue bien en Notion, con botón **Copiar**. Editable en pantalla antes de copiar. Si ese día ya tiene notas en I'M BACK, muestra solo lo que falta (commits/reuniones no reflejados). Agrupa repos por proyecto (p. ej. `airisk-api` + `airiskmanagement` → "AI Risk"): mapeo repo→proyecto en `config.yaml`, a confirmar con el usuario.

### 7.4 Stand-up (para `#equipo-tecnologia-stand-up`, canal `C056VQM4E74`)
Prompt guardado en `prompts/standup.md`. Contexto JSON: **bloque de I'M BACK de `previous_workday(hoy)`** como fuente principal (sin lo de "Pendiente:") + commits/reuniones de ese día como apoyo; para "hoy": pendientes de I'M BACK, tareas activas de Notion y reuniones de hoy. Sin inventar nada que no esté en los datos, sin mencionar este repo. Si "ayer" no tiene notas en I'M BACK, dilo y resume desde git/Calendar. Editable y botón **Copiar**.

**Formato exacto** (el que el usuario ya publica en el canal; verificado leyendo **solo sus propios mensajes** del 10 y 11/11/2026 — del canal solo interesa ese formato, no el contenido de otros miembros). Markdown de Slack (`*negrita*`), viñetas `•` por proyecto y `◦` sangradas con 4 espacios por tarea:
```
Buenos días! :saluting_face:
*Tareas realizadas el último día*
• AI Risk
    ◦ Revisar permisos de roles en aprobaciones de Alta dirección y Soporte
    ◦ Corregir incidencias del flujo de casos de uso
    ◦ Subir cambios a producción
*Tareas que haré durante hoy*
• AI Risk
    ◦ Probar flujo completo con un caso de uso de prueba
• Kit migración
    ◦ Reunión revisión kit
```
- Sin sección de "Bloqueos" (el usuario no la usa).
- Cada tarea: frase corta en infinitivo, poco técnica, ~4–10 palabras ("Corregir…", "Revisar…", "Subir a producción"). Condensa las notas largas de I'M BACK en 5–9 puntos por proyecto como máximo; los "Pasado a production" se agrupan en un único "Subir cambios a producción".
- Reuniones de hoy van en "hoy" bajo su proyecto como "Reunión <tema>".

### 7.5 Parte de horas (calendario para 1million hub)

En la plataforma interna **1million hub** (Trabajo → Tareas → Mis tareas) cada empleado apunta en un calendario semanal (L–V) las tareas realizadas cada día con su franja horaria y categoría; se contabilizan las horas diarias y la semana se envía a aprobación. El hub ya importa las reuniones de Google Calendar por su cuenta (y tiene un botón "Notion" por día que **no funciona bien: ignóralo**). **El dashboard no tiene acceso al hub**: solo genera la propuesta para que el usuario la copie a mano.

- **Selector:** un día o una semana (L–V). Vista en **rejilla de calendario** parecida a la del hub (columnas = días, filas = horas), y también como lista de texto copiable.
- **Jornada por defecto** (configurable en `config.yaml`): **08:30–17:30** con comida **generalmente 14:00–15:00**. **Mínimo 8 h trabajadas al día** (puede superarse; no tiene que cuadrar exacto).
- **Duraciones en cuartos de hora** (decisión del usuario, 2026-11-11): cada tarea dura **15 min como mínimo** y siempre un múltiplo de 15 (15 min, 30 min, 45 min, 1 h, 1 h 15…), según lo que estimen los commits; inicios y finales en :00, :15, :30 o :45. Las reuniones conservan su hora real de Calendar. Configurable (`min_block_minutes`, `block_step_minutes`).
- **Estimación de duración a partir de los commits:** ordena los commits del día por hora; el tiempo de una tarea ≈ desde el fin del bloque anterior (o inicio de jornada, vuelta de comer o fin de reunión) hasta el último commit de esa tarea. El hueco entre commits indica cuánto se tardó. **No un bloque por commit**: agrupa varios commits/cambios relacionados (mismo repo/rama/tema y entrada de I'M BACK) en una sola tarea. Referencia de cómo queda: el lunes 2026-11-09 en el hub (≈10 bloques de "AI Risk - …" de duración variable entre 08:30 y 17:30).
- **Categorías** (exactamente estas): **Desarrollo de negocio**, **Reunión**, **Documentación**, **Tareas administrativas**, **Formación**. En el hub, el trabajo de desarrollo/código se apunta como *Desarrollo de negocio*; documentación técnica o de producto como *Documentación*.
- **Títulos** con el formato del hub: `<Proyecto> - <tarea>` (p. ej. "AI Risk - Permisos de Soporte e incidencias por rol").
- **Cómo se construye:**
  1. Las **reuniones de Calendar** se colocan en su hora real como *Reunión* (son fijas).
  2. Las **tareas hechas ese día según I'M BACK** (fuente principal; nunca lo de "Pendiente:") se colocan en el orden y con la duración que indiquen sus commits (paso anterior). Tareas sin commits (documentación, revisiones…) ocupan los huecos restantes. Si no hay notas en I'M BACK, propone desde git y avisa.
  3. Preprocesado **determinista** en Python (orden de commits, huecos, reuniones fijas, comida) y Claude solo **agrupa y titula** (`claude -p`, prompt `prompts/timesheet.md`): sin solapes, bloques ≥ 15 min en múltiplos de 15, total ≥ 8 h, sin inventar tareas que no estén en los datos.
- Cada bloque es **editable** en pantalla (mover, cambiar duración, categoría o título) antes de copiar. Muestra el total de horas por día y aviso si baja de 8 h.
- Salida de `claude -p` en JSON estructurado (`[{date, start, end, project, title, category}]`) para pintar la rejilla; validar el JSON (sin solapes, bloques ≥ 15 min, total ≥ 8 h, categoría válida) antes de mostrarlo. Se guarda en `summaries` con `kind=timesheet`.

**Implementado (2026-11-11)** — `/timesheet` (enlace "Parte de horas" en la barra):
- Vista semanal tipo hub: columnas L–V sobre rejilla 07:00–20:00, bloques coloreados por categoría, total por día y de la semana. Cada día se genera por separado (botón "Generar" o "Generar semana", en paralelo) y se cachea; si los datos cambian se avisa y se puede "Regenerar". "Texto para copiar" por día (editable) con "Copiar". "Actualizar datos de la semana" recoge git + Notion + Calendar del rango.
- `core/timesheet.py` (determinista, con tests): comida de 60 min en el hueco sin commits ni reuniones más cercano a las 14:00 (entre 13:00 y 16:00, en cuartos de hora); la jornada se alarga si hay commits o reuniones fuera de 08:30–17:30; cada tarea va del final de la anterior a su último commit; huecos entre dos tramos de la misma tarea (p. ej. cortada por una reunión) son de esa tarea; los demás huecos, para tareas de I'M BACK sin commits según su peso estimado; si no hay, se alarga la tarea anterior; bordes redondeados al cuarto de hora (salvo los fijos de reuniones y comida), bloques contiguos con el mismo título fusionados, bloques < 15 min absorbidos por el vecino; aviso si el día baja de 8 h.
- `prompts/timesheet.md`: Claude solo devuelve JSON con tareas (título, proyecto, categoría, commits o minutos estimados). `parse_tasks` valida: commits inventados o repetidos fuera, categoría inválida → "Desarrollo de negocio", commits sin asignar → tarea propia. Una respuesta inválida no se guarda.
- Cada bloque es un botón: al pulsarlo se abre un modal con el nombre completo de la tarea, horario, duración, tipo (con su color) y proyecto. Resuelve los títulos cortados en bloques de 15–30 min. Se cierra con Esc, la × o pulsando fuera.
- Limitación conocida: como los commits ocupan casi toda la jornada, las tareas sin commits (documentación, informes) suelen quedar con poco tiempo al final del día. Revisarlo con el usuario; mejora futura: edición de bloques en la rejilla.

### 7.6 Ajustes (icono ⚙ en la barra superior, `/settings`)
- Tabla con todos los repos descubiertos (proyecto, si es worktree) y dos interruptores por repo: **Visible** (oculta commits, WIP y commits sin subir de ese repo) y **Cambios sin commitear** (oculta solo el WIP).
- Se guarda en SQLite (`repo_settings`), no en `config.yaml`. El filtro se aplica al preparar los datos de las vistas (`core/views.py`), así que **lo oculto tampoco se envía a Claude**. Los datos se siguen recogiendo: al reactivar aparece al momento.
- Distinto de `exclude_repos` (config): lo excluido allí no se recoge nunca (este repo, Kanvas, shannon).
- Los worktrees comparten commits con su repo principal: ocultar un worktree solo oculta su WIP.

Los prompts (`standup.md`, `day_summary.md`, `notion_summary.md`, `timesheet.md`) viven en ficheros para que el usuario los ajuste sin tocar código. Regla común en todos: *"Usa solo la información proporcionada. Si algo no está claro, dilo en vez de inventarlo."*

---

## 8. Estructura del proyecto

```
C:\Users\daxte\Documents\1MillionBot\dashboard\
├─ PLAN_TECNICO.md
├─ README.md
├─ CONTRIBUTING.md        # convención de commits (Conventional Commits, en inglés)
├─ config.yaml            # emails, usuario, tz, repos_root, exclude_repos, fuentes activas, hora stand-up
├─ .env / .env.example    # tokens (el .env fuera de git)
├─ secrets/               # credentials.json, token.json (fuera de git)
├─ core/                  # config.py · dates.py (días laborables) · db.py (SQLite) · views.py (datos por vista y contexto para Claude)
├─ collectors/            # base.py · git_local.py · notion_auth.py · notion.py · gcal.py · slack.py · github.py
├─ llm/claude_cli.py      # envoltorio de claude -p + caché por hash
├─ prompts/               # standup.md · day_summary.md · notion_summary.md
├─ web/                   # app.py · templates/ · static/
├─ db/                    # schema.sql · dashboard.db (fuera de git)
├─ jobs/                  # collect_all.py · morning_job.py
├─ tests/                 # fechas, parseo git, filtros de exclusión
└─ .gitignore             # .env, secrets/, db/*.db
```

Inicializa este directorio como repo git propio (`git init`) con `.gitignore` correcto **antes** del primer commit, para que ningún secreto se versione.

---

## 9. Fases y criterios de aceptación

**Fase 1 — MVP con git local (sin credenciales externas)**
- ✅ (2026-11-11) `config.yaml`, SQLite, colector git local con commits (incluidos no pushed) y WIP: `python -m jobs.collect_all [--date D | --since A --until B] [--show]`. Verificado con datos reales: 16 commits el 10/11 (todos subidos), 5 "solo local" y 2 repos con WIP el 11/11; worktrees deduplicados; `dashboard/`, `Kanvas` y `shannon` excluidos.
- ✅ Lógica de día laborable con tests (`python -m pytest`: 14 tests, incluidos DST y cambio de año).
- ✅ Web (`python -m web.app`, http://127.0.0.1:8765): vista por día con flechas que saltan fines de semana, notas de I'M BACK, commits con marca "solo local", y para hoy "Qué toca hoy" (pendientes del día anterior, tareas activas, WIP y commits sin subir). Botones "Actualizar datos" y "Generar stand-up" / "Regenerar" / "Copiar".
- ✅ Adelantado de la Fase 2: colector de Notion (`collectors/notion.py`) con notas (`kind=note`) y pendientes (`kind=task_plan`) de I'M BACK y tareas activas (`kind=task`). Las notas de un rango se reemplazan en cada recogida (las ediciones y borrados en Notion se reflejan).
- ✅ `llm/claude_cli.py`: `claude -p --tools "" --strict-mcp-config` (sin herramientas ni conectores), contexto por stdin, `cwd` fuera de los repos, caché por hash en `summaries`; si falla se muestra el error y se conserva el último resultado.
- ⏳ Pendiente de validar por el usuario: stand-up generado para el 11/11 comparado con el que publicó.
- ✅ Aceptación: ejecutar para "ayer laborable" lista commits reales de los repos del usuario, marca los no subidos, **no aparece nada del repo `dashboard/`**, y genera un stand-up coherente que el usuario valida.

**Fase 2 — Notion**
- Lectura de I'M BACK y de tareas explícitas; vista "Hoy" con tareas del día.
- Apartado "Resumen para Notion" (día o rango) con botón Copiar.
- ✅ Aceptación: el usuario ve en "Hoy" lo que apuntó el día laborable anterior, y puede copiar un resumen del día en el formato de su página.

**Fase 3 — Google Calendar, parte de horas y Slack**
- Reuniones del día/ayer.
- **Parte de horas** (7.5) para día y semana.
- Señales de Slack (si el workspace lo permite).
- ✅ Aceptación: para un día con notas en I'M BACK, commits y reuniones, la propuesta suma ≥ 8 h sin solapes, con bloques ≥ 15 min (múltiplos de 15) que agrupan commits relacionados, duraciones coherentes con los huecos entre commits, reuniones a su hora y solo las cinco categorías.

**Fase 4 — Automatización**
- `schtasks`: colectores cada 30 min (laborables) y job matinal (stand-up a la hora configurada, solo L–V). Notificación de Windows al terminar.
- Resumen semanal; búsqueda en el historial; GitHub remoto (PRs/reviews).

**Mejoras futuras (solo con petición expresa):** escribir el resumen en Notion con confirmación previa, publicar el stand-up en Slack con confirmación.

---

## 10. Cómo trabajar con el usuario

- Un paso cada vez; confirma que cada conexión funciona (muestra datos reales leídos) antes de la siguiente.
- Usa `AskUserQuestion`/preguntas concretas para lo pendiente de aclarar. **Lista de preguntas abiertas:**
  1. Calendarios de Google a incluir (de momento solo el principal) y canales/palabras clave de Slack relevantes.
  2. Festivos.
- **GitHub remoto** (PRs/reviews): aplazado por decisión del usuario (2026-11-11); queda en Fase 4.
- **Resueltas (2026-11-11):** autor git `pablogarcia@1millionbot.com`; GitHub `pablogarcia11`; stand-up 08:30 L–V, zona `Europe/Madrid`; en fin de semana "Hoy" muestra el último viernes con aviso; I'M BACK es el diario de trabajo y destino del resumen (estructura en 5.1); fuentes de "Hoy" (7.1); stand-up basado en I'M BACK para `#equipo-tecnologia-stand-up`; pendientes en I'M BACK = subapartado "Pendiente:" dentro del proyecto; parte de horas para 1million hub (7.5); mapeo repo → proyecto y proyecto "1MB" (4.1); Kanvas y shannon excluidos; Calendar y Slack vía conectores de Claude (sección 2); Notion vía OAuth propio.
- Commits del propio dashboard: **en inglés y con Conventional Commits** (`feat: …`, `fix(git): …`), igual que el resto de repos de la empresa; norma completa en `CONTRIBUTING.md`. Sin secretos, y recuerda que la actividad de este repo nunca debe aparecer en sus resúmenes.
- Si algo requiere permisos de administrador de la empresa (Slack, Workspace, Notion), no insistas: marca la fuente como pendiente y avanza con las demás.
