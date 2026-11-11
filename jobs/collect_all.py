"""Ejecuta los colectores activos y guarda el resultado en SQLite.

Uso:
  python -m jobs.collect_all                     # hoy y el día laborable anterior
  python -m jobs.collect_all --date 2026-11-10   # un día concreto
  python -m jobs.collect_all --since 2026-11-03 --until 2026-11-10 --show
"""
import argparse
from datetime import date, datetime

from collectors.git_local import GitLocalCollector
from core import db
from core.config import load_config
from core.dates import day_bounds, previous_workday


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--show", action="store_true", help="muestra la actividad guardada del rango")
    args = ap.parse_args()

    cfg = load_config()
    tz = cfg["user"]["timezone"]
    holidays = cfg["schedule"].get("holidays", [])
    today = datetime.now().astimezone().date()
    if args.date:
        start = end = date.fromisoformat(args.date)
    elif args.since:
        start = date.fromisoformat(args.since)
        end = date.fromisoformat(args.until) if args.until else today
    else:
        start, end = previous_workday(today, holidays), today
    since, until = day_bounds(start, tz)[0], day_bounds(end, tz)[1]

    con = db.connect()
    if cfg["sources"]["git"]["enabled"]:
        git = GitLocalCollector(cfg)
        items = git.collect(since, until, include_wip=end >= today)
        commits = [i for i in items if i.kind == "commit"]
        db.upsert_activities(con, commits)
        if end >= today:
            db.replace_kind(con, "git", "wip", [i for i in items if i.kind == "wip"])
        db.set_sync_state(con, "git", "; ".join(git.errors) or None)
        print(f"git: {len(commits)} commits, {len(items) - len(commits)} con trabajo sin commitear")
        for e in git.errors:
            print("  aviso:", e)

    if args.show:
        for a in db.activities(con, start.isoformat(), end.isoformat()):
            x = a["extra"]
            local = "" if x.get("pushed", True) else "  [solo local]"
            hora = a["ts"][11:16] if a["kind"] == "commit" else "     "
            print(f"{a['work_date']} {hora}  {a['project']:<14} {x.get('repo', ''):<28} {a['title'][:70]}{local}")


if __name__ == "__main__":
    main()
