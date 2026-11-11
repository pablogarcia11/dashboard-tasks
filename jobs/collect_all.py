"""Ejecuta los colectores activos y guarda el resultado en SQLite.

Uso:
  python -m jobs.collect_all                     # hoy y el día laborable anterior
  python -m jobs.collect_all --date 2026-11-10   # un día concreto
  python -m jobs.collect_all --since 2026-11-03 --until 2026-11-10 --show
"""
import argparse
import sqlite3
from datetime import date, datetime

from collectors.gcal import GcalCollector
from collectors.git_local import GitLocalCollector
from collectors.notion import NotionCollector
from core import db
from core.config import load_config
from core.dates import day_bounds, previous_workday


def run_collect(cfg: dict, con: sqlite3.Connection, start: date, end: date) -> list[str]:
    """Recoge [start, end] de las fuentes activas. Devuelve líneas de resumen (y avisos)."""
    tz = cfg["user"]["timezone"]
    today = datetime.now().astimezone().date()
    since, until = day_bounds(start, tz)[0], day_bounds(end, tz)[1]
    sources, report = cfg["sources"], []

    if sources["git"]["enabled"]:
        git = GitLocalCollector(cfg)
        items = git.collect(since, until, include_wip=end >= today)
        commits = [i for i in items if i.kind == "commit"]
        db.upsert_activities(con, commits)
        if end >= today:
            db.replace_kind(con, "git", "wip", [i for i in items if i.kind == "wip"])
        db.set_sync_state(con, "git", "; ".join(git.errors) or None)
        report.append(f"git: {len(commits)} commits, {len(items) - len(commits)} repos con trabajo sin commitear")
        report += [f"  aviso: {e}" for e in git.errors]

    if sources["notion"]["enabled"]:
        try:
            notion = NotionCollector(cfg)
            journal = notion.collect_journal(start, end)
            db.replace_range(con, "notion", ["note", "task_plan"], start.isoformat(), end.isoformat(), journal)
            tasks = notion.collect_tasks()
            db.replace_kind(con, "notion", "task", tasks)
            db.set_sync_state(con, "notion")
            pending = sum(1 for i in journal if i.kind == "task_plan")
            report.append(f"notion: {len(journal) - pending} notas y {pending} pendientes en I'M BACK, "
                          f"{len(tasks)} tareas activas")
        except Exception as e:  # una fuente caída no debe tumbar las demás
            db.set_sync_state(con, "notion", str(e))
            report.append(f"notion: error: {e}")
    if sources["gcal"]["enabled"]:
        try:
            meetings = GcalCollector(cfg).collect(start, end)
            db.replace_range(con, "gcal", ["meeting"], start.isoformat(), end.isoformat(), meetings)
            db.set_sync_state(con, "gcal")
            report.append(f"gcal: {len(meetings)} reuniones")
        except Exception as e:
            db.set_sync_state(con, "gcal", str(e))
            report.append(f"gcal: error: {e}")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--show", action="store_true", help="muestra la actividad guardada del rango")
    args = ap.parse_args()

    cfg = load_config()
    today = datetime.now().astimezone().date()
    if args.date:
        start = end = date.fromisoformat(args.date)
    elif args.since:
        start = date.fromisoformat(args.since)
        end = date.fromisoformat(args.until) if args.until else today
    else:
        start, end = previous_workday(today, cfg["schedule"].get("holidays", [])), today

    con = db.connect()
    for line in run_collect(cfg, con, start, end):
        print(line)

    if args.show:
        for a in db.activities(con, start.isoformat(), end.isoformat()):
            x = a["extra"]
            local = "" if x.get("pushed", True) else "  [solo local]"
            hora = a["ts"][11:16] if a["kind"] == "commit" else "     "
            where = x.get("repo") or a["kind"]
            print(f"{a['work_date']} {hora}  {a['project'][:14]:<14} {where[:28]:<28} {a['title'][:70]}{local}")


if __name__ == "__main__":
    main()
