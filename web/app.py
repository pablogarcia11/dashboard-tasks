"""Dashboard web local (FastAPI + Jinja2 + HTMX). Escucha solo en 127.0.0.1.

Uso:  python -m web.app
"""
import threading
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from collectors.git_local import GitLocalCollector
from core import db
from core.config import ROOT, load_config
from core.dates import effective_today, is_workday, next_workday, previous_workday
from core.timesheet import as_text, build_blocks, fmt, parse_tasks
from core.views import day_data, standup_context, timesheet_inputs
from jobs.collect_all import run_collect
from llm.claude_cli import ClaudeError, generate, input_hash

WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
          "octubre", "noviembre", "diciembre"]

cfg = load_config()
HOLIDAYS = cfg["schedule"].get("holidays", [])
collect_lock = threading.Lock()


def today() -> date:
    return datetime.now().astimezone().date()


def collect(start: date, end: date, only=None) -> list[str]:
    with collect_lock:  # SQLite + colectores: una recogida cada vez
        return run_collect(cfg, db.connect(), start, end, only)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Al arrancar, refresca el día laborable anterior y hoy sin bloquear el servidor
    t = today()
    threading.Thread(target=collect, args=(previous_workday(t, HOLIDAYS), t), daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "web" / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "web" / "templates")
templates.env.filters["long_date"] = lambda d: f"{WEEKDAYS[d.weekday()]} {d.day} de {MONTHS[d.month - 1]}"
templates.env.filters["title_date"] = lambda d: f"{WEEKDAYS[d.weekday()].capitalize()} {d.day} de {MONTHS[d.month - 1]} {d.year}"
templates.env.filters["hhmm"] = lambda ts: ts[11:16]
# Qué hacer cuando falla cada fuente (se muestra junto al error)
templates.env.globals["sync_hints"] = {
    "git": "Comprueba que el repo existe y que git funciona en él; si el aviso habla de «dubious ownership», revisa la configuración de git del repo.",
    "notion": "Si el permiso caducó o se revocó, vuelve a autorizar con: python -m collectors.notion_auth",
    "gcal": "Reconecta Google Calendar en claude.ai → Configuración → Conectores, marcando todos los permisos, y pulsa «Actualizar datos».",
}
templates.env.globals["claude_hint"] = ("Si es un límite de uso de Claude, espera unos minutos y vuelve a intentarlo; "
                                        "si dice que falta iniciar sesión, ejecuta «claude» en una terminal.")
# Logo oficial: se muestra si existe web/static/logo.png (no se versiona una copia recreada)
templates.env.globals["has_logo"] = (ROOT / "web" / "static" / "logo.png").is_file()


@app.get("/")
def index():
    shown, _ = effective_today(today(), HOLIDAYS)
    return RedirectResponse(f"/day/{shown.isoformat()}")


@app.get("/day/{d}", response_class=HTMLResponse)
def day_view(request: Request, d: str):
    requested = date.fromisoformat(d)
    shown, weekend = effective_today(requested, HOLIDAYS)
    if shown != requested and requested != today():
        return RedirectResponse(f"/day/{shown.isoformat()}")
    con = db.connect()
    nxt = next_workday(shown, HOLIDAYS)
    return templates.TemplateResponse(request, "day.html", {
        "day": shown, "is_today": shown == effective_today(today(), HOLIDAYS)[0], "weekend": weekend,
        "prev": previous_workday(shown, HOLIDAYS), "next": nxt if nxt <= today() else None,
        "data": day_data(con, shown, HOLIDAYS), "sync": db.sync_states(con),
        "standup": db.get_summary(con, shown.isoformat(), "standup"),
    })


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
    return templates.TemplateResponse(request, template, {
        "day": day, "is_today": day == effective_today(today(), HOLIDAYS)[0],
        "data": day_data(con, day, HOLIDAYS), "refresh_error": error, "refreshed": not error,
    })


@app.get("/settings", response_class=HTMLResponse)
def settings_view(request: Request):
    git = GitLocalCollector(cfg)
    repos = sorted(git.repos(), key=lambda r: (r.project.lower(), str(r.path).lower()))
    mains = {r.common_dir: r for r in repos if not r.is_worktree}
    settings = db.repo_settings(db.connect())
    rows = []
    for r in repos:
        rel = r.path.relative_to(git.root).as_posix()
        main = mains.get(r.common_dir)
        rows.append({"repo": rel, "project": r.project, **settings.get(rel, {"visible": True, "show_wip": True}),
                     "worktree_of": main.path.relative_to(git.root).as_posix() if r.is_worktree and main else None})
    return templates.TemplateResponse(request, "settings.html", {
        "rows": rows, "excluded": cfg["git"].get("exclude_repos", []), "root": str(git.root)})


@app.post("/settings/repo")
async def settings_repo(request: Request):
    form = await request.form()
    # Un checkbox desmarcado no envía "value"
    db.set_repo_setting(db.connect(), form["repo"], form["field"], form.get("value") == "on")
    return Response(status_code=204)


@app.post("/collect/{d}")
def collect_day(d: str):
    day = date.fromisoformat(d)
    collect(previous_workday(day, HOLIDAYS), day)
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
    shown, _ = effective_today(today(), HOLIDAYS)
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
    })


def timesheet_column(request: Request, d: str, generate_now: bool = False, force: bool = False):
    day = date.fromisoformat(d)
    ctx = {"day": day, "ppm": PPM, "grid_start": GRID_START, "grid_height": (GRID_END - GRID_START) * PPM,
           "blocks": [], "warnings": [], "state": "ok", "error": None, "total": 0}
    if day > today() or not is_workday(day, HOLIDAYS):
        ctx["state"] = "future" if day > today() else "holiday"
        return templates.TemplateResponse(request, "_timesheet_day.html", ctx)

    con = db.connect()
    inputs = timesheet_inputs(con, day, cfg)
    commits, cats = inputs["commits"], cfg["timesheet"]["categories"]
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
        ctx["blocks"], ctx["warnings"] = build_blocks(cfg["timesheet"], inputs["meetings"], commits, tasks)
        ctx["total"] = sum(b.minutes for b in ctx["blocks"] if b.title != "Por definir")
        ctx["text"] = as_text([b for b in ctx["blocks"] if b.title != "Por definir"])
    return templates.TemplateResponse(request, "_timesheet_day.html", ctx)


@app.get("/timesheet/day/{d}", response_class=HTMLResponse)
def timesheet_day(request: Request, d: str):
    return timesheet_column(request, d)


@app.post("/timesheet/day/{d}", response_class=HTMLResponse)
def timesheet_day_generate(request: Request, d: str, force: bool = False):
    return timesheet_column(request, d, generate_now=True, force=force)


@app.post("/standup/{d}", response_class=HTMLResponse)
def standup(request: Request, d: str, force: bool = False):
    day = date.fromisoformat(d)
    con = db.connect()
    error, cached = None, False
    try:
        text, cached = generate(con, cfg, "standup", d, standup_context(con, day, HOLIDAYS), force=force)
    except ClaudeError as e:
        error = str(e)
        last = db.get_summary(con, d, "standup")  # conserva el último resultado
        text = last["content_md"] if last else ""
    return templates.TemplateResponse(request, "_standup.html",
                                      {"day": day, "text": text, "error": error, "cached": cached})


def main():
    s = cfg["server"]
    uvicorn.run("web.app:app", host=s.get("host", "127.0.0.1"), port=s.get("port", 8765))


if __name__ == "__main__":
    main()
