# Dashboard Tasks

Dashboard local para la gente de 1MillionBot. Junta en una pantalla tu actividad del día: tus commits (también los que aún no has subido), tu diario y tus tareas de Notion, y tus reuniones de Google Calendar. Con eso te prepara el **stand-up**, las **notas para tu diario** y el **parte de horas** para el hub, listos para copiar.

Funciona solo en tu ordenador (`http://127.0.0.1:8765`), en **Windows, macOS y Linux**. Lee tus herramientas sin escribir nada en ellas y usa **Claude Code con tu suscripción** para redactar (sin API key).

## Qué necesitas

- **Python 3.11 o superior** (o [uv](https://docs.astral.sh/uv/), que lo instala por ti).
- **Git** y tus repos clonados en una o varias carpetas.
- **Claude Code** instalado y con tu sesión iniciada (ejecuta `claude` una vez en una terminal).
- En [claude.ai](https://claude.ai) → Configuración → Conectores:
  - **Google Calendar** (con todos los permisos): para las reuniones.
  - **Slack** (opcional): para que el stand-up copie tu formato de los que ya publicas. Sin él se usa un formato por defecto.
- **Un token de GitHub** (opcional): para ver en «Qué toca hoy» las pull requests que esperan tu revisión. Ajustes › GitHub explica cómo crearlo.
- Las credenciales de la conexión de Notion del equipo (`NOTION_CLIENT_ID` y `NOTION_CLIENT_SECRET`) y el ID de la base de datos de tareas (`NOTION_TASKS_DATABASE_ID`): pídelos a quien la administre.

## Instalación

Se hace una sola vez, en la carpeta del dashboard.

**Windows** (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

**macOS / Linux** (Terminal):

```bash
bash setup.sh
```

`setup` comprueba lo que falta, crea el entorno de Python, instala las dependencias, crea el fichero `.env` e instala el comando **`dashboard-tasks`**. Abre `.env` y rellena las credenciales de Notion y el ID de la base de datos de tareas.

## Arrancar el dashboard

Desde cualquier terminal y cualquier carpeta:

```
dashboard-tasks
```

Arranca el dashboard y lo abre en el navegador. Si ya estaba en marcha, solo lo abre. Para pararlo: Ctrl+C en esa terminal.

- La primera vez, abre una **terminal nueva** después de `setup` para que reconozca el comando.
- El comando se instala en `~/.local/bin` (en Windows, `C:\Users\<tú>\.local\bin`) y `setup` añade esa carpeta al PATH si hace falta.
- Sin el comando, desde la carpeta del dashboard: `.\start.ps1` (Windows) o `./start.sh` (macOS / Linux).

## Primer arranque

Ve a **Ajustes** (⚙, arriba a la derecha) y sigue **Primeros pasos**:

1. **Conectar con Notion**: inicia sesión y comparte tu página diario (y la base de Tareas).
2. **Página diario**: búscala y pulsa «Usar como diario». La vista previa te dice si el dashboard entiende su formato.
3. **Carpetas de repositorios**: «Elegir carpeta…» y selecciona donde guardas tus proyectos. Si los tienes repartidos, añade todas las carpetas que necesites con «Añadir otra carpeta…». También puedes elegir un repo suelto.
4. **Emails de autor**: se detectan de tu git; añade otros si firmas commits con más de uno.

Mientras falte algo, la vista Día te lo recuerda.

### Formatos de diario que entiende

- **Días** como encabezado (de cualquier nivel) o desplegable, como páginas hijas o como base de datos con una página por día.
- **Fechas** como `10/11/2026`, `2026-11-10` o «10 de noviembre de 2026», con o sin el día de la semana.
- **Proyectos** como encabezados o desplegables dentro de cada día (sin ellos, todo va a «General»).
- **Pendientes** bajo «Pendiente:», «Para mañana:» o como casillas sin marcar.

## Uso diario

### Día

- Qué toca hoy (pendientes de ayer, tareas activas de Notion, pull requests si conectas GitHub, reuniones, cambios sin commitear y commits sin subir), tus notas del diario y tus commits, agrupados por proyecto. Los proyectos se pueden plegar y el dashboard lo recuerda.
- Para moverte: **Hoy**, las flechas ‹ › (saltan fines de semana) o el **calendario** entre ellas para ir a cualquier día laborable (no deja elegir tus días libres). En fin de semana o festivo se muestra el último día laborable.
- El icono ↻ de cada tarjeta vuelve a leer solo esa parte; «Actualizar datos» lo lee todo. Con la vista de hoy abierta, el diario y los commits se releen solos cada 10 minutos.
- Si algún día anterior tiene commits y no lo apuntaste en tu diario, un aviso te lleva a él para generar sus notas.
- La tarjeta de la derecha tiene dos pestañas (en los días anteriores, solo las notas: el stand-up es del día en curso):
  - **Stand-up**: imita el formato de tus últimos stand-ups del canal que elijas en Ajustes.
  - **Notas para tu diario**: borrador a partir de tus commits con el formato de tu diario. Respeta lo que ya hayas escrito ese día y añade solo lo que falta.
  - ↻ regenera el texto y el icono de copiar lo deja en el portapapeles. Te avisa si hay commits nuevos desde que se generó.

- Bajo la fecha, la **semana**: pulsa un día para ir a él. Un punto verde indica que ese día tiene notas en tu diario; uno coral, que tiene commits pero aún no lo has apuntado.
- Junto a «Actualizar datos» se ve hace cuánto se leyeron los datos, y en las reuniones de hoy, cuánto falta para la siguiente.

### Parte de horas

- La semana en formato calendario, como en el hub: reuniones a su hora, tareas agrupadas y horas estimadas a partir de tus commits, en tramos de 15 minutos y con la comida respetada.
- «Generar» por día o «Generar semana». Si los datos cambian, te avisa para regenerar.
- Pulsa un bloque para ver la tarea completa (horario, duración, tipo y proyecto).
- **Corrige la propuesta sobre la rejilla**: arrastra una tarea para moverla, tira de su borde inferior para alargarla o acortarla, o púlsala para cambiar su nombre, horario, tipo y proyecto o eliminarla. «Añadir tarea» crea una nueva y «Deshacer mis cambios» vuelve a la propuesta. Eliminar una tarea pide confirmación.
- Las reuniones que coinciden en el tiempo se reparten el ancho de la columna, como en Google Calendar. Los bloques de menos de 15 minutos no tienen borde para alargarlos (taparía el bloque entero): arrástralos para moverlos y cambia su duración en el formulario.
- «Copiar semana» copia el parte de todos los días de una vez.
- Cada día tiene su «Texto para copiar», editable. Revísalo y pásalo al hub. Avisa si un día baja de 8 h.

- La columna de hoy marca la hora actual, y bajo la semana se ven las horas por categoría.
- Cuando un día llega a su jornada (8 h por defecto, o la que pongas en Ajustes), aparece una marca verde junto a su número y se celebra con una pequeña animación. Si completas toda la semana (los festivos no cuentan), sale confeti, una sola vez por semana y navegador.
- **Resumen de la semana**: debajo, Claude redacta lo conseguido en cada proyecto a partir de tu diario, para la Sprint Review. Se copia con el icono.

### Buscar

La lupa de la barra (o la tecla **/**) busca en tus commits, notas, pendientes y reuniones de cualquier día, sin distinguir tildes ni mayúsculas. Cada resultado lleva a su día.

### Atajos de teclado

Pulsa **?** en cualquier pantalla para verlos: ← → cambian de día o de semana, **T** vuelve a hoy, **D** y **P** cambian de sección, **R** actualiza los datos, **C** copia el stand-up o las notas y **/** abre el buscador.

### Animaciones

La interfaz se mueve con propósito: las tareas se deslizan a su sitio al editarlas, se levantan al arrastrarlas, caen en ola al generar el parte, los totales cuentan hasta su valor y el formulario de tarea sale del bloque que pulsas. En la vista Día, la fecha rueda palabra a palabra al cambiar de día, las tarjetas entran escalonadas, lo nuevo se despliega al actualizar, la reunión que empieza late y Claude deja una franja de luz sobre el texto que acaba de redactar. En Ajustes, los festivos se colocan solos en su sitio, los interruptores responden con un muelle y, cuando completas los primeros pasos, se celebra una sola vez. Al navegar con el teclado (← → T D P) no se anima nada. Si tu sistema tiene activado «reducir movimiento», todo se limita a fundidos cortos y no hay saltos ni confeti.

### Ajustes

- **Apariencia**: modo claro u oscuro (por defecto, el de tu sistema).
- **Notion**: conectar o desconectar la cuenta y cambiar de página diario.
- **GitHub** (opcional): cómo crear el token para ver tus pull requests y si se están leyendo bien.
- **Stand-up**: el canal donde publicas y «Volver a aprender» tu formato (se renueva solo cada semana).
- **Festivos y vacaciones**: los días que no trabajas, sueltos o por rangos. No cuentan como «ayer» en el stand-up ni piden parte. Al quitar un día aparece «Deshacer» para recuperarlo.
- **Parte de horas**: tu jornada y tu comida si no son las de la empresa (jornada parcial, intensiva…).
- **Repositorios**: carpetas, emails de autor y **qué se muestra**: por cada repo, «Visible» y «Cambios sin commitear».

## Privacidad

- Todo se queda en tu ordenador: los datos se guardan en `db/` y la web solo escucha en `127.0.0.1`.
- El dashboard **solo lee**: no escribe en Notion, Slack, Calendar, GitHub ni el hub. Copiar y pegar lo haces tú.
- Lo que ocultas en Ajustes tampoco se envía a Claude.

## Actualizar

En la carpeta del dashboard:

```bash
git pull
```

Y vuelve a ejecutar `setup` (instala dependencias nuevas y actualiza el comando; no toca tu `.env` ni tus ajustes). Reinicia el dashboard para ver los cambios. Si mueves la carpeta del dashboard, vuelve a ejecutar `setup`.

## Problemas frecuentes

- **`dashboard-tasks` no se reconoce**: abre una terminal nueva. Si sigue igual, vuelve a ejecutar `setup`.
- **No salen commits**: revisa en Ajustes las carpetas de repositorios y tus emails de autor.
- **Error en gcal**: reconecta Google Calendar en claude.ai → Conectores, con todos los permisos. Si el error habla de la sesión de Claude Code, ejecuta `claude auth login`; y si usas Claude Code con otra carpeta de configuración (`CLAUDE_CONFIG_DIR`, p. ej. para la cuenta de empresa), ponla también en el `.env` del dashboard y reinícialo.
- **El stand-up no sigue tu formato**: conecta Slack en claude.ai → Conectores y pulsa «Volver a aprender» en Ajustes. Comprueba que el canal es el tuyo.
- **Error en notion**: vuelve a conectar Notion en Ajustes.
- **«Elegir carpeta…» no abre nada**: el selector puede quedar detrás del navegador; también puedes escribir la ruta a mano.
- **El puerto 8765 está ocupado por otro programa**: ciérralo; el dashboard siempre usa ese puerto (la conexión de Notion está registrada con él).

---

## Para quien lo desarrolla

```bash
python -m pytest -q                                          # tests
python -m jobs.collect_all --date 2026-11-10 --show          # recoger un día desde la terminal
python -m jobs.collect_all --since 2026-11-03 --until 2026-11-07   # recoger un rango
python -m web.app                                            # servidor sin abrir el navegador
```

(Con el entorno activado, o usando `.venv\Scripts\python.exe` en Windows y `.venv/bin/python` en macOS / Linux.)

- Configuración común de la empresa: `config.yaml` (propiedades de la base de tareas de Notion, horario por defecto del parte, categorías, **proyectos según el nombre del repo** y palabras clave de reuniones, modelo de Claude). Lo de cada persona se guarda en su `db/` local desde Ajustes.
- Prompts que usa Claude: `prompts/`. Diseño y decisiones: [PLAN_TECNICO.md](PLAN_TECNICO.md). Commits: [CONTRIBUTING.md](CONTRIBUTING.md).
- Scripts: `setup.ps1` / `setup.sh` (instalación y comando `dashboard-tasks`), `start.ps1` / `start.sh` (arranque).
- Capturas de la interfaz con Playwright: instala `requirements-dev.txt` y `python -m playwright install chromium`.
- Animaciones: `web/static/motion.js` con GSAP y su plugin Flip, ya incluidos en `web/static/vendor/` (licencia «Standard no charge» de GreenSock). No hace falta `npm` ni ninguna instalación; sin `motion.js` las páginas funcionan igual, sin animar. Los valores comunes (curvas y duraciones) están como variables al principio de `web/static/style.css`.
- Logo: copia el PNG oficial de 1MillionBot en `web/static/logo.png`.
