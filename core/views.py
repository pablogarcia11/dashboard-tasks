"""Consultas que preparan los datos de cada vista y el contexto que se envía a Claude."""
import sqlite3
from collections import defaultdict
from datetime import date

from core import db
from core.dates import previous_workday


def group_by_project(items: list[dict]) -> dict[str, list[dict]]:
    groups = defaultdict(list)
    for a in items:
        groups[a["project"] or "Sin proyecto"].append(a)
    return dict(groups)


def day_data(con: sqlite3.Connection, day: date, holidays=()) -> dict:
    """Todo lo de un día laborable: notas, commits, pendientes del día anterior, tareas y WIP."""
    d = day.isoformat()
    acts = db.activities(con, d, d)
    prev = previous_workday(day, holidays).isoformat()
    return {
        "notes": group_by_project([a for a in acts if a["kind"] == "note"]),
        "commits": group_by_project([a for a in acts if a["kind"] == "commit"]),
        "meetings": [a for a in acts if a["kind"] == "meeting"],
        "pending_from_prev": group_by_project(
            [a for a in db.activities(con, prev, prev, ["notion"]) if a["kind"] == "task_plan"]),
        # Instantáneas del estado actual (solo tienen sentido para hoy)
        "tasks": [a for a in db.activities(con, "0000-00-00", "9999-99-99", ["notion"]) if a["kind"] == "task"],
        "wip": [a for a in db.activities(con, "0000-00-00", "9999-99-99", ["git"]) if a["kind"] == "wip"],
        "unpushed": [a for a in db.activities(con, prev, d, ["git"])
                     if a["kind"] == "commit" and not a["extra"].get("pushed", True)],
    }


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
