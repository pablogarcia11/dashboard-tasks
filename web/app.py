"""Dashboard web local (FastAPI + Jinja2 + HTMX). Escucha solo en 127.0.0.1.

Uso:  python -m web.app
"""
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from collectors.git_local import GitLocalCollector
from core import db
from core.config import ROOT, load_config
from core.dates import date_ranges, effective_today, is_workday, next_workday, previous_workday
from core import identity, settings
from core.identity import avatar_path, display_name, initials, notion_owner
from collectors.github import github_token
from core.search import KINDS as SEARCH_KINDS, highlight, search
from core.settings import effective_config
from collectors import notion_auth
from collectors.notion import NotionClient, journal_candidates, journal_preview
from collectors.claude_connector import ConnectorError
from collectors.slack import fetch_channel_messages, own_standups
from core.timesheet import as_text, build_blocks, fmt, parse_tasks
from core.timesheet import edited_json, parse_edited, short_day_warning
from core.views import (day_data, journal_notes_context, standup_markdown, standup_context, timesheet_inputs,
                        unnoted_days, week_overview, weekly_context)
from jobs.collect_all import run_collect
from llm.claude_cli import ClaudeError, generate, input_hash

WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
          "octubre", "noviembre", "diciembre"]

cfg = load_config()
collect_lock = threading.Lock()


def holidays() -> tuple[str, ...]:
    """Días no laborables: los de la empresa (config.yaml) y los festivos y vacaciones de la persona (Ajustes)."""
    company = [str(d) for d in cfg["schedule"].get("holidays") or []]
    return tuple(sorted(set(company) | set(settings.days_off(db.connect()))))


def today() -> date:
    return datetime.now().astimezone().date()


def collect(start: date, end: date, only=None) -> list[str]:
    with collect_lock:  # SQLite + colectores: una recogida cada vez
        con = db.connect()
        return run_collect(effective_config(cfg, con), con, start, end, only)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Al arrancar, refresca el día laborable anterior y hoy sin bloquear el servidor
    t = today()
    threading.Thread(target=collect, args=(previous_workday(t, holidays()), t), daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "web" / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "web" / "templates")
templates.env.filters["long_date"] = lambda d: f"{WEEKDAYS[d.weekday()]} {d.day} de {MONTHS[d.month - 1]}"
templates.env.filters["title_date"] = lambda d: f"{WEEKDAYS[d.weekday()].capitalize()} {d.day} de {MONTHS[d.month - 1]} {d.year}"
templates.env.filters["hhmm"] = lambda ts: ts[11:16]
templates.env.globals["highlight"] = highlight
templates.env.filters["short_date"] = lambda d: f"{d.day} {MONTHS[d.month - 1][:3]}"
# Qué hacer cuando falla cada fuente (se muestra junto al error)
templates.env.globals["sync_hints"] = {
    "git": "Comprueba que el repo existe y que git funciona en él; si el aviso habla de «dubious ownership», revisa la configuración de git del repo.",
    "notion": "Si el permiso caducó o se revocó, vuelve a conectar Notion en Ajustes.",
    "gcal": "Reconecta Google Calendar en claude.ai → Configuración → Conectores, marcando todos los permisos, y pulsa «Actualizar datos».",
    "github": "Revisa el token de GitHub en .env (GITHUB_TOKEN) siguiendo Ajustes › GitHub, y pulsa «Actualizar datos».",
}
templates.env.globals["claude_hint"] = ("Si es un límite de uso de Claude, espera unos minutos y vuelve a intentarlo; "
                                        "si dice que falta iniciar sesión, ejecuta «claude» en una terminal.")
def load_identity() -> None:
    """Nombre y foto de quien usa el dashboard, deducidos de Notion/git (core/identity.py)."""
    templates.env.globals["user_name"] = display_name()
    templates.env.globals["user_initials"] = initials(display_name())
    templates.env.globals["has_avatar"] = avatar_path() is not None


def standup_channel() -> str:
    """Canal de stand-up de la persona (Ajustes); "" si aún no lo ha elegido."""
    return settings.get_all(db.connect()).get(settings.STANDUP_CHANNEL) or cfg["standup"].get("channel") or ""


def user_emails(con) -> set[str]:
    """Emails con los que se reconoce a la persona en Slack: los de git y el de su cuenta de Notion."""
    emails = set(settings.extra_authors(con)) | {identity.git_global_email() or ""}
    emails.add(((notion_owner().get("person") or {}).get("email") or ""))
    return {e.lower() for e in emails if e}


def standup_examples(con, force: bool = False) -> dict:
    """Últimos stand-ups de la persona en su canal, para imitar su formato. Se renuevan cada
    `relearn_days` días (o al cambiar de canal); si Slack falla, se conservan los anteriores."""
    try:
        stored = json.loads(settings.get_all(con).get(settings.STANDUP_EXAMPLES) or "{}")
    except ValueError:
        stored = {}
    channel, scfg = standup_channel(), cfg["standup"]
    if not channel:   # sin canal elegido no hay de dónde aprender: formato por defecto
        return {"channel": "", "examples": [], "error": None}
    age = (datetime.now().astimezone() - datetime.fromisoformat(stored["fetched_at"])).days \
        if stored.get("fetched_at") else None
    if not force and stored.get("channel") == channel and age is not None and age < scfg.get("relearn_days", 7):
        return stored
    try:
        msgs = fetch_channel_messages(channel, cfg["claude"])
        stored = {"channel": channel, "examples": own_standups(msgs, user_emails(con), scfg.get("examples", 3)),
                  "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"), "error": None}
    except ConnectorError as e:
        stored = {**stored, "error": str(e)}
    settings.set_value(con, settings.STANDUP_EXAMPLES, json.dumps(stored, ensure_ascii=False))
    return stored


def journal_title() -> str:
    """Título de la página diario elegida en Ajustes (sustituye a un nombre fijo como "I'M BACK")."""
    return settings.get_all(db.connect()).get(settings.JOURNAL_PAGE_TITLE) or "el diario"


load_identity()
templates.env.globals["journal_title"] = journal_title
templates.env.globals["standup_channel"] = standup_channel
# Logo oficial: se muestra si existe web/static/logo.png (no se versiona una copia recreada)
templates.env.globals["has_logo"] = (ROOT / "web" / "static" / "logo.png").is_file()


@app.get("/avatar")
def avatar():
    """Foto de perfil (copia local de la de Notion); el navegador la guarda un día."""
    path = avatar_path()
    if not path:
        return Response(status_code=404)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@app.get("/")
def index():
    shown, _ = effective_today(today(), holidays())
    return RedirectResponse(f"/day/{shown.isoformat()}")


@app.get("/day/{d}", response_class=HTMLResponse)
def day_view(request: Request, d: str):
    requested = date.fromisoformat(d)
    shown, weekend = effective_today(requested, holidays())
    if shown != requested and requested != today():
        return RedirectResponse(f"/day/{shown.isoformat()}")
    con = db.connect()
    nxt = next_workday(shown, holidays())
    return templates.TemplateResponse(request, "day.html", {
        "day": shown, "is_today": shown == effective_today(today(), holidays())[0], "weekend": weekend,
        "today": today(),
        "prev": previous_workday(shown, holidays()), "next": nxt if nxt <= today() else None,
        "data": day_data(con, shown, holidays()), "sync": db.sync_states(con),
        "week": week_overview(con, shown, today(), holidays()), "last_sync": last_sync(con),
        "unnoted": unnoted_days(con, today(), holidays()),
        "auto_refresh_minutes": cfg["server"].get("auto_refresh_minutes", 10),
        "standup": db.get_summary(con, shown.isoformat(), "standup"),
        "journal_notes": journal_notes_state(con, shown),
        "pending_steps": sum(not s["done"] for s in setup_steps(con)),
    })


def last_sync(con) -> str | None:
    """Última vez que alguna fuente se recogió bien (ISO), para mostrar «Actualizado hace…»."""
    stamps = [s["last_ok"] for s in db.sync_states(con).values() if s.get("last_ok")]
    return max(stamps) if stamps else None


# Tarjetas de la vista Día que se pueden actualizar por separado: plantilla y fuente que la alimenta
CARDS = {"notes": ("_card_notes.html", "notion"), "commits": ("_card_commits.html", "git")}


@app.post("/refresh/{d}/{card}", response_class=HTMLResponse)
def refresh_card(request: Request, d: str, card: str):
    """Recoge solo la fuente de una tarjeta para ese día y devuelve la tarjeta actualizada."""
    if card not in CARDS:
        return Response(status_code=404)
    template, source = CARDS[card]
    day = date.fromisoformat(d)
    collect(day, day, only={source})
    con = db.connect()
    error = db.sync_states(con).get(source, {}).get("last_error")
    is_today = day == effective_today(today(), holidays())[0]
    return templates.TemplateResponse(request, template, {
        "day": day, "is_today": is_today,
        "data": day_data(con, day, holidays()), "refresh_error": error, "refreshed": not error,
        # "Para no perder" solo existe en la vista de hoy
        "keep_safe_oob": card == "commits" and is_today,
    })


@app.get("/search", response_class=HTMLResponse)
def search_view(request: Request, q: str = ""):
    """Busca en el historial guardado. Con HTMX (al escribir) solo devuelve la lista de resultados."""
    hits, total = search(db.connect(), q)
    by_day: dict[date, list[dict]] = {}
    for h in hits:
        by_day.setdefault(date.fromisoformat(h["work_date"]), []).append(h)
    ctx = {"q": q.strip(), "by_day": by_day, "total": total, "shown": len(hits), "kinds": SEARCH_KINDS}
    template = "_search_results.html" if request.headers.get("HX-Request") else "search.html"
    return templates.TemplateResponse(request, template, ctx)


@app.get("/settings", response_class=HTMLResponse)
def settings_view(request: Request, msg: str = ""):
    con = db.connect()
    saved = settings.get_all(con)
    git = GitLocalCollector(effective_config(cfg, con))
    repos = sorted(git.repos(), key=lambda r: (r.project.lower(), str(r.path).lower()))
    mains = {r.common_dir: r for r in repos if not r.is_worktree}
    prefs = db.repo_settings(con)
    rows = []
    for r in repos:
        main = mains.get(r.common_dir)
        rows.append({"repo": r.name, "project": r.project, **prefs.get(r.name, {"visible": True, "show_wip": True}),
                     "worktree_of": main.name if r.is_worktree and main else None})
    folders = [{"path": str(root), "missing": not root.is_dir(), "repos": sum(r.root == root for r in repos)}
               for root in git.roots]
    owner = notion_owner()
    extra = settings.extra_authors(con)
    return templates.TemplateResponse(request, "settings.html", {
        "rows": rows, "msg": SETTINGS_MESSAGES.get(msg), "folders": folders,
        "steps": setup_steps(con), "path_example": PATH_EXAMPLE,
        "schedule": {"current": effective_config(cfg, con)["timesheet"],
                     "custom": any(saved.get(f"timesheet.{k}") for k in settings.TIMESHEET_KEYS),
                     "company": cfg["timesheet"]},
        "standup": {"channel": standup_channel(),
                    "stored": json.loads(saved.get(settings.STANDUP_EXAMPLES) or "{}")},
        "days_off": days_off_state(con),
        "github": {"has_token": bool(github_token()), "state": db.sync_states(con).get("github", {}),
                   "count": sum(1 for a in db.activities(con, "0000-00-00", "9999-99-99", ["github"]))},
        "authors": {"detected": sorted(git.detected_authors), "extra": [e for e in extra if e not in git.detected_authors]},
        "notion": {
            "has_credentials": all(notion_auth.client_credentials()),
            "connected": notion_auth.TOKEN_FILE.is_file(), "user": owner.get("name"),
            "workspace": notion_workspace(),
            "journal_id": saved.get(settings.JOURNAL_PAGE_ID), "journal_title": saved.get(settings.JOURNAL_PAGE_TITLE),
        },
    })


SETTINGS_MESSAGES = {
    "notion-connected": ("ok", "Notion conectado. Ahora elige tu página diario."),
    "notion-disconnected": ("ok", "Notion desconectado."),
    "notion-error": ("error", "No se pudo conectar con Notion. Vuelve a intentarlo; si se repite, revisa "
                              "NOTION_CLIENT_ID y NOTION_CLIENT_SECRET en .env."),
    "repos-added": ("ok", "Carpeta añadida. Sus repos ya aparecen en la lista de abajo."),
    "repos-removed": ("ok", "Carpeta quitada. Sus repos y sus commits ya no se muestran."),
    "standup-learned": ("ok", "Formato del stand-up actualizado con tus últimos mensajes del canal."),
    "timesheet-saved": ("ok", "Horario guardado. Regenera los días del parte de horas que quieras recalcular."),
    "timesheet-reset": ("ok", "Vuelves a usar el horario de la empresa."),
    "standup-error": ("error", "No se pudo leer el canal de Slack. Comprueba que el conector de Slack está "
                               "conectado en claude.ai y que el nombre del canal es correcto."),
}


def hx_redirect(request: Request, url: str) -> Response:
    """Lleva a `url` tras una acción de HTMX. Si solo cambia el #ancla respecto a la página abierta,
    el navegador se limitaría a desplazarse sin recargar (y no se verían los cambios): se pide recargar."""
    headers = {"HX-Redirect": url}
    current, target = urlsplit(request.headers.get("HX-Current-URL", "")), urlsplit(url)
    if (current.path, current.query) == (target.path, target.query):
        headers["HX-Refresh"] = "true"
    return Response(headers=headers)


def setup_steps(con) -> list[dict]:
    """Lo que hace falta para que el dashboard funcione a una persona nueva, y si ya está hecho."""
    saved = settings.get_all(con)
    gcal = db.sync_states(con).get("gcal", {})
    has_creds = all(notion_auth.client_credentials())
    return [
        {"label": "Claude Code instalado", "done": bool(shutil.which(cfg["claude"].get("command", "claude"))),
         "hint": "Instala Claude Code y ejecuta «claude» una vez en una terminal para iniciar sesión."},
        {"label": "Notion conectado", "done": notion_auth.TOKEN_FILE.is_file(), "href": "/settings#notion",
         "hint": None if has_creds else "Antes, añade NOTION_CLIENT_ID y NOTION_CLIENT_SECRET al fichero .env."},
        {"label": "Página diario elegida", "done": bool(saved.get(settings.JOURNAL_PAGE_ID)), "href": "/settings#notion"},
        {"label": "Carpeta de repositorios elegida", "done": bool(settings.repos_roots(con)), "href": "/settings#repos"},
        {"label": "Email de autor de git", "done": bool(identity.git_global_email() or settings.extra_authors(con)),
         "href": "/settings#repos", "hint": "Configura git config --global user.email o añade tu email en Ajustes."},
        {"label": "Google Calendar conectado en Claude", "done": bool(gcal.get("last_ok")) and not gcal.get("last_error"),
         "hint": "En claude.ai → Configuración → Conectores, conecta Google Calendar con todos los permisos y pulsa «Actualizar datos»."},
    ]


def notion_workspace() -> str | None:
    try:
        return json.loads(notion_auth.TOKEN_FILE.read_text(encoding="utf-8")).get("workspace_name")
    except (OSError, ValueError):
        return None


JOURNAL_BACKFILL_DAYS = 60   # al cambiar de página diario se releen estos días de la nueva


def refresh_in_background(only: set, days: int | None = None) -> None:
    """Recoge en segundo plano el día laborable anterior y hoy (o los últimos `days` días)."""
    t = today()
    start = t - timedelta(days=days) if days else previous_workday(t, holidays())
    threading.Thread(target=collect, args=(start, t, only), daemon=True).start()


# --- Notion: conectar, desconectar y elegir la página diario --------------------------------------

oauth_states: set[str] = set()


@app.get("/settings/notion/connect")
def notion_connect():
    if not all(notion_auth.client_credentials()):
        return RedirectResponse("/settings?msg=notion-error")
    state = secrets.token_urlsafe(16)
    oauth_states.add(state)
    return RedirectResponse(notion_auth.authorize_url(state))


@app.get("/oauth/notion/callback")
def notion_callback(state: str = "", code: str = "", error: str = ""):
    """Notion vuelve aquí tras autorizar (es el redirect registrado en la conexión OAuth)."""
    if error or not code or state not in oauth_states:
        return RedirectResponse("/settings?msg=notion-error#notion")
    oauth_states.discard(state)
    try:
        notion_auth.exchange_code(code)
    except RuntimeError:
        return RedirectResponse("/settings?msg=notion-error#notion")
    identity.reset()
    load_identity()
    return RedirectResponse("/settings?msg=notion-connected#notion")


@app.post("/settings/notion/disconnect")
def notion_disconnect(request: Request):
    con = db.connect()
    notion_auth.TOKEN_FILE.unlink(missing_ok=True)
    settings.set_value(con, settings.JOURNAL_PAGE_ID, None)
    settings.set_value(con, settings.JOURNAL_PAGE_TITLE, None)
    db.replace_kind(con, "notion", "task", [])   # las tareas eran de esa cuenta
    identity.reset()
    load_identity()
    return hx_redirect(request, "/settings?msg=notion-disconnected#notion")


@app.get("/settings/notion/pages", response_class=HTMLResponse)
def notion_pages(request: Request, q: str = ""):
    """Páginas compartidas con la conexión que pueden ser el diario (búsqueda por título)."""
    try:
        pages, error = journal_candidates(NotionClient(), q.strip()), None
    except Exception as e:  # sin conexión, token caducado...
        pages, error = [], str(e)
    current = settings.get_all(db.connect()).get(settings.JOURNAL_PAGE_ID, "")
    return templates.TemplateResponse(request, "_notion_pages.html", {
        "pages": pages, "error": error, "query": q, "current": current.replace("-", "")})


@app.post("/settings/notion/journal", response_class=HTMLResponse)
async def notion_set_journal(request: Request):
    form = await request.form()
    con = db.connect()
    changed = form["page_id"] != settings.get_all(con).get(settings.JOURNAL_PAGE_ID)
    settings.set_value(con, settings.JOURNAL_PAGE_ID, form["page_id"])
    settings.set_value(con, settings.JOURNAL_PAGE_TITLE, form["title"])
    if changed:
        # Las notas guardadas eran de la página anterior: fuera, y se releen de la nueva
        db.delete_kinds(con, "notion", ["note", "task_plan"])
        refresh_in_background({"notion"}, days=JOURNAL_BACKFILL_DAYS)
    return hx_redirect(request, "/settings#notion")


@app.get("/settings/notion/journal-status", response_class=HTMLResponse)
def notion_journal_status(request: Request):
    """Comprueba que la página diario tiene el formato esperado (días como encabezado 1 con fecha)."""
    page_id = settings.get_all(db.connect()).get(settings.JOURNAL_PAGE_ID)
    try:
        preview, error = (journal_preview(NotionClient(), page_id), None) if page_id else (None, None)
    except Exception as e:
        preview, error = None, str(e)
    return templates.TemplateResponse(request, "_journal_status.html", {"preview": preview, "error": error})


# --- Carpeta de repositorios ------------------------------------------------------------------------

picker_lock = threading.Lock()


PICK_TITLE = "Elige una carpeta con tus repositorios"
PATH_EXAMPLE = r"C:\Users\tu-usuario\Documents\repos" if sys.platform == "win32" else "/Users/tu-usuario/repos"
# tkinter en un proceso aparte: las ventanas deben abrirse en el hilo principal de un proceso
TK_PICKER = """
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
print(filedialog.askdirectory(parent=root, initialdir=sys.argv[1], mustexist=True, title=sys.argv[2]) or "")
"""


def pick_directory(initial: str | None) -> str | None:
    """Abre el selector de carpetas nativo del sistema (el servidor corre en el mismo ordenador).

    macOS: diálogo de Finder (osascript). Windows/Linux: tkinter en un proceso aparte, porque desde
    un hilo del servidor no se pueden abrir ventanas (en macOS, ni siquiera con tkinter).
    """
    start = initial or str(Path.home())
    if sys.platform == "darwin":
        script = (f'POSIX path of (choose folder with prompt "{PICK_TITLE}" '
                  f'default location (POSIX file "{start}"))')
        cmd = ["osascript", "-e", script]
    else:
        cmd = [sys.executable, "-c", TK_PICKER, start, PICK_TITLE]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=600)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() or None   # vacío si se cancela


def add_repos_folder(request: Request, path: str) -> Response:
    folder = Path(path.strip().strip('"')).expanduser()
    if not path.strip() or not folder.is_dir():
        return Response(f"No existe la carpeta «{path}».", status_code=422)
    con = db.connect()
    roots = settings.repos_roots(con)
    folder = str(folder.resolve())
    if any(os.path.normcase(folder) == os.path.normcase(r) for r in roots):
        return Response("Esa carpeta ya está en la lista.", status_code=422)
    settings.set_repos_roots(con, roots + [folder])
    refresh_in_background({"git"})
    return hx_redirect(request, "/settings?msg=repos-added#repos")


@app.post("/settings/standup/channel")
async def standup_set_channel(request: Request):
    form = await request.form()
    channel = form.get("channel", "").strip().lstrip("#")
    if not channel:
        return Response("Escribe el nombre del canal.", status_code=422)
    settings.set_value(db.connect(), settings.STANDUP_CHANNEL, channel)
    return hx_redirect(request, "/settings#standup")


@app.post("/settings/standup/learn")
def standup_learn(request: Request):
    """Vuelve a leer sus últimos stand-ups del canal (conector de Slack)."""
    stored = standup_examples(db.connect(), force=True)
    msg = "standup-error" if stored.get("error") else "standup-learned"
    return hx_redirect(request, f"/settings?msg={msg}#standup")


@app.post("/settings/timesheet")
async def timesheet_schedule(request: Request):
    """Guarda el horario de la persona para el parte de horas (o vuelve al de la empresa)."""
    form = await request.form()
    con = db.connect()
    if form.get("action") == "reset":
        for k in settings.TIMESHEET_KEYS:
            settings.set_value(con, f"timesheet.{k}", None)
        return hx_redirect(request, "/settings?msg=timesheet-reset#timesheet")
    values = {k: (form.get(k) or "").strip() for k in settings.TIMESHEET_KEYS}
    times = [values[k] for k in ("day_start", "lunch_start", "lunch_end", "day_end")]
    if not all(re.fullmatch(r"\d{2}:\d{2}", t) for t in times) or times != sorted(times) or len(set(times)) < 4:
        return Response("Revisa las horas: la comida tiene que quedar dentro de la jornada.", status_code=422)
    try:
        hours = float(values["min_daily_hours"].replace(",", "."))
    except ValueError:
        hours = -1
    if not 0 < hours <= 24:
        return Response("Las horas mínimas al día tienen que estar entre 0 y 24.", status_code=422)
    values["min_daily_hours"] = str(hours)
    for k, v in values.items():
        settings.set_value(con, f"timesheet.{k}", v)
    return hx_redirect(request, "/settings?msg=timesheet-saved#timesheet")


def days_off_state(con) -> dict:
    return {"company": date_ranges([str(d) for d in cfg["schedule"].get("holidays") or []]),
            "own": date_ranges(settings.days_off(con)), "today": today()}


@app.post("/settings/days-off", response_class=HTMLResponse)
async def days_off(request: Request):
    """Añade un festivo o unas vacaciones (un día o un rango) o quita un rango. Solo cuentan los días de L a V.
    Devuelve la lista actualizada (_days_off.html) para sustituirla en Ajustes sin recargar."""
    form = await request.form()
    con = db.connect()
    days = set(settings.days_off(con))
    try:
        start = date.fromisoformat(form.get("start", ""))
        end = date.fromisoformat(form.get("end") or form.get("start", ""))
    except ValueError:
        return Response("Elige una fecha.", status_code=422)
    if end < start:
        return Response("La fecha final no puede ser anterior a la inicial.", status_code=422)
    if (end - start).days > 92:
        return Response("Como mucho tres meses de una vez.", status_code=422)
    span = {(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)
            if (start + timedelta(days=i)).weekday() < 5}
    if form.get("action") == "remove":
        days -= span
    elif not span:
        return Response("Ese día es fin de semana: ya es no laborable.", status_code=422)
    else:
        days |= span
    settings.set_days_off(con, sorted(days))
    return templates.TemplateResponse(request, "_days_off.html", {"days_off": days_off_state(con)})


@app.post("/settings/git-authors")
async def git_authors(request: Request):
    """Añade o quita un email de autor manual (los de git config se detectan solos)."""
    form = await request.form()
    email = form.get("email", "").strip().lower()
    con = db.connect()
    emails = settings.extra_authors(con)
    if form.get("action") == "remove":
        emails = [e for e in emails if e != email]
    elif "@" not in email or " " in email:
        return Response(f"«{email}» no parece un email.", status_code=422)
    else:
        emails.append(email)
    settings.set_extra_authors(con, emails)
    refresh_in_background({"git"})
    return hx_redirect(request, "/settings#repos")


@app.post("/settings/repos-folders/pick")
def repos_folder_pick(request: Request):
    if not picker_lock.acquire(blocking=False):
        return Response("Ya hay un selector de carpetas abierto.", status_code=409)
    try:
        roots = settings.repos_roots(db.connect())
        # Empieza junto a la última carpeta añadida: las siguientes suelen estar cerca
        path = pick_directory(str(Path(roots[-1]).parent) if roots else None)
    finally:
        picker_lock.release()
    if not path:
        return Response(status_code=204)   # cancelado
    return add_repos_folder(request, path)


@app.post("/settings/repos-folders")
async def repos_folder_manual(request: Request):
    form = await request.form()
    return add_repos_folder(request, form.get("path", ""))


@app.post("/settings/repos-folders/remove")
async def repos_folder_remove(request: Request):
    """Quita una carpeta y la actividad guardada de los repos que solo estaban en ella."""
    form = await request.form()
    con = db.connect()
    before = {r.name for r in GitLocalCollector(effective_config(cfg, con)).repos()}
    settings.set_repos_roots(con, [r for r in settings.repos_roots(con) if r != form.get("path")])
    after = {r.name for r in GitLocalCollector(effective_config(cfg, con)).repos()}
    with collect_lock:
        db.delete_git_repos(con, sorted(before - after))
    return hx_redirect(request, "/settings?msg=repos-removed#repos")


@app.post("/settings/repo")
async def settings_repo(request: Request):
    form = await request.form()
    # Un checkbox desmarcado no envía "value"
    db.set_repo_setting(db.connect(), form["repo"], form["field"], form.get("value") == "on")
    return Response(status_code=204)


@app.post("/collect/{d}")
def collect_day(d: str):
    day = date.fromisoformat(d)
    collect(previous_workday(day, holidays()), day)
    return Response(headers={"HX-Refresh": "true"})


@app.post("/collect-range/{start}/{end}")
def collect_range(start: str, end: str):
    collect(date.fromisoformat(start), min(date.fromisoformat(end), today()))
    return Response(headers={"HX-Refresh": "true"})


# --- Parte de horas -------------------------------------------------------------------------

# Rejilla 07:00–20:00 a 0,8 px por minuto (48 px por hora, como Google Calendar): la semana cabe
# en pantalla. Los bloques de 15 min (12 px) se pintan en una línea; el detalle está en el modal.
GRID_START, GRID_END, PPM = 7 * 60, 20 * 60, 0.8
CATEGORY_CLASS = {"Desarrollo de negocio": "dev", "Reunión": "meet", "Documentación": "doc",
                  "Tareas administrativas": "admin", "Formación": "learn"}
templates.env.filters["fmt"] = fmt
templates.env.filters["cat_class"] = lambda c: CATEGORY_CLASS.get(c, "dev")


@app.get("/timesheet")
def timesheet_index():
    shown, _ = effective_today(today(), holidays())
    return RedirectResponse(f"/timesheet/week/{shown.isoformat()}")


@app.get("/timesheet/week/{d}", response_class=HTMLResponse)
def timesheet_week(request: Request, d: str):
    monday = date.fromisoformat(d) - timedelta(days=date.fromisoformat(d).weekday())
    days = [monday + timedelta(days=i) for i in range(5)]
    return templates.TemplateResponse(request, "timesheet.html", {
        "days": days, "today": today(), "prev": monday - timedelta(days=7),
        "next": monday + timedelta(days=7) if monday + timedelta(days=7) <= today() else None,
        "hours": range(GRID_START // 60, GRID_END // 60), "ppm": PPM, "grid_start": GRID_START,
        "grid_height": (GRID_END - GRID_START) * PPM, "sync": db.sync_states(db.connect()),
        "collect_end": min(days[-1], today()),
        "is_current_week": monday == today() - timedelta(days=today().weekday()),
        "weekly": weekly_state(db.connect(), monday),
        "categories": cfg["timesheet"]["categories"], "category_class": CATEGORY_CLASS,
        "step": cfg["timesheet"].get("block_step_minutes", 15), "grid_end": GRID_END,
    })


def timesheet_column(request: Request, d: str, generate_now: bool = False, force: bool = False):
    day = date.fromisoformat(d)
    ctx = {"day": day, "ppm": PPM, "grid_start": GRID_START, "grid_height": (GRID_END - GRID_START) * PPM,
           "blocks": [], "warnings": [], "state": "ok", "error": None, "total": 0, "is_today": day == today(),
           "edited": False}
    if day > today() or not is_workday(day, holidays()):
        ctx["state"] = "future" if day > today() else "holiday"
        return templates.TemplateResponse(request, "_timesheet_day.html", ctx)

    con = db.connect()
    ts_cfg = effective_config(cfg, con)["timesheet"]   # con el horario de la persona si lo ha cambiado
    ctx["step"] = ts_cfg.get("block_step_minutes", 15)
    if generate_now and force:
        db.delete_summary(con, d, TIMESHEET_EDIT)        # regenerar descarta lo editado a mano
    edit = db.get_summary(con, d, TIMESHEET_EDIT)
    if edit:   # la persona ha movido o cambiado bloques: mandan sobre lo calculado
        blocks = parse_edited(edit["content_md"], ts_cfg["categories"], ctx["step"])
        ctx.update(blocks=blocks, edited=True, total=sum(b.minutes for b in blocks), text=as_text(blocks),
                   warnings=short_day_warning(blocks, ts_cfg))
        return templates.TemplateResponse(request, "_timesheet_day.html", ctx)

    inputs = timesheet_inputs(con, day, cfg)
    commits, cats = inputs["commits"], ts_cfg["categories"]
    text = None
    if not inputs["has_work"]:
        ctx["state"] = "empty"
    elif generate_now:
        try:
            text, _ = generate(con, cfg, "timesheet", d, inputs["context"], force=force,
                               validate=lambda t: parse_tasks(t, commits, cats))
        except ClaudeError as e:
            ctx["error"] = str(e)
    cached = db.get_summary(con, d, "timesheet")
    if inputs["has_work"] and text is None:
        if cached:
            text = cached["content_md"]
            ctx["stale"] = cached["input_hash"] != input_hash(cfg, "timesheet", inputs["context"])
        else:
            ctx["state"] = "pending"
    tasks = parse_tasks(text, commits, cats) if text else []
    if ctx["state"] in ("ok", "empty"):
        ctx["blocks"], ctx["warnings"] = build_blocks(ts_cfg, inputs["meetings"], commits, tasks)
        ctx["total"] = sum(b.minutes for b in ctx["blocks"] if b.title != "Por definir")
        ctx["text"] = as_text([b for b in ctx["blocks"] if b.title != "Por definir"])
    return templates.TemplateResponse(request, "_timesheet_day.html", ctx)


TIMESHEET_EDIT = "timesheet_edit"   # summaries.kind de los bloques de un día editados a mano (JSON)


@app.post("/timesheet/day/{d}/blocks", response_class=HTMLResponse)
async def timesheet_day_edit(request: Request, d: str):
    """Guarda los bloques de un día tal como los ha dejado la persona en la rejilla."""
    day = date.fromisoformat(d)
    if day > today():
        return Response("Ese día aún no ha llegado.", status_code=422)
    form = await request.form()
    con = db.connect()
    ts_cfg = effective_config(cfg, con)["timesheet"]
    try:
        blocks = parse_edited(form.get("blocks", ""), ts_cfg["categories"], ts_cfg.get("block_step_minutes", 15))
    except ValueError as e:
        return Response(str(e), status_code=422)
    db.save_summary(con, d, TIMESHEET_EDIT, edited_json(blocks), "")
    return timesheet_column(request, d)


@app.post("/timesheet/day/{d}/blocks/reset", response_class=HTMLResponse)
def timesheet_day_reset(request: Request, d: str):
    """Descarta lo editado a mano: el día vuelve a la propuesta calculada."""
    db.delete_summary(db.connect(), d, TIMESHEET_EDIT)
    return timesheet_column(request, d)


@app.get("/timesheet/day/{d}", response_class=HTMLResponse)
def timesheet_day(request: Request, d: str):
    return timesheet_column(request, d)


@app.post("/timesheet/day/{d}", response_class=HTMLResponse)
def timesheet_day_generate(request: Request, d: str, force: bool = False):
    return timesheet_column(request, d, generate_now=True, force=force)


@app.post("/standup/{d}", response_class=HTMLResponse)
def standup(request: Request, d: str, force: bool = False):
    day = date.fromisoformat(d)
    if day != effective_today(today(), holidays())[0]:   # el stand-up es solo del día en curso
        return Response("El stand-up solo se genera para hoy.", status_code=409)
    con = db.connect()
    error, cached = None, False
    context = standup_context(con, day, holidays())
    context["ejemplos_formato"] = standup_examples(con).get("examples") or []   # su formato, no uno fijo
    try:
        text, cached = generate(con, cfg, "standup", d, context, force=force)
    except ClaudeError as e:
        error = str(e)
        last = db.get_summary(con, d, "standup")  # conserva el último resultado
        text = last["content_md"] if last else ""
    return templates.TemplateResponse(request, "_standup.html", {
        "day": day, "prev": previous_workday(day, holidays()), "text": standup_markdown(text), "error": error})


def weekly_state(con, monday: date) -> dict:
    """Resumen de la semana guardado y si los datos han cambiado desde que se generó."""
    ctx = weekly_context(con, monday, today(), holidays())
    saved = db.get_summary(con, monday.isoformat(), "weekly_summary")
    return {"context": ctx, "has_data": bool(ctx), "text": saved["content_md"] if saved else None,
            "stale": bool(saved and ctx) and saved["input_hash"] != input_hash(cfg, "weekly_summary", ctx)}


@app.post("/weekly/{d}", response_class=HTMLResponse)
def weekly_summary(request: Request, d: str, force: bool = False):
    """Redacta (o devuelve guardado) el resumen de la semana de `d` a partir del diario y los commits."""
    monday = date.fromisoformat(d) - timedelta(days=date.fromisoformat(d).weekday())
    con = db.connect()
    state, error = weekly_state(con, monday), None
    if state["has_data"]:
        try:
            state["text"], _ = generate(con, cfg, "weekly_summary", monday.isoformat(), state["context"], force=force)
            state["stale"] = False
        except ClaudeError as e:
            error = str(e)   # se conserva el último resumen guardado
    return templates.TemplateResponse(request, "_weekly.html", {"monday": monday, **state, "error": error})


def journal_notes_state(con, day: date) -> dict:
    """Borrador guardado de las notas del diario y si hay commits nuevos desde que se generó."""
    ctx = journal_notes_context(con, day, cfg["user"]["timezone"])
    saved = db.get_summary(con, day.isoformat(), "journal_notes")
    return {"context": ctx, "has_commits": bool(ctx["commits"]), "text": saved["content_md"] if saved else None,
            "stale": bool(saved) and saved["input_hash"] != input_hash(cfg, "journal_notes", ctx)}


@app.post("/journal-notes/{d}", response_class=HTMLResponse)
def journal_notes(request: Request, d: str, force: bool = False):
    """Redacta (o devuelve guardadas) las notas del día para el diario a partir de los commits."""
    day = date.fromisoformat(d)
    collect(day, day, only={"notion"})   # lo último que haya escrito a mano ese día, para no pisarlo
    con = db.connect()
    state, error = journal_notes_state(con, day), None
    if state["has_commits"]:
        try:
            state["text"], _ = generate(con, cfg, "journal_notes", d, state["context"], force=force)
            state["stale"] = False
        except ClaudeError as e:
            error = str(e)   # se conserva el último borrador guardado
    return templates.TemplateResponse(request, "_card_journal_notes.html", {
        "day": day, "text": state["text"], "stale": state["stale"], "has_commits": state["has_commits"],
        "error": error, "is_today": day == effective_today(today(), holidays())[0]})


def main():
    s = cfg["server"]
    uvicorn.run("web.app:app", host=s.get("host", "127.0.0.1"), port=s.get("port", 8765))


if __name__ == "__main__":
    main()
