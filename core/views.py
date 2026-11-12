"""Consultas que preparan los datos de cada vista y el contexto que se envía a Claude."""
import re
import sqlite3
from collections import defaultdict
from datetime import date, timedelta

from core import db
from core.dates import previous_workday
from core.timesheet import minute_of


def group_by_project(items: list[dict]) -> dict[str, list[dict]]:
    groups = defaultdict(list)
    for a in items:
        groups[a["project"] or "Sin proyecto"].append(a)
    return dict(groups)


LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
SLACK_BULLET = re.compile(r"^([ \t]*)([•◦▪▫‣])\s+")
SLACK_BOLD = re.compile(r"(?<![*\w])\*(?![\s*])([^*\n]+?)(?<!\s)\*(?![*\w])")   # *texto*, no **texto**


def standup_markdown(text: str) -> str:
    """Deja el stand-up en Markdown estándar, que es lo que Slack convierte en formato al pegarlo:
    - restos del formato interno de Slack: `*negrita*` → `**negrita**`, viñetas • / ◦ → `- `
      (◦ o sangría = subviñeta, 4 espacios por nivel);
    - línea en blanco entre el final de una lista y el texto siguiente; sin ella, Markdown trata ese
      texto como continuación del último elemento de la lista."""
    out: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        m = SLACK_BULLET.match(line)
        if m:
            level = max(len(m.group(1).replace("\t", "    ")) // 4, 1 if m.group(2) in "◦▫" else 0)
            line = "    " * level + "- " + line[m.end():]
        line = SLACK_BOLD.sub(r"**\1**", line)
        if line.strip() and not LIST_ITEM.match(line) and out and LIST_ITEM.match(out[-1]):
            out.append("")
        out.append(line)
    return "\n".join(out)


def visible_git(items: list[dict], settings: dict) -> list[dict]:
    """Quita la actividad de git de los repos ocultos en Ajustes (y el WIP si se ocultó solo eso)."""
    out = []
    for a in items:
        s = settings.get(a["extra"].get("repo", ""), {})
        if a["source"] == "git" and (not s.get("visible", True)
                                     or (a["kind"] == "wip" and not s.get("show_wip", True))):
            continue
        out.append(a)
    return out


def day_data(con: sqlite3.Connection, day: date, holidays=()) -> dict:
    """Todo lo de un día laborable: notas, commits, pendientes del día anterior, tareas y WIP."""
    d = day.isoformat()
    settings = db.repo_settings(con)
    acts = visible_git(db.activities(con, d, d), settings)
    prev = previous_workday(day, holidays).isoformat()
    git_now = visible_git(db.activities(con, prev, d, ["git"]), settings)
    unpushed = [a for a in git_now if a["kind"] == "commit" and not a["extra"].get("pushed", True)]
    return {
        "notes": group_by_project([a for a in acts if a["kind"] == "note"]),
        "commits": group_by_project([a for a in acts if a["kind"] == "commit"]),
        "meetings": [a for a in acts if a["kind"] == "meeting"],
        "pending_from_prev": group_by_project(
            [a for a in db.activities(con, prev, prev, ["notion"]) if a["kind"] == "task_plan"]),
        # Instantáneas del estado actual (solo tienen sentido para hoy)
        "tasks": [a for a in db.activities(con, "0000-00-00", "9999-99-99", ["notion"]) if a["kind"] == "task"],
        "wip": visible_git([a for a in db.activities(con, "0000-00-00", "9999-99-99", ["git"])
                            if a["kind"] == "wip"], settings),
        "unpushed": unpushed,
        "unpushed_repos": unpushed_by_repo(unpushed),
    }


def unpushed_by_repo(unpushed: list[dict]) -> list[dict]:
    """Commits sin subir agrupados por repo (el detalle de cada commit ya está en la tarjeta Commits)."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in unpushed:
        groups[c["extra"].get("repo", "")].append(c)
    return [{"repo": repo, "count": len(cs), "titles": [c["title"] for c in cs]} for repo, cs in groups.items()]


def week_overview(con: sqlite3.Connection, day: date, today: date, holidays=()) -> list[dict]:
    """Los cinco días de la semana de `day` y cómo está el diario en cada uno:
    'notes' (hay notas), 'missing' (hay commits pero no notas: falta apuntar), 'empty' (sin actividad),
    'future' o 'holiday'."""
    monday = day - timedelta(days=day.weekday())
    days = [monday + timedelta(days=i) for i in range(5)]
    settings = db.repo_settings(con)
    acts = visible_git(db.activities(con, days[0].isoformat(), days[-1].isoformat()), settings)
    noted = {a["work_date"] for a in acts if a["kind"] == "note"}
    committed = {a["work_date"] for a in acts if a["kind"] == "commit"}
    out = []
    for d in days:
        iso = d.isoformat()
        if d > today:
            state = "future"
        elif iso in holidays:
            state = "holiday"
        elif iso in noted:
            state = "notes"
        else:
            state = "missing" if iso in committed else "empty"
        out.append({"date": d, "state": state, "selected": d == day, "today": d == today})
    return out


def unnoted_days(con: sqlite3.Connection, today: date, holidays=(), lookback: int = 21) -> list[date]:
    """Días laborables anteriores a hoy (últimas tres semanas) con commits y sin ninguna nota en el
    diario: lo que falta por apuntar. Del más reciente al más antiguo."""
    start = today - timedelta(days=lookback)
    acts = visible_git(db.activities(con, start.isoformat(), (today - timedelta(days=1)).isoformat()),
                       db.repo_settings(con))
    noted = {a["work_date"] for a in acts if a["kind"] == "note"}
    committed = {a["work_date"] for a in acts if a["kind"] == "commit"}
    days = [date.fromisoformat(d) for d in committed - noted]
    return sorted((d for d in days if d.weekday() < 5 and d.isoformat() not in holidays), reverse=True)


def timesheet_inputs(con: sqlite3.Connection, day: date, cfg: dict) -> dict:
    """Datos del parte de horas de un día: contexto para Claude y datos para el cálculo horario."""
    tz = cfg["user"]["timezone"]
    d = day.isoformat()
    acts = visible_git(db.activities(con, d, d), db.repo_settings(con))
    commits = [{"sha": a["extra"]["sha"], "minute": minute_of(a["ts"], tz), "project": a["project"],
                "subject": a["title"], "repo": a["extra"].get("repo", ""),
                "size": f"+{a['extra'].get('insertions', 0)} -{a['extra'].get('deletions', 0)}"}
               for a in acts if a["kind"] == "commit"]
    meetings = [{"start": minute_of(a["extra"]["start"], tz), "end": minute_of(a["extra"]["end"], tz),
                 "title": a["title"], "project": a["project"]} for a in acts if a["kind"] == "meeting"]
    notes = group_by_project([a for a in acts if a["kind"] == "note"])
    context = {
        "fecha": d,
        "commits": [{"sha": c["sha"], "hora": f"{c['minute'] // 60:02d}:{c['minute'] % 60:02d}",
                     "proyecto": c["project"], "repo": c["repo"], "mensaje": c["subject"], "tamaño": c["size"]}
                    for c in sorted(commits, key=lambda c: c["minute"])],
        "notas_im_back": {p: [{"tarea": n["title"], "detalle": n["body"][:400]} for n in ns]
                          for p, ns in notes.items()},
        "reuniones": [f"{m['title']} ({m['project']})" for m in meetings],
        "categorias": cfg["timesheet"]["categories"],
    }
    return {"context": context, "commits": commits, "meetings": meetings,
            "has_work": bool(commits or notes)}


WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def journal_heading(day: date) -> str:
    """Encabezado del día con el formato del diario: «Martes 10/11/2026»."""
    return f"{WEEKDAYS[day.weekday()]} {day.day:02d}/{day.month:02d}/{day.year}"


def written_journal_md(con: sqlite3.Connection, day: date) -> str:
    """Lo que la persona ya apuntó ese día en su diario, en el mismo Markdown que se genera."""
    d = day.isoformat()
    notes = [a for a in db.activities(con, d, d, ["notion"]) if a["kind"] in ("note", "task_plan")]
    lines = []
    for project, items in group_by_project(notes).items():
        lines.append(f"### {project}")
        done = [a for a in items if a["kind"] == "note"]
        pending = [a for a in items if a["kind"] == "task_plan"]
        for a in done:
            lines.append(f"- {a['title']}")
            lines += [f"  {sub}" for sub in (a["body"] or "").splitlines() if sub.strip()]
        if pending:
            lines.append("- Pendiente:")
            lines += [f"  - {a['title']}" for a in pending]
    return "\n".join(lines)


def journal_notes_context(con: sqlite3.Connection, day: date, tz: str) -> dict:
    """Lo ya escrito en el diario ese día y los commits (repos visibles) por proyecto, para completar
    las notas del diario sin perder nada de lo escrito a mano."""
    d = day.isoformat()
    commits = [a for a in visible_git(db.activities(con, d, d, ["git"]), db.repo_settings(con))
               if a["kind"] == "commit"]
    by_project = {}
    for a in sorted(commits, key=lambda a: a["ts"]):
        m = minute_of(a["ts"], tz)
        x = a["extra"]
        by_project.setdefault(a["project"] or "Sin proyecto", []).append({
            "hora": f"{m // 60:02d}:{m % 60:02d}", "repo": x.get("repo", ""), "mensaje": a["title"],
            "cambios": f"{x.get('files', 0)} ficheros, +{x.get('insertions', 0)} -{x.get('deletions', 0)}",
        })
    return {"encabezado_dia": journal_heading(day), "ya_escrito": written_journal_md(con, day), "commits": by_project}


def weekly_context(con: sqlite3.Connection, monday: date, today: date, holidays=()) -> dict:
    """Contexto del resumen de la semana: por día, notas del diario (lo hecho), commits y reuniones;
    y lo último que quedó pendiente. Solo días laborables hasta hoy."""
    friday = monday + timedelta(days=4)
    days = [d for d in (monday + timedelta(days=i) for i in range(5))
            if d <= today and d.isoformat() not in holidays]
    if not days:
        return {}
    settings = db.repo_settings(con)
    acts = visible_git(db.activities(con, days[0].isoformat(), days[-1].isoformat()), settings)
    by_day = []
    pending: dict[str, list[str]] = {}
    for d in days:
        iso = d.isoformat()
        mine = [a for a in acts if a["work_date"] == iso]
        notes = group_by_project([a for a in mine if a["kind"] == "note"])
        commits = group_by_project([a for a in mine if a["kind"] == "commit"])
        plans = group_by_project([a for a in mine if a["kind"] == "task_plan"])
        if plans:
            pending = {p: [a["title"] for a in items] for p, items in plans.items()}
        if not (notes or commits):
            continue
        by_day.append({
            "dia": journal_heading(d),
            "notas": {p: [a["title"] + (f" ({a['body'][:300]})" if a["body"] else "") for a in items]
                      for p, items in notes.items()},
            "commits": {p: [a["title"] for a in items] for p, items in commits.items()},
            "reuniones": [{"reunion": a["title"], "proyecto": a["project"]} for a in mine if a["kind"] == "meeting"],
        })
    if not by_day:
        return {}
    return {"semana": f"del {WEEKDAYS[0].lower()} {monday.day} al {WEEKDAYS[4].lower()} {friday.day} de "
                      f"{MONTHS[friday.month - 1]} de {friday.year}",
            "dias": by_day, "pendiente": pending}


MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
          "octubre", "noviembre", "diciembre"]


def standup_context(con: sqlite3.Connection, today: date, holidays=()) -> dict:
    """Contexto recortado para el stand-up: solo títulos, nunca diffs."""
    yesterday = previous_workday(today, holidays)
    y = day_data(con, yesterday, holidays)
    t = day_data(con, today, holidays)
    return {
        "ayer": {
            "fecha": yesterday.isoformat(),
            "notas_im_back": {p: [{"tarea": n["title"], "detalle": n["body"][:600]} for n in notes]
                              for p, notes in y["notes"].items()},
            "commits": {p: [c["title"] for c in cs] for p, cs in y["commits"].items()},
            "reuniones": [{"reunion": m["title"], "proyecto": m["project"]} for m in y["meetings"]],
        },
        "hoy": {
            "fecha": today.isoformat(),
            "pendientes_de_ayer": {p: [n["title"] for n in ns] for p, ns in t["pending_from_prev"].items()},
            "tareas_activas": [{"tarea": a["title"], "estado": a["status"]} for a in t["tasks"]],
            "reuniones": [{"reunion": m["title"], "proyecto": m["project"]} for m in t["meetings"]],
            "trabajo_sin_terminar": [f"{w['project']}: {w['title']}" for w in t["wip"]]
                                    + [f"{c['project']}: commit sin subir «{c['title']}»" for c in t["unpushed"]],
        },
    }
