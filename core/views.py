"""Consultas que preparan los datos de cada vista y el contexto que se envía a Claude."""
import sqlite3
from collections import defaultdict
from datetime import date

from core import db
from core.dates import previous_workday
from core.timesheet import minute_of


def group_by_project(items: list[dict]) -> dict[str, list[dict]]:
    groups = defaultdict(list)
    for a in items:
        groups[a["project"] or "Sin proyecto"].append(a)
    return dict(groups)


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
        "unpushed": [a for a in git_now if a["kind"] == "commit" and not a["extra"].get("pushed", True)],
    }


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
            "reuniones": [m["title"] for m in y["meetings"]],
        },
        "hoy": {
            "fecha": today.isoformat(),
            "pendientes_de_ayer": {p: [n["title"] for n in ns] for p, ns in t["pending_from_prev"].items()},
            "tareas_activas": [{"tarea": a["title"], "estado": a["status"]} for a in t["tasks"]],
            "reuniones": [m["title"] for m in t["meetings"]],
            "trabajo_sin_terminar": [f"{w['project']}: {w['title']}" for w in t["wip"]]
                                    + [f"{c['project']}: commit sin subir «{c['title']}»" for c in t["unpushed"]],
        },
    }
